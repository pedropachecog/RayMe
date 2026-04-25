---
phase: 03-first-working-call-mvp
plan: "06"
subsystem: testing
tags: [pytest, prompt-context, calls, sliding-window]
requires:
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-02 RED call prompt context contracts for selected text and speech rows."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-05 build_call_prompt_context implementation in the Web UI server prompt builder."
provides:
  - "Verified call prompt context helper with selected non-stale text plus speech rows."
  - "Explicit test coverage for the 24 conversational turn cap plus optional system prompt."
affects: [03-first-working-call-mvp, web-ui-server, prompt-builder, call-memory]
tech-stack:
  added: []
  patterns:
    - "Call prompt context reuses selected-branch prompt filtering while applying a post-filter sliding window."
key-files:
  created:
    - .planning/phases/03-first-working-call-mvp/03-06-SUMMARY.md
  modified:
    - web-ui/server/tests/test_prompt_builder.py
key-decisions:
  - "Kept the runtime build_call_prompt_context implementation from Plan 03-05 because it already satisfied the Plan 03-06 helper contract."
  - "Made the call prompt total-message cap explicit in tests instead of changing production prompt-builder code."
patterns-established:
  - "Call memory tests assert event-row exclusion, selected alternate use, stale-row exclusion, chronological order, and a capped recent-turn window."
requirements-completed: [REQ-63, REQ-40, REQ-50]
duration: 2m 06s
completed: 2026-04-25
---

# Phase 03 Plan 06: Call Prompt Window Summary

**Call prompt memory verified with selected non-stale text and speech rows, event-row exclusion, and a 24-turn sliding window.**

## Performance

- **Duration:** 2m 06s
- **Started:** 2026-04-25T20:44:35Z
- **Completed:** 2026-04-25T20:46:41Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Verified that `build_call_prompt_context` is exported from `prompt_builder.py` and reuses the existing system/persona prompt and selected-branch behavior.
- Confirmed call context includes `user_text`, `ai_text`, `user_speech`, and `ai_speech` while excluding `call_start` and `call_end` event rows.
- Added an explicit test assertion that a 30-turn call fixture returns no more than 25 messages when the system prompt is present.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add call prompt windowing helper** - `ff9af8b` (test)

## Files Created/Modified

- `web-ui/server/tests/test_prompt_builder.py` - Tightened the call sliding-window test to assert the total cap of 24 conversational turns plus the system prompt.
- `web-ui/server/app/domain/prompt_builder.py` - Verified existing Plan 03-05 implementation; no code change was needed in this plan.
- `.planning/phases/03-first-working-call-mvp/03-06-SUMMARY.md` - New execution summary.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py -q` - 9 passed.

## Decisions Made

- Treated the Plan 03-05 `build_call_prompt_context` implementation as the production implementation for this plan because it already matched the 03-06 action and acceptance criteria.
- Refined test coverage rather than duplicating or rewriting the helper.

## Deviations from Plan

None requiring auto-fix. The implementation work requested by the plan was already present from Plan 03-05; this plan verified it and strengthened the acceptance test.

## Issues Encountered

None.

## Known Stubs

None. Stub scan found only normal empty list initializers and an empty-string test case, not product placeholders or unwired UI data.

## Threat Flags

None. No new runtime endpoint, auth path, file access pattern, schema change, or trust-boundary surface was introduced.

## Auth Gates

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Call prompt memory is ready for downstream call-turn generation work. The Web UI server can hydrate bounded recent text and speech context from the unified thread while keeping call boundary events visible in thread history but out of LLM conversational messages.

## Self-Check: PASSED

- Found expected file: `.planning/phases/03-first-working-call-mvp/03-06-SUMMARY.md`.
- Found task commit: `ff9af8b`.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
