---
phase: 01-foundations-text-chat-end-to-end
plan: "02"
subsystem: backend-contracts
tags: [pytest, fastapi, chat, llm-streaming, branching]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 01 backend FastAPI/pytest harness"
provides:
  - "ThreadMessageShape and message alternate contract types"
  - "Prompt builder, LLM stream, and message-action interface modules"
  - "Collectable backend contract tests for unified messages, stream done shape, prompt selection, and LLM-backed actions"
affects: [web-ui-server, chat-storage, prompt-builder, message-actions, client-chat-contracts]

tech-stack:
  added: []
  patterns:
    - "Contract-first backend tests collect before durable storage and route implementation"
    - "Server-side LLM helper calls are monkeypatchable through message action module imports"

key-files:
  created:
    - web-ui/server/app/domain/llm_stream.py
    - web-ui/server/app/domain/message_actions.py
    - web-ui/server/app/domain/prompt_builder.py
    - web-ui/server/app/storage/models.py
    - web-ui/server/tests/test_migrations.py
    - web-ui/server/tests/test_chat_stream.py
    - web-ui/server/tests/test_message_actions.py
    - web-ui/server/tests/test_prompt_builder.py
    - web-ui/server/tests/test_threads.py
  modified: []

key-decisions:
  - "The backend chat contract uses a full ThreadMessageShape for thread hydration and SSE done events."
  - "Regenerate, generated swipes, and continue are contracted to call server-side prompt context plus collect_chat_completion."
  - "Lorebook/world-info payloads are preserved in storage contracts but excluded from Phase 1 prompt context."

patterns-established:
  - "SSE chat events use JSON lines shaped as data: {\"type\":\"token\",\"text\":\"...\"} and data: {\"type\":\"done\",\"message\":{...}}."
  - "Selected alternates, stale flags, and ordered alternates are part of every hydrated thread message."
  - "Message action contract tests monkeypatch build_prompt_context and collect_chat_completion at the action module boundary."

requirements-completed: [REQ-03, REQ-17, REQ-30, REQ-31, REQ-32, REQ-33, REQ-34, REQ-35, REQ-60, REQ-70, REQ-71, REQ-72]

duration: 7min
completed: 2026-04-24
---

# Phase 01 Plan 02: Backend Chat Contract Summary

**Collectable backend contracts for unified chat messages, selected alternates, stream done-message shape, and LLM-backed regenerate/swipe/continue actions.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-24T03:41:30Z
- **Completed:** 2026-04-24T03:48:29Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Added storage contract constants and `ThreadMessageShape` / `MessageAlternateShape` for thread hydration, SSE done events, selected alternates, and stale flags.
- Added importable `build_prompt_context`, `stream_chat_completion`, `collect_chat_completion`, and message action interface functions.
- Added non-skipped backend contract tests for unified message kinds, selected alternates, prompt filtering, stream token/done shape, regenerate, swipes, edit stale handling, truncate, keep, and continue.
- Locked checker-required behavior that regenerate, swipe generation, and continue must use server-side settings plus `build_prompt_context` and `collect_chat_completion`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write schema, thread, prompt, and stream contracts** - `c495b45` (`feat(01-02)`)
2. **Task 2: Write LLM-backed message-action contracts** - `b08caf5` (`feat(01-02)`)

**Plan metadata:** recorded in the final `docs(01-02)` summary commit.

## Files Created/Modified

- `web-ui/server/app/storage/models.py` - Table-name constants, message-kind/source-action constants, and thread message/alternate contract shapes.
- `web-ui/server/app/domain/prompt_builder.py` - Importable selected-branch prompt builder interface.
- `web-ui/server/app/domain/llm_stream.py` - Importable OpenAI-compatible stream/collect interfaces and SSE event shape helpers.
- `web-ui/server/app/domain/message_actions.py` - Importable regenerate, swipe, edit, truncate, keep, and continue action interfaces.
- `web-ui/server/tests/test_migrations.py` - Unified message schema contract tests.
- `web-ui/server/tests/test_threads.py` - Thread creation and hydration shape contract tests.
- `web-ui/server/tests/test_prompt_builder.py` - Lorebook exclusion and selected-branch prompt context contract tests.
- `web-ui/server/tests/test_chat_stream.py` - Token event, final persistence, and full done-message shape contract tests.
- `web-ui/server/tests/test_message_actions.py` - LLM-backed message action contract tests with prompt/LLM monkeypatch assertions.
- `.planning/phases/01-foundations-text-chat-end-to-end/01-02-SUMMARY.md` - Execution summary.

