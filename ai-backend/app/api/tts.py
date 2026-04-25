from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.config import AiBackendSettings
from app.models.model_manager import ModelManager
from app.models.tts_registry import TtsSynthesisInput

router = APIRouter()


class TtsSynthesizeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str | None = Field(default=None, max_length=64)
    text: str = Field(min_length=1, max_length=5000)
    reference_audio_b64: str = Field(
        min_length=1,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)
    use_default_engine: bool = False
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)


@router.post("/tts/synthesize")
def synthesize(request: Request, payload: TtsSynthesizeRequest) -> dict[str, Any]:
    target_engine = _target_engine(request, payload)
    reference_audio = _decode_reference_audio(payload.reference_audio_b64)
    manager = _manager_from_app(request)

    try:
        manager.switch_tts_engine(target_engine)
        adapter = manager.tts_adapters[target_engine]
        result = adapter.synthesize(
            TtsSynthesisInput(
                text=payload.text,
                reference_audio=reference_audio,
                reference_audio_content_type=payload.reference_audio_content_type,
                reference_transcript=payload.reference_transcript,
                speech_speed=payload.speech_speed,
            )
        )
        if not result.wav_bytes:
            raise ValueError("synthesis returned empty audio")
    except HTTPException:
        raise
    except Exception as exc:
        _mark_engine_unavailable(manager, target_engine)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "tts_failed",
                "message": "Synthesis failed",
                "engine_id": target_engine,
            },
        ) from exc

    return {
        "engine_id": target_engine,
        "voice_id": payload.voice_id,
        "content_type": "audio/wav",
        "audio_base64": base64.b64encode(result.wav_bytes).decode("ascii"),
        "sample_rate": result.sample_rate,
        "duration_ms": result.duration_ms,
    }


def _target_engine(request: Request, payload: TtsSynthesizeRequest) -> str:
    if payload.use_default_engine:
        return payload.engine_id or _settings_from_app(request).default_tts_engine
    if not payload.engine_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_tts_request", "message": "engine_id is required"},
        )
    return payload.engine_id


def _decode_reference_audio(reference_audio_b64: str) -> bytes:
    try:
        decoded = base64.b64decode(reference_audio_b64, validate=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_tts_request",
                "message": "reference_audio_b64 must be valid base64",
            },
        ) from exc
    if not decoded:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_tts_request",
                "message": "reference_audio_b64 must not be empty",
            },
        )
    return decoded


def _settings_from_app(request: Request) -> AiBackendSettings:
    manager = getattr(request.app.state, "model_manager", None)
    settings = getattr(manager, "settings", None)
    if isinstance(settings, AiBackendSettings):
        return settings
    return AiBackendSettings()


def _manager_from_app(request: Request) -> Any:
    manager = getattr(request.app.state, "model_manager", None)
    if manager is None:
        manager = ModelManager(AiBackendSettings())
        manager.startup()
        request.app.state.model_manager = manager
    return manager


def _mark_engine_unavailable(manager: Any, engine_id: str) -> None:
    marker = getattr(manager, "_mark_unavailable", None)
    if callable(marker):
        marker(engine_id, "engine synthesis failed")
