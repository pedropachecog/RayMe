# Phase 09: Integrate Faster Qwen3-TTS 1.7B Into Live Calls - Pattern Map

**Mapped:** 2026-07-31
**Scope:** AI backend worker/runtime, live-call flow control, Web server token-to-speech scheduling, saved voice identity, browser readiness, canonical deployment, tests, and evidence
**Pattern families:** 5
**Critical contract:** `.planning/LIVE-CALL-INVARIANTS.md`

## File Classification

The phase artifacts name a broad cross-tier change. The table below separates files that are explicit in `09-CONTEXT.md` / `09-RESEARCH.md` from files implied by the locked identity, readiness, migration, test, and evidence contracts.

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `ai-backend/app/models/tts_qwen3_protocol.py` (new) | model / IPC schema | event-driven, streaming | `ai-backend/app/models/tts_registry.py` Pydantic contracts + `tts_voxcpm2.py` worker events | partial; no versioned IPC analog |
| `ai-backend/app/models/tts_qwen3_worker.py` (new) | service / CUDA worker | streaming, event-driven, file-I/O | `ai-backend/app/models/tts_voxcpm2_worker.py` | role-match; cancellation loop must differ |
| `ai-backend/app/models/tts_qwen3.py` | service / adapter supervisor | streaming, subprocess IPC | `ai-backend/app/models/tts_voxcpm2.py` | exact role/data-flow analog |
| `ai-backend/app/models/tts_registry.py` | model / registry | request-response, streaming contracts | existing `TtsEngineMetadata`, `TtsSynthesisInput`, `TtsAudioChunk` | exact in-file pattern |
| `ai-backend/app/models/engine_metadata.py` | config / status roster | request-response | existing `ENGINE_METADATA` | exact in-file pattern |
| `ai-backend/app/models/model_manager.py` | service / residency manager | event-driven, request-response | existing one-hot `switch_tts_engine()` | exact role; synchronous load is an anti-pattern |
| `ai-backend/app/config.py` (if model path is settings-owned) | config | request-response | existing immutable `AiBackendSettings` | role-match |
| `ai-backend/app/api/tts.py` | controller | request-response | existing typed request/base64 validation | role-match; exception taxonomy must change |
| `ai-backend/app/api/webrtc.py` | controller | streaming, request-response | existing turn-scoped `/speak`, `/interrupt`, `/end` routes | exact boundary analog |
| `ai-backend/app/call/session.py` | service / call scheduler | streaming, event-driven | existing VoxCPM2 streaming path | exact role/data-flow analog with known defects |
| `ai-backend/app/call/tracks.py` | service / paced media track | streaming, pub-sub | `QueuedAudioOutputTrack` | exact role; queue admission must be extended |
| `ai-backend/pyproject.toml`, `ai-backend/uv.lock` | config / dependency lock | batch | existing optional `tts` dependency group | exact in-file pattern |
| `ai-backend/tests/test_tts_qwen3.py` (new) | test | streaming, subprocess IPC | `ai-backend/tests/test_tts_voxcpm2.py` | exact role-match |
| `ai-backend/tests/test_tts_registry.py` | test | request-response | existing metadata roster contracts | exact in-file pattern |
| `ai-backend/tests/test_model_manager.py` | test | event-driven | existing one-hot/failure-containment tests | exact in-file pattern |
| `ai-backend/tests/test_call_session.py` | test | streaming, event-driven | existing slow Vox stream and interrupt regressions | exact in-file pattern |
| `ai-backend/tests/test_webrtc_signaling.py` | test | request-response, streaming | existing `/speak` and control route tests | exact role-match |
| `web-ui/server/app/domain/call_tts_segments.py` (new) | utility / incremental segmenter | transform, streaming | `web-ui/server/app/api/calls.py` token loop | partial; no segmenter exists |
| `web-ui/server/app/api/calls.py` | controller / turn pump | streaming, event-driven | existing SSE token loop and backend bridge | exact insertion point; current full accumulation is forbidden |
| `web-ui/server/app/domain/call_service.py` | service / persistence and voice resolution | CRUD, file-I/O | existing message writeback and saved asset lookup | exact role-match |
| `web-ui/server/app/domain/voice_service.py` | service / saved voices | CRUD, file-I/O, request-response | existing Vox engine-settings validation | role-match; Qwen may not downgrade modes |
| `web-ui/server/app/api/voices.py` | controller | CRUD, file-I/O, request-response | existing preview/save/test-play routes | exact boundary analog |
| `web-ui/server/app/domain/ai_backend_client.py` | provider / backend bridge | request-response, streaming control | existing typed status and safe processing errors | exact role-match |
| `web-ui/server/app/domain/settings_service.py` | service / persisted config | CRUD | exact `endpoint_settings` normalization | exact in-file pattern |
| `web-ui/server/alembic/versions/0003_qwen3_engine_identity.py` (new) | migration | batch, CRUD | `0002_voice_storage.py` + `tests/test_migrations.py` | role-match |
| `web-ui/server/tests/test_call_tts_segments.py` (new) | test | transform, streaming | `web-ui/server/tests/test_calls.py` scripted completion/backend fixtures | role-match |
| `web-ui/server/tests/test_calls.py` | test | streaming, CRUD | existing SSE sequence, writeback, interrupt, sanitized-error tests | exact in-file pattern |
| `web-ui/server/tests/test_voices.py` | test | CRUD, file-I/O | existing transcript-guided validation and preview/test-play tests | exact in-file pattern |
| `web-ui/server/tests/test_migrations.py` | test | batch, CRUD | existing upgrade-to-head SQLite fixture | exact in-file pattern |
| `web-ui/client/src/lib/api/types.ts` | model / API types | request-response | existing engine/status/voice interfaces | exact in-file pattern |
| `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` | component | event-driven | existing metadata-driven engine cards | exact in-file pattern |
| `web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte` | component | event-driven | existing engine label/caveat switch | exact in-file pattern |
| `web-ui/client/src/routes/voice-lab/+page.svelte` | component / route | CRUD, request-response | existing upload/transcribe/preview/save/test flow | exact in-file pattern |
| `web-ui/client/tests/unit/voice-lab.test.ts` | test | static contract, request-response | existing source/API contract tests | exact in-file pattern |
| `web-ui/client/tests/e2e/voice-lab.spec.ts` | test | request-response, browser event-driven | existing mocked settings/Voice Lab workflows | exact in-file pattern |
| `web-ui/client/tests/unit/settings.test.ts`, `web-ui/client/tests/e2e/settings-connection.spec.ts` | test | request-response | existing hard-coded engine-status fixtures | exact in-file pattern |
| `scripts/deploy-omen.sh` | deployment / config | batch, remote process control | existing optional VoxCPM2 verification branch | exact role-match; this is the only permitted deploy path |
| `09-evidence-manifest.json` (new) | config / eval dataset | batch | Spike 005/006 scenario constants and result schemas | partial |
| `09-run-omen-evidence.py` (new) | utility / hardware evaluator | batch, streaming, file-I/O | Spike 005 `soak_probe.py` + Spike 006 `live_contract_probe.py` | exact purpose analog |
| `09-verify-evidence.py` (new) | utility / independent verifier | batch, transform | Spike result gates | partial; existing probes self-score instead of independently recomputing |

