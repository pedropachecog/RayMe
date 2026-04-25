from __future__ import annotations

from app.models.tts_registry import ImportGatedTtsAdapter


class LuxTtsAdapter(ImportGatedTtsAdapter):
    engine_id = "luxtts"
    required_modules = ("luxtts",)
