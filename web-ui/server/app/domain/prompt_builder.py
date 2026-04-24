"""Prompt context contract for selected-branch chat history."""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict

PromptAction = Literal["send", "regenerate", "swipe", "continue"]


class PromptContextMessage(TypedDict):
    role: str
    content: str


class PromptContextRepository(Protocol):
    """Repository boundary consumed by the prompt builder implementation."""

    async def get_prompt_thread(self, thread_id: str) -> object: ...


async def build_prompt_context(
    thread_id: str,
    *,
    repository: PromptContextRepository | None = None,
    until_message_id: str | None = None,
    action: PromptAction | None = None,
    composer_text: str | None = None,
) -> list[PromptContextMessage]:
    """Build LLM messages from the selected non-stale branch only."""

    raise NotImplementedError


__all__ = [
    "PromptAction",
    "PromptContextMessage",
    "PromptContextRepository",
    "build_prompt_context",
]