`web-ui/server/app/storage/models.py` already stores `Voice.default_engine` and nullable `reference_transcript`; Phase 09 needs a data migration and boundary validation, not a new column. Avoid a needless schema rewrite unless planning finds a genuinely missing readiness/provenance field.

## Pattern Family 1: Worker Isolation, IPC, and Native Streaming

### `ai-backend/app/models/tts_qwen3.py`

**Analog:** `ai-backend/app/models/tts_voxcpm2.py`

**Imports and supervisor ownership** (`tts_voxcpm2.py:1-26,44-59`):

```python
import queue as thread_queue
import subprocess
import sys
import threading
from collections.abc import Callable, Iterable

from app.models.tts_registry import (
    ImportGatedTtsAdapter,
    TtsAudioChunk,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)

class VoxCpm2TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "voxcpm2"
    required_modules = ("voxcpm",)
    synthesis_enabled = True
```

Reuse the ownership shape: adapter fields own the `Popen`, the stdout-reader queue, and the worker lifecycle. Replace the placeholder `Qwen3TtsAdapter(ImportGatedTtsAdapter)` currently at `tts_qwen3.py:6-8`; its current `engine_id = "qwen3_0_6b"` and `required_modules = ("qwen_tts",)` are explicitly obsolete.

**Spawn pattern** (`tts_voxcpm2.py:242-267`):

```python
ai_backend_root = Path(__file__).resolve().parents[2]
env = dict(os.environ)
_sanitize_python_hash_seed(env)
env["PYTHONPATH"] = str(ai_backend_root) if not existing_pythonpath else ...
self._worker = self._process_factory(
    [sys.executable, "-m", "app.models.tts_voxcpm2_worker"],
    cwd=str(ai_backend_root),
    env=env,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
    bufsize=1,
)
```

Copy the spawn environment, line-buffered pipes, injectable `process_factory`, and stdout reader. Substitute the Qwen worker module and immutable local model path. Do not import Torch or `faster_qwen3_tts` in the parent before Windows spawn.

**Worker shutdown pattern** (`tts_voxcpm2.py:329-346`):

```python
self._worker = None
self._worker_lines = None
if worker.poll() is None:
    worker.terminate()
    try:
        worker.wait(timeout=5)
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait(timeout=5)
```

Reuse the terminate-then-kill containment. Add request-scoped cancel acknowledgement with the locked two-second hard deadline before the process-level fallback.

**Chunk conversion pattern** (`tts_voxcpm2.py:218-235`):

