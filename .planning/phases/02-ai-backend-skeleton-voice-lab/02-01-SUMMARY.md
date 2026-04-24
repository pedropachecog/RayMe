---
phase: 02-ai-backend-skeleton-voice-lab
plan: "01"
subsystem: testing
tags: [pytest, fastapi, sqlite, settings, voice-lab, contracts]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: FastAPI app factory, SQLite migration tests, Settings API tests, character CRUD contracts
provides:
  - Web UI server RED contracts for voice asset upload, transcription, preview, save, library, delete, and test-play APIs
  - Schema assertions for voices, voice_assets, and character default voice references
  - Settings assertions for audio save defaults, VAD controls, and compact AI backend status
affects: [02-04, 02-09, 02-10, 02-11, 02-13, 02-14]

tech-stack:
  added: []
  patterns: [Wave 0 RED contract tests, FastAPI TestClient route contracts, Alembic schema assertions]

key-files:
  created: [web-ui/server/tests/test_voices.py]
  modified:
    - web-ui/server/tests/test_migrations.py
    - web-ui/server/tests/test_health_settings.py

key-decisions:
  - "Voice APIs must use stable internal voice IDs while allowing mutable display names."
  - "Voice save must not require preview_id, preview_url, or successful synthesis output."
  - "Settings must default to saving AI audio, not saving mic audio, VAD threshold 0.5, and end silence 700 ms."

patterns-established:
  - "Voice API contracts assert route behavior before implementation and fail on missing routes with 404."
  - "Settings tests preserve save-before-test ordering before web, AI backend, and LLM probe routes."

requirements-completed: [REQ-05, REQ-15, REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-80]

duration: 9 min
completed: 2026-04-24
---

# Phase 02 Plan 01: Wave 0 Server Voice Contracts Summary

**RED pytest contracts for durable voice storage, voice API behavior, character default voice references, and Phase 2 Settings extensions.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-24T22:51:44Z
- **Completed:** 2026-04-24T23:00:14Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added `web-ui/server/tests/test_voices.py` covering voice asset upload, transcription, optional preview, save, list/detail, rename, force delete tombstones, character unavailable state, and test-play routes.
- Extended migration contracts to require `voices`, `voice_assets`, and `characters.default_voice_id`.
- Extended Settings contracts to require save-audio defaults, VAD settings, compact `ai_backend_status`, and preserved save-before-test route ordering.

## Task Commits

1. **Task 1: Add voice API and storage contract tests** - `6c6cfc8` (test)
2. **Task 2: Extend migration and Settings contracts** - `bac4291` (test)

## Files Created/Modified

- `web-ui/server/tests/test_voices.py` - New voice API and storage contract tests.
- `web-ui/server/tests/test_migrations.py` - Added voice table, voice asset, and character default voice schema assertions.
- `web-ui/server/tests/test_health_settings.py` - Added Settings audio/VAD/status contracts while keeping existing endpoint probe behavior.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q` - RED as expected: 7 failures, all from missing `/api/voices` routes returning 404.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_migrations.py web-ui/server/tests/test_health_settings.py -q` - RED as expected: 3 failures, 10 passes. Failures are missing voice tables and missing Settings extension fields.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_migrations.py web-ui/server/tests/test_health_settings.py -q` - RED as expected: 10 failures, 10 passes. Failures match the intentional Wave 0 implementation gaps.
- Acceptance `rg` checks passed for voice route strings, six-engine roster strings, optional preview save assertions, voice schema strings, Settings strings, and save-before-test route references.

## Decisions Made

- Followed Phase 2 decisions D-04 through D-19 exactly: Web UI server owns durable voice state, preview is optional, deletes produce unavailable/tombstone behavior, and Settings owns audio/VAD defaults.
- Kept this plan RED-only. No voice implementation was added because later Phase 2 plans are responsible for satisfying these contracts.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Expected RED verification failures only. No syntax, import, fixture, or collection errors remained after test cleanup.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. Stub-pattern scan only found an existing intentional empty `base_url=""` probe case in `test_health_settings.py`.

## Threat Flags

None. This plan adds security-relevant tests for future voice upload/delete and Settings behavior, but it does not introduce runtime endpoints or new trust-boundary implementation.

## Next Phase Readiness

Ready for later Phase 2 implementation plans to make the RED contracts pass, especially schema/storage work, voice API service work, character default voice hydration, and Settings status extensions.

## Self-Check: PASSED

- Verified created/modified files exist: `test_voices.py`, `test_migrations.py`, `test_health_settings.py`, and this summary.
- Verified task commits exist: `6c6cfc8`, `bac4291`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-24*
