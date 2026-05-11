# Phase 7: Add VoxCPM2 to the TTS roster with empirical quality, latency, VRAM, and call-flow evaluations - Pattern Map

**Mapped:** 2026-05-11
**Files analyzed:** 41 new/modified files or artifact families
**Analogs found:** 37 / 41

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `ai-backend/pyproject.toml` | config | batch | `ai-backend/pyproject.toml` optional `tts` extra | exact |
| `ai-backend/app/models/tts_voxcpm2.py` | model/adapter | request-response, file-I/O, transform | `ai-backend/app/models/tts_f5.py` | role-match |
| `ai-backend/app/models/tts_registry.py` | model/config | request-response | `ai-backend/app/models/tts_registry.py` | exact |
| `ai-backend/app/models/engine_metadata.py` | model/config | request-response | `ai-backend/app/models/engine_metadata.py` | exact |
| `ai-backend/app/models/model_manager.py` | service | request-response, resource lifecycle | `ai-backend/app/models/model_manager.py` | exact |
| `ai-backend/app/api/tts.py` | controller/route | request-response, file-I/O | `ai-backend/app/api/tts.py` | exact |
| `ai-backend/app/api/webrtc.py` | controller/route | request-response, event-driven | `ai-backend/app/api/webrtc.py` | exact |
| `ai-backend/app/call/session.py` | service | event-driven, streaming, file-I/O | `ai-backend/app/call/session.py` | exact |
| `ai-backend/tests/test_tts_voxcpm2.py` | test | request-response, file-I/O, transform | `ai-backend/tests/test_tts_registry.py` | role-match |
| `ai-backend/tests/test_tts_registry.py` | test | request-response | `ai-backend/tests/test_tts_registry.py` | exact |
| `ai-backend/tests/test_model_manager.py` | test | request-response, resource lifecycle | `ai-backend/tests/test_model_manager.py` | exact |
| `ai-backend/tests/test_call_session.py` | test | event-driven, streaming | `ai-backend/tests/test_call_session.py` | exact |
| `ai-backend/tests/test_webrtc_signaling.py` | test | request-response, event-driven | `ai-backend/tests/test_webrtc_signaling.py` | exact |
| `web-ui/server/app/api/voices.py` | controller/route | request-response, file-I/O | `web-ui/server/app/api/voices.py` | exact |
| `web-ui/server/app/domain/voice_service.py` | service | CRUD, file-I/O, request-response | `web-ui/server/app/domain/voice_service.py` | exact |
| `web-ui/server/app/storage/models.py` | model/store | CRUD | `web-ui/server/app/storage/models.py` | exact |
| `web-ui/server/app/domain/call_service.py` | service | event-driven, file-I/O | `web-ui/server/app/domain/call_service.py` | exact |
| `web-ui/server/app/api/calls.py` | controller/route | streaming, event-driven | `web-ui/server/app/api/calls.py` | exact |
| `web-ui/server/app/domain/ai_backend_client.py` | service | request-response | `web-ui/server/app/domain/ai_backend_client.py` | exact |
| `web-ui/server/tests/test_voices.py` | test | CRUD, file-I/O, request-response | `web-ui/server/tests/test_voices.py` | exact |
| `web-ui/server/tests/test_calls.py` | test | streaming, event-driven | `web-ui/server/tests/test_calls.py` | exact |
| `web-ui/client/src/routes/voice-lab/+page.svelte` | component/route | request-response, CRUD | `web-ui/client/src/routes/voice-lab/+page.svelte` | exact |
| `web-ui/client/src/lib/components/voice/VoxCpm2Controls.svelte` | component | transform, conditional UI | `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` | partial |
| `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` | component | request-response metadata | `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` | exact |
| `web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte` | component | CRUD, transform | `web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte` | exact |
| `web-ui/client/src/lib/api/types.ts` | utility/types | transform | `web-ui/client/src/lib/api/types.ts` | exact |
| `web-ui/client/src/lib/api/voices.ts` | utility/client | request-response | `web-ui/client/src/lib/api/voices.ts` | exact |
| `web-ui/client/tests/unit/voice-lab.test.ts` | test | request-response, static contract | `web-ui/client/tests/unit/voice-lab.test.ts` | exact |
| `web-ui/client/tests/e2e/voice-lab.spec.ts` | test | request-response, file-I/O | `web-ui/client/tests/e2e/voice-lab.spec.ts` | exact |
| `web-ui/client/tests/e2e/call-start.spec.ts` | test | event-driven | `web-ui/client/tests/e2e/call-start.spec.ts` | role-match |
| `web-ui/client/tests/e2e/settings-connection.spec.ts` | test | request-response metadata | `web-ui/client/tests/e2e/settings-connection.spec.ts` | role-match |
| `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py` | utility/probe | batch, file-I/O | `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py` | exact |
| `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py` | test | batch, transform | `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py` | exact |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/MANUAL-QUALITY.csv` | test artifact | file-I/O | `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/MANUAL-QUALITY.csv` | exact |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.{json,csv}` | test artifact | batch, file-I/O | `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/RESULT-MATRIX.csv` | exact |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/*.wav` | test artifact | file-I/O | `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py` sample output | exact |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py` | utility/probe | request-response, event-driven, file-I/O | `web-ui/server/tests/test_calls.py` + `web-ui/server/app/domain/ai_backend_client.py` | partial |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json` | test artifact | batch, file-I/O | `ai-backend/app/models/model_manager.py` health VRAM fields | partial |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-call-flow.json` | test artifact | event-driven, file-I/O | `web-ui/server/tests/test_calls.py` speak-call payload assertions | partial |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-OMEN-EVIDENCE.md` | config/test artifact | batch, operations | `scripts/deploy-omen.sh` | partial |
| `scripts/deploy-omen.sh` | config/utility | batch, operations | `scripts/deploy-omen.sh` | exact |

## Pattern Assignments

### `ai-backend/pyproject.toml` (config, batch)

**Analog:** `ai-backend/pyproject.toml`

**Optional TTS extra pattern** (lines 20-25):
```toml
[project.optional-dependencies]
tts = [
  "f5-tts==1.1.17",
  "coqui-tts==0.27.5",
  "qwen-tts==0.1.1",
]
```

Planner should add `voxcpm==2.0.2` here, not to always-installed dependencies.

### `ai-backend/app/models/tts_voxcpm2.py` (model/adapter, request-response + file-I/O)

**Analog:** `ai-backend/app/models/tts_f5.py`

**Imports and contract pattern** (lines 1-20):
```python
from __future__ import annotations

import tempfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.models.tts_registry import (
    ImportGatedTtsAdapter,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)
from app.models.gpu_runtime import require_torch_cuda_runtime
```

**Adapter load and CUDA guard pattern** (lines 23-39):
```python
class F5TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "f5"
    required_modules = ("f5_tts",)
    synthesis_enabled = True

    def __init__(self, runtime_factory: Callable[[], Any] | None = None) -> None:
        super().__init__()
        self._runtime_factory = runtime_factory
        self._runtime: Any | None = None

    def load(self) -> None:
        self._ensure_runtime_available()
        if self._runtime_factory is None:
            require_torch_cuda_runtime("F5-TTS")
        if self._runtime is None:
            self._runtime = self._build_runtime()
        self.loaded = True
```

**Temp reference file and WAV output pattern** (lines 45-78):
```python
def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
    if not self.loaded:
        self.load()
    runtime = self._runtime or self._build_runtime()
    self._runtime = runtime
    reference_transcript = (request.reference_transcript or "").strip()
    if not reference_transcript:
        raise ValueError("F5 synthesis requires a reference transcript")

    with tempfile.TemporaryDirectory(prefix="rayme-f5-") as tmp_dir:
        reference_path = Path(tmp_dir) / f"reference{_audio_suffix(request.reference_audio_content_type)}"
        reference_path.write_bytes(request.reference_audio)
        wav, sample_rate, _ = runtime.infer(
            str(reference_path),
            reference_transcript,
            request.text,
            show_info=lambda *_args, **_kwargs: None,
            progress=None,
            nfe_step=7,
            speed=request.speech_speed,
        )

    wav_array = np.asarray(wav, dtype=np.float32).flatten()
    if wav_array.size == 0:
        raise ValueError("F5 synthesis returned empty audio")
    buffer = BytesIO()
    sf.write(buffer, wav_array, int(sample_rate), format="WAV")
    wav_bytes = buffer.getvalue()
    return TtsSynthesisOutput(
        engine_id=self.engine_id,
        wav_bytes=wav_bytes,
        sample_rate=int(sample_rate),
        duration_ms=round((wav_array.size / float(sample_rate)) * 1000, 1),
    )
```

**CUDA-only helper to copy** (source `ai-backend/app/models/gpu_runtime.py`, lines 38-68):
```python
def require_torch_cuda_runtime(component: str) -> GpuRuntimeInfo:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - depends on deployment image
        raise GpuRuntimeError(f"{component} requires PyTorch with CUDA support.") from exc

    version = str(getattr(torch, "__version__", "unknown"))
    torch_version = getattr(torch, "version", None)
    cuda_version = str(getattr(torch_version, "cuda", "") or "")
    cuda_api = getattr(torch, "cuda", None)
    cuda_available = bool(cuda_api and cuda_api.is_available())

    if "+cpu" in version.lower() or not cuda_version or not cuda_available:
        raise GpuRuntimeError(
            f"{component} requires a CUDA-enabled PyTorch runtime; "
            f"torch={version}, torch_cuda={cuda_version or 'none'}, "
            f"cuda_available={cuda_available}."
        )
```

For VoxCPM2, copy this shape but use `required_modules = ("voxcpm",)`, force `device="cuda"` when building the runtime, write reference bytes to a temp file, and return the actual VoxCPM2 sample rate instead of hard-coding 24000.

### `ai-backend/app/models/tts_registry.py` (model/config, request-response)

**Analog:** `ai-backend/app/models/tts_registry.py`

**Synthesis contract to extend with bounded engine options** (lines 55-67):
```python
class TtsSynthesisInput(BaseModel):
    text: str
    reference_audio: bytes
    reference_audio_content_type: str | None = None
    reference_transcript: str | None = None
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)

class TtsSynthesisOutput(BaseModel):
    engine_id: str
    wav_bytes: bytes
    sample_rate: int = 24000
    duration_ms: float | None = None
```

**Import-gated optional runtime pattern** (lines 91-120):
```python
class ImportGatedTtsAdapter:
    engine_id: str
    required_modules: tuple[str, ...] = ()
    synthesis_enabled = False

    def __init__(self) -> None:
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
```

**Full roster metadata pattern** (lines 122-184):
```python
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
    ...
)
```

**Roster validation and adapter builder pattern** (lines 279-306):
```python
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
```

Update `EXPECTED_ENGINE_IDS`, `TTS_ENGINE_METADATA`, `build_default_tts_adapters()`, and `__all__` together.

### `ai-backend/app/models/engine_metadata.py` and `model_manager.py` (model/service, resource lifecycle)

**Analogs:** `ai-backend/app/models/engine_metadata.py`, `ai-backend/app/models/model_manager.py`

**Health metadata mirror pattern** (source `engine_metadata.py`, lines 26-33):
```python
ENGINE_METADATA: tuple[EngineMetadata, ...] = (
    EngineMetadata(id="f5", label="F5-TTS", default=True),
    EngineMetadata(id="xtts_v2", label="XTTS v2"),
    EngineMetadata(id="qwen3_0_6b", label="Qwen3-TTS 0.6B-Base", caveats=["opt-in"]),
    EngineMetadata(id="luxtts", label="LuxTTS", caveats=["quality caveat"]),
    EngineMetadata(id="chatterbox_turbo", label="Chatterbox Turbo", caveats=["experimental"]),
    EngineMetadata(id="tada_1b", label="TADA 1B", caveats=["experimental"]),
)
```

**One-hot resident engine and engine-scoped failure pattern** (source `model_manager.py`, lines 96-127):
```python
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
```

**Health payload and VRAM pattern** (source `model_manager.py`, lines 129-151):
```python
return {
    "service": "rayme-ai-backend",
    "status": status,
    "stt_model": self.settings.stt_model,
    "stt_compute_type": self.settings.stt_compute_type,
    "stt_language": self.settings.stt_language,
    "stt_ready": self.stt_ready,
    "vad_ready": True,
    "vad_threshold": self.settings.vad_threshold,
    "vad_end_silence_ms": self.settings.vad_end_silence_ms,
    "resident_tts_engine": self.resident_tts_engine,
    "available_engines": [status.model_dump() for status in engine_statuses],
    "loading_engine": self.loading_engine,
    "vram_used_mb": vram["used_mb"],
    "vram_headroom_mb": vram["headroom_mb"],
}
```

### `ai-backend/app/api/tts.py` (controller/route, request-response)

**Analog:** `ai-backend/app/api/tts.py`

**Validated request payload pattern** (lines 16-30):
```python
class TtsSynthesizeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str | None = Field(default=None, max_length=64)
    text: str = Field(min_length=1, max_length=5000)
    reference_audio_b64: str = Field(
        min_length=1,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)
    use_default_engine: bool = False
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)
```

**Route switch, synthesize, fixed public error pattern** (lines 32-72):
```python
@router.post("/tts/synthesize")
def synthesize(request: Request, payload: TtsSynthesizeRequest) -> dict[str, Any]:
    target_engine = _target_engine(request, payload)
    reference_audio = _decode_reference_audio(payload.reference_audio_b64)
    manager = _manager_from_app(request)

    try:
        manager.switch_tts_engine(target_engine)
        adapter = manager.tts_adapters[target_engine]
        result = adapter.synthesize(
            TtsSynthesisInput(
                text=payload.text,
                reference_audio=reference_audio,
                reference_audio_content_type=payload.reference_audio_content_type,
                reference_transcript=payload.reference_transcript,
                speech_speed=payload.speech_speed,
            )
        )
        if not result.wav_bytes:
            raise ValueError("synthesis returned empty audio")
    except HTTPException:
        raise
    except Exception as exc:
        _mark_engine_unavailable(manager, target_engine)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "tts_failed",
                "message": "Synthesis failed",
                "engine_id": target_engine,
            },
        ) from exc
```

Add VoxCPM2 options as bounded fields and pass them through `TtsSynthesisInput`; do not expose raw VoxCPM exceptions.

### `ai-backend/app/api/webrtc.py` and `ai-backend/app/call/session.py` (route/service, event-driven)

**Analogs:** `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`

**Speak request shape to extend** (source `webrtc.py`, lines 69-83):
```python
class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    turn_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=5000)
    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str = Field(min_length=1, max_length=64)
    final_chunk: bool = False
    reference_audio_b64: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)
```

**Speak route forwarding and fixed error pattern** (source `webrtc.py`, lines 272-335):
```python
@router.post("/sessions/{session_id}/speak")
async def speak_session(
    request: Request,
    session_id: str,
    payload: SpeakRequest,
) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    try:
        adapter = _tts_adapter(request, payload.engine_id)
        event = await session.speak_text(
            payload.turn_id,
            payload.text,
            payload.voice_id,
            payload.engine_id,
            final_chunk=payload.final_chunk,
            tts_adapter=adapter,
            reference_audio_b64=payload.reference_audio_b64,
            reference_transcript=payload.reference_transcript,
            reference_audio_content_type=payload.reference_audio_content_type,
        )
    except asyncio.CancelledError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "call_tts_failed",
                "message": "Speech playback cancelled",
                "engine_id": payload.engine_id,
            },
        )
```

**Call speech enqueue and recovery pattern** (source `session.py`, lines 726-835):
```python
async def speak_text(
    self,
    turn_id: str,
    text: str,
    voice_id: str,
    engine_id: str,
    final_chunk: bool = False,
    *,
    tts_adapter: Any | None = None,
    reference_audio_b64: str | None = None,
    reference_transcript: str | None = None,
    reference_audio_content_type: str | None = None,
) -> dict[str, Any]:
    ...
    result = await self._synthesize_speech(
        turn_id=turn_id,
        text=text,
        voice_id=voice_id,
        engine_id=engine_id,
        tts_adapter=tts_adapter,
        reference_audio_b64=reference_audio_b64,
        reference_transcript=reference_transcript,
        reference_audio_content_type=reference_audio_content_type,
    )
    ...
    if wav_bytes:
        audio_stats = audio_stats_for_wav_bytes(
            wav_bytes,
            target_sample_rate=int(getattr(self.outbound_audio_track, "sample_rate", 48000)),
        )
        playback_seconds = await self._queue_outbound_audio(
            wav_bytes,
            preroll_seconds=CALL_TTS_AUDIO_PREROLL_SECONDS,
        )
        self.state = "speaking"
        audio_started_event = simple_event(
            AI_AUDIO_STARTED_EVENT,
            session_id=self.session_id,
            turn_id=turn_id,
            voice_id=voice_id,
            engine_id=engine_id,
            audio=audio_stats,
        )
```

**Generic adapter bridge pattern** (source `session.py`, lines 1392-1510):
```python
async def _synthesize_speech(...):
    adapter = tts_adapter or self.tts_adapter
    if adapter is None:
        return {"wav_bytes": b"", "sample_rate": 24000, "duration_ms": 0}

    is_async = self._is_tts_method_async(adapter, reference_audio_b64)
    if is_async:
        result = await self._do_async_synthesis(...)
    else:
        result = await asyncio.to_thread(self._run_sync_synthesis, ...)
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    return dict(result)

def _run_sync_synthesis(...):
    if not reference_audio_b64:
        raise ValueError("call TTS reference audio is required")
    result = adapter.synthesize(
        TtsSynthesisInput(
            text=text,
            reference_audio=base64.b64decode(reference_audio_b64, validate=True),
            reference_transcript=reference_transcript,
            reference_audio_content_type=reference_audio_content_type,
            speech_speed=1.0,
        )
    )
```

Thread VoxCPM2 settings through this path without changing the public `/webrtc/.../speak` route shape beyond bounded request fields.

### Web UI Server Voice and Call Files

**Files:** `web-ui/server/app/api/voices.py`, `domain/voice_service.py`, `storage/models.py`, `domain/call_service.py`, `api/calls.py`, `domain/ai_backend_client.py`

**Voice API schema pattern** (source `voices.py`, lines 31-69):
```python
class VoiceSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    default_engine: str = Field(min_length=1, max_length=80)
    reference_transcript: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class VoicePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ...
    use_default_engine: bool = True
    engine: str | None = Field(default=None, max_length=80)
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)
```

**AI backend synthesis payload bridge** (source `voices.py`, lines 301-316):
```python
def _synthesis_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content")
    audio_base64 = base64.b64encode(content).decode("ascii") if isinstance(content, bytes) else None
    engine_id = payload.get("engine") or payload.get("default_engine")
    return {
        "kind": kind,
        "text": payload.get("text") or payload.get("preview_text") or "",
        "engine_id": engine_id,
        "use_default_engine": payload.get("use_default_engine", True),
        "reference_transcript": payload.get("reference_transcript"),
        "reference_audio_base64": audio_base64,
        "reference_audio_content_type": payload.get("content_type"),
        "voice_id": payload.get("voice_id") or payload.get("asset_id"),
        "asset_id": payload.get("asset_id"),
        "speech_speed": payload.get("speech_speed", 1.0),
    }
```

**Durable metadata storage pattern** (source `voice_service.py`, lines 118-135):
```python
async def save_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
    asset = await self.get_asset(str(payload["asset_id"]))
    metadata = dict(payload.get("metadata") or {})
    metadata["sample_asset_id"] = asset.id
    voice = Voice(
        id=new_voice_id(),
        name=str(payload["name"]),
        default_engine=str(payload["default_engine"]),
        reference_transcript=payload.get("reference_transcript"),
        metadata_json=metadata,
        deleted_at=None,
    )
    asset.voice_id = voice.id
```

**Test-play uses saved metadata and transcript pattern** (source `voice_service.py`, lines 172-199):
```python
engine = voice.default_engine if payload.get("use_default_engine", True) else payload.get("engine")
result = await self.processor.test_play(
    voice_id=voice.id,
    text=payload.get("text", ""),
    engine=engine,
    reference_transcript=voice.reference_transcript,
    content=sample.path.read_bytes(),
    content_type=asset.content_type,
    speech_speed=payload.get("speech_speed", _voice_speech_speed(voice)),
)
```

**Storage model pattern for voice-level settings** (source `storage/models.py`, lines 184-192):
```python
class Voice(TimestampMixin, Base):
    __tablename__ = VOICES_TABLE

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_engine: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**Per-engine metadata lookup pattern** (source `voice_service.py`, lines 297-311):
```python
def _voice_speech_speed(voice: Voice) -> float:
    metadata = dict(voice.metadata_json or {})
    value = metadata.get("speech_speed")
    if isinstance(value, int | float):
        return float(value)

    engine_settings = metadata.get("engine_settings")
    if isinstance(engine_settings, dict):
        engine_value = engine_settings.get(voice.default_engine)
        if isinstance(engine_value, dict):
            speed = engine_value.get("speech_speed")
            if isinstance(speed, int | float):
                return float(speed)
```

Use the same `metadata_json.engine_settings[engine_id]` pattern for VoxCPM2 cloning mode and style controls.

**Call voice reference forwarding pattern** (source `call_service.py`, lines 213-259):
```python
async def voice_reference_for_call(self, call_id: str, voice_blob_dir: Path) -> dict[str, Any]:
    call = self._active_call(call_id)
    voice = await self._required_available_voice(call.voice_id)
    ...
    return {
        "reference_audio_base64": base64.b64encode(sample_path.read_bytes()).decode("ascii"),
        "reference_audio_content_type": asset.content_type,
        "reference_transcript": voice.reference_transcript,
    }
```

**Call turn to AI backend speak pattern** (source `api/calls.py`, lines 422-435):
```python
tts_task = asyncio.create_task(
    _speak_call(
        backend,
        endpoint_settings.ai_backend_url,
        session_id,
        {
            "turn_id": payload.turn_id,
            "text": visible_text,
            "voice_id": call["voice_id"],
            "engine_id": call["engine_id"],
            "final_chunk": True,
            **voice_reference,
        },
    ),
)
```

**HTTP client one-public-API pattern** (source `ai_backend_client.py`, lines 134-147 and 201-218):
```python
async def synthesize(self, base_url: str, payload: Mapping[str, Any]) -> SynthesisResult:
    response = await self._request(
        "POST",
        _join_endpoint(base_url, "/tts/synthesize"),
        json=dict(payload),
        processing_message=SYNTHESIS_FAILED_MESSAGE,
        processing_code="synthesis_failed",
        timeout=self._synthesis_timeout,
    )

async def speak_call(self, base_url: str, session_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    response = await self._request(
        "POST",
        _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/speak"),
        json=dict(payload),
        processing_message=WEBRTC_FAILED_MESSAGE,
        processing_code="call_tts_failed",
        timeout=self._synthesis_timeout,
    )
```

### Client Voice Lab, Controls, Picker, Types

**Files:** `+page.svelte`, `VoxCpm2Controls.svelte`, `TtsEnginePicker.svelte`, `VoiceAssignmentSelect.svelte`, `types.ts`, `voices.ts`

**Fallback roster pattern** (source `+page.svelte`, lines 33-93):
```typescript
const DEFAULT_TTS_ENGINES: TtsEngineMetadata[] = [
  {
    id: 'f5',
    label: 'F5-TTS',
    is_default: true,
    caveat_chips: ['Default', 'Requires transcript'],
    requires_transcript: true,
    availability: { available: true, state: 'resident' }
  },
  ...
];
```

**Backend metadata normalization pattern** (source `+page.svelte`, lines 141-190):
```typescript
async function loadEngineMetadata() {
  try {
    const settings = await getSettings();
    engines = normalizeEngines(settings.ai_backend_status?.available_engines);
    selectedEngine = settings.tts_default_engine || engines.find((engine) => engine.is_default)?.id || 'f5';
  } catch {
    engines = DEFAULT_TTS_ENGINES;
  }
}

function normalizeEngines(value: unknown): TtsEngineMetadata[] {
  if (!Array.isArray(value) || value.length === 0) {
    return DEFAULT_TTS_ENGINES;
  }
  const byId = new Map(DEFAULT_TTS_ENGINES.map((engine) => [engine.id, engine]));
  ...
  return DEFAULT_TTS_ENGINES.map((engine) => byId.get(engine.id) ?? engine);
}
```

**Preview and save payload patterns** (source `+page.svelte`, lines 248-294):
```typescript
const result: VoiceSynthesisResult = await previewVoice({
  asset_id: asset.asset_id,
  name: voiceName.trim(),
  default_engine: selectedEngine,
  reference_transcript: transcript.trim(),
  preview_text: previewText,
  use_default_engine: useDefaultEngine,
  engine: useDefaultEngine ? null : selectedEngine,
  speech_speed: speechSpeed
});

await saveVoice({
  asset_id: asset.asset_id,
  name: voiceName.trim(),
  default_engine: selectedEngine,
  reference_transcript: transcript.trim(),
  metadata: {
    source: 'voice-lab',
    sample_filename: selectedFile?.name ?? null,
    speech_speed: speechSpeed,
    engine_settings: {
      [selectedEngine]: {
        speech_speed: speechSpeed
      }
    }
  }
});
```

**Conditional UI insertion point** (source `+page.svelte`, lines 472-491):
```svelte
<TtsEnginePicker bind:selectedEngine {engines} />

<SynthPreviewPanel
  bind:previewText
  bind:useDefaultEngine
  bind:speechSpeed
  disabled={!canPreview}
  state={previewState}
  audioUrl={previewAudioUrl}
  errorMessage={previewError}
  onPreview={previewCurrentVoice}
/>
```

Put `VoxCpm2Controls.svelte` between picker and preview and render it only when `selectedEngine === 'voxcpm2'`.

**Picker caveat and unavailable rendering pattern** (source `TtsEnginePicker.svelte`, lines 7-22 and 31-59):
```svelte
const fallbackCaveats: Record<string, string[]> = {
  f5: ['Default', 'Requires transcript'],
  xtts_v2: ['No transcript required', 'Streaming capable'],
  qwen3_0_6b: ['Opt-in', 'Latency caveat', 'Accent caveat'],
  luxtts: ['Quality caveat', 'Retest references'],
  chatterbox_turbo: ['Experimental', 'Avoid baseline long-form'],
  tada_1b: ['Experimental', 'High VRAM', 'WSL caution']
};

{#each engines as engine (engine.id)}
  {@const available = engine.availability?.available !== false}
  <label class:selected={selectedEngine === engine.id} class:unavailable={!available}>
    ...
    {#if !available}
      {engine.availability?.unavailable_reason || 'This engine is not available in the current runtime.'}
    {:else if engine.requires_transcript}
      Transcript required for this voice clone path.
    {:else}
      Reference transcript not required for this engine.
    {/if}
```

**Voice assignment label fallback pattern** (source `VoiceAssignmentSelect.svelte`, lines 20-37):
```typescript
function engineLabel(engine: TtsEngineId | null | undefined): string {
  switch (engine) {
    case 'f5':
      return 'F5-TTS';
    case 'xtts_v2':
      return 'XTTS v2';
    case 'qwen3_0_6b':
      return 'Qwen3-TTS 0.6B-Base';
    case 'luxtts':
      return 'LuxTTS';
    case 'chatterbox_turbo':
      return 'Chatterbox Turbo';
    case 'tada_1b':
      return 'TADA 1B';
    default:
      return engine ? String(engine) : 'Unknown engine';
  }
}
```

**Types and API wrapper pattern** (source `types.ts`, lines 362-463; `voices.ts`, lines 35-46 and 92-99):
```typescript
export type TtsEngineId =
  | 'f5'
  | 'xtts_v2'
  | 'qwen3_0_6b'
  | 'luxtts'
  | 'chatterbox_turbo'
  | 'tada_1b'
  | (string & {});

export interface VoicePreviewPayload {
  asset_id: string;
  name?: string | null;
  default_engine?: TtsEngineId | null;
  reference_transcript?: string | null;
  preview_text?: string | null;
  use_default_engine?: boolean;
  engine?: TtsEngineId | null;
  speech_speed?: number;
}

export function previewVoice(payload: VoicePreviewPayload): Promise<VoiceSynthesisResult> {
  return apiFetch<VoiceSynthesisResult>('/voices/preview', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}
```

Add typed VoxCPM2 option payload fields in `types.ts` and route them through existing `previewVoice`, `saveVoice`, and `testPlayVoice`.

### Backend and Server Test Patterns

**Backend registry/route tests:** `ai-backend/tests/test_tts_registry.py`

**Full roster constants pattern** (lines 18-55):
```python
EXPECTED_ENGINE_LABELS = {
    "f5": "F5-TTS",
    "xtts_v2": "XTTS v2",
    "qwen3_0_6b": "Qwen3-TTS 0.6B-Base",
    "luxtts": "LuxTTS",
    "chatterbox_turbo": "Chatterbox Turbo",
    "tada_1b": "TADA 1B",
}
ENGINE_REQUIREMENTS = {
    "f5": {
        "model_license": "CC-BY-NC",
        "requires_transcript": True,
        "supports_streaming": False,
    },
    ...
}
```

**Synthesize route contract and sanitized error pattern** (lines 251-337):
```python
def _synthesis_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "voice_id": "voice_test",
        "engine_id": "xtts_v2",
        "text": "Hello from RayMe.",
        "reference_audio_b64": base64.b64encode(b"reference wav").decode("ascii"),
        "reference_transcript": "Reference transcript.",
        "use_default_engine": False,
    }
    payload.update(overrides)
    return payload

def test_tts_synthesize_failure_returns_fixed_public_error() -> None:
    ...
    assert response.json()["detail"] == {
        "code": "tts_failed",
        "message": "Synthesis failed",
        "engine_id": "xtts_v2",
    }
    assert "Traceback" not in rendered
    assert "CUDA out of memory" not in rendered
```

**Adapter unit test pattern** (lines 340-375):
```python
class ScriptedF5Runtime:
    def infer(self, ref_file: str, ref_text: str, gen_text: str, **_: Any) -> tuple[Any, int, None]:
        self.calls.append((ref_file, ref_text, gen_text, _))
        sample_rate = 24_000
        t = np.linspace(0, 0.05, int(sample_rate * 0.05), endpoint=False)
        return (0.1 * np.sin(2 * math.pi * 440 * t), sample_rate, None)

runtime = ScriptedF5Runtime()
adapter = F5TtsAdapter(runtime_factory=lambda: runtime)
result = adapter.synthesize(
    TtsSynthesisInput(
        text="Generated RayMe audio.",
        reference_audio=b"scripted-reference-wav",
        reference_transcript="Reference transcript.",
        speech_speed=0.75,
    )
)
```

**Model manager failure isolation pattern** (source `test_model_manager.py`, lines 227-260):
```python
def test_failed_engine_self_test_degrades_only_that_engine_with_typed_reason() -> None:
    manager, _, _ = _build_manager(failing_engine="xtts_v2")
    _complete(manager.startup())
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["status"] == "degraded"
    assert health["resident_tts_engine"] == "f5"
    assert statuses["xtts_v2"]["available"] is False
    assert statuses["f5"]["available"] is True
    _assert_no_raw_exception_text(statuses["xtts_v2"]["unavailable_reason"])
```

**Call session generic adapter pattern** (source `test_call_session.py`, lines 1125-1143):
```python
def test_speak_text_generic_adapter_uses_real_reference_audio() -> None:
    adapter = ScriptedGenericTtsAdapter()
    session, _ = _new_session(tts_adapter=adapter)

    _run(
        session.speak_text(
            "ai-turn-reference",
            "Hello from AI.",
            "voice-1",
            "f5",
            final_chunk=True,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="Real reference text.",
            reference_audio_content_type="audio/wav",
        )
    )

    assert adapter.reference_audio == b"real-sample"
```

**WebRTC speak route test pattern** (source `test_webrtc_signaling.py`, lines 272-327):
```python
response = client.post(
    SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
    json={
        "turn_id": "ai-turn-1",
        "text": "Hello from AI.",
        "voice_id": "voice-1",
        "engine_id": "f5",
        "final_chunk": True,
    },
)

assert response.status_code == 200
assert manager.switch_calls == ["f5"]
assert payload["event"]["type"] == "ai_done"
```

**Server voice tests for roster and metadata** (source `web-ui/server/tests/test_voices.py`, lines 25-32 and 259-327):
```python
SUPPORTED_TTS_ENGINES = (
    "F5-TTS",
    "XTTS v2",
    "Qwen3-TTS 0.6B-Base",
    "LuxTTS",
    "Chatterbox Turbo",
    "TADA 1B",
)

for engine_name in SUPPORTED_TTS_ENGINES:
    uploaded = _upload_voice_asset(client, _wav_audio(f"{engine_name}.wav"))
    response = client.post(
        "/api/voices",
        json=_voice_payload(
            asset_id=asset_id,
            name=f"{engine_name} reference voice",
            default_engine=engine_name,
            reference_transcript=f"Editable transcript for {engine_name}.",
        ),
    )
```

**Server AI backend bridge test pattern** (source `test_voices.py`, lines 491-537):
```python
def handler(request: httpx.Request) -> httpx.Response:
    requests.append(request)
    if request.url.path == "/base/tts/synthesize":
        payload = json.loads(request.content)
        assert payload["voice_id"] == "voice_asset_preview_test"
        assert payload["asset_id"] == "voice_asset_preview_test"
        assert payload["speech_speed"] == 0.75
        assert payload["reference_audio_base64"]
        return httpx.Response(200, json={...})
```

**Server call forwarding test pattern** (source `web-ui/server/tests/test_calls.py`, lines 575-584):
```python
assert [call["payload"]["text"] for call in call_fixture.backend.speak_calls] == [
    "First AI answer.",
    "Second AI answer.",
]
assert all(call["payload"]["reference_audio_base64"] for call in call_fixture.backend.speak_calls)
assert all(
    call["payload"]["reference_transcript"] == "Reference transcript for the assigned voice."
    for call in call_fixture.backend.speak_calls
)
```

### Client Test Patterns

**Unit static/API wrapper pattern** (source `web-ui/client/tests/unit/voice-lab.test.ts`, lines 16-33 and 114-130):
```typescript
const sourceFiles = [
  'src/routes/voice-lab/+page.svelte',
  'src/lib/components/voice/AudioSampleDropzone.svelte',
  'src/lib/components/voice/TranscriptEditor.svelte',
  'src/lib/components/voice/TtsEnginePicker.svelte',
  'src/lib/components/voice/SynthPreviewPanel.svelte',
  'src/lib/components/voice/VoiceLibraryList.svelte',
  'src/lib/api/voices.ts',
  'src/lib/api/types.ts'
];

await previewVoice({
  asset_id: 'asset 1',
  name: 'Aster',
  default_engine: 'f5',
  reference_transcript: 'Reference text',
  preview_text: 'Preview this voice.',
  use_default_engine: false,
  engine: 'xtts_v2',
  speech_speed: 0.75
});
```

**Client roster/metadata assertions** (source `voice-lab.test.ts`, lines 246-256):
```typescript
it('exposes the full six-engine roster from metadata-driven picker sources', () => {
  for (const label of engineLabels) {
    expect(voiceLabSources).toContain(label);
  }

  for (const metadataTerm of ['caveat', 'caveats', 'metadata', 'default_engine']) {
    expect(voiceLabSources).toMatch(new RegExp(metadataTerm, 'i'));
  }
});
```

**Voice Lab E2E payload pattern** (source `voice-lab.spec.ts`, lines 391-410 and 456-468):
```typescript
await page.route('**/api/voices/preview', async (route) => {
  expect(route.request().method()).toBe('POST');
  const expectedPayload = {
    asset_id: 'sample-asset',
    reference_transcript: editedTranscript,
    default_engine: 'f5',
    use_default_engine: true,
    preview_text: previewText,
    speech_speed: 0.75
  };
});

