# Phase 09: Integrate Faster Qwen3-TTS 1.7B Into Live Calls - Research

**Researched:** 2026-07-31
**Domain:** Native CUDA voice-cloning runtime, live-call streaming, bounded playout, cancellation, and deployment
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Runtime And Model Identity
- **D-01:** Pin the official `faster-qwen3-tts` v0.3.2 runtime and `Qwen/Qwen3-TTS-12Hz-1.7B-Base`. Production may not float to an untested commit, package version, or model.
- **D-02:** Use a truthful canonical engine id for 1.7B (recommended: `qwen3_1_7b`). Treat the old `qwen3_0_6b` value as compatibility data only: migrate or translate existing saved records explicitly, and never let it silently select 0.6B or masquerade as 1.7B.
- **D-03:** Keep the runtime behind RayMe's one-hot TTS manager on CUDA. CPU fallback and a second resident TTS model are failures.
- **D-04:** Keep one RayMe public API. The browser and Web UI server must not call an upstream TTS server or learn upstream runtime internals.

### Voice Cloning And Transcript Protection
- **D-05:** Use the Base model's zero-shot ICL voice-cloning path with the saved reference WAV and its matching transcript. Promptless/custom-voice modes are out of scope.
- **D-06:** A missing or blank reference transcript is a blocking validation error for this engine in save, preview/test-play, call start, and backend synthesis boundaries.
- **D-07:** Add a practical alignment preflight using existing RayMe STT/transcript assets and bounded sanity checks. Grossly mismatched audio/transcript pairs must fail before long generation begins, with an actionable sanitized message. Validation must tolerate ordinary STT punctuation/casing errors and accented English.
- **D-08:** Enforce generation ceilings (tokens/chunks/audio duration relative to requested text) so a bad prompt cannot repeat or run to a token-cap-length output. A ceiling breach is an engine-scoped sanitized failure, never partial unbounded playback.

### Loading, Prewarm, And Visible State
- **D-09:** Model load and reference-prompt preparation are separate visible states. RayMe must expose `loading`, `resident`, and reference `prewarming`/`ready`/failure state instead of hiding them behind a frozen first call turn.
- **D-10:** Prewarm the selected saved voice's reference prompt before the first spoken turn when the call is prepared. Do not retain unbounded reference caches; cache ownership and eviction follow the one-hot model lifecycle.
- **D-11:** Preview and test-play may trigger the same load/prewarm path, and must surface progress and sanitized errors through existing product controls.

### Live Streaming Contract
- **D-12:** Real calls use `generate_voice_clone_streaming` only for Faster Qwen3-TTS. No whole-synthesis fallback is allowed before or after first playback.
- **D-13:** Preserve early playback. A bounded startup/jitter buffer may smooth joins, but the first playable audio must be enqueued before a deliberately slow synthesis stream completes.
- **D-14:** Bound producer-to-consumer queue capacity and apply backpressure. Do not accumulate an entire turn in memory when network or playout is slower than generation.
- **D-15:** Keep immediate timing (`first chunk`, `first enqueue`, `ai_audio_started`) separate from final timing (`generation complete`, `playout complete`, final event). Do not overwrite early metrics with completion values.
- **D-16:** The upstream `non_streaming_mode` optimization may prefill only the current safe synthesis segment; it must never cause RayMe to wait for the full assistant response or full turn audio before first playback.

### Cancellation And Failure Semantics
- **D-17:** Barge-in, explicit interrupt, hangup, engine switch, and session close must signal generation cancellation, stop/drain future audio, discard late chunks, and return the call to the correct listening/closed state promptly.
- **D-18:** A cancelled turn cannot emit normal `ai_done`, cannot persist a complete `ai_speech` artifact, and cannot leak late audio into the next turn.
- **D-19:** Faster Qwen3 failures are engine-scoped and sanitized. They may mark that engine unavailable/caveated while keeping STT, WebRTC, the backend, and other TTS engines usable.

### Evidence And Deployment
- **D-20:** Regression tests must prove slow-stream first playback before completion, bounded queueing, no whole-synthesis fallback, separate immediate/final metrics, prompt interruption, late-chunk rejection, and preservation of the existing VoxCPM2 live-stream invariant tests.
- **D-21:** Preserve the Spike 005 failure-mode gate in the integrated path: a hot-process multi-turn run must check intelligibility, audio validity, latency drift, memory drift, and early/middle/late acoustic stability.
- **D-22:** `scripts/deploy-omen.sh` is the only OMEN deployment mechanism. It must install/verify the pinned runtime and model through the canonical launchers/tasks, then verify status and a RayMe-shaped call flow before handoff for the builder's physical call.

### the agent's Discretion
- Exact compatibility migration mechanism for persisted `qwen3_0_6b` values, provided it is explicit, tested, and does not lie about model identity.
- Exact transcript similarity algorithm and tolerance, provided it catches the known gross mismatch without rejecting normal punctuation/casing/accented-English variance.
- Exact prompt-cache key, capacity, and observability fields, provided cache lifetime is bounded and tied to model residency.
- Exact native chunk size, startup-buffer duration, queue capacity, and cancellation primitive, provided measured live-call invariants and target latency hold.
- Exact UI wording and progress presentation within RayMe's existing design system.

### Deferred Ideas (OUT OF SCOPE)
- Shipping 0.6B as a separate selectable engine.
- Qwen3 custom-voice design, multilingual controls, standalone upstream server mode, GGML, or additional quantization paths.
- General redesign of Voice Lab or call UI beyond the status/error controls required for this integration.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-22 | “Voice save captures: name, engine (**F5-TTS**, **XTTS v2**, or **Qwen3-TTS** — user-selected per voice), sample audio path, reference transcript, timestamps. Qwen3-TTS uses the pinned `faster-qwen3-tts==0.3.2` runtime with `Qwen/Qwen3-TTS-12Hz-1.7B-Base`; its ICL cloning path requires a reference transcript that matches the saved sample. The former `0.6B-Base` experimental identifier is compatibility-only and must not silently load the old model.” [VERIFIED: .planning/REQUIREMENTS.md:51-52] | Truthful roster migration, reference validation/prewarm, saved-voice data migration, pinned worker/runtime, and Voice Lab/API changes below. |
| REQ-45 | “**Streaming/chunked TTS playback for every engine**: the orchestrator uses a shared chunk planner for all TTS engines. It must prefer natural sentence boundaries, enforce engine-specific token/character caps … avoid tiny unnatural fragments, start playback from the first viable chunk, stitch later chunks cleanly, and log first-chunk TTFA, total stitched playback time, and inter-chunk gaps.” [VERIFIED: .planning/REQUIREMENTS.md:83-84] | Incremental LLM-to-TTS segment pump, native per-segment streaming, playout-backed capacity, joins, and immediate/final metrics below. |
| REQ-46 | “End-to-end turn latency (user finishes speaking → AI starts speaking) is targeted at **<800 ms** (stretch: <500 ms). This is a design budget, not a blocking acceptance gate.” [VERIFIED: .planning/REQUIREMENTS.md:85-86] | Visible prewarm, four-step chunks, early playback, native TTFA/RayMe first-playback instrumentation, and deployment gates below. |
</phase_requirements>

## Summary

The selected runtime is technically viable and already passed RayMe's actual failure-mode gates on OMEN: 1.7B four-step streaming measured 368.9 ms median native TTFA and 1.46 RTFx, reserved 5,604 MiB, and stayed stable through 50 hot turns with 50/50 valid natural-EOS outputs, overall WER 0.00736, zero reserved-memory growth, and stable early/late acoustics. The capacity-two live probe started consumption at 387.3 ms while generation continued for 24.0275 s and stopped 278.3 ms after cancellation. [VERIFIED: .planning/spikes/004-b-faster-qwen3-tts-17b-cuda/README.md:37-51; .planning/spikes/005-faster-qwen3-tts-longitudinal-quality/README.md:49-58; .planning/spikes/006-faster-qwen3-tts-live-stream-contract/README.md:42-49]

