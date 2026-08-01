"""Durable call preflight, active-session mapping, and thread writeback."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ai_backend_client import SpeechTurnTerminal
from app.domain.thread_service import (
    CharacterUnavailableError,
    ThreadNotFoundError,
    ThreadService,
    new_message_id,
)
from app.domain.voice_service import (
    QWEN3_ENGINE_ID,
    VOXCPM2_ENGINE_ID,
    VoiceAssetNotFoundError,
    VoiceMetadataValidationError,
    VoiceService,
    canonical_voice_engine_id_for_read,
    normalize_voxcpm2_engine_settings,
    validate_saved_qwen3_reference,
)
from app.storage.models import CallTurn, Character, Message, Thread, Voice, utc_now

logger = logging.getLogger(__name__)

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
    completed_ai_turn_ids: set[str] = field(default_factory=set, repr=False)
    pending_ai_turn_ids: set[str] = field(default_factory=set, repr=False)
    lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    persistence_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    active_turn_tasks: set[Any] = field(default_factory=set, repr=False)
    turn_states: dict[str, str] = field(default_factory=dict, repr=False)
    end_message_recorded: bool = field(default=False, repr=False)

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


@dataclass(frozen=True, slots=True)
class CallVoicePreparation:
    voice_id: str
    backend_voice_id: str
    engine_id: str
    reference_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CallTurnReservation:
    created: bool
    state: str
    request_matches: bool


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
        preflight: CallVoicePreparation,
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
        engine_id = canonical_voice_engine_id_for_read(voice.default_engine)
        if voice.id != preflight.voice_id or engine_id != preflight.engine_id:
            raise CallVoiceUnavailableError()
        started_at = utc_now()
        call = ActiveCall(
            call_id=new_call_id(),
            session_id=new_rtc_session_id(),
            thread_id=thread.id,
            voice_id=voice.id,
            engine_id=engine_id,
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

    async def preflight_call_voice(
        self,
        *,
        thread_id: str | None,
        character_id: str | None,
        voice_blob_dir: Path,
    ) -> CallVoicePreparation:
        """Validate the selected saved voice before any backend request."""
        if not thread_id and not character_id:
            raise ThreadNotFoundError("thread_id or character_id is required")
        if thread_id is not None:
            character = await self._character_for_thread(await self._get_thread(thread_id))
        else:
            assert character_id is not None
            character = await self._get_character(character_id)
        voice = await self._required_available_voice(character.default_voice_id)
        return await self._voice_preparation(voice, voice_blob_dir)

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

    async def reserve_call_turn(
        self,
        call_id: str,
        *,
        turn_id: str,
        text: str,
        task: Any | None,
    ) -> CallTurnReservation:
        """Durably own a turn before user history, prompt, LLM, or TTS work."""
        call = self._active_call(call_id)
        request_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        async with call.lifecycle_lock:
            if call.ended_at is not None:
                raise CallSessionNotFoundError()
            known_state = call.turn_states.get(turn_id)
            if known_state is not None:
                existing = await self.session.scalar(
                    select(CallTurn).where(
                        CallTurn.call_id == call_id,
                        CallTurn.turn_id == turn_id,
                    )
                )
                return CallTurnReservation(
                    created=False,
                    state=known_state,
                    request_matches=(
                        existing is not None
                        and existing.request_sha256 == request_sha256
                    ),
                )

            existing = await self.session.scalar(
                select(CallTurn).where(
                    CallTurn.call_id == call_id,
                    CallTurn.turn_id == turn_id,
                )
            )
            if existing is not None:
                call.turn_states[turn_id] = existing.state
                return CallTurnReservation(
                    created=False,
                    state=existing.state,
                    request_matches=existing.request_sha256 == request_sha256,
                )

            now = utc_now()
            turn = CallTurn(
                id=f"call_turn_{uuid4().hex}",
                call_id=call_id,
                turn_id=turn_id,
                thread_id=call.thread_id,
                request_sha256=request_sha256,
                state="reserved",
                created_at=now,
                updated_at=now,
            )
            self.session.add(turn)
            try:
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                existing = await self.session.scalar(
                    select(CallTurn).where(
                        CallTurn.call_id == call_id,
                        CallTurn.turn_id == turn_id,
                    )
                )
                if existing is None:
                    raise
                call.turn_states[turn_id] = existing.state
                return CallTurnReservation(
                    created=False,
                    state=existing.state,
                    request_matches=existing.request_sha256 == request_sha256,
                )
            call.turn_states[turn_id] = "reserved"
            if task is not None:
                call.active_turn_tasks.add(task)
            return CallTurnReservation(
                created=True,
                state="reserved",
                request_matches=True,
            )

    async def register_active_turn(self, call_id: str, task: Any) -> bool:
        call = self._active_call(call_id)
        async with call.lifecycle_lock:
            if call.ended_at is not None:
                return False
            call.active_turn_tasks.add(task)
            return True

    async def unregister_active_turn(self, call_id: str, task: Any) -> None:
        call = self._active_call(call_id)
        async with call.lifecycle_lock:
            call.active_turn_tasks.discard(task)

    async def cancel_active_turns(self, call_id: str) -> None:
        call = self._active_call(call_id)
        async with call.lifecycle_lock:
            tasks = tuple(call.active_turn_tasks)
            for task in tasks:
                task.cancel()
        awaitable_tasks = [task for task in tasks if isinstance(task, asyncio.Future)]
        if awaitable_tasks:
            await asyncio.gather(*awaitable_tasks, return_exceptions=True)
        async with call.lifecycle_lock:
            call.active_turn_tasks.difference_update(tasks)

    async def record_user_speech(self, call_id: str, text: str) -> dict[str, Any]:
        call = self._active_call(call_id)
        return await self._append_message(
            call.thread_id,
            text,
            message_kind="user_speech",
            role="user",
        )

    async def record_reserved_user_speech(
        self,
        call_id: str,
        *,
        turn_id: str,
        text: str,
    ) -> dict[str, Any] | None:
        call = self._active_call(call_id)
        async with call.persistence_lock:
            async with call.lifecycle_lock:
                if (
                    call.ended_at is not None
                    or call.turn_states.get(turn_id) != "reserved"
                ):
                    return None
                message = await self._stage_message(
                    call.thread_id,
                    text,
                    message_kind="user_speech",
                    role="user",
                )
                turn = await self.session.scalar(
                    select(CallTurn).where(
                        CallTurn.call_id == call_id,
                        CallTurn.turn_id == turn_id,
                    )
                )
                if turn is None or turn.state != "reserved":
                    await self.session.rollback()
                    return None
                turn.user_message_id = str(message["id"])
                turn.state = "running"
                turn.updated_at = utc_now()
                await self.session.commit()
                call.turn_states[turn_id] = "running"
                return message

    async def record_ai_speech(self, call_id: str, text: str) -> dict[str, Any]:
        call = self._active_call(call_id)
        return await self._append_message(
            call.thread_id,
            text,
            message_kind="ai_speech",
            role="assistant",
        )

    async def record_completed_ai_speech(
        self,
        call_id: str,
        *,
        turn_id: str,
        text: str,
        terminal: SpeechTurnTerminal,
    ) -> dict[str, Any] | None:
        """Persist one exact assistant row only after normal completed playout."""
        call = self._active_call(call_id)
        if terminal.status != "normal" or not terminal.playout_completed:
            return None
        async with call.lifecycle_lock:
            if (
                call.ended_at is not None
                or call.turn_states.get(turn_id) != "running"
                or turn_id in call.completed_ai_turn_ids
                or turn_id in call.pending_ai_turn_ids
            ):
                return None
            call.pending_ai_turn_ids.add(turn_id)

        try:
            # Keep per-call message sequencing deterministic, but do not hold
            # the lifecycle lock while preparing the transaction. Hangup can
            # therefore publish its terminal state before this commit gate.
            async with call.persistence_lock:
                async with call.lifecycle_lock:
                    if call.ended_at is not None:
                        call.pending_ai_turn_ids.discard(turn_id)
                        return None

                message = await self._stage_message(
                    call.thread_id,
                    text,
                    message_kind="ai_speech",
                    role="assistant",
                    call_id=call.call_id,
                    call_turn_id=turn_id,
                )

                async with call.lifecycle_lock:
                    if call.ended_at is not None:
                        await self.session.rollback()
                        call.pending_ai_turn_ids.discard(turn_id)
                        return None
                    turn = await self.session.scalar(
                        select(CallTurn).where(
                            CallTurn.call_id == call.call_id,
                            CallTurn.turn_id == turn_id,
                        )
                    )
                    if turn is None or turn.state != "running":
                        await self.session.rollback()
                        call.pending_ai_turn_ids.discard(turn_id)
                        return None
                    turn.assistant_message_id = str(message["id"])
                    turn.state = "completed"
                    turn.updated_at = utc_now()
                    try:
                        await self.session.commit()
                    except IntegrityError:
                        await self.session.rollback()
                        existing = await self.session.scalar(
                            select(Message.id).where(
                                Message.call_id == call.call_id,
                                Message.call_turn_id == turn_id,
                            )
                        )
                        call.pending_ai_turn_ids.discard(turn_id)
                        if existing is not None:
                            call.completed_ai_turn_ids.add(turn_id)
                            return None
                        raise
                    call.pending_ai_turn_ids.discard(turn_id)
                    call.completed_ai_turn_ids.add(turn_id)
                    call.turn_states[turn_id] = "completed"
                    return message
        except asyncio.CancelledError:
            await self.session.rollback()
            async with call.lifecycle_lock:
                call.pending_ai_turn_ids.discard(turn_id)
            raise
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(
                select(Message.id).where(
                    Message.call_id == call.call_id,
                    Message.call_turn_id == turn_id,
                )
            )
            async with call.lifecycle_lock:
                call.pending_ai_turn_ids.discard(turn_id)
                if existing is not None:
                    call.completed_ai_turn_ids.add(turn_id)
                    return None
            raise
        except Exception:
            await self.session.rollback()
            async with call.lifecycle_lock:
                call.pending_ai_turn_ids.discard(turn_id)
            raise

    async def finish_call_turn(
        self,
        call_id: str,
        *,
        turn_id: str,
        state: Literal["completed", "failed", "cancelled"],
    ) -> None:
        call = self._active_call(call_id)
        async with call.persistence_lock:
            async with call.lifecycle_lock:
                current = call.turn_states.get(turn_id)
                if current not in {"reserved", "running"}:
                    return
                turn = await self.session.scalar(
                    select(CallTurn).where(
                        CallTurn.call_id == call_id,
                        CallTurn.turn_id == turn_id,
                    )
                )
                if turn is None or turn.state not in {"reserved", "running"}:
                    return
                turn.state = state
                turn.updated_at = utc_now()
                await self.session.commit()
                call.turn_states[turn_id] = state

    async def voice_reference_for_call(self, call_id: str, voice_blob_dir: Path) -> dict[str, Any]:
        call = self._active_call(call_id)
        voice = await self._required_available_voice(call.voice_id)
        preparation = await self._voice_preparation(voice, voice_blob_dir)
        if preparation.engine_id != call.engine_id:
            raise CallVoiceUnavailableError()
        if preparation.reference_payload is not None:
            voice_reference = dict(preparation.reference_payload)
        else:
            voice_reference = await self._standard_voice_reference(voice, voice_blob_dir)
        if call.engine_id == VOXCPM2_ENGINE_ID:
            try:
                voice_reference.update(_voxcpm2_call_fields(voice.metadata_json))
            except VoiceMetadataValidationError:
                logger.warning(
                    "[voice-ref] INVALID_VOXCPM2_METADATA call=%s voice_id=%s",
                    call_id,
                    voice.id,
                )
                raise CallVoiceUnavailableError() from None
        return voice_reference

    async def voice_preparation_for_call(
        self,
        call_id: str,
        voice_blob_dir: Path,
    ) -> CallVoicePreparation:
        call = self._active_call(call_id)
        voice = await self._required_available_voice(call.voice_id)
        preparation = await self._voice_preparation(voice, voice_blob_dir)
        if preparation.engine_id != call.engine_id:
            raise CallVoiceUnavailableError()
        return preparation

    async def begin_end(self, call_id: str) -> dict[str, Any]:
        """Publish terminal lifecycle state before backend or database waits."""
        call = self._active_call(call_id)
        async with call.lifecycle_lock:
            if call.ended_at is None:
                call.ended_at = utc_now()
            tasks = tuple(call.active_turn_tasks)
            for task in tasks:
                task.cancel()
        awaitable_tasks = [task for task in tasks if isinstance(task, asyncio.Future)]
        if awaitable_tasks:
            await asyncio.gather(*awaitable_tasks, return_exceptions=True)
        async with call.lifecycle_lock:
            call.active_turn_tasks.difference_update(tasks)
            active_turn_ids = {
                turn_id
                for turn_id, state in call.turn_states.items()
                if state in {"reserved", "running"}
            }
            for turn_id in active_turn_ids:
                call.turn_states[turn_id] = "cancelled"
        return call.to_public_dict()

    async def end_call(self, call_id: str, reason: str = "hangup") -> dict[str, Any]:
        call = self._active_call(call_id)
        await self.begin_end(call_id)
        async with call.persistence_lock:
            await self.session.execute(
                update(CallTurn)
                .where(
                    CallTurn.call_id == call_id,
                    CallTurn.state.in_(("reserved", "running")),
                )
                .values(state="cancelled", updated_at=utc_now())
            )
            async with call.lifecycle_lock:
                if not call.end_message_recorded:
                    await self._append_message(
                        call.thread_id,
                        "Call ended",
                        message_kind="call_end",
                        role="event",
                    )
                    call.end_message_recorded = True
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

    async def _get_character(self, character_id: str) -> Character:
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

    async def _required_available_voice(self, voice_id: str | None) -> Voice:
        if not voice_id:
            raise CallVoiceRequiredError()

        result = await self.session.execute(select(Voice).where(Voice.id == voice_id))
        voice = result.scalar_one_or_none()
        if voice is None or voice.deleted_at is not None:
            raise CallVoiceUnavailableError()
        return voice

    async def _voice_preparation(
        self,
        voice: Voice,
        voice_blob_dir: Path,
    ) -> CallVoicePreparation:
        engine_id = canonical_voice_engine_id_for_read(voice.default_engine)
        if engine_id != QWEN3_ENGINE_ID:
            return CallVoicePreparation(
                voice_id=voice.id,
                backend_voice_id=voice.id,
                engine_id=engine_id,
            )

        voice_service = VoiceService(self.session, voice_blob_dir, processor=object())
        try:
            asset = await voice_service.asset_for_voice(voice.id)
            if asset is None:
                raise VoiceAssetNotFoundError(voice.id)
            sample = await voice_service.sample_blob(asset.id)
            authorized = validate_saved_qwen3_reference(
                voice,
                asset,
                reference_bytes=sample.path.read_bytes(),
                content_type=sample.content_type,
            )
        except (OSError, VoiceAssetNotFoundError, VoiceMetadataValidationError):
            logger.warning(
                "[voice-ref] qwen_reference_rejected voice_id=%s",
                voice.id,
            )
            raise CallVoiceUnavailableError() from None
        return CallVoicePreparation(
            voice_id=voice.id,
            backend_voice_id=authorized.voice_key,
            engine_id=engine_id,
            reference_payload={
                "voice_id": authorized.voice_key,
                "reference_audio_base64": base64.b64encode(authorized.reference_bytes).decode(
                    "ascii"
                ),
                "reference_audio_content_type": authorized.content_type,
                "reference_transcript": authorized.reference_transcript,
            },
        )

    async def _standard_voice_reference(
        self,
        voice: Voice,
        voice_blob_dir: Path,
    ) -> dict[str, Any]:
        voice_service = VoiceService(self.session, voice_blob_dir, processor=object())
        asset = await voice_service.asset_for_voice(voice.id)
        if asset is None:
            raise CallVoiceUnavailableError()
        try:
            sample = await voice_service.sample_blob(asset.id)
            reference_bytes = sample.path.read_bytes()
        except (OSError, VoiceAssetNotFoundError):
            logger.warning("[voice-ref] saved_reference_unavailable voice_id=%s", voice.id)
            raise CallVoiceUnavailableError() from None
        return {
            "reference_audio_base64": base64.b64encode(reference_bytes).decode("ascii"),
            "reference_audio_content_type": asset.content_type,
            "reference_transcript": voice.reference_transcript,
        }

    async def _append_message(
        self,
        thread_id: str,
        content_text: str,
        *,
        message_kind: str,
        role: str,
        call_id: str | None = None,
        call_turn_id: str | None = None,
    ) -> dict[str, Any]:
        message = await self._stage_message(
            thread_id,
            content_text,
            message_kind=message_kind,
            role=role,
            call_id=call_id,
            call_turn_id=call_turn_id,
        )
        await self.session.commit()
        return message

    async def _stage_message(
        self,
        thread_id: str,
        content_text: str,
        *,
        message_kind: str,
        role: str,
        call_id: str | None = None,
        call_turn_id: str | None = None,
    ) -> dict[str, Any]:
        thread = await self._get_thread(thread_id)
        now = utc_now()
        message = Message(
            id=new_message_id(),
            thread_id=thread_id,
            call_id=call_id,
            call_turn_id=call_turn_id,
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
        await self.session.flush()
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


def _voxcpm2_call_fields(metadata: Any) -> dict[str, Any]:
    engine_settings = metadata.get("engine_settings") if isinstance(metadata, dict) else None
    raw_settings = (
        engine_settings.get(VOXCPM2_ENGINE_ID) if isinstance(engine_settings, dict) else None
    )
    settings = normalize_voxcpm2_engine_settings(raw_settings)
    return {
        "voxcpm2_cloning_mode": settings["cloning_mode"],
        "voxcpm2_style_prompt": settings["style_prompt"],
        "voxcpm2_cfg_value": settings["cfg_value"],
        "voxcpm2_inference_timesteps": settings["inference_timesteps"],
        "voxcpm2_normalize": settings["normalize"],
        "voxcpm2_denoise": settings["denoise"],
    }


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
