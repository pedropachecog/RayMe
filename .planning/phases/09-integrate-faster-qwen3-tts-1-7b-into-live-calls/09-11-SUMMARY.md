---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 11
subsystem: live-call-audio
tags: [webrtc, qwen3-tts, voxcpm2, backpressure, playout, cancellation, metrics]

requires:
  - phase: 09-05
    provides: Hardened native Qwen stream, exact-request cancellation, and bounded worker failure semantics
provides:
  - Sample-credited WebRTC playout bounded by paced 20 ms consumption
  - Physically separate immediate, generation-complete, and playout-complete metrics
  - Request-scoped terminal cancellation for interrupt, hangup, engine switch, failure, and session close
  - Late audio and normal-terminal rejection after cancellation while preserving VoxCPM2 no-fallback behavior
affects: [09-12, 09-13, 09-14, qwen3-evaluation, live-call-streaming]

actuals:
  tokens: 13619
  tasks: 2
  commits: 5

tech-stack:
  added: []
  patterns: [sample-credit-playout, paced-admission-backpressure, request-scoped-terminal-cancel, two-stage-playback-metrics]

key-files:
  created: []
  modified:
    - ai-backend/app/call/tracks.py
    - ai-backend/app/call/session.py
    - ai-backend/app/api/webrtc.py
    - ai-backend/tests/test_call_session.py
    - ai-backend/tests/test_webrtc_signaling.py

key-decisions:
  - "Bound playout by pending PCM samples across both the queue and internal frame buffer, releasing admission credit only when paced 20 ms recv consumes audio."
  - "Keep startup evidence in ai_audio_started while generation completion, playout completion, EOS, queue debt, underflow, join, order, and discard evidence exists only on the terminal metrics carrier."
  - "Mark the exact turn cancelled before stopping playout, signal the matching adapter request, drain the task within the two-second control budget, and reject all later audio-start or normal-done events."

patterns-established:
  - "Audio queue capacity is measured in samples/audio duration, not object count, and includes bytes already moved into the track's internal frame buffer."
  - "Every terminal call control carries its cause plus matching turn/request identity and terminal playout evidence without exposing runtime internals."

requirements-completed: [REQ-45, REQ-46]

