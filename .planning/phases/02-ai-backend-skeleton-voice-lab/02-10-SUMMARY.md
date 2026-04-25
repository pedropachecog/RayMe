---
phase: 02-ai-backend-skeleton-voice-lab
plan: "10"
subsystem: api
tags: [fastapi, pydantic, settings, ai-backend, pytest]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: Typed AI backend client/status bridge from 02-05 and AI backend health residency payload from 02-06
provides:
  - Persisted Settings audio/VAD/STT/TTS defaults with JSON boolean and numeric types
  - Settings API VAD validation bounds for threshold and end silence
  - Compact AI backend residency status on `/api/settings`
affects: [02-14, 02-18]

tech-stack:
  added: []
  patterns: [Settings response-model extension, compact backend status mapping, deterministic dependency-overridden endpoint tests]

key-files:
  created: []
  modified:
    - web-ui/server/app/domain/settings_service.py
    - web-ui/server/app/api/settings.py
    - web-ui/server/tests/test_health_settings.py

key-decisions:
  - "Settings now persists `stt_model` and `tts_default_engine` alongside audio/VAD fields so later UI/call phases can read the same server-side defaults."
  - "Settings responses use the compact AI backend status shape with `available_engines`, `loading_engine`, and VRAM fields, matching the RayMe-owned status bridge."
  - "Unit tests override the AI backend client dependency for Settings reads so tests never make live LAN/backend probes."

patterns-established:
  - "Public Settings payloads are assembled from persisted settings plus a typed, sanitized AI backend status lookup."
  - "VAD user input is bounded in the Pydantic request model before reaching persistence."

requirements-completed: [REQ-02, REQ-05, REQ-80, REQ-A3]

duration: 6 min
completed: 2026-04-25
---

# Phase 02 Plan 10: Settings Audio/VAD and Backend Status Summary

**Server-side Settings persistence for Phase 2 audio/VAD defaults plus compact AI backend residency status.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-25T00:34:20Z
- **Completed:** 2026-04-25T00:40:46Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Extended persisted endpoint settings with `save_ai_audio`, `save_mic_audio`, `vad_threshold`, `vad_end_silence_ms`, `stt_model`, and `tts_default_engine`.
- Added tests proving defaults are available before any `app_settings` row exists and persisted JSON keeps booleans/numbers as typed JSON values.
- Extended Settings API models to include the new fields, enforce VAD bounds of `0.0..1.0` and `100..3000`, and return compact AI backend status fields.
- Preserved save-before-test behavior and raw LLM key masking in the existing Settings test suite.

## Task Commits

TDD tasks produced RED and GREEN commits:

1. **Task 1 RED: Add Settings persistence contracts** - `1600cdc` (test)
2. **Task 1 GREEN: Persist Phase 2 Settings defaults** - `e80f8b4` (feat)
3. **Task 2 RED: Add Settings status API contracts** - `de50569` (test)
4. **Task 2 GREEN: Expose compact AI backend Settings status** - `9e5c18a` (feat)

## Files Created/Modified

- `web-ui/server/app/domain/settings_service.py` - Adds persisted STT/default-TTS settings and updates the default compact AI backend status shape.
- `web-ui/server/app/api/settings.py` - Extends request/response models, validates VAD bounds, and maps live typed AI backend status into public Settings responses.
- `web-ui/server/tests/test_health_settings.py` - Adds persistence/default/type contracts, VAD validation tests, compact Settings status coverage, and deterministic AI backend dependency overrides.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` - PASS, 17 tests.
- `uv run --project web-ui/server ruff check web-ui/server/app/api/settings.py web-ui/server/app/domain/settings_service.py web-ui/server/tests/test_health_settings.py` - PASS.
- `rg "save_ai_audio|save_mic_audio|vad_threshold|vad_end_silence_ms|stt_model|tts_default_engine|distil-large-v3|f5" web-ui/server/app/domain/settings_service.py web-ui/server/tests/test_health_settings.py` - PASS.
- `rg "ai_backend_status|endpoint_status|resident_tts_engine|available_engines|vram_used_mb|vram_headroom_mb|ge=0|le=1|ge=100|le=3000" web-ui/server/app/api/settings.py web-ui/server/tests/test_health_settings.py` - PASS.

## Decisions Made

- Kept Settings as the server-side owner of Phase 2 call-adjacent defaults, while AI backend health remains the source of transient residency metadata.
- Used dependency overrides in tests for `/api/settings` status reads so unit tests verify mapping behavior without requiring a running AI backend.
- Preserved the existing `/api/settings/test/*` save-before-test semantics: probe routes read already-persisted settings and never trust browser-supplied test payloads.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added Settings response-model fields during Task 1**
- **Found during:** Task 1 (Extend persisted Settings fields)
- **Issue:** `EndpointSettings.to_public_dict()` returned `stt_model` and `tts_default_engine`, but FastAPI's `PublicSettings` response model filtered them out, preventing Task 1 verification from passing.
- **Fix:** Added the new fields to `SettingsPatch` and `PublicSettings` and stripped string values through the existing text validator.
- **Files modified:** `web-ui/server/app/api/settings.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` passed after the service implementation.
- **Committed in:** `e80f8b4`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Required for the persisted service fields to be visible through the public Settings API. No architecture change or scope expansion.

## Issues Encountered

- The existing Settings service carried the old status field names (`available_tts_engines`, `loading_state`, `vram_mb`). Task 2 updated the default and live API status shapes to the compact Phase 2 names.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. Stub-pattern scan only found intentional nullable/unavailable status fields and test fixtures.

## Threat Flags

None. The modified browser-facing Settings API and AI backend status mapping are the planned trust-boundary surfaces in this plan's threat model and include typed response shaping, VAD input bounds, and raw LLM key masking tests.

## Next Phase Readiness

Settings server state is ready for the Phase 2 Settings UI plan to render audio toggles, VAD controls, persisted STT/TTS defaults, and backend residency details without adding new server fields.

## TDD Gate Compliance

- RED gate commits present: `1600cdc`, `de50569`
- GREEN gate commits present after RED commits: `e80f8b4`, `9e5c18a`

## Self-Check: PASSED

- Verified key files exist: `settings_service.py`, `settings.py`, `test_health_settings.py`, and this summary.
- Verified task commits exist: `1600cdc`, `e80f8b4`, `de50569`, `9e5c18a`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
