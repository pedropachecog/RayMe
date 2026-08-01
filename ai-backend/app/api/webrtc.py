from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import logging
import os
import secrets
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.stt import _settings_from_app, _stt_adapter_from_app, _vad_adapter_from_app
from app.api.tts import _qwen_error_detail, _qwen_http_status
from app.call.session import (
    AcceptedSpeechConfiguration,
    CallSession,
    CallSessionManager,
    PeerOfferConfiguration,
    SpeechSegmentConflictError,
    SpeechSessionSelectionError,
    SpeechTurnTerminalError,
    TerminalCallSessionError,
)
from app.call.tracks import QueuedAudioOutputTrack
from app.models.model_manager import ModelManager
from app.models.tts_qwen3 import Qwen3WorkerError
from app.models.tts_registry import (
    MAX_REFERENCE_AUDIO_B64_LENGTH,
    MAX_REFERENCE_AUDIO_BYTES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webrtc", tags=["webrtc"])

RAYME_EVENTS_CHANNEL = "rayme-events"
WEBRTC_OFFER_FAILED = "webrtc_offer_failed"
WEBRTC_OFFER_FAILED_MESSAGE = "WebRTC offer could not be accepted"
WEBRTC_AUDIO_TRACK_FAILED = "webrtc_audio_track_failed"
WEBRTC_AUDIO_TRACK_FAILED_MESSAGE = "Backend could not create call audio output track"
WEBRTC_RUNTIME_UNAVAILABLE = "webrtc_runtime_unavailable"
WEBRTC_RUNTIME_UNAVAILABLE_MESSAGE = "Backend WebRTC runtime is unavailable"


def _require_service_auth(request: Request) -> None:
    settings = getattr(request.app.state, "ai_backend_settings", None)
    expected = str(getattr(settings, "service_auth_token", "") or "")
    if len(expected) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "service_auth_not_configured",
                "message": "Service authentication is unavailable",
            },
        )
    authorization = request.headers.get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not supplied
        or not secrets.compare_digest(supplied, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "service_auth_invalid",
                "message": "Service authentication failed",
            },
        )


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
    text: str = Field(max_length=5000)
    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str = Field(min_length=1, max_length=64)
    final_chunk: bool = False
    segment_id: str | None = Field(default=None, min_length=1, max_length=160)
    segment_ordinal: int | None = Field(default=None, ge=0, le=100_000)
    reference_audio_b64: str | None = Field(
        default=None,
        max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)
    voxcpm2_cloning_mode: Literal["auto", "reference_only", "transcript_guided"] = "auto"
    voxcpm2_style_prompt: str | None = Field(default=None, max_length=300)
    voxcpm2_cfg_value: float = Field(default=2.0, ge=1.0, le=3.0)
    voxcpm2_inference_timesteps: int = Field(default=10, ge=4, le=30)
    voxcpm2_normalize: bool = True
    voxcpm2_denoise: bool = True
    release_evidence_mode: Literal["phase09_release_evidence"] | None = None
    release_evidence_seed: int | None = Field(
        default=None,
        ge=0,
        le=4_294_967_295,
    )

    @model_validator(mode="after")
    def require_paired_release_evidence_fields(self) -> "SpeakRequest":
        if (self.release_evidence_mode is None) != (self.release_evidence_seed is None):
            raise ValueError("release evidence mode and seed must be provided together")
        if not self.text.strip() and not (
            self.engine_id == "qwen3_1_7b" and self.final_chunk
        ):
            raise ValueError("speech text is required unless finalizing a Qwen turn")
        return self


class PrepareSpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str = Field(min_length=1, max_length=64)
    reference_audio_b64: str = Field(
        min_length=1,
        max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str = Field(min_length=1, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)

    @field_validator("reference_transcript")
    @classmethod
    def require_reference_transcript(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reference transcript is required")
        return value


class ReconnectAudioBackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pcm_b64: str = Field(default="", max_length=4_000_000)
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    backfill_id: str | None = Field(default=None, max_length=160)
    reason: str | None = Field(default=None, max_length=80)
    attempt: int | None = Field(default=None, ge=0, le=10)
    duration_ms: int | None = Field(default=None, ge=0, le=60000)
    batch_index: int | None = Field(default=None, ge=0, le=20)
    final: bool = True


class CallControlResponse(BaseModel):
    session_id: str
    state: str
    muted: bool | None = None
    interrupted: bool | None = None
    cancelled_turn_id: str | None = None
    receiver_drain_ms: int | None = Field(default=None, ge=1, le=500)
    reason: str | None = None


@router.get("/status")
def get_webrtc_status(request: Request) -> dict[str, object]:
    manager = _manager_from_app(request)
    model_manager = getattr(request.app.state, "model_manager", None)
    model_health = model_manager.health() if model_manager is not None else {}
    return {
        "status": "ready",
        "phase": "03",
        "live_call_ready": True,
        "media_transport_ready": True,
        "active_sessions": manager.stats()["active_sessions"],
        "deployed_commit": os.environ.get("RAYME_DEPLOYED_COMMIT", "").strip(),
        "tts_model": {
            "resident_engine": model_health.get("resident_tts_engine"),
            "loading_engine": model_health.get("loading_engine"),
            "torch_reserved_mib": model_health.get("tts_torch_reserved_mib"),
        },
        "selected_voice_prompt": model_health.get(
            "selected_voice_prompt",
            {
                "engine_id": None,
                "voice_key": None,
                "state": "none",
                "error_code": None,
            },
        ),
        "message": "Phase 3 live call signaling is ready.",
    }


@router.post(
    "/sessions/{session_id}/prepare",
    dependencies=[Depends(_require_service_auth)],
)
async def prepare_session_speech(
    request: Request,
    session_id: str,
    payload: PrepareSpeechRequest,
) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    if not await session.can_prepare_tts_prompt():
        raise _terminal_session_prepare_error()
    if payload.voice_id != session.voice_id or payload.engine_id != session.engine_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "call_tts_prepare_mismatch",
                "message": "Selected voice does not match the call",
            },
        )
    reference_audio = _decode_reference_audio(payload.reference_audio_b64)
    model_manager = getattr(request.app.state, "model_manager", None)
    prepare = getattr(model_manager, "prepare_tts_engine", None)
    if not callable(prepare):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "call_tts_prepare_unavailable",
                "message": "Voice preparation is unavailable",
            },
        )
    try:
        result = await prepare(
            payload.engine_id,
            voice_key=payload.voice_id,
            reference_audio=reference_audio,
            reference_transcript=payload.reference_transcript,
            prompt_lease_owner=session_id,
        )
        release_lease = getattr(model_manager, "release_tts_prompt_lease", None)
        if callable(release_lease):
            installed = await session.install_or_release_tts_prompt_lease(
                release_lease
            )
            if not installed:
                raise _terminal_session_prepare_error()
    except HTTPException:
        raise
    except Qwen3WorkerError as exc:
        raise HTTPException(
            status_code=_qwen_http_status(exc),
            detail=_qwen_error_detail(exc, payload.engine_id),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "call_tts_prepare_failed",
                "message": "Voice preparation failed",
                "engine_id": payload.engine_id,
            },
        ) from exc
    return {"session_id": session_id, **dict(result)}