await page.route('**/api/voices/voice-a/test-play', async (route) => {
  expect(route.request().postDataJSON()).toMatchObject({
    text: 'Read this library test phrase.',
    use_default_engine: true,
    speech_speed: 0.75
  });
});
```

**Call/settings fallback analogs** (source `call-start.spec.ts`, lines 782-790; `settings-connection.spec.ts`, lines 63-70):
```typescript
default_voice: {
  id: 'voice-call-start',
  name: 'Call Start Voice',
  default_engine: 'f5',
  reference_transcript: 'Reference text.',
  sample_asset_id: 'asset-call-start',
  preview_audio_url: null,
  metadata: {},
}

ai_backend_status: {
  endpoint_status: 'Connected',
  stt_model: 'distil-large-v3',
  vad_ready: true,
  resident_tts_engine: 'f5',
  available_engines: ['f5', 'xtts_v2', 'qwen3_0_6b'],
}
```

### Scenario Matrix and Evidence Artifacts

**Files:** `tts_scenario_matrix.py`, `test_tts_scenario_matrix.py`, Phase 7 results JSON/CSV/WAV files, `MANUAL-QUALITY.csv`

**Engine and scenario constants to extend** (source `tts_scenario_matrix.py`, lines 34-61 and 104-120):
```python
ENGINE_ORDER = ("f5", "xtts", "luxtts", "chatterbox_turbo", "tada_1b", "qwen3")
PROFILE_ORDER = ("baseline", "optimized", "optimized_seed_1337")
RESULT_PATH = PHASE_DIR / "results" / "tts_scenario_matrix_local.json"
OUTPUT_SAMPLE_DIR = PHASE_DIR / "results" / "tts_scenario_audio"

