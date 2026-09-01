"""Message-action contracts and API integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.messages import get_message_action_session, get_message_completion_client
from app.config import Settings
from app.domain import message_actions
from app.domain.llm_stream import (
    REFUSAL_RETRY_CORRECTION,
    ChatCompletionSettings,
)
from app.domain.message_actions import MessageGenerationContext, SqlAlchemyMessageActionRepository
from app.domain.prompt_builder import (
    PromptMessageCandidate,
    SqlAlchemyPromptRepository,
    build_prompt_context,
    build_structured_prompt,
)
from app.domain.prompt_profiles import PromptGenerationSettings
from app.domain.refusal_guard import LLMEmptyOutput, LLMRefusalExhausted
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
STRUCTURED_SERVER_SETTINGS = ChatCompletionSettings(
    base_url="http://llm.local/v1",
    model="unsloth/Qwen3.5-27B",
    api_key="server-secret",
    disable_thinking=True,
    prompt_generation=PromptGenerationSettings.defaults().merge(
        {
            "model_profile": "qwen_llama_server",
            "temperature": 0.65,
            "top_k": 72,
            "max_tokens": 768,
        }
    ),
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
            selected_content=message.selected_content() or "",
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
        self.scripts: list[list[str]] | None = None
        self.requests: list[dict[str, object]] = []

    async def stream_chat_completion_tokens(
        self,
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
        *,
        seed: int,
        attempt: int,
    ):
        self.requests.append(
            {
                "settings": settings,
                "messages": list(messages),
                "seed": seed,
                "attempt": attempt,
            }
        )
        tokens = self.scripts[attempt - 1] if self.scripts is not None else self.tokens
        for token in tokens:
            yield token


_WAIT_FOR_CANCELLATION = object()


class ActionAttemptClient:
    def __init__(self, scripts: list[list[str | object]]) -> None:
        self.scripts = scripts
        self.requests: list[dict[str, object]] = []
        self.closed_attempts: list[int] = []
        self.waiting = asyncio.Event()

    async def stream_chat_completion_tokens(
        self,
        settings: ChatCompletionSettings,
        messages: list[dict[str, object]],
        *,
        seed: int,
        attempt: int,
    ):
        self.requests.append(
            {
                "settings": settings,
                "messages": [dict(message) for message in messages],
                "seed": seed,
                "attempt": attempt,
            }
        )
        try:
            for item in self.scripts[attempt - 1]:
                if item is _WAIT_FOR_CANCELLATION:
                    self.waiting.set()
                    await asyncio.Event().wait()
                else:
                    yield str(item)
        finally:
            self.closed_attempts.append(attempt)


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

    async def scripted_build_structured_prompt(*args: object, **kwargs: object) -> object:
        calls.append(("build_structured_prompt", kwargs["action"]))
        assert kwargs["repository"] is repository
        assert kwargs["until_message_id"] == "user-1"
        return _prompt_result(("user", "Prompt from user", ("history:user-1",)))

    async def scripted_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        calls.append(("collect_chat_completion", settings))
        assert settings == SERVER_SETTINGS
        assert settings.api_key == "server-secret"
        assert _role_content_messages(messages) == [{"role": "user", "content": "Prompt from user"}]
        return "Regenerated server response"

    monkeypatch.setattr(
        message_actions,
        "build_structured_prompt",
        scripted_build_structured_prompt,
    )
    monkeypatch.setattr(
        message_actions, "collect_chat_completion", scripted_collect_chat_completion
    )

    result = await message_actions.regenerate_ai_turn(
        "ai-1",
        repository=repository,
        settings=SERVER_SETTINGS,
    )

    assert calls[0] == ("build_structured_prompt", "regenerate")
    assert calls[1] == ("collect_chat_completion", SERVER_SETTINGS)
    assert [message.content_text for message in repository.visible_ai_turns()] == [
        "Regenerated server response"
    ]
    assert result.selected_content() == "Regenerated server response"


async def test_swipe_calls_llm_persists_alternate_and_excludes_unselected_from_future_context(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = ScriptedActionRepository()

    async def scripted_build_structured_prompt(*args: object, **kwargs: object) -> object:
        assert kwargs["repository"] is repository
        assert kwargs["action"] == "swipe"
        return _prompt_result(("assistant", "Selected branch only", ("history:ai-selected",)))

    async def scripted_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        assert settings == SERVER_SETTINGS
        prompt_text = "\n".join(message["content"] for message in messages)
        assert "Selected branch only" in prompt_text
        assert "Hidden branch" not in prompt_text
        return "Generated swipe alternate"

    monkeypatch.setattr(
        message_actions,
        "build_structured_prompt",
        scripted_build_structured_prompt,
    )
    monkeypatch.setattr(
        message_actions, "collect_chat_completion", scripted_collect_chat_completion
    )

    result = await message_actions.create_swipe_alternate(
        "ai-1",
        repository=repository,
        settings=SERVER_SETTINGS,
    )

    selected = result.alternates[-1]
    assert selected.source_action == "swipe"
    assert selected.alternate_index == 1
    assert result.selected_alternate_id == selected.id


async def test_continue_commits_composer_text_before_selecting_continue_alternate(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = ScriptedActionRepository()

    async def scripted_build_structured_prompt(*args: object, **kwargs: object) -> object:
        assert kwargs["repository"] is repository
        assert kwargs["action"] == "continue"
        assert kwargs["until_message_id"] == "user-1"
        assert kwargs["composer_text"] == "finish this sentence"
        return _prompt_result(
            ("user", "Prompt from user", ("history:user-1",)),
            ("assistant", "finish this sentence", ("assistant_prefill",)),
        )

    async def scripted_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        assert settings == SERVER_SETTINGS
        assert _role_content(messages[-1]) == {
            "role": "assistant",
            "content": "finish this sentence",
        }
        assert all(message["content"] != "Original AI response" for message in messages)
        return "Extended AI response"

    monkeypatch.setattr(
        message_actions,
        "build_structured_prompt",
        scripted_build_structured_prompt,
    )
    monkeypatch.setattr(
        message_actions, "collect_chat_completion", scripted_collect_chat_completion
    )

    result = await message_actions.continue_ai_turn(
        "ai-1",
        "finish this sentence",
        repository=repository,
        settings=SERVER_SETTINGS,
    )

    selected = result.alternates[-1]
    assert selected.source_action == "continue"
    assert result.selected_alternate_id == selected.id
    assert selected.content_text == "finish this sentenceExtended AI response"


@pytest.mark.parametrize(
    ("action", "invoke"),
    [
        (
            "regenerate",
            lambda repository, client: message_actions.regenerate_ai_turn(
                "ai-1",
                repository=repository,
                settings=STRUCTURED_SERVER_SETTINGS,
                completion_client=client,
            ),
        ),
        (
            "swipe",
            lambda repository, client: message_actions.create_swipe_alternate(
                "ai-1",
                repository=repository,
                settings=STRUCTURED_SERVER_SETTINGS,
                completion_client=client,
            ),
        ),
        (
            "continue",
            lambda repository, client: message_actions.continue_ai_turn(
                "ai-1",
                "Existing prefix.",
                repository=repository,
                settings=STRUCTURED_SERVER_SETTINGS,
                completion_client=client,
            ),
        ),
    ],
)
async def test_generation_actions_share_saved_profile_and_structured_composer(
    monkeypatch: MonkeyPatch,
    action: str,
    invoke: object,
) -> None:
    repository = ScriptedActionRepository()
    client = ScriptedCompletionClient()
    client.tokens = ["Accepted action response."]
    builds: list[dict[str, object]] = []

    async def capture_structured_prompt(*args: object, **kwargs: object):
        builds.append(dict(kwargs))
        return await build_structured_prompt(*args, **kwargs)

    monkeypatch.setattr(
        message_actions,
        "build_structured_prompt",
        capture_structured_prompt,
    )

    await invoke(repository, client)  # type: ignore[operator]

    assert len(builds) == 1
    assert builds[0]["action"] == action
    assert builds[0]["settings"] == STRUCTURED_SERVER_SETTINGS.prompt_generation
    request = client.requests[0]
    assert request["settings"] == STRUCTURED_SERVER_SETTINGS
    assert all(message.get("section_ids") for message in request["messages"])
    if action == "continue":
        assert request["messages"][-1]["role"] == "assistant"
        assert request["messages"][-1]["content"] == "Existing prefix."


@pytest.mark.parametrize("action", ["regenerate", "swipe", "continue"])
async def test_generation_action_outcome_matrix_is_accepted_only_and_atomic(action: str) -> None:
    refusal = "I cannot continue because the safety guidelines forbid it."

    accepted_repository = ScriptedActionRepository()
    accepted_client = ActionAttemptClient([[refusal], ["Accepted action response."]])
    accepted = await _invoke_generation_action(action, accepted_repository, accepted_client)
    assert accepted.selected_content()
    assert accepted_client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in accepted_client.requests] == [1, 2]
    retry_messages = accepted_client.requests[1]["messages"]
    correction_index = -2 if action == "continue" else -1
    assert _role_content(retry_messages[correction_index]) == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }
    assert refusal not in repr(retry_messages)

    exhausted_repository = ScriptedActionRepository()
    exhausted_before = exhausted_repository.messages["ai-1"]
    exhausted_client = ActionAttemptClient([[refusal], [refusal], [refusal]])
    with pytest.raises(LLMRefusalExhausted):
        await _invoke_generation_action(action, exhausted_repository, exhausted_client)
    assert exhausted_repository.messages["ai-1"] == exhausted_before
    assert exhausted_client.closed_attempts == [1, 2, 3]

    empty_repository = ScriptedActionRepository()
    empty_before = empty_repository.messages["ai-1"]
    empty_client = ActionAttemptClient([[]])
    with pytest.raises(LLMEmptyOutput):
        await _invoke_generation_action(action, empty_repository, empty_client)
    assert empty_repository.messages["ai-1"] == empty_before
    assert empty_client.closed_attempts == [1]

    cancelled_repository = ScriptedActionRepository()
    cancelled_before = cancelled_repository.messages["ai-1"]
    cancelled_client = ActionAttemptClient(
        [["Accepted prefix before cancellation.", _WAIT_FOR_CANCELLATION]]
    )
    cancelled_task = asyncio.create_task(
        _invoke_generation_action(action, cancelled_repository, cancelled_client)
    )
    await cancelled_client.waiting.wait()
    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task
    assert cancelled_repository.messages["ai-1"] == cancelled_before
    assert cancelled_client.closed_attempts == [1]


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


@pytest.mark.parametrize(
    ("path_suffix", "payload"),
    [
        ("regenerate", None),
        ("swipes", None),
        ("continue", {"composer_text": "Existing prefix."}),
    ],
)
@pytest.mark.parametrize(
    ("tokens", "expected_code"),
    [
        (["I cannot continue because the safety guidelines forbid it."], "llm_refusal_exhausted"),
        ([], "llm_empty_output"),
    ],
)
def test_message_action_routes_return_typed_failures_without_version_mutation(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
    path_suffix: str,
    payload: dict[str, str] | None,
    tokens: list[str],
    expected_code: str,
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    ids = asyncio.run(_create_action_thread(sessionmaker))
    before = asyncio.run(_message_version_state(sessionmaker, ids["ai"]))
    scripted_client.tokens = tokens

    response = client.post(
        f"/api/messages/{ids['ai']}/{path_suffix}",
        json=payload,
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == expected_code
    assert "safety guidelines" not in detail["message"]
    assert asyncio.run(_message_version_state(sessionmaker, ids["ai"])) == before


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


@pytest.mark.parametrize(
    "refusal",
    [
        (
            "I cannot continue with explicit sexual descriptions or erotic content "
            "involving genitalia. Please let me know if you have other non-explicit "
            "questions or topics you'd like to discuss instead."
        ),
        "I can't generate explicit sexual descriptions of genitalia or erotic content.",
        (
            "I cannot continue with that description. I am unable to generate sexually "
            "explicit content or erotica."
        ),
        (
            "I cannot continue this specific erotic description involving explicit sexual "
            "anatomy or fetish content. I’m happy to discuss other creative writing topics "
            "or help with a different scenario!"
        ),
    ],
)
def test_swipe_route_retries_explicit_description_refusal_before_selecting_alternate(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
    refusal: str,
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    recovered = "The character answers in her own voice and continues the scene."
    scripted_client.scripts = [[refusal], [recovered]]
    ids = asyncio.run(_create_prior_branch_thread(sessionmaker))
    before = asyncio.run(_message_version_state(sessionmaker, ids["target_ai"]))

    response = client.post(f"/api/messages/{ids['target_ai']}/swipes")

    assert response.status_code == 200
    body = response.json()
    after = asyncio.run(_message_version_state(sessionmaker, ids["target_ai"]))
    assert [request["attempt"] for request in scripted_client.requests] == [1, 2]
    assert _role_content(scripted_client.requests[1]["messages"][-1]) == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }
    assert len(after[2]) == len(before[2]) + 1
    assert after[2][-1][1] == recovered
    assert refusal not in repr(after)
    assert body["selected_alternate_id"] == after[1]
    assert body["alternates"][-1]["content_text"] == recovered


@pytest.mark.parametrize(
    ("prefix", "model_output", "expected_suffix"),
    [
        (" Yes, I will do it. ", "NO i can't do that!", "NO i can't do that!"),
        (
            "Yes, I will do it.",
            "Yes, I will do it. Then I will begin.",
            " Then I will begin.",
        ),
    ],
)
def test_continue_route_commits_exact_prefix_before_generated_suffix(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
    prefix: str,
    model_output: str,
    expected_suffix: str,
) -> None:
    client, _sessionmaker, scripted_client = message_action_client
    scripted_client.tokens = [model_output]
    ids = asyncio.run(_create_action_thread(message_action_client[1]))

    response = client.post(
        f"/api/messages/{ids['ai']}/continue",
        json={"composer_text": prefix},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ids["ai"]
    assert body["message_kind"] == "ai_text"
    assert body["role"] == "assistant"
    selected = body["alternates"][-1]
    assert selected["source_action"] == "continue"
    assert body["selected_alternate_id"] == selected["id"]
    assert selected["content_text"] == f"{prefix}{expected_suffix}"
    assert selected["content_text"].startswith(prefix)
    assert selected["content_text"].count(prefix) == 1
    assert body["content_text"] == selected["content_text"]
    prompt_messages = scripted_client.requests[0]["messages"]
    assert _role_content(prompt_messages[-1]) == {"role": "assistant", "content": prefix}
    assert _role_content(prompt_messages[-2]) == {
        "role": "user",
        "content": "Prompt from user",
    }
    assert all(message["content"] != "Original AI response" for message in prompt_messages)
    assert all(
        "Committed assistant prefix" not in message["content"] for message in prompt_messages
    )


def test_continue_uses_edited_assistant_text_as_prefix_when_composer_is_empty(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    """The Edit → Continue UI flow must keep the edited assistant text immutable."""

    client, sessionmaker, scripted_client = message_action_client
    prefix = "Miles' eyes opened wide. He felt the palpitations of his"
    refusal = " Miles did not tremble."
    ids = asyncio.run(_create_action_thread(sessionmaker))

    seeded = client.post(f"/api/messages/{ids['ai']}/swipes")
    assert seeded.status_code == 200
    scripted_client.requests.clear()
    scripted_client.tokens = [refusal]

    edited = client.patch(f"/api/messages/{ids['ai']}", json={"content": prefix})
    assert edited.status_code == 200
    assert edited.json()["content_text"] == prefix
    assert edited.json()["alternates"][-1]["content_text"] == prefix

    response = client.post(
        f"/api/messages/{ids['ai']}/continue",
        json={"composer_text": ""},
    )

    assert response.status_code == 200
    body = response.json()
    selected = body["alternates"][-1]
    expected = f"{prefix}{refusal}"
    assert selected["source_action"] == "continue"
    assert selected["content_text"] == expected
    assert selected["content_text"].startswith(prefix)
    assert selected["content_text"].count(prefix) == 1
    assert body["content_text"] == expected
    prompt_messages = scripted_client.requests[0]["messages"]
    assert _role_content(prompt_messages[-1]) == {"role": "assistant", "content": prefix}
    assert all(message["content"] != "Original AI response" for message in prompt_messages)


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
    assert all(
        message["id"] != ids["downstream"] for message in truncate_response.json()["messages"]
    )
    rows_after_truncate = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    assert all(row.id != ids["downstream"] for row in rows_after_truncate)


def test_edit_route_persists_assistant_content_and_selected_alternate(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, _scripted_client = message_action_client
    ids = asyncio.run(_create_action_thread(sessionmaker, include_downstream=True))

    seeded = client.post(f"/api/messages/{ids['ai']}/swipes")
    assert seeded.status_code == 200

    response = client.patch(
        f"/api/messages/{ids['ai']}",
        json={"content": "Persisted edited assistant response"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ids["ai"]
    assert body["content_text"] == "Persisted edited assistant response"
    assert body["selected_alternate_id"] == body["alternates"][-1]["id"]
    assert body["alternates"][-1]["content_text"] == "Persisted edited assistant response"

    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    assistant = next(row for row in rows if row.id == ids["ai"])
    downstream = next(row for row in rows if row.id == ids["downstream"])
    assert assistant.content_text == "Persisted edited assistant response"
    assert downstream.stale_after_edit is False


def test_assistant_edit_isolated_from_later_stale_ai_record(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, _scripted_client = message_action_client
    ids = asyncio.run(_create_assistant_identity_isolation_thread(sessionmaker))

    response = client.patch(
        f"/api/messages/{ids['target']}",
        json={"content": "Corrected second-to-last assistant response"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ids["target"]
    assert body["content_text"] == "Corrected second-to-last assistant response"
    assert body["selected_alternate_id"] == ids["target_alternate"]

    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    target = next(row for row in rows if row.id == ids["target"])
    final = next(row for row in rows if row.id == ids["final"])
    final_alternates = asyncio.run(_alternates_for_message(sessionmaker, ids["final"]))
    assert target.content_text == "Corrected second-to-last assistant response"
    assert target.selected_alternate_id == ids["target_alternate"]
    assert final.id == ids["final"]
    assert final.content_text == "Final stale assistant response"
    assert final.selected_alternate_id == ids["final_alternate"]
    assert final.stale_after_edit is True
    assert [
        (alternate.id, alternate.message_id, alternate.content_text)
        for alternate in final_alternates
    ] == [(ids["final_alternate"], ids["final"], "Final stale assistant response")]


def test_user_edit_then_regenerate_uses_edited_prompt_and_reactivates_response(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    ids = asyncio.run(_create_action_thread(sessionmaker))
    scripted_client.tokens = ["AI response to corrected prompt"]

    edit_response = client.patch(
        f"/api/messages/{ids['user']}",
        json={"content": "Corrected user prompt"},
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["content_text"] == "Corrected user prompt"

    regenerate_response = client.post(f"/api/messages/{ids['ai']}/regenerate")

    assert regenerate_response.status_code == 200
    body = regenerate_response.json()
    assert body["content_text"] == "AI response to corrected prompt"
    assert body["stale_after_edit"] is False
    assert _role_content(scripted_client.requests[0]["messages"][-1]) == {
        "role": "user",
        "content": "Corrected user prompt",
    }
    assert all(
        message["content"] != "Prompt from user"
        for message in scripted_client.requests[0]["messages"]
    )

    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    user = next(row for row in rows if row.id == ids["user"])
    assistant = next(row for row in rows if row.id == ids["ai"])
    assert user.content_text == "Corrected user prompt"
    assert assistant.content_text == "AI response to corrected prompt"
    assert assistant.stale_after_edit is False


def test_call_assistant_edit_is_exact_and_preserves_call_linkage(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, _scripted_client = message_action_client
    ids = asyncio.run(_create_call_edit_thread(sessionmaker, include_later_turns=True))

    response = client.patch(
        f"/api/messages/{ids['assistant']}",
        json={"content": "Corrected spoken assistant response"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == ids["assistant"]
    assert response.json()["message_kind"] == "ai_speech"
    assert response.json()["content_text"] == "Corrected spoken assistant response"

    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    target = next(row for row in rows if row.id == ids["assistant"])
    later_user = next(row for row in rows if row.id == ids["later_user"])
    later_assistant = next(row for row in rows if row.id == ids["later_assistant"])
    assert (
        target.id,
        target.message_kind,
        target.role,
        target.call_id,
        target.call_turn_id,
        target.content_text,
        target.stale_after_edit,
    ) == (
        ids["assistant"],
        "ai_speech",
        "assistant",
        ids["call"],
        "turn-assistant",
        "Corrected spoken assistant response",
        False,
    )
    assert (
        later_user.content_text,
        later_user.call_id,
        later_user.call_turn_id,
        later_user.stale_after_edit,
    ) == ("Later spoken user turn", ids["call"], "turn-later-user", False)
    assert (
        later_assistant.content_text,
        later_assistant.call_id,
        later_assistant.call_turn_id,
        later_assistant.stale_after_edit,
    ) == ("Later spoken assistant turn", ids["call"], "turn-later-assistant", False)


def test_call_user_edit_regenerates_following_ai_from_corrected_content(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    ids = asyncio.run(_create_call_edit_thread(sessionmaker))
    scripted_client.tokens = ["AI response to corrected spoken prompt"]

    edit_response = client.patch(
        f"/api/messages/{ids['user']}",
        json={"content": "Corrected spoken user prompt"},
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["message_kind"] == "user_speech"
    assert edit_response.json()["content_text"] == "Corrected spoken user prompt"

    regenerate_response = client.post(f"/api/messages/{ids['assistant']}/regenerate")

    assert regenerate_response.status_code == 200
    assert regenerate_response.json()["message_kind"] == "ai_speech"
    assert regenerate_response.json()["content_text"] == "AI response to corrected spoken prompt"
    assert _role_content(scripted_client.requests[0]["messages"][-1]) == {
        "role": "user",
        "content": "Corrected spoken user prompt",
    }
    assert all(
        message["content"] != "Original spoken user prompt"
        for message in scripted_client.requests[0]["messages"]
    )

    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    user = next(row for row in rows if row.id == ids["user"])
    assistant = next(row for row in rows if row.id == ids["assistant"])
    assert (
        user.id,
        user.message_kind,
        user.call_id,
        user.call_turn_id,
        user.content_text,
        user.stale_after_edit,
    ) == (
        ids["user"],
        "user_speech",
        ids["call"],
        "turn-user",
        "Corrected spoken user prompt",
        False,
    )
    assert (
        assistant.id,
        assistant.message_kind,
        assistant.call_id,
        assistant.call_turn_id,
        assistant.content_text,
        assistant.stale_after_edit,
    ) == (
        ids["assistant"],
        "ai_speech",
        ids["call"],
        "turn-assistant",
        "AI response to corrected spoken prompt",
        False,
    )


def test_editing_a_previously_stale_user_reactivates_its_regeneration_context(
    message_action_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, sessionmaker, scripted_client = message_action_client
    ids = asyncio.run(_create_stale_regeneration_thread(sessionmaker))
    scripted_client.tokens = ["Independent final response from corrected user"]

    edit_response = client.patch(
        f"/api/messages/{ids['stale_user']}",
        json={"content": "Corrected stale user prompt"},
    )

    assert edit_response.status_code == 200
    assert edit_response.json()["stale_after_edit"] is False

    regenerate_response = client.post(f"/api/messages/{ids['final_ai']}/regenerate")

    assert regenerate_response.status_code == 200
    assert (
        regenerate_response.json()["content_text"]
        == "Independent final response from corrected user"
    )
    assert _role_content(scripted_client.requests[0]["messages"][-1]) == {
        "role": "user",
        "content": "Corrected stale user prompt",
    }
    rows = asyncio.run(_messages_for_thread(sessionmaker, ids["thread"]))
    stale_user = next(row for row in rows if row.id == ids["stale_user"])
    final_ai = next(row for row in rows if row.id == ids["final_ai"])
    assert stale_user.stale_after_edit is False
    assert final_ai.content_text == "Independent final response from corrected user"


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


async def _create_call_edit_thread(
    sessionmaker: async_sessionmaker,
    *,
    include_later_turns: bool = False,
) -> dict[str, str]:
    async with sessionmaker() as session:
        await _insert_character(session, character_id="char_call_actions")
        thread_id = (await ThreadService(session).create_thread(character_id="char_call_actions"))[
            "thread_id"
        ]
        call_id = "call-edit-1"
        messages = [
            Message(
                id="call-user-1",
                thread_id=thread_id,
                call_id=call_id,
                call_turn_id="turn-user",
                message_kind="user_speech",
                role="user",
                sequence=1,
                content_text="Original spoken user prompt",
            ),
            Message(
                id="call-ai-1",
                thread_id=thread_id,
                call_id=call_id,
                call_turn_id="turn-assistant",
                message_kind="ai_speech",
                role="assistant",
                sequence=2,
                content_text="Original spoken assistant response",
            ),
        ]
        if include_later_turns:
            messages.extend(
                [
                    Message(
                        id="call-later-user-1",
                        thread_id=thread_id,
                        call_id=call_id,
                        call_turn_id="turn-later-user",
                        message_kind="user_speech",
                        role="user",
                        sequence=3,
                        content_text="Later spoken user turn",
                    ),
                    Message(
                        id="call-later-ai-1",
                        thread_id=thread_id,
                        call_id=call_id,
                        call_turn_id="turn-later-assistant",
                        message_kind="ai_speech",
                        role="assistant",
                        sequence=4,
                        content_text="Later spoken assistant turn",
                    ),
                ]
            )
        session.add_all(messages)
        await session.commit()
        return {
            "thread": thread_id,
            "call": call_id,
            "user": "call-user-1",
            "assistant": "call-ai-1",
            "later_user": "call-later-user-1",
            "later_assistant": "call-later-ai-1",
        }


async def _create_assistant_identity_isolation_thread(
    sessionmaker: async_sessionmaker,
) -> dict[str, str]:
    async with sessionmaker() as session:
        await _insert_character(session, character_id="char_assistant_isolation")
        thread_id = (
            await ThreadService(session).create_thread(character_id="char_assistant_isolation")
        )["thread_id"]
        session.add_all(
            [
                Message(
                    id="user-before-target",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=1,
                    content_text="Prompt before stale assistant pair",
                ),
                Message(
                    id="assistant-target",
                    thread_id=thread_id,
                    message_kind="ai_text",
                    role="assistant",
                    sequence=2,
                    content_text="Original second-to-last assistant response",
                    selected_alternate_id="alt-assistant-target",
                    stale_after_edit=True,
                ),
                MessageAlternate(
                    id="alt-assistant-target",
                    message_id="assistant-target",
                    alternate_index=0,
                    content_text="Original second-to-last assistant response",
                    source_action="regenerate",
                ),
                Message(
                    id="stale-user-between",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=3,
                    content_text="Previously stale user message",
                    stale_after_edit=True,
                ),
                Message(
                    id="assistant-final",
                    thread_id=thread_id,
                    message_kind="ai_text",
                    role="assistant",
                    sequence=4,
                    content_text="Final stale assistant response",
                    selected_alternate_id="alt-assistant-final",
                    stale_after_edit=True,
                ),
                MessageAlternate(
                    id="alt-assistant-final",
                    message_id="assistant-final",
                    alternate_index=0,
                    content_text="Final stale assistant response",
                    source_action="regenerate",
                ),
            ]
        )
        await session.commit()
        return {
            "thread": thread_id,
            "target": "assistant-target",
            "target_alternate": "alt-assistant-target",
            "final": "assistant-final",
            "final_alternate": "alt-assistant-final",
        }


async def _create_stale_regeneration_thread(sessionmaker: async_sessionmaker) -> dict[str, str]:
    async with sessionmaker() as session:
        await _insert_character(session, character_id="char_stale_regeneration")
        thread_id = (
            await ThreadService(session).create_thread(character_id="char_stale_regeneration")
        )["thread_id"]
        session.add_all(
            [
                Message(
                    id="user-before-branch",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=1,
                    content_text="Original branch prompt",
                ),
                Message(
                    id="assistant-before-stale-user",
                    thread_id=thread_id,
                    message_kind="ai_text",
                    role="assistant",
                    sequence=2,
                    content_text="Earlier assistant response that must not become the final response",
                ),
                Message(
                    id="stale-user-to-edit",
                    thread_id=thread_id,
                    message_kind="user_text",
                    role="user",
                    sequence=3,
                    content_text="Old stale user prompt",
                    stale_after_edit=True,
                ),
                Message(
                    id="final-ai-to-regenerate",
                    thread_id=thread_id,
                    message_kind="ai_text",
                    role="assistant",
                    sequence=4,
                    content_text="Old stale final response",
                    stale_after_edit=True,
                ),
            ]
        )
        await session.commit()
        return {
            "thread": thread_id,
            "stale_user": "stale-user-to-edit",
            "final_ai": "final-ai-to-regenerate",
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


async def _alternates_for_message(
    sessionmaker: async_sessionmaker,
    message_id: str,
) -> list[MessageAlternate]:
    async with sessionmaker() as session:
        result = await session.execute(
            select(MessageAlternate)
            .where(MessageAlternate.message_id == message_id)
            .order_by(MessageAlternate.alternate_index)
        )
        return list(result.scalars())


async def _message_version_state(
    sessionmaker: async_sessionmaker,
    message_id: str,
) -> tuple[str | None, str | None, tuple[tuple[str, str, str], ...]]:
    async with sessionmaker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        result = await session.execute(
            select(MessageAlternate)
            .where(MessageAlternate.message_id == message_id)
            .order_by(MessageAlternate.alternate_index)
        )
        alternates = tuple(
            (alternate.id, alternate.content_text, alternate.source_action)
            for alternate in result.scalars()
        )
        return message.content_text, message.selected_alternate_id, alternates


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


def _prompt_result(
    *messages: tuple[str, str, tuple[str, ...]],
) -> object:
    return SimpleNamespace(
        transmitted_message_candidates=tuple(
            PromptMessageCandidate(
                role=role,  # type: ignore[arg-type]
                content=content,
                section_ids=section_ids,
            )
            for role, content, section_ids in messages
        )
    )


def _role_content(message: dict[str, object]) -> dict[str, object]:
    return {"role": message["role"], "content": message["content"]}


def _role_content_messages(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    return [_role_content(message) for message in messages]


async def _invoke_generation_action(
    action: str,
    repository: ScriptedActionRepository,
    client: object,
) -> ThreadMessageShape:
    if action == "regenerate":
        return await message_actions.regenerate_ai_turn(
            "ai-1",
            repository=repository,
            settings=STRUCTURED_SERVER_SETTINGS,
            completion_client=client,
        )
    if action == "swipe":
        return await message_actions.create_swipe_alternate(
            "ai-1",
            repository=repository,
            settings=STRUCTURED_SERVER_SETTINGS,
            completion_client=client,
        )
    if action == "continue":
        return await message_actions.continue_ai_turn(
            "ai-1",
            "Existing prefix.",
            repository=repository,
            settings=STRUCTURED_SERVER_SETTINGS,
            completion_client=client,
        )
    raise AssertionError(f"unsupported test action: {action}")