@router.post("/offer", dependencies=[Depends(_require_service_auth)])
async def create_webrtc_offer_answer(
    request: Request,
    payload: CallOfferRequest,
) -> dict[str, Any]:
    manager = _manager_from_app(request)
    existing_session = manager.get_session(payload.session_id)
    if (
        existing_session is not None
        and existing_session.state in {"ended", "failed"}
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "call_session_terminal",
                "message": "Call session has ended; start a new call",
            },
        )
    offer_sdp = payload.offer.sdp
    logger.info(
        "[rayme-call] offer.received session=%s thread=%s sdp_len=%d "
        "has_audio=%s has_ice_ufrag=%s has_fingerprint=%s",
        payload.session_id,
        payload.thread_id,
        len(offer_sdp),
        "m=audio" in offer_sdp,
        "a=ice-ufrag:" in offer_sdp,
        "a=fingerprint:" in offer_sdp,
    )
    peer_connection = _create_peer_connection(payload.offer)
    outbound_audio_track = _attach_outbound_audio_track(peer_connection)

    negotiate_started = time.monotonic()
    pending_generation: int | None = None
    try:
        if existing_session is not None:
            session = existing_session
            session.mark_media_reconnect_pending()
            pending_generation = await session.mark_peer_connection_pending(
                peer_connection,
                outbound_audio_track=outbound_audio_track,
                configuration=PeerOfferConfiguration(
                    thread_id=payload.thread_id,
                    voice_id=payload.voice_id,
                    engine_id=payload.engine_id,
                    prompt_messages=tuple(
                        message.model_dump()
                        for message in payload.prompt_messages
                    ),
                    vad_adapter=_vad_adapter(request),
                    stt_adapter=_stt_adapter(request),
                ),
            )
        else:
            session = await manager.create_session(
                session_id=payload.session_id,
                thread_id=payload.thread_id,
                voice_id=payload.voice_id,
                engine_id=payload.engine_id,
                prompt_messages=[
                    message.model_dump() for message in payload.prompt_messages
                ],
                peer_connection=peer_connection,
                vad_adapter=_vad_adapter(request),
                stt_adapter=_stt_adapter(request),
                outbound_audio_track=outbound_audio_track,
                close_previous_peer=False,
            )
        _attach_peer_handlers(
            peer_connection,
            session,
            pending_generation=pending_generation,
        )
        answer = await _negotiate_answer(peer_connection, payload.offer)
        if (
            existing_session is not None
            and peer_connection is not session.peer_connection
            and not session.is_peer_connection_pending(
                peer_connection,
                pending_generation,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "webrtc_offer_superseded",
                    "message": "A newer reconnect offer replaced this offer",
                },
            )
    except TerminalCallSessionError as exc:
        await _close_peer_connection(peer_connection)
        logger.info(
            "[rayme-call] offer.rejected_terminal session=%s elapsed_ms=%d",
            payload.session_id,
            int((time.monotonic() - negotiate_started) * 1000),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "call_session_terminal",
                "message": "Call session has ended; start a new call",
            },
        ) from exc
    except HTTPException:
        if existing_session is not None:
            await _restore_failed_offer_session(
                existing_session,
                peer_connection,
                pending_generation,
            )
        else:
            await manager.remove_session(payload.session_id)
            await _close_peer_connection(peer_connection)
        logger.exception(
            "[rayme-call] offer.failed session=%s elapsed_ms=%d",
            payload.session_id,
            int((time.monotonic() - negotiate_started) * 1000),
        )
        raise
    except asyncio.CancelledError:
        if existing_session is not None:
            await _restore_failed_offer_session(
                existing_session,
                peer_connection,
                pending_generation,
            )
        else:
            await manager.remove_session(payload.session_id)
            await _close_peer_connection(peer_connection)
        logger.info(
            "[rayme-call] offer.cancelled session=%s elapsed_ms=%d",
            payload.session_id,
            int((time.monotonic() - negotiate_started) * 1000),
        )
        raise
    except Exception as exc:
        if existing_session is not None:
            await _restore_failed_offer_session(
                existing_session,
                peer_connection,
                pending_generation,
            )
        else:
            await manager.remove_session(payload.session_id)
            await _close_peer_connection(peer_connection)
        logger.exception(
            "[rayme-call] offer.unhandled session=%s elapsed_ms=%d exc=%s",
            payload.session_id,
            int((time.monotonic() - negotiate_started) * 1000),
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "webrtc_offer_failed",
                "message": "WebRTC offer could not be accepted",
            },
        ) from exc

    answer_sdp = answer.get("sdp", "")
    logger.info(
        "[rayme-call] offer.answered session=%s elapsed_ms=%d answer_sdp_len=%d "
        "answer_has_audio=%s data_channel_owner=%s",
        session.session_id,
        int((time.monotonic() - negotiate_started) * 1000),
        len(answer_sdp),
        "m=audio" in answer_sdp,
        "browser",
    )
    return {
        "session_id": session.session_id,
        "answer": answer,
        "event_channel": RAYME_EVENTS_CHANNEL,
        "data_channel": {"label": RAYME_EVENTS_CHANNEL},
    }


@router.post(
    "/sessions/{session_id}/mute",
    response_model=CallControlResponse,
    dependencies=[Depends(_require_service_auth)],
)
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


@router.post(
    "/sessions/{session_id}/interrupt",
    response_model=CallControlResponse,
    dependencies=[Depends(_require_service_auth)],
)
async def interrupt_session(request: Request, session_id: str) -> CallControlResponse:
    session = _session_or_404(request, session_id)
    try:
        event = await session.interrupt()
        return CallControlResponse(
            session_id=session.session_id,
            state=session.state,
            interrupted=True,
            cancelled_turn_id=event.get("cancelled_turn_id"),
            receiver_drain_ms=int(event["receiver_drain_ms"]),
        )
    except Exception as exc:
        raise _control_error() from exc