```python
if line.startswith(WORKER_CHUNK_PREFIX):
    payload = json.loads(line[len(WORKER_CHUNK_PREFIX) :])
    yield TtsAudioChunk(
        engine_id=self.engine_id,
        chunk_index=int(payload["chunk_index"]),
        wav_bytes=base64.b64decode(payload.get("wav_b64") or b"", validate=True),
        sample_rate=int(payload["sample_rate"]),
        duration_ms=float(payload["duration_ms"]),
        generated_at_ms=float(payload["generated_at_ms"]),
    )
```

The Qwen adapter must validate a typed, versioned event before this conversion, enforce the exact `request_id`, monotonic chunk indexes/timestamps, byte and cumulative duration ceilings, and exactly one terminal event.

**Do not copy:**

- `VoxCpm2TtsAdapter.synthesize()` at lines 80-118 or `_synthesize_in_worker()` at 186-208 into the Qwen live path. Qwen calls may never fall back from `stream()` to whole synthesis.
- `_iter_worker_lines()` resets its timeout after every line (`tts_voxcpm2.py:300-327`) but has no request identity. Qwen needs request-scoped terminal validation and a cancellation watchdog.
- Raw string prefixes are not enough for the Phase 09 protocol; use Pydantic discriminated command/event models.

### `ai-backend/app/models/tts_qwen3_worker.py`

**Analog:** `ai-backend/app/models/tts_voxcpm2_worker.py`

**CUDA stays inside the worker** (`tts_voxcpm2_worker.py:59-68`):

```python
def _runtime() -> Any:
    global _RUNTIME
    if _RUNTIME is None:
        require_torch_cuda_runtime("VoxCPM2")
        from voxcpm import VoxCPM
        runtime = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)
        _assert_runtime_uses_cuda(runtime)
        _RUNTIME = runtime
    return _RUNTIME
```

Copy the lazy worker-local import and singleton ownership. Qwen replaces this with the exact local 1.7B snapshot, bfloat16/SDPA/Torch backend, CUDA graph warmup, and runtime/model/CUDA handshake from `09-AI-SPEC.md`.

**Immediate yield pattern** (`tts_voxcpm2_worker.py:93-139`):

```python
for generated in generate_streaming(**generate_kwargs):
    ...
    _emit(WORKER_CHUNK_PREFIX, {"chunk_index": chunk_index, ...})
    chunk_index += 1
...
_emit(WORKER_DONE_PREFIX, {"chunk_count": chunk_index})
```

Keep immediate per-chunk emission and generator exhaustion as the authoritative normal terminal. For Qwen, `timing["is_final"]` is diagnostic only.

**Live-call violation in the superficially similar worker:** `main()` at `tts_voxcpm2_worker.py:37-56` reads stdin and then calls `_handle_stream()` synchronously. While that generator runs it cannot receive `cancel`. Qwen must use a dedicated stdin reader thread/event so barge-in, hangup, switch, and close can signal the active request while native CUDA generation is still running.

### `ai-backend/app/models/tts_qwen3_protocol.py`

**Closest code patterns:** Pydantic contracts in `tts_registry.py:38-89`; IPC framing/lifecycle in `tts_voxcpm2.py:29-39,210-240`.

Use `BaseModel`, `Field`, and `Literal` exactly as existing backend contracts do. The source-of-truth event skeleton is `09-AI-SPEC.md:480-512`; do not invent untyped dictionaries. Commands need at least `schema_version`, discriminated operation, bounded `request_id`, and only RayMe-owned voice/cache identifiers. Events need validated `loaded`, `prewarm ready/failed`, `chunk`, and exactly one of `done/cancelled/error`.

No close existing analog covers all required properties. The planner should treat the AI spec as authoritative where it is stricter than VoxCPM2.

### `ai-backend/tests/test_tts_qwen3.py`

**Analog:** `ai-backend/tests/test_tts_voxcpm2.py`

The existing worker double is the right seam (`test_tts_voxcpm2.py:95-181`): scripted stdin parses operations, scripted stdout queues events, and the fake process records `terminate`/`kill`. Reuse dependency injection through `process_factory`.

The no-fallback assertion is concrete (`test_tts_voxcpm2.py:250-271`):

```python
with pytest.raises(ValueError, match="streaming synthesis failed"):
    list(adapter.stream(_request()))
assert process.ops == ["load", "stream"]
assert "synthesize" not in process.ops
```

Qwen tests must extend this to malformed schema/version, wrong request id, duplicate terminal, non-monotonic chunks, invalid audio/rate, blank/mismatch preflight, capacity-one prompt replacement, ceiling/non-natural EOS, cancel acknowledgement, cancel timeout and forced termination, and engine recovery. Never make these tests import or download the real model locally.

## Pattern Family 2: Registry, One-Hot Residency, Readiness, and API Errors

### `ai-backend/app/models/tts_registry.py` and `engine_metadata.py`

**Canonical contracts** (`tts_registry.py:17-55,81-118`):