ENGINE_CHUNK_LIMITS = {
    "f5": {"max_estimated_tokens": 260, "max_chars": 520, "min_words": 8, "first_words": 28},
    ...
}

def scenario_specs() -> list[ScenarioSpec]:
    return [
        ScenarioSpec(name="short_reply", text=SHORT_REPLY_TEXT, description="One concise assistant reply."),
        ScenarioSpec(name="medium_reply", text=MEDIUM_REPLY_TEXT, description="A practical multi-sentence assistant answer."),
        ScenarioSpec(name="long_reply", text=_read_target_text(LONG_REPLY_FIXTURE), description="Long-form assistant narration from the Phase 0 fixture."),
    ]
```

**Shared chunk planner and playback metadata pattern** (source `tts_scenario_matrix.py`, lines 240-358):
```python
def build_chunk_plan(engine: str, text: str) -> ChunkPlan:
    limits = ENGINE_CHUNK_LIMITS.get(engine, ENGINE_CHUNK_LIMITS["f5"])
    ...
    return ChunkPlan(
        engine=engine,
        chunks=merged or [" ".join(text.strip().split())],
        max_estimated_tokens=max_estimated_tokens,
        max_chars=max_chars,
        strategy="sentence_boundary_token_cap_v1",
    )

def _chunk_playback_metadata(...):
    ...
    metadata.update(
        {
            "chunk_generate_ttfa_ms": [_round_or_none(value) for value in chunk_ttfa_ms],
            "chunk_generate_total_ms": [_round_or_none(value) for value in chunk_total_ms],
            "chunk_audio_duration_s": [_round_or_none(value, 3) for value in chunk_audio_duration_s],
            "chunk_audio_ready_offsets_ms": [_round_or_none(value) for value in ready_offsets],
            "inter_chunk_gap_ms": [_round_or_none(value) for value in inter_chunk_gaps],
            "max_inter_chunk_gap_ms": _round_or_none(max(inter_chunk_gaps) if inter_chunk_gaps else 0.0),
            "stitched_playback_ms": _round_or_none(playback_end_ms),
        }
    )