@router.post(
    "/sessions/{session_id}/turns/{turn_id}/cancel",
    dependencies=[Depends(_require_service_auth)],
)
async def cancel_session_speech_turn(
    request: Request,
    session_id: str,
    turn_id: str,
) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    try:
        cancellation = await session.cancel_speech_turn(turn_id)
        return {
            "session_id": session.session_id,
            "turn_id": turn_id,
            "state": session.state,
            "status": "cancelled",
            **cancellation,
        }
    except Exception as exc:
        raise _control_error() from exc


@router.post(
    "/sessions/{session_id}/speak",
    dependencies=[Depends(_require_service_auth)],
)
async def speak_session(
    request: Request,
    session_id: str,
    payload: SpeakRequest,
) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    try:
        accepted_configuration: AcceptedSpeechConfiguration = (
            await session.reserve_accepted_speech_configuration(
                voice_id=payload.voice_id,
                engine_id=payload.engine_id,
            )
        )
        if payload.release_evidence_mode is not None and (
            payload.engine_id != "qwen3_1_7b"
            or not session_id.startswith("phase09-evidence-")
            or not payload.turn_id.startswith("evidence-")
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "qwen_release_evidence_scope_invalid",
                    "message": "Release evidence seed is restricted to the Phase 09 evidence runner",
                    "engine_id": payload.engine_id,
                },
            )
        _reject_oversized_reference_audio(payload.reference_audio_b64)
        if payload.engine_id == "qwen3_1_7b" and not str(
            payload.reference_transcript or ""
        ).strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "qwen3_transcript_required",
                    "message": "Matching reference transcript is required",
                    "engine_id": payload.engine_id,
                },
            )
        terminal_marker = (
            payload.engine_id == "qwen3_1_7b"
            and payload.final_chunk
            and not payload.text.strip()
        )
        if terminal_marker:
            event = await session.complete_speech_turn(
                turn_id=payload.turn_id,
                voice_id=payload.voice_id,
                engine_id=payload.engine_id,
                segment_id=payload.segment_id,
                segment_ordinal=payload.segment_ordinal,
                accepted_configuration=accepted_configuration,
            )
        else:
            qwen_reference_audio = None
            if payload.engine_id == "qwen3_1_7b":
                qwen_reference_audio = _decode_reference_audio(
                    payload.reference_audio_b64 or ""
                )
            adapter = _tts_adapter(
                request,
                payload.engine_id,
                voice_key=payload.voice_id,
                reference_audio=qwen_reference_audio,
                reference_transcript=payload.reference_transcript,
            )
            event = await session.speak_text(
                payload.turn_id,
                payload.text,
                payload.voice_id,
                payload.engine_id,
                final_chunk=payload.final_chunk,
                segment_id=payload.segment_id,
                segment_ordinal=payload.segment_ordinal,
                accepted_configuration=accepted_configuration,
                tts_adapter=adapter,
                reference_audio_b64=payload.reference_audio_b64,
                reference_transcript=payload.reference_transcript,
                reference_audio_content_type=payload.reference_audio_content_type,
                voxcpm2_cloning_mode=payload.voxcpm2_cloning_mode,
                voxcpm2_style_prompt=payload.voxcpm2_style_prompt,
                voxcpm2_cfg_value=payload.voxcpm2_cfg_value,
                voxcpm2_inference_timesteps=payload.voxcpm2_inference_timesteps,
                voxcpm2_normalize=payload.voxcpm2_normalize,
                voxcpm2_denoise=payload.voxcpm2_denoise,
                qwen3_release_evidence_mode=payload.release_evidence_mode,
                qwen3_release_evidence_seed=payload.release_evidence_seed,
            )
    except (
        SpeechSegmentConflictError,
        SpeechSessionSelectionError,
        SpeechTurnTerminalError,
    ) as exc:
        code = (
            "call_speech_segment_conflict"
            if isinstance(exc, SpeechSegmentConflictError)
            else (
                "call_speech_turn_terminal"
                if isinstance(exc, SpeechTurnTerminalError)
                else "call_speech_selection_mismatch"
            )
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": code,
                "message": "Speech request conflicts with the active call",
            },
        ) from exc
    except asyncio.CancelledError:
        # The SSE generator on the web-ui side was cancelled (e.g., HTTP
        # connection closed). Return 502 so the web-ui client sees a
        # processing error rather than an opaque 500 Internal Server Error.
        logger.info(
            "[rayme-call] speak.cancelled session=%s turn=%s",
            session_id,
            payload.turn_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "call_tts_failed",
                "message": "Speech playback cancelled",
                "engine_id": payload.engine_id,
            },
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


