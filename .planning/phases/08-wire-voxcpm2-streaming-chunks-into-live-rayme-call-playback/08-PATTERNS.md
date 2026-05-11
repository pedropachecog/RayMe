# Phase 08: Wire VoxCPM2 Streaming Chunks Into Live RayMe Call Playback - Pattern Map

**Mapped:** 2026-05-11  
**Files analyzed:** 22  
**Analogs found:** 21 / 22

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `ai-backend/app/models/tts_registry.py` | model/config | transform | `ai-backend/app/models/tts_registry.py` | exact |
| `ai-backend/app/models/tts_voxcpm2.py` | service/adapter | streaming + file-I/O | `ai-backend/app/models/tts_voxcpm2.py` | exact |
| `ai-backend/app/models/model_manager.py` | service/config | stateful CRUD | `ai-backend/app/models/model_manager.py` | exact |
| `ai-backend/app/call/session.py` | service/orchestrator | streaming + event-driven | `ai-backend/app/call/session.py` | role-match |
| `ai-backend/app/call/tracks.py` | service/transport | streaming + file-I/O | `ai-backend/app/call/tracks.py` | exact |
| `ai-backend/app/api/webrtc.py` | controller/route | request-response | `ai-backend/app/api/webrtc.py` | exact |
| `web-ui/server/app/api/calls.py` | controller/route | streaming SSE + CRUD | `web-ui/server/app/api/calls.py` | exact |
| `web-ui/server/app/domain/ai_backend_client.py` | service/client | request-response | `web-ui/server/app/domain/ai_backend_client.py` | exact |
| `ai-backend/tests/test_tts_voxcpm2.py` | test | transform + file-I/O | `ai-backend/tests/test_tts_voxcpm2.py` | exact |
| `ai-backend/tests/test_call_session.py` | test | event-driven + streaming | `ai-backend/tests/test_call_session.py` | exact |
| `ai-backend/tests/test_webrtc_signaling.py` | test | request-response | `ai-backend/tests/test_webrtc_signaling.py` | exact |
| `ai-backend/tests/test_model_manager.py` | test | stateful CRUD | `ai-backend/tests/test_model_manager.py` | exact |
| `web-ui/server/tests/test_calls.py` | test | streaming SSE + CRUD | `web-ui/server/tests/test_calls.py` | exact |
| `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py` | utility/evidence | batch + request-response + file-I/O | `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py` | role-match |
| `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py` | utility/verifier | batch + file-I/O | `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py` | role-match |
| `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-PROMOTION-DECISION.md` | config/decision doc | batch | `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-PROMOTION-DECISION.md` | role-match |
| `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-live-streaming-call-flow.json` | evidence artifact | file-I/O | `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-decision.json` | partial |
| `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-decision.json` | config/evidence | batch | `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-decision.json` | role-match |
| `.planning/PROJECT.md` | config/doc | decision writeback | `.planning/PROJECT.md` | exact |
| `.planning/STATE.md` | config/doc | append-only state | `.planning/STATE.md` | exact |
| `.planning/ROADMAP.md` | config/doc | roadmap update | `.planning/ROADMAP.md` | exact |
| `ai-backend/app/models/<streaming contract helper, if created>` | utility/model | streaming | None | no exact analog |

## Pattern Assignments

### `ai-backend/app/models/tts_registry.py` (model/config, transform)

**Analog:** `ai-backend/app/models/tts_registry.py`

**Imports pattern** (lines 3-8):
```python
import importlib.util
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field
```

**Model and validation pattern** (lines 44-78):
```python
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
    reference_audio_content_type: str | None = None
    reference_transcript: str | None = None
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)
    voxcpm2_cloning_mode: Literal["auto", "reference_only", "transcript_guided"] = "auto"
```

**Protocol pattern** (lines 85-99):
```python
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
```

**Metadata pattern** (lines 196-204):
```python
TtsEngineMetadata(
    id="voxcpm2",
    label="VoxCPM2",
    code_license="Apache-2.0",
    model_license="Apache-2.0",
    caveat_chips=["Candidate", "48 kHz", "RTX 3060 gate pending"],
    runtime_evidence="Phase 7 optional runtime evidence required for openbmb/VoxCPM2: health, CUDA load, TTFA/RTF, VRAM, quality, and call-flow checks.",
    requires_transcript=False,
    supports_streaming=True,
```

**Apply:** add any `TtsAudioChunk` / streaming protocol beside `TtsSynthesisOutput` and `TtsAdapter`; export it in `__all__` using the existing lines 333-347 export style.

---

### `ai-backend/app/models/tts_voxcpm2.py` (service/adapter, streaming + file-I/O)

**Analog:** `ai-backend/app/models/tts_voxcpm2.py`

**Imports pattern** (lines 3-17):
```python
import tempfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.models.gpu_runtime import require_torch_cuda_runtime
from app.models.tts_registry import (
    ImportGatedTtsAdapter,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)
```

**Runtime loading pattern** (lines 37-43, 85-93):
```python
def load(self) -> None:
    if self._runtime_factory is None:
        self._ensure_runtime_available()
        require_torch_cuda_runtime("VoxCPM2")
    if self._runtime is None:
        self._runtime = self._build_runtime()
    self.loaded = True

def _build_runtime(self) -> Any:
    if self._runtime_factory is not None:
        return self._runtime_factory()
    require_torch_cuda_runtime("VoxCPM2")
    from voxcpm import VoxCPM

    runtime = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)
    _assert_runtime_uses_cuda(runtime)
    return runtime
```