coverage:
  - id: D1
    description: "Fast native TTS generation remains bounded by real 20 ms WebRTC playout consumption while first audio starts before stream completion."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "ai-backend/tests/test_call_session.py#test_qwen_fast_producer_is_bounded_by_paced_track_consumption"
        status: pass
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py ai-backend/tests/test_tts_voxcpm2.py -q -k 'slow or stream or playback or metric or fallback' (14 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Interrupt, barge-in, hangup, switch, failure, and close cancel the exact Qwen request, discard late output, suppress normal completion, and allow a clean later call."
    requirement: REQ-46
    verification:
      - kind: integration
        ref: "ai-backend/tests/test_call_session.py#test_qwen_control_causes_are_request_scoped_terminal_safe_and_recoverable"
        status: pass
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q -k 'cancel or interrupt or hangup or switch or close or late' (21 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The full AI backend remains green, including the VoxCPM2 native streaming path and its prohibition on whole-synthesis fallback."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests -q (229 passed)"
        status: pass
    human_judgment: false

duration: 23min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 11: Bounded Live Playout and Terminal-Safe Controls Summary

**Native Qwen and VoxCPM2 audio now reaches a sample-bounded paced WebRTC track with truthful terminal metrics and exact-request cancellation across every call-ending control.**

## Performance

- **Duration:** 23 min
- **Started:** 2026-07-31T19:39:46Z
- **Completed:** 2026-07-31T20:02:12Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Replaced the outbound track's unbounded audio accumulation with a fixed PCM-sample credit that includes both queued chunks and the internal frame buffer, blocks producers when full, and releases credit only as paced 20 ms frames are consumed.
- Removed the hidden whole-turn retention in `CallSession` by clearing startup WAV references immediately after early playback begins, while retaining the capacity-two thread/async bridge and first-audio-before-completion contract.
- Added terminal-only generation/playout evidence: generation and playout completion, natural EOS, bridge/track high-water, producer/admission block time, underflow, debt, joins, order violations, completed waits, and discarded samples/chunks.
- Made button interrupt, VAD-originated interruption, hangup, engine switch/reoffer, connection failure, and session close cancel the exact active request before stopping the normal turn lifecycle.
- Added a final event-boundary guard that discards late `ai_audio_started` and `ai_done` events for cancelled/terminal sessions, preventing stale audio or false normal completion from leaking into a later call.

## Task Commits

Each TDD task has separate RED and GREEN commits:

1. **Task 1 RED: Define paced playout credit contracts** - `8048801` (test)
2. **Task 1 GREEN: Bound streaming playout by paced audio credit** - `d067b31` (feat)
3. **Task 2 RED: Define terminal-safe Qwen control contracts** - `736d87b` (test)
4. **Task 2 GREEN: Make Qwen call controls terminal-safe** - `8003e2e` (feat)
5. **Post-GREEN correctness: Scope underflow to active playout** - `dfc3809` (fix)

## Files Created/Modified

- `ai-backend/app/call/tracks.py` - Pending-sample admission credit, paced release/notification, stop wakeup, and playout high-water/debt/underflow/join/order/discard metrics.
- `ai-backend/app/call/session.py` - Startup-buffer release, final metric separation, exact-request control cancellation, bounded task drain, recovery, and late-event rejection.
- `ai-backend/app/api/webrtc.py` - Existing-session reoffers now cancel an active turn before changing the selected voice or engine.
- `ai-backend/tests/test_call_session.py` - Slow-consumer credit, truthful metric, stop wakeup, six control-cause, late-event, and recovery recurrence coverage.
- `ai-backend/tests/test_webrtc_signaling.py` - Concurrent WebRTC Qwen speak/reoffer regression proving exact-request cancellation on engine switch.

## Decisions Made

- Used a 1.5-second default pending-audio budget, expressed as samples at the track's actual sample rate. Tests lower the budget explicitly to prove that the bound—not timing luck—forces admission blocking.
- Kept the existing 20 ms RTP pacing unchanged. Backpressure is credited by actual sample consumption rather than queue dequeue, so moving a chunk into `_buffer` cannot fake available capacity.
- Counted underflow only while admitted audio is actively draining, so ordinary silent RTP keepalive before first audio and after playout completion cannot masquerade as a smoothness defect.
- Kept `ai_audio_started` limited to first-known/startup facts. Every total, completion timestamp, EOS claim, and smoothness/debt field remains terminal-only.
- Reused the adapter's request-scoped cancellation acknowledgement and bounded it at the call boundary. A control records sanitized acknowledgement state but never exposes worker, model, path, or transcript details.
- Reoffers only cancel when the saved voice or engine actually changes; ordinary same-selection reconnect keeps the existing media recovery behavior.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The local optional Ruff executable is not installed in the AI backend environment, so no Ruff command was available. Python compilation, both focused plan commands, the full 229-test backend suite, commit hooks, and `git diff --check` all passed.

## User Setup Required

None - this plan adds no dependency, service, secret, or deployment setting.

## Next Phase Readiness

- Plans 09-12 and later evidence/deployment work can now measure real paced playout debt instead of the former unbounded track and can trust terminal cancellation identity across all backend controls.
- Physical call acceptance remains a later phase gate; this plan intentionally does not deploy OMEN.

## Self-Check: PASSED

- All five modified implementation/test files and this summary exist.
- Commits `8048801`, `d067b31`, `736d87b`, `8003e2e`, and `dfc3809` exist in git history in RED/GREEN order followed by the terminal-metric correctness fix.
- Task 1 focused verification passed 14 tests; Task 2 focused verification passed 21 tests; the complete backend suite passed 229 tests with three existing dependency warnings.
- `git diff --check` passed, VoxCPM2 no-whole-synthesis regressions remain green, and no stubs, skipped tests, unrun verification, unexpected deletions, or new unmodeled trust surface remains.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
