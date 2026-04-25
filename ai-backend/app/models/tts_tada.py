from __future__ import annotations

from app.models.tts_registry import ImportGatedTtsAdapter


class TadaTtsAdapter(ImportGatedTtsAdapter):
    engine_id = "tada_1b"
    required_modules = ("tada_tts",)
