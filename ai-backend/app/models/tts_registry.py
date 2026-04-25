from __future__ import annotations

import importlib.util
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - exercised by OMEN-PC Python 3.10 runtime.
    class StrEnum(str, Enum):
        pass


class EngineSwitchState(StrEnum):
    IDLE = "idle"
    LOADING = "loading"
    RESIDENT = "resident"
    UNAVAILABLE = "unavailable"


SWITCH_STATES = {"idle", "loading", "resident", "unavailable"}
EXPECTED_ENGINE_IDS = {
    "f5",
    "xtts_v2",
    "qwen3_0_6b",
    "luxtts",
    "chatterbox_turbo",
    "tada_1b",
}


class TtsEngineAvailability(BaseModel):
    state: EngineSwitchState = EngineSwitchState.IDLE
    available: bool = True
    unavailable_reason: str | None = None


class TtsEngineMetadata(BaseModel, frozen=True):
    id: str
    label: str
    is_default: bool = False
    code_license: str
    model_license: str
    caveat_chips: list[str] = Field(default_factory=list)
    runtime_evidence: str
    requires_transcript: bool = False
    supports_streaming: bool = False
    quality_notes: str
    availability: TtsEngineAvailability = Field(default_factory=TtsEngineAvailability)


class TtsSynthesisInput(BaseModel):
    text: str
    reference_audio: bytes
    reference_transcript: str | None = None


class TtsSynthesisOutput(BaseModel):
    engine_id: str
    wav_bytes: bytes
    sample_rate: int = 24000
    duration_ms: float | None = None


class TtsAdapterUnavailable(RuntimeError):
    pass


@runtime_checkable
class TtsAdapter(Protocol):
    engine_id: str

    def startup_self_test(self) -> None:
        ...

    def load(self) -> None:
        ...

    def unload(self) -> None:
        ...

    def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
        ...


class ImportGatedTtsAdapter:
    engine_id: str
    required_modules: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.loaded = False

    def startup_self_test(self) -> None:
        return None

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
        self._ensure_runtime_available()
        raise TtsAdapterUnavailable("TTS runtime adapter is not enabled for synthesis")

    def _ensure_runtime_available(self) -> None:
        missing = [
            module
            for module in self.required_modules
            if importlib.util.find_spec(module) is None
        ]
        if missing:
            raise TtsAdapterUnavailable("TTS runtime package unavailable")


TTS_ENGINE_METADATA: tuple[TtsEngineMetadata, ...] = (
    TtsEngineMetadata(
        id="f5",
        label="F5-TTS",
        is_default=True,
        code_license="MIT",
        model_license="CC-BY-NC",
        caveat_chips=["Default", "Requires transcript", "Non-commercial model"],
        runtime_evidence="Phase 0 TTFA 517.3 ms, RTF 0.388, 30-min soak peak 1990.2 MB on RTX 3060.",
        requires_transcript=True,
        supports_streaming=False,
        quality_notes="Default resident path; tune long-form stretch/duration before final call-feel phase.",
    ),
    TtsEngineMetadata(
        id="xtts_v2",
        label="XTTS v2",
        code_license="MPL-2.0",
        model_license="CPML",
        caveat_chips=["Transcript portable", "Native streaming", "Non-commercial model"],
        runtime_evidence="Phase 0 WSL short TTFA 489.9 ms and 30-min soak peak 2104.0 MB; scenario matrix measured native streaming inside chunk-safe paths.",
        requires_transcript=True,
        supports_streaming=True,
        quality_notes="Transcript stored for portability. Native streaming inside safe chunks; long text must honor the 400-token stream cap.",
    ),
    TtsEngineMetadata(
        id="qwen3_0_6b",
        label="Qwen3-TTS 0.6B-Base",
        code_license="Apache-2.0",
        model_license="Apache-2.0",
        caveat_chips=["Opt-in", "Latency caveat", "Accent caveat"],
        runtime_evidence="Phase 0 acceptance gate failed on TTFA/RTF/accent, but 0.6B-Base fit the RTX 3060 with 3010.0 MB soak peak.",
        requires_transcript=False,
        supports_streaming=False,
        quality_notes="0.6B-Base variant only. Opt-in path with latency and accent-quality caveats; Qwen 1.7B remains ineligible without FlashAttention 2 evidence.",
    ),
    TtsEngineMetadata(
        id="luxtts",
        label="LuxTTS",
        code_license="Research pending",
        model_license="Research pending",
        caveat_chips=["Quality caveat", "Retest references"],
        runtime_evidence="Warm scenario matrix includes very fast optimized rows; STATE records current user-sample quality failures.",
        quality_notes="Do not choose default by latency alone; retest with better reference samples before promoting.",
    ),
    TtsEngineMetadata(
        id="chatterbox_turbo",
        label="Chatterbox Turbo",
        code_license="Research pending",
        model_license="Research pending",
        caveat_chips=["Experimental", "Avoid baseline long-form"],
        runtime_evidence="Warm scenario matrix measured optimized Windows short TTFA around 840.2 ms, peak about 4667.4 MB.",
        quality_notes="Baseline long-form is gibberish; optimized long-form normal and seed 1337 samples were acceptable in listening checks.",
    ),
    TtsEngineMetadata(
        id="tada_1b",
        label="TADA 1B",
        code_license="Research pending",
        model_license="Research pending",
        caveat_chips=["Experimental", "High VRAM", "WSL caution"],
        runtime_evidence="Scenario matrix measured acceptable Windows optimized long-form and about 7.5 GB peak VRAM.",
        quality_notes="One-hot residency is mandatory because this is the highest-VRAM measured roster path; WSL remains caution.",
    ),
)