```python
class EngineSwitchState(StrEnum):
    IDLE = "idle"
    LOADING = "loading"
    RESIDENT = "resident"
    UNAVAILABLE = "unavailable"

class TtsEngineMetadata(BaseModel, frozen=True):
    id: str
    label: str
    requires_transcript: bool = False
    supports_streaming: bool = False
    availability: TtsEngineAvailability = Field(default_factory=TtsEngineAvailability)

@runtime_checkable
class TtsStreamingAdapter(Protocol):
    def stream(self, request: TtsSynthesisInput) -> Iterable[TtsAudioChunk]: ...
```

Replace the exact old roster id in both metadata tables with `qwen3_1_7b`, label it `Qwen3-TTS 1.7B-Base`, set `requires_transcript=True` and `supports_streaming=True`, and update runtime evidence/caveats truthfully. Preserve `f5` as the single default. Compatibility belongs at persisted/read boundaries, not as a second selectable `qwen3_0_6b` adapter.

`TtsSynthesisInput` already carries reference bytes, content type, and transcript (`tts_registry.py:58-69`). Extend it only with generic request/turn/cache/cancellation fields actually needed across the adapter boundary; do not leak upstream runtime internals into browser APIs.

### `ai-backend/app/models/model_manager.py`

**One-hot order** (`model_manager.py:100-145`):

```python
previous = self.resident_tts_engine
self.loading_engine = engine_id
target.state = "loading"
if previous is not None:
    self._unload_engine(previous)
    self._statuses[previous].resident = False
    self._statuses[previous].state = "idle"
self._load_engine(engine_id)
target.resident = True
target.state = "resident"
self.resident_tts_engine = engine_id
```

Preserve unload-before-load and the invariant that `health()` reports one resident (`model_manager.py:147-169`). Extend status with separate prompt readiness (`none/prewarming/ready/failed`), cache identity timestamps, and sanitized error codes.

**Do not copy the blocking boundary:** `switch_tts_engine()` directly calls synchronous `_load_engine()` at lines 128-129. Calling it from the event loop hides a 90-second Qwen load even if `state="loading"` was assigned. Add an async prepare/load seam around the worker and return observable state before awaiting completion. Do not weaken one-hot order to gain responsiveness.

**Failure containment test pattern** (`test_model_manager.py:235-246,282-310`):

```python
assert events.index("f5:unload") < events.index("xtts_v2:load")
...
assert statuses["voxcpm2"]["available"] is False
for engine_id in (...):
    assert statuses[engine_id]["available"] is True
_assert_no_raw_exception_text(health)
```

Use the same event-list assertions for Qwen one-hot order, event-loop responsiveness during fake slow load/prewarm, prompt invalidation on edit/switch/unload, and Qwen-only failure containment.

### `ai-backend/app/api/tts.py`, `api/webrtc.py`, and Web backend client

**Boundary validation pattern** (`api/tts.py:22-42,100-138`): request fields are bounded with Pydantic and base64 is decoded with `validate=True`, empty/oversized input gets structured 4xx detail.

**Current anti-pattern** (`api/tts.py:51-87`):

```python
try:
    manager.switch_tts_engine(target_engine)
    result = adapter.synthesize(...)
except Exception as exc:
    _mark_engine_unavailable(manager, target_engine)
    raise HTTPException(status_code=502, detail={"code": "tts_failed", ...})
```

Do not mark Qwen unavailable for a blank transcript, mismatch, bad target length, or generation ceiling. Implement typed categories:

- request/reference validation: actionable 4xx, model remains usable;
- voice prewarm failure: that voice key becomes `failed`, model may stay resident;
- generation ceiling/cancel: request terminal is non-success, health policy decides whether reload is needed;
- malformed IPC, identity/CUDA mismatch, worker crash/hang: terminate worker and mark Qwen unavailable.

The Web client currently maps every generic 4xx to `unreachable` (`ai_backend_client.py:288-294`) while only 5xx uses `_processing_error_from_response()` (`301-321`). Extend safe-detail parsing for the stable Qwen validation statuses; never pass tracebacks, model/cache paths, full transcripts, or raw worker messages through.

**Turn boundary pattern** (`api/webrtc.py:73-93,328-398`): `SpeakRequest` is strict (`extra="forbid"`), is bound to `turn_id`, and delegates state/event ownership to `CallSession`. Preserve that single public API. Add prepare/prewarm/finalize semantics without creating an upstream TTS endpoint in the browser or Web server.

**Do not copy:** `_tts_adapter()` calls synchronous `switch(engine_id)` at `api/webrtc.py:540-551`. Qwen call preparation must make load and prompt readiness visible before the first speech request instead of freezing `/speak`.

## Pattern Family 3: Live Call Stream, Paced Track, and Incremental LLM Segments

### `ai-backend/app/call/session.py`

**Route streaming by capability** (`session.py:112-117`) currently hard-codes VoxCPM2:

```python
return (
    engine_id == "voxcpm2"
    and adapter is not None
    and callable(getattr(adapter, "stream", None))
)
```

Extend this explicitly to the canonical Qwen id or make it metadata/capability-driven while retaining tests that no non-stream adapter is misrouted.

**Bounded startup pattern** (`session.py:47-51,1117-1129`):