```

**Result row schema** (source `tts_scenario_matrix.py`, lines 402-480):
```python
row = {
    "engine": engine,
    "runtime": runtime,
    "host_account": host_account,
    "profile": profile,
    "scenario": scenario.name,
    "scenario_description": scenario.description,
    "scenario_word_count": scenario.word_count,
    "backend": backend,
    "mode": mode,
    "streaming_support": streaming_support,
    "true_streaming": true_streaming,
    "status": status,
    "request_ttfa_ms": _round_or_none(request_ttfa_ms),
    "request_total_ms": _round_or_none(request_total_ms),
    "peak_vram_mb": _round_or_none(peak_vram_mb),
    "sample_rate": sample_rate,
    "output_wav": str(output_wav) if output_wav else None,
    "optimizations_applied": optimizations_applied,
    "optimization_notes": optimization_notes,
}
```

**Audio sample artifact pattern** (source `tts_scenario_matrix.py`, lines 398-403 and 599-603):
```python
def _sample_path(sample_root: Path, engine: str, profile: str, scenario: str) -> Path:
    return sample_root / f"{engine}__{profile}__{scenario}.wav"

def _write_audio_sample(sample_out: Path, sample: Any, sample_rate: int) -> None:
    import soundfile as sf
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, _to_float_np(sample), int(sample_rate))
```

**Matrix output and CLI pattern** (source `tts_scenario_matrix.py`, lines 1981-2058):
```python
document = {
    "probe": "tts_scenario_matrix",
    "runtime": runtime,
    "host_account": host_account,
    "ref_audio": str(ref_audio),
    "ref_text": str(ref_text_path),
    "engines": engines,
    "profiles": list(PROFILE_ORDER),
    "scenarios": [...],
    "rows": rows,
    "summary": build_summary(rows),
    "engine_payloads": engine_payloads,
}
write_results(output, document)