**Core generation pattern** (lines 49-83):
```python
def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
    if not self.loaded:
        self.load()
    runtime = self._runtime or self._build_runtime()
    self._runtime = runtime
    reference_transcript = (request.reference_transcript or "").strip()
    warning_codes: list[str] = []

    with tempfile.TemporaryDirectory(prefix="rayme-voxcpm2-") as tmp_dir:
        reference_path = Path(tmp_dir) / f"reference{_audio_suffix(request.reference_audio_content_type)}"
        reference_path.write_bytes(request.reference_audio)
        generate_kwargs = _build_generate_kwargs(
            request=request,
            reference_path=reference_path,
            reference_transcript=reference_transcript,
            warning_codes=warning_codes,
        )
        _ensure_librosa_load()
        generated = runtime.generate(**generate_kwargs)

    wav, sample_rate = _split_generate_result(generated, runtime)
    wav_array = np.asarray(wav, dtype=np.float32).flatten()
    if wav_array.size == 0:
        raise ValueError("VoxCPM2 synthesis failed")
```

**VoxCPM2 option mapping pattern** (lines 113-141):
```python
kwargs: dict[str, Any] = {
    "text": text,
    "cfg_value": request.voxcpm2_cfg_value,
    "inference_timesteps": request.voxcpm2_inference_timesteps,
    "normalize": request.voxcpm2_normalize,
    "denoise": request.voxcpm2_denoise,
}

if request.voxcpm2_cloning_mode == "transcript_guided" and reference_transcript:
    kwargs["prompt_wav_path"] = str(reference_path)
    kwargs["prompt_text"] = reference_transcript
    kwargs["reference_wav_path"] = str(reference_path)
else:
    kwargs["reference_wav_path"] = str(reference_path)
```

**Chunk serialization pattern:** copy the lines 69-80 WAV serialization shape, but apply it per streaming chunk. Reject `wav_array.size == 0` as lines 70-72 do.

---

### `ai-backend/app/models/model_manager.py` (service/config, stateful CRUD)

**Analog:** `ai-backend/app/models/model_manager.py`

**One-hot residency pattern** (lines 96-127):
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
```

**Engine-scoped unavailable pattern** (lines 115-121, 178-183):
```python
try:
    self._load_engine(engine_id)
except Exception:
    self.resident_tts_engine = None
    self.loading_engine = None
    self._mark_unavailable(engine_id, "engine load failed")
    raise

def _mark_unavailable(self, engine_id: str, reason: str) -> None:
    status = self._statuses[engine_id]
    status.available = False
    status.resident = False
    status.state = "unavailable"
    status.unavailable_reason = reason
```

**Apply:** do not bypass `switch_tts_engine()` for streaming. VoxCPM2 streaming must use the same resident adapter selected by `/webrtc/speak`.

---

### `ai-backend/app/call/session.py` (service/orchestrator, streaming + event-driven)

**Analog:** `ai-backend/app/call/session.py`

**Imports and event constants pattern** (lines 17-39):
```python
from app.call.events import (
    AI_AUDIO_STARTED_EVENT,
    AI_DONE_EVENT,
    ENDED_EVENT,
    FAILED_EVENT,
    INTERRUPTED_EVENT,
    MUTED_EVENT,
    failed_event,
    simple_event,
)
from app.call.tracks import (
    InboundAudioFrameNormalizer,
    OutboundAudioBuffer,
    PcmAudioFrame,
    audio_stats_for_wav_bytes,
    normalize_inbound_audio_frame,
    write_pcm_frames_to_temp_wav,
)
from app.models.tts_registry import MAX_REFERENCE_AUDIO_BYTES, TtsSynthesisInput
```

**Current whole-WAV lifecycle to preserve** (lines 758-827):
```python
async def speak_text(...):
    self._cancelled_ai_turns.discard(turn_id)
    self.state = "thinking"
    current_task = asyncio.current_task()
    if current_task is not None:
        self.active_turn_task = current_task

    audio_started_event: dict[str, Any] | None = None

    try:
        result = await self._synthesize_speech(...)
        if turn_id in self._cancelled_ai_turns:
            return {"status": "cancelled", "turn_id": turn_id}
        wav_bytes = bytes(result.get("wav_bytes") or b"")
        playback_seconds = 0.0
        if wav_bytes:
            audio_stats = audio_stats_for_wav_bytes(...)
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
            await self.emit_event(audio_started_event)
```

**Error and single-final pattern** (lines 830-880):
```python
except Exception:
    self.state = "listening"
    event = failed_event(
        session_id=self.session_id,
        turn_id=turn_id,
        code="call_tts_failed",
        message="Speech playback failed. Please try again.",
        retry_allowed=True,
    )
    event["engine_id"] = engine_id
    await self.emit_event(event)
    if audio_started_event is not None:
        return {**event, "ai_audio_started_event": audio_started_event}
    return event

if final_chunk:
    self.state = "listening"
    done_event = await self.emit_event(
        simple_event(AI_DONE_EVENT, session_id=self.session_id, turn_id=turn_id, ...)
    )
```

**Async/sync synthesis boundary pattern** (lines 1438-1487):
```python
adapter = tts_adapter or self.tts_adapter
if adapter is None:
    return {"wav_bytes": b"", "sample_rate": 24000, "duration_ms": 0}

