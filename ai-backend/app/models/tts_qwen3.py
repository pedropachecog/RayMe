from __future__ import annotations

from app.models.tts_registry import ImportGatedTtsAdapter


class Qwen3TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "qwen3_0_6b"
    required_modules = ("qwen_tts",)
