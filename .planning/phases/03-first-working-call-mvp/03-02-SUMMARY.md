---
phase: 03-first-working-call-mvp
plan: "02"
subsystem: testing
tags: [pytest, fastapi, sqlalchemy, calls, prompt-context]
requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: "Durable voice ownership, unavailable-voice semantics, AI backend status boundary, and unified message schema."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-01 AI backend RED call signaling and inbound audio contracts."
provides:
  - "RED Web UI server call bootstrap and control route contracts."
  - "RED durable call_start/call_end writeback contract over existing messages.content_text."
  - "RED call prompt context contract for text plus speech rows with a 24-turn window."
affects: [03-first-working-call-mvp, web-ui-server, call-api, prompt-builder]
tech-stack:
  added: []
  patterns:
    - "FastAPI TestClient plus temporary SQLite fixtures for Web UI server contracts."
    - "Prompt builder repository fakes to lock selected-branch and stale-row behavior."
key-files:
  created:
    - web-ui/server/tests/test_calls.py
  modified:
    - web-ui/server/tests/test_prompt_builder.py
key-decisions:
  - "Call bootstrap and controls are specified as same-origin Web UI server routes before implementation."
  - "Call prompt memory uses recent selected non-stale text and speech rows, excluding call boundary events."
patterns-established:
  - "Call API RED tests assert fixed public error codes instead of raw backend or framework errors."
  - "Call prompt RED tests call a future build_call_prompt_context helper with max_turns=24."
requirements-completed: [REQ-40, REQ-50, REQ-63, REQ-A1]
duration: 5m 27s
completed: 2026-04-25
---

# Phase 03 Plan 02: Web UI Call Contract Tests Summary

**RED Web UI server contracts for call bootstrap, durable call boundary rows, voice/readiness failures, same-origin control safety, and sliding-window call prompt memory.**

## Performance

- **Duration:** 5m 27s
- **Started:** 2026-04-25T20:00:32Z
- **Completed:** 2026-04-25T20:05:59Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `web-ui/server/tests/test_calls.py` covering `POST /api/calls/start`, `/offer`, `/mute`, `/interrupt`, and `/end` without adding `/turns`.
- Locked public call failure codes: `call_voice_required`, `call_voice_unavailable`, `call_backend_not_ready`, `call_session_not_found`, and `call_origin_not_allowed`.
- Extended prompt-builder tests with call context expectations for `user_text`, `ai_text`, `user_speech`, `ai_speech`, event-row exclusion, selected-branch preservation, stale-row exclusion, and a 24-turn sliding window.

## Task Commits

1. **Task 1: Add RED call API and writeback tests** - `d0885a1` (test)
2. **Task 2: Add RED sliding-window call prompt tests** - `627c70c` (test)

## Files Created/Modified

- `web-ui/server/tests/test_calls.py` - New RED Web UI call API, control ownership, voice preflight, backend readiness, Origin rejection, and boundary writeback tests.
- `web-ui/server/tests/test_prompt_builder.py` - Added RED call prompt context tests on top of existing selected-branch prompt contracts.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` - RED: 12 failures, all from missing `/api/calls/*` implementation or missing call public error mapping.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py -q` - RED: 2 failures from missing `build_call_prompt_context`; 7 existing tests passed.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_prompt_builder.py -q` - RED: 14 failed, 7 passed.

## Decisions Made

- Used the planned route surface directly in tests rather than adding implementation scaffolding in this Wave 0 contract plan.
- Kept durable writeback on the existing `messages` table with `call_start` and `call_end` rows, matching the no-migration Phase 3 constraint.
- Specified call prompt context as a dedicated `build_call_prompt_context(..., max_turns=24, repository=...)` helper contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed test fixture insertion order**
- **Found during:** Task 1
- **Issue:** The initial RED fixture inserted a thread and opening message in one flush without ORM relationships, so SQLite could attempt the message insert before the thread row and raise a foreign-key error.
- **Fix:** Flushed the thread row before inserting the opening message and added safe helpers for public error-code assertions.
- **Files modified:** `web-ui/server/tests/test_calls.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` now reaches planned missing-route failures.
- **Committed in:** `d0885a1`

---

**Total deviations:** 1 auto-fixed blocking issue.
**Impact on plan:** The fix only made the RED test fixture valid; it did not add implementation or change the planned contracts.

## Issues Encountered

- The expected current state is RED. `/api/calls/*` routes and `build_call_prompt_context` are intentionally absent until later Phase 3 implementation plans.

## Known Stubs

None. Test fakes are intentional contract fixtures, not product stubs.

## Threat Flags

None. This plan added tests only; no new runtime endpoint, auth path, file access, schema, or trust-boundary implementation was introduced.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 03-03 and later implementation work can now target the committed Web UI call API and prompt-memory RED contracts.

## Self-Check: PASSED

- Found expected files: `web-ui/server/tests/test_calls.py`, `web-ui/server/tests/test_prompt_builder.py`, `.planning/phases/03-first-working-call-mvp/03-02-SUMMARY.md`.
- Found task commits: `d0885a1`, `627c70c`.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
