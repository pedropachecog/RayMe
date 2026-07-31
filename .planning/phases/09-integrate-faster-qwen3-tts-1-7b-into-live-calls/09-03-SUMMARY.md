---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 03
subsystem: ai-runtime
tags: [qwen3-tts, webrtc, native-streaming, backpressure, cancellation, readiness]

requires:
  - phase: 09-02
    provides: Supervised native Qwen worker, full-ICL prompt ownership, and exact-request cancellation
provides:
  - Responsive one-hot Qwen model loading with separately observable selected-voice prompt readiness
  - Strict RayMe-owned WebRTC prepare and speak contracts for opaque saved-voice identity
  - Capacity-two Qwen native-stream bridge with early playback, truthful metrics, and exact cancellation
affects: [09-04, 09-08, 09-11, qwen3-deployment, call-session, webrtc-status]

actuals:
  tokens: 14081
  tasks: 2
  commits: 5

tech-stack:
  added: []
  patterns: [async-one-hot-prepare, split-model-prompt-readiness, bounded-thread-async-bridge, request-scoped-call-cancellation]

key-files:
  created: []
  modified:
    - ai-backend/app/models/tts_registry.py
    - ai-backend/app/models/model_manager.py
    - ai-backend/app/api/webrtc.py
    - ai-backend/app/call/session.py
    - ai-backend/tests/test_model_manager.py
    - ai-backend/tests/test_webrtc_signaling.py
    - ai-backend/tests/test_call_session.py

key-decisions:
  - "Expose Qwen model residency and selected opaque-voice prompt readiness as separate state machines so a resident model cannot masquerade as a call-ready voice."
  - "Admit live native streaming only for the explicit voxcpm2 and qwen3_1_7b engine set; Qwen receives the exact turn id as request id and never reaches whole synthesis."
  - "Use a capacity-two blocking thread-to-async bridge and report its high-water/block time only in terminal metrics while preserving bounded startup playback."
  - "Signal the matching adapter request before cancelling the call task, and use the same path for interrupt and hangup so no cancelled turn emits ai_done."

