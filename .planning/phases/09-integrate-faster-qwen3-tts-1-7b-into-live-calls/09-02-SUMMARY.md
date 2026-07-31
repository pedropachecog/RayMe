---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 02
subsystem: ai-runtime
tags: [qwen3-tts, worker-ipc, cuda-isolation, voice-cloning, native-streaming]

requires:
  - phase: 09-01
    provides: Immutable Faster Qwen3-TTS runtime lock and truthful qwen3_1_7b roster identity
provides:
  - Versioned bounded request-scoped Qwen worker command and event protocol
  - Spawned CUDA-only 1.7B runtime with capacity-one full-ICL prompt ownership
  - Native streaming-only adapter with exact-request cancellation and worker containment
affects: [09-03, model-manager, call-session, qwen3-deployment, qwen3-evidence]

actuals:
  tokens: 19051
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns: [pydantic-discriminated-ipc, spawned-cuda-owner, capacity-one-icl-cache, request-scoped-cancellation]

key-files:
  created:
    - ai-backend/app/models/tts_qwen3_protocol.py
    - ai-backend/app/models/tts_qwen3_worker.py
  modified:
    - ai-backend/app/models/tts_qwen3.py
    - ai-backend/tests/test_tts_qwen3.py

key-decisions:
  - "Keep all Torch, Faster Qwen3-TTS, model, and full-ICL prompt ownership inside one spawned worker; the parent adapter handles only validated JSON events and WAV bytes."
  - "Treat generator exhaustion as normal authority while converting token/audio ceilings, malformed IPC, and runtime failures into one request-scoped non-success terminal."
  - "Preserve cancellation that arrives before worker dispatch, require the matching cancelled terminal, and terminate the worker when acknowledgement does not arrive within two seconds."

patterns-established:
  - "Qwen worker IPC accepts only schema-version-one discriminated commands/events with bounded identities, payloads, timing, and counts."
  - "A Qwen generation request has monotonic chunks, an adapter-enforced cumulative duration ceiling, and exactly one done/cancelled/error terminal."
  - "Qwen3TtsAdapter.synthesize is deliberately unavailable; production Qwen audio can only use generate_voice_clone_streaming."

requirements-completed: [REQ-22, REQ-45]

coverage:
  - id: D1
    description: "Malformed, oversized, wrong-version, cross-request, non-monotonic, duplicate-terminal, and late Qwen worker data is rejected before it can become readiness or playout state."
    requirement: REQ-22
    verification:
      - kind: unit
        ref: "ai-backend/tests/test_tts_qwen3.py protocol/schema/event contracts (23 focused cases)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The spawned worker alone owns the exact CUDA runtime and one full-ICL prompt, while the adapter pulls only native 24 kHz chunks and contains cancellation, malformed events, hangs, and worker failures."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py -q (35 passed)"
        status: pass
      - kind: integration
        ref: "Qwen/registry/model-manager focused compatibility sweep (63 passed)"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 02: Supervised Qwen Worker and Protocol Summary

**A spawned CUDA-only Qwen worker now owns the immutable 1.7B model and one full-ICL voice prompt, emitting only validated native stream chunks under exact-request cancellation.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-31T15:40:36Z
- **Completed:** 2026-07-31T15:53:48Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added bounded Pydantic command/event unions for load, prewarm, generate, cancel, invalidate, unload, readiness, chunks, and terminal outcomes.
- Replaced the 0.6B import-gated placeholder with a supervised `qwen3_1_7b` adapter that never imports CUDA/model code in the parent process.
- Added the worker-local exact 1.7B Torch CUDA/SDPA load, warmup, capacity-one full-ICL prompt, native four-step stream, audio/token ceilings, and request-scoped cancellation.
- Proved malformed IPC and stuck workers are terminated without whole-synthesis, generic generate, CPU, x-vector-only, or prompt-tensor fallback.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Define worker protocol contracts** - `ae78f88` (test)
2. **Task 1 GREEN: Implement validated worker IPC** - `7988d86` (feat)
3. **Task 2 RED: Define worker lifecycle and native-stream contracts** - `137f1c5` (test)
4. **Task 2 GREEN: Implement supervised worker and streaming adapter** - `2f0d1e6` (feat)

## Files Created/Modified

- `ai-backend/app/models/tts_qwen3_protocol.py` - Strict discriminated commands/events plus request-scoped stream sequence validation.
- `ai-backend/app/models/tts_qwen3_worker.py` - Sole CUDA/model/prompt owner with native generation, cancellation reader, and sanitized terminals.
- `ai-backend/app/models/tts_qwen3.py` - Spawn supervisor, load/prewarm/stream/cancel/invalidate/unload API, protocol enforcement, and terminate/kill containment.
- `ai-backend/tests/test_tts_qwen3.py` - Model-free protocol, exact-settings, full-ICL, stream, cancellation-race, timeout, malformed-event, and lifecycle regressions.

## Decisions Made

- The worker receives model location only from the deployment-owned environment and requires the exact approved model revision declaration; browser/request schemas never carry a filesystem path.
- Full reference audio and transcript cross IPC only on bounded prewarm commands. Generated requests carry the opaque selected voice key and target segment only; prompt tensors remain worker-local.
- Cancellation is considered successful only after the stream reader validates the matching `cancelled` terminal. Process shutdown can unblock a waiter but cannot masquerade as acknowledgement.
- A native runtime exception after emitted audio produces one error terminal with the matching chunk count and no private exception detail.

## Deviations from Plan

None - plan executed exactly as written. The pre-dispatch cancellation race, cumulative audio validation, and matching error-terminal count were required parts of D-17/T-09-01 rather than scope additions.

## Issues Encountered

- The initial fake lifecycle assertion treated `unload` as a logical flag only. The locked architecture requires process ownership cleanup, so the test was corrected to require worker termination after unload.

## User Setup Required

None - model snapshot materialization and OMEN environment wiring remain owned by the canonical deployment plans.

## Next Phase Readiness

- Plan 09-03 can attach this adapter to one-hot manager residency and expose model versus selected-voice prompt readiness separately.
- The local tests import/download no real model; OMEN CUDA/model attestation remains intentionally deferred to the canonical deployment/evidence plans.

## Self-Check: PASSED

- All four implementation/test files and this summary exist.
- Commits `ae78f88`, `7988d86`, `137f1c5`, and `2f0d1e6` are present in git history.
- The prescribed 35-test Qwen suite, 63-test Qwen/registry/manager compatibility sweep, whole-synthesis source scan, and `git diff --check` passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
