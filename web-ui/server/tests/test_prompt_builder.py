"""Prompt-context contracts for selected branch LLM calls."""

from app.domain.prompt_builder import build_prompt_context


class FakePromptRepository:
    def __init__(self) -> None:
        self.thread = {
            "id": "thread-1",
            "lorebook_json": {"entries": [{"content": "secret world info"}]},
        }
        self.messages = [
            {"role": "user", "content_text": "Hello"},
            {
                "role": "assistant",
                "content_text": "Original branch",
                "selected_alternate_id": "selected-alt",
                "alternates": [
                    {"id": "selected-alt", "content_text": "Selected branch"},
                    {"id": "unused-alt", "content_text": "Hidden branch"},
                ],
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
    assert "secret world info" not in prompt_text


async def test_swipe_selected_branch_only_enters_prompt() -> None:
    repository = FakePromptRepository()

    messages = await build_prompt_context("thread-1", repository=repository, action="swipe")

    prompt_text = "\n".join(message["content"] for message in messages)
    assert "Selected branch" in prompt_text
    assert "Hidden branch" not in prompt_text