is_async = self._is_tts_method_async(adapter, reference_audio_b64)
if is_async:
    result = await self._do_async_synthesis(...)
else:
    result = await asyncio.to_thread(
        self._run_sync_synthesis,
        adapter,
        turn_id,
        text,
        voice_id,
        engine_id,
        reference_audio_b64,
        reference_transcript,
        reference_audio_content_type,
        voxcpm2_options or {},
    )
if hasattr(result, "model_dump"):
    result = result.model_dump()
return dict(result)
```

**Queue/playback helper pattern** (lines 1567-1637):
```python
async def _queue_outbound_audio(self, wav_bytes: bytes, *, preroll_seconds: float = 0.0) -> float:
    if not wav_bytes:
        logger.info("[rayme-call] tts.enqueue_empty session=%s", self.session_id)
        return 0.0
    enqueue = getattr(self.outbound_audio_track, "enqueue", None)
    if callable(enqueue):
        result = self._call_track_enqueue(enqueue, wav_bytes, preroll_seconds=preroll_seconds)
        if inspect.isawaitable(result):
            result = await result
        return float(result or 0.0)
    self.outbound_audio_buffer.append(wav_bytes)
    return 0.0

async def _wait_for_outbound_audio_playback(self, playback_seconds: float) -> None:
    wait_until_idle = getattr(self.outbound_audio_track, "wait_until_idle", None)
    if not callable(wait_until_idle):
        return
    timeout = max(playback_seconds + 2.0, 2.0)
    result = wait_until_idle(timeout=timeout)
    completed = await result if inspect.isawaitable(result) else bool(result)
```

**Interrupt/cancel pattern** (lines 748-756, 882-896):
```python
async def interrupt(self) -> dict[str, Any]:
    self.interrupted = True
    await self.cancel_ai_turn()
    self.state = "interrupted"
    event = await self.emit_event(simple_event(INTERRUPTED_EVENT, session_id=self.session_id))
    self.state = "listening"
    return event

async def cancel_ai_turn(self, turn_id: str | None = None) -> None:
    active = self.active_turn_task
    if turn_id is not None:
        self._cancelled_ai_turns.add(turn_id)
    if active is not None:
        cancel = getattr(active, "cancel", None)
        if callable(cancel):
            cancel()
    self.active_turn_task = None
    stop = getattr(self.outbound_audio_track, "stop_current", None)
```

**Apply:** add a VoxCPM2 streaming branch inside `speak_text()` or a helper it calls. Emit `ai_audio_started` only after the first successful `_queue_outbound_audio()` call. Keep one `AI_DONE_EVENT` after all chunk generation/playback reaches the current completion boundary.

---

### `ai-backend/app/call/tracks.py` (service/transport, streaming + file-I/O)

**Analog:** `ai-backend/app/call/tracks.py`

**Queue track pattern** (lines 54-72):
```python
class QueuedAudioOutputTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, *, sample_rate: int = 48000, frame_ms: int = 20) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.frame_samples = max(int(sample_rate * frame_ms / 1000), 1)
        self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue()
        self._buffer = np.asarray([], dtype=np.int16)
        self.last_enqueue_stats: dict[str, float | int] = {
            "duration_ms": 0,
            "samples": 0,
            "rms": 0.0,
            "peak": 0.0,
        }
```

**Enqueue and stats pattern** (lines 98-119):
```python
async def enqueue(self, wav_bytes: bytes, *, preroll_seconds: float = 0.0) -> float:
    samples = _wav_bytes_to_int16(wav_bytes, target_sample_rate=self.sample_rate)
    preroll_samples = int(self.sample_rate * max(preroll_seconds, 0.0))
    if preroll_samples > 0:
        samples = np.concatenate([np.zeros(preroll_samples, dtype=np.int16), samples])
    self.last_enqueue_stats = audio_stats_for_int16_samples(samples, sample_rate=self.sample_rate)
    duration_seconds = float(self.last_enqueue_stats["duration_ms"]) / 1000.0
    if samples.size:
        await self._queue.put(samples)
    return duration_seconds
```

**Drain and decode pattern** (lines 141-145, 288-309):
```python
async def stop_current(self) -> None:
    while not self._queue.empty():
        self._queue.get_nowait()
        self._queue.task_done()
    self._buffer = np.asarray([], dtype=np.int16)

def _wav_bytes_to_int16(wav_bytes: bytes, *, target_sample_rate: int) -> np.ndarray:
    samples, sample_rate = sf.read(BytesIO(wav_bytes), dtype="float32", always_2d=True)
    mono = np.asarray(samples, dtype=np.float32).mean(axis=1)
    if sample_rate != target_sample_rate:
        mono = _resample_linear(mono, source_rate=int(sample_rate), target_rate=target_sample_rate)
    clipped = np.clip(mono, -1.0, 1.0)
    return (clipped * np.iinfo(np.int16).max).astype(np.int16)
```

**Apply:** prefer per-chunk valid WAV bytes into this existing `enqueue()` boundary. Do not apply the 250 ms call preroll to every later chunk; reserve it for the first chunk if retained.

---

### `ai-backend/app/api/webrtc.py` (controller/route, request-response)

**Analog:** `ai-backend/app/api/webrtc.py`

**Request model/validation pattern** (lines 73-93):
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
        max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    voxcpm2_cloning_mode: Literal["auto", "reference_only", "transcript_guided"] = "auto"
    voxcpm2_cfg_value: float = Field(default=2.0, ge=1.0, le=3.0)
```

