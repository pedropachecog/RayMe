---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 10
subsystem: web-api
tags: [qwen3-tts, incremental-llm, speech-segmentation, sse, terminal-persistence]

requires:
  - phase: 09-06
    provides: Saved-voice-derived Qwen prompt ownership and exact cancellation lifecycle
  - phase: 09-11
    provides: Native streamed playout completion, bounded audio credit, and terminal-safe controls
provides:
  - Deterministic natural-boundary live-call segmenter with a 60-word ceiling
  - Capacity-two sequential SpeechTurn scheduler over the existing WebRTC speak endpoint
  - Qwen speech submission before a held-open LLM stream completes
  - One exact durable assistant row only after normal completed playout
affects: [09-12, 09-13, 09-14, qwen3-evaluation, call-history, live-call-orchestration]

actuals:
  tokens: 11876
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns: [incremental-natural-segmentation, bounded-turn-scheduler, typed-speech-terminal, terminal-authorized-persistence]

key-files:
  created:
    - web-ui/server/app/domain/call_tts_segments.py
    - web-ui/server/tests/test_call_tts_segments.py
  modified:
    - web-ui/server/app/api/calls.py
    - web-ui/server/app/domain/ai_backend_client.py
    - web-ui/server/app/domain/call_service.py
    - web-ui/server/tests/test_calls.py

key-decisions:
  - "Incremental Qwen text uses the existing WebRTC speak endpoint through a capacity-two turn scheduler; no browser route or second service was added."
  - "Natural sentence and safe newline boundaries emit as soon as useful, tiny fragments remain attached, and a late phrase boundary or the 60th word enforces the hard segment ceiling."
  - "Only a typed normal terminal with completed playout authorizes one durable ai_speech row containing the exact visible accumulated text."
  - "Hangup cancels the server-owned LLM/speech turn before ending the backend session so late completion cannot write history."

patterns-established:
  - "SpeechTurn.submit accepts bounded non-final work without waiting for terminal playout; SpeechTurn.finalize is the single terminal wait and one backend request runs at a time."
  - "Cancelled/error terminals, call end, and repeated completion for the same turn id fail closed before durable assistant writeback or normal ai_done."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "A safe Qwen sentence enters native speech work while a deliberately held-open LLM stream continues, with deterministic natural segmentation and a 60-word bound."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "web-ui/server/tests/test_calls.py#test_qwen_slow_llm_submits_first_safe_segment_before_stream_completion"
        status: pass
      - kind: unit
        ref: "web-ui/server/tests/test_call_tts_segments.py (7 passed as part of the 69-test plan suite)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A normal multi-segment turn writes one exact ai_speech row only after completed playout, while blank, cancelled, hung-up, ceiling, and worker-error turns write none and emit no normal ai_done."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_call_tts_segments.py -q (69 passed)"
        status: pass
      - kind: integration
        ref: "uv run --project web-ui/server pytest web-ui/server/tests -q (224 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Cancelled turn schedulers reject later segments, later calls remain usable, SSE errors stay fixed and private-free, and VoxCPM2 keeps its early-stream/no-whole-fallback contract."
    requirement: REQ-46
    verification:
      - kind: integration
        ref: "web-ui/server/tests/test_calls.py#test_speech_turn_rejects_post_cancel_submission_and_a_later_turn_can_finish"
        status: pass
      - kind: integration
        ref: "AI backend slow/stream/playback/metric/fallback recurrence suite (14 passed)"
        status: pass
    human_judgment: false

duration: 18min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 10: Incremental LLM-to-TTS and Terminal Persistence Summary

