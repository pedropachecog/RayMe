"""Prompt-context contracts for selected branch LLM calls."""

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

    assert messages[-1] == {
        "role": "user",
        "content": "Continue with: finish this sentence",
    }
    assert repository.messages[-1]["content_text"] == "Edited-away downstream answer"


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