This is not an adapter-only phase. Production currently has four architecture violations that would survive a naive engine swap: it waits until the LLM stream is complete before starting TTS, performs potentially long engine loads synchronously on the FastAPI event loop, bridges native chunks through an unbounded queue into another unbounded playout queue, and persists the complete `ai_speech` row before synthesis succeeds or survives cancellation. [VERIFIED: web-ui/server/app/api/calls.py:357-443; ai-backend/app/api/webrtc.py:540-560; ai-backend/app/call/session.py:1063-1087,1216-1234; ai-backend/app/call/tracks.py:54-62,98-119; web-ui/server/app/api/calls.py:399-443]

The plan must therefore land a complete turn pipeline: a supervised CUDA worker, validated request-scoped IPC, separate asynchronous model/prompt readiness, STT-backed reference preflight, incremental natural text segmentation while LLM tokens are still arriving, a bounded segment scheduler, native streaming inside each segment, playout-credit backpressure, explicit cancellation/terminal semantics, post-success persistence, UI state, identity migration, and canonical OMEN evidence. The locked `09-AI-SPEC.md` already fixes the runtime, initial inference settings, worker protocol, evaluation thresholds, and evidence dataset; plans should implement it rather than reopen those choices. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:350-470,480-555,595-719]

**Primary recommendation:** Implement `qwen3_1_7b` as a RayMe-supervised, CUDA-only, capacity-one-prompt worker and refactor Qwen call speech into a turn-scoped incremental segment pump whose backpressure reaches the paced WebRTC track; release only after deterministic contracts, the full 50-turn OMEN gate, a deployed normal/barge-in call flow, and browser-visible readiness all pass.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Engine identity and one-hot residency | API / AI backend | Worker process | `ModelManager` already owns resident engine state; the worker owns CUDA model state only. [VERIFIED: ai-backend/app/models/model_manager.py:100-169] |
| CUDA model load, warmup, prompt tensors, native generation | Worker process | API / AI backend | The locked architecture makes the spawned worker the only CUDA importer/owner; the adapter supervises it. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:380-410] |
| Reference transcript presence and alignment | API / AI backend | Web UI server | The backend is the final synthesis trust boundary; the Web server blocks save/preview/call earlier for actionable UX. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:24-28] |
| Saved voice identity/audio/transcript | Database / RayMe blob storage | Web UI server | `voices.default_engine` and `reference_transcript` are persisted, while `voice_assets.storage_path` addresses the saved blob. [VERIFIED: web-ui/server/app/storage/models.py:184-212] |
| Incremental LLM text segmentation | Web UI server | AI backend call scheduler | The Web server sees tokens as they arrive; the AI backend enforces the final segment ceiling and serializes speech work. [VERIFIED: web-ui/server/app/api/calls.py:357-399] |
| Native chunk bridge and first-audio events | API / AI backend | Worker process | `CallSession` already owns first enqueue, `ai_audio_started`, final timing, and call state. [VERIFIED: ai-backend/app/call/session.py:1063-1187,1293-1325] |
| End-to-end audio backlog bound | WebRTC playout track | Call-session bridge | A bounded bridge is insufficient while the paced track accepts unlimited arrays; playout must return admission credit as samples are consumed. [VERIFIED: ai-backend/app/call/tracks.py:54-62,75-119,151-166] |
| Visible load/prewarm state | Browser / Client | Web UI server and AI backend | The backend is authoritative; existing settings/Voice Lab controls must poll or subscribe and render it. [VERIFIED: web-ui/client/src/lib/api/types.ts:352-392; 09-CONTEXT.md:30-33] |
| Cancellation and terminal persistence | API / AI backend | Web UI server/database | Worker generation and playout stop in the AI backend; only a normal terminal event authorizes durable `ai_speech`. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:42-45] |
| Runtime/model installation and attestation | Deployment script | Worker load handshake | `scripts/deploy-omen.sh` is the sole deploy path and already writes canonical launchers/tasks. [VERIFIED: scripts/deploy-omen.sh:291-315,354-375] |

## Standard Stack

### Core

| Library / Runtime | Version | Purpose | Why Standard Here |
|-------------------|---------|---------|-------------------|
| `faster-qwen3-tts` [WARNING: flagged as suspicious — verify before using.] | v0.3.2, source commit `a70afc0f81f7f5f8801c3227968f1102f43f211c`; published 2026-07-17 | Native CUDA-graph Qwen3-TTS streaming | It is the user-selected official repository and the exact commit that passed RayMe's OMEN spikes. The official package declares version `0.3.2`. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2] [VERIFIED: PyPI registry and GSD legitimacy seam, 2026-07-31] |
| `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | snapshot `fd4b254389122332181a7c3db7f27e918eec64e3` | Full-ICL zero-shot voice cloning | The immutable official Qwen snapshot is 1.7B Base, Apache-2.0, and is the accepted model. [CITED: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base/tree/fd4b254389122332181a7c3db7f27e918eec64e3] |
| Python | OMEN 3.11.15 | Worker and AI backend runtime | The package supports Python 3.10+; the target currently runs 3.11.15. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2] [VERIFIED: read-only OMEN probe, 2026-07-31] |
| PyTorch / CUDA | `torch==2.10.0+cu126`, CUDA 12.6 | CUDA graphs and model execution | This is the working OMEN runtime; `torch.cuda.is_available()` is true on `NVIDIA GeForce RTX 3060`. [VERIFIED: read-only OMEN probe, 2026-07-31] |
| `qwen-tts` | `0.1.1` | Upstream Qwen model and prompt APIs used by the faster wrapper | v0.3.2 declares `qwen-tts>=0.1.1`; OMEN already has `0.1.1`. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/blob/a70afc0f81f7f5f8801c3227968f1102f43f211c/pyproject.toml] [VERIFIED: read-only OMEN probe, 2026-07-31] |
| `transformers` | `4.57.3` | Model/tokenizer runtime | v0.3.2 declares `transformers>=4.57,<5`; OMEN's accepted runtime is `4.57.3`. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/blob/a70afc0f81f7f5f8801c3227968f1102f43f211c/pyproject.toml] [VERIFIED: read-only OMEN probe, 2026-07-31] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic` | `2.10.6` in AI backend | Validate every command/event crossing worker IPC | Use before any worker event becomes a `TtsAudioChunk`; current dependency is exactly `"pydantic==2.10.6"`. [VERIFIED: ai-backend/pyproject.toml:9-12] |
| `soundfile` | `0.13.1` | Decode reference WAV and serialize native chunks | Reuse the installed dependency, exactly `"soundfile==0.13.1"`. [VERIFIED: ai-backend/pyproject.toml:12-15] |
| `numpy` | `2.2.6` | Mono conversion, finite/silence checks, acoustic metrics | Reuse the installed dependency, exactly `"numpy==2.2.6"`. [VERIFIED: ai-backend/pyproject.toml:12-15] |
| `huggingface-hub` | v0.3.2 constraint `>=0.36.0,<1.0` | Materialize immutable model snapshot during deploy | Resolve the exact snapshot before service start; pass only a local directory to the worker. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/blob/a70afc0f81f7f5f8801c3227968f1102f43f211c/pyproject.toml] |
| `asyncio`, `threading`, `subprocess`, `hashlib`, `difflib` | Python stdlib | Queueing, cancellation reader, worker supervision, cache hashing, edit similarity | Use these rather than adding a generic orchestration or NLP dependency. The similarity thresholds and capacity remain locked by the AI spec. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:380-430,442-455] |
| RayMe Whisper STT | existing `faster-whisper==1.2.1`, CUDA `int8_float16` | Reference/audio alignment preflight and WER evidence | Reuse the production STT engine; do not add a second transcription runtime. The exact dependency string is `"faster-whisper==1.2.1"`. [VERIFIED: ai-backend/pyproject.toml:15-17; ai-backend/app/config.py:6-10] |

### Alternatives Considered

These are documented only to prevent accidental scope drift; the choices are already locked.

| Instead of | Could Use | Tradeoff / Disposition |
|------------|-----------|------------------------|
| RayMe-supervised native Python worker | Upstream CLI or OpenAI-compatible server | Rejected: creates a second public/service lifecycle and weakens request-scoped cancellation/backpressure. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:132-140] |
| Torch CUDA-graph backend | GGML/quantization | Deferred explicitly. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:137-142] |
| Full ICL with matching transcript | X-vector-only or custom voice | Rejected by D-05; it changes the selected cloning path. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:24-28] |
| `qwen3_1_7b` | Reusing `qwen3_0_6b` as an alias | Rejected because it lies about model identity. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:18-22] |
| Native streaming per safe segment | Whole synthesis or full-response buffering | Forbidden by the live-call contract. [VERIFIED: .planning/LIVE-CALL-INVARIANTS.md:1-48] |

