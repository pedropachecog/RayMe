"""Prompt-context contracts for selected branch LLM calls."""

from app.domain import prompt_builder
from app.domain.prompt_builder import build_prompt_context


class FakePromptRepository:
    def __init__(self) -> None:
        self.thread = {
            "id": "thread-1",
            "character_snapshot_name": "Ray",
            "character_snapshot_description": "A focused AI caller.",
            "character_snapshot_personality": "Warm and concise.",
            "character_snapshot_scenario": "Late-night LAN testing.",
            "character_snapshot_system_prompt": "Stay in character.",
            "character_snapshot_post_history_instructions": "Keep replies natural.",
            "lorebook_json": {"entries": [{"content": "secret world info"}]},
            "world_info": {"entries": [{"content": "world secret"}]},
        }
        self.messages = [
            {"id": "user-1", "role": "user", "content_text": "Hello"},
            {
                "id": "ai-1",
                "role": "assistant",
                "content_text": "Original branch",
                "selected_alternate_id": "selected-alt",
                "alternates": [
                    {"id": "selected-alt", "content_text": "Selected branch"},
                    {"id": "unused-alt", "content_text": "Hidden branch"},
                ],
            },
            {
                "id": "user-stale",
                "role": "user",
                "content_text": "Edited-away downstream prompt",
                "stale_after_edit": True,
            },
            {
                "id": "ai-stale",
                "role": "assistant",
                "content_text": "Edited-away downstream answer",
                "stale_after_edit": True,
            },
        ]

    async def get_prompt_thread(self, thread_id: str) -> object:
        assert thread_id == self.thread["id"]
        return self


async def test_lorebook_preserved_but_not_injected() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context("thread-1", repository=repository)

    prompt_text = "\n".join(message["content"] for message in messages)
    assert repository.thread["lorebook_json"] is not None
    assert repository.thread["world_info"] is not None
    assert "secret world info" not in prompt_text
    assert "world secret" not in prompt_text


async def test_character_persona_fields_enter_system_context() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context("thread-1", repository=repository)

    assert messages[0]["role"] == "system"
    assert "Stay in character." in messages[0]["content"]
    assert "Name: Ray" in messages[0]["content"]
    assert "Description: A focused AI caller." in messages[0]["content"]
    assert "Personality: Warm and concise." in messages[0]["content"]
    assert "Scenario: Late-night LAN testing." in messages[0]["content"]
    assert "Keep replies natural." in messages[0]["content"]


async def test_swipe_selected_branch_only_enters_prompt() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context("thread-1", repository=repository, action="swipe")

    prompt_text = "\n".join(message["content"] for message in messages)
    assert "Selected branch" in prompt_text
    assert "Hidden branch" not in prompt_text


async def test_continue_includes_composer_text_without_mutating_storage() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context(
        "thread-1",
        repository=repository,
        action="continue",
        composer_text="finish this sentence",
    )

    assert messages[-1]["role"] == "user"
    assert "Continue the previous assistant message." in messages[-1]["content"]
    assert "Return the complete assistant message" in messages[-1]["content"]
    assert "User continuation note: finish this sentence" in messages[-1]["content"]
    assert messages[-2]["role"] == "assistant"
    assert repository.messages[-1]["content_text"] == "Edited-away downstream answer"


async def test_continue_without_composer_text_avoids_assistant_prefill() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context(
        "thread-1",
        repository=repository,
        action="continue",
        until_message_id="ai-1",
        composer_text="",
    )

    assert messages[-1] == {
        "role": "user",
        "content": (
            "Continue the previous assistant message. Return the complete assistant message, "
            "including the existing text and the continuation."
        ),
    }
    assert messages[-2] == {"role": "assistant", "content": "Selected branch"}


async def test_stale_rows_are_excluded_from_prompt_context() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context("thread-1", repository=repository)

    prompt_text = "\n".join(message["content"] for message in messages)
    assert "Edited-away downstream prompt" not in prompt_text
    assert "Edited-away downstream answer" not in prompt_text


async def test_until_message_id_stops_context_at_selected_branch_position() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context(
        "thread-1",
        repository=repository,
        until_message_id="user-1",
        action="regenerate",
    )

    prompt_text = "\n".join(message["content"] for message in messages)
    assert "Hello" in prompt_text
    assert "Selected branch" not in prompt_text


