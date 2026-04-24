---
phase: 01-foundations-text-chat-end-to-end
plan: "08"
subsystem: database
tags: [sqlite, sqlalchemy, alembic, migrations, chat-storage]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plans 01-07 scaffolded backend/client/AI-backend/LLM docs, contract tests, sanitizer tests, E2E shells, and card fixtures"
provides:
  - "Wave 0 validation completion marker after scaffold artifact verification"
  - "Async SQLAlchemy storage models and session helpers for sqlite+aiosqlite"
  - "Alembic initial migration for app settings, characters, character assets, threads, messages, and message alternates"
  - "Migration tests proving message kind and alternate source-action constraints plus branch metadata"
affects: [web-ui-server, chat-storage, character-crud, thread-management, message-actions]

tech-stack:
  added: []
  patterns:
    - "Declarative SQLAlchemy models mirror the first Alembic migration"
    - "Migration tests apply Alembic to a temporary SQLite database before asserting schema behavior"
    - "Thread rows store character snapshots while character rows use soft-delete timestamps"

key-files:
  created:
    - web-ui/server/app/storage/session.py
    - web-ui/server/alembic.ini
    - web-ui/server/alembic/env.py
    - web-ui/server/alembic/versions/0001_initial_schema.py
  modified:
    - .planning/phases/01-foundations-text-chat-end-to-end/01-VALIDATION.md
    - web-ui/server/app/storage/models.py
    - web-ui/server/tests/test_migrations.py

key-decisions:
  - "The first migration enforces the six required message_kind values and four alternate source_action values with SQLite check constraints."
  - "Messages keep selected_alternate_id, edit lineage, stale flags, branch root, sequence, and timestamps as durable branch metadata."
  - "Character deletes are represented by deleted_at while threads keep character snapshot fields for history preservation."
  - "SQLite keeps default journal behavior in this phase; only foreign key enforcement is configured in the session helper."

patterns-established:
  - "Use Alembic revision 0001_initial_schema as the schema source for Phase 1 storage."
  - "Use app.storage.session.create_engine/get_session for async sqlite+aiosqlite access."
  - "Preserve Plan 02 ThreadMessageShape dataclass contracts alongside ORM models until repository implementations replace contract fakes."

requirements-completed: [REQ-12, REQ-16, REQ-17, REQ-30, REQ-31, REQ-32, REQ-33, REQ-34, REQ-35, REQ-60, REQ-70, REQ-71]

duration: 10min
completed: 2026-04-24
---

# Phase 01 Plan 08: Initial Storage Schema Summary

**SQLite storage foundation with async SQLAlchemy models, Alembic initial schema, unified message constraints, branch metadata, and Wave 0 validation completion.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-24T04:45:49Z
- **Completed:** 2026-04-24T04:55:43Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Verified Wave 0 scaffold artifacts existed, then set `wave_0_complete: true` in the Phase 1 validation frontmatter without changing validation rows.
- Added SQLAlchemy declarative models for app settings, characters, character assets, threads, unified messages, and message alternates while preserving prior dataclass thread-message contracts.
- Added async SQLite session helpers using `sqlite+aiosqlite` and foreign key enforcement without changing SQLite journal mode.
- Added Alembic config, async migration environment, and revision `0001_initial_schema`.
- Replaced constant-only migration tests with Alembic-backed SQLite tests for table creation, allowed message kinds, rejected unknown kinds, supported alternate actions, selected alternates, stale flags, and branch roots.

## Task Commits

Each task was committed atomically:

1. **Task 1: Mark Wave 0 validation complete** - `fd06a2f` (`docs(01-08)`)
2. **Task 2: Implement schema models and migration** - `2282d3a` (`feat(01-08)`)

**Plan metadata:** committed separately with this summary.

## Files Created/Modified

- `.planning/phases/01-foundations-text-chat-end-to-end/01-VALIDATION.md` - Marks Wave 0 complete after scaffold artifact checks.
- `web-ui/server/app/storage/models.py` - Adds ORM models, table constants, check constraints, indexes, and branch metadata while keeping thread-message shape helpers.
- `web-ui/server/app/storage/session.py` - Adds async engine/session factory and SQLite foreign key pragma configuration.
- `web-ui/server/alembic.ini` - Configures the Web UI server Alembic script location and default SQLite URL.
- `web-ui/server/alembic/env.py` - Adds async Alembic migration runner with `Base.metadata`.
- `web-ui/server/alembic/versions/0001_initial_schema.py` - Creates the initial six-table schema and indexes.
- `web-ui/server/tests/test_migrations.py` - Applies Alembic to temp SQLite databases and proves schema constraints.

## Decisions Made

- Stored imported-card raw source and lorebook payloads as JSON columns on characters and thread snapshots so later CRUD/import work can preserve data without prompt injection.
- Kept `selected_alternate_id` as a nullable durable branch pointer on `messages`; alternate rows are constrained by `source_action` and ordered by `alternate_index`.
- Used soft delete timestamps on characters and threads rather than cascading away history.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_migrations.py -q` - PASS, 4 tests.
- `uv run --project web-ui/server ruff check web-ui/server/app/storage/models.py web-ui/server/app/storage/session.py web-ui/server/alembic/env.py web-ui/server/alembic/versions/0001_initial_schema.py web-ui/server/tests/test_migrations.py` - PASS.
- `rg "user_text|ai_text|user_speech|ai_speech|call_start|call_end|message_alternates|stale_after_edit|selected_alternate_id" web-ui/server/app/storage/models.py web-ui/server/alembic/versions/0001_initial_schema.py` - PASS.
- `rg "PRAGMA journal_mode=WAL|journal_mode.*WAL" web-ui/server` - PASS, no matches.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Alembic emitted a deprecation warning until `path_separator = os` was added to `web-ui/server/alembic.ini`; final migration tests run without that warning.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The storage schema is ready for character CRUD/import, thread APIs, prompt building, streaming final-message persistence, and message action repository implementations.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-08-SUMMARY.md`.
- Key storage and migration files exist on disk.
- Task commits `fd06a2f` and `2282d3a` exist in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
