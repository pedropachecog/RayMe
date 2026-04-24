"""Thread creation, listing, hydration, rename, and delete services."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.character_service import portrait_url_for_asset
from app.storage.models import (
    Character,
    CharacterAsset,
    Message,
    MessageAlternate,
    MessageAlternateShape,
    Thread,
    ThreadMessageShape,
    utc_now,
)

ACTIVE_PORTRAIT_KIND = "portrait"


class CharacterUnavailableError(LookupError):
    """Raised when a thread cannot be created for the requested character."""


class ThreadNotFoundError(LookupError):
    """Raised when a requested thread does not exist."""


@dataclass(frozen=True, slots=True)
class AlternateGreetingIndexError(ValueError):
    """Raised when the selected alternate greeting index is outside the card range."""

    requested_index: int
    alternate_count: int

    @property
    def detail(self) -> dict[str, Any]:
        return {
            "code": "alternate_greeting_index_out_of_range",
            "message": "alternate_greeting_index is outside the character alternate greetings range",
            "alternate_greeting_index": self.requested_index,
            "alternate_greeting_count": self.alternate_count,
        }


def new_thread_id() -> str:
    return f"thread_{uuid4().hex}"


def new_message_id() -> str:
    return f"msg_{uuid4().hex}"


def new_alternate_id() -> str:
    return f"alt_{uuid4().hex}"


class ThreadService:
    """SQLAlchemy-backed thread API service."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_threads(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Thread)
            .where(Thread.deleted_at.is_(None))
            .order_by(Thread.updated_at.desc(), Thread.last_message_at.desc(), Thread.created_at.desc())
        )
        threads = list(result.scalars())
        return [await self._thread_list_item(thread) for thread in threads]

    async def create_thread(
        self,
        *,
        character_id: str,
        title: str | None = None,
        alternate_greeting_index: int | None = None,
    ) -> dict[str, str]:
        character = await self._get_character_for_thread(character_id)
        opening_text, opening_index = self._resolve_opening_message(
            character,
            alternate_greeting_index,
        )
        now = utc_now()
        thread = Thread(
            id=new_thread_id(),
            character_id=character.id,
            title=_coalesce_title(title, character.name),
            character_snapshot_name=character.name,
            character_snapshot_description=character.description,
            character_snapshot_personality=character.personality,
            character_snapshot_scenario=character.scenario,
            character_snapshot_first_mes=character.first_mes,
            character_snapshot_system_prompt=character.system_prompt,
            character_snapshot_post_history_instructions=(
                character.post_history_instructions
            ),
            character_snapshot_lorebook_json=character.lorebook_json,
            character_snapshot_raw_source_json=character.raw_source_json,
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(thread)
        await self.session.flush()

        opening_message = Message(
            id=new_message_id(),
            thread_id=thread.id,
            message_kind="ai_text",
            role="assistant",
            sequence=0,
            content_text=opening_text,
            created_at=now,
            updated_at=now,
        )
        self.session.add(opening_message)
        await self.session.flush()

        opening_alternate = MessageAlternate(
            id=new_alternate_id(),
            message_id=opening_message.id,
            alternate_index=opening_index,
            content_text=opening_text,
            source_action="first_mes",
            created_at=now,
            updated_at=now,
        )
        opening_message.selected_alternate_id = opening_alternate.id
        self.session.add(opening_alternate)
        await self.session.commit()
        return {"thread_id": thread.id}

    async def get_thread_detail(self, thread_id: str) -> dict[str, Any]:
        thread = await self._get_thread(thread_id)
        messages = await self._hydrate_messages(thread.id)
        portrait = await self._active_portrait(thread.character_id)
        return {
            "id": thread.id,
            "title": thread.title,
            "character_id": thread.character_id,
            "character_name": thread.character_snapshot_name,
            "character_portrait_url": portrait_url_for_asset(thread.character_id, portrait),
            "character_portrait_asset_id": portrait.id if portrait else None,
            "character_portrait_storage_path": portrait.storage_path if portrait else None,
            "character_snapshot": {
                "name": thread.character_snapshot_name,
                "description": thread.character_snapshot_description,
                "personality": thread.character_snapshot_personality,
                "scenario": thread.character_snapshot_scenario,
                "first_mes": thread.character_snapshot_first_mes,
                "system_prompt": thread.character_snapshot_system_prompt,
                "post_history_instructions": (
                    thread.character_snapshot_post_history_instructions
                ),
                "lorebook_json": thread.character_snapshot_lorebook_json,
                "raw_source_json": thread.character_snapshot_raw_source_json,
            },
            "messages": [message.to_dict() for message in messages],
            "last_message_at": _isoformat(thread.last_message_at),
            "created_at": _isoformat(thread.created_at),
            "updated_at": _isoformat(thread.updated_at),
        }

    async def rename_thread(self, thread_id: str, title: str) -> dict[str, Any]:
        thread = await self._get_thread(thread_id)
        stripped_title = title.strip()
        if not stripped_title:
            raise ValueError("Thread title is required")

        thread.title = stripped_title
        thread.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(thread)
        return {
            "thread_id": thread.id,
            "title": thread.title,
            "updated_at": _isoformat(thread.updated_at),
        }

    async def delete_thread(self, thread_id: str) -> dict[str, Any]:
        await self._get_thread(thread_id)
        message_ids = select(Message.id).where(Message.thread_id == thread_id)
        await self.session.execute(
            delete(MessageAlternate).where(MessageAlternate.message_id.in_(message_ids))
        )
        await self.session.execute(delete(Message).where(Message.thread_id == thread_id))
        await self.session.execute(delete(Thread).where(Thread.id == thread_id))
        await self.session.commit()
        return {"thread_id": thread_id, "deleted": True}

    async def _get_character_for_thread(self, character_id: str) -> Character:
        result = await self.session.execute(
            select(Character).where(
                Character.id == character_id,
                Character.deleted_at.is_(None),
            )
        )
        character = result.scalar_one_or_none()
        if character is None:
            raise CharacterUnavailableError(character_id)
        return character

    async def _get_thread(self, thread_id: str) -> Thread:
        result = await self.session.execute(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.deleted_at.is_(None),
            )
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            raise ThreadNotFoundError(thread_id)
        return thread

    def _resolve_opening_message(
        self,
        character: Character,
        alternate_greeting_index: int | None,
    ) -> tuple[str, int]:
        alternate_greetings = list(character.alternate_greetings_json or [])
        if alternate_greeting_index is None:
            return character.first_mes or "", 0

        if alternate_greeting_index < 0 or alternate_greeting_index >= len(alternate_greetings):
            raise AlternateGreetingIndexError(
                requested_index=alternate_greeting_index,
                alternate_count=len(alternate_greetings),
            )

        return str(alternate_greetings[alternate_greeting_index]), alternate_greeting_index

    async def _thread_list_item(self, thread: Thread) -> dict[str, Any]:
        messages = await self._hydrate_messages(thread.id)
        last_message = messages[-1] if messages else None
        portrait = await self._active_portrait(thread.character_id)
        return {
            "id": thread.id,
            "title": thread.title,
            "character_id": thread.character_id,
            "character_name": thread.character_snapshot_name,
            "character_portrait_url": portrait_url_for_asset(thread.character_id, portrait),
            "character_portrait_asset_id": portrait.id if portrait else None,
            "character_portrait_storage_path": portrait.storage_path if portrait else None,
            "last_message_snippet": _snippet(last_message.selected_content() if last_message else None),
            "last_message_at": _isoformat(thread.last_message_at),
            "created_at": _isoformat(thread.created_at),
            "updated_at": _isoformat(thread.updated_at),
        }

    async def _hydrate_messages(self, thread_id: str) -> list[ThreadMessageShape]:
        result = await self.session.execute(
            select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence)
        )
        messages = list(result.scalars())
        if not messages:
            return []

        alternates_by_message_id = await self._alternates_by_message_id(
            message.id for message in messages
        )
        return [
            ThreadMessageShape(
                id=message.id,
                thread_id=message.thread_id,
                message_kind=message.message_kind,
                role=message.role,
                sequence=message.sequence,
                content_text=message.content_text,
                selected_alternate_id=message.selected_alternate_id,
                alternates=alternates_by_message_id.get(message.id, []),
                stale_after_edit=message.stale_after_edit,
                created_at=_isoformat(message.created_at),
                updated_at=_isoformat(message.updated_at),
            )
            for message in messages
        ]

    async def _alternates_by_message_id(
        self,
        message_ids: Iterable[str],
    ) -> dict[str, list[MessageAlternateShape]]:
        ids = list(message_ids)
        if not ids:
            return {}

        result = await self.session.execute(
            select(MessageAlternate)
            .where(MessageAlternate.message_id.in_(ids))
            .order_by(MessageAlternate.message_id, MessageAlternate.alternate_index)
        )
        grouped: dict[str, list[MessageAlternateShape]] = {}
        for alternate in result.scalars():
            grouped.setdefault(alternate.message_id, []).append(
                MessageAlternateShape(
                    id=alternate.id,
                    message_id=alternate.message_id,
                    alternate_index=alternate.alternate_index,
                    content_text=alternate.content_text,
                    source_action=alternate.source_action,
                    created_at=_isoformat(alternate.created_at),
                )
            )
        return grouped

    async def _active_portrait(self, character_id: str | None) -> CharacterAsset | None:
        if character_id is None:
            return None

        result = await self.session.execute(
            select(CharacterAsset)
            .where(
                CharacterAsset.character_id == character_id,
                CharacterAsset.asset_kind == ACTIVE_PORTRAIT_KIND,
            )
            .order_by(CharacterAsset.created_at.desc())
        )
        return result.scalars().first()


def _coalesce_title(title: str | None, fallback: str) -> str:
    if title is None:
        return fallback
    stripped = title.strip()
    return stripped or fallback


def _snippet(content: str | None, *, max_length: int = 120) -> str:
    text = " ".join((content or "").split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}..."


def _isoformat(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


__all__ = [
    "ACTIVE_PORTRAIT_KIND",
    "AlternateGreetingIndexError",
    "CharacterUnavailableError",
    "ThreadNotFoundError",
    "ThreadService",
    "new_alternate_id",
    "new_message_id",
    "new_thread_id",
]