**Installation:**

```bash
# Production dependency form; update pyproject.toml and uv.lock together.
uv add --project ai-backend --optional tts \
  "faster-qwen3-tts @ git+https://github.com/andimarafioti/faster-qwen3-tts@a70afc0f81f7f5f8801c3227968f1102f43f211c"

# Deployment and hardware verification remain exclusively inside this command.
RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh
```

The direct source pin is the production form fixed by the AI design contract; `faster-qwen3-tts==0.3.2` is suitable only for registry/manual equivalence checks. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:150-172]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `faster-qwen3-tts` | PyPI / official Git commit | 14 days at research date; published 2026-07-17 | Registry seam returned unknown | `github.com/andimarafioti/faster-qwen3-tts` | SUS: `too-new`, `unknown-downloads`; source approved | RESOLVED — the product owner supplied this exact repository, accepted audio produced by tag `v0.3.2` at commit `a70afc0f81f7f5f8801c3227968f1102f43f211c`, selected 1.7B, and explicitly authorized implementation/deployment. Execution must still run `node /home/agent/.codex/gsd-core/bin/gsd-tools.cjs package-legitimacy check --ecosystem pypi faster-qwen3-tts`, `python3 -m pip index versions faster-qwen3-tts`, and `git ls-remote --tags https://github.com/andimarafioti/faster-qwen3-tts refs/tags/v0.3.2`; then `uv lock --project ai-backend --check` plus `rg -n 'a70afc0f81f7f5f8801c3227968f1102f43f211c' ai-backend/uv.lock` must prove the immutable lock. No new product choice or human checkpoint remains. [VERIFIED: user direction, accepted Spikes 004b/005/006, GSD package-legitimacy seam, PyPI, and official source, 2026-07-31] |

The PyPI registry exposes versions `0.1.0` through `0.3.2`; current is `0.3.2`. Python packages have no npm-style postinstall check. [VERIFIED: `python3 -m pip index versions faster-qwen3-tts`, 2026-07-31]

**Packages removed due to [SLOP] verdict:** none.

**Packages flagged as suspicious [SUS]:** `faster-qwen3-tts`. The suspicion is package age/download telemetry, not a source mismatch. The trust-establishing human decision is already recorded: the product owner supplied the source, accepted its pinned output, selected 1.7B, and authorized deployment. The exact metadata, tag, commit, and lock commands above remain blocking automated execution gates.

## Architecture Patterns

### System Architecture Diagram

```text
Saved voice WAV + exact transcript
        │
        ├─ Voice Lab save/preview/test-play ───────────────┐
        │                                                   │
        ▼                                                   ▼
Web UI server ── RayMe API ──> reference validator ──> one-hot ModelManager
        │                           │                         │
        │                           └─ existing CUDA STT       ├─ model: idle/loading/resident/unavailable
        │                                                     └─ prompt: none/prewarming/ready/failed
        │                                                               │
LLM token stream                                                        ▼
        │                                                Qwen adapter/supervisor
        ▼                                                               │ versioned commands/events
incremental natural-boundary segmenter                                  ▼
        │                                                    spawned CUDA worker
        ▼                                                    ├─ exact local 1.7B snapshot
bounded turn segment queue (capacity chosen/tested)          ├─ capacity-one ICL prompt cache
        │                                                    └─ one active native generator
        ▼                                                               │ pull stream
CallSession turn scheduler <── cancel/terminal state ────────────────────┘
        │
        ▼
capacity-two thread→async chunk bridge
        │
        ▼
playout-credit admission (bounded queued audio, paced release)
        │
        ▼
QueuedAudioOutputTrack → aiortc/WebRTC → browser call audio
        │
        ├─ immediate carrier: first chunk/enqueue/ai_audio_started
        └─ final carrier: generation terminal/playout complete/ai_done or cancelled/error
```

### Recommended Project Structure

```text
ai-backend/
├── app/models/
│   ├── tts_qwen3.py                 # adapter, supervisor, public exceptions, prompt API
│   ├── tts_qwen3_protocol.py        # CUDA-free Pydantic IPC command/event schemas
│   ├── tts_qwen3_worker.py          # only CUDA owner; load/prewarm/generate/cancel loop
│   ├── tts_registry.py              # qwen3_1_7b metadata/capabilities/input contract
│   ├── engine_metadata.py           # matching canonical status roster
│   └── model_manager.py             # async load lifecycle and prompt readiness
├── app/call/
│   ├── session.py                   # turn segment pump, bounded bridge, terminal semantics
│   └── tracks.py                    # playout-credit/backlog bound
├── app/api/
│   ├── tts.py                       # validate/prepare/preview via same readiness path
│   └── webrtc.py                    # turn-scoped segment/finalize or compatible speak bridge
└── tests/
    ├── test_tts_qwen3.py            # new protocol/supervisor/cache/ceiling/cancel tests
    ├── test_call_session.py          # streaming/backpressure/cancellation/metrics
    └── test_model_manager.py         # one-hot async readiness/failure containment

web-ui/server/
├── alembic/versions/0003_qwen3_engine_identity.py
├── app/domain/call_tts_segments.py   # incremental deterministic text segmentation
├── app/api/calls.py                  # feed segments before LLM completion; persist on success
├── app/domain/voice_service.py       # Qwen validation and editable engine/transcript
└── tests/                            # migration, voice, call-segment, cancellation tests

web-ui/client/
├── src/lib/api/types.ts              # truthful id and model/prompt readiness
├── src/routes/voice-lab/+page.svelte # visible load/prewarm/error states
├── src/lib/components/voice/         # picker/assignment/library labels
└── tests/unit + tests/e2e             # state/error/rendered workflow coverage

.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/
├── 09-evidence-manifest.json
├── 09-run-omen-evidence.py
├── 09-verify-evidence.py
└── results/                          # schema-versioned scalar JSON; private WAVs remain local
```

### Pattern 1: Supervised, request-scoped worker

**What:** The AI backend owns a subprocess whose main generation thread owns CUDA. A small stdin reader remains able to set a cancellation event while generation is inside the synchronous pull generator. The parent validates every versioned event, associates it with one request id, and terminates/reloads on protocol failure or missed cancellation deadline. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:380-410,480-532]

**When to use:** Model load, prompt preparation, preview generation, and every live Qwen segment.

**Required state machine:** `load → loaded`, `prewarm → ready|error`, `generate → chunk* → done|cancelled|error`; exactly one terminal event is accepted for each request. The exact terminal values are quoted as `Literal["done", "cancelled", "error"]`. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:493-512]

### Pattern 2: Separate model and prompt readiness

**What:** Keep the existing model states, quoted verbatim as `"idle", "loading", "resident", "unavailable"`, and add prompt states quoted verbatim as `"none/prewarming/ready/failed"`. [VERIFIED: ai-backend/app/models/tts_registry.py:17-33; 09-AI-SPEC.md:451-455]

**When to use:** Call preparation, preview, and test-play. Start load/prewarm in a background task or thread and return/publish observable state immediately; never perform the ~90-second cold load synchronously inside `/webrtc/.../speak`. The accepted spike recorded the long cold path, and the current route synchronously calls `switch(engine_id)`. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:559-579; ai-backend/app/api/webrtc.py:540-560]

**Cache:** Capacity one is sufficient. Key SHA-256(reference bytes), normalized exact transcript, model revision, full-ICL mode, and appended-silence policy; clear it on edit, voice delete, engine unload/switch, worker exit, or model identity change. Never persist/serialize prompt tensors. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:435-455]

### Pattern 3: Incremental LLM-to-TTS segment pump

**What:** Feed a deterministic natural-boundary segmenter as each LLM token arrives. Once it emits a safe sentence/phrase, submit it to a bounded, turn-scoped speech queue immediately; keep streaming later LLM tokens and segments. The final tail closes the turn. Do not join the whole `accumulated` response before the first speech request. The current code does exactly that at lines 399-443 and must be replaced for Qwen calls. [VERIFIED: web-ui/server/app/api/calls.py:357-443; 09-CONTEXT.md:35-40]