parser.add_argument("--ref-audio", required=True)
parser.add_argument("--ref-text", required=True)
parser.add_argument("--output", default=str(RESULT_PATH))
parser.add_argument("--sample-root", default=str(OUTPUT_SAMPLE_DIR))
parser.add_argument("--engines", nargs="*", choices=ENGINE_ORDER, default=list(ENGINE_ORDER))
```

**Probe tests to copy** (source `test_tts_scenario_matrix.py`, lines 14-49 and 176-191):
```python
def test_build_result_row_excludes_model_load_from_request_metrics() -> None:
    scenario = ScenarioSpec(name="short_reply", text="Short test reply.", description="Short reply")
    row = build_result_row(
        engine="luxtts",
        runtime="windows_native",
        profile="optimized",
        generate_ttfa_ms=320.0,
        generate_total_ms=320.0,
        audio_duration_s=1.6,
        peak_vram_mb=900.0,
        sample_rate=48000,
        ...
    )
    assert row["request_ttfa_ms"] == 320.0

def test_chunk_playback_metadata_tracks_hidden_generation_and_gaps() -> None:
    metadata = _chunk_playback_metadata(
        plan=plan,
        chunk_ttfa_ms=[200.0, 500.0],
        chunk_total_ms=[400.0, 900.0],
        chunk_audio_duration_s=[1.2, 0.8],
    )
    assert metadata["chunk_audio_ready_offsets_ms"] == [200.0, 900.0]
