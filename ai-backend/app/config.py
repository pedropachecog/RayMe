from __future__ import annotations

import os
from typing import Mapping

from pydantic import BaseModel, Field, field_validator


class AiBackendSettings(BaseModel, frozen=True):
    stt_model: str = "distil-large-v3"
    stt_compute_type: str = "int8_float16"
    stt_language: str = "en"
    default_tts_engine: str = "f5"
    vram_budget_mb: int = 11000
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_end_silence_ms: int = Field(default=700, ge=0)
    vad_silero_min_silence_ms: int = Field(default=300, ge=50)
    vad_max_turn_ms: int = Field(default=30000, ge=1000)
    call_vad_end_silence_ms: int = Field(default=1800, ge=500)
    call_vad_max_turn_ms: int = Field(default=120000, ge=1000)
    call_media_reconnect_grace_ms: int = Field(default=5000, ge=0)
    call_min_turn_rms: float = Field(default=25.0, ge=0.0)
    load_models_on_startup: bool = True
    service_auth_token: str = ""

    @field_validator("service_auth_token")
    @classmethod
    def validate_service_auth_token(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and len(normalized) < 32:
            raise ValueError("RAYME_AI_BACKEND_SERVICE_TOKEN must be at least 32 characters")
        return normalized


def load_ai_backend_settings(
    environ: Mapping[str, str] | None = None,
) -> AiBackendSettings:
    source = os.environ if environ is None else environ
    default_tts_engine = (
        source.get("RAYME_TTS_DEFAULT_ENGINE", "f5").strip() or "f5"
    )
    return AiBackendSettings(
        default_tts_engine=default_tts_engine,
        service_auth_token=source.get("RAYME_AI_BACKEND_SERVICE_TOKEN", ""),
    )
