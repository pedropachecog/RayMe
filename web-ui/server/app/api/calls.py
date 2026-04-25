"""Same-origin Web UI call facade routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.ai_backend_client import AiBackendClient, AiBackendClientError
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
        voice_reference = await service.voice_reference_for_call(call_id, voice_blob_dir)
        endpoint_settings = await SettingsService(session, runtime_settings).read()
    except CallServiceError as exc:
        raise _call_error(exc) from exc

    completion_settings = ChatCompletionSettings(
        base_url=endpoint_settings.llm_base_url,
        api_key=endpoint_settings.llm_api_key,
        model=endpoint_settings.llm_model,
    )

    async def events() -> AsyncIterator[str]:
        current_task = asyncio.current_task()
        if current_task is not None:
            _ACTIVE_LLM_TURNS[call_id] = current_task
        accumulated: list[str] = []
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
            if visible_text:
                await _speak_call(
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
                )
            message = await service.record_ai_speech(call_id, visible_text)
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
        await _end_call(backend, endpoint_settings.ai_backend_url, session_id, reason)
        ended = await service.end_call(call_id, reason=reason)
        return {"call_id": call_id, "session_id": session_id, "reason": ended["reason"]}
    except CallServiceError as exc:
        raise _call_error(exc) from exc
    except AiBackendClientError as exc:
        raise _backend_error(exc) from exc


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
        return {"session_id": payload["session_id"], "answer": None}
    return dict(await backend.create_webrtc_offer(base_url, payload))


async def _mute_call(backend: Any, base_url: str, session_id: str, muted: bool) -> dict[str, Any]:
    if not hasattr(backend, "mute_call"):
        return {"session_id": session_id, "muted": muted}
    return dict(await backend.mute_call(base_url, session_id, muted))


async def _interrupt_call(backend: Any, base_url: str, session_id: str) -> dict[str, Any]:
    if not hasattr(backend, "interrupt_call"):
        return {"session_id": session_id, "interrupted": True}
    return dict(await backend.interrupt_call(base_url, session_id))


async def _end_call(backend: Any, base_url: str, session_id: str, reason: str) -> dict[str, Any]:
    if not hasattr(backend, "end_call"):
        return {"session_id": session_id, "reason": reason}
    return dict(await backend.end_call(base_url, session_id, reason))


async def _speak_call(
    backend: Any,
    base_url: str,
    session_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not hasattr(backend, "speak_call"):
        return {"session_id": session_id, "event": {"type": "ai_done"}}
    return dict(await backend.speak_call(base_url, session_id, payload))


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