```

**Manual quality CSV header** (source prior spike `MANUAL-QUALITY.csv`, line 1):
```csv
runtime,engine,profile,scenario,sample_folder,sample_file,intelligibility_1_5,voice_match_1_5,prosody_1_5,acceptance,notes
```

**Result matrix CSV header** (source prior spike `RESULT-MATRIX.csv`, line 1):
```csv
runtime,engine,profile,scenario,status,request_ttfa_ms,request_total_ms,request_rtf,generate_ttfa_ms,generate_total_ms,generation_rtf,stitched_playback_ms,max_inter_chunk_gap_ms,chunk_count,chunk_word_counts,chunk_estimated_tokens,request_prompt_prep_ms,cached_prompt_build_ms,model_load_ms,warmup_ms,audio_duration_s,stitched_audio_duration_s,peak_vram_mb,sample_rate,backend,mode,streaming_support,true_streaming,seed,scenario_word_count,scenario_description,sample_folder,sample_file,optimizations_applied,optimization_notes,streaming_error,reason
```

### `scripts/deploy-omen.sh` and OMEN Evidence

**Analog:** `scripts/deploy-omen.sh`

**Canonical deployment path and GPU verification pattern** (lines 1-23 and 48-51):
```bash
#!/usr/bin/env bash
set -euo pipefail

