"""Same-origin Web UI call facade routes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.config import Settings
from app.domain.ai_backend_client import AiBackendClient, AiBackendClientError, AiBackendUnavailable
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

router = APIRouter(prefix="/api/calls", tags=["calls"])
DEFAULT_CALL_VOICE_BLOB_DIR = SERVER_ROOT / "data" / "blobs" / "voices"

CALL_BACKEND_NOT_READY = "call_backend_not_ready"
CALL_BACKEND_CLIENT_MISCONFIGURED = "call_backend_client_misconfigured"
CALL_ORIGIN_NOT_ALLOWED = "call_origin_not_allowed"
CALL_SESSION_NOT_FOUND_CODE = "call_session_not_found"
CALL_GENERATION_FAILED = "call_generation_failed"
RAYME_EVENTS_CHANNEL = "rayme-events"
CALL_BACKEND_NOT_READY_MESSAGE = (
    "RayMe voice backend is not ready. Check Settings, then try again."
)
_ACTIVE_LLM_TURNS: dict[str, asyncio.Task[Any]] = {}


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
    reason: str | None = Field(default=None, max_length=80)
    attempt: int | None = Field(default=None, ge=0, le=10)
    duration_ms: int | None = Field(default=None, ge=0, le=60000)
    batch_index: int | None = Field(default=None, ge=0, le=20)
    final: bool = True


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


def get_call_backend_client() -> AiBackendClient:
    return AiBackendClient()


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


@router.post("/start", status_code=status.HTTP_201_CREATED, dependencies=[Depends(enforce_same_origin_for_calls)])
async def start_call(
    payload: CallStartRequest,
    session: AsyncSession = Depends(get_call_session),
    runtime_settings: Settings = Depends(get_call_runtime_settings),
    backend: Any = Depends(get_call_backend_client),
) -> dict[str, Any]:
    endpoint_settings = await SettingsService(session, runtime_settings).read()
    await _ensure_backend_ready(backend, endpoint_settings.ai_backend_url)
    try:
        return await CallService(session).start_call(
            thread_id=payload.thread_id,
            character_id=payload.character_id,
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
) -> dict[str, Any]:
    service = CallService(session)
    try:
        stored_session_id = service.session_for_call(call_id)
        _reject_mismatched_session(stored_session_id, payload.session_id)
        call = service.attach_session(call_id, stored_session_id)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        offer_payload = {
            "session_id": stored_session_id,
            "thread_id": call["thread_id"],
            "voice_id": call["voice_id"],
            "engine_id": call["engine_id"],
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
        return {
            "call_id": call_id,
            "session_id": returned_session_id,
            "answer": response.get("answer"),
            "event_channel": RAYME_EVENTS_CHANNEL,
        }
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
        await _mute_call(backend, endpoint_settings.ai_backend_url, session_id, payload.muted)
        state = service.set_muted(call_id, payload.muted)
        return {"call_id": call_id, "session_id": session_id, "muted": state["muted"]}
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
        task = _ACTIVE_LLM_TURNS.get(call_id)
        if task is not None:
            task.cancel()
        endpoint_settings = await SettingsService(session, runtime_settings).read()
        await _interrupt_call(backend, endpoint_settings.ai_backend_url, session_id)
        service.interrupt(call_id)
        return {"call_id": call_id, "session_id": session_id, "interrupted": True}
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
        session_id = service.session_for_call(call_id)
        _reject_mismatched_session(session_id, payload.session_id)
        call = service.active_call(call_id)
        await service.record_user_speech(call_id, payload.text)
        prompt_messages = await build_call_prompt_context(
            call["thread_id"],
            repository=SqlAlchemyPromptRepository(session),
            max_turns=24,
        )
        try:
            voice_reference = await service.voice_reference_for_call(call_id, voice_blob_dir)
        except CallServiceError as exc:
            logger.warning(
                "[call-turn] voice_reference.unavailable call=%s err=%s — aborting turn",
                call_id,
                exc.message,
            )

            async def _voice_unavailable_events() -> AsyncIterator[str]:
                yield _sse(
                    {
                        "type": "error",
                        "turn_id": payload.turn_id,
                        "code": "call_tts_failed",
                        "message": "Speech playback failed: voice audio unavailable.",
                    }
                )

            return StreamingResponse(
                _voice_unavailable_events(), media_type="text/event-stream"
            )
        endpoint_settings = await SettingsService(session, runtime_settings).read()
    except CallServiceError as exc:
        raise _call_error(exc) from exc

    completion_settings = ChatCompletionSettings(
        base_url=endpoint_settings.llm_base_url,
        api_key=endpoint_settings.llm_api_key,
        model=endpoint_settings.llm_model,
        disable_thinking=endpoint_settings.llm_disable_thinking,
    )

    async def events() -> AsyncIterator[str]:
        current_task = asyncio.current_task()
        if current_task is not None:
            _ACTIVE_LLM_TURNS[call_id] = current_task
        accumulated: list[str] = []
        llm_started = time.perf_counter()
        first_token_logged = False
        try:
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
                    continue
                if event.get("type") == "error":
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
            if visible_text:
                message = await service.record_ai_speech(call_id, visible_text)
                # Block the SSE stream until TTS synthesis completes and audio
                # is enqueued to the WebRTC outbound track. This keeps the
                # browser in 'speaking' state (SSE stream active), which
                # prevents Android Chrome from suspending the tab and dropping
                # the WebRTC ICE connection during the TTS gap.
                # ai_audio_started / ai_done for the media pipeline are still
                # delivered via the WebRTC data channel independently.
                #
                # We yield SSE keepalive comments during the wait to prevent
                # FastAPI's StreamingResponse from timing out the idle HTTP
                # connection. An idle SSE connection is cancelled, which
                # propagates CancelledError to _synthesize_speech on the AI
                # backend, aborting F5-TTS mid-inference.
                tts_task = asyncio.create_task(
                    _speak_call(
                        backend,
                        endpoint_settings.ai_backend_url,
                        session_id,
                        {
                            "turn_id": payload.turn_id,
                            "text": visible_text,
                            "voice_id": call["voice_id"],
                            "engine_id": call["engine_id"],
                            "final_chunk": True,
                            **voice_reference,
                        },
                    ),
                )
                speak_result: dict[str, Any] | None = None
                while not tts_task.done():
                    await asyncio.sleep(2.0)
                    # SSE comment — keeps the HTTP connection alive without
                    # being interpreted as an event by the client
                    yield ": keepalive\n\n"
                try:
                    speak_result = await tts_task
                except AiBackendClientError as exc:
                    logger.warning(
                        "[call-turn] speak_call.sync_failed call=%s turn=%s "
                        "code=%s message=%s — yielding ai_done for UI recovery",
                        call_id,
                        payload.turn_id,
                        exc.code,
                        exc.message,
                    )
                    # TTS failed but LLM text was saved. Yield ai_done so the
                    # browser transitions from 'speaking' back to 'listening'.
                    # The user sees the AI text but no audio — they can try again.
                audio_started_event = _extract_ai_audio_started_event(speak_result)
                if audio_started_event is not None:
                    yield _sse(audio_started_event)
                logger.info(
                    "[call-turn] ai_done call=%s turn=%s visible_text_len=%d",
                    call_id,
                    payload.turn_id,
                    len(visible_text),
                )
            else:
                message = None
            yield _sse(
                {
                    "type": "ai_done",
                    "turn_id": payload.turn_id,
                    "message": message,
                }
            )
        except asyncio.CancelledError:
            return
        except AiBackendClientError:
            yield _sse(
                {
                    "type": "error",
                    "turn_id": payload.turn_id,
                    "code": "call_tts_failed",
                    "message": "Speech playback failed",
                }
            )
        except Exception:
            yield _sse(
                {
                    "type": "error",
                    "turn_id": payload.turn_id,
                    "code": CALL_GENERATION_FAILED,
                    "message": "AI generation failed",
                }
            )
        finally:
            if current_task is not None and _ACTIVE_LLM_TURNS.get(call_id) is current_task:
                _ACTIVE_LLM_TURNS.pop(call_id, None)

    return StreamingResponse(events(), media_type="text/event-stream")


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
        detail_serialized = detail_serialized[:800] + "...<truncated>"
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
            "[call-turn] speak_call.sync_failed turn=%s session=%s "
            "code=%s message=%s",
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


def _extract_ai_audio_started_event(speak_result: Mapping[str, Any] | None) -> dict[str, Any] | None:
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
