"""Message action contracts for regenerate, swipes, edits, stale rows, and continue."""

from __future__ import annotations

from typing import Protocol

from app.domain.llm_stream import ChatCompletionSettings, collect_chat_completion
from app.domain.prompt_builder import build_prompt_context
from app.storage.models import ThreadMessageShape

REGENERATE_SOURCE_ACTION = "regenerate"
SWIPE_SOURCE_ACTION = "swipe"
CONTINUE_SOURCE_ACTION = "continue"


class MessageActionRepository(Protocol):
    """Repository boundary consumed by durable message action implementations."""

    async def replace_selected_ai_response(
        self,
        message_id: str,
        content_text: str,
        *,
        source_action: str,
    ) -> ThreadMessageShape: ...

    async def add_selected_alternate(
        self,
        message_id: str,
        content_text: str,
        *,
        source_action: str,
    ) -> ThreadMessageShape: ...

    async def edit_message_and_mark_downstream_stale(
        self,
        message_id: str,
        content_text: str,
    ) -> ThreadMessageShape: ...

    async def truncate_stale_after(self, message_id: str) -> list[ThreadMessageShape]: ...

    async def keep_stale_after(self, message_id: str) -> ThreadMessageShape: ...


async def regenerate_ai_turn(
    message_id: str,
    *,
    repository: MessageActionRepository,
    settings: ChatCompletionSettings,
) -> ThreadMessageShape:
    """Regenerate an AI turn through the server-side LLM path and replace selection."""

    raise NotImplementedError


async def create_swipe_alternate(
    message_id: str,
    *,
    repository: MessageActionRepository,
    settings: ChatCompletionSettings,
) -> ThreadMessageShape:
    """Create and select a generated swipe alternate for an existing AI turn."""

    raise NotImplementedError


async def edit_message_and_mark_stale(
    message_id: str,
    content_text: str,
    *,
    repository: MessageActionRepository,
) -> ThreadMessageShape:
    """Edit a prior message and mark downstream turns stale."""

    raise NotImplementedError


async def truncate_stale_after_message(
    message_id: str,
    *,
    repository: MessageActionRepository,
) -> list[ThreadMessageShape]:
    """Drop stale downstream rows after an edited message."""

    raise NotImplementedError


async def keep_stale_after_message(
    message_id: str,
    *,
    repository: MessageActionRepository,
) -> ThreadMessageShape:
    """Record that the user chose to keep stale downstream rows visible."""

    raise NotImplementedError


async def continue_ai_turn(
    message_id: str,
    composer_text: str,
    *,
    repository: MessageActionRepository,
    settings: ChatCompletionSettings,
) -> ThreadMessageShape:
    """Extend the previous AI turn through the server-side LLM path."""

    raise NotImplementedError


__all__ = [
    "CONTINUE_SOURCE_ACTION",
    "MessageActionRepository",
    "REGENERATE_SOURCE_ACTION",
    "SWIPE_SOURCE_ACTION",
    "build_prompt_context",
    "collect_chat_completion",
    "continue_ai_turn",
    "create_swipe_alternate",
    "edit_message_and_mark_stale",
    "keep_stale_after_message",
    "regenerate_ai_turn",
    "truncate_stale_after_message",
]