```python
CALL_TTS_STREAM_START_MIN_CHUNKS = 2
CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS = 0.75
CALL_TTS_STREAM_MAX_STARTUP_BUFFER_SECONDS = 1.25
...
return buffered_enough or waited >= CALL_TTS_STREAM_MAX_STARTUP_BUFFER_SECONDS
```

Reuse the explicit upper-bound idea and the first-playback event sequence. Preserve the immediate carrier (`session.py:1157-1187`) with only first-known fields:

```python
tts_playback={
    "streaming_used": True,
    "fallback_used": False,
    "whole_wav_fallback_used": False,
    "first_chunk_generated_ms": first_chunk["generated_at_ms"],
    "first_chunk_enqueued_ms": first_chunk_enqueued_ms,
    "ai_audio_started_ms": ai_audio_started_ms,
    "chunk_count_at_start": len(pending_chunks),
    "startup_buffered_audio_ms": buffered_audio_ms,
}
```

Final fields stay in `tts_playback_final` only (`session.py:1094-1112,1293-1325`). Do not backfill total generation/playout into `ai_audio_started`.

**Current thread bridge violation** (`session.py:1077-1079,1214-1233`):

```python
queue: asyncio.Queue[Any] = asyncio.Queue()
...
loop.call_soon_threadsafe(queue.put_nowait, item)
```

Replace it with `asyncio.Queue(maxsize=2)` and a producer-side blocking put such as `asyncio.run_coroutine_threadsafe(queue.put(item), loop).result()` with cancellation-aware terminal draining. `put_nowait` scheduled onto the loop is neither backpressure nor safe once capacity is added.

**Early playback invariant** (`session.py:1276-1283`):

```python
# RayMe is a live phone call. Never wait for full TTS stream
# completion before first playback as a smoothness fix.
if startup_buffer_ready():
    await start_playback_from_buffer()
...
await enqueue_stream_chunk(pending_chunks[-1], first=False)
```

Preserve this exact product shape. Qwen `non_streaming_mode=True` may prefill one safe text segment only; it cannot justify collecting the native generator or waiting for the full assistant response.

**Cancellation gap** (`session.py:1360-1374`): the current method cancels the asyncio task, stops the outbound track, and drains a local buffer, but never calls the adapter. Qwen needs to record cancellation first, invoke `adapter.cancel(request_id)`, keep draining/discarding worker protocol events until the matching `cancelled` terminal (or force termination), and suppress `ai_done`.

**Regression analogs** (`test_call_session.py`):

- Slow stream: lines 1265-1329 assert `ai_audio_started` and outbound chunks exist while `adapter.stream_completed` is still false.
- Immediate/final separation: lines 1193-1252 assert no `buffered_until_complete`, `total_generation_ms`, or `total_playback_ms` in the immediate event.
- Late-chunk interruption: lines 1390-1437 assert `stop_current`, no normal `ai_done`, and only pre-interrupt chunks.
- No whole fallback at adapter level: `test_tts_voxcpm2.py:250-297` must remain green unchanged.

Add Qwen-specific twins plus a deliberately slow consumer that asserts bridge high-water `<=2`, positive producer blocking, exact chunk order/no drops, and zero post-cancel enqueue.

### `ai-backend/app/call/tracks.py`

**Pacing pattern** (`tracks.py:75-96,198-212`): every `recv()` calls `_pace_realtime()`, advances fixed 20 ms frames, and emits RTP continuously. Preserve it.

**Current playout backlog violation** (`tracks.py:57-62,98-119`):

```python
self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue()
...
if samples.size:
    await self._queue.put(samples)
```

A capacity-two bridge alone is fake boundedness because the consumer can immediately pour complete chunks into this unbounded track faster than `recv()` consumes them. Add pending-sample/audio-duration accounting that includes `_buffer`, await admission credit over a tested bound, decrement/notify as `_next_samples()` consumes frames, and expose high-water/underflow/discard metrics.

Reuse `stop_current()` (`tracks.py:141-145`) as the drain point, extended to wake blocked producers and reset pending-sample accounting atomically.

### `web-ui/server/app/domain/call_tts_segments.py` and `api/calls.py`

**Insertion point:** the existing LLM token loop (`calls.py:357-397`) already yields `ai_token` immediately. Feed the new deterministic segmenter at the same point.

**Current full-response violation** (`calls.py:361,385,399-443`):

```python
accumulated: list[str] = []
...
accumulated.append(token)
yield _sse({"type": "ai_token", ...})
...
visible_text = "".join(accumulated)
tts_task = asyncio.create_task(_speak_call(..., {"text": visible_text, "final_chunk": True}))
```

This makes a fast native TTS engine still behave like generated-audio playback. Replace it for Qwen with the locked incremental pump:

```python
async for token in llm_tokens:
    yield ai_token_event(token)
    for segment in segmenter.feed(token):
        await speech_turn.submit(segment)

tail = segmenter.finish()
if tail:
    await speech_turn.submit(tail)
await speech_turn.finish()
```

