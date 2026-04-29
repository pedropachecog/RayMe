from __future__ import annotations

from pydantic import BaseModel, Field


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
    call_min_turn_rms: float = Field(default=25.0, ge=0.0)
    load_models_on_startup: bool = True
