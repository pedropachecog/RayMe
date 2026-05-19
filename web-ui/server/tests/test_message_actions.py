"""Message-action contracts and API integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.messages import get_message_action_session, get_message_completion_client
from app.config import Settings
from app.domain import message_actions
from app.domain.llm_stream import ChatCompletionSettings
from app.domain.message_actions import MessageGenerationContext, SqlAlchemyMessageActionRepository
from app.domain.prompt_builder import SqlAlchemyPromptRepository, build_prompt_context
from app.domain.settings_service import SETTINGS_KEY
from app.domain.thread_service import ThreadService
from app.main import create_app
from app.storage.models import (
    AppSetting,
    Base,
    Character,
    Message,
    MessageAlternate,
    MessageAlternateShape,
    ThreadMessageShape,
)
from app.storage.session import create_engine

SERVER_SETTINGS = ChatCompletionSettings(
    base_url="http://llm.local/v1",
    model="configured-model",
    api_key="server-secret",
)


class ScriptedActionRepository:
    def __init__(self) -> None:
        self.messages = {
            "user-1": ThreadMessageShape(
                id="user-1",
                thread_id="thread-1",
                message_kind="user_text",
                role="user",
                sequence=1,
                content_text="Prompt from user",
            ),
            "ai-1": ThreadMessageShape(
                id="ai-1",
                thread_id="thread-1",
                message_kind="ai_text",
                role="assistant",
                sequence=2,
                content_text="Original AI response",
                alternates=[
                    MessageAlternateShape(
                        id="alt-0",
                        message_id="ai-1",
                        alternate_index=0,
                        content_text="Original AI response",
                        source_action="regenerate",
                    )
                ],
            ),
            "downstream-1": ThreadMessageShape(
                id="downstream-1",
                thread_id="thread-1",
                message_kind="user_text",
                role="user",
                sequence=3,
                content_text="Later user turn",
            ),
        }
        self.keep_choice_message_id: str | None = None
        self.truncated_after_message_id: str | None = None

    async def get_prompt_thread(self, thread_id: str) -> object:
        return {"id": thread_id, "messages": list(self.messages.values())}

    async def get_generation_context(
        self,
        message_id: str,
        *,
        include_target: bool,
    ) -> MessageGenerationContext:
        message = self.messages[message_id]
        return MessageGenerationContext(
            thread_id=message.thread_id,
            message_id=message.id,
            message_kind=message.message_kind,
            role=message.role,
            until_message_id=message.id if include_target else "user-1",
        )

    async def replace_selected_ai_response(
        self,
        message_id: str,
        content_text: str,
        *,
        source_action: str,
    ) -> ThreadMessageShape:
        alternate = MessageAlternateShape(
            id="alt-regenerated",
            message_id=message_id,
            alternate_index=1,
            content_text=content_text,
            source_action=source_action,
        )
        message = self.messages[message_id]
        updated = ThreadMessageShape(
            id=message.id,
            thread_id=message.thread_id,
            message_kind=message.message_kind,
            role=message.role,
            sequence=message.sequence,
            content_text=content_text,
            selected_alternate_id=alternate.id,
            alternates=[alternate],
            stale_after_edit=message.stale_after_edit,
        )
        self.messages[message_id] = updated
        return updated

    async def add_selected_alternate(
        self,
        message_id: str,
        content_text: str,
        *,
        source_action: str,
    ) -> ThreadMessageShape:
        message = self.messages[message_id]
        next_index = max(alternate.alternate_index for alternate in message.alternates) + 1
        alternate = MessageAlternateShape(
            id=f"alt-{source_action}",
            message_id=message_id,
            alternate_index=next_index,
            content_text=content_text,
            source_action=source_action,
        )
        updated = ThreadMessageShape(
            id=message.id,
            thread_id=message.thread_id,
            message_kind=message.message_kind,
            role=message.role,
            sequence=message.sequence,
            content_text=message.content_text,
            selected_alternate_id=alternate.id,
            alternates=[*message.alternates, alternate],
            stale_after_edit=message.stale_after_edit,
        )
        self.messages[message_id] = updated
        return updated

    async def select_alternate(self, message_id: str, alternate_id: str) -> ThreadMessageShape:
        message = self.messages[message_id]
        updated = ThreadMessageShape(
            id=message.id,
            thread_id=message.thread_id,
            message_kind=message.message_kind,
            role=message.role,
            sequence=message.sequence,
            content_text=message.content_text,
            selected_alternate_id=alternate_id,
            alternates=message.alternates,
            stale_after_edit=message.stale_after_edit,
        )
        self.messages[message_id] = updated
        return updated

    async def edit_message_and_mark_downstream_stale(
        self,
        message_id: str,
        content_text: str,
    ) -> ThreadMessageShape:
        message = self.messages[message_id]
        self.messages[message_id] = ThreadMessageShape(
            id=message.id,
            thread_id=message.thread_id,
            message_kind=message.message_kind,
            role=message.role,
            sequence=message.sequence,
            content_text=content_text,
            selected_alternate_id=message.selected_alternate_id,
            alternates=message.alternates,
        )
        downstream = self.messages["downstream-1"]
        self.messages["downstream-1"] = ThreadMessageShape(
            id=downstream.id,
            thread_id=downstream.thread_id,
            message_kind=downstream.message_kind,
            role=downstream.role,
            sequence=downstream.sequence,
            content_text=downstream.content_text,
            stale_after_edit=True,
        )
        return self.messages[message_id]

    async def truncate_stale_after(self, message_id: str) -> list[ThreadMessageShape]:
        self.truncated_after_message_id = message_id
        self.messages.pop("downstream-1")
        return list(self.messages.values())

    async def keep_stale_after(self, message_id: str) -> ThreadMessageShape:
        self.keep_choice_message_id = message_id
        return self.messages[message_id]

    def visible_ai_turns(self) -> list[ThreadMessageShape]:
        return [
            message
            for message in self.messages.values()
            if message.role == "assistant" and not message.stale_after_edit
        ]


class ScriptedCompletionClient:
    def __init__(self) -> None:
        self.tokens = ["Generated"]
        self.requests: list[dict[str, object]] = []

    async def stream_chat_completion_tokens(
        self,
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ):
        self.requests.append({"settings": settings, "messages": list(messages)})
        for token in self.tokens:
            yield token


@pytest.fixture()
def message_action_client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, async_sessionmaker, ScriptedCompletionClient]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-test.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    scripted_client = ScriptedCompletionClient()
    app = create_app(
        Settings(
            llm_base_url="http://server-llm.local/v1",
            llm_model="server-model",
            llm_api_key="server-secret",
        ),
        static_client_dir=None,
    )

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_message_action_session] = override_session
    app.dependency_overrides[get_message_completion_client] = lambda: scripted_client

    with TestClient(app) as client:
        yield client, sessionmaker, scripted_client

    asyncio.run(engine.dispose())


async def test_regenerate_calls_llm_and_replaces_selected_ai_response(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = ScriptedActionRepository()
    calls: list[tuple[str, object]] = []

    async def scripted_build_prompt_context(*args: object, **kwargs: object) -> list[dict[str, str]]:
        calls.append(("build_prompt_context", kwargs["action"]))
        assert kwargs["repository"] is repository
        assert kwargs["until_message_id"] == "user-1"
        return [{"role": "user", "content": "Prompt from user"}]

    async def scripted_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        calls.append(("collect_chat_completion", settings))
        assert settings == SERVER_SETTINGS
        assert settings.api_key == "server-secret"
        assert messages == [{"role": "user", "content": "Prompt from user"}]
        return "Regenerated server response"

    monkeypatch.setattr(message_actions, "build_prompt_context", scripted_build_prompt_context)
    monkeypatch.setattr(message_actions, "collect_chat_completion", scripted_collect_chat_completion)

    result = await message_actions.regenerate_ai_turn(
        "ai-1",
        repository=repository,
        settings=SERVER_SETTINGS,
    )

    assert calls[0] == ("build_prompt_context", "regenerate")
    assert calls[1] == ("collect_chat_completion", SERVER_SETTINGS)
    assert [message.content_text for message in repository.visible_ai_turns()] == [
        "Regenerated server response"
    ]
    assert result.selected_content() == "Regenerated server response"


async def test_swipe_calls_llm_persists_alternate_and_excludes_unselected_from_future_context(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = ScriptedActionRepository()

    async def scripted_build_prompt_context(*args: object, **kwargs: object) -> list[dict[str, str]]:
        assert kwargs["repository"] is repository
        assert kwargs["action"] == "swipe"
        return [{"role": "assistant", "content": "Selected branch only"}]

    async def scripted_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        assert settings == SERVER_SETTINGS
        prompt_text = "\n".join(message["content"] for message in messages)
        assert "Selected branch only" in prompt_text
        assert "Hidden branch" not in prompt_text
        return "Generated swipe alternate"

    monkeypatch.setattr(message_actions, "build_prompt_context", scripted_build_prompt_context)
    monkeypatch.setattr(message_actions, "collect_chat_completion", scripted_collect_chat_completion)

    result = await message_actions.create_swipe_alternate(
        "ai-1",
        repository=repository,
        settings=SERVER_SETTINGS,
    )

    selected = result.alternates[-1]
    assert selected.source_action == "swipe"
    assert selected.alternate_index == 1
    assert result.selected_alternate_id == selected.id


async def test_continue_calls_llm_with_composer_text_and_selects_continue_alternate(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = ScriptedActionRepository()

    async def scripted_build_prompt_context(*args: object, **kwargs: object) -> list[dict[str, str]]:
        assert kwargs["repository"] is repository
        assert kwargs["action"] == "continue"
        assert kwargs["until_message_id"] == "ai-1"
        assert kwargs["composer_text"] == "finish this sentence"
        return [
            {"role": "assistant", "content": "Original AI response"},
            {"role": "user", "content": "Continue with: finish this sentence"},
        ]

    async def scripted_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        assert settings == SERVER_SETTINGS
        assert "finish this sentence" in "\n".join(message["content"] for message in messages)
        return "Extended AI response"

    monkeypatch.setattr(message_actions, "build_prompt_context", scripted_build_prompt_context)
    monkeypatch.setattr(message_actions, "collect_chat_completion", scripted_collect_chat_completion)

    result = await message_actions.continue_ai_turn(
        "ai-1",
        "finish this sentence",
        repository=repository,
        settings=SERVER_SETTINGS,
    )

    selected = result.alternates[-1]
    assert selected.source_action == "continue"
    assert result.selected_alternate_id == selected.id
    assert selected.content_text == "Extended AI response"


async def test_edit_marks_downstream_turns_stale() -> None:
    repository = ScriptedActionRepository()

    await message_actions.edit_message_and_mark_stale(
        "user-1",
        "Edited user prompt",
        repository=repository,
    )

    assert repository.messages["user-1"].content_text == "Edited user prompt"
    assert repository.messages["downstream-1"].stale_after_edit is True


async def test_truncate_stale_removes_downstream_rows() -> None:
    repository = ScriptedActionRepository()
    repository.messages["downstream-1"] = ThreadMessageShape(
        id="downstream-1",
        thread_id="thread-1",
        message_kind="user_text",
        role="user",
        sequence=3,
        content_text="Later stale turn",
        stale_after_edit=True,
    )

    remaining = await message_actions.truncate_stale_after_message(
        "user-1",
        repository=repository,
    )

    assert repository.truncated_after_message_id == "user-1"
    assert all(message.id != "downstream-1" for message in remaining)


async def test_keep_stale_records_user_choice() -> None:
    repository = ScriptedActionRepository()

    await message_actions.keep_stale_after_message("user-1", repository=repository)

    assert repository.keep_choice_message_id == "user-1"
    assert "downstream-1" in repository.messages


def test_regenerate_route_uses_server_settings_and_replaces_without_appending_ai_turn(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    scripted_client.tokens = ["Regenerated server response"]
    ids = asyncio.run(_create_action_thread(sessionmaker))

    response = client.post(f"/api/messages/{ids['ai']}/regenerate")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ids["ai"]
    assert body["content_text"] == "Regenerated server response"
    assert body["alternates"][-1]["source_action"] == "regenerate"
    assert body["selected_alternate_id"] == body["alternates"][-1]["id"]
    assert scripted_client.requests[0]["settings"] == ChatCompletionSettings(
        base_url="http://server-llm.local/v1",
        model="server-model",
        api_key="server-secret",
        disable_thinking=True,
    )

    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    assert [row.id for row in rows if row.sequence >= 2 and row.role == "assistant"] == [ids["ai"]]
    assert rows[-1].sequence == 2


@pytest.mark.parametrize("disable_thinking", [True, False])
def test_message_action_routes_forward_qwen_disable_thinking_setting(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
    *,
    disable_thinking: bool,
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    scripted_client.tokens = ["Regenerated server response"]
    ids = asyncio.run(_create_action_thread(sessionmaker))
    asyncio.run(
        _write_endpoint_settings(
            sessionmaker,
            llm_model="unsloth/Qwen3.5-27B",
            llm_disable_thinking=disable_thinking,
        )
    )

    response = client.post(f"/api/messages/{ids['ai']}/regenerate")

    assert response.status_code == 200
    assert scripted_client.requests[0]["settings"] == ChatCompletionSettings(
        base_url="http://server-llm.local/v1",
        model="unsloth/Qwen3.5-27B",
        api_key="server-secret",
        disable_thinking=disable_thinking,
    )


def test_swipe_route_generates_selected_alternate_and_future_context_excludes_unselected(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    scripted_client.tokens = ["Generated swipe alternate"]
    ids = asyncio.run(_create_prior_branch_thread(sessionmaker))

    response = client.post(f"/api/messages/{ids['target_ai']}/swipes")

    assert response.status_code == 200
    body = response.json()
    selected = body["alternates"][-1]
    assert selected["source_action"] == "swipe"
    assert selected["alternate_index"] == 1
    assert body["selected_alternate_id"] == selected["id"]

    prompt_text = "\n".join(
        message["content"] for message in scripted_client.requests[0]["messages"]
    )
    assert "Selected prior branch" in prompt_text
    assert "Hidden prior branch" not in prompt_text

    future_prompt_text = asyncio.run(_prompt_text_through_message(sessionmaker, ids["target_ai"]))
    assert "Generated swipe alternate" in future_prompt_text
    assert "Target original alternate" not in future_prompt_text


def test_continue_route_uses_composer_text_and_returns_thread_message_shape(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, _sessionmaker, scripted_client = message_action_client
    scripted_client.tokens = ["Extended AI response"]
    ids = asyncio.run(_create_action_thread(message_action_client[1]))

    response = client.post(
        f"/api/messages/{ids['ai']}/continue",
        json={"composer_text": "finish this sentence"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ids["ai"]
    assert body["message_kind"] == "ai_text"
    assert body["role"] == "assistant"
    assert body["content_text"] == "Extended AI response"
    assert body["alternates"][-1]["source_action"] == "continue"
    assert body["selected_alternate_id"] == body["alternates"][-1]["id"]
    prompt_text = "\n".join(
        message["content"] for message in scripted_client.requests[0]["messages"]
    )
    assert "finish this sentence" in prompt_text


def test_edit_route_marks_downstream_stale_and_truncate_keep_behaviors_work(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, _scripted_client = message_action_client
    ids = asyncio.run(_create_action_thread(sessionmaker, include_downstream=True))

    edit_response = client.patch(
        f"/api/messages/{ids['user']}",
        json={"content": "Edited user prompt"},
    )

    assert edit_response.status_code == 200
    assert edit_response.json()["content_text"] == "Edited user prompt"
    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    downstream = next(row for row in rows if row.id == ids["downstream"])
    assert downstream.stale_after_edit is True

    keep_response = client.post(f"/api/messages/{ids['user']}/keep-stale")

    assert keep_response.status_code == 200
    rows_after_keep = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    assert any(row.id == ids["downstream"] for row in rows_after_keep)

    truncate_response = client.post(f"/api/messages/{ids['user']}/truncate-stale")

    assert truncate_response.status_code == 200
    assert all(message["id"] != ids["downstream"] for message in truncate_response.json()["messages"])
    rows_after_truncate = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    assert all(row.id != ids["downstream"] for row in rows_after_truncate)


async def _create_action_thread(
    sessionmaker: async_sessionmaker,
    *,
    include_downstream: bool = False,
) -> dict[str, str]:
    async with sessionmaker() as session:
        await _insert_character(session, character_id="char_actions")
        thread_id = (await ThreadService(session).create_thread(character_id="char_actions"))[
            "thread_id"
        ]
        session.add_all(
            [
                Message(
                    id="user-1",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=1,
                    content_text="Prompt from user",
                ),
                Message(
                    id="ai-1",
                    thread_id=thread_id,
                    message_kind="ai_text",
                    role="assistant",
                    sequence=2,
                    content_text="Original AI response",
                ),
            ]
        )
        if include_downstream:
            session.add(
                Message(
                    id="downstream-1",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=3,
                    content_text="Later downstream turn",
                )
            )
        await session.commit()
        return {
            "thread": thread_id,
            "user": "user-1",
            "ai": "ai-1",
            "downstream": "downstream-1",
        }


async def _create_prior_branch_thread(sessionmaker: async_sessionmaker) -> dict[str, str]:
    async with sessionmaker() as session:
        await _insert_character(session, character_id="char_swipes")
        thread_id = (await ThreadService(session).create_thread(character_id="char_swipes"))[
            "thread_id"
        ]
        session.add_all(
            [
                Message(
                    id="user-1",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=1,
                    content_text="First prompt",
                ),
                Message(
                    id="ai-prior",
                    thread_id=thread_id,
                    message_kind="ai_text",
                    role="assistant",
                    sequence=2,
                    content_text="Prior fallback",
                    selected_alternate_id="alt-prior-selected",
                ),
                MessageAlternate(
                    id="alt-prior-hidden",
                    message_id="ai-prior",
                    alternate_index=0,
                    content_text="Hidden prior branch",
                    source_action="swipe",
                ),
                MessageAlternate(
                    id="alt-prior-selected",
                    message_id="ai-prior",
                    alternate_index=1,
                    content_text="Selected prior branch",
                    source_action="swipe",
                ),
                Message(
                    id="user-2",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=3,
                    content_text="Second prompt",
                ),
                Message(
                    id="ai-target",
                    thread_id=thread_id,
                    message_kind="ai_text",
                    role="assistant",
                    sequence=4,
                    content_text="Target fallback",
                    selected_alternate_id="alt-target-original",
                ),
                MessageAlternate(
                    id="alt-target-original",
                    message_id="ai-target",
                    alternate_index=0,
                    content_text="Target original alternate",
                    source_action="regenerate",
                ),
            ]
        )
        await session.commit()
        return {"thread": thread_id, "target_ai": "ai-target"}


async def _write_endpoint_settings(
    sessionmaker: async_sessionmaker,
    *,
    llm_model: str,
    llm_disable_thinking: bool,
) -> None:
    async with sessionmaker() as session:
        session.add(
            AppSetting(
                key=SETTINGS_KEY,
                value_json={
                    "llm_model": llm_model,
                    "llm_disable_thinking": llm_disable_thinking,
                },
            )
        )
        await session.commit()


async def _insert_character(session: object, *, character_id: str) -> None:
    session.add(
        Character(
            id=character_id,
            name="Action Character",
            description="description",
            personality="personality",
            scenario="scenario",
            first_mes="Opening from card.",
            system_prompt="system prompt",
            raw_source_json={"spec": "chara_card_v3"},
            lorebook_json={"entries": [{"content": "do not inject"}]},
        )
    )
    await session.commit()


async def _messages_for_thread(sessionmaker: async_sessionmaker, thread_id: str) -> list[Message]:
    async with sessionmaker() as session:
        result = await session.execute(
            select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence)
        )
        return list(result.scalars())


async def _prompt_text_through_message(sessionmaker: async_sessionmaker, message_id: str) -> str:
    async with sessionmaker() as session:
        repository = SqlAlchemyMessageActionRepository(session)
        context = await repository.get_generation_context(message_id, include_target=True)
        prompt_messages = await build_prompt_context(
            context.thread_id,
            repository=SqlAlchemyPromptRepository(session),
            until_message_id=message_id,
            action="swipe",
        )
        return "\n".join(message["content"] for message in prompt_messages)