**When to use:** Every Qwen live assistant turn. Keep preview/test-play as one bounded segment because they already have complete short text.

**Recommended segmentation policy:** Prefer `.?!` plus safe newline boundaries, retain punctuation, avoid emitting tiny fragments, force a phrase boundary before the locked 60-word ceiling, and flush the final tail. Do not add a generic NLP package: this is an incremental protocol-aware splitter, not document sentence tokenization. Validate every segment again in the AI backend. The 60-word ceiling and natural-boundary requirement are locked. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:367-376,459-470]

**API shape:** Keep the existing RayMe `/webrtc` boundary but make Qwen speech turn-scoped. Non-final segment submissions should return after bounded acceptance, not after playout; the final submission/finalize operation may keep the SSE alive until the normal terminal event. This allows segment 2 generation to overlap segment 1 playout while preserving one generator at a time.

### Pattern 4: End-to-end backpressure, not queue theater

**What:** Use `asyncio.Queue(maxsize=2)` for the blocking-thread bridge and make the producer wait on `asyncio.run_coroutine_threadsafe(queue.put(item), loop).result()` with cancellation checks. Then make outbound enqueue wait for playout credit based on pending samples/audio duration. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:394-408,522-532]

**Why both layers:** Today the bridge queue is unbounded, and `QueuedAudioOutputTrack.enqueue()` immediately moves each entire chunk to another unbounded queue. Merely setting the first queue's `maxsize` would not slow the producer because the consumer can drain it faster than real-time into the track. [VERIFIED: ai-backend/app/call/session.py:1077-1087,1216-1234,1260-1284; ai-backend/app/call/tracks.py:54-62,98-119]

**Admission rule:** Track pending samples (including `_buffer`) and block Qwen chunk admission over a tested bounded audio budget; decrement/notify as 20 ms frames are consumed. Record bridge high-water, playout pending-audio high-water, producer block time, underflow count, and discarded-late-chunk count. Preserve the existing bounded startup values unless OMEN evidence justifies adjustment. The current values are quoted as `0.25`, `0.75`, `2`, `0.75`, and `1.25` seconds/chunks. [VERIFIED: ai-backend/app/call/session.py:47-54]

### Pattern 5: Cancellation is a protocol, not task cancellation

**What:** On barge-in, explicit interrupt, hangup, engine switch, or close: mark the turn cancelled first; stop/drain playout; reject further segment submissions; send `cancel(request_id)`; continue draining/discarding worker events until `cancelled`; force-terminate after the hard two-second deadline; suppress `ai_done` and complete persistence; restore `listening` or `ended`. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:42-45; 09-AI-SPEC.md:403-410,522-532]

**Why:** Current `cancel_ai_turn()` cancels the asyncio task and track but has no adapter cancellation signal, while `end()` cancels only the task and closes the peer. Cancelling `asyncio.to_thread()` does not stop the native thread/worker. [VERIFIED: ai-backend/app/call/session.py:1360-1401; 09-AI-SPEC.md:296-320]

### Pattern 6: Persist only normal terminal speech

**What:** Keep live `ai_token` UI events transient. Commit one `ai_speech` row only after the call scheduler reports a normal final terminal and playout completion. On cancel/error, retain no complete speech row. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:42-45]

**Why:** Current Web UI code writes `record_ai_speech()` before it launches TTS, so a later cancellation already has a durable complete turn. [VERIFIED: web-ui/server/app/api/calls.py:399-443; web-ui/server/app/domain/call_service.py:209-216]

### Pattern 7: Explicit compatibility migration

**What:** Add an Alembic data migration that rewrites exact persisted `voices.default_engine == "qwen3_0_6b"` to `"qwen3_1_7b"`, plus read-boundary normalization during the upgrade window and tests proving no API returns the old id. Update the JSON `endpoint_settings.tts_default_engine` if it contains the exact old id. Never map an arbitrary unknown Qwen string. The exact stored field and settings key are quoted as `"default_engine"`, `SETTINGS_KEY = "endpoint_settings"`, and `"tts_default_engine"`. [VERIFIED: web-ui/server/alembic/versions/0002_voice_storage.py:38-48; web-ui/server/app/domain/settings_service.py:13-27]

**Current live data:** The read-only OMEN inventory found 44 `f5`, 1 `luxtts`, and 20 `voxcpm2` voice rows, zero `qwen3_0_6b` rows, and `endpoint_settings.tts_default_engine == "f5"`; the migration remains necessary for other databases/fixtures and future reproducibility. [VERIFIED: read-only OMEN SQLite aggregate query, 2026-07-31]

### Anti-Patterns to Avoid

- **Adapter-only replacement:** It leaves full-LLM-response waiting, hidden cold load, unbounded playout, and premature persistence intact. [VERIFIED: current code citations in Summary]
- **Collecting the native generator:** Never call `list(stream)`, concatenate all chunks, write a whole-turn WAV, or invoke `generate_voice_clone()` from a live Qwen path. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2]
- **Blocking playback inside the pull loop:** Upstream documents that this prevents generation/playout overlap. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2]
- **Copying the Vox worker loop literally:** Its current stdin loop cannot receive cancel while `_handle_stream` is blocking; Qwen needs a reader thread/event. [VERIFIED: ai-backend/app/models/tts_voxcpm2_worker.py:37-56]
- **Global exception means engine unavailable:** Missing transcript/mismatch/segment-too-long are request validation errors, not proof the runtime is broken. The current `/tts/synthesize` catches every exception and marks the engine unavailable. [VERIFIED: ai-backend/app/api/tts.py:45-87]
- **Trusting upstream `is_final`:** Generator exhaustion is authoritative; an exact multiple of `chunk_size` can exhaust without a yielded record flagged final. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:315-320]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Qwen CUDA decoding/codec streaming | A custom model loop or codec | Pinned `FasterQwen3TTS.generate_voice_clone_streaming()` | The accepted performance and quality evidence belongs to that exact implementation. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2] |
| Voice prompt extraction | A separate speaker embedding pipeline | Upstream full-ICL `create_voice_clone_prompt()` behavior through the pinned runtime | Full ICL is the selected fidelity path and needs matching audio/text context. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:222-279] |
| Worker schema validation | String prefixes and ad hoc dictionary checks | Existing Pydantic with versioned discriminated events | Wrong-id, malformed, duplicate, and oversized events are security/reliability boundaries. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:480-520] |
| Reference transcription | A second ASR model/service | RayMe's resident CUDA Whisper adapter | It already produced the saved editable transcript and passed the 50-turn WER gate. [VERIFIED: .planning/spikes/005-faster-qwen3-tts-longitudinal-quality/README.md:35-41,49-58] |
| Model revision downloads | Mutable `from_pretrained(repo_id)` at call time | `huggingface_hub.snapshot_download(revision=...)` in `deploy-omen.sh`, then local path | The faster wrapper does not provide a safe production revision pin through its load boundary; deployment must materialize the snapshot first. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:169-185] |
| Deployment/task repair | Ad hoc PowerShell, launchers, or scheduled tasks | `scripts/deploy-omen.sh` | Project policy makes it the only authorized deployment mechanism. [VERIFIED: AGENTS.md, OMEN Deployment] |
| Acoustic/WER release scoring | A hosted LLM/audio judge | Phase-owned local evidence runner, RayMe STT, NumPy/SoundFile, and product-owner listening | The locked evaluation contract keeps private voice data local and tests audible longitudinal failure directly. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:612-719] |

