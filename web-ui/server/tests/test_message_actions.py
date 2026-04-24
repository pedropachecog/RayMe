"""Message-action contracts for LLM-backed branch operations."""

from __future__ import annotations

from pytest import MonkeyPatch

from app.domain import message_actions
from app.domain.llm_stream import ChatCompletionSettings
from app.storage.models import MessageAlternateShape, ThreadMessageShape

SERVER_SETTINGS = ChatCompletionSettings(
    base_url="http://llm.local/v1",
    model="configured-model",
    api_key="server-secret",
)


class FakeActionRepository:
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


async def test_regenerate_calls_llm_and_replaces_selected_ai_response(
    monkeypatch: MonkeyPatch,
) -> None:
    repository = FakeActionRepository()
    calls: list[tuple[str, object]] = []

    async def fake_build_prompt_context(*args: object, **kwargs: object) -> list[dict[str, str]]:
        calls.append(("build_prompt_context", kwargs["action"]))
        assert kwargs["repository"] is repository
        return [{"role": "user", "content": "Prompt from user"}]

    async def fake_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        calls.append(("collect_chat_completion", settings))
        assert settings == SERVER_SETTINGS
        assert settings.api_key == "server-secret"
        assert messages == [{"role": "user", "content": "Prompt from user"}]
        return "Regenerated server response"

    monkeypatch.setattr(message_actions, "build_prompt_context", fake_build_prompt_context)
    monkeypatch.setattr(message_actions, "collect_chat_completion", fake_collect_chat_completion)

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
    repository = FakeActionRepository()

    async def fake_build_prompt_context(*args: object, **kwargs: object) -> list[dict[str, str]]:
        assert kwargs["repository"] is repository
        assert kwargs["action"] == "swipe"
        return [{"role": "assistant", "content": "Selected branch only"}]

    async def fake_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        assert settings == SERVER_SETTINGS
        prompt_text = "\n".join(message["content"] for message in messages)
        assert "Selected branch only" in prompt_text
        assert "Hidden branch" not in prompt_text
        return "Generated swipe alternate"

    monkeypatch.setattr(message_actions, "build_prompt_context", fake_build_prompt_context)
    monkeypatch.setattr(message_actions, "collect_chat_completion", fake_collect_chat_completion)

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
    repository = FakeActionRepository()

    async def fake_build_prompt_context(*args: object, **kwargs: object) -> list[dict[str, str]]:
        assert kwargs["repository"] is repository
        assert kwargs["action"] == "continue"
        assert kwargs["composer_text"] == "finish this sentence"
        return [
            {"role": "assistant", "content": "Original AI response"},
            {"role": "user", "content": "Continue with: finish this sentence"},
        ]

    async def fake_collect_chat_completion(
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ) -> str:
        assert settings == SERVER_SETTINGS
        assert "finish this sentence" in "\n".join(message["content"] for message in messages)
        return "Extended AI response"

    monkeypatch.setattr(message_actions, "build_prompt_context", fake_build_prompt_context)
    monkeypatch.setattr(message_actions, "collect_chat_completion", fake_collect_chat_completion)

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
    repository = FakeActionRepository()

    await message_actions.edit_message_and_mark_stale(
        "user-1",
        "Edited user prompt",
        repository=repository,
    )

    assert repository.messages["user-1"].content_text == "Edited user prompt"
    assert repository.messages["downstream-1"].stale_after_edit is True


async def test_truncate_stale_removes_downstream_rows() -> None:
    repository = FakeActionRepository()
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
    repository = FakeActionRepository()

    await message_actions.keep_stale_after_message("user-1", repository=repository)

    assert repository.keep_choice_message_id == "user-1"
    assert "downstream-1" in repository.messages
