---
phase: 01-foundations-text-chat-end-to-end
plan: "14"
subsystem: api
tags: [fastapi, sse, openai, prompts, chat]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 11 persisted server-side LLM endpoint settings"
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 13 thread hydration with selected alternates and stale flags"
provides:
  - "Selected-branch prompt builder for send, regenerate, swipe, and continue"
  - "OpenAI-compatible streaming and collect helpers using server-side settings"
  - "POST /api/chat/{thread_id}/send SSE endpoint with token/done/error events"
  - "Contract tests for prompt safety, streaming persistence, and override rejection"
affects: [web-ui-server, text-chat, message-actions, settings]

tech-stack:
  added: []
  patterns:
    - "Reuse ThreadService hydration for prompt context and done-message shape parity"
    - "SSE events are JSON `data:` lines with token, done, or error payloads"
    - "Persist user text before streaming; persist AI text only after upstream completion"

key-files:
  created:
    - web-ui/server/app/api/chat.py
  modified:
    - web-ui/server/app/domain/prompt_builder.py
    - web-ui/server/app/domain/llm_stream.py
    - web-ui/server/app/main.py
    - web-ui/server/tests/test_prompt_builder.py
    - web-ui/server/tests/test_chat_stream.py

key-decisions:
  - "Prompt context uses ThreadService hydration so selected alternates and stale flags match thread detail responses."
  - "Chat send accepts only `content`; browser-supplied base URL, API key, and model fields are rejected."
  - "Upstream stream failures emit a generic SSE error event and do not persist partial assistant text."

patterns-established:
  - "Server-side ChatCompletionSettings is the only source for LLM base URL, API key, and model."
  - "Done events reuse ThreadMessageShape serialization, preserving `selected_alternate_id`, ordered `alternates`, and `stale_after_edit`."

requirements-completed: [REQ-03, REQ-16, REQ-30, REQ-34, REQ-35, REQ-60]

duration: 10min
completed: 2026-04-24
---

# Phase 01 Plan 14: Prompt Builder and Streaming Chat Summary

**Selected-branch prompt construction plus server-side OpenAI-compatible SSE chat send with atomic final-message persistence.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-24T05:51:25Z
- **Completed:** 2026-04-24T06:00:54Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Implemented `build_prompt_context()` with character persona fields, selected alternate resolution, stale-row exclusion, `until_message_id`, and continue composer-prefix support.
- Implemented `stream_chat_completion()` and `collect_chat_completion()` over `AsyncOpenAI`, with deterministic fake-client seams for tests.
- Added `POST /api/chat/{thread_id}/send` as an SSE endpoint that stores the user turn first, streams token events, commits final AI text once, and emits a full `ThreadMessageShape` done event.
- Added tests proving lorebook/world-info exclusion, unselected alternate exclusion, continue composer context, stale exclusion, token-before-done ordering, exactly-once AI persistence, full done shape, upstream error behavior, and browser override rejection.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement selected-branch prompt builder** - `d276f83` (`feat`)
2. **Task 2: Implement SSE chat stream and LLM helpers** - `bf74e6e` (`feat`)

**Plan metadata:** this summary is committed separately.

## Files Created/Modified

- `web-ui/server/app/domain/prompt_builder.py` - Selected-branch prompt builder and SQLAlchemy prompt repository.
- `web-ui/server/app/domain/llm_stream.py` - OpenAI-compatible token streaming, collection helper, and SSE event encoding.
- `web-ui/server/app/api/chat.py` - Chat send route, request validation, durable message writes, and stream response.
- `web-ui/server/app/main.py` - Registers the chat router in the FastAPI app factory.
- `web-ui/server/tests/test_prompt_builder.py` - Prompt safety and branch-selection contract tests.
- `web-ui/server/tests/test_chat_stream.py` - LLM helper and end-to-end chat stream route contract tests.

## Decisions Made

- Used `ThreadService.get_thread_detail()` as the canonical hydration source for prompt context and done-event parity.
- Rejected unknown chat-send body fields instead of ignoring them, so browser requests cannot smuggle LLM endpoint/model/key overrides.
- Emitted a generic `{"type":"error","message":"LLM stream failed"}` event on upstream failure to avoid leaking provider errors or secrets.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Registered chat router in the app factory**
- **Found during:** Task 2 (Implement SSE chat stream and LLM helpers)
- **Issue:** The plan's target files did not include `web-ui/server/app/main.py`, but `/api/chat/{thread_id}/send` would be unreachable without router registration.
- **Fix:** Imported and included `chat_router` in `create_app()` before static client mounting.
- **Files modified:** `web-ui/server/app/main.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_app.py -q`
- **Committed in:** `bf74e6e`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** Required to expose the planned API route. No schema or architecture change was introduced.

## Issues Encountered

None - implementation and verification completed without unresolved issues.

## Known Stubs

None. Stub scan found only intentional optional `None` defaults, local empty accumulators, and empty-list assertions in tests.

## User Setup Required

None - no external service configuration is required for tests. Runtime chat uses persisted Settings LLM values.

## Shared Orchestrator Artifacts

Per sequential wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py -q` - PASS, 6 tests.
- `rg "lorebook_json|selected_alternate_id|composer_text|until_message_id" web-ui/server/app/domain/prompt_builder.py web-ui/server/tests/test_prompt_builder.py` - PASS.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_chat_stream.py -q` - PASS, 6 tests.
- `rg "text/event-stream|AsyncOpenAI|collect_chat_completion|data: |selected_alternate_id|stale_after_edit" web-ui/server/app web-ui/server/tests/test_chat_stream.py` - PASS.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py web-ui/server/tests/test_chat_stream.py -q` - PASS, 12 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_app.py -q` - PASS, 2 tests.
- `uv run --project web-ui/server ruff check web-ui/server/app/domain/prompt_builder.py web-ui/server/app/domain/llm_stream.py web-ui/server/app/api/chat.py web-ui/server/app/main.py web-ui/server/tests/test_prompt_builder.py web-ui/server/tests/test_chat_stream.py` - PASS.

## Next Phase Readiness

The normal text send path now has a safe prompt context, server-side LLM settings boundary, SSE token stream, persisted user turns, clean final AI persistence, and done-message shape parity with thread hydration. Message-action plans can reuse the same prompt builder and collect helper.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-14-SUMMARY.md`.
- Key created and modified files exist on disk.
- Task commits `d276f83` and `bf74e6e` exist in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remained untouched.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