@router.post(
    "/sessions/{session_id}/reconnect-audio",
    dependencies=[Depends(_require_service_auth)],
)
async def backfill_session_reconnect_audio(
    request: Request,
    session_id: str,
    payload: ReconnectAudioBackfillRequest,
) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    try:
        pcm = base64.b64decode(payload.pcm_b64, validate=True)
        result = await session.backfill_reconnect_audio(
            pcm=pcm,
            sample_rate=payload.sample_rate,
            channels=payload.channels,
            backfill_id=payload.backfill_id,
            reason=payload.reason,
            attempt=payload.attempt,
            batch_index=payload.batch_index,
            final=payload.final,
        )
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "call_reconnect_audio_invalid",
                "message": "Reconnect audio backfill was invalid",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "call_reconnect_audio_failed",
                "message": "Reconnect audio backfill failed",
            },
        ) from exc

    return {
        "session_id": session.session_id,
        **result,
    }


@router.post(
    "/sessions/{session_id}/events/drain",
    dependencies=[Depends(_require_service_auth)],
)
async def drain_session_events(
    request: Request,
    session_id: str,
) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    return {
        "session_id": session.session_id,
        "events": session.drain_undelivered_events(),
    }


@router.post(
    "/sessions/{session_id}/end",
    response_model=CallControlResponse,
    dependencies=[Depends(_require_service_auth)],
)
async def end_session(
    request: Request,
    session_id: str,
    payload: EndControlRequest | None = None,
) -> CallControlResponse:
    manager = _manager_from_app(request)
    session = _session_or_404(request, session_id)
    reason = payload.reason if payload is not None else "hangup"
    try:
        ended_session = await manager.end_session(session_id, reason=reason)
        if ended_session is not None:
            session = ended_session
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


def _reject_oversized_reference_audio(reference_audio_b64: str | None) -> None:
    if not reference_audio_b64:
        return
    padding = len(reference_audio_b64) - len(reference_audio_b64.rstrip("="))
    decoded_size = max((len(reference_audio_b64) * 3 // 4) - padding, 0)
    if decoded_size > MAX_REFERENCE_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "call_tts_reference_audio_too_large",
                "message": "Reference audio is too large",
            },
        )


def _decode_reference_audio(reference_audio_b64: str) -> bytes:
    _reject_oversized_reference_audio(reference_audio_b64)
    try:
        decoded = base64.b64decode(reference_audio_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "call_tts_reference_audio_invalid",
                "message": "Reference audio is invalid",
            },
        ) from exc
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "call_tts_reference_audio_invalid",
                "message": "Reference audio is invalid",
            },
        )
    return decoded


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


def _terminal_session_prepare_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "call_session_terminal",
            "message": "Ended call sessions cannot prepare speech",
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
        settings.vad_silero_min_silence_ms,
    )


def _tts_adapter(
    request: Request,
    engine_id: str,
    *,
    voice_key: str | None = None,
    reference_audio: bytes | None = None,
    reference_transcript: str | None = None,
) -> Any:
    manager = getattr(request.app.state, "model_manager", None)
    if manager is None:
        manager = ModelManager(_settings_from_app(request))
        manager.startup()
        request.app.state.model_manager = manager
    if engine_id == "qwen3_1_7b":
        is_ready = getattr(manager, "is_tts_prompt_ready", None)
        if not callable(is_ready) or not is_ready(
            engine_id,
            voice_key or "",
            reference_audio=reference_audio,
            reference_transcript=reference_transcript,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "call_tts_not_ready",
                    "message": "Selected voice is not ready",
                    "engine_id": engine_id,
                },
            )
    else:
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


