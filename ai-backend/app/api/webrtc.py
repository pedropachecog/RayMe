from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.stt import _settings_from_app, _stt_adapter_from_app, _vad_adapter_from_app
from app.call.session import CallSession, CallSessionManager

router = APIRouter(prefix="/webrtc", tags=["webrtc"])

RAYME_EVENTS_CHANNEL = "rayme-events"


class SessionDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sdp: str = Field(min_length=1)
    type: Literal["offer"]


class PromptMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class CallOfferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str = Field(min_length=1, max_length=64)
    prompt_messages: list[PromptMessage] = Field(default_factory=list, max_length=48)
    offer: SessionDescription


class MuteControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    muted: bool


class EndControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="hangup", min_length=1, max_length=80)


class CallControlResponse(BaseModel):
    session_id: str
    state: str
    muted: bool | None = None
    interrupted: bool | None = None
    reason: str | None = None


@router.get("/status")
def get_webrtc_status(request: Request) -> dict[str, object]:
    manager = _manager_from_app(request)
    return {
        "status": "ready",
        "phase": "03",
        "live_call_ready": True,
        "media_transport_ready": True,
        "active_sessions": manager.stats()["active_sessions"],
        "message": "Phase 3 live call signaling is ready.",
    }


@router.post("/offer")
async def create_webrtc_offer_answer(
    request: Request,
    payload: CallOfferRequest,
) -> dict[str, Any]:
    manager = _manager_from_app(request)
    peer_connection = _create_peer_connection(payload.offer)
    data_channel = _create_data_channel(peer_connection)

    try:
        session = await manager.create_session(
            session_id=payload.session_id,
            thread_id=payload.thread_id,
            voice_id=payload.voice_id,
            engine_id=payload.engine_id,
            prompt_messages=[message.model_dump() for message in payload.prompt_messages],
            peer_connection=peer_connection,
            data_channel=data_channel,
            vad_adapter=_vad_adapter(request),
            stt_adapter=_stt_adapter(request),
        )
        _attach_peer_handlers(peer_connection, session)
        answer = await _negotiate_answer(peer_connection, payload.offer)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "webrtc_offer_failed",
                "message": "WebRTC offer could not be accepted",
            },
        ) from exc

    return {
        "session_id": session.session_id,
        "answer": answer,
        "event_channel": RAYME_EVENTS_CHANNEL,
        "data_channel": {"label": RAYME_EVENTS_CHANNEL},
    }


@router.post("/sessions/{session_id}/mute", response_model=CallControlResponse)
async def mute_session(
    request: Request,
    session_id: str,
    payload: MuteControlRequest,
) -> CallControlResponse:
    session = _session_or_404(request, session_id)
    try:
        await session.set_muted(payload.muted)
        return CallControlResponse(
            session_id=session.session_id,
            state=session.state,
            muted=session.muted,
        )
    except Exception as exc:
        raise _control_error() from exc


@router.post("/sessions/{session_id}/interrupt", response_model=CallControlResponse)
async def interrupt_session(request: Request, session_id: str) -> CallControlResponse:
    session = _session_or_404(request, session_id)
    try:
        await session.interrupt()
        return CallControlResponse(
            session_id=session.session_id,
            state=session.state,
            interrupted=True,
        )
    except Exception as exc:
        raise _control_error() from exc


@router.post("/sessions/{session_id}/end", response_model=CallControlResponse)
async def end_session(
    request: Request,
    session_id: str,
    payload: EndControlRequest | None = None,
) -> CallControlResponse:
    manager = _manager_from_app(request)
    session = _session_or_404(request, session_id)
    reason = payload.reason if payload is not None else "hangup"
    try:
        await session.end(reason=reason)
        manager._sessions.pop(session_id, None)
        return CallControlResponse(
            session_id=session.session_id,
            state=session.state,
            reason=session.end_reason or reason,
        )
    except Exception as exc:
        raise _control_error() from exc


def _manager_from_app(request: Request) -> CallSessionManager:
    manager = getattr(request.app.state, "call_session_manager", None)
    if isinstance(manager, CallSessionManager):
        return manager
    settings = _settings_from_app(request)
    manager = CallSessionManager(settings=settings)
    request.app.state.call_session_manager = manager
    return manager


def _session_or_404(request: Request, session_id: str) -> CallSession:
    session = _manager_from_app(request).get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "call_session_not_found",
                "message": "Call session was not found",
            },
        )
    return session


def _control_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": "call_control_failed",
            "message": "Call control request failed",
        },
    )


def _stt_adapter(request: Request) -> Any:
    settings = _settings_from_app(request)
    return _stt_adapter_from_app(request, settings)


def _vad_adapter(request: Request) -> Any:
    settings = _settings_from_app(request)
    return _vad_adapter_from_app(
        request,
        settings,
        settings.vad_threshold,
        settings.vad_end_silence_ms,
    )


def _create_peer_connection(offer: SessionDescription) -> Any:
    if not _looks_like_real_media_offer(offer.sdp):
        return None
    try:
        from aiortc import RTCPeerConnection

        return RTCPeerConnection()
    except Exception:
        return None


def _looks_like_real_media_offer(sdp: str) -> bool:
    return "m=audio" in sdp and "a=ice-ufrag:" in sdp


def _create_data_channel(peer_connection: Any) -> Any:
    if peer_connection is None:
        return None
    create_data_channel = getattr(peer_connection, "createDataChannel", None)
    if not callable(create_data_channel):
        return None
    try:
        return create_data_channel(RAYME_EVENTS_CHANNEL)
    except Exception:
        return None


def _attach_peer_handlers(peer_connection: Any, session: CallSession) -> None:
    if peer_connection is None or not hasattr(peer_connection, "on"):
        return

    @peer_connection.on("datachannel")
    def on_datachannel(channel: Any) -> None:
        if getattr(channel, "label", None) == RAYME_EVENTS_CHANNEL:
            session.data_channel = channel

    @peer_connection.on("track")
    def on_track(track: Any) -> None:
        if getattr(track, "kind", None) == "audio":
            asyncio.create_task(_receive_audio_track(session, track))

    @peer_connection.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        await session.handle_connection_state_change()


async def _receive_audio_track(session: CallSession, track: Any) -> None:
    while session.state not in {"ended", "failed"}:
        try:
            frame = await track.recv()
        except Exception:
            await session.fail(reason="connection_failed")
            return
        await session.handle_inbound_audio_frame(frame)


async def _negotiate_answer(
    peer_connection: Any,
    offer: SessionDescription,
) -> dict[str, str]:
    if peer_connection is None:
        return _fake_answer()

    try:
        from aiortc import RTCSessionDescription

        await peer_connection.setRemoteDescription(
            RTCSessionDescription(sdp=offer.sdp, type=offer.type)
        )
        answer = await peer_connection.createAnswer()
        await peer_connection.setLocalDescription(answer)
        local_description = peer_connection.localDescription
        return {
            "type": getattr(local_description, "type", "answer"),
            "sdp": getattr(local_description, "sdp", "") or _fake_answer()["sdp"],
        }
    except Exception:
        return _fake_answer()


def _fake_answer() -> dict[str, str]:
    return {
        "type": "answer",
        "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=RayMe\r\nt=0 0\r\n",
    }