The segmenter has no close codebase analog. It must prefer `.?!` and safe newline boundaries, retain punctuation, avoid tiny fragments, force a natural phrase boundary before 60 words, and flush one final tail. Use only deterministic stdlib logic; validate the 60-word ceiling again in the AI backend.

The speech scheduler must be bounded and turn-scoped. Non-final submissions return after bounded acceptance rather than waiting for playout. One Qwen generator stays active at a time while later LLM tokens continue arriving and earlier audio plays.

**Persistence anti-pattern:** `record_ai_speech()` currently runs before `_speak_call()` at `calls.py:407-443`. Move durable `ai_speech` writeback to the single normal terminal after final playout. Cancel/error retains transient `ai_token` UI events but no complete assistant speech row.

**Test fixture pattern** (`web-ui/server/tests/test_calls.py:54-148`): extend `ScriptedCallBackend.speak_call()` and `ScriptedCompletionClient` with events that hold the LLM open after a complete first sentence. Assert the first non-final speech submission happens while the completion stream remains open. Existing SSE/writeback assertions at lines 639-700 are the base, but the current expectation of one whole `speak_call` per turn must change for Qwen segments.

The cancellation test at `test_calls.py:1008-1025` already asserts both server generation cancellation and backend interrupt. Add database assertions proving cancel-before-audio and cancel-after-audio persist zero complete `ai_speech` rows.

## Pattern Family 4: Saved Voice Identity, Migration, Validation, and Visible UI

### `web-ui/server/app/domain/voice_service.py`, `api/voices.py`, and `call_service.py`

**Existing durable flow** (`voice_service.py:139-156`):

```python
voice = Voice(
    id=new_voice_id(),
    name=str(payload["name"]),
    default_engine=str(payload["default_engine"]),
    reference_transcript=payload.get("reference_transcript"),
    metadata_json=metadata,
)
asset.voice_id = voice.id
self.session.add(voice)
await self.session.commit()
```

Keep the voice/asset ownership and CRUD paths. Normalize the exact legacy id to `qwen3_1_7b` at save/read/update boundaries during the upgrade window, and block missing/blank Qwen transcript before commit, preview, test-play, call start, and final backend synthesis.

**Saved reference path pattern** (`call_service.py:218-264`): resolve the newest saved sample asset, require `Path(asset.storage_path).name == asset.storage_path`, build the path under the configured RayMe blob directory, and read the saved transcript. Keep the containment check.

**Privacy fix required:** do not copy the current logs at `call_service.py:221-254`; they expose `blob_dir`, `expected_path`, and directory contents. Qwen logs/evidence may contain only opaque voice/request ids, hashes, stable codes, and scalar scores.

**Superficially similar Vox validation that is forbidden for Qwen** (`voice_service.py:440-459`):

```python
if voxcpm2_settings["cloning_mode"] == "transcript_guided" and not str(reference_transcript or "").strip():
    voxcpm2_settings = {**voxcpm2_settings, "cloning_mode": "reference_only"}
    warnings.append(...)
```

Qwen must never silently downgrade to x-vector/reference-only mode. Blank or grossly mismatched transcript is a blocking, sanitized validation error. Reuse RayMe STT and the AI spec's tolerant normalization/dual-threshold gate; pass the user-approved exact transcript into ICL after validation.

### `web-ui/server/alembic/versions/0003_qwen3_engine_identity.py`

**Analog:** `0002_voice_storage.py:15-18,38-78` for revision metadata and Alembic `upgrade()`/`downgrade()` structure; `tests/test_migrations.py:33-47` for upgrade-to-head against a temporary SQLite database.

The migration should update only exact values:

- `voices.default_engine == "qwen3_0_6b"` to `"qwen3_1_7b"`;
- `app_settings.key == "endpoint_settings"` JSON key `tts_default_engine` when its exact value is old id.

Unknown engine strings must remain untouched/rejected. Make upgrade idempotent. A downgrade may reverse the exact canonical value only if the project migration policy expects reversible data migrations; document potential ambiguity rather than rewriting arbitrary Qwen values.

The stored names are fixed by code: `Voice.default_engine` / `reference_transcript` at `storage/models.py:184-192`, `SETTINGS_KEY = "endpoint_settings"` and `tts_default_engine` at `settings_service.py:13-27,105-122`.

### Browser types and components

**Status type pattern** (`client/src/lib/api/types.ts:342-393`): preserve the server-driven engine list, `loading_engine`, per-engine availability, and metadata fields. Add separate model and selected-voice prompt readiness shapes rather than collapsing both to one boolean.

**Metadata-driven card pattern** (`TtsEnginePicker.svelte:32-63`): cards remain visible, unavailable cards are disabled, and the reason is displayed from backend metadata. Update the Qwen id/label/caveat copy and render honest `loading`/`resident` plus `prewarming`/`ready`/`failed` states.