class TtsEngineRegistry:
    def __init__(
        self,
        engines: Sequence[TtsEngineMetadata | Mapping[str, object]] | None = None,
        adapters: Mapping[str, TtsAdapter] | None = None,
    ) -> None:
        self.engines = self._normalize_engines(engines or TTS_ENGINE_METADATA)
        self.adapters = dict(adapters or {})
        self._validate_full_roster()
        self._resident_engine = self.default_engine_id
        self._loading_engine: str | None = None

    @classmethod
    def default(cls) -> TtsEngineRegistry:
        return cls()

    @classmethod
    def from_defaults(cls) -> TtsEngineRegistry:
        return cls()

    @property
    def default_engine_id(self) -> str:
        defaults = [engine.id for engine in self.engines.values() if engine.is_default]
        if defaults != ["f5"]:
            raise ValueError("TTS registry requires f5 as the single default engine")
        return defaults[0]

    @property
    def resident_engine_id(self) -> str:
        return self._resident_engine

    @property
    def loading_engine(self) -> str | None:
        return self._loading_engine

    def list_engines(self) -> list[TtsEngineMetadata]:
        return list(self.engines.values())

    def get_engine(self, engine_id: str) -> TtsEngineMetadata:
        try:
            return self.engines[engine_id]
        except KeyError as exc:
            raise ValueError(f"unknown TTS engine: {engine_id}") from exc

    def mark_unavailable(self, engine_id: str, reason: str) -> None:
        engine = self.get_engine(engine_id)
        self.engines[engine_id] = engine.model_copy(
            update={
                "availability": TtsEngineAvailability(
                    state=EngineSwitchState.UNAVAILABLE,
                    available=False,
                    unavailable_reason=reason,
                )
            }
        )

    def mark_resident(self, engine_id: str) -> None:
        self.get_engine(engine_id)
        for current_id, engine in list(self.engines.items()):
            state = (
                EngineSwitchState.RESIDENT
                if current_id == engine_id
                else EngineSwitchState.IDLE
            )
            self.engines[current_id] = engine.model_copy(
                update={"availability": TtsEngineAvailability(state=state)}
            )
        self._resident_engine = engine_id
        self._loading_engine = None

    def switch_tts_engine(self, engine_id: str) -> TtsEngineMetadata:
        engine = self.get_engine(engine_id)
        if not engine.availability.available:
            raise ValueError("TTS engine unavailable")
        self._loading_engine = engine_id
        self.mark_resident(engine_id)
        return self.engines[engine_id]

    def _normalize_engines(
        self,
        engines: Iterable[TtsEngineMetadata | Mapping[str, object]],
    ) -> dict[str, TtsEngineMetadata]:
        normalized: dict[str, TtsEngineMetadata] = {}
        for engine in engines:
            metadata = (
                engine
                if isinstance(engine, TtsEngineMetadata)
                else TtsEngineMetadata.model_validate(engine)
            )
            normalized[metadata.id] = metadata
        return normalized

    def _validate_full_roster(self) -> None:
        found = set(self.engines)
        missing = sorted(EXPECTED_ENGINE_IDS - found)
        extra = sorted(found - EXPECTED_ENGINE_IDS)
        if missing:
            raise ValueError(f"TTS registry missing required engines: {', '.join(missing)}")
        if extra:
            raise ValueError(f"TTS registry has unknown engines: {', '.join(extra)}")
        _ = self.default_engine_id


def build_default_tts_adapters() -> dict[str, TtsAdapter]:
    from app.models.tts_chatterbox import ChatterboxTurboTtsAdapter
    from app.models.tts_f5 import F5TtsAdapter
    from app.models.tts_luxtts import LuxTtsAdapter
    from app.models.tts_qwen3 import Qwen3TtsAdapter
    from app.models.tts_tada import TadaTtsAdapter
    from app.models.tts_xtts import XttsV2TtsAdapter

    adapters: tuple[TtsAdapter, ...] = (
        F5TtsAdapter(),
        XttsV2TtsAdapter(),
        Qwen3TtsAdapter(),
        LuxTtsAdapter(),
        ChatterboxTurboTtsAdapter(),
        TadaTtsAdapter(),
    )
    return {adapter.engine_id: adapter for adapter in adapters}


__all__ = [
    "EXPECTED_ENGINE_IDS",
    "SWITCH_STATES",
    "EngineSwitchState",
    "ImportGatedTtsAdapter",
    "TTS_ENGINE_METADATA",
    "TtsAdapter",
    "TtsAdapterUnavailable",
    "TtsEngineAvailability",
    "TtsEngineMetadata",
    "TtsEngineRegistry",
    "TtsSynthesisInput",
    "TtsSynthesisOutput",
    "build_default_tts_adapters",
]