## Decisions Made

- Kept implementation functions as importable async interfaces that raise `NotImplementedError`, matching the plan's contract-first scope.
- Exposed `build_prompt_context` and `collect_chat_completion` through `message_actions.py` so action tests can monkeypatch the exact server-side generation boundary.
- Represented thread messages as dataclass-backed typed dictionaries until the later SQLAlchemy/Alembic storage plan creates real tables.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests --collect-only -q` - PASS, 16 tests collected.
- `rg "test_done_event_contains_full_thread_message_shape|build_prompt_context|collect_chat_completion|ThreadMessageShape" web-ui/server/app web-ui/server/tests` - PASS.
- `rg "test_regenerate_calls_llm|test_swipe_calls_llm|test_continue_calls_llm|source_action.*swipe|source_action.*continue" web-ui/server/tests/test_message_actions.py web-ui/server/app/domain/message_actions.py` - PASS.
- `rg -n "pytest\.mark\.(skip|xfail)|skip\(|xfail\(|\btodo\b" web-ui/server/tests` - PASS, no matches.
- `uv run --project web-ui/server ruff check web-ui/server/app web-ui/server/tests` - PASS.

Full test execution was not run because this plan intentionally creates contract tests and importable stubs; the required verification gate is collect-only.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Ruff flagged `build_prompt_context` and `collect_chat_completion` imports in `message_actions.py` as unused. The imports are required monkeypatch contract hooks, so they were added to `__all__` and the lint gate passed.

## Known Stubs

- `web-ui/server/app/domain/llm_stream.py:72` - `stream_chat_completion` raises `NotImplementedError`; Plan 14 implements the real OpenAI-compatible streaming path.
- `web-ui/server/app/domain/llm_stream.py:83` - `collect_chat_completion` raises `NotImplementedError`; Plan 14 implements the real completion helper.
- `web-ui/server/app/domain/prompt_builder.py:31` - `build_prompt_context` raises `NotImplementedError`; Plan 14 implements selected-branch prompt construction.
- `web-ui/server/app/domain/message_actions.py:54` - `regenerate_ai_turn` raises `NotImplementedError`; Plan 15 implements durable LLM-backed actions.
- `web-ui/server/app/domain/message_actions.py:65` - `create_swipe_alternate` raises `NotImplementedError`; Plan 15 implements durable LLM-backed actions.
- `web-ui/server/app/domain/message_actions.py:76` - `edit_message_and_mark_stale` raises `NotImplementedError`; Plan 15 implements durable edit/stale behavior.
- `web-ui/server/app/domain/message_actions.py:86` - `truncate_stale_after_message` raises `NotImplementedError`; Plan 15 implements durable stale truncation.
- `web-ui/server/app/domain/message_actions.py:96` - `keep_stale_after_message` raises `NotImplementedError`; Plan 15 implements durable keep-stale choice recording.
- `web-ui/server/app/domain/message_actions.py:108` - `continue_ai_turn` raises `NotImplementedError`; Plan 15 implements durable LLM-backed continue.

These stubs are intentional contract boundaries and do not block this plan's goal.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Backend contract tests now define the behavior later storage, prompt builder, stream proxy, message action, API, and client chat plans must satisfy. The orchestrator should handle shared state and roadmap updates after the wave.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-02-SUMMARY.md`.
- Key created backend contract files exist on disk.
- Task commits `c495b45` and `b08caf5` exist in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