**Key insight:** The hard work is lifecycle and flow control, not synthesis math. Reusing the pinned runtime while making every queue, state transition, terminal event, and persisted artifact explicit is safer than wrapping a fast generator in opaque convenience code.

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `voices.default_engine` is a free string and `reference_transcript` is nullable; the exact definitions are `default_engine: Mapped[str]` and `reference_transcript: Mapped[str | None]`. The live OMEN database currently has no old Qwen rows, but other databases can. [VERIFIED: web-ui/server/app/storage/models.py:184-192; read-only OMEN aggregate query, 2026-07-31] | Add an Alembic code+data migration, update the exact old id only, validate Qwen transcript at save/update, and test old-id upgrade. No destructive live data rewrite is currently needed on OMEN beyond running the migration. |
| Live service config | `app_settings` stores `SETTINGS_KEY = "endpoint_settings"` and includes `"tts_default_engine"`; OMEN currently stores `"f5"`. [VERIFIED: web-ui/server/app/domain/settings_service.py:13-27,105-122; read-only OMEN query, 2026-07-31] | Migration/read normalization must translate an exact old id if present. Do not change the user's global default implicitly unless Phase 9 explicitly intends promotion. |
| OS-registered state | Scheduled tasks are exactly `RayMePhase1AI` and `RayMePhase1Web`, pointing to `C:\Users\pmpg\rayme\start-ai-backend.cmd` and `C:\Users\pmpg\rayme\start-web-ui.cmd`. [VERIFIED: scripts/deploy-omen.sh:354-375; read-only OMEN scheduled-task query, 2026-07-31] | No rename. Extend only the canonical launcher text generated by `deploy-omen.sh` with the immutable local model-path/runtime settings needed by the worker. |
| Secrets/env vars | The generated AI launcher currently sets only CUDA `PATH`; no Qwen model-dir/revision variable exists. The Web launcher contains database and endpoint settings. [VERIFIED: scripts/deploy-omen.sh:291-315; repository `rg` for Qwen env vars, 2026-07-31] | Add non-secret local snapshot/config variables in `deploy-omen.sh`; never log raw reference audio/transcript, tokens, or private paths. No existing secret-key rename is required. |
| Build artifacts / installed packages | The production AI venv currently has `qwen-tts==0.1.1` and `transformers==4.57.3` but does not have `faster-qwen3-tts`; Torch is `2.10.0+cu126`. [VERIFIED: read-only OMEN package probe, 2026-07-31] | Update `pyproject.toml` and `uv.lock`; have canonical deploy install the pinned source, then reassert CUDA Torch after sync. Materialize/verify the exact model snapshot. Do not rely on spike venv/cache artifacts as production state. |

**Canonical runtime path:** The database URL embedded by the deploy script is quoted verbatim as `sqlite+aiosqlite:///C:/Users/pmpg/rayme/RayMe/web-ui/server/data/rayme.sqlite3`. [VERIFIED: scripts/deploy-omen.sh:304-315]

## Common Pitfalls

### Pitfall 1: Speech still starts after the whole LLM response

**What goes wrong:** Native audio streaming looks correct in isolation, but calls remain generated-audio playback because no synthesis request begins until LLM EOS.

**Why it happens:** `calls.py` appends every token, joins `visible_text`, then calls `_speak_call()` once. [VERIFIED: web-ui/server/app/api/calls.py:357-443]

**How to avoid:** Implement the incremental segment pump in the same phase and add a slow-LLM regression proving first TTS submission/audio happens before LLM completion.

**Warning signs:** Long responses sit in `rehearsing`; native TTFA is fast but user-perceived first audio scales with LLM response length.

### Pitfall 2: Capacity two does not actually bound audio memory

**What goes wrong:** The thread bridge never exceeds two, yet a whole turn accumulates inside `QueuedAudioOutputTrack`.

**Why it happens:** Its current `_queue` is unbounded, and enqueue is much faster than paced `recv()`. [VERIFIED: ai-backend/app/call/tracks.py:54-62,75-119]

**How to avoid:** Tie producer admission to pending playout samples/audio duration and assert both bridge and track high-water under a deliberately slow consumer.

**Warning signs:** Bridge high-water is two while track queue/pending duration grows with output length.

### Pitfall 3: “Visible loading” still freezes status

**What goes wrong:** State is set to `loading`, but the same event loop is blocked inside a 90-second model load so no client can observe it.

**Why it happens:** Both `/tts/synthesize` and `/webrtc/.../speak` call the synchronous model switch path. [VERIFIED: ai-backend/app/api/tts.py:45-68; ai-backend/app/api/webrtc.py:540-560; ai-backend/app/models/model_manager.py:100-145]

**How to avoid:** Create asynchronous prepare/status operations around a supervised worker load; keep the event loop responsive and poll/subscribe from existing controls.

**Warning signs:** Status jumps from idle to resident after one long request or the browser appears frozen despite a `loading` enum.

### Pitfall 4: Async task cancellation leaves CUDA generation alive

**What goes wrong:** The user interrupts, audio stops briefly, but the worker continues generating and late chunks/terminal events arrive.

**Why it happens:** Cancelling `to_thread` does not stop its thread; current call cancellation never invokes the adapter. [VERIFIED: ai-backend/app/call/session.py:1360-1401; 09-AI-SPEC.md:296-320]

**How to avoid:** Use request-scoped cancel commands, worker event checks, terminal draining, late-event rejection, and a hard process-termination watchdog.

**Warning signs:** GPU stays busy after hangup, next turn blocks, cancelled request emits `done`, or old audio enters the next turn.

### Pitfall 5: Reference text is treated as optional metadata

**What goes wrong:** A mismatched transcript produces repetition or a token-cap-length output; a blank transcript silently changes clone mode.

**Why it happens:** Current request and database fields are nullable, and current Qwen metadata declares `requires_transcript=False`. [VERIFIED: ai-backend/app/models/tts_registry.py:176-185; web-ui/server/app/storage/models.py:184-192]

**How to avoid:** Enforce blank checks at every boundary, STT alignment before prompt creation, full ICL only, and the text-relative token/audio ceiling. The known mismatch ran for 81.92 seconds. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:113-124]

**Warning signs:** No natural EOS, implausible duration, repeated phrases, reference-content leakage, or `max_new_tokens` reached.

### Pitfall 6: Validation failures poison engine availability

**What goes wrong:** A user's bad transcript disables Qwen globally, or a worker crash is mislabeled as a user input error.

**Why it happens:** Current synthesis catches all exceptions and marks the target unavailable. [VERIFIED: ai-backend/app/api/tts.py:69-87]

**How to avoid:** Define typed categories: request validation (4xx, engine stays resident), prompt prewarm failure (voice key failed, model may stay resident), generation ceiling/cancel (request failed, health policy evaluated), and runtime/protocol identity failure (engine unavailable/worker terminated).

**Warning signs:** Other valid saved voices stop working after one mismatch, or the UI reports generic unreachable for actionable 4xx errors. Current Web client bridge maps all generic 4xx to `unreachable`. [VERIFIED: web-ui/server/app/domain/ai_backend_client.py:266-294]

### Pitfall 7: Cancelled speech was already persisted

**What goes wrong:** Call history shows a complete assistant speech artifact the caller never heard.

**Why it happens:** Persistence occurs before TTS task creation. [VERIFIED: web-ui/server/app/api/calls.py:399-443]

**How to avoid:** Persist only normal terminal completion; test the database after cancel-before-audio and cancel-after-audio.

**Warning signs:** One `ai_speech` row exists for a turn with no `ai_done`.

### Pitfall 8: The client silently drops the new engine

**What goes wrong:** Backend returns `qwen3_1_7b`, but the Voice Lab normalizer rebuilds its list from hard-coded fallback ids and discards it.

**Why it happens:** The current client union and fallback components contain only `qwen3_0_6b`. [VERIFIED: web-ui/client/src/lib/api/types.ts:363-392; web-ui/client/src/routes/voice-lab/+page.svelte:36-103,175-230]

**How to avoid:** Replace all hard-coded old ids, preserve server-returned canonical metadata, migrate saved values, and add API/UI tests for exact label, transcript requirement, and readiness state.

**Warning signs:** Settings shows Qwen while Voice Lab does not, or the UI renders the raw id.

### Pitfall 9: `uv sync` replaces the working CUDA wheel

**What goes wrong:** The package installs, but Torch becomes a default/CPU wheel and Qwen or STT silently loses CUDA.

**Why it happens:** The dependency declares a broad `torch>=2.5.1`; OMEN depends on the explicit `2.10.0+cu126` install sequence. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/blob/a70afc0f81f7f5f8801c3227968f1102f43f211c/pyproject.toml] [VERIFIED: scripts/deploy-omen.sh:108-293]

