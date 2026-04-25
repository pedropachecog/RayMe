from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.audio.io import uploaded_bytes_to_temp_wav
from app.config import AiBackendSettings
from app.models.stt import WhisperSttAdapter
from app.models.vad import SileroVadAdapter

router = APIRouter()


@router.post("/stt/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    vad_threshold: float | None = Form(default=None),
    vad_end_silence_ms: int | None = Form(default=None),
) -> dict[str, Any]:
    settings = _settings_from_app(request)
    threshold = settings.vad_threshold if vad_threshold is None else vad_threshold
    end_silence_ms = (
        settings.vad_end_silence_ms
        if vad_end_silence_ms is None
        else vad_end_silence_ms
    )

    try:
        audio = uploaded_bytes_to_temp_wav(
            await file.read(),
            original_filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_audio", "message": "Invalid audio input"},
        ) from exc

    try:
        stt_adapter = _stt_adapter_from_app(request, settings)
        vad_adapter = _vad_adapter_from_app(request, settings, threshold, end_silence_ms)
        result = stt_adapter.transcribe(
            audio=audio.path,
            vad_adapter=vad_adapter,
            vad_threshold=threshold,
            vad_end_silence_ms=end_silence_ms,
        )
        return _response_contract(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "stt_failed",
                "message": "Transcription failed",
                "retry_allowed": True,
                "manual_transcript_allowed": True,
            },
        ) from exc
    finally:
        audio.cleanup()


def _settings_from_app(request: Request) -> AiBackendSettings:
    manager = getattr(request.app.state, "model_manager", None)
    settings = getattr(manager, "settings", None)
    if isinstance(settings, AiBackendSettings):
        return settings
    return AiBackendSettings()


def _stt_adapter_from_app(request: Request, settings: AiBackendSettings) -> Any:
    adapter = getattr(request.app.state, "stt_adapter", None)
    if adapter is not None:
        return adapter
    manager = getattr(request.app.state, "model_manager", None)
    adapter = getattr(manager, "stt_adapter", None)
    if adapter is not None:
        return adapter
    adapter = WhisperSttAdapter(settings=settings)
    request.app.state.stt_adapter = adapter
    return adapter


def _vad_adapter_from_app(
    request: Request,
    settings: AiBackendSettings,
    threshold: float,
    end_silence_ms: int,
) -> Any:
    adapter = getattr(request.app.state, "vad_adapter", None)
    if adapter is not None:
        return adapter
    manager = getattr(request.app.state, "model_manager", None)
    adapter = getattr(manager, "vad_adapter", None)
    if adapter is not None:
        return adapter
    adapter = SileroVadAdapter(
        threshold=threshold,
        end_silence_ms=end_silence_ms,
        sampling_rate=16000,
    )
    request.app.state.vad_adapter = adapter
    return adapter


def _response_contract(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        mapping = result.model_dump()
    else:
        mapping = dict(result)
    return {
        "status": mapping.get("status", "needs_manual_transcript"),
        "transcript": mapping.get("transcript") or "",
        "segments": mapping.get("segments") or [],
        "language": mapping.get("language") or "en",
        "model": mapping.get("model") or "distil-large-v3",
        "compute_type": mapping.get("compute_type") or "int8_float16",
        "speech_detected": bool(mapping.get("speech_detected", False)),
        "retry_allowed": bool(mapping.get("retry_allowed", True)),
        "manual_transcript_allowed": bool(mapping.get("manual_transcript_allowed", True)),
    }