async def _close_peer_connection(peer_connection: Any) -> None:
    close = getattr(peer_connection, "close", None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def _restore_failed_offer_session(
    session: CallSession,
    failed_peer_connection: Any,
    pending_generation: int | None,
) -> None:
    await session.reject_pending_peer_connection(
        failed_peer_connection,
        generation=pending_generation,
    )


def _create_peer_connection(offer: SessionDescription) -> Any:
    if not _looks_like_real_media_offer(offer.sdp):
        raise _offer_error()
    try:
        from aiortc import RTCPeerConnection

        return RTCPeerConnection()
    except Exception as exc:
        raise _offer_error(
            code=WEBRTC_RUNTIME_UNAVAILABLE,
            message=WEBRTC_RUNTIME_UNAVAILABLE_MESSAGE,
        ) from exc


def _looks_like_real_media_offer(sdp: str) -> bool:
    return "m=audio" in sdp and "a=ice-ufrag:" in sdp


def _attach_outbound_audio_track(peer_connection: Any) -> QueuedAudioOutputTrack:
    add_track = getattr(peer_connection, "addTrack", None)
    if not callable(add_track):
        raise _offer_error(
            code=WEBRTC_AUDIO_TRACK_FAILED,
            message=WEBRTC_AUDIO_TRACK_FAILED_MESSAGE,
        )
    try:
        track = QueuedAudioOutputTrack()
        add_track(track)
        return track
    except Exception as exc:
        raise _offer_error(
            code=WEBRTC_AUDIO_TRACK_FAILED,
            message=WEBRTC_AUDIO_TRACK_FAILED_MESSAGE,
        ) from exc


def _attach_peer_handlers(
    peer_connection: Any,
    session: CallSession,
    *,
    pending_generation: int | None = None,
) -> None:
    if not hasattr(peer_connection, "on"):
        return

    keepalive_task: asyncio.Task | None = None

    async def accept_pending_peer_if_connected(source: str) -> None:
        if not session.is_peer_connection_pending(
            peer_connection,
            pending_generation,
        ):
            return
        connection_state = getattr(peer_connection, "connectionState", None)
        ice_state = getattr(peer_connection, "iceConnectionState", None)
        if connection_state != "connected" and ice_state not in {"connected", "completed"}:
            return
        accepted, _ = await session.accept_pending_peer_connection(
            peer_connection,
            generation=pending_generation,
        )
        if not accepted:
            return
        logger.info(
            "[rayme-call] peer.pending.accepted session=%s source=%s conn=%s ice=%s",
            session.session_id,
            source,
            connection_state,
            ice_state,
        )

    async def discard_failed_pending_peer(source: str) -> bool:
        if not session.is_peer_connection_pending(
            peer_connection,
            pending_generation,
        ):
            return False
        connection_state = getattr(peer_connection, "connectionState", None)
        ice_state = getattr(peer_connection, "iceConnectionState", None)
        if connection_state not in {"failed", "closed"} and ice_state not in {"failed", "closed"}:
            return False
        discarded = await session.reject_pending_peer_connection(
            peer_connection,
            generation=pending_generation,
        )
        if not discarded:
            return False
        logger.info(
            "[rayme-call] peer.pending.discarded session=%s source=%s conn=%s ice=%s",
            session.session_id,
            source,
            connection_state,
            ice_state,
        )
        return True

    @peer_connection.on("datachannel")
    def on_datachannel(channel: Any) -> None:
        nonlocal keepalive_task
        label = getattr(channel, "label", None)
        ready = getattr(channel, "readyState", "?")
        logger.info(
            "[rayme-call] peer.on_datachannel session=%s label=%s readyState=%s",
            session.session_id,
            label,
            ready,
        )
        if label == RAYME_EVENTS_CHANNEL:
            session.set_data_channel_for_peer(
                peer_connection,
                channel,
                generation=pending_generation,
            )

            def start_keepalive() -> None:
                nonlocal keepalive_task
                if keepalive_task is not None and not keepalive_task.done():
                    return
                keepalive_task = asyncio.create_task(
                    _data_channel_keepalive(session, channel)
                )

            if hasattr(channel, "on"):
                @channel.on("open")
                def on_dc_open() -> None:
                    logger.info(
                        "[rayme-call] datachannel.open session=%s label=%s",
                        session.session_id,
                        label,
                    )
                    start_keepalive()

                @channel.on("close")
                def on_dc_close() -> None:
                    nonlocal keepalive_task
                    if keepalive_task is not None:
                        keepalive_task.cancel()
                        keepalive_task = None
                    logger.info(
                        "[rayme-call] datachannel.close session=%s label=%s",
                        session.session_id,
                        label,
                    )

                @channel.on("error")
                def on_dc_error(error: Any) -> None:
                    logger.info(
                        "[rayme-call] datachannel.error session=%s label=%s err=%s",
                        session.session_id,
                        label,
                        error.__class__.__name__ if error else "?",
                    )

            if getattr(channel, "readyState", None) == "open":
                logger.info(
                    "[rayme-call] datachannel.open session=%s label=%s already_open=True",
                    session.session_id,
                    label,
                )
                start_keepalive()

    @peer_connection.on("track")
    def on_track(track: Any) -> None:
        kind = getattr(track, "kind", None)
        track_id = getattr(track, "id", None)
        logger.info(
            "[rayme-call] peer.on_track session=%s kind=%s id=%s",
            session.session_id,
            kind,
            track_id,
        )
        if kind == "audio":
            asyncio.create_task(
                _receive_audio_track(
                    session,
                    track,
                    peer_connection,
                    pending_generation=pending_generation,
                )
            )

    @peer_connection.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        state = getattr(peer_connection, "connectionState", None)
        logger.info(
            "[rayme-call] peer.connectionstatechange session=%s state=%s",
            session.session_id,
            state,
        )
        if await discard_failed_pending_peer("connectionstatechange"):
            return
        await accept_pending_peer_if_connected("connectionstatechange")
        if peer_connection is session.peer_connection:
            await session.handle_connection_state_change(peer_connection)

    @peer_connection.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange() -> None:
        state = getattr(peer_connection, "iceConnectionState", None)
        logger.info(
            "[rayme-call] peer.iceconnectionstatechange session=%s state=%s",
            session.session_id,
            state,
        )
        if await discard_failed_pending_peer("iceconnectionstatechange"):
            return
        await accept_pending_peer_if_connected("iceconnectionstatechange")
        if peer_connection is session.peer_connection:
            await session.handle_connection_state_change(
                peer_connection,
                terminal_state=state,
            )

    @peer_connection.on("icegatheringstatechange")
    async def on_icegatheringstatechange() -> None:
        state = getattr(peer_connection, "iceGatheringState", None)
        logger.info(
            "[rayme-call] peer.icegatheringstatechange session=%s state=%s",
            session.session_id,
            state,
        )

    @peer_connection.on("signalingstatechange")
    async def on_signalingstatechange() -> None:
        state = getattr(peer_connection, "signalingState", None)
        logger.info(
            "[rayme-call] peer.signalingstatechange session=%s state=%s",
            session.session_id,
            state,
        )


async def _receive_audio_track(
    session: CallSession,
    track: Any,
    peer_connection: Any | None = None,
    *,
    pending_generation: int | None = None,
) -> None:
    logger.info(
        "[rayme-call] track.recv.start session=%s kind=%s id=%s",
        session.session_id,
        getattr(track, "kind", None),
        getattr(track, "id", None),
    )
    frame_count = 0
    consecutive_live_recv_errors = 0
    while session.state not in {"ended", "failed"}:
        if (
            peer_connection is not None
            and not session.is_peer_connection_active_or_pending(peer_connection)
        ):
            logger.info(
                "[rayme-call] track.recv.superseded session=%s frames=%d",
                session.session_id,
                frame_count,
            )
            break
        try:
            frame = await track.recv()
        except Exception as exc:
            exc_name = exc.__class__.__name__
            if (
                peer_connection is not None
                and not session.is_peer_connection_active_or_pending(peer_connection)
            ):
                logger.info(
                    "[rayme-call] track.recv.superseded session=%s frames=%d "
                    "after_exc=%s",
                    session.session_id,
                    frame_count,
                    exc_name,
                )
                break
            pc = peer_connection or session.peer_connection
            ice_state = getattr(pc, "iceConnectionState", "?")
            conn_state = getattr(pc, "connectionState", "?")
            logger.info(
                "[rayme-call] track.recv.error session=%s frames=%d exc=%s "
                "ice=%s conn=%s",
                session.session_id,
                frame_count,
                exc_name,
                ice_state,
                conn_state,
            )
            if session.state in {"ended", "failed"}:
                break
            if ice_state in {"failed", "closed"} or conn_state in {"failed", "closed"}:
                await _handle_receiver_peer_terminal(
                    session,
                    pc,
                    pending_generation=pending_generation,
                    terminal_state=(
                        "failed"
                        if "failed" in {ice_state, conn_state}
                        else "closed"
                    ),
                )
                return
            if ice_state == "disconnected" or conn_state == "disconnected":
                reconnected = False
                for attempt in range(10):
                    await asyncio.sleep(0.5)
                    if session.state in {"ended", "failed"}:
                        return
                    if not session.is_peer_connection_active_or_pending(pc):
                        logger.info(
                            "[rayme-call] track.recv.superseded session=%s frames=%d "
                            "during_reconnect=True",
                            session.session_id,
                            frame_count,
                        )
                        return
                    ice_state = getattr(pc, "iceConnectionState", "?")
                    conn_state = getattr(pc, "connectionState", "?")
                    if (
                        ice_state in {"completed", "connected"}
                        or conn_state == "connected"
                    ):
                        reconnected = True
                        logger.info(
                            "[rayme-call] track.recv.reconnected session=%s "
                            "ice=%s conn=%s after=%.1fs",
                            session.session_id,
                            ice_state,
                            conn_state,
                            (attempt + 1) * 0.5,
                        )
                        break
                if not reconnected:
                    logger.info(
                        "[rayme-call] track.recv.reconnect_timeout session=%s",
                        session.session_id,
                    )
                    await _handle_receiver_peer_terminal(
                        session,
                        pc,
                        pending_generation=pending_generation,
                        terminal_state="failed",
                    )
                    return
                continue
            # The inbound read can raise while ICE/connection are still alive
            # on mobile Chrome. Treat that as a transient RTP/read gap: keep
            # outbound audio alive and keep the input receive loop ready for
            # resumed microphone frames instead of silently killing listening.
            consecutive_live_recv_errors += 1
            backoff_seconds = min(1.0, 0.1 * consecutive_live_recv_errors)
            logger.info(
                "[rayme-call] track.recv.live_retry session=%s frames=%d "
                "exc=%s consecutive=%d backoff=%.1fs",
                session.session_id,
                frame_count,
                exc_name,
                consecutive_live_recv_errors,
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)
            continue
        frame_count += 1
        consecutive_live_recv_errors = 0
        if frame_count == 1:
            if (
                peer_connection is not None
                and session.is_peer_connection_pending(
                    peer_connection,
                    pending_generation,
                )
            ):
                accepted, _ = (
                    await session.accept_pending_peer_connection(
                        peer_connection,
                        generation=pending_generation,
                    )
                )
                if not accepted:
                    break
                logger.info(
                    "[rayme-call] peer.pending.accepted session=%s source=first_audio_frame",
                    session.session_id,
                )
            session.start_media_reconnect_grace_if_pending()
            logger.info(
                "[rayme-call] track.recv.first_frame session=%s sample_rate=%s "
                "samples=%s",
                session.session_id,
                getattr(frame, "sample_rate", "?"),
                getattr(frame, "samples", "?"),
            )
        elif frame_count % 50 == 0:
            logger.info(
                "[rayme-call] track.recv.progress session=%s frames=%d state=%s",
                session.session_id,
                frame_count,
                session.state,
            )
        await session.handle_inbound_audio_frame(frame)
    logger.info(
        "[rayme-call] track.recv.exit session=%s frames=%d state=%s",
        session.session_id,
        frame_count,
        session.state,
    )


async def _handle_receiver_peer_terminal(
    session: CallSession,
    peer_connection: Any,
    *,
    pending_generation: int | None,
    terminal_state: str,
) -> None:
    if peer_connection is session.peer_connection:
        await session.handle_connection_state_change(
            peer_connection,
            terminal_state=terminal_state,
        )
        return
    if session.is_peer_connection_pending(
        peer_connection,
        pending_generation,
    ):
        await session.reject_pending_peer_connection(
            peer_connection,
            generation=pending_generation,
        )


async def _data_channel_keepalive(session: CallSession, channel: Any) -> None:
    send = getattr(channel, "send", None)
    if not callable(send):
        return

    interval = 2.0

    def _send_ping() -> bool:
        try:
            if getattr(channel, "readyState", "closed") != "open":
                return False
            send('{"type":"ping"}')
            return True
        except Exception:
            return False

    # Send first ping immediately — the data channel just opened,
    # and on Android Chrome the NAT binding can expire within seconds
    # if no packets flow from backend to browser. Waiting 0.5s for
    # the first ping was too long.
    if not _send_ping():
        return

    try:
        while True:
            await asyncio.sleep(interval)
            if session.state in {"ended", "failed"}:
                break
            if not _send_ping():
                break
    except asyncio.CancelledError:
        return


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


def _offer_error(
    *,
    code: str = WEBRTC_OFFER_FAILED,
    message: str = WEBRTC_OFFER_FAILED_MESSAGE,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": code,
            "message": message,
        },
    )
