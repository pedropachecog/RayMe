from __future__ import annotations

from app.models.tts_registry import ImportGatedTtsAdapter


REQUIRED_PACKAGE = "voxcpm==2.0.2"


class VoxCpm2TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "voxcpm2"
    required_modules = ("voxcpm",)
    synthesis_enabled = True

    def startup_self_test(self) -> None:
        self._ensure_runtime_available()
