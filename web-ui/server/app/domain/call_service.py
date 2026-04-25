"""Durable call preflight, active-session mapping, and thread writeback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.thread_service import (
    CharacterUnavailableError,
    ThreadNotFoundError,
    ThreadService,
    new_message_id,
)
from app.storage.models import Character, Message, Thread, Voice, utc_now

CALL_VOICE_REQUIRED = "call_voice_required"
CALL_VOICE_UNAVAILABLE = "call_voice_unavailable"
CALL_SESSION_NOT_FOUND = "call_session_not_found"

CallEventType = Literal["user_speech", "ai_speech"]


class CallServiceError(Exception):
    """Base public-safe call service error."""

    status_code = 400

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class CallVoiceRequiredError(CallServiceError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            code=CALL_VOICE_REQUIRED,
            message="Assign a voice before calling this character.",
        )


class CallVoiceUnavailableError(CallServiceError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            code=CALL_VOICE_UNAVAILABLE,
            message="The assigned voice is unavailable. Choose another voice before calling.",
        )


class CallSessionNotFoundError(CallServiceError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__(
            code=CALL_SESSION_NOT_FOUND,
            message="Call session was not found",
        )


@dataclass(slots=True)
class ActiveCall:
    call_id: str
    session_id: str
    thread_id: str
    voice_id: str
    engine_id: str
    character_name: str
    voice_name: str
    started_at: datetime
    ended_at: datetime | None = None
    muted: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "session_id": self.session_id,
            "thread_id": self.thread_id,
            "voice_id": self.voice_id,
            "engine_id": self.engine_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "muted": self.muted,
        }


_ACTIVE_CALLS: dict[str, ActiveCall] = {}


def new_call_id() -> str:
    return f"call_{uuid4().hex}"


def new_rtc_session_id() -> str:
    return f"rtc_{uuid4().hex}"


class CallService:
    """Owns call preflight, active call/session mapping, and durable writeback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_call(
        self,
        *,
        thread_id: str | None = None,
        character_id: str | None = None,
    ) -> dict[str, Any]:
        if not thread_id and not character_id:
            raise ThreadNotFoundError("thread_id or character_id is required")

        if thread_id is None:
            assert character_id is not None
            created = await ThreadService(self.session).create_thread(character_id=character_id)
            thread_id = created["thread_id"]

        thread = await self._get_thread(thread_id)
        character = await self._character_for_thread(thread)
        voice = await self._required_available_voice(character.default_voice_id)
        started_at = utc_now()
        call = ActiveCall(
            call_id=new_call_id(),
            session_id=new_rtc_session_id(),
            thread_id=thread.id,
            voice_id=voice.id,
            engine_id=voice.default_engine,
            character_name=character.name,
            voice_name=voice.name,
            started_at=started_at,
        )
        _ACTIVE_CALLS[call.call_id] = call
        await self._append_message(
            thread.id,
            "Call started",
            message_kind="call_start",
            role="event",
        )
        return call.to_public_dict()

    def attach_session(self, call_id: str, session_id: str) -> dict[str, Any]:
        call = self._active_call(call_id)
        call.session_id = session_id
        return call.to_public_dict()

    def session_for_call(self, call_id: str) -> str:
        return self._active_call(call_id).session_id

    async def record_event(self, call_id: str, event: dict[str, Any]) -> dict[str, Any]:
        call = self._active_call(call_id)
        event_type = str(event.get("type") or "")
        if event_type == "user_speech" or event_type == "user_final":
            return await self._append_message(
                call.thread_id,
                str(event.get("text") or ""),
                message_kind="user_speech",
                role="user",
            )
        if event_type == "ai_speech" or event_type == "ai_final":
            return await self._append_message(
                call.thread_id,
                str(event.get("text") or ""),
                message_kind="ai_speech",
                role="assistant",
            )
        return call.to_public_dict()

    def set_muted(self, call_id: str, muted: bool) -> dict[str, Any]:
        call = self._active_call(call_id)
        call.muted = muted
        return call.to_public_dict()

    def interrupt(self, call_id: str) -> dict[str, Any]:
        return self._active_call(call_id).to_public_dict()

    def active_call(self, call_id: str) -> dict[str, Any]:
        return self._active_call(call_id).to_public_dict()

    async def record_user_speech(self, call_id: str, text: str) -> dict[str, Any]:
        call = self._active_call(call_id)
        return await self._append_message(
            call.thread_id,
            text,
            message_kind="user_speech",
            role="user",
        )

    async def record_ai_speech(self, call_id: str, text: str) -> dict[str, Any]:
        call = self._active_call(call_id)
        return await self._append_message(
            call.thread_id,
            text,
            message_kind="ai_speech",
            role="assistant",
        )

    async def end_call(self, call_id: str, reason: str = "hangup") -> dict[str, Any]:
        call = self._active_call(call_id)
        if call.ended_at is None:
            call.ended_at = utc_now()
            await self._append_message(
                call.thread_id,
                "Call ended",
                message_kind="call_end",
                role="event",
            )
        result = call.to_public_dict()
        result["reason"] = reason
        return result

    async def _get_thread(self, thread_id: str) -> Thread:
        result = await self.session.execute(
            select(Thread).where(Thread.id == thread_id, Thread.deleted_at.is_(None))
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            raise ThreadNotFoundError(thread_id)
        return thread

    async def _character_for_thread(self, thread: Thread) -> Character:
        if thread.character_id is None:
            raise CharacterUnavailableError(thread.id)
        result = await self.session.execute(
            select(Character).where(
                Character.id == thread.character_id,
                Character.deleted_at.is_(None),
            )
        )
        character = result.scalar_one_or_none()
        if character is None:
            raise CharacterUnavailableError(thread.character_id)
        return character

    async def _required_available_voice(self, voice_id: str | None) -> Voice:
        if not voice_id:
            raise CallVoiceRequiredError()

        result = await self.session.execute(select(Voice).where(Voice.id == voice_id))
        voice = result.scalar_one_or_none()
        if voice is None or voice.deleted_at is not None:
            raise CallVoiceUnavailableError()
        return voice

    async def _append_message(
        self,
        thread_id: str,
        content_text: str,
        *,
        message_kind: str,
        role: str,
    ) -> dict[str, Any]:
        thread = await self._get_thread(thread_id)
        now = utc_now()
        message = Message(
            id=new_message_id(),
            thread_id=thread_id,
            message_kind=message_kind,
            role=role,
            sequence=await self._next_sequence(thread_id),
            content_text=content_text,
            created_at=now,
            updated_at=now,
        )
        self.session.add(message)
        thread.last_message_at = now
        thread.updated_at = now
        await self.session.commit()
        return {
            "id": message.id,
            "thread_id": message.thread_id,
            "message_kind": message.message_kind,
            "role": message.role,
            "sequence": message.sequence,
            "content_text": message.content_text,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "updated_at": message.updated_at.isoformat() if message.updated_at else None,
        }

    async def _next_sequence(self, thread_id: str) -> int:
        result = await self.session.execute(
            select(func.max(Message.sequence)).where(Message.thread_id == thread_id)
        )
        max_sequence = result.scalar_one_or_none()
        return (max_sequence if max_sequence is not None else -1) + 1

    def _active_call(self, call_id: str) -> ActiveCall:
        call = _ACTIVE_CALLS.get(call_id)
        if call is None:
            raise CallSessionNotFoundError()
        return call


__all__ = [
    "CALL_SESSION_NOT_FOUND",
    "CALL_VOICE_REQUIRED",
    "CALL_VOICE_UNAVAILABLE",
    "ActiveCall",
    "CallService",
    "CallServiceError",
    "CallSessionNotFoundError",
    "CallVoiceRequiredError",
    "CallVoiceUnavailableError",
    "new_call_id",
    "new_rtc_session_id",
]
