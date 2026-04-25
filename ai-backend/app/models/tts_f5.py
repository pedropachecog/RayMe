from __future__ import annotations

from app.models.tts_registry import ImportGatedTtsAdapter


class F5TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "f5"
    required_modules = ("f5_tts",)
