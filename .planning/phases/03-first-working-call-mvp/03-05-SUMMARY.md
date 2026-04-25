---
phase: 03-first-working-call-mvp
plan: "05"
subsystem: api
tags: [fastapi, calls, webrtc, sqlalchemy, prompt-context]
requires:
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-02 RED Web UI server call route, writeback, and call prompt contracts."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-04 AI backend WebRTC readiness, offer, and session control endpoints."
provides:
  - "Same-origin `/api/calls` Web UI server facade for start, offer, mute, interrupt, and end controls."
  - "Server-owned `call_id` to `rtc_` session mapping with durable call boundary and speech writeback."
  - "AI backend WebRTC proxy methods and call prompt context hydration over recent text plus speech rows."
affects: [03-first-working-call-mvp, web-ui-server, call-api, prompt-builder]
tech-stack:
  added: []
  patterns:
    - "FastAPI same-origin unsafe-method guard for browser call controls."
    - "Module-level active call registry mapping server call IDs to AI backend session IDs."
    - "Call prompt context helper reusing selected-branch prompt filtering with a 24-turn window."
key-files:
  created:
    - web-ui/server/app/domain/call_service.py
    - web-ui/server/app/api/calls.py
  modified:
    - web-ui/server/app/domain/ai_backend_client.py
    - web-ui/server/app/domain/prompt_builder.py
    - web-ui/server/app/main.py
key-decisions:
  - "Browser call controls go only through same-origin Web UI server routes; the browser never receives direct AI backend control ownership."
  - "The Web UI server owns `call_` IDs and maps them to server-generated `rtc_` session IDs before proxying AI backend WebRTC calls."
  - "Prior committed RED tests keep call boundary message text as `Call started` and `Call ended` while future plans can enrich summaries."
patterns-established:
  - "Call route dependencies expose `get_call_session` and `get_call_backend_client` for isolated server tests."
  - "Call prompt memory includes selected non-stale `user_text`, `ai_text`, `user_speech`, and `ai_speech` rows while excluding call boundary events."
requirements-completed: [REQ-40, REQ-47, REQ-50, REQ-A1]
duration: 7m 16s
completed: 2026-04-25
---

# Phase 03 Plan 05: Web UI Server Call Facade Summary

**Web UI server-owned call facade with `call_`/`rtc_` session mapping, same-origin controls, AI backend proxying, and durable thread writeback.**

## Performance

- **Duration:** 7m 16s
- **Started:** 2026-04-25T20:33:28Z
- **Completed:** 2026-04-25T20:40:44Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `CallService` for thread-or-character call starts, voice preflight, server-generated active-call records, mute/interrupt/end state, and chronological `messages` writes.
- Added `/api/calls/start`, `/offer`, `/mute`, `/interrupt`, and `/end` routes with unsafe-method Origin rejection and server-owned call/session lookup.
- Extended `AiBackendClient` with WebRTC status, offer, mute, interrupt, and end proxy methods.
- Implemented `build_call_prompt_context` so call offers hydrate recent selected text and speech rows while excluding `call_start`/`call_end` events.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add CallService for preflight and writeback** - `774cddb` (feat)
2. **Task 2: Add same-origin call API and AI backend proxy methods** - `c4b87d2` (feat)

## Files Created/Modified

- `web-ui/server/app/domain/call_service.py` - New durable call service, active-call registry, voice validation, and thread chronology writes.
- `web-ui/server/app/api/calls.py` - New same-origin call facade with start, offer, mute, interrupt, and end routes.
- `web-ui/server/app/domain/ai_backend_client.py` - Added WebRTC status, offer, and session-control proxy methods.
- `web-ui/server/app/domain/prompt_builder.py` - Added call prompt context helper for selected text/speech rows with a 24-turn window.
- `web-ui/server/app/main.py` - Included the calls router in the Web UI server app.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` - 12 passed.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_health_settings.py -q` - 30 passed.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_prompt_builder.py web-ui/server/tests/test_health_settings.py -q` - 39 passed.

## Decisions Made

- Server-generated `rtc_` session IDs are returned at call start and reused for `/webrtc/offer`, preserving Web UI server ownership of the call-to-session mapping.
- Missing Origin headers are allowed for non-browser tests, while foreign Origin headers are rejected with `call_origin_not_allowed`.
- The route layer accepts test fakes through dependency overrides while production paths use `AiBackendClient`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 route-level verification depended on Task 2**
- **Found during:** Task 1
- **Issue:** The Task 1 verification command exercises `/api/calls/*`, but the plan assigns those routes to Task 2.
- **Fix:** Committed Task 1 after satisfying service-level static criteria, then cleared the same verification command after Task 2 added the router.
- **Files modified:** `web-ui/server/app/domain/call_service.py`, `web-ui/server/app/api/calls.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` passed after Task 2.
- **Committed in:** `774cddb`, `c4b87d2`

**2. [Rule 3 - Blocking] Added missing call prompt context helper required by plan verification**
- **Found during:** Task 2
- **Issue:** Plan-level verification included `test_prompt_builder.py`, whose prior RED tests required `build_call_prompt_context`.
- **Fix:** Added `build_call_prompt_context` using the selected-branch prompt filtering pattern and a `max_turns=24` call window.
- **Files modified:** `web-ui/server/app/domain/prompt_builder.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py -q` passed as part of the 39-test plan suite.
- **Committed in:** `c4b87d2`

**3. [Rule 1 - Contract Alignment] Preserved prior RED boundary-row text**
- **Found during:** Task 1
- **Issue:** The implementation plan requested richer `call_start`/`call_end` prose, while the committed Phase 03-02 RED tests assert exact `Call started` and `Call ended` content.
- **Fix:** Preserved the committed contract for this plan so server tests remain authoritative; richer call summaries can be layered in a later contract update.
- **Files modified:** `web-ui/server/app/domain/call_service.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` passed.
- **Committed in:** `774cddb`

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 contract alignment).
**Impact on plan:** All changes stayed within the call facade, prompt context, and durable writeback surface needed for the plan.

## Issues Encountered

- Task 1's test command could not pass before the Task 2 route layer existed. The final plan verification passes.

## Known Stubs

None. Test-only fake backend fallbacks are dependency-override paths; production routes use `AiBackendClient`.

## Threat Flags

None. The new call routes and same-origin guard are covered by the plan threat model.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 03-06 can build the client call API/FSM against the committed `/api/calls` facade and `rayme-events` channel contract.

## Self-Check: PASSED

- Found expected files: `web-ui/server/app/domain/call_service.py`, `web-ui/server/app/api/calls.py`, `web-ui/server/app/domain/ai_backend_client.py`, `web-ui/server/app/domain/prompt_builder.py`, `web-ui/server/app/main.py`, `.planning/phases/03-first-working-call-mvp/03-05-SUMMARY.md`.
- Found task commits: `774cddb`, `c4b87d2`.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