**How to avoid:** Preserve/reassert the canonical CUDA wheel after dependency sync and fail deployment unless imported Torch version/CUDA/device match.

**Warning signs:** `+cpu`, `torch.version.cuda is None`, `torch.cuda.is_available()==False`, or worker identity failure.

### Pitfall 10: Private voice material enters logs/evidence

**What goes wrong:** Absolute blob/cache paths, full transcripts, or audio end up in logs or committed JSON.

**Why it happens:** Current call reference diagnostics log `blob_dir`, `expected_path`, and directory contents. [VERIFIED: web-ui/server/app/domain/call_service.py:218-275]

**How to avoid:** Log opaque voice/request ids, content hashes, scalar scores, and stable codes only; add a leak scan to contracts and decision-ready evidence.

**Warning signs:** `C:\Users\...`, blob filenames, base64 payloads, or full transcript text in logs/results.

### Pitfall 11: Independent text segments create audible resets

**What goes wrong:** Native chunks are clean, but sentence-to-sentence joins change pitch, style, or identity.

**Why it happens:** Each safe text segment starts a new upstream generation even though it reuses the prompt.

**How to avoid:** Prefer natural boundaries, avoid tiny fragments, use the same prewarmed ICL prompt/settings, overlap generation/playout, and gate joins through the Phase 09 human/audio metrics. The upstream issue is documented in the locked research. [VERIFIED: .planning/spikes/004-b-faster-qwen3-tts-17b-cuda/README.md:17-26; 09-AI-SPEC.md:459-470]

**Warning signs:** clean within-chunk audio but a pitch/mood jump at RayMe text-segment boundaries.

## Code Examples

Verified and locked patterns from the phase AI design contract and official runtime:

### Validated worker events

```python
# Source: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:480-512
class QwenChunkEvent(BaseModel):
    schema_version: Literal[1] = 1
    event: Literal["chunk"]
    request_id: str = Field(min_length=1, max_length=128)
    chunk_index: int = Field(ge=0)
    wav_b64: str = Field(min_length=1)
    sample_rate: Literal[24000]
    duration_ms: float = Field(gt=0, le=2000)
    generated_at_ms: float = Field(ge=0)
    total_steps_so_far: int = Field(ge=1, le=384)

class QwenTerminalEvent(BaseModel):
    schema_version: Literal[1] = 1
    event: Literal["done", "cancelled", "error"]
    request_id: str = Field(min_length=1, max_length=128)
    chunk_count: int = Field(ge=0)
    natural_eos: bool = False
    error_code: str | None = None
```

Every discrete value in this skeleton is quoted verbatim from the source-of-truth spec. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:480-512]

### Pinned native generation

```python
# Source: official v0.3.2 API plus locked 09-AI-SPEC.md:201-279
stream = model.generate_voice_clone_streaming(
    text=segment_text,
    language="English",
    ref_text=exact_reference_transcript,
    voice_clone_prompt=prompt_items,
    chunk_size=4,
    max_new_tokens=max_new_tokens,
    xvec_only=False,
    non_streaming_mode=True,
    append_silence=True,
    parity_mode=False,
    temperature=0.9,
    top_k=50,
    top_p=1.0,
    do_sample=True,
    repetition_penalty=1.05,
)
try:
    yield from stream
finally:
    stream.close()
```

The exact initial values are locked by the AI spec and accepted spike, not inferred. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:201-279,355-376] The API's audio generator is pull-based, and official docs warn against blocking after each yield. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2]

### Text-relative generation ceiling

```python
# Source: 09-AI-SPEC.md:367-376
expected_seconds = max(1.0, word_count / 2.2)
hard_audio_seconds = min(32.0, max(6.0, expected_seconds * 2.25 + 2.0))
max_new_tokens = min(384, math.ceil(hard_audio_seconds * 12 / 4) * 4)
```

Fail the segment if the worker reaches the token ceiling, cumulative decoded audio exceeds `hard_audio_seconds`, or generator completion is not natural; drain queued partial audio and do not emit success. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:367-376,734-739]

### Real blocking bridge

```python
# Source pattern: 09-AI-SPEC.md:394-408,522-532
queue: asyncio.Queue[QwenChunkEvent | QwenTerminalEvent] = asyncio.Queue(maxsize=2)

def publish_from_reader(item: QwenChunkEvent | QwenTerminalEvent) -> None:
    future = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
    future.result()  # blocks the reader; cancellation path keeps draining/discarding
```

Do not replace `future.result()` with `call_soon_threadsafe(queue.put_nowait, ...)`; the current code uses the latter and has no backpressure. [VERIFIED: ai-backend/app/call/session.py:1214-1234]

### Incremental segment pump contract

```python
# Recommended repository pattern; values/ceilings come from locked D-16 and AI-SPEC.
async for token in llm_tokens:
    yield ai_token_event(token)
    for segment in segmenter.feed(token):
        await speech_turn.submit(segment)  # bounded acceptance; first segment starts now

tail = segmenter.finish()
if tail:
    await speech_turn.submit(tail)
await speech_turn.finish()                # wait for one normal terminal or failure
```

The first RED test must hold the LLM stream open after emitting a complete first sentence and prove first speech submission/playback occurs before LLM completion. This is the product-level counterpart to the existing slow-native-stream regression. [VERIFIED: .planning/LIVE-CALL-INVARIANTS.md:1-48; ai-backend/tests/test_call_session.py:1265-1329]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Import-gated `qwen-tts` placeholder, id `qwen3_0_6b`, no streaming | Official `faster-qwen3-tts` v0.3.2 at immutable commit, 1.7B Base snapshot, id `qwen3_1_7b` | Phase 09 selection, 2026-07-31 | Makes the accepted native CUDA path truthful and testable. [VERIFIED: ai-backend/app/models/tts_qwen3.py:1-8; 09-CONTEXT.md:18-22] |
| Upstream whole/non-streaming terminology interpreted as whole audio | `non_streaming_mode=True` only prefills the current safe text segment while `generate_voice_clone_streaming()` still yields audio | v0.3.2 / Phase 09 | Preserves the quality setting without violating early audio. [CITED: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2] |
| Full LLM response joined before one speech request | Incremental natural segment emission while LLM streaming continues | Phase 09 | First speech no longer scales with full response length. [VERIFIED: current old behavior at web-ui/server/app/api/calls.py:357-443; new behavior required by 09-CONTEXT.md:35-40] |
| Unbounded thread bridge and unbounded track queue | Capacity-two bridge plus playout-credit admission | Phase 09 | Bounds memory/audio debt against real consumption. [VERIFIED: current old behavior at ai-backend/app/call/session.py:1077-1087 and tracks.py:54-62; target at 09-AI-SPEC.md:522-555] |
| Async task cancel only | Request-scoped worker cancel/ack/drain/terminate lifecycle | Phase 09 | Stops CUDA work and prevents late events after barge/hangup/switch. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:403-410,522-532] |
| Mutable model-id resolution | Deploy-time exact snapshot materialization and worker local path | Phase 09 | Prevents silent model drift. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:169-185] |

**Deprecated/outdated:**

- `qwen3_0_6b` as a selectable engine: compatibility input only; migrate to `qwen3_1_7b`. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:18-22]
- `Qwen3TtsAdapter(ImportGatedTtsAdapter)` requiring only `qwen_tts`: replace with the supervised faster runtime adapter. [VERIFIED: ai-backend/app/models/tts_qwen3.py:1-8]
- A live Qwen call path through `synthesize()`: prohibited; `generate_voice_clone_streaming()` is the only call generator. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:35-40]
- Full-response TTS launch after `visible_text = "".join(accumulated)`: incompatible with D-16 and REQ-45. [VERIFIED: web-ui/server/app/api/calls.py:357-443]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | None. Proposed implementation details are recommendations within explicitly delegated discretion; runtime values, thresholds, identities, and current-code claims were verified against official or repository sources. | — | — |

## Open Questions (RESOLVED)

1. **Resolved: young-package trust decision**
   - Resolution: The product owner's repository provenance, accepted `v0.3.2` spike output, explicit 1.7B selection, and deployment authorization satisfy the human trust decision for the exact source commit. The SUS telemetry remains recorded and cannot authorize any different source/version.
   - Execution gate: Run the exact package-legitimacy, PyPI metadata, tag/commit, lock-check, and lock-commit assertions named in the Package Legitimacy Audit. Any mismatch blocks installation; no additional human checkpoint is required for this already approved source.