patterns-established:
  - "Qwen call readiness requires both resident model state and ready selected-voice prompt state for the exact opaque voice key."
  - "Threaded streaming producers enter asyncio through run_coroutine_threadsafe(queue.put) against a capacity-two queue; cancellation breaks blocked admission without dropping normal chunks."
  - "Immediate ai_audio_started evidence contains only facts known at playback start; generation totals, bridge high-water, and producer blocking time are terminal-only."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "Qwen model residency and selected-voice prompt readiness are separate, responsive, one-hot states exposed through sanitized RayMe WebRTC status and prepare contracts."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py ai-backend/tests/test_webrtc_signaling.py -q (41 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A held-open Qwen producer starts outbound audio before stream completion through a capacity-two blocking bridge without whole-synthesis fallback or dropped chunks."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "ai-backend/tests/test_call_session.py Qwen slow-stream and capacity-two backpressure contracts"
        status: pass
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py ai-backend/tests/test_tts_voxcpm2.py -q (99 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Qwen interrupt and hangup before or after first audio stop playout, cancel the exact request, restore listening or ended state, reject late completion, and preserve VoxCPM2 live-stream invariants."
    requirement: REQ-46
    verification:
      - kind: integration
        ref: "ai-backend/tests/test_call_session.py#test_qwen_termination_cancels_exact_request_and_rejects_normal_completion"
        status: pass
      - kind: integration
        ref: "ai-backend/tests/test_tts_voxcpm2.py recurrence suite in the 99-test verification command"
        status: pass
    human_judgment: false

duration: 18min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 03: Qwen Live-Call Contract Summary

**RayMe now prepares the exact Qwen voice visibly and streams its native audio into live calls through a bounded bridge that starts early and cancels the matching request cleanly.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-31T16:01:00Z
- **Completed:** 2026-07-31T16:19:24Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added responsive async one-hot engine preparation and a separate selected-voice prompt readiness state with same-key idempotence and sanitized failures.
- Added strict `/webrtc` prepare/status/speak boundaries carrying deployed commit, opaque voice identity, contained reference bytes, exact transcript, and no browser model or filesystem path.
- Routed Qwen only through its native generator and a capacity-two blocking bridge, proving first playback before a deliberately held-open producer completes.
- Added exact-request cancellation for interrupt and hangup before and after first audio, with stopped playout, no late `ai_done`, and correct listening/ended recovery.
- Kept the established VoxCPM2 early-playback, no-whole-synthesis, timing-carrier, and interruption recurrence suite green.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Define readiness and strict WebRTC contracts** - `e64af32` (test)
2. **Task 1 GREEN: Implement Qwen model and prompt readiness** - `a65eaa0` (feat)
3. **Task 2 RED: Define Qwen live stream, backpressure, and cancellation contracts** - `7e00a79` (test)
4. **Task 2 test repair: Correct retained adapter assertion scope** - `4e3c89a` (test)
5. **Task 2 GREEN: Implement bounded Qwen streaming and exact cancellation** - `778cc5e` (feat)

## Files Created/Modified

- `ai-backend/app/models/tts_registry.py` - Strict generic synthesis identities for request, turn, and opaque voice key.
- `ai-backend/app/models/model_manager.py` - Async one-hot engine preparation and independent selected-voice prompt state.
- `ai-backend/app/api/webrtc.py` - Strict Qwen prepare/speak validation plus deployed-commit and readiness status carriers.
- `ai-backend/app/call/session.py` - Explicit Qwen streaming route, capacity-two bridge, terminal metrics, and interrupt/hangup cancellation.
- `ai-backend/tests/test_model_manager.py` - Slow-load responsiveness, one-hot residency, prompt-state, idempotence, and failure contracts.
- `ai-backend/tests/test_webrtc_signaling.py` - Strict payload, sanitized status, readiness gate, and prepared Qwen native-stream route coverage.
- `ai-backend/tests/test_call_session.py` - Slow Qwen early-playback, blocking backpressure, no-fallback, interrupt, and hangup regressions.

## Decisions Made

- Model `idle|loading|resident|unavailable` and selected-voice prompt `none|prewarming|ready|failed` remain separate public facts; call readiness requires both for the exact voice.
- Qwen and VoxCPM2 are the only current engines admitted to the live native-stream path by explicit engine identity plus callable stream support.
- The producer blocks on capacity-two admission instead of using an unbounded callback queue or dropping chunks; queue capacity, high-water, and producer wait time are final metrics.
- Cancellation marks the turn cancelled and stops outbound playout before signalling the exact adapter request, then cancels the call task. The adapter signal is idempotent across the control path and task cancellation handler.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected Qwen slow-stream test adapter scope**
- **Found during:** Task 2 GREEN verification
- **Issue:** The RED test created its scripted adapter inside the async scenario but asserted its captured request identity outside that scope.
- **Fix:** Retained the adapter in the enclosing test scope without changing the behavior under test.
- **Files modified:** `ai-backend/tests/test_call_session.py`
- **Verification:** Focused Qwen contract run passed, followed by the full 99-test Task 2 suite.
- **Committed in:** `4e3c89a`

---

**Total deviations:** 1 auto-fixed bug.
**Impact on plan:** Test-only scope correction; no product scope change.

## Issues Encountered

- The optional Ruff executable is not installed in the existing backend environment, so no unplanned package installation was attempted. Both prescribed pytest commands and `git diff --check` passed.

## User Setup Required

None - real OMEN model materialization, deployment, saved-voice preparation, and hardware tracer execution remain Plan 09-04.

## Next Phase Readiness

- Plan 09-04 can deploy the canonical runtime and exercise the real saved-voice path through manager prepare, strict WebRTC boundaries, CallSession early playback, and exact cancellation.
- Local behavior is proven with model-free fakes. This plan does not claim real RTX 3060 audio quality, latency, or physical-call readiness; those remain blocking hardware evidence.

## Self-Check: PASSED

- All seven modified implementation/test files and this summary exist.
- Commits `e64af32`, `a65eaa0`, `7e00a79`, `4e3c89a`, and `778cc5e` are present in git history.
- The prescribed readiness/status suite passed 41 tests; the prescribed call/WebRTC/Vox suite passed 99 tests; the prohibited whole-synthesis source scan and `git diff --check` passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