OMEN_SSH_ALIAS="${OMEN_SSH_ALIAS:-rayme-pmpg}"
OMEN_REPO="${OMEN_REPO:-C:\\Users\\pmpg\\rayme\\RayMe}"
OMEN_BRANCH="${OMEN_BRANCH:-main}"

RAYME_SSH_ALIAS="${OMEN_SSH_ALIAS}" RAYME_SSH_USER="${OMEN_SSH_USER:-pmpg}" \
  "$REPO_ROOT/scripts/bootstrap-rayme-ssh.sh" restore >/dev/null

ssh "${OMEN_SSH_ALIAS}" "powershell -NoProfile -ExecutionPolicy Bypass -Command - "

Write-Host "== Verifying AI GPU runtime"
$env:PATH = "$cudaRuntimeBin;$env:PATH"
& "$repo\ai-backend\.venv\Scripts\python.exe" -c "import torch, torchaudio; assert '+cpu' not in torch.__version__.lower(), torch.__version__; assert torch.version.cuda, torch.__version__; assert torch.cuda.is_available(), torch.__version__; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'device', torch.cuda.get_device_name(0)); print('torchaudio', torchaudio.__version__)"
```

**Scheduled task and health verification pattern** (lines 87-95 and 127-141):
```powershell
Write-Host "== Asserting canonical scheduled tasks"
schtasks /Delete /TN RayMePhase1AI /F 2>&1 | Out-Null
schtasks /Delete /TN RayMePhase1Web /F 2>&1 | Out-Null
schtasks /Create /TN RayMePhase1AI /TR "C:\Users\pmpg\rayme\start-ai-backend.cmd" /SC ONCE /ST 23:59 /F | Out-Host
schtasks /Create /TN RayMePhase1Web /TR "C:\Users\pmpg\rayme\start-web-ui.cmd" /SC ONCE /ST 23:59 /F | Out-Host

