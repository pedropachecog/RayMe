"""Same-origin Web UI call facade routes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, Literal, TypedDict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.ai_backend_client import (
    AiBackendClient,
    AiBackendClientError,
    AiBackendProcessingError,
    AiBackendUnavailable,
    SpeechTurn,
)
from app.domain.call_tts_segments import CallTtsSegmenter
from app.domain.call_service import (
    CALL_SESSION_NOT_FOUND,
    CallService,
    CallServiceError,
    CallSessionNotFoundError,
)
from app.domain.llm_stream import ChatCompletionSettings, SSE_DATA_PREFIX, stream_chat_completion
from app.domain.prompt_builder import SqlAlchemyPromptRepository, build_call_prompt_context
from app.domain.settings_service import SettingsService
from app.domain.thread_service import CharacterUnavailableError, ThreadNotFoundError
from app.storage.session import SERVER_ROOT, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calls", tags=["calls"])

CALL_INTERRUPT_RECEIVER_DRAIN_MS = 250
MAX_CALL_INTERRUPT_RECEIVER_DRAIN_MS = 500


def _safe_receiver_drain_ms(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_CALL_INTERRUPT_RECEIVER_DRAIN_MS
    ):
        return CALL_INTERRUPT_RECEIVER_DRAIN_MS
    return value


DEFAULT_CALL_VOICE_BLOB_DIR = SERVER_ROOT / "data" / "blobs" / "voices"

CALL_BACKEND_NOT_READY = "call_backend_not_ready"
CALL_BACKEND_CLIENT_MISCONFIGURED = "call_backend_client_misconfigured"
CALL_ORIGIN_NOT_ALLOWED = "call_origin_not_allowed"
CALL_SESSION_NOT_FOUND_CODE = "call_session_not_found"
CALL_GENERATION_FAILED = "call_generation_failed"
RAYME_EVENTS_CHANNEL = "rayme-events"
CALL_BACKEND_NOT_READY_MESSAGE = "RayMe voice backend is not ready. Check Settings, then try again."
CALL_TURN_REJOIN_POLL_SECONDS = 0.05

CallTurnExistingState = Literal["reserved", "running", "failed", "cancelled"]


class CallTurnExistingEvent(TypedDict):
    type: Literal["turn_existing"]
    turn_id: str
    state: CallTurnExistingState
    recoverable: bool


class CallStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str | None = Field(default=None, min_length=1, max_length=128)
    character_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_thread_or_character(self) -> "CallStartRequest":
        if not self.thread_id and not self.character_id:
            raise ValueError("thread_id or character_id is required")
        return self


class SessionDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sdp: str = Field(min_length=1)
    type: Literal["offer"] = "offer"


class CallOfferRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    offer: SessionDescription | None = None
    sdp: str | None = Field(default=None, min_length=1)
    type: Literal["offer"] | None = None
    session_id: str | None = Field(default=None, min_length=1, max_length=128)

    def offer_payload(self) -> dict[str, str]:
        if self.offer is not None:
            return self.offer.model_dump()
        if self.sdp is not None:
            return {"sdp": self.sdp, "type": self.type or "offer"}
        raise ValueError("offer is required")


class MuteRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    muted: bool = False


class EndRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    reason: str = Field(default="hangup", min_length=1, max_length=80)


class CallTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20000)
    source: Literal["user_final"]


class CallReconnectAudioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    pcm_b64: str = Field(default="", max_length=4_000_000)
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    backfill_id: str | None = Field(default=None, max_length=160)
    audio_input_epoch: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=80)
    attempt: int | None = Field(default=None, ge=0, le=10)
    duration_ms: int | None = Field(default=None, ge=0, le=60000)
    batch_index: int | None = Field(default=None, ge=0, le=20)
    final: bool = True


class CallRecoverEventsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)


class CallDebugEventRequest(BaseModel):
    """Browser-side diagnostic event mirrored to the server log.

    The browser cannot be remote-inspected on Android in this environment, so
    WebRTC state changes are forwarded here purely so they appear in the OMEN
    web log. This route does not touch the database, does not call the AI
    backend, and does not change call state.
    """

    model_config = ConfigDict(extra="forbid")

    event: str = Field(min_length=1, max_length=120)
    detail: dict[str, Any] | None = Field(default=None)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)


async def get_call_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_call_runtime_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_call_backend_client(
    runtime_settings: Settings = Depends(get_call_runtime_settings),
) -> AiBackendClient:
    return AiBackendClient(
        service_auth_token=runtime_settings.ai_backend_service_token,
        ca_bundle=runtime_settings.ai_backend_ca_bundle,
    )


def get_call_voice_blob_dir() -> Path:
    return DEFAULT_CALL_VOICE_BLOB_DIR


def get_call_completion_client() -> object | None:
    return None


def get_call_service(session: AsyncSession = Depends(get_call_session)) -> CallService:
    return CallService(session)


async def enforce_same_origin_for_calls(
    request: Request,
    runtime_settings: Settings = Depends(get_call_runtime_settings),
) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return

    allowed_origins = {
        _origin_from_url(runtime_settings.web_public_url),
        *(_origin_from_url(origin) for origin in runtime_settings.allowed_origins),
        _origin_from_url(str(request.base_url)),
    }
    if _origin_from_url(origin) not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": CALL_ORIGIN_NOT_ALLOWED,
                "message": "Call controls must come from the RayMe Web UI origin.",
            },
        )


@router.post(
    "/start",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_same_origin_for_calls)],
)
async def start_call(
    payload: CallStartRequest,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
    voice_blob_dir: Path = Depends(get_call_voice_blob_dir),
) -> dict[str, Any]:
    endpoint_settings = await SettingsService(session, runtime_settings).read()
    service = CallService(session)
    try:
        preflight = await service.preflight_call_voice(
            thread_id=payload.thread_id,
            character_id=payload.character_id,
            voice_blob_dir=voice_blob_dir,
        )
        await _ensure_backend_ready(backend, endpoint_settings.ai_backend_url)
        return await service.start_call(
            thread_id=payload.thread_id,
            character_id=payload.character_id,
            preflight=preflight,
        )
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except (ThreadNotFoundError, CharacterUnavailableError) as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc


@router.post("/{call_id}/offer", dependencies=[Depends(enforce_same_origin_for_calls)])
async def create_call_offer(
    call_id: str,
    payload: CallOfferRequest,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
    voice_blob_dir: Path = Depends(get_call_voice_blob_dir),
) -> dict[str, Any]:
    service = CallService(session)
    try:
        stored_session_id = service.session_for_call(call_id)
        _reject_mismatched_session(stored_session_id, payload.session_id)
        call = service.attach_session(call_id, stored_session_id)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        voice_preparation = await service.voice_preparation_for_call(
            call_id,
            voice_blob_dir,
        )
        offer_payload = {
            "session_id": stored_session_id,
            "thread_id": call["thread_id"],
            "voice_id": voice_preparation.backend_voice_id,
            "engine_id": voice_preparation.engine_id,
            "prompt_messages": await build_call_prompt_context(
                call["thread_id"],
                repository=SqlAlchemyPromptRepository(session),
                max_turns=24,
            ),
            "offer": payload.offer_payload(),
        }
        response = await _create_offer(backend, endpoint_settings.ai_backend_url, offer_payload)
        returned_session_id = str(response.get("session_id") or stored_session_id)
        service.attach_session(call_id, returned_session_id)
        result = {
            "call_id": call_id,
            "session_id": returned_session_id,
            "answer": response.get("answer"),
            "event_channel": RAYME_EVENTS_CHANNEL,
        }
        if voice_preparation.reference_payload is not None:
            result["preparation"] = await _prepare_call_voice(
                backend,
                endpoint_settings.ai_backend_url,
                returned_session_id,
                engine_id=voice_preparation.engine_id,
                voice_id=voice_preparation.backend_voice_id,
                reference_payload=voice_preparation.reference_payload,
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except AiBackendClientError as exc:
        raise _backend_error(exc) from exc


@router.post("/{call_id}/mute", dependencies=[Depends(enforce_same_origin_for_calls)])
async def mute_call(
    call_id: str,
    payload: MuteRequest,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
) -> dict[str, Any]:
    service = CallService(session)
    try:
        session_id = service.session_for_call(call_id)
        _reject_mismatched_session(session_id, payload.session_id)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        backend_state = await _mute_call(
            backend,
            endpoint_settings.ai_backend_url,
            session_id,
            payload.muted,
        )
        backend_muted = backend_state.get("muted")
        audio_input_epoch = backend_state.get("audio_input_epoch")
        if (
            not isinstance(backend_muted, bool)
            or isinstance(audio_input_epoch, bool)
            or not isinstance(audio_input_epoch, int)
            or audio_input_epoch < 0
        ):
            raise AiBackendProcessingError(
                code="call_control_failed",
                message="Call control request failed",
            )
        state = service.set_muted(call_id, backend_muted)
        return {
            "call_id": call_id,
            "session_id": session_id,
            "muted": state["muted"],
            "audio_input_epoch": audio_input_epoch,
        }
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except AiBackendClientError as exc:
        raise _backend_error(exc) from exc


@router.post("/{call_id}/interrupt", dependencies=[Depends(enforce_same_origin_for_calls)])
async def interrupt_call(
    call_id: str,
    payload: EndRequest | None = None,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
) -> dict[str, Any]:
    service = CallService(session)
    try:
        session_id = service.session_for_call(call_id)
        _reject_mismatched_session(session_id, payload.session_id if payload else None)
        await service.cancel_active_turns(call_id)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        interrupt_result = await _interrupt_call(
            backend,
            endpoint_settings.ai_backend_url,
            session_id,
        )
        service.interrupt(call_id)
        return {
            "call_id": call_id,
            "session_id": session_id,
            "interrupted": True,
            "cancelled_turn_id": interrupt_result.get("cancelled_turn_id"),
            "receiver_drain_ms": _safe_receiver_drain_ms(
                interrupt_result.get("receiver_drain_ms")
            ),
        }
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except AiBackendClientError as exc:
        raise _backend_error(exc) from exc


@router.post("/{call_id}/turns", dependencies=[Depends(enforce_same_origin_for_calls)])
async def create_call_turn(
    call_id: str,
    payload: CallTurnRequest,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
    completion_client: object | None = Depends(get_call_completion_client),
    voice_blob_dir: Path = Depends(get_call_voice_blob_dir),
) -> StreamingResponse:
    service = CallService(session)
    try:
        stored_session_id = service.session_for_call(call_id)
        _reject_mismatched_session(stored_session_id, payload.session_id)
    except CallServiceError as exc:
        raise _call_error(exc) from exc

    async def events() -> AsyncIterator[str]:
        current_task = asyncio.current_task()
        reservation_created = False
        reservation_owner_token: str | None = None
        terminal_state: Literal["completed", "failed", "cancelled"] = "failed"
        accumulated: list[str] = []
        speech_turn: SpeechTurn | None = None
        rehearsing_sent = False
        first_token_logged = False
        try:
            session_id = stored_session_id
            reservation = await service.reserve_call_turn(
                call_id,
                turn_id=payload.turn_id,
                text=payload.text,
                task=current_task,
            )
            if not reservation.created:
                if reservation.request_matches:
                    request_sha256 = service.call_turn_request_sha256(payload.text)
                    snapshot = reservation
                    emitted_state: str | None = None
                    while snapshot.state in {"reserved", "running"}:
                        if snapshot.state != emitted_state:
                            yield _sse(
                                _turn_existing_event(
                                    payload.turn_id,
                                    snapshot.state,
                                    recoverable=False,
                                )
                            )
                            emitted_state = snapshot.state
                        await asyncio.sleep(CALL_TURN_REJOIN_POLL_SECONDS)
                        snapshot = await service.call_turn_status(
                            call_id,
                            turn_id=payload.turn_id,
                            request_sha256=request_sha256,
                        )
                    if snapshot.state == "completed":
                        yield _sse(
                            {
                                "type": "ai_done",
                                "turn_id": payload.turn_id,
                                "message": snapshot.assistant_message,
                                "existing": True,
                            }
                        )
                    else:
                        yield _sse(
                            _turn_existing_event(
                                payload.turn_id,
                                snapshot.state,
                                recoverable=True,
                            )
                        )
                else:
                    yield _sse(
                        {
                            "type": "error",
                            "turn_id": payload.turn_id,
                            "code": "call_turn_conflict",
                            "message": "Turn identifier is already in use",
                        }
                    )
                return
            reservation_created = True
            reservation_owner_token = reservation.owner_token
            if reservation_owner_token is None:
                raise RuntimeError("created call turn reservation has no owner")
            call = service.active_call(call_id)
            user_message = await service.record_reserved_user_speech(
                call_id,
                turn_id=payload.turn_id,
                text=payload.text,
                owner_token=reservation_owner_token,
            )
            if user_message is None:
                terminal_state = "cancelled"
                yield _sse(
                    {
                        "type": "error",
                        "turn_id": payload.turn_id,
                        "code": CALL_SESSION_NOT_FOUND_CODE,
                        "message": "Call session was not found",
                    }
                )
                return
            prompt_messages = await build_call_prompt_context(
                call["thread_id"],
                repository=SqlAlchemyPromptRepository(session),
                max_turns=24,
            )
            try:
                voice_reference = await service.voice_reference_for_call(
                    call_id,
                    voice_blob_dir,
                )
            except CallServiceError as exc:
                logger.warning(
                    "[call-turn] voice_reference.unavailable call=%s err=%s",
                    call_id,
                    exc.message,
                )
                yield _sse(
                    {
                        "type": "error",
                        "turn_id": payload.turn_id,
                        "code": "call_tts_failed",
                        "message": "Speech playback failed: voice audio unavailable.",
                    }
                )
                return
            endpoint_settings = await SettingsService(session, runtime_settings).read()
            completion_settings = ChatCompletionSettings(
                base_url=endpoint_settings.llm_base_url,
                api_key=endpoint_settings.llm_api_key,
                model=endpoint_settings.llm_model,
                disable_thinking=endpoint_settings.llm_disable_thinking,
            )
            segmenter = (
                CallTtsSegmenter() if call["engine_id"] == "qwen3_1_7b" else None
            )
            llm_started = time.perf_counter()
            async for raw_event in stream_chat_completion(
                completion_settings,
                prompt_messages,
                client=completion_client,
            ):
                event = _decode_sse_event(raw_event)
                if event.get("type") == "token":
                    token = str(event.get("text") or "")
                    if not token:
                        continue
                    if not first_token_logged:
                        first_token_logged = True
                        logger.info(
                            "[call-turn] llm.first_token call=%s turn=%s elapsed_ms=%d disable_thinking=%s model=%s",
                            call_id,
                            payload.turn_id,
                            int((time.perf_counter() - llm_started) * 1000),
                            completion_settings.disable_thinking,
                            completion_settings.model,
                        )
                    accumulated.append(token)
                    yield _sse({"type": "ai_token", "turn_id": payload.turn_id, "text": token})
                    if segmenter is not None:
                        for segment in segmenter.feed(token):
                            if speech_turn is None:
                                speech_turn = SpeechTurn(
                                    backend=backend,
                                    base_url=endpoint_settings.ai_backend_url,
                                    session_id=session_id,
                                    turn_id=payload.turn_id,
                                    voice_id=str(call["voice_id"]),
                                    engine_id=str(call["engine_id"]),
                                    voice_reference=voice_reference,
                                )
                            if not rehearsing_sent:
                                rehearsing_sent = True
                                yield _sse(
                                    {
                                        "type": "state",
                                        "turn_id": payload.turn_id,
                                        "state": "rehearsing",
                                    }
                                )
                            await speech_turn.submit(segment)
                    continue
                if event.get("type") == "error":
                    if speech_turn is not None:
                        await speech_turn.cancel()
                    yield _sse(
                        {
                            "type": "error",
                            "turn_id": payload.turn_id,
                            "code": CALL_GENERATION_FAILED,
                            "message": "AI generation failed",
                        }
                    )
                    return

            visible_text = "".join(accumulated)
            logger.info(
                "[call-turn] llm.done call=%s turn=%s elapsed_ms=%d chars=%d",
                call_id,
                payload.turn_id,
                int((time.perf_counter() - llm_started) * 1000),
                len(visible_text),
            )
            if not visible_text.strip():
                terminal_state = "completed"
                yield _sse(
                    {
                        "type": "ai_done",
                        "turn_id": payload.turn_id,
                        "message": None,
                    }
                )
                return

            if speech_turn is None:
                speech_turn = SpeechTurn(
                    backend=backend,
                    base_url=endpoint_settings.ai_backend_url,
                    session_id=session_id,
                    turn_id=payload.turn_id,
                    voice_id=str(call["voice_id"]),
                    engine_id=str(call["engine_id"]),
                    voice_reference=voice_reference,
                )
            if not rehearsing_sent:
                rehearsing_sent = True
                yield _sse(
                    {
                        "type": "state",
                        "turn_id": payload.turn_id,
                        "state": "rehearsing",
                    }
                )

            final_text = segmenter.finish() if segmenter is not None else visible_text
            terminal_task = asyncio.create_task(speech_turn.finalize(final_text))
            while not terminal_task.done():
                await asyncio.sleep(2.0)
                yield ": keepalive\n\n"
            terminal = await terminal_task
            audio_started_event = _extract_ai_audio_started_event(terminal.response)
            if audio_started_event is not None:
                yield _sse(audio_started_event)
            if terminal.status == "cancelled":
                terminal_state = "cancelled"
                return
            if terminal.status != "normal" or not terminal.playout_completed:
                logger.warning(
                    "[call-turn] speech_turn.failed call=%s turn=%s code=%s",
                    call_id,
                    payload.turn_id,
                    terminal.error_code or "call_tts_failed",
                )
                yield _sse(
                    {
                        "type": "error",
                        "turn_id": payload.turn_id,
                        "code": "call_tts_failed",
                        "message": "Speech playback failed",
                    }
                )
                return
            message = await service.record_completed_ai_speech(
                call_id,
                turn_id=payload.turn_id,
                text=visible_text,
                terminal=terminal,
                owner_token=reservation_owner_token,
            )
            if message is None:
                terminal_state = "cancelled"
                return
            terminal_state = "completed"
            logger.info(
                "[call-turn] ai_done call=%s turn=%s visible_text_len=%d",
                call_id,
                payload.turn_id,
                len(visible_text),
            )
            yield _sse(
                {
                    "type": "ai_done",
                    "turn_id": payload.turn_id,
                    "message": message,
                }
            )
        except asyncio.CancelledError:
            terminal_state = "cancelled"
            if speech_turn is not None:
                await speech_turn.cancel()
            return
        except CallServiceError as exc:
            terminal_state = "cancelled"
            yield _sse(
                {
                    "type": "error",
                    "turn_id": payload.turn_id,
                    "code": exc.code,
                    "message": exc.message,
                }
            )
        except AiBackendClientError:
            if speech_turn is not None:
                await speech_turn.cancel()
            yield _sse(
                {
                    "type": "error",
                    "turn_id": payload.turn_id,
                    "code": "call_tts_failed",
                    "message": "Speech playback failed",
                }
            )
        except Exception:
            if speech_turn is not None:
                await speech_turn.cancel()
            yield _sse(
                {
                    "type": "error",
                    "turn_id": payload.turn_id,
                    "code": CALL_GENERATION_FAILED,
                    "message": "AI generation failed",
                }
            )
        finally:
            if speech_turn is not None and speech_turn.terminal is None:
                await speech_turn.cancel()
            if reservation_created and terminal_state != "completed":
                await service.finish_call_turn(
                    call_id,
                    turn_id=payload.turn_id,
                    state=terminal_state,
                    owner_token=reservation_owner_token,
                )
            elif reservation_created:
                await service.finish_call_turn(
                    call_id,
                    turn_id=payload.turn_id,
                    state="completed",
                    owner_token=reservation_owner_token,
                )
            if reservation_created and current_task is not None:
                await service.unregister_active_turn(
                    call_id,
                    current_task,
                    turn_id=payload.turn_id,
                    owner_token=reservation_owner_token,
                )

    return StreamingResponse(events(), media_type="text/event-stream")


def _turn_existing_event(
    turn_id: str,
    state: str,
    *,
    recoverable: bool,
) -> CallTurnExistingEvent:
    if state not in {"reserved", "running", "failed", "cancelled"}:
        raise ValueError(f"unsupported duplicate call turn state: {state}")
    return {
        "type": "turn_existing",
        "turn_id": turn_id,
        "state": state,
        "recoverable": recoverable,
    }


@router.post("/{call_id}/reconnect-audio", dependencies=[Depends(enforce_same_origin_for_calls)])
async def backfill_call_reconnect_audio(
    call_id: str,
    payload: CallReconnectAudioRequest,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
) -> dict[str, Any]:
    service = CallService(session)
    try:
        session_id = service.session_for_call(call_id)
        _reject_mismatched_session(session_id, payload.session_id)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        result = await _backfill_call_audio(
            backend,
            endpoint_settings.ai_backend_url,
            session_id,
            {
                "pcm_b64": payload.pcm_b64,
                "sample_rate": payload.sample_rate,
                "channels": payload.channels,
                "backfill_id": payload.backfill_id,
                "audio_input_epoch": payload.audio_input_epoch,
                "reason": payload.reason,
                "attempt": payload.attempt,
                "duration_ms": payload.duration_ms,
                "batch_index": payload.batch_index,
                "final": payload.final,
            },
        )
        return {"call_id": call_id, "session_id": session_id, **result}
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except AiBackendClientError as exc:
        raise _backend_error(exc) from exc


@router.post("/{call_id}/events/recover", dependencies=[Depends(enforce_same_origin_for_calls)])
async def recover_call_events(
    call_id: str,
    payload: CallRecoverEventsRequest,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
) -> dict[str, Any]:
    service = CallService(session)
    try:
        session_id = service.session_for_call(call_id)
        _reject_mismatched_session(session_id, payload.session_id)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        result = await _drain_call_events(
            backend,
            endpoint_settings.ai_backend_url,
            session_id,
        )
        events = result.get("events")
        return {
            "call_id": call_id,
            "session_id": session_id,
            "events": events if isinstance(events, list) else [],
        }
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except AiBackendClientError as exc:
        raise _backend_error(exc) from exc


@router.post("/{call_id}/end", dependencies=[Depends(enforce_same_origin_for_calls)])
async def end_call(
    call_id: str,
    payload: EndRequest | None = None,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
) -> dict[str, Any]:
    service = CallService(session)
    reason = payload.reason if payload else "hangup"
    try:
        session_id = service.session_for_call(call_id)
        _reject_mismatched_session(session_id, payload.session_id if payload else None)
        await service.begin_end(call_id)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        try:
            await _end_call(backend, endpoint_settings.ai_backend_url, session_id, reason)
        except AiBackendClientError as exc:
            if exc.code == CALL_BACKEND_CLIENT_MISCONFIGURED:
                raise
        ended = await service.end_call(call_id, reason=reason)
        return {"call_id": call_id, "session_id": session_id, "reason": ended["reason"]}
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except AiBackendClientError as exc:
        raise _backend_error(exc) from exc


@router.post(
    "/{call_id}/_debug/event",
    dependencies=[Depends(enforce_same_origin_for_calls)],
)
async def record_call_debug_event(
    call_id: str,
    payload: CallDebugEventRequest,
) -> dict[str, str]:
    """Mirror browser WebRTC lifecycle events to the OMEN web log.

    Behavior-neutral: no DB write, no backend forwarding, no call state change.
    Sole purpose is observability for Android browsers without remote devtools.
    """

    detail_serialized = ""
    if payload.detail is not None:
        try:
            detail_serialized = json.dumps(payload.detail, separators=(",", ":"))
        except (TypeError, ValueError):
            detail_serialized = "<unserializable>"
    if len(detail_serialized) > 800:
        truncation_marker = "...<truncated>"
        detail_serialized = detail_serialized[: 800 - len(truncation_marker)] + truncation_marker
    logger.info(
        "[browser-call] event=%s call=%s session=%s detail=%s",
        payload.event,
        call_id,
        payload.session_id or "",
        detail_serialized,
    )
    return {"status": "ok"}


async def _ensure_backend_ready(backend: Any, base_url: str) -> None:
    if hasattr(backend, "readiness"):
        status_payload = await backend.readiness()
    else:
        status_payload = await backend.get_webrtc_status(base_url)

    if _backend_status_ready(status_payload):
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": CALL_BACKEND_NOT_READY,
            "message": CALL_BACKEND_NOT_READY_MESSAGE,
        },
    )


def _backend_status_ready(payload: Mapping[str, Any]) -> bool:
    if payload.get("ready") is True:
        return True
    if payload.get("live_call_ready") is True and payload.get("media_transport_ready") is True:
        return str(payload.get("status")) in {"ready", "ok", "degraded"}
    return False


async def _create_offer(backend: Any, base_url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not hasattr(backend, "create_webrtc_offer"):
        raise _missing_backend_method("create_webrtc_offer")
    return dict(await backend.create_webrtc_offer(base_url, payload))


async def _prepare_call_voice(
    backend: Any,
    base_url: str,
    session_id: str,
    *,
    engine_id: str,
    voice_id: str,
    reference_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not hasattr(backend, "prepare_call_speech"):
        raise _missing_backend_method("prepare_call_speech")
    preparation = dict(
        await backend.prepare_call_speech(
            base_url,
            session_id,
            {
                "voice_id": voice_id,
                "engine_id": engine_id,
                "reference_audio_base64": reference_payload["reference_audio_base64"],
                "reference_audio_content_type": reference_payload.get(
                    "reference_audio_content_type"
                ),
                "reference_transcript": reference_payload["reference_transcript"],
            },
        )
    )
    readiness = _call_preparation_readiness(
        preparation,
        engine_id=engine_id,
        voice_id=voice_id,
    )
    if readiness["prompt"]["state"] == "ready":
        return readiness
    _raise_failed_call_preparation(readiness)

    if not hasattr(backend, "get_tts_preparation_status"):
        raise _missing_backend_method("get_tts_preparation_status")
    for _ in range(20):
        status_payload = dict(await backend.get_tts_preparation_status(base_url))
        readiness = _call_preparation_readiness(
            status_payload,
            engine_id=engine_id,
            voice_id=voice_id,
        )
        if readiness["prompt"]["state"] == "ready":
            return readiness
        _raise_failed_call_preparation(readiness)
        await asyncio.sleep(0.05)
    raise AiBackendProcessingError(
        code="call_tts_prepare_failed",
        message="Voice preparation failed",
    )


def _call_preparation_readiness(
    payload: Mapping[str, Any],
    *,
    engine_id: str,
    voice_id: str,
) -> dict[str, Any]:
    raw_model = payload.get("model")
    raw_prompt = payload.get("prompt")
    model = raw_model if isinstance(raw_model, Mapping) else {}
    prompt = raw_prompt if isinstance(raw_prompt, Mapping) else {}
    model_state = model.get("state", payload.get("model_state"))
    model_engine = model.get("engine_id", payload.get("engine_id"))
    if model_state == "ready":
        model_state = "resident"
    if model_state not in {"idle", "loading", "resident", "failed"}:
        model_state = "idle"
    if model_engine != engine_id:
        model_engine = None

    prompt_state = prompt.get("state", payload.get("prompt_state"))
    prompt_voice_key = prompt.get("voice_key", payload.get("voice_key"))
    error_code = prompt.get("error_code", payload.get("error_code"))
    if prompt_state not in {"none", "prewarming", "ready", "failed"}:
        prompt_state = "none"
    if prompt_voice_key != voice_id:
        prompt_state = "failed"
        prompt_voice_key = None
        error_code = "call_tts_prepare_mismatch"
    if not isinstance(error_code, str) or error_code not in {
        "qwen3_alignment_failed",
        "qwen3_prompt_failed",
        "qwen3_prompt_not_ready",
        "qwen3_transcript_mismatch",
        "qwen3_worker_protocol",
        "qwen3_worker_timeout",
        "qwen3_worker_stopped",
        "call_tts_prepare_mismatch",
        "call_tts_prepare_unavailable",
        "call_tts_prepare_failed",
    }:
        error_code = None
    return {
        "model": {"state": model_state, "engine_id": model_engine},
        "prompt": {
            "state": prompt_state,
            "voice_key": prompt_voice_key,
            "error_code": error_code,
        },
    }


def _raise_failed_call_preparation(readiness: Mapping[str, Any]) -> None:
    prompt = readiness.get("prompt")
    if not isinstance(prompt, Mapping) or prompt.get("state") != "failed":
        return
    code = prompt.get("error_code")
    if not isinstance(code, str) or not code:
        code = "call_tts_prepare_failed"
    raise AiBackendProcessingError(code=code, message="Voice preparation failed")


async def _mute_call(backend: Any, base_url: str, session_id: str, muted: bool) -> dict[str, Any]:
    if not hasattr(backend, "mute_call"):
        raise _missing_backend_method("mute_call")
    return dict(await backend.mute_call(base_url, session_id, muted))


async def _interrupt_call(backend: Any, base_url: str, session_id: str) -> dict[str, Any]:
    if not hasattr(backend, "interrupt_call"):
        raise _missing_backend_method("interrupt_call")
    return dict(await backend.interrupt_call(base_url, session_id))


async def _end_call(backend: Any, base_url: str, session_id: str, reason: str) -> dict[str, Any]:
    if not hasattr(backend, "end_call"):
        raise _missing_backend_method("end_call")
    return dict(await backend.end_call(base_url, session_id, reason))


async def _speak_call(
    backend: Any,
    base_url: str,
    session_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not hasattr(backend, "speak_call"):
        raise _missing_backend_method("speak_call")
    return dict(await backend.speak_call(base_url, session_id, payload))


async def _backfill_call_audio(
    backend: Any,
    base_url: str,
    session_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not hasattr(backend, "backfill_call_audio"):
        raise _missing_backend_method("backfill_call_audio")
    return dict(await backend.backfill_call_audio(base_url, session_id, payload))


async def _drain_call_events(backend: Any, base_url: str, session_id: str) -> dict[str, Any]:
    if not hasattr(backend, "drain_call_events"):
        raise _missing_backend_method("drain_call_events")
    return dict(await backend.drain_call_events(base_url, session_id))


async def _speak_call_sync(
    backend: Any,
    base_url: str,
    session_id: str,
    turn_id: str,
    text: str,
    voice_id: str,
    engine_id: str,
    voice_reference: dict[str, Any],
) -> bool:
    """Synchronous TTS call within the SSE generator.

    Blocks the SSE stream until TTS synthesis completes and audio is enqueued
    to the WebRTC outbound track. This keeps the browser in 'speaking' state,
    preventing Android Chrome from dropping the WebRTC ICE connection during
    the TTS gap. Returns True if TTS succeeded.
    """
    try:
        await _speak_call(
            backend,
            base_url,
            session_id,
            {
                "turn_id": turn_id,
                "text": text,
                "voice_id": voice_id,
                "engine_id": engine_id,
                "final_chunk": True,
                **voice_reference,
            },
        )
        return True
    except AiBackendClientError as exc:
        logger.warning(
            "[call-turn] speak_call.sync_failed turn=%s session=%s code=%s message=%s",
            turn_id,
            session_id,
            exc.code,
            exc.message,
        )
        return False
    except Exception:
        logger.exception(
            "[call-turn] speak_call.sync_exception turn=%s session=%s",
            turn_id,
            session_id,
        )
        return False


def _missing_backend_method(method_name: str) -> AiBackendUnavailable:
    return AiBackendUnavailable(
        code=CALL_BACKEND_CLIENT_MISCONFIGURED,
        message=f"AI backend client is missing required call method: {method_name}",
    )


def _reject_mismatched_session(stored_session_id: str, provided_session_id: str | None) -> None:
    if provided_session_id is not None and provided_session_id != stored_session_id:
        raise CallSessionNotFoundError()


def _call_error(exc: CallServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.to_public_dict())


def _backend_error(exc: AiBackendClientError) -> HTTPException:
    return HTTPException(status_code=502, detail=exc.to_public_dict())


def _origin_from_url(value: str) -> str:
    stripped = value.strip().rstrip("/")
    if "://" not in stripped:
        return stripped
    scheme, rest = stripped.split("://", 1)
    authority = rest.split("/", 1)[0]
    return f"{scheme.lower()}://{authority.lower()}"


def _sse(event: Mapping[str, Any]) -> str:
    return f"{SSE_DATA_PREFIX}{json.dumps(dict(event), separators=(',', ':'))}\n\n"


def _decode_sse_event(raw_event: str) -> dict[str, Any]:
    for line in raw_event.splitlines():
        if not line.startswith(SSE_DATA_PREFIX):
            continue
        try:
            payload = json.loads(line[len(SSE_DATA_PREFIX) :])
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _extract_ai_audio_started_event(
    speak_result: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if speak_result is None:
        return None
    event = speak_result.get("event")
    candidates = [
        speak_result.get("ai_audio_started_event"),
        event.get("ai_audio_started_event") if isinstance(event, Mapping) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping) and candidate.get("type") == "ai_audio_started":
            return dict(candidate)
    return None


__all__ = [
    "CALL_BACKEND_NOT_READY",
    "CALL_GENERATION_FAILED",
    "CALL_ORIGIN_NOT_ALLOWED",
    "CALL_SESSION_NOT_FOUND_CODE",
    "CALL_SESSION_NOT_FOUND",
    "RAYME_EVENTS_CHANNEL",
    "get_call_backend_client",
    "get_call_completion_client",
    "get_call_session",
    "get_call_voice_blob_dir",
    "router",
]