**Normalization bug to avoid** (`voice-lab/+page.svelte:175-230`): the function builds a map from `DEFAULT_TTS_ENGINES` but returns only `DEFAULT_TTS_ENGINES.map(...)`. A server-returned new id can be inserted into the map and then silently dropped. Update the fallback roster and preserve returned canonical metadata rather than filtering it away.

**Existing visible async-state pattern** (`voice-lab/+page.svelte:127-153,279-337`): explicit string unions drive preview/save progress, reactive validation blocks missing required transcript, and failures preserve user inputs. Reuse this pattern for model loading and prompt prewarming. Do not show the call ready while the selected prompt is not ready.

**Identity sweep:** replace old hard-coded labels/ids in `types.ts`, `TtsEnginePicker.svelte`, `VoiceAssignmentSelect.svelte:20-38,100-102`, `voice-lab/+page.svelte`, client settings fixtures, unit tests, and E2E fixtures. The old id may appear only in migration/compatibility tests after Phase 09.

**Browser test analogs:**

- `voice-lab.test.ts:353-368` protects user input on synthesis failure; extend with Qwen transcript mismatch and readiness errors.
- `voice-lab.spec.ts:334-400` mocks status metadata; add distinct loading/resident and prewarming/ready/failed states.
- `voice-lab.spec.ts:548-570` demonstrates delayed backend response plus visible row-scoped progress; reuse for prewarm without freezing controls.

## Pattern Family 5: Dependencies, Canonical Deployment, and Evidence

### `ai-backend/pyproject.toml` and `uv.lock`

The optional dependency pattern is `pyproject.toml:20-26`:

```toml
[project.optional-dependencies]
tts = [
  "f5-tts==1.1.17",
  "coqui-tts==0.27.5",
  "qwen-tts==0.1.1",
  "voxcpm==2.0.2",
]
```

Add the immutable Git source at commit `a70afc0f81f7f5f8801c3227968f1102f43f211c` and regenerate `uv.lock`. Keep `qwen-tts==0.1.1` and `transformers==4.57.3` compatible with the accepted OMEN runtime. Do not let the dependency's broad Torch constraint replace `torch==2.10.0+cu126` with a CPU/default-index wheel.

### `scripts/deploy-omen.sh`

This file is the sole deployment analog and target. Do not create any new OMEN launcher/deploy script.

**Exact-commit safety pattern** (`deploy-omen.sh:20,51-74`): derive local HEAD, update OMEN, and fail unless deployed HEAD equals expected HEAD. Preserve it.

**Optional hardware verification pattern** (`deploy-omen.sh:108-289`): a feature flag performs dependency sync, reasserts CUDA Torch, imports the exact runtime, checks CUDA/model/sample-rate/VRAM, emits marker-prefixed JSON, and copies it back after the remote command. Add an analogous Qwen branch under `RAYME_OMEN_VERIFY_QWEN3=1`; do not replace the existing Vox verification.

**Canonical launcher pattern** (`deploy-omen.sh:295-315`): only this script writes `start-ai-backend.cmd` and `start-web-ui.cmd`. Add immutable non-secret model-dir/revision variables to the AI launcher here if needed. Never write launchers elsewhere.

**Runtime verification pattern** (`deploy-omen.sh:291-294`): after every sync, assert Torch is not CPU-only, CUDA is present, `torch.cuda.is_available()` is true, and report the device. Extend with exact faster package source/version, model revision/local snapshot, bfloat16 CUDA parameters, sample rate 24000, and one-hot residency.

**Health pattern** (`deploy-omen.sh:411-425`): verify both AI health and Web settings. Phase 09 must additionally verify `/webrtc/status`, Qwen model readiness, selected voice prompt readiness, normal streamed call flow, barge-in, hangup/recovery, and commit-matched evidence. Do not silently promote Qwen to global default; the user selects the saved Qwen voice for the acceptance call.

### `09-run-omen-evidence.py`, manifest, and verifier

**Longitudinal analog:** Spike 005 `soak_probe.py`.

- `acoustic_metrics()` (`67-109`) computes finite/peak/RMS/silence/clipping/centroid/high-frequency/flatness.
- `run_turn()` (`132-196`) records first playback before completion, TTFA, RTFx, natural EOS, chunk count, Torch/system GPU memory, and a deterministic PCM hash.
- gates (`305-324`) compare early/late RMS, centroid, flatness, RTFx, TTFA, reserved memory, validity, natural EOS, and 50-turn completion.
- reel selection (`358-363`) uses turns 1/25/46/50.

**Live contract analog:** Spike 006 `live_contract_probe.py:54-159,226-260` uses a capacity-two queue, checks stop between puts/yields, records first consume vs producer completion, interruption latency, post-cancel chunks, and emits schema-versioned JSON.

**STT analog:** Spike 005 `evaluate_stt.py:26-48,51-105` normalizes lexical words, computes edit distance/WER, compares early and late buckets, and records schema-versioned results.

The integrated runner should call the production RayMe worker/call path, not a parallel model-only implementation. Private reference WAV/transcript and generated speech stay local; committed evidence contains opaque fixture ids/hashes and scalar metrics.