class CallPromptRepository:
    def __init__(self) -> None:
        self.thread = {
            "id": "thread-call",
            "character_snapshot_name": "Ray",
            "character_snapshot_description": "A focused AI caller.",
            "character_snapshot_personality": "Warm and concise.",
            "character_snapshot_scenario": "Late-night LAN testing.",
            "character_snapshot_system_prompt": "Stay in character.",
            "character_snapshot_post_history_instructions": "Keep replies natural.",
        }
        self.messages = [
            {
                "id": "call-start",
                "role": "event",
                "message_kind": "call_start",
                "content_text": "Call started",
            },
            {
                "id": "user-text",
                "role": "user",
                "message_kind": "user_text",
                "content_text": "Typed context before the call.",
            },
            {
                "id": "ai-text",
                "role": "assistant",
                "message_kind": "ai_text",
                "content_text": "Hidden unselected branch.",
                "selected_alternate_id": "call-selected-alt",
                "alternates": [
                    {"id": "call-selected-alt", "content_text": "Selected text branch."},
                    {"id": "call-hidden-alt", "content_text": "Hidden alternate branch."},
                ],
            },
            {
                "id": "user-speech",
                "role": "user",
                "message_kind": "user_speech",
                "content_text": "Spoken user turn.",
            },
            {
                "id": "ai-speech",
                "role": "assistant",
                "message_kind": "ai_speech",
                "content_text": "Spoken assistant answer.",
            },
            {
                "id": "stale-user-speech",
                "role": "user",
                "message_kind": "user_speech",
                "content_text": "Edited-away spoken prompt.",
                "stale_after_edit": True,
            },
            {
                "id": "call-end",
                "role": "event",
                "message_kind": "call_end",
                "content_text": "Call ended",
            },
        ]

    async def get_prompt_thread(self, thread_id: str) -> object:
        assert thread_id == self.thread["id"]
        return self


async def test_call_context_includes_text_and_speech_but_excludes_call_events() -> None:
    repository = CallPromptRepository()

    messages = await _build_call_prompt_context("thread-call", max_turns=24, repository=repository)

    assert messages[0]["role"] == "system"
    assert "Stay in character." in messages[0]["content"]
    prompt_text = "\n".join(message["content"] for message in messages)
    assert "Typed context before the call." in prompt_text
    assert "Selected text branch." in prompt_text
    assert "Hidden alternate branch." not in prompt_text
    assert "Spoken user turn." in prompt_text
    assert "Spoken assistant answer." in prompt_text
    assert "Edited-away spoken prompt." not in prompt_text
    assert "Call started" not in prompt_text
    assert "Call ended" not in prompt_text
    assert "call_start" not in prompt_text
    assert "call_end" not in prompt_text


async def test_call_context_sliding_window_limits_to_recent_24_turn_messages() -> None:
    repository = CallPromptRepository()
    repository.messages = [
        {
            "id": "setup-call-start",
            "role": "event",
            "message_kind": "call_start",
            "content_text": "Call started",
        },
        *[
            {
                "id": f"turn-{index:02d}",
                "role": "user" if index % 2 == 0 else "assistant",
                "message_kind": "user_speech" if index % 2 == 0 else "ai_speech",
                "content_text": f"Call turn {index:02d}",
            }
            for index in range(30)
        ],
        {
            "id": "setup-call-end",
            "role": "event",
            "message_kind": "call_end",
            "content_text": "Call ended",
        },
    ]

    messages = await _build_call_prompt_context("thread-call", max_turns=24, repository=repository)

    assert messages[0]["role"] == "system"
    assert len(messages) <= 25
    turn_messages = messages[1:]
    assert len(turn_messages) <= 24
    assert [message["content"] for message in turn_messages] == [
        f"Call turn {index:02d}" for index in range(6, 30)
    ]


async def _build_call_prompt_context(
    thread_id: str,
    *,
    max_turns: int,
    repository: object,
) -> list[dict[str, str]]:
    build_call_prompt_context = getattr(prompt_builder, "build_call_prompt_context")
    return await build_call_prompt_context(thread_id, max_turns=max_turns, repository=repository)
