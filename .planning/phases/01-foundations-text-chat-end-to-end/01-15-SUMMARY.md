---
phase: 01-foundations-text-chat-end-to-end
plan: "15"
subsystem: api
tags: [fastapi, sqlalchemy, openai, chat, branching]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 14 selected-branch prompt builder and collect_chat_completion helper"
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 13 thread hydration with selected alternates and stale flags"
provides:
  - "LLM-backed regenerate, swipe, and continue message actions"
  - "Durable edit, stale, truncate, and keep-stale message actions"
  - "POST/PATCH /api/messages/{message_id} action routes returning ThreadMessageShape payloads"
affects: [web-ui-server, text-chat, message-actions, prompt-context]

tech-stack:
  added: []
  patterns:
    - "Message actions reuse build_prompt_context plus collect_chat_completion with server-side settings"
    - "Generated alternates are persisted and selected on the existing AI message row"
    - "Edit mutates the selected branch and marks downstream rows stale until truncate or keep"

key-files:
  created:
    - web-ui/server/app/api/messages.py
  modified:
    - web-ui/server/app/domain/message_actions.py
    - web-ui/server/app/main.py
    - web-ui/server/tests/test_message_actions.py

key-decisions:
  - "The /api/messages/{message_id}/swipes route also accepts an alternate_id to durably select an existing branch."
  - "Regenerate updates the target AI row content and selects a generated regenerate alternate, avoiding a second canonical AI turn."
  - "Keep-stale preserves downstream stale rows and updates thread activity; truncate-stale removes stale downstream rows."

patterns-established:
  - "Message action routes return the same ThreadMessageShape dictionary contract as thread hydration and stream done events."
  - "Non-stream generated actions use the same server-side LLM settings boundary as chat send."

requirements-completed: [REQ-32, REQ-33, REQ-34, REQ-35, REQ-60]

duration: 10min
completed: 2026-04-24
---

# Phase 01 Plan 15: Durable Message Actions Summary

**LLM-backed regenerate, swipe, and continue actions with durable selected alternates and edit stale-state handling.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-24T07:01:24Z
- **Completed:** 2026-04-24T07:11:56Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Implemented `SqlAlchemyMessageActionRepository` for regenerate, swipe, alternate selection, edit, truncate-stale, keep-stale, and continue.
- Added `/api/messages/{message_id}` action routes using persisted server LLM settings and the shared OpenAI-compatible collection helper.
- Expanded message-action tests to cover route-level durable behavior against SQLite with a fake LLM client.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement LLM-backed regenerate, swipe, edit, and continue routes** - `9be8558` (`feat`)

**Plan metadata:** this summary is committed separately.

## Files Created/Modified

- `web-ui/server/app/api/messages.py` - Message action route definitions, request validation, settings lookup, and response shaping.
- `web-ui/server/app/domain/message_actions.py` - Durable repository and domain functions for generated alternates and stale-state mutations.
- `web-ui/server/app/main.py` - Registers the message action router with the FastAPI app.
- `web-ui/server/tests/test_message_actions.py` - Contract and API integration coverage for regenerate, swipe, continue, edit, truncate, and keep-stale.

## Decisions Made

- Used the existing `message_alternates` table for generated regenerate/swipe/continue branches rather than adding schema.
- Let `/api/messages/{message_id}/swipes` select an existing alternate when `alternate_id` is supplied, so future UI swipe navigation can persist branch choice.
- Kept keep-stale as a preservation action: stale downstream rows remain flagged and visible, while truncate-stale removes only stale downstream rows.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Registered message action router in the app factory**
- **Found during:** Task 1 (Implement LLM-backed regenerate, swipe, edit, and continue routes)
- **Issue:** The plan's target files did not include `web-ui/server/app/main.py`, but the new `/api/messages/{message_id}/...` routes would be unreachable without router registration.
- **Fix:** Imported and included `messages_router` in `create_app()`.
- **Files modified:** `web-ui/server/app/main.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_app.py -q` as part of the 24-test relevant backend gate.
- **Committed in:** `9be8558`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** Required to expose the planned API surface. No schema or architecture change was introduced.

## Issues Encountered

None - implementation and verification completed without unresolved issues.

## Known Stubs

None. Stub scan found only the intentional optional empty `composer_text` default for Continue when no instruction/prefix is supplied.

## User Setup Required

None - no external service configuration is required for tests. Runtime message generation uses persisted Settings LLM values.

## Shared Orchestrator Artifacts

Per sequential wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` - PASS, 10 tests.
- `rg "collect_chat_completion|build_prompt_context|source_action=.*swipe|source_action=.*continue|alternate_index|truncate-stale|keep-stale" web-ui/server/app web-ui/server/tests/test_message_actions.py` - PASS.
- `uv run --project web-ui/server ruff check web-ui/server/app/domain/message_actions.py web-ui/server/app/api/messages.py web-ui/server/app/main.py web-ui/server/tests/test_message_actions.py` - PASS.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py web-ui/server/tests/test_chat_stream.py web-ui/server/tests/test_prompt_builder.py web-ui/server/tests/test_app.py -q` - PASS, 24 tests.
- `git diff --check -- web-ui/server/app/domain/message_actions.py web-ui/server/app/api/messages.py web-ui/server/app/main.py web-ui/server/tests/test_message_actions.py` - PASS.

## Next Phase Readiness

Backend message actions now return durable generated `ThreadMessageShape` payloads for the frontend action UI in Plan 22. Prompt context remains selected-branch safe, and server-side LLM endpoint settings are the only generation settings source.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-15-SUMMARY.md`.
- Key created and modified files exist on disk.
- Task commit `9be8558` exists in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remained untouched.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