**Speak route pattern** (lines 283-353):
```python
@router.post("/sessions/{session_id}/speak")
async def speak_session(request: Request, session_id: str, payload: SpeakRequest) -> dict[str, Any]:
    session = _session_or_404(request, session_id)
    try:
        _reject_oversized_reference_audio(payload.reference_audio_b64)
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
            voxcpm2_cloning_mode=payload.voxcpm2_cloning_mode,
            voxcpm2_style_prompt=payload.voxcpm2_style_prompt,
```

**Sanitized failure pattern** (lines 329-347):
```python
except Exception as exc:
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "code": "call_tts_failed",
            "message": "Speech playback failed",
            "engine_id": payload.engine_id,
        },
    ) from exc

if event.get("type") == "failed" and event.get("code") == "call_tts_failed":
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={...})
```

**Adapter selection pattern** (lines 495-515):
```python
def _tts_adapter(request: Request, engine_id: str) -> Any:
    manager = getattr(request.app.state, "model_manager", None)
    if manager is None:
        manager = ModelManager(_settings_from_app(request))
        manager.startup()
        request.app.state.model_manager = manager
    switch = getattr(manager, "switch_tts_engine", None)
    if callable(switch):
        switch(engine_id)
    adapters = getattr(manager, "tts_adapters", {})
    try:
        return adapters[engine_id]
```

**Apply:** preserve the public route. Add streaming timing fields inside `event`/response only if needed for evidence and Web UI extraction; keep browser-facing errors fixed and sanitized.

---

### `web-ui/server/app/api/calls.py` (controller/route, streaming SSE + CRUD)

**Analog:** `web-ui/server/app/api/calls.py`

**Imports pattern** (lines 5-21):
```python
import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Mapping

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
```

**One durable AI speech row + speak request pattern** (lines 399-435):
```python
visible_text = "".join(accumulated)
if visible_text:
    message = await service.record_ai_speech(call_id, visible_text)
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

**SSE keepalive while speak request stays open** (lines 437-464):
```python
speak_result: dict[str, Any] | None = None
while not tts_task.done():
    await asyncio.sleep(2.0)
    yield ": keepalive\n\n"
try:
    speak_result = await tts_task
except AiBackendClientError as exc:
    yield _sse(
        {
            "type": "error",
            "turn_id": payload.turn_id,
            "code": "call_tts_failed",
            "message": "Speech playback failed",
        }
    )
audio_started_event = _extract_ai_audio_started_event(speak_result)
if audio_started_event is not None:
    yield _sse(audio_started_event)
