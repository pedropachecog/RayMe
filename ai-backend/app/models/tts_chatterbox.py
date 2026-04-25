from __future__ import annotations

from app.models.tts_registry import ImportGatedTtsAdapter


class ChatterboxTurboTtsAdapter(ImportGatedTtsAdapter):
    engine_id = "chatterbox_turbo"
    required_modules = ("chatterbox_tts",)
