from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.config import AiBackendSettings
from app.models.engine_metadata import ENGINE_METADATA, EngineMetadata, EngineStatus
from app.models.tts_registry import build_default_tts_adapters


VramProbe = Callable[[], Mapping[str, int | float]]


class NullTtsAdapter:
    def __init__(self, engine_id: str) -> None:
        self.engine_id = engine_id
        self.loaded = False

    def startup_self_test(self) -> None:
        return None

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False


class ModelManager:
    def __init__(
        self,
        settings: AiBackendSettings | None = None,
        tts_adapters: Mapping[str, Any] | None = None,
        adapters: Mapping[str, Any] | None = None,
        vram_probe: VramProbe | None = None,
    ) -> None:
        self.settings = settings or AiBackendSettings()
        self.engine_metadata = {engine.id: engine for engine in ENGINE_METADATA}
        adapter_map = tts_adapters or adapters
        self.tts_adapters = dict(adapter_map or self._build_null_adapters())
        self.vram_probe: VramProbe = vram_probe or self._probe_vram
        self.loading_engine: str | None = None
        self.resident_tts_engine: str | None = None
        self._statuses = {
            engine.id: EngineStatus(id=engine.id, label=engine.label)
            for engine in ENGINE_METADATA
        }
        self._started = False
        if self.settings.default_tts_engine not in self._statuses:
            raise ValueError("default_tts_engine must match a registered engine")

    def startup(self) -> None:
        for engine_id, adapter in self.tts_adapters.items():
            if engine_id not in self._statuses:
                continue
            if getattr(adapter, "synthesis_enabled", True) is False:
                self._mark_unavailable(
                    engine_id,
                    "engine synthesis is not implemented in Phase 02",
                )
                continue
            try:
                self._run_self_test(adapter)
            except Exception:
                self._mark_unavailable(engine_id, "engine startup self-test failed")

        if self._statuses[self.settings.default_tts_engine].available:
            try:
                self.switch_tts_engine(self.settings.default_tts_engine)
            except Exception:
                self._mark_unavailable(
                    self.settings.default_tts_engine,
                    "default engine load failed",
                )
        self._started = True

    def shutdown(self) -> None:
        if self.resident_tts_engine is not None:
            self._unload_engine(self.resident_tts_engine)
        self.resident_tts_engine = None
        self.loading_engine = None
        for status in self._statuses.values():
            if status.available:
                status.resident = False
                status.state = "idle"
        self._started = False

    def switch_tts_engine(self, engine_id: str) -> EngineStatus:
        if engine_id not in self._statuses:
            raise ValueError("unknown TTS engine")
        target = self._statuses[engine_id]
        if not target.available:
            raise ValueError("TTS engine unavailable")
        if self.resident_tts_engine == engine_id:
            target.resident = True
            target.state = "resident"
            return target

        previous = self.resident_tts_engine
        self.loading_engine = engine_id
        target.state = "loading"
        if previous is not None:
            self._unload_engine(previous)
            self._statuses[previous].resident = False
            self._statuses[previous].state = "idle"

        try:
            self._load_engine(engine_id)
        except Exception:
            self.resident_tts_engine = None
            self.loading_engine = None
            self._mark_unavailable(engine_id, "engine load failed")
            raise

        target.resident = True
        target.state = "resident"
        self.resident_tts_engine = engine_id
        self.loading_engine = None
        return target

    def health(self) -> dict[str, object]:
        vram = self._safe_vram_probe()
        engine_statuses = list(self._statuses.values())
        degraded = any(not status.available for status in engine_statuses)
        status = "degraded" if degraded else "ok"
        if not self._started and self.resident_tts_engine is None:
            status = "starting"
        return {
            "service": "rayme-ai-backend",
            "status": status,
            "stt_model": self.settings.stt_model,
            "stt_compute_type": self.settings.stt_compute_type,
            "stt_language": self.settings.stt_language,
            "vad_ready": True,
            "vad_threshold": self.settings.vad_threshold,
            "vad_end_silence_ms": self.settings.vad_end_silence_ms,
            "resident_tts_engine": self.resident_tts_engine,
            "available_engines": [status.model_dump() for status in engine_statuses],
            "loading_engine": self.loading_engine,
            "vram_used_mb": vram["used_mb"],
            "vram_headroom_mb": vram["headroom_mb"],
        }

    def metadata(self) -> tuple[EngineMetadata, ...]:
        return ENGINE_METADATA

    def _build_null_adapters(self) -> dict[str, NullTtsAdapter]:
        try:
            return build_default_tts_adapters()
        except Exception:
            return {engine.id: NullTtsAdapter(engine.id) for engine in ENGINE_METADATA}

    def _run_self_test(self, adapter: Any) -> None:
        if hasattr(adapter, "startup_self_test"):
            adapter.startup_self_test()
        elif hasattr(adapter, "self_test"):
            adapter.self_test()

    def _load_engine(self, engine_id: str) -> None:
        adapter = self.tts_adapters[engine_id]
        if hasattr(adapter, "load"):
            adapter.load()

    def _unload_engine(self, engine_id: str) -> None:
        adapter = self.tts_adapters.get(engine_id)
        if adapter is not None and hasattr(adapter, "unload"):
            adapter.unload()

    def _mark_unavailable(self, engine_id: str, reason: str) -> None:
        status = self._statuses[engine_id]
        status.available = False
        status.resident = False
        status.state = "unavailable"
        status.unavailable_reason = reason

    def _safe_vram_probe(self) -> dict[str, int | float]:
        try:
            raw = dict(self.vram_probe())
        except Exception:
            raw = {}
        used_mb = raw.get("used_mb", 0)
        headroom_mb = raw.get("headroom_mb", self.settings.vram_budget_mb - used_mb)
        return {"used_mb": used_mb, "headroom_mb": headroom_mb}

    def _probe_vram(self) -> dict[str, int | float]:
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            used_mb = round(info.used / 1024 / 1024, 1)
            return {
                "used_mb": used_mb,
                "headroom_mb": max(self.settings.vram_budget_mb - used_mb, 0),
            }
        except Exception:
            return {"used_mb": 0, "headroom_mb": self.settings.vram_budget_mb}
