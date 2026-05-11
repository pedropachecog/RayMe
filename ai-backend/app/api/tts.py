from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.config import AiBackendSettings
from app.models.model_manager import ModelManager
from app.models.tts_registry import (
    MAX_REFERENCE_AUDIO_B64_LENGTH,
    MAX_REFERENCE_AUDIO_BYTES,
    TtsSynthesisInput,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class TtsSynthesizeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str | None = Field(default=None, max_length=64)
    text: str = Field(min_length=1, max_length=5000)
    reference_audio_b64: str = Field(
        min_length=1,
        max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)
    use_default_engine: bool = False
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)
    voxcpm2_cloning_mode: str = Field(default="auto", pattern="^(auto|reference_only|transcript_guided)$")
    voxcpm2_style_prompt: str | None = Field(default=None, max_length=300)
    voxcpm2_cfg_value: float = Field(default=2.0, ge=1.0, le=3.0)
    voxcpm2_inference_timesteps: int = Field(default=10, ge=4, le=30)
    voxcpm2_normalize: bool = True
    voxcpm2_denoise: bool = True


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
                voxcpm2_cloning_mode=payload.voxcpm2_cloning_mode,
                voxcpm2_style_prompt=payload.voxcpm2_style_prompt,
                voxcpm2_cfg_value=payload.voxcpm2_cfg_value,
                voxcpm2_inference_timesteps=payload.voxcpm2_inference_timesteps,
                voxcpm2_normalize=payload.voxcpm2_normalize,
                voxcpm2_denoise=payload.voxcpm2_denoise,
            )
        )
        if not result.wav_bytes:
            raise ValueError("synthesis returned empty audio")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "[rayme-tts] synthesize.failed engine=%s exc=%s",
            target_engine,
            exc.__class__.__name__,
        )
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
        "warnings": result.warning_codes or result.warnings,
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
    if len(decoded) > MAX_REFERENCE_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "invalid_tts_request",
                "message": "reference audio is too large",
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
    statuses = getattr(manager, "_statuses", {})
    if isinstance(statuses, dict) and engine_id not in statuses:
        return
    marker = getattr(manager, "_mark_unavailable", None)
    if callable(marker):
        try:
            marker(engine_id, "engine synthesis failed")
        except Exception:
            logger.warning(
                "[rayme-tts] mark_unavailable.failed engine=%s",
                engine_id,
                exc_info=True,
            )
