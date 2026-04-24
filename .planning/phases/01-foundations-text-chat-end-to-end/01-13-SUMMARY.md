---
phase: 01-foundations-text-chat-end-to-end
plan: "13"
subsystem: api
tags: [fastapi, sqlalchemy, threads, messages, alternates]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 08 storage schema and Plan 12 character CRUD/import APIs"
provides:
  - "Thread list/detail/create/rename/delete API routes"
  - "Opening assistant messages from first_mes or selected alternate greeting"
  - "Full thread hydration with selected alternates, ordered alternate lists, and stale flags"
  - "Home-ready thread list rows with character name, portrait reference, snippet, and activity ordering"
affects: [web-ui-server, home, chat, thread-management, message-actions]

tech-stack:
  added: []
  patterns:
    - "ThreadService owns SQLAlchemy-backed thread creation, hydration, rename, and delete behavior"
    - "Thread routes expose dependency-overridable async SQLAlchemy sessions for tests"
    - "Thread message payloads reuse ThreadMessageShape selected-branch serialization"

key-files:
  created:
    - web-ui/server/app/domain/thread_service.py
    - web-ui/server/app/api/threads.py
  modified:
    - web-ui/server/app/main.py
    - web-ui/server/tests/test_threads.py

key-decisions:
  - "POST /api/threads returns only thread_id for client navigation."
  - "Thread creation always persists the opening assistant message with a selected message_alternates row using source_action='first_mes'."
  - "DELETE /api/threads/{thread_id} removes only the selected thread's messages, alternates, and thread row."

patterns-established:
  - "Hydrate message content through selected_alternate_id before returning thread detail or list snippets."
  - "Return typed 400 detail codes for invalid alternate_greeting_index values."
  - "Keep thread API tests end-to-end through FastAPI and temporary SQLite databases."

requirements-completed: [REQ-17, REQ-30, REQ-31, REQ-60, REQ-70, REQ-71, REQ-72]

duration: 6min
completed: 2026-04-24
---

# Phase 01 Plan 13: Backend Thread Management Summary

**FastAPI thread management with durable first-message openings, selected alternate hydration, and Home-ready thread list metadata.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-24T05:41:12Z
- **Completed:** 2026-04-24T05:47:41Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added `/api/threads` list/detail/create/rename/delete routes and registered them with the Web UI FastAPI app.
- Added `ThreadService` for creating threads from active characters, snapshotting card metadata, and inserting the opening `ai_text` turn at sequence 0.
- Persisted first message and selected alternate greetings as selected `message_alternates` rows with `source_action='first_mes'`.
- Hydrated thread detail with chronological messages, selected content, selected alternate IDs, ordered alternates, and stale flags.
- Replaced contract-only thread tests with API-backed SQLite tests for creation, alternate greeting selection/rejection, detail hydration, list sorting/snippets/portrait references, rename, and scoped delete.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement thread APIs and opening greetings** - `cd1043b` (`feat`)

**Plan metadata:** this summary is committed separately.

## Files Created/Modified

- `web-ui/server/app/domain/thread_service.py` - SQLAlchemy thread service for list/detail/create/rename/delete and selected-branch hydration.
- `web-ui/server/app/api/threads.py` - FastAPI thread route contracts, request models, dependency override points, and typed errors.
- `web-ui/server/app/main.py` - Registers the thread router before static client mounting.
- `web-ui/server/tests/test_threads.py` - API-backed tests for all planned thread behavior.

## Decisions Made

- `POST /api/threads` returns `{"thread_id": "..."}` only, matching the navigation contract.
- Opening messages always get a selected alternate row, including the default `first_mes`, so hydration can prove the selected opening text is durable.
- Thread delete is scoped as a hard delete of the selected thread's conversation rows; tests prove other threads remain queryable.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Registered thread router in the app factory**
- **Found during:** Task 1 (Implement thread APIs and opening greetings)
- **Issue:** The plan's target file list did not include `web-ui/server/app/main.py`, but the new `/api/threads` routes would be unreachable without router registration.
- **Fix:** Imported and included `threads_router` in `create_app()` before static client mounting.
- **Files modified:** `web-ui/server/app/main.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q`
- **Committed in:** `cd1043b`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** Required to make the planned API usable; no architecture or schema change was introduced.

## Issues Encountered

- The initial list-snippet test setup changed a message fallback but not its selected alternate; the fixture was corrected to update the selected alternate row because the API correctly resolves selected content.

## Known Stubs

None. Stub scan found only intentional optional `None` defaults and local empty grouping initialization in typed code/tests.

## User Setup Required

None - no external service configuration required.

## Shared Orchestrator Artifacts

Per sequential wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q` - PASS, 7 tests.
- `rg "/api/threads|alternate_greeting_index|source_action=.*first_mes|updated_at|selected_alternate_id|stale_after_edit|alternates" web-ui/server/app web-ui/server/tests/test_threads.py` - PASS.
- `uv run --project web-ui/server ruff check web-ui/server/app/domain/thread_service.py web-ui/server/app/api/threads.py web-ui/server/app/main.py web-ui/server/tests/test_threads.py` - PASS.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_app.py -q` - PASS, 2 tests.

## Next Phase Readiness

Home and Chat frontend work can consume real thread list/detail/create/rename/delete endpoints, and later message-action work can rely on selected alternate IDs and stale flags returning through the thread hydration contract.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-13-SUMMARY.md`.
- Key created files exist on disk.
- Task commit `cd1043b` exists in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remained untouched.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
