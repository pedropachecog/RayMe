"""Durable message actions for regenerate, swipes, edits, stale rows, and continue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.llm_stream import ChatCompletionSettings, collect_chat_completion
from app.domain.prompt_builder import build_prompt_context
from app.domain.thread_service import ThreadNotFoundError, ThreadService, new_alternate_id
from app.storage.models import (
    Message,
    MessageAlternate,
    MessageAlternateShape,
    MessageAlternateSourceAction,
    Thread,
    ThreadMessageShape,
    utc_now,
)

REGENERATE_SOURCE_ACTION = "regenerate"
SWIPE_SOURCE_ACTION = "swipe"
CONTINUE_SOURCE_ACTION = "continue"


class MessageActionNotFoundError(LookupError):
    """Raised when a message action target cannot be found."""


class InvalidMessageActionError(ValueError):
    """Raised when an action is not valid for the requested message."""


@dataclass(frozen=True, slots=True)
class MessageGenerationContext:
    """Prompt metadata for generation actions."""

    thread_id: str
    message_id: str
    message_kind: str
    role: str
    until_message_id: str | None


class MessageActionRepository(Protocol):
    """Repository boundary consumed by durable message action implementations."""

    async def get_prompt_thread(self, thread_id: str) -> object: ...

    async def get_generation_context(
        self,
        message_id: str,
        *,
        include_target: bool,
    ) -> MessageGenerationContext: ...

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

    async def select_alternate(self, message_id: str, alternate_id: str) -> ThreadMessageShape: ...

    async def edit_message_and_mark_downstream_stale(
        self,
        message_id: str,
        content_text: str,
    ) -> ThreadMessageShape: ...

    async def truncate_stale_after(self, message_id: str) -> list[ThreadMessageShape]: ...

    async def keep_stale_after(self, message_id: str) -> ThreadMessageShape: ...


class SqlAlchemyMessageActionRepository:
    """SQLAlchemy-backed branch and stale-state mutations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_prompt_thread(self, thread_id: str) -> object:
        return await ThreadService(self.session).get_thread_detail(thread_id)

    async def get_generation_context(
        self,
        message_id: str,
        *,
        include_target: bool,
    ) -> MessageGenerationContext:
        message = await self._get_message(message_id)
        until_message_id = message.id if include_target else await self._previous_message_id(message)
        return MessageGenerationContext(
            thread_id=message.thread_id,
            message_id=message.id,
            message_kind=message.message_kind,
            role=message.role,
            until_message_id=until_message_id,
        )

    async def replace_selected_ai_response(
        self,
        message_id: str,
        content_text: str,
        *,
        source_action: str,
    ) -> ThreadMessageShape:
        message = await self._get_ai_message(message_id)
        now = utc_now()
        alternate = MessageAlternate(
            id=new_alternate_id(),
            message_id=message.id,
            alternate_index=await self._next_alternate_index(message.id),
            content_text=content_text,
            source_action=_source_action(source_action),
            branch_root_id=message.id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(alternate)
        message.content_text = content_text
        message.selected_alternate_id = alternate.id
        message.updated_at = now
        await self._touch_thread(message.thread_id, now)
        await self.session.commit()
        return await self._hydrate_message(message.thread_id, message.id)

    async def add_selected_alternate(
        self,
        message_id: str,
        content_text: str,
        *,
        source_action: str,
    ) -> ThreadMessageShape:
        message = await self._get_ai_message(message_id)
        now = utc_now()
        alternate = MessageAlternate(
            id=new_alternate_id(),
            message_id=message.id,
            alternate_index=await self._next_alternate_index(message.id),
            content_text=content_text,
            source_action=_source_action(source_action),
            branch_root_id=message.id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(alternate)
        message.selected_alternate_id = alternate.id
        message.updated_at = now
        await self._touch_thread(message.thread_id, now)
        await self.session.commit()
        return await self._hydrate_message(message.thread_id, message.id)

    async def select_alternate(self, message_id: str, alternate_id: str) -> ThreadMessageShape:
        message = await self._get_ai_message(message_id)
        result = await self.session.execute(
            select(MessageAlternate).where(
                MessageAlternate.message_id == message.id,
                MessageAlternate.id == alternate_id,
            )
        )
        alternate = result.scalar_one_or_none()
        if alternate is None:
            raise MessageActionNotFoundError(alternate_id)

        now = utc_now()
        message.selected_alternate_id = alternate.id
        message.updated_at = now
        await self._touch_thread(message.thread_id, now)
        await self.session.commit()
        return await self._hydrate_message(message.thread_id, message.id)

    async def edit_message_and_mark_downstream_stale(
        self,
        message_id: str,
        content_text: str,
    ) -> ThreadMessageShape:
        message = await self._get_message(message_id)
        now = utc_now()
        message.content_text = content_text
        message.updated_at = now

        if message.selected_alternate_id is not None:
            selected = await self.session.get(MessageAlternate, message.selected_alternate_id)
            if selected is not None and selected.message_id == message.id:
                selected.content_text = content_text
                selected.updated_at = now

        await self.session.execute(
            update(Message)
            .where(
                Message.thread_id == message.thread_id,
                Message.sequence > message.sequence,
            )
            .values(stale_after_edit=True, updated_at=now)
        )
        await self._touch_thread(message.thread_id, now)
        await self.session.commit()
        return await self._hydrate_message(message.thread_id, message.id)

    async def truncate_stale_after(self, message_id: str) -> list[ThreadMessageShape]:
        message = await self._get_message(message_id)
        stale_message_ids = select(Message.id).where(
            Message.thread_id == message.thread_id,
            Message.sequence > message.sequence,
            Message.stale_after_edit.is_(True),
        )
        await self.session.execute(
            delete(MessageAlternate).where(MessageAlternate.message_id.in_(stale_message_ids))
        )
        await self.session.execute(delete(Message).where(Message.id.in_(stale_message_ids)))
        await self._touch_thread(message.thread_id, utc_now())
        await self.session.commit()
        return await self._hydrate_thread_messages(message.thread_id)

    async def keep_stale_after(self, message_id: str) -> ThreadMessageShape:
        message = await self._get_message(message_id)
        await self._touch_thread(message.thread_id, utc_now())
        await self.session.commit()
        return await self._hydrate_message(message.thread_id, message.id)

    async def _get_message(self, message_id: str) -> Message:
        result = await self.session.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()
        if message is None:
            raise MessageActionNotFoundError(message_id)
        return message

    async def _get_ai_message(self, message_id: str) -> Message:
        message = await self._get_message(message_id)
        if message.role != "assistant" or not message.message_kind.startswith("ai_"):
            raise InvalidMessageActionError("Message action requires an AI message")
        return message

    async def _previous_message_id(self, message: Message) -> str | None:
        result = await self.session.execute(
            select(Message.id)
            .where(
                Message.thread_id == message.thread_id,
                Message.sequence < message.sequence,
                Message.stale_after_edit.is_(False),
            )
            .order_by(Message.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _next_alternate_index(self, message_id: str) -> int:
        result = await self.session.execute(
            select(func.max(MessageAlternate.alternate_index)).where(
                MessageAlternate.message_id == message_id
            )
        )
        max_index = result.scalar_one_or_none()
        return (max_index if max_index is not None else -1) + 1

    async def _touch_thread(self, thread_id: str, when: object) -> None:
        result = await self.session.execute(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.deleted_at.is_(None),
            )
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            raise ThreadNotFoundError(thread_id)
        thread.updated_at = when
        thread.last_message_at = when

    async def _hydrate_message(self, thread_id: str, message_id: str) -> ThreadMessageShape:
        for message in await self._hydrate_thread_messages(thread_id):
            if message.id == message_id:
                return message
        raise MessageActionNotFoundError(message_id)

    async def _hydrate_thread_messages(self, thread_id: str) -> list[ThreadMessageShape]:
        detail = await ThreadService(self.session).get_thread_detail(thread_id)
        return [_shape_from_thread_message_dict(message) for message in detail["messages"]]


async def regenerate_ai_turn(
    message_id: str,
    *,
    repository: MessageActionRepository,
    settings: ChatCompletionSettings,
    completion_client: object | None = None,
) -> ThreadMessageShape:
    """Regenerate an AI turn through the server-side LLM path and replace selection."""

    context = await _generation_context(message_id, repository, include_target=False)
    prompt_messages = await build_prompt_context(
        context.thread_id,
        repository=repository,
        until_message_id=context.until_message_id,
        action=REGENERATE_SOURCE_ACTION,
    )
    content_text = await _collect_generated_text(
        settings,
        prompt_messages,
        completion_client=completion_client,
    )
    return await repository.replace_selected_ai_response(
        message_id,
        content_text,
        source_action=REGENERATE_SOURCE_ACTION,
    )


async def create_swipe_alternate(
    message_id: str,
    *,
    repository: MessageActionRepository,
    settings: ChatCompletionSettings,
    completion_client: object | None = None,
) -> ThreadMessageShape:
    """Create and select a generated swipe alternate for an existing AI turn."""

    context = await _generation_context(message_id, repository, include_target=False)
    prompt_messages = await build_prompt_context(
        context.thread_id,
        repository=repository,
        until_message_id=context.until_message_id,
        action=SWIPE_SOURCE_ACTION,
    )
    content_text = await _collect_generated_text(
        settings,
        prompt_messages,
        completion_client=completion_client,
    )
    return await repository.add_selected_alternate(
        message_id,
        content_text,
        source_action=SWIPE_SOURCE_ACTION,
    )


async def select_message_alternate(
    message_id: str,
    alternate_id: str,
    *,
    repository: MessageActionRepository,
) -> ThreadMessageShape:
    """Select an existing alternate as the canonical branch for future context."""

    return await repository.select_alternate(message_id, alternate_id)


async def edit_message_and_mark_stale(
    message_id: str,
    content_text: str,
    *,
    repository: MessageActionRepository,
) -> ThreadMessageShape:
    """Edit a prior message and mark downstream turns stale."""

    return await repository.edit_message_and_mark_downstream_stale(message_id, content_text)


async def truncate_stale_after_message(
    message_id: str,
    *,
    repository: MessageActionRepository,
) -> list[ThreadMessageShape]:
    """Drop stale downstream rows after an edited message."""

    return await repository.truncate_stale_after(message_id)


async def keep_stale_after_message(
    message_id: str,
    *,
    repository: MessageActionRepository,
) -> ThreadMessageShape:
    """Record that the user chose to keep stale downstream rows visible."""

    return await repository.keep_stale_after(message_id)


async def continue_ai_turn(
    message_id: str,
    composer_text: str,
    *,
    repository: MessageActionRepository,
    settings: ChatCompletionSettings,
    completion_client: object | None = None,
) -> ThreadMessageShape:
    """Extend the previous AI turn through the server-side LLM path."""

    context = await _generation_context(message_id, repository, include_target=True)
    prompt_messages = await build_prompt_context(
        context.thread_id,
        repository=repository,
        until_message_id=context.until_message_id,
        action=CONTINUE_SOURCE_ACTION,
        composer_text=composer_text,
    )
    content_text = await _collect_generated_text(
        settings,
        prompt_messages,
        completion_client=completion_client,
    )
    return await repository.add_selected_alternate(
        message_id,
        content_text,
        source_action=CONTINUE_SOURCE_ACTION,
    )


async def _generation_context(
    message_id: str,
    repository: MessageActionRepository,
    *,
    include_target: bool,
) -> MessageGenerationContext:
    context = await repository.get_generation_context(message_id, include_target=include_target)
    if context.role != "assistant" or not context.message_kind.startswith("ai_"):
        raise InvalidMessageActionError("Message action requires an AI message")
    return context


async def _collect_generated_text(
    settings: ChatCompletionSettings,
    prompt_messages: object,
    *,
    completion_client: object | None,
) -> str:
    if completion_client is None:
        return await collect_chat_completion(settings, prompt_messages)
    return await collect_chat_completion(settings, prompt_messages, client=completion_client)


def _source_action(source_action: str) -> MessageAlternateSourceAction:
    if source_action not in {
        REGENERATE_SOURCE_ACTION,
        SWIPE_SOURCE_ACTION,
        CONTINUE_SOURCE_ACTION,
    }:
        raise InvalidMessageActionError("Unsupported message alternate source action")
    return source_action  # type: ignore[return-value]


def _shape_from_thread_message_dict(message: dict[str, object]) -> ThreadMessageShape:
    return ThreadMessageShape(
        id=str(message["id"]),
        thread_id=str(message["thread_id"]),
        message_kind=message["message_kind"],  # type: ignore[arg-type]
        role=message["role"],  # type: ignore[arg-type]
        sequence=int(message["sequence"]),
        content_text=_optional_string(message["content_text"]),
        selected_alternate_id=_optional_string(message["selected_alternate_id"]),
        alternates=[
            MessageAlternateShape(
                id=str(alternate["id"]),
                message_id=str(alternate["message_id"]),
                alternate_index=int(alternate["alternate_index"]),
                content_text=str(alternate["content_text"]),
                source_action=alternate["source_action"],  # type: ignore[arg-type]
                created_at=_optional_string(alternate["created_at"]),
            )
            for alternate in _alternates_from_dict(message)
        ],
        stale_after_edit=bool(message["stale_after_edit"]),
        created_at=_optional_string(message["created_at"]),
        updated_at=_optional_string(message["updated_at"]),
    )


def _alternates_from_dict(message: dict[str, object]) -> list[dict[str, object]]:
    alternates = message.get("alternates")
    return alternates if isinstance(alternates, list) else []


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "CONTINUE_SOURCE_ACTION",
    "InvalidMessageActionError",
    "MessageActionRepository",
    "MessageActionNotFoundError",
    "MessageGenerationContext",
    "REGENERATE_SOURCE_ACTION",
    "SWIPE_SOURCE_ACTION",
    "SqlAlchemyMessageActionRepository",
    "build_prompt_context",
    "collect_chat_completion",
    "continue_ai_turn",
    "create_swipe_alternate",
    "edit_message_and_mark_stale",
    "keep_stale_after_message",
    "regenerate_ai_turn",
    "select_message_alternate",
    "truncate_stale_after_message",
]