**Qwen now starts speaking from the first safe LLM phrase through a bounded sequential scheduler, while durable call history records only normally completed playout.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-31T20:37:12Z
- **Completed:** 2026-07-31T20:54:46Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added deterministic incremental segmentation that preserves punctuation, avoids tiny fragments, prefers natural boundaries, forces a phrase no later than 60 words, and flushes one final tail.
- Started the first Qwen synthesis segment while a slow LLM stream remained open, with capacity-two acceptance and one sequential backend generation owner.
- Kept `ai_token` captions flowing during segment submission and kept SSE alive while final playout completed, without adding a browser/API topology.
- Moved durable `ai_speech` writeback behind one typed normal terminal plus completed playout and suppressed normal completion for cancellation, hangup, ceiling, and worker failures.
- Preserved non-Qwen single-request behavior and the existing VoxCPM2 early-stream/no-whole-synthesis regressions.

## Task Commits

Each TDD task was committed as separate RED and GREEN gates:

1. **Task 1 RED: Define incremental Qwen segment contracts** - `5daa017` (test)
2. **Task 1 GREEN: Stream Qwen segments during LLM generation** - `074eca4` (feat)
3. **Task 2 RED: Define terminal-authorized speech persistence** - `113fbc6` (test)
4. **Task 2 GREEN: Persist speech only after normal playout** - `2c6f079` (feat)

## Files Created/Modified

- `web-ui/server/app/domain/call_tts_segments.py` - Pure incremental natural-boundary segmenter with tiny-fragment retention and hard word ceiling.
- `web-ui/server/app/domain/ai_backend_client.py` - Capacity-two `SpeechTurn.submit/finalize` scheduler and sanitized normal/cancelled/error terminal model.
- `web-ui/server/app/api/calls.py` - Incremental Qwen token pump, SSE state/keepalive handling, terminal gating, and hangup cancellation.
- `web-ui/server/app/domain/call_service.py` - Exact-once normal-playout authorization for durable assistant speech.
- `web-ui/server/tests/test_call_tts_segments.py` - Table-driven boundary, punctuation, tail, phrase, and ceiling contracts.
- `web-ui/server/tests/test_calls.py` - Held-open LLM, multi-segment, blank, cancellation, hangup, failure, privacy, persistence, and recovery regressions.

## Decisions Made

- Reused the existing `/webrtc/sessions/{session_id}/speak` topology. The internal scheduler owns segment admission and finalization, keeping upstream/browser details out of the public API.
- Limited incremental segmentation to Qwen live turns. Existing engines retain their compatible single final speech request, while all engines benefit from terminal-authorized persistence.
- Treated the last completed non-final Qwen segment as the turn terminal when LLM EOS leaves no unsent tail; completed playout remains mandatory before persistence.
- Kept the exact visible LLM text as the durable artifact rather than reconstructing it from normalized spoken segments.
- Cancelled the active server turn on both interrupt and hangup, then let the existing backend control path stop matching generation and playout.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None beyond the expected failing RED persistence cases. The planned terminal gate made all cancellation, hangup, error, and normal multi-segment contracts green.

## Known Stubs

None.

## Verification

- Task 1 focused segment/Qwen gate: 18 passed, 43 deselected.
- Complete Plan 09-10 server gate: 69 passed.
- Full Web UI server suite: 224 passed.
- Slow-stream, playback, metric, and no-whole-fallback recurrence gate: 14 passed, 98 deselected.
- Python compilation and `git diff --check`: passed.

## User Setup Required

None - no dependency, secret, route, service, or deployment setting was added.

## Next Phase Readiness

- Plan 09-12 can treat server-side first-segment timing and exact terminal persistence as deterministic evidence contracts.
- The final OMEN evidence runner can now prove the deployed path starts speech before LLM completion and stores only normally completed output.
- No implementation blocker, skipped test, known stub, or unrun verification remains in this plan.

## Self-Check: PASSED

- All six implementation/test files and this summary exist.
- Commits `5daa017`, `074eca4`, `113fbc6`, and `2c6f079` exist in git history in RED/GREEN order.
- Both task gates, the full server suite, the live-call recurrence suite, compilation, and `git diff --check` passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
