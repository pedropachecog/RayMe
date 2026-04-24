---
phase: 02-ai-backend-skeleton-voice-lab
plan: "04"
subsystem: database
tags: [sqlalchemy, alembic, sqlite, fastapi, voice-lab, blob-storage]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: Wave 0 Web UI server voice/schema contracts from plan 02-01
provides:
  - Migration-backed `voices` and `voice_assets` tables with character default voice references
  - Voice sample upload validation for WAV, MP3, and FLAC with atomic blob writes
  - Minimal Voice API/service wiring needed by the existing voice contract suite
affects: [02-09, 02-11, 02-13, 02-15]

tech-stack:
  added: []
  patterns: [Alembic additive voice schema, asset-id-derived blob names, soft-delete voice tombstones]

key-files:
  created:
    - web-ui/server/alembic/versions/0002_voice_storage.py
    - web-ui/server/app/domain/voice_assets.py
    - web-ui/server/app/domain/voice_service.py
    - web-ui/server/app/api/voices.py
  modified:
    - web-ui/server/app/storage/models.py
    - web-ui/server/app/domain/character_service.py
    - web-ui/server/app/api/characters.py
    - web-ui/server/app/main.py
    - web-ui/server/tests/test_migrations.py
    - web-ui/server/tests/test_voices.py

key-decisions:
  - "Voice sample blob paths are generated from server-side asset IDs and never from uploaded filenames."
  - "Voice assets allow nullable `voice_id` so uploaded samples can exist before the user saves a voice."
  - "Minimal Voice API/service wiring was pulled forward because the plan-level verification included the existing voice API contract file."

patterns-established:
  - "Voice uploads validate filename, extension, content type, size, and optional WAV metadata before using `atomic_write_blob`."
  - "Deleted voices keep stable IDs and render recoverable `Voice unavailable` character default state."

requirements-completed: [REQ-15, REQ-20, REQ-22, REQ-24]

duration: 11 min
completed: 2026-04-24
---

# Phase 02 Plan 04: Voice Storage Foundation Summary

**Migration-backed voice records and asset-id-based audio sample storage with safe upload validation.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-24T23:28:30Z
- **Completed:** 2026-04-24T23:39:38Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Added `Voice` and `VoiceAsset` ORM models, `voices` and `voice_assets` table constants, and nullable `characters.default_voice_id`.
- Added Alembic revision `0002_voice_storage.py` with the required voice tables, foreign keys, and indexes.
- Added `voice_assets.py` validation for WAV/MP3/FLAC uploads, 25 MiB cap, path-like filename rejection, duration warnings, and atomic sample blob writes.
- Pulled forward minimal Voice API/service and character default voice hydration so the existing `test_voices.py` contracts pass.

## Task Commits

TDD tasks produced RED and GREEN commits:

1. **Task 1 RED: Add voice schema migration contract** - `de90faf` (test)
2. **Task 1 GREEN: Add voice storage schema** - `dcaad5f` (feat)
3. **Task 2 RED: Add voice sample validation contract** - `33f28e8` (test)
4. **Task 2 GREEN: Add voice sample storage foundation** - `f615084` (feat)

## Files Created/Modified

- `web-ui/server/alembic/versions/0002_voice_storage.py` - Adds voice storage tables, indexes, and character default voice FK.
- `web-ui/server/app/storage/models.py` - Adds `Voice`, `VoiceAsset`, voice table constants, and `Character.default_voice_id`.
- `web-ui/server/app/domain/voice_assets.py` - Validates and stores original voice sample blobs safely.
- `web-ui/server/tests/test_migrations.py` - Adds index/FK schema assertions.
- `web-ui/server/tests/test_voices.py` - Adds helper-level upload validation and blob-name tests.
- `web-ui/server/app/domain/voice_service.py` - Minimal durable voice service for upload/save/list/rename/delete/test-play contracts.
- `web-ui/server/app/api/voices.py` - Minimal FastAPI routes for Voice Lab/Library contracts.
- `web-ui/server/app/domain/character_service.py` and `web-ui/server/app/api/characters.py` - Adds default voice persistence and `Voice unavailable` response hydration.
- `web-ui/server/app/main.py` - Includes the voice router.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_migrations.py -q` - PASS, 5 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_blob_store.py -q` - PASS, 14 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_migrations.py web-ui/server/tests/test_voices.py web-ui/server/tests/test_blob_store.py -q` - PASS, 19 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_app.py -q` - PASS, 2 tests.
- `uv run --project web-ui/server ruff check ...` on modified server files - PASS.
- Acceptance `rg` checks passed for the schema strings and voice sample helper strings.

## Decisions Made

- Kept uploaded sample storage paths as flat `{asset_id}.{extension}` names.
- Allowed `voice_assets.voice_id` to be nullable because Voice Lab uploads a sample before saving a voice record.
- Used soft-delete via `voices.deleted_at` so character references retain stable IDs and can render an unavailable state.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pulled forward minimal Voice API/service wiring**
- **Found during:** Task 2 (Add voice sample asset validation helper)
- **Issue:** The plan's verification command ran the full existing `test_voices.py` suite, which included Voice API contracts from plan 02-01 and failed with `/api/voices` 404s after the helper itself passed.
- **Fix:** Added minimal `VoiceService`, `/api/voices` routes, router registration, and character default voice hydration needed to satisfy the committed contracts.
- **Files modified:** `web-ui/server/app/domain/voice_service.py`, `web-ui/server/app/api/voices.py`, `web-ui/server/app/main.py`, `web-ui/server/app/domain/character_service.py`, `web-ui/server/app/api/characters.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_blob_store.py -q` passed.
- **Committed in:** `f615084`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** The deviation satisfied the plan's own verification command and aligns with planned 02-09 behavior, but it brings forward part of that later API/service scope.

## Issues Encountered

- The original Task 2 helper implementation passed its focused tests, but the full required command failed on pre-existing RED route contracts. The route/service pull-forward resolved that blocker.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. `Voice unavailable` strings are required tombstone-state copy, not placeholder text.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: network_endpoint | `web-ui/server/app/api/voices.py` | Minimal `/api/voices` upload, preview, save, delete, and test-play routes were pulled forward from later plan scope. |
| threat_flag: file_access | `web-ui/server/app/domain/voice_service.py` | Voice service reads stored sample blobs for transient processing calls. |

## Next Phase Readiness

The voice schema, sample validation, and committed Voice API contracts now pass. Plan 02-09 should treat the pulled-forward service/routes as its starting point and harden/extend them rather than reintroducing duplicate implementations.

## Self-Check: PASSED

- Verified key created files exist: `0002_voice_storage.py`, `voice_assets.py`, `voice_service.py`, `voices.py`, and this summary.
- Verified task commits exist: `de90faf`, `dcaad5f`, `33f28e8`, `f615084`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-24*