Write-Host "== Verifying health"
$aiHealth = curl.exe -k -sS https://192.168.1.199:9443/health
$webHealth = curl.exe -k -sS https://192.168.1.199:8443/api/settings
...
if (-not $aiStatus.stt_ready -or -not $aiStatus.vad_ready -or $aiStatus.resident_tts_engine -ne "f5") {
  throw "AI backend is not ready for live calls"
}
```

Do not create ad-hoc OMEN deployment scripts. If VoxCPM2 deployment verification needs new checks, extend this script.

## Shared Patterns

### Metadata-Visible Optional Engines
**Source:** `ai-backend/app/models/tts_registry.py` lines 91-120, 122-184, 290-306
**Apply to:** backend registry, metadata mirror, model manager, client fallback roster, Settings/Voice Lab tests

Add VoxCPM2 to metadata even when the package is absent. Missing runtime should mark only VoxCPM2 unavailable.

### Fixed Public Error Codes
**Source:** `ai-backend/app/api/tts.py` lines 54-63; `ai-backend/app/api/webrtc.py` lines 301-319; tests lines 318-337
**Apply to:** VoxCPM2 load, preview/test-play synthesis, call speak failures

Return `tts_failed` or `call_tts_failed` with `engine_id`. Never leak tracebacks, local paths, or CUDA OOM text.

### Voice-Level Engine Settings
**Source:** `web-ui/server/app/storage/models.py` lines 184-192; `web-ui/server/app/domain/voice_service.py` lines 297-311; client save payload lines 278-294
**Apply to:** cloning mode, style controls, transcript-guided/reference-only choice

Store under `metadata.engine_settings.voxcpm2`. Preserve it when switching away from VoxCPM2; ignore it for other engines.

### One Public AI Backend API
**Source:** `web-ui/server/app/domain/ai_backend_client.py` lines 134-147 and 201-218
**Apply to:** preview, test-play, call speech

Web UI server and browser should keep using `/tts/synthesize` and `/webrtc/sessions/{session_id}/speak`; do not add browser-visible VoxCPM2 routes.

### Shared Chunk Planner and Evidence
**Source:** `tts_scenario_matrix.py` lines 240-358, 402-480, 599-603
**Apply to:** VoxCPM2 short/medium/long scenarios, streaming benchmark rows, generated WAVs, matrix CSV/JSON, promotion gate

Use the same scenario text, chunk planner, TTFA/RTF/stitch fields, VRAM fields, and WAV output naming shape.

### Call-Flow Evidence Probe
**Source:** `web-ui/server/tests/test_calls.py`, `web-ui/server/app/domain/ai_backend_client.py`, `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`
**Apply to:** `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py`

Build the probe like a focused integration harness over existing RayMe APIs. Reuse the same payload shapes tested by `test_calls.py` and the Web UI AI backend client instead of adding VoxCPM2-specific public routes. The probe should write JSON only under the Phase 7 `results/` directory and record sanitized failure categories, `warm_call_ttfa_ms`, `f5_warm_call_ttfa_ms`, preview/test-play pass flags, call audio enqueue status, and saved AI audio path.

### OMEN Deployment
**Source:** `AGENTS.md`; `scripts/deploy-omen.sh` lines 1-23, 48-51, 87-95, 127-141
**Apply to:** live install/load/call-flow evidence and any deployment support changes

Deployment must go through `scripts/deploy-omen.sh`. Fix that script if needed; do not create external launchers or scheduled tasks.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `web-ui/client/src/lib/components/voice/VoxCpm2Controls.svelte` | component | conditional UI, transform | No existing engine-specific controls component. Use `TtsEnginePicker.svelte` for metadata rendering and `SynthPreviewPanel.svelte`/Voice Lab page for bounded form control style. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json` | test artifact | batch, file-I/O | No standalone VRAM soak artifact exists. Use `model_manager.health()` VRAM fields and scenario matrix `peak_vram_mb` row schema. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-call-flow.json` | test artifact | event-driven, file-I/O | No standalone call-flow JSON artifact exists. Use `web-ui/server/tests/test_calls.py` speak-call payload assertions and call SSE event shape. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-OMEN-EVIDENCE.md` | test artifact | operations, batch | No exact evidence-doc analog exists. Use `scripts/deploy-omen.sh` as the operational source and record command, commit, host, model/cache paths, health, VRAM, and call-flow evidence. |

## Metadata

**Analog search scope:** `ai-backend/`, `web-ui/server/`, `web-ui/client/src/`, `web-ui/client/tests/`, `.planning/phases/00-measurement-gate/probes/`, `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/`, `scripts/`

**Files scanned:** 245 tracked files excluding `node_modules`, `.venv`, and `__pycache__`

**Pattern extraction date:** 2026-05-11