2. **Resolved: compatibility rows outside the current OMEN database**
   - Resolution: Ship an idempotent exact-id data migration plus read-boundary normalization for every installation. Rewrite only `voices.default_engine == "qwen3_0_6b"` and exact endpoint-settings `tts_default_engine == "qwen3_0_6b"` to `qwen3_1_7b`; preserve unknown engine strings and unrelated JSON. The current OMEN zero-row case is simply the idempotent no-op fixture, not a reason to omit compatibility behavior. [VERIFIED: read-only OMEN query; web-ui/server/app/storage/models.py:184-192; Phase 09 Plan 09-07]

3. **Resolved: physical-call acceptance is a post-deployment human gate**
   - Resolution: Audible likeness/naturalness and the builder's final perception on the integrated phone path are intentionally outside autonomous implementation proof. Complete local, browser, OMEN runtime, call-flow, cancellation, privacy, and 50-turn gates first; record `autonomous_release_ready` separately from `integrated_human_listening_status=pending` and `physical_call_status=pending`; then hand off one exact selected-voice call workflow. This is a deliberate acceptance boundary, not an implementation unknown. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:595-719; Phase 09 Plan 09-15]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Local Python | deterministic tests/evidence verifier | ✓ | 3.12.3 | — |
| Local `uv` | Python sync/tests | ✓ | 0.12.0 | — |
| Local Node/npm | client unit/build/e2e | ✓ | Node 22.23.2 / npm 10.9.8 | — |
| Local SSH alias `rayme-pmpg` | read-only audit and canonical deploy target | ✓ | OpenSSH 9.6p1 client; alias connected | — |
| Local CUDA GPU | hardware generation | ✗ | `nvidia-smi` absent | Run hardware gates on OMEN only; do not CPU-fallback. |
| Local ffmpeg | media conversion | ✗ | — | Not required for the Qwen worker; saved reference WAV is handled by SoundFile. Existing upload support remains unchanged. |
| OMEN Python | AI runtime | ✓ | 3.11.15 | — |
| OMEN NVIDIA GPU | Qwen/STT/TTS | ✓ | GeForce RTX 3060, 12,288 MiB; driver 560.94 | No CPU fallback. |
| OMEN Torch/CUDA | CUDA worker | ✓ | `2.10.0+cu126`, CUDA 12.6, available true | Deployment must preserve/reassert it. |
| OMEN `qwen-tts` / transformers | wrapper dependencies | ✓ | 0.1.1 / 4.57.3 | — |
| OMEN `faster-qwen3-tts` production install | selected engine | ✗ | not installed in production AI venv | Install exact commit only through `scripts/deploy-omen.sh`. |
| Exact local model snapshot path | immutable worker load | Not yet production-attested | accepted snapshot exists in spike evidence, not guaranteed at canonical service path | `deploy-omen.sh` materializes/verifies it before service start. |
| Canonical scheduled tasks | service launch | ✓ | `RayMePhase1AI`, `RayMePhase1Web` point to canonical `.cmd` launchers | — |

**Missing dependencies with no fallback:** none after the canonical deploy install step; production `faster-qwen3-tts` and exact snapshot are required work, and CPU/remote-server substitution is forbidden.

**Missing dependencies with fallback:** local CUDA is intentionally absent; all hardware evidence runs on OMEN.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| AI backend | `pytest==9.0.3`; config in `ai-backend/pyproject.toml` [VERIFIED: ai-backend/pyproject.toml:27-35] |
| Web UI server | `pytest==9.0.3`, `pytest-asyncio==1.3.0`; config in `web-ui/server/pyproject.toml` [VERIFIED: web-ui/server/pyproject.toml:18-30] |
| Client unit | `vitest==4.1.5`; `web-ui/client/vitest.config.ts` [VERIFIED: web-ui/client/package.json:8-15,27-31] |
| Browser E2E | `@playwright/test==1.59.1`; `web-ui/client/playwright.config.ts` [VERIFIED: web-ui/client/package.json:27-31] |
| Quick run command | `uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py ai-backend/tests/test_call_session.py ai-backend/tests/test_model_manager.py -q` |
| Full suite command | `uv run --project ai-backend pytest ai-backend/tests -q && uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run` |

### Phase Requirements → Test Map

| Req ID / Decision | Behavior | Test Type | Automated Command | File Exists? |
|-------------------|----------|-----------|-------------------|-------------|
| REQ-22 / D-01–D-08 | Exact runtime/model/id, full-ICL prompt, blank/mismatch rejection, ceiling | unit + migration + OMEN integration | `uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py ai-backend/tests/test_tts_registry.py -q` | ❌ `test_tts_qwen3.py` Wave 0; registry exists |
| REQ-22 / D-09–D-11 | Separate observable model/prompt readiness through preview/test/call | unit + API + browser | `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py ai-backend/tests/test_webrtc_signaling.py -q && uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_calls.py -q` | ✅ extend existing |
| REQ-45 / D-12–D-16 | LLM first safe segment before LLM completion; native first audio before stream completion; no fallback; bounded end-to-end queue | deterministic async unit/API | `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q && uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` | ✅ extend existing; add segmenter test |
| REQ-45 / D-17–D-19 | cancel before/after audio, hangup, switch, close; no late audio/done/persistence; recovery | unit + API + OMEN call-flow | same focused backend/server commands plus `09-verify-evidence.py --decision-ready` | ✅ extend existing; evidence files Wave 0 |
| REQ-46 | native TTFA, RayMe first playback, RTFx, load/prewarm, underflow and drift thresholds | OMEN hardware evidence | `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh` | ❌ Phase 09 deploy/evidence branch Wave 0 |
| D-20 | Preserve VoxCPM2 slow-stream and no-whole-fallback regressions | regression | `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` | ✅ existing |
| D-21 | 50 hot turns, WER/acoustics/memory/anchor stability and reel | OMEN soak + human gate | `09-verify-evidence.py --decision-ready` after canonical deploy | ❌ integrated descendant Wave 0 |
| D-22 | canonical deploy, exact identity, rendered UI, RayMe-shaped normal/cancelled call | deploy + Playwright + live API | deploy command plus saved Playwright and call-flow artifacts | ❌ Phase 09 artifacts Wave 0 |

### Required RED Regressions

1. Slow LLM: first complete sentence is submitted/played while the LLM stream is deliberately held open.
2. Slow native stream: first Qwen playback precedes producer completion.
3. No live fallback: injected `synthesize()`/`generate_voice_clone()` fails the test if called; existing VoxCPM2 guard stays green.
4. Slow playout: bridge high-water and paced-track pending-audio high-water remain bounded; producer block time is positive; chunk order/drop count are exact.
5. Cancel before first chunk and after first audio: worker receives matching request id; no post-cancel enqueue/audio, `ai_done`, or complete `ai_speech` row.
6. Hangup/switch/close: same cancellation contract, worker/cache lifecycle ends, another call succeeds.
7. Mismatch/blank/ceiling: generation is never entered for validation rejects; runaway partial audio is drained and terminal is non-success.
8. State visibility: event loop remains responsive during a fake slow load/prewarm; UI renders `loading`/`resident` and `prewarming`/`ready`/`failed` distinctly.
9. Migration: exact old ids in voices/settings migrate; unknown ids remain unknown/rejected; OMEN zero-row case is idempotent.
10. Evidence verifier: recomputes raw thresholds, rejects stale/commit-mismatched artifacts, fallback, unbounded high-water, private-data leakage, and missing critical scenarios.

### Sampling Rate

- **Per task commit:** focused tests for the touched tier, each runnable in under 30 seconds with fake worker/stream fixtures.
- **Per wave merge:** full backend, server, and client unit suites; `git diff --check`.
- **UI wave:** saved Playwright Voice Lab/readiness/error workflow with console-error assertion.
- **Phase gate:** full suites, `09-verify-evidence.py --contracts-only`, canonical OMEN deploy/evidence, `--decision-ready`, saved rendered browser smoke, operational handoff check, and product-owner physical call only after all agent-run gates.

