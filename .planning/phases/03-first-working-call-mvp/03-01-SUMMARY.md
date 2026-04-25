---
phase: 03-first-working-call-mvp
plan: "01"
subsystem: testing
tags: [pytest, ai-backend, webrtc, call-session, red-tests]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: "Phase 2 WebRTC skeleton routes and AI backend pytest infrastructure"
provides:
  - "RED call session lifecycle contracts for mute, interrupt, teardown, failure state, and stats"
  - "RED inbound mic-audio finalization contract from VAD end-of-turn to STT user_final event"
  - "RED WebRTC signaling and session control route contracts"
affects: [03-first-working-call-mvp, ai-backend, call-session, webrtc-signaling]

tech-stack:
  added: []
  patterns: ["pytest RED contract tests before Phase 3 implementation"]

key-files:
  created: [ai-backend/tests/test_call_session.py]
  modified: [ai-backend/tests/test_webrtc_signaling.py]

key-decisions:
  - "Phase 3 AI backend call behavior is locked by RED tests before replacing the Phase 2 WebRTC skeleton."
  - "Inbound mic audio must finalize through VAD and STT into a typed user_final event, not through fabricated JSON input."
  - "WebRTC malformed payloads must return sanitized 400/422 validation responses without traceback text."

patterns-established:
  - "CallSession tests use fake peer, VAD, STT, and AI-turn doubles to define backend session behavior without loading models."
  - "WebRTC signaling tests assert public JSON response contracts and sanitized validation behavior through FastAPI TestClient."

requirements-completed: [REQ-47, REQ-A0, REQ-A1]

duration: 5min
completed: 2026-04-25
---

# Phase 03 Plan 01: AI Backend Call Contract Tests Summary

**RED pytest contracts now define the Phase 3 AI backend call session and WebRTC signaling surface before live media implementation begins.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-25T19:52:27Z
- **Completed:** 2026-04-25T19:57:07Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Added `CallSession` / `CallSessionManager` lifecycle tests for stable session IDs, server-side mute, interrupt cancellation, idempotent teardown, failed connection cleanup, and stats.
- Added inbound audio tests requiring unmuted PCM frames to buffer until VAD end-of-turn, call STT once, and emit exactly one `user_final` event.
- Replaced the Phase 2 WebRTC “offer always rejects” test with Phase 3 status, offer/answer, mute, interrupt, end, and sanitized malformed-payload contracts.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add RED call session tests** - `736b2cb` (test)
2. **Task 2: Add RED inbound audio to user_final tests** - `9a69043` (test)
3. **Task 3: Extend WebRTC signaling tests for live call contracts** - `78b0e4b` (test)

**Plan metadata:** final docs commit records this summary and state updates.

## Files Created/Modified

- `ai-backend/tests/test_call_session.py` - New RED contracts for future `app.call.session` session manager, lifecycle, mute, interrupt, teardown, stats, and inbound audio finalization.
- `ai-backend/tests/test_webrtc_signaling.py` - Updated RED contracts for Phase 3 WebRTC status, offer/answer, control routes, and sanitized validation errors.

## Decisions Made

- Call session implementation must expose `CallSession` and `CallSessionManager` from `app.call.session`.
- Server-side mute must count inbound frames as dropped while preventing VAD/STT consumption.
- The call data event for finalized user speech is typed as `user_final` with `session_id`, `turn_id`, and `text`.
- WebRTC signaling uses `/webrtc/offer` plus `/webrtc/sessions/{session_id}/mute`, `/interrupt`, and `/end` controls.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` failed as expected with `ModuleNotFoundError: No module named 'app.call'`.
- `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q` failed as expected against the Phase 2 skeleton: missing `active_sessions`, `/webrtc/offer` still returns `501`, and session control routes still return `404`.
- `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` failed as expected during collection on missing `app.call`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The failing pytest results are intentional RED contract failures for missing Phase 3 implementation.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 3 implementation plans can now replace the Phase 2 WebRTC skeleton by satisfying the committed RED contracts.

## Self-Check: PASSED

- Created/modified files exist: `ai-backend/tests/test_call_session.py`, `ai-backend/tests/test_webrtc_signaling.py`, `.planning/phases/03-first-working-call-mvp/03-01-SUMMARY.md`.
- Task commits exist in git history: `736b2cb`, `9a69043`, `78b0e4b`.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
