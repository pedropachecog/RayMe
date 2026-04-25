from __future__ import annotations

from app.models.tts_registry import ImportGatedTtsAdapter


class XttsV2TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "xtts_v2"
    required_modules = ("coqui_tts",)