### Wave 0 Gaps

- [ ] `ai-backend/tests/test_tts_qwen3.py` — protocol, worker supervision, identity, cache, ceiling, cancel, malformed/crash/hang.
- [ ] `web-ui/server/tests/test_call_tts_segments.py` — incremental natural segmentation and slow-LLM early submission.
- [ ] Alembic migration fixture/test for exact old engine id in voices and JSON settings.
- [ ] `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-evidence-manifest.json` — 20 locked scenarios and fixture hashes.
- [ ] `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py` — contracts-only and decision-ready modes.
- [ ] Integrated OMEN runner descended from Spikes 005/006; do not copy private reference WAV/transcript into git.
- [ ] Saved client E2E test and result artifact for Voice Lab load/prewarm/error state.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no new auth in phase | Preserve the existing trusted-LAN topology; do not add a second public TTS service. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md:18-22] |
| V3 Session Management | limited | Bind worker commands/events to RayMe `session_id`/`turn_id`/`request_id`; exactly one active request and terminal event. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:480-532] |
| V4 Access Control | yes | Only selected saved voice ids may resolve reference blobs; enforce RayMe-owned path containment and reject arbitrary paths. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:734-740] |
| V5 Input Validation | yes | Pydantic request/IPC schemas, strict base64/size/sample-rate/duration/index checks, blank transcript rejection, STT alignment, text/token/audio ceilings. [VERIFIED: ai-backend/app/models/tts_registry.py:34-69,81-89; 09-AI-SPEC.md:480-555] |
| V6 Cryptography | yes, integrity only | Use standard `hashlib.sha256` for opaque cache/evidence identity; never hand-roll crypto and never treat a hash as authorization. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:442-455] |

### Known Threat Patterns for the Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Wrong-request/late/duplicate worker event | Spoofing / Tampering | Versioned discriminated schema, exact request id, monotonic index/time, one terminal, terminate on violation. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:480-520] |
| Malicious or malformed base64/audio | Tampering / Denial of Service | Existing byte/base64 caps plus decoded WAV validation, finite/sample-rate/duration/cumulative ceilings. [VERIFIED: ai-backend/app/models/tts_registry.py:34-69; 09-AI-SPEC.md:493-515] |
| Transcript mismatch or no natural EOS | Denial of Service | STT alignment preflight and text-relative token/audio ceiling before/while generating. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:367-376,424-430] |
| Arbitrary reference path | Elevation / Information Disclosure | Resolve only the selected saved `VoiceAsset`, require basename/path containment, never accept a worker filesystem path from browser input. Current basename check exists. [VERIFIED: web-ui/server/app/domain/call_service.py:225-255] |
| Worker crash/hang/CUDA corruption | Denial of Service | Process isolation, heartbeat/terminal timeout, cancel watchdog, force termination, engine-scoped health, recovery call probe. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:380-410,734-751] |
| Runtime/model substitution | Tampering | Commit-pinned package, immutable Hub revision/local snapshot, load-handshake version/CUDA/device attestation, one-hot residency. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:150-185,355-376] |
| Voice transcript/audio/path in logs | Information Disclosure | Opaque ids/hashes and scalar metrics only; leak-scan JSON/log excerpts. Current path-heavy logs must be removed. [VERIFIED: web-ui/server/app/domain/call_service.py:218-275; 09-AI-SPEC.md:435-457] |
| Unbounded queues/cache/output | Denial of Service | Capacity-one prompt cache, bounded segment queue, capacity-two chunk bridge, playout credit, token/audio ceiling. [VERIFIED: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md:442-455,522-555] |

## Project Constraints (from AGENTS.md)

- Speak and write user-facing material in AIbert's direct, human, grounded voice; visible state/logs/controls are real product behavior.
- Before any call/TTS/STT/VAD/WebRTC/reconnect/UI/deployment work, read `.planning/LIVE-CALL-INVARIANTS.md`; this research did.
- Never wait for the full assistant response or full TTS stream before first playback. Bounded startup/jitter buffering is allowed only if early playback, listening recovery, and barge-in remain intact.
- Every live-call TTS change must retain a slow-stream regression proving first playback before completion and tests rejecting whole-synthesis fallback on the VoxCPM2 path.
- Non-trivial regressions, incident repairs, and deployments must use GSD artifacts and verification gates.
- Deploy to OMEN only through `scripts/deploy-omen.sh`; do not create ad hoc launchers/scripts, manually alter `RayMePhase1AI`/`RayMePhase1Web`, or bypass canonical `start-ai-backend.cmd`/`start-web-ui.cmd`.
- GPU acceleration is mandatory; CPU fallback for STT/TTS/VAD/LLM/embedding is a regression. The real backend is `OMEN-PC` at `192.168.1.199`, reached only through `ssh rayme-pmpg`.
- Before user testing, run relevant unit/API tests, saved Playwright/browser verification for UI, live OMEN verification for GPU/LAN behavior, save results under the phase directory, state commit/deployed target, and run `scripts/operational-check.sh handoff`.
- Preserve user data and unrelated dirty worktree changes. The existing uncommitted `.planning/ROADMAP.md` change belongs to the parent workflow and was not modified by this research.
- For delegated work, the parent stops the same task and waits; planning/execution delegation is explicitly authorized by the user, while debugging follows the repository's special inline session-manager rule.

## Sources

### Primary (HIGH confidence)

- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-CONTEXT.md` — locked product decisions, scope, measured baseline, and canonical references.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-AI-SPEC.md` — locked runtime settings, worker/prompt architecture, protocol, thresholds, 20-scenario evaluation, guardrails, and monitoring.
- `.planning/LIVE-CALL-INVARIANTS.md` and `AGENTS.md` — non-negotiable live-call/deployment rules.
- Spikes 004b, 005, and 006 — RTX 3060 latency/VRAM, 50-turn stability/WER, capacity-two streaming, and cancellation evidence.
- Opened production source files cited inline — actual roster, manager, call session/track, Web server call/voice persistence, client types/UI, migrations, and deploy path.
- Read-only OMEN probes, 2026-07-31 — Python/Torch/CUDA/GPU, scheduled task action paths, production package presence, and aggregate engine-id/settings inventory.

### Secondary (MEDIUM confidence)

- [Official faster-qwen3-tts v0.3.2 repository](https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2) — install requirements, native streaming, pull semantics, chunk sizing, full ICL, `non_streaming_mode`, and silence behavior.
- [Pinned upstream model implementation](https://github.com/andimarafioti/faster-qwen3-tts/blob/a70afc0f81f7f5f8801c3227968f1102f43f211c/faster_qwen3_tts/model.py) — inspected at the exact accepted source commit.
- [Pinned upstream streaming implementation](https://github.com/andimarafioti/faster-qwen3-tts/blob/a70afc0f81f7f5f8801c3227968f1102f43f211c/faster_qwen3_tts/streaming.py) — generator, chunk, and terminal behavior.
- [Pinned upstream dependency metadata](https://github.com/andimarafioti/faster-qwen3-tts/blob/a70afc0f81f7f5f8801c3227968f1102f43f211c/pyproject.toml) — Python/package constraints and official source metadata.
- [Immutable Qwen 1.7B Base snapshot](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base/tree/fd4b254389122332181a7c3db7f27e918eec64e3) — revision, model identity, license, and files.

### Tertiary (LOW confidence)

- None. No unverified community package or training-memory claim is used as a planning decision.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — exact official tag/commit/model snapshot were inspected, package registry verified, and the same combination passed OMEN spikes; package age remains an explicit SUS checkpoint.
- Architecture: HIGH — mapped against opened production code, locked CONTEXT/AI-SPEC, existing live-call regressions, and accepted RayMe-shaped stream evidence.
- Pitfalls: HIGH — the critical failures are directly visible in current code or reproduced in accepted spikes.
- Environment: HIGH — local and OMEN dependencies/runtime state were probed read-only during this session.
- UI wording: MEDIUM — exact copy remains delegated discretion, but required states/errors and existing surfaces are known.

**Research date:** 2026-07-31
**Valid until:** 2026-08-07 for the fast-moving upstream/package/deployment identity; architectural findings remain valid until the call pipeline changes.
