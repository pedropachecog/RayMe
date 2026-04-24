---
phase: 01-foundations-text-chat-end-to-end
plan: "09"
subsystem: storage
tags: [filesystem, blobs, atomic-write, cleanup, pytest]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 01 scaffolded the FastAPI server storage package and test layout."
provides:
  - "Atomic filesystem blob write helper using same-directory temp files, fsync, and os.replace."
  - "Traversal-safe blob filename validation."
  - "Blob orphan reaper constrained to the configured blob directory."
  - "Storage safety tests for traversal rejection, temp cleanup, replace ordering, and scoped cleanup."
affects: [character-portraits, character-import, voice-audio-blobs, storage]

tech-stack:
  added: []
  patterns:
    - "Filesystem blobs are written to same-directory temporary files before atomic rename."
    - "Blob cleanup enumerates configured storage directories rather than deleting caller-supplied paths."

key-files:
  created:
    - web-ui/server/app/storage/blob_store.py
    - web-ui/server/app/storage/reaper.py
    - web-ui/server/tests/test_blob_store.py
  modified: []

key-decisions:
  - "Blob names are flat filenames only; absolute paths, separators, empty names, and traversal segments are rejected before writes."
  - "The orphan reaper only scans immediate files in the configured blob directory and ignores references resolving outside that directory."

patterns-established:
  - "atomic_write_blob(blob_dir, final_name, data) validates a flat final filename, writes bytes to a .tmp file in blob_dir, fsyncs, and os.replace()s into place."
  - "reap_orphan_blobs(blob_dir, referenced_paths) deletes stale .tmp files and unreferenced direct children without traversing outside blob_dir."

requirements-completed: [REQ-12, REQ-13]

duration: "~8min"
completed: 2026-04-24
---

# Phase 01 Plan 09: Filesystem Blob Storage Summary

**Atomic filesystem blob storage with traversal-safe writes and scoped orphan cleanup for character portraits and future audio blobs**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-24T04:53:00Z
- **Completed:** 2026-04-24T05:01:17Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added `atomic_write_blob`, which writes through a same-directory `.tmp` file, flushes and fsyncs bytes, then atomically renames with `os.replace`.
- Added flat filename validation that rejects absolute paths, path separators, traversal strings such as `../evil.png`, empty names, and null bytes.
- Added `reap_orphan_blobs`, which deletes stale `.tmp` files and unreferenced blob files only by enumerating direct children of the configured blob directory.
- Added focused storage safety tests covering traversal rejection, pre-replace temp behavior, temp cleanup on replace failure, and cleanup confinement.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement atomic blob writes and orphan reaping** - `f0d0434` (feat)

**Plan metadata:** recorded by the final docs commit for this summary.

## Files Created/Modified

- `web-ui/server/app/storage/blob_store.py` - Atomic blob write helper and final filename validation.
- `web-ui/server/app/storage/reaper.py` - Orphan cleanup helper constrained to the configured blob directory.
- `web-ui/server/tests/test_blob_store.py` - Storage safety tests for the blob writer and reaper.

## Decisions Made

- Final blob names are flat filenames only. This keeps traversal prevention local to the blob storage boundary and avoids accepting nested client-supplied paths.
- The reaper never deletes caller-supplied paths directly. It normalizes references only for comparison, then deletes direct children found by enumerating `blob_dir`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_blob_store.py -q` - PASS (`4 passed in 0.13s`)
- `rg "os\\.replace|os\\.fsync|\\.tmp|\\.\\./evil\\.png" web-ui/server/app/storage web-ui/server/tests/test_blob_store.py` - PASS
- Acceptance checks:
  - `atomic_write_blob` uses both `os.fsync` and `os.replace`.
  - Tests include `../evil.png`.
  - Tests prove traversal input is rejected.
  - Tests prove orphan cleanup cannot delete outside `blob_dir`.

## Known Stubs

None.

## Threat Flags

None - the new filesystem write and cleanup surface is the planned `upload bytes -> filesystem` boundary and implements the plan's traversal and orphan cleanup mitigations.

## User Setup Required

None - no external service configuration required.

## Shared Orchestrator Artifacts

Per wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified by this plan.

## Next Phase Readiness

Character portrait upload/import work can now depend on `atomic_write_blob` for durable file placement and `reap_orphan_blobs` for cleanup after metadata mismatches or failed workflows.

## Self-Check: PASSED

- Created files exist on disk: `blob_store.py`, `reaper.py`, `test_blob_store.py`, and this summary.
- Task commit exists in git history: `f0d0434`.
- No tracked file deletions were introduced by the task commit.
- Shared orchestrator artifacts remained untouched by this executor.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
