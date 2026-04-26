from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.api.stt import _settings_from_app, _stt_adapter_from_app, _vad_adapter_from_app
from app.call.session import CallSession, CallSessionManager
from app.call.tracks import QueuedAudioOutputTrack
from app.models.model_manager import ModelManager

router = APIRouter(prefix="/webrtc", tags=["webrtc"])

RAYME_EVENTS_CHANNEL = "rayme-events"
WEBRTC_OFFER_FAILED = "webrtc_offer_failed"
WEBRTC_OFFER_FAILED_MESSAGE = "WebRTC offer could not be accepted"


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


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=5000)
    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str = Field(min_length=1, max_length=64)
    final_chunk: bool = False
    reference_audio_b64: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)


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
    outbound_audio_track = _attach_outbound_audio_track(peer_connection)

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
            outbound_audio_track=outbound_audio_track,
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


@router.post("/sessions/{session_id}/speak")
async def speak_session(
    request: Request,
    session_id: str,
    payload: SpeakRequest,
) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    try:
        adapter = _tts_adapter(request, payload.engine_id)
        event = await session.speak_text(
            payload.turn_id,
            payload.text,
            payload.voice_id,
            payload.engine_id,
            final_chunk=payload.final_chunk,
            tts_adapter=adapter,
            reference_audio_b64=payload.reference_audio_b64,
            reference_transcript=payload.reference_transcript,
            reference_audio_content_type=payload.reference_audio_content_type,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "call_tts_failed",
                "message": "Speech playback failed",
                "engine_id": payload.engine_id,
            },
        ) from exc

    if event.get("type") == "failed" and event.get("code") == "call_tts_failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "call_tts_failed",
                "message": "Speech playback failed",
                "engine_id": payload.engine_id,
            },
        )
    return {
        "session_id": session.session_id,
        "turn_id": payload.turn_id,
        "state": session.state,
        "event": event,
    }


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


def _tts_adapter(request: Request, engine_id: str) -> Any:
    manager = getattr(request.app.state, "model_manager", None)
    if manager is None:
        manager = ModelManager(_settings_from_app(request))
        manager.startup()
        request.app.state.model_manager = manager
    switch = getattr(manager, "switch_tts_engine", None)
    if callable(switch):
        switch(engine_id)
    adapters = getattr(manager, "tts_adapters", {})
    try:
        return adapters[engine_id]
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "call_tts_failed",
                "message": "Speech playback failed",
                "engine_id": engine_id,
            },
        ) from exc


def _create_peer_connection(offer: SessionDescription) -> Any:
    if not _looks_like_real_media_offer(offer.sdp):
        raise _offer_error()
    try:
        from aiortc import RTCPeerConnection

        return RTCPeerConnection()
    except Exception as exc:
        raise _offer_error() from exc


def _looks_like_real_media_offer(sdp: str) -> bool:
    return "m=audio" in sdp and "a=ice-ufrag:" in sdp


def _create_data_channel(peer_connection: Any) -> Any:
    create_data_channel = getattr(peer_connection, "createDataChannel", None)
    if not callable(create_data_channel):
        raise _offer_error()
    try:
        return create_data_channel(RAYME_EVENTS_CHANNEL)
    except Exception as exc:
        raise _offer_error() from exc


def _attach_outbound_audio_track(peer_connection: Any) -> QueuedAudioOutputTrack:
    add_track = getattr(peer_connection, "addTrack", None)
    if not callable(add_track):
        raise _offer_error()
    try:
        track = QueuedAudioOutputTrack()
        add_track(track)
        return track
    except Exception as exc:
        raise _offer_error() from exc


def _attach_peer_handlers(peer_connection: Any, session: CallSession) -> None:
    if not hasattr(peer_connection, "on"):
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
    try:
        from aiortc import RTCSessionDescription

        await peer_connection.setRemoteDescription(
            RTCSessionDescription(sdp=offer.sdp, type=offer.type)
        )
        answer = await peer_connection.createAnswer()
        await peer_connection.setLocalDescription(answer)
        local_description = peer_connection.localDescription
        sdp = getattr(local_description, "sdp", "")
        if not sdp:
            raise RuntimeError("empty WebRTC answer SDP")
        return {
            "type": getattr(local_description, "type", "answer"),
            "sdp": sdp,
        }
    except Exception as exc:
        raise _offer_error() from exc


def _offer_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": WEBRTC_OFFER_FAILED,
            "message": WEBRTC_OFFER_FAILED_MESSAGE,
        },
    )