**Do not copy self-trust:** the spike probes write `overall_status` from their own gate booleans. `09-verify-evidence.py` must independently load raw samples, validate schema/commit/runtime/model/fixture hashes and recency, recompute thresholds, reject missing critical scenarios, scan for private paths/transcripts/audio/tokens, and ignore any stored `overall_status` as proof.

## Shared Patterns

### Stable, sanitized errors

**Sources:** `ai-backend/app/api/tts.py:73-87`, `web-ui/server/app/domain/ai_backend_client.py:67-84,301-321`, `web-ui/server/tests/test_calls.py:773-829`.

Public responses use stable `code` + fixed/actionable `message`. Tests render the entire response and assert no `Traceback`, `/home/`, `C:\`, or model path. Qwen adds transcript-required, transcript-mismatch, prompt-prewarm-failed, generation-ceiling, cancellation-timeout, worker-protocol, and runtime-identity codes without exposing reference content.

### One public API and saved-voice path containment

**Sources:** `api/webrtc.py:328-398`, `voice_service.py:233-238`, `call_service.py:225-264`.

The browser calls RayMe APIs only. The server resolves an opaque saved voice id to a basename-constrained RayMe blob. Never accept an arbitrary worker path, raw prompt tensor, upstream server URL, or model internals from a browser payload.

### Cancellation order

Across Web server, `CallSession`, track, adapter, and worker:

1. mark the turn cancelled and reject later segment submissions/events;
2. stop/drain audible playout and release blocked admissions;
3. send request-scoped worker cancel;
4. drain/discard late worker events until `cancelled`, or terminate after the hard deadline;
5. restore `listening` or complete `ended` state;
6. emit no normal `ai_done` and persist no complete `ai_speech`.

### Immediate versus final evidence

`ai_audio_started` contains only first-chunk/enqueue/startup fields known then. Terminal events contain generation completion, playout completion, total chunks/audio, EOS/RTF, underflow, joins, queue high-water, and terminal reason. Tests must fail if final-only fields appear in the immediate carrier.

### Testing hierarchy

- fake worker/protocol/slow streams locally;
- API/server persistence and migration in temporary SQLite;
- client readiness/errors in unit and saved Playwright workflows;
- real CUDA/model/50-turn/call-flow only on OMEN through `scripts/deploy-omen.sh`;
- final physical call remains the product-owner acceptance checkpoint after automated/deployed gates pass.

## No Close Analog Found

| File / Capability | Reason | Planner Source |
|---|---|---|
| `tts_qwen3_protocol.py` versioned request-scoped IPC | Existing Vox worker uses raw prefixes and untyped payloads | `09-AI-SPEC.md:480-532` |
| `call_tts_segments.py` incremental natural-boundary segmenter | Current code only accumulates the full LLM response | `09-RESEARCH.md` Pattern 3 and incremental pump example |
| async model + separate prompt readiness | Current manager exposes model states only and blocks during load | `09-CONTEXT.md` D-09 through D-11; `09-AI-SPEC.md` State Management |
| end-to-end playout credit | Current bridge and track queues are both unbounded | `09-RESEARCH.md` Pattern 4; `09-AI-SPEC.md` bounded live bridge |
| independent decision-ready evidence verifier | Spike scripts score their own results | `09-AI-SPEC.md` Evaluation Strategy / CI-CD Integration |

## Planner Guardrails

1. A plan that only replaces `tts_qwen3.py` is incomplete: it leaves full-LLM waiting, hidden cold load, unbounded queues, and premature persistence intact.
2. Add the slow-LLM regression before implementing the Web token-to-segment pump.
3. Add the slow-native-stream, slow-playout/backpressure, no-fallback, timing-separation, and cancellation regressions before changing call flow.
4. Keep the existing VoxCPM2 streaming/no-whole-fallback regressions green; do not generalize by weakening their assertions.
5. Treat the exact dependency source checkpoint as already product-directed but still record owner/repo/tag/commit/PyPI metadata before installation, as required by `09-RESEARCH.md`.
6. Make local deterministic tests pass before any deployment work. OMEN changes go only through `scripts/deploy-omen.sh`.
7. Do not request the user's physical call until exact deployed commit, health/readiness, normal/cancelled RayMe-shaped flows, 50-turn non-degradation, and browser evidence all pass.

## Metadata

**Analog search scope:** `ai-backend/app`, `ai-backend/tests`, `web-ui/server/app`, `web-ui/server/tests`, `web-ui/server/alembic`, `web-ui/client/src`, `web-ui/client/tests`, `scripts`, `.planning/spikes/005-*`, `.planning/spikes/006-*`

**Primary analog families:**

1. VoxCPM2 adapter/worker/protocol tests
2. TTS registry/model manager/readiness APIs
3. CallSession/QueuedAudioOutputTrack/Web server turn pump
4. Voice persistence/migrations/Voice Lab metadata UI
5. Canonical deploy and Spike 005/006 evidence harnesses

**Pattern extraction date:** 2026-07-31