```

**Nested event extraction pattern** (lines 805-816):
```python
def _extract_ai_audio_started_event(speak_result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if speak_result is None:
        return None
    event = speak_result.get("event")
    candidates = [
        speak_result.get("ai_audio_started_event"),
        event.get("ai_audio_started_event") if isinstance(event, Mapping) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping) and candidate.get("type") == "ai_audio_started":
            return dict(candidate)
```

**Apply:** do not persist per-chunk rows. Let `/webrtc/speak` remain blocking until playback completion and use SSE keepalives while waiting.

---

### `web-ui/server/app/domain/ai_backend_client.py` (service/client, request-response)

**Analog:** `web-ui/server/app/domain/ai_backend_client.py`

**Public-safe error type pattern** (lines 67-84):
```python
class AiBackendClientError(Exception):
    """Public-safe AI backend client error."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
```

**Speak client pattern** (lines 201-218):
```python
async def speak_call(self, base_url: str, session_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    response = await self._request(
        "POST",
        _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/speak"),
        json=dict(payload),
        processing_message=WEBRTC_FAILED_MESSAGE,
        processing_code="call_tts_failed",
        timeout=self._synthesis_timeout,
    )
    response_payload = _json_payload(response)
    if not isinstance(response_payload, dict):
        raise _invalid_response()
    return dict(response_payload)
```

**Sanitizing backend details pattern** (lines 266-321):
```python
try:
    ...
except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
    raise AiBackendUnavailable(code="unreachable", message=UNREACHABLE_MESSAGE) from exc

if response.status_code >= 500 and processing_message and processing_code:
    raise _processing_error_from_response(response, processing_code, processing_message)

code = detail.get("code")
message = detail.get("message")
if not isinstance(code, str) or not code:
    code = fallback_code
if not isinstance(message, str) or not message:
    message = fallback_message
return AiBackendProcessingError(code=code, message=message)
```

**Apply:** increase no public surface unless evidence requires extra response fields; keep the client returning opaque dicts for `/webrtc/speak`.

---

### `ai-backend/tests/test_tts_voxcpm2.py` (test, transform + file-I/O)

**Analog:** `ai-backend/tests/test_tts_voxcpm2.py`

**Scripted runtime pattern** (lines 50-75):
```python
class ScriptedVoxCpmRuntime:
    sample_rate = 48_000
    allowed_generate_kwargs = {...}

    def __init__(self, audio: np.ndarray | None = None) -> None:
        self.audio = _tone() if audio is None else audio
        self.calls: list[dict[str, Any]] = []

    def parameters(self) -> list[Any]:
        return [types.SimpleNamespace(device=types.SimpleNamespace(type="cuda"))]

    def generate(self, **kwargs: Any) -> tuple[np.ndarray, int]:
        unknown_kwargs = set(kwargs) - self.allowed_generate_kwargs
        if unknown_kwargs:
            raise TypeError(f"unexpected generate kwargs: {sorted(unknown_kwargs)}")
        self.calls.append(kwargs)
        return self.audio, self.sample_rate
```

**Bounded options test pattern** (lines 214-239):
```python
valid = _request(
    voxcpm2_cloning_mode="reference_only",
    voxcpm2_style_prompt="calm, close-mic conversational style",
    voxcpm2_cfg_value=1.5,
    voxcpm2_inference_timesteps=16,
    voxcpm2_normalize=True,
    voxcpm2_denoise=True,
)

with pytest.raises(ValueError):
    TtsSynthesisInput(**{**valid.model_dump(), "voxcpm2_cloning_mode": "device_auto"})
```

**Apply:** add `generate_streaming()` to `ScriptedVoxCpmRuntime` and assert adapter streaming yields first non-empty chunk, 48 kHz metadata, warning codes, and sanitized empty/invalid chunk behavior.

---

### `ai-backend/tests/test_call_session.py` (test, event-driven + streaming)

**Analog:** `ai-backend/tests/test_call_session.py`

**Track fixture pattern** (lines 65-88):
```python
class ScriptedOutboundAudioTrack:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.preroll_seconds: list[float] = []
        self.stop_calls = 0
        self.wait_calls: list[float | None] = []

    async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
        self.chunks.append(chunk)
        self.preroll_seconds.append(preroll_seconds)
        self.last_enqueue_stats = {"duration_ms": int(120 + preroll_seconds * 1000), ...}
        return float(self.last_enqueue_stats["duration_ms"]) / 1000.0

    async def stop_current(self) -> None:
        self.stop_calls += 1
```

**Session fixture pattern** (lines 202-225):
```python
def _new_session(...):
    peer = ScriptedPeerConnection()
    session = CallSession(
        session_id=session_id,
        peer_connection=peer,
        vad_adapter=vad_adapter,
        stt_adapter=stt_adapter,
        tts_adapter=tts_adapter,
        outbound_audio_track=outbound_audio_track,
        data_channel=data_channel,
        event_sink=event_sink,
        settings=settings,
    )
    return session, peer
```

**Ordering assertion pattern** (lines 924-959):
```python
def test_speak_text_queues_audio_before_audio_started_event() -> None:
    order: list[str] = []

    class OrderedTrack(ScriptedOutboundAudioTrack):
        async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
            order.append("enqueue")
            return await super().enqueue(chunk, preroll_seconds=preroll_seconds)

    def sink(event: dict[str, Any]) -> None:
        order.append(event["type"])

    ...
    assert order.index("enqueue") < order.index("ai_audio_started")
    assert order.index("ai_audio_started") < order.index("wait_until_idle")
```

**Interrupt assertion pattern** (lines 1214-1247):
```python
def test_interrupt_cancels_voxcpm2_active_speech_before_ai_done() -> None:
    events: list[dict[str, Any]] = []
    track = ScriptedOutboundAudioTrack()
    adapter = ScriptedTtsAdapter(delay=1)
    session, _ = _new_session(tts_adapter=adapter, outbound_audio_track=track, event_sink=events.append)

    async def scenario() -> None:
        speech = asyncio.create_task(session.speak_text(..., "voxcpm2", final_chunk=True))
        await asyncio.sleep(0)
        await session.interrupt()
        try:
            await speech
        except asyncio.CancelledError:
            pass

    assert track.chunks == []
    assert track.stop_calls == 1
    assert [item["type"] for item in events] == ["interrupted"]
```

**Apply:** create tests with a scripted streaming adapter that yields chunk 1, blocks before chunk 2, asserts first enqueue/`ai_audio_started` happen before final generator completion, then interrupts after first chunk and verifies no later chunks or duplicate `ai_done`.

---

### `ai-backend/tests/test_webrtc_signaling.py` (test, request-response)

**Analog:** `ai-backend/tests/test_webrtc_signaling.py`

**Adapter fixture pattern** (lines 33-60):
```python
class ScriptedTtsAdapter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def synthesize_call_text(self, *, turn_id: str, text: str, voice_id: str, engine_id: str, **options: Any) -> dict[str, Any]:
        self.calls.append({"turn_id": turn_id, "text": text, "voice_id": voice_id, "engine_id": engine_id, **options})
        if self.fail:
            raise RuntimeError("raw model failure Traceback /home/pmpg/.cache/model-cache ...")
```

**Speak route contract pattern** (lines 282-312):
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
payload = response.json()
assert manager.switch_calls == ["f5"]
assert payload["event"]["type"] == "ai_done"
```

**VoxCPM2 options contract pattern** (lines 315-357):
```python
response = client.post(
    SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
    json={
        "engine_id": "voxcpm2",
        "reference_audio_base64": "cmVhbC1zYW1wbGU=",
        "reference_transcript": "Real VoxCPM2 reference text.",
        "voxcpm2_cloning_mode": "transcript_guided",
        "voxcpm2_style_prompt": "warm phone call voice",
        "voxcpm2_cfg_value": 2.4,
        "voxcpm2_inference_timesteps": 12,
        "voxcpm2_normalize": True,
        "voxcpm2_denoise": False,
    },
)

assert response.status_code == 200
assert manager.switch_calls == ["voxcpm2"]
```

**Sanitized failure pattern** (lines 424-450):
```python
assert response.status_code == 502
assert response.json()["detail"] == {
    "code": "call_tts_failed",
    "message": "Speech playback failed",
    "engine_id": "f5",
}
assert "raw model failure" not in response.text
assert "Traceback" not in response.text
assert "/home/" not in response.text
```

**Apply:** add WebRTC speak tests for streaming timing fields and fallback flags, but keep route/status/error contracts unchanged.

---

### `web-ui/server/tests/test_calls.py` (test, streaming SSE + CRUD)

**Analog:** `web-ui/server/tests/test_calls.py`

**Scripted backend pattern** (lines 42-95):
```python
class ScriptedCallBackend:
    def __init__(self, *, ready: bool = True, voice_available: bool = True) -> None:
        self.ready = ready
        self.voice_available = voice_available
        self.speak_calls: list[dict[str, Any]] = []

    async def speak_call(self, base_url: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.speak_calls.append(
            {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
        )
        return {"session_id": session_id, "event": {"type": "ai_done"}}
```

**Single durable speech row pattern** (lines 559-580):
```python
assert first.status_code == 200
assert second.status_code == 200
first_events = _sse_events(first.text)
second_events = _sse_events(second.text)
assert [event["type"] for event in first_events] == ["ai_token", "ai_token", "ai_done"]
assert [event["type"] for event in second_events] == ["ai_token", "ai_token", "ai_done"]

rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
speech_rows = [row for row in rows if row[0] in {"user_speech", "ai_speech"}]
assert speech_rows == [
    ("user_speech", "user", "First user turn."),
    ("ai_speech", "assistant", "First AI answer."),
]
```

**Nested audio-started event pattern** (lines 745-797):
```python
class BackendWithNestedAudioStarted(ScriptedCallBackend):
    async def speak_call(...):
        return {
            "session_id": session_id,
            "turn_id": payload.get("turn_id"),
            "state": "speaking",
            "event": {
                "type": "ai_done",
                "turn_id": payload.get("turn_id"),
                "ai_audio_started_event": {
                    "type": "ai_audio_started",
                    "turn_id": payload.get("turn_id"),
                    "session_id": session_id,
                },
            },
        }

events = _sse_events(response.text)
event_types = [e["type"] for e in events]
assert "ai_audio_started" in event_types
```

**Apply:** if backend returns streaming proof fields nested under `ai_audio_started_event` or `event`, assert Web UI forwards them without additional durable rows.

---

### `ai-backend/tests/test_model_manager.py` (test, stateful CRUD)

**Analog:** `ai-backend/tests/test_model_manager.py`

**One-hot switch test pattern** (lines 214-225):
```python
def test_switch_tts_engine_unloads_previous_resident_before_loading_target() -> None:
    manager, _, events = _build_manager()

    _complete(manager.startup())
    _complete(manager.switch_tts_engine("xtts_v2"))
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["resident_tts_engine"] == "xtts_v2"
    assert health["loading_engine"] is None
    assert _resident_engine_ids(statuses) == ["xtts_v2"]
    assert events.index("f5:unload") < events.index("xtts_v2:load")
```

**VoxCPM2 scoped failure pattern** (lines 246-274):
```python
def test_voxcpm2_load_failure_degrades_only_voxcpm2() -> None:
    manager, _, events = _build_manager(load_failing_engine="voxcpm2")

    _complete(manager.startup())
    with pytest.raises(RuntimeError):
        _complete(manager.switch_tts_engine("voxcpm2"))
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["status"] == "degraded"
    assert health["resident_tts_engine"] is None
    assert statuses["voxcpm2"]["available"] is False
    assert statuses["voxcpm2"]["unavailable_reason"] == "engine load failed"
```

**Apply:** if streaming startup changes adapter capabilities, keep one-hot residency and engine-scoped failure tests passing.

---

### `.planning/phases/08.../08-run-call-flow-evidence.py` (utility/evidence, batch + request-response + file-I/O)

**Analog:** `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py`

**Script header and paths pattern** (lines 1-31):
```python
#!/usr/bin/env python3
"""Generate live VoxCPM2 preview, test-play, and call speak evidence.

Run with the AI backend environment so aiortc is available, for example:

    uv run --project ai-backend python .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py
"""

PHASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PHASE_DIR.parents[2]
RESULTS_DIR = PHASE_DIR / "results"
AUDIO_DIR = RESULTS_DIR / "audio"
CALL_FLOW_JSON = RESULTS_DIR / "voxcpm2-call-flow.json"
```

**HTTP client and sanitized failure pattern** (lines 70-152):
```python
class RayMeApi:
    def __init__(self, *, web_base_url: str, ai_base_url: str, timeout: float) -> None:
        self.web_base_url = web_base_url.rstrip("/")
        self.ai_base_url = ai_base_url.rstrip("/")
        self.timeout = timeout
        self.ssl_context = ssl._create_unverified_context()

    def post_json(self, base_url: str, path: str, payload: dict[str, Any]) -> ApiResponse:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(..., method="POST")
        return self._open_json(request)
```

**Current call speak measurement to replace** (lines 370-388):
```python
speak_payload = {
    "turn_id": f"turn-{uuid.uuid4().hex[:16]}",
    "text": args.call_text,
    "voice_id": created_voice_id,
    "engine_id": "voxcpm2",
    "final_chunk": True,
    **_voxcpm2_payload_base(reference_audio_b64, args.reference_transcript),
    "reference_transcript": reference_transcript,
}
speak_start = time.perf_counter()
speak = _require_ok(
    api.post_json(api.ai_base_url, f"/webrtc/sessions/{session_id}/speak", speak_payload),
    operation="call speak",
)
warm_call_ttfa_ms = (time.perf_counter() - speak_start) * 1000
audio_event = speak_event.get("ai_audio_started_event") if isinstance(speak_event, dict) else None
call_audio_enqueued = isinstance(audio_event, dict) and bool(audio_event.get("audio"))
```

**Apply:** for Phase 8, do not use total speak request duration as TTFA. Read timing fields from `ai_audio_started_event`/response: first chunk generated, first enqueue, chunk count, fallback flags, inter-chunk gaps, total generation, playback wait, and repeated warm samples. Keep the same WebRTC offer setup.

---

### `.planning/phases/08.../08-verify-evidence.py` (utility/verifier, batch + file-I/O)

**Analog:** `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py`

**Required fields pattern** (lines 92-102):
```python
CALL_FLOW_REQUIRED_FIELDS = {
    "engine",
    "preview_result",
    "test_play_result",
    "call_speak_result",
    "call_audio_enqueued",
    "saved_ai_audio_path",
    "sanitized_failure_category",
    "warm_call_ttfa_ms",
    "f5_warm_call_ttfa_ms",
}
```

**Verifier helpers pattern** (lines 124-166):
```python
def _read_json(path: Path) -> Any:
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON in {path.relative_to(PHASE_DIR)}: {exc}") from exc

def _require_fields(payload: dict[str, Any], required: set[str], *, label: str) -> None:
    missing = required - set(payload)
    if missing:
        raise EvidenceError(f"{label} missing fields: {sorted(missing)}")

def _verify_no_raw_error_leak(value: Any, *, label: str) -> None:
    text = json.dumps(value, sort_keys=True)
    forbidden = ["Traceback", "File \"", "C:\\", "/home/", ".cache", "huggingface", "openbmb/VoxCPM2"]
```

**Call-flow verification pattern** (lines 287-310):
```python
payload = _read_json(CALL_FLOW_JSON)
if not isinstance(payload, dict):
    raise EvidenceError("call-flow JSON must be an object")
_require_fields(payload, CALL_FLOW_REQUIRED_FIELDS, label="call-flow JSON")
if payload.get("engine") != "voxcpm2":
    raise EvidenceError("call-flow JSON engine must be voxcpm2")
if payload.get("call_audio_enqueued") is not True:
    raise EvidenceError("call_audio_enqueued must be true")
_verify_no_raw_error_leak(payload, label="call-flow JSON")
_require_number(payload.get("warm_call_ttfa_ms"), label="warm_call_ttfa_ms")
```

**Apply:** Phase 8 verifier must require `streaming_used is True`, `fallback_used is False`, `whole_wav_fallback_used is False`, `chunk_count >= 1`, finite first-chunk/enqueue/audio-started timings, and median warm VoxCPM2 TTFA less than median warm F5 TTFA.

---

### Decision and durable project docs (config/doc, decision writeback)

**Analogs:** `07-PROMOTION-DECISION.md`, prior `voxcpm2-decision.json`, `.planning/PROJECT.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`

**Promotion decision doc pattern** (`07-PROMOTION-DECISION.md` lines 1-18):
```markdown
---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
outcome: selectable_with_caveats
decided: 2026-05-11
reference_voice: BeauBrown-s2
reference_audio: web-ui/server/data/blobs/voices/voice_asset_531ca6a567db4f01a870cdfba8abae96.wav
---

# VoxCPM2 Promotion Decision

Outcome: selectable_with_caveats

## Decision

VoxCPM2 is accepted into the visible TTS roster as a selectable engine with caveats.
```

**Decision JSON pattern** (`results/voxcpm2-decision.json` lines 1-12):
```json
{
  "final_outcome": "selectable_with_caveats",
  "reference_audio": "web-ui/server/data/blobs/voices/voice_asset_531ca6a567db4f01a870cdfba8abae96.wav",
  "reference_voice": "BeauBrown-s2",
  "rationale": "Manual listening judged VoxCPM2 far superior to F5, but live RayMe call TTFA remains slower because calls do not yet consume VoxCPM2 streaming chunks.",
  "voxcpm2_warm_call_ttfa_ms": 14425.6,
  "f5_warm_call_ttfa_ms": 1117.1
}
```

**Project decision line to update only on pass** (`.planning/PROJECT.md` lines 107-109):
```markdown
- **TTS v1 default (Resolved Tension #3):** `f5`. TTFA = `517.3` ms, RTF = `0.388`.
- **TTS v1 engine roster (REQ-22):** `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`, and `VoxCPM2`. ... VoxCPM2 is `selectable_with_caveats`: manual quality is far superior to F5, but current RayMe calls do not yet consume VoxCPM2 streaming chunks, so F5 remains the default for fastest call feel.
- **TTS chunking requirement (REQ-45):** all engines need a shared chunk planner before final long-form decisions.
```

**State update pattern** (`.planning/STATE.md` lines 53-64 and 66-78):
```markdown
- Phase 07 plan 07-12 completed on 2026-05-11: VoxCPM2 final outcome is `selectable_with_caveats`; manual listening judged VoxCPM2 far superior to F5, while live RayMe call TTFA still favors F5 because calls do not yet consume VoxCPM2 streaming chunks.

## Current Decisions

- TTS v1 default: `f5`.
- TTS v1 roster: `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`.
```

**Roadmap update pattern** (`.planning/ROADMAP.md` lines 492-519):
```markdown
### Phase 7: Add VoxCPM2 to the TTS roster with empirical quality, latency, VRAM, and call-flow evaluations

**Final outcome:** `selectable_with_caveats`. ... F5 remains the default because current RayMe calls still wait for full VoxCPM2 synthesis before playback, so live call TTFA does not yet get the streaming benefit.

### Phase 8: Wire VoxCPM2 streaming chunks into live RayMe call playback

**Goal:** [To be planned]
```

**Apply:** update these docs only after Phase 8 verifier passes. Keep evidence paths and median F5/VoxCPM2 comparison values cited in the decision artifact.

## Shared Patterns

### No Auth Guard

**Source:** current FastAPI routes use request/app-state boundaries, not auth middleware.  
**Apply to:** `ai-backend/app/api/webrtc.py`, `web-ui/server/app/api/calls.py`, evidence scripts.

There is no auth pattern to copy for Phase 8. Keep existing route exposure and public error behavior.

### Validation

**Source:** `ai-backend/app/api/webrtc.py` lines 73-93 and `ai-backend/app/api/tts.py` lines 22-42  
**Apply to:** all new `/webrtc/speak` or synthesis timing fields.

```python
model_config = ConfigDict(extra="forbid", populate_by_name=True)
text: str = Field(min_length=1, max_length=5000)
reference_audio_b64: str | None = Field(..., max_length=MAX_REFERENCE_AUDIO_B64_LENGTH)
voxcpm2_cfg_value: float = Field(default=2.0, ge=1.0, le=3.0)
voxcpm2_inference_timesteps: int = Field(default=10, ge=4, le=30)
```

### Error Handling

**Source:** `ai-backend/app/api/webrtc.py` lines 329-347; `web-ui/server/app/domain/ai_backend_client.py` lines 301-321  
**Apply to:** backend streaming failure, Web UI SSE failure, evidence failure categories.

```python
raise HTTPException(
    status_code=status.HTTP_502_BAD_GATEWAY,
    detail={
        "code": "call_tts_failed",
        "message": "Speech playback failed",
        "engine_id": payload.engine_id,
    },
)
```

### Cancellation

**Source:** `ai-backend/app/call/session.py` lines 748-756 and 882-896  
**Apply to:** streaming chunk producer, async queue consumer, and per-chunk enqueue loop.

```python
await self.cancel_ai_turn()
...
if active is not None:
    cancel = getattr(active, "cancel", None)
    if callable(cancel):
        cancel()
...
stop = getattr(self.outbound_audio_track, "stop_current", None)
```

### First Audio Event

**Source:** `ai-backend/app/call/session.py` lines 813-827 and `web-ui/server/app/api/calls.py` lines 462-464  
**Apply to:** first streamed chunk only.

```python
playback_seconds = await self._queue_outbound_audio(...)
self.state = "speaking"
audio_started_event = simple_event(AI_AUDIO_STARTED_EVENT, ...)
await self.emit_event(audio_started_event)
```

### Transport Boundary

**Source:** `ai-backend/app/call/tracks.py` lines 98-119 and 288-309  
**Apply to:** every emitted VoxCPM2 chunk.

```python
samples = _wav_bytes_to_int16(wav_bytes, target_sample_rate=self.sample_rate)
if samples.size:
    await self._queue.put(samples)
return duration_seconds
```

### Evidence Strictness

**Source:** Phase 7 verifier lines 137-166 and 287-310  
**Apply to:** Phase 8 evidence verifier.

```python
_require_fields(payload, CALL_FLOW_REQUIRED_FIELDS, label="call-flow JSON")
_verify_no_raw_error_leak(payload, label="call-flow JSON")
_require_number(payload.get("warm_call_ttfa_ms"), label="warm_call_ttfa_ms")
```

### OMEN Deployment

**Source:** `AGENTS.md` OMEN Deployment section  
**Apply to:** any live evidence run that needs deployment.

Use only `scripts/deploy-omen.sh`. Do not create ad-hoc OMEN scripts, manual scheduled-task changes, or hidden-process launchers.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `ai-backend/app/models/<streaming contract helper, if created>` | utility/model | streaming | The registry has `supports_streaming` metadata, and VoxCPM2 has benchmark evidence, but the repo has no live-call TTS chunk protocol or sync-generator-to-async-consumer bridge yet. Prefer adding the contract in `tts_registry.py`; create a helper only if planner needs to keep registry small. |

## Metadata

**Analog search scope:** `ai-backend/app`, `ai-backend/tests`, `web-ui/server/app`, `web-ui/server/tests`, `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency`, `.planning/PROJECT.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`  
**Files scanned:** 22465 under AI backend, Web UI server, and Phase 7 planning scope  
**Pattern extraction date:** 2026-05-11  
**Project instructions applied:** `AGENTS.md`; no root `CLAUDE.md`, `.claude/skills`, or `.agents/skills` were present.
