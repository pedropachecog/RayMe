---
phase: 01-foundations-text-chat-end-to-end
plan: "12"
subsystem: api
tags: [fastapi, sqlalchemy, character-cards, portraits, pillow, blob-storage]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 03 backend contracts, Plan 04 card fixtures, Plan 08 storage schema, and Plan 09 blob storage"
provides:
  - "Safe SillyTavern v2/v3 JSON and PNG card import"
  - "SillyTavern v2 JSON export"
  - "Character CRUD/import/export API routes"
  - "Portrait validation and atomic blob-backed storage"
  - "Soft-delete character behavior that preserves threads and messages"
affects: [web-ui-server, character-gallery, character-editor, chat-history, portrait-assets]

tech-stack:
  added: []
  patterns:
    - "Permissive Pydantic source-card boundary with normalized dataclass storage shape"
    - "Character routes use dependency-overridable async SQLAlchemy sessions for tests"
    - "Active portrait is represented by character_assets.asset_kind without schema changes"

key-files:
  created:
    - web-ui/server/app/domain/card_models.py
    - web-ui/server/app/domain/portraits.py
    - web-ui/server/app/domain/character_service.py
    - web-ui/server/app/api/characters.py
  modified:
    - web-ui/server/app/domain/cards.py
    - web-ui/server/app/domain/card_export.py
    - web-ui/server/app/main.py
    - web-ui/server/tests/test_card_import.py
    - web-ui/server/tests/test_card_export.py
    - web-ui/server/tests/test_characters.py

key-decisions:
  - "Phase 1 export remains v2 JSON only; no v3 PNG export path was added."
  - "Imported lorebook/world-info is preserved as storage data and reported as present, not injected into prompt fields."
  - "Portrait uploads reject client paths and store blobs under server-generated asset IDs."
  - "Portrait replacement archives previous active assets by asset_kind instead of changing the Phase 1 schema."

patterns-established:
  - "Use `parse_character_card_bytes` for all JSON/PNG card uploads before persistence."
  - "Use `CharacterService` as the storage boundary for character CRUD, import/export, and portrait operations."
  - "Use `character_assets.asset_kind == \"portrait\"` as the current active portrait reference."

requirements-completed: [REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-16]

duration: 11min
completed: 2026-04-24
---

# Phase 01 Plan 12: Character Cards And Character API Summary

**Safe SillyTavern card import/export with FastAPI character CRUD, soft delete history preservation, and validated portrait blob storage.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-24T05:16:37Z
- **Completed:** 2026-04-24T05:27:34Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Implemented v2/v3 JSON and PNG card parsing with 10 MiB upload limits, 1 MiB PNG metadata limits, strict base64 decode, `ccv3` precedence, safe parse errors, raw JSON preservation, and lorebook/world-info preservation.
- Implemented v2 JSON export only, including normalized editor fields, alternate greetings, tags, and preserved lorebook data.
- Added `/api/characters` CRUD, import, read, update, soft delete, and `/export-v2` routes backed by async SQLAlchemy.
- Added PNG/JPEG/WebP portrait validation, rejected SVG/path-like filenames/unreadable/oversized images, and stored portrait blobs through `atomic_write_blob` using generated asset IDs.
- Expanded tests to cover fixture imports, malformed/oversized card data, CRUD field persistence, import warnings, history-preserving delete, and portrait replace/delete behavior.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement safe card parser and v2 exporter** - `4c0f838` (`feat`)
2. **Task 2: Implement character CRUD and portrait storage** - `b8d01ad` (`feat`)

**Plan metadata:** this summary is committed separately.

## Files Created/Modified

- `web-ui/server/app/domain/card_models.py` - Pydantic source-card boundary and normalized card dataclasses.
- `web-ui/server/app/domain/cards.py` - JSON/PNG parser, safe errors, lorebook handling, and delete wrapper delegation.
- `web-ui/server/app/domain/card_export.py` - v2 JSON export helper.
- `web-ui/server/app/domain/portraits.py` - Portrait filename, type, byte-size, and dimension validation.
- `web-ui/server/app/domain/character_service.py` - Character CRUD/import/export, soft delete, and portrait asset service.
- `web-ui/server/app/api/characters.py` - FastAPI character routes.
- `web-ui/server/app/main.py` - Includes the character router before static client mounting.
- `web-ui/server/tests/test_card_import.py` - Parser coverage for fixture formats, `ccv3` precedence, malformed base64, oversized metadata, upload limits, and lorebook preservation.
- `web-ui/server/tests/test_card_export.py` - v2 JSON export coverage.
- `web-ui/server/tests/test_characters.py` - API, history preservation, import warning, export, and portrait tests.

## Decisions Made

- Active portrait state is represented by exactly one `character_assets` row with `asset_kind == "portrait"`; replacements archive old rows as `portrait_history`.
- Character deletion is a soft delete that removes the character from gallery/list results while keeping related thread/message rows queryable.
- Router dependencies expose override points for test database sessions and portrait blob directories.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added FastAPI router wiring**
- **Found during:** Task 2 (Implement character CRUD and portrait storage)
- **Issue:** The task file list did not include `web-ui/server/app/main.py`, but the new `/api/characters` router would be unreachable without app registration.
- **Fix:** Included `characters_router` in `create_app()` before static client mounting.
- **Files modified:** `web-ui/server/app/main.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_characters.py -q`
- **Committed in:** `b8d01ad`

**2. [Rule 1 - Bug] Replaced stale delete contract stub**
- **Found during:** Task 1/2 integration
- **Issue:** `delete_character_preserving_thread_snapshots` still raised `NotImplementedError`, blocking the existing character delete contract.
- **Fix:** Delegated to the provided repository protocol while the concrete API path performs soft delete through `CharacterService`.
- **Files modified:** `web-ui/server/app/domain/cards.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_characters.py -q`
- **Committed in:** `4c0f838`

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug).
**Impact on plan:** Both fixes were required for the planned API and delete behavior to work; no schema or architecture change was introduced.

## Issues Encountered

- SQLAlchemy test setup needed to commit the thread row before inserting a message because the models do not define ORM relationships for flush ordering. The test fixture was adjusted; production behavior was unchanged.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Shared Orchestrator Artifacts

Per wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified by this plan.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_card_import.py web-ui/server/tests/test_card_export.py -q` - PASS, 17 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_characters.py -q` - PASS, 8 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_card_import.py web-ui/server/tests/test_card_export.py web-ui/server/tests/test_characters.py -q` - PASS, 25 tests.
- `uv run --project web-ui/server ruff check web-ui/server/app/domain/card_models.py web-ui/server/app/domain/cards.py web-ui/server/app/domain/card_export.py web-ui/server/app/domain/portraits.py web-ui/server/app/domain/character_service.py web-ui/server/app/api/characters.py web-ui/server/app/main.py web-ui/server/tests/test_card_import.py web-ui/server/tests/test_card_export.py web-ui/server/tests/test_characters.py` - PASS.
- `rg "ccv3|chara|validate=True|extra=\"allow\"|lorebook_json|export-v2|/api/characters|/portrait|deleted_at|Lorebook present - not used in v1|atomic_write_blob|4096|character_assets" web-ui/server/app web-ui/server/tests` - PASS.

## Next Phase Readiness

Character Gallery and Character Editor frontend work can now call real import/create/update/delete/export/portrait endpoints. Chat/thread work can rely on soft-deleted characters leaving historical threads and messages intact.

## Self-Check: PASSED

- Summary and key created files exist on disk.
- Task commits `4c0f838` and `b8d01ad` exist in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remained untouched.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
