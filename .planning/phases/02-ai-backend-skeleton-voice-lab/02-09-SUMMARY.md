---
phase: 02-ai-backend-skeleton-voice-lab
plan: "09"
subsystem: api
tags: [fastapi, sqlalchemy, voice-lab, ai-backend-client, pytest]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: Voice storage foundation from 02-04 and typed AI backend client from 02-05
provides:
  - Durable Web UI voice service for upload, transcription, preview, save, list, detail, rename, soft-delete, and test-play
  - Voice API routes under `/api/voices` wired before static serving
  - AI backend STT integration through `/stt/transcribe` using stored Web UI sample bytes
affects: [02-10, 02-11, 02-12, 02-13, 02-14, 02-15, 02-18]

tech-stack:
  added: []
  patterns: [durable Web UI voice ownership, AiBackendClient-backed transient processing, soft-delete tombstones]

key-files:
  created: []
  modified:
    - web-ui/server/app/domain/voice_service.py
    - web-ui/server/app/api/voices.py
    - web-ui/server/app/domain/ai_backend_client.py
    - web-ui/server/tests/test_voices.py
    - web-ui/server/tests/test_health_settings.py

key-decisions:
  - "Voice save persists caller metadata plus the sample asset link and remains independent from preview success."
  - "Voice rename changes only the mutable display name; default engine and transcript remain stable unless future explicit edit routes are added."
  - "Web UI voice transcription targets the implemented AI backend `/stt/transcribe` route, not the earlier placeholder `/transcribe` path."

patterns-established:
  - "Voice API processing dependencies adapt `AiBackendClient` into service methods while tests can override the processor."
  - "Referenced voice deletes require `force=true` and return readable referents before soft-delete."

requirements-completed: [REQ-20, REQ-21, REQ-22, REQ-23, REQ-24]

duration: 6 min
completed: 2026-04-25
---

# Phase 02 Plan 09: Web UI Voice Domain/API Summary

**Durable Voice Lab and Voice Library server APIs with stored sample processing through the AI backend client.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-25T00:23:44Z
- **Completed:** 2026-04-25T00:29:43Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Hardened `VoiceService` persistence so saved voices keep name, default engine, editable transcript, metadata, and sample asset linkage without any preview-success requirement.
- Added API and service coverage for saving after a `tts_failed` preview, rename-only semantics, readable delete referents, unsupported-upload sanitation, and stored sample bytes sent to backend processing.
- Replaced the default passthrough voice processor with an `AiBackendClient` adapter and aligned transcription with the implemented `/stt/transcribe` AI backend route.

## Task Commits

TDD tasks produced RED and GREEN commits:

1. **Task 1 RED: Add voice service hardening contracts** - `cb42993` (test)
2. **Task 1 GREEN: Harden voice service persistence** - `175695e` (feat)
3. **Task 2 RED: Add voice API backend route contract** - `f8b6560` (test)
4. **Task 2 GREEN: Target AI backend STT route from voice API** - `8d0621c` (fix)

## Files Created/Modified

- `web-ui/server/app/domain/voice_service.py` - Persists metadata with sample linkage, keeps preview optional, limits rename to display name, and returns synthesis result fields for test-play.
- `web-ui/server/app/api/voices.py` - Adds strict request models, metadata pass-through, and an `AiBackendClient`-backed processor dependency.
- `web-ui/server/app/domain/ai_backend_client.py` - Sends transcription requests to `/stt/transcribe`.
- `web-ui/server/tests/test_voices.py` - Adds voice service/API contracts for metadata, rename-only behavior, delete referents, sanitized upload errors, and backend route/payload alignment.
- `web-ui/server/tests/test_health_settings.py` - Updates the existing AI backend client contract to the implemented STT route.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q` - PASS, 13 tests after Task 1.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_app.py -q` - PASS, 16 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` - PASS, 14 tests.
- `uv run --project web-ui/server ruff check web-ui/server/app/api/voices.py web-ui/server/app/domain/voice_service.py web-ui/server/app/domain/ai_backend_client.py web-ui/server/tests/test_voices.py web-ui/server/tests/test_health_settings.py` - PASS.
- Acceptance `rg` checks for `VoiceService` methods, generated ID prefixes, `deleted_at`, route strings, force-delete terms, `soft_delete`, and router wiring passed.

## Decisions Made

- Kept durable voice state in the Web UI server and passed sample bytes to the AI backend only for transient STT/TTS processing.
- Treated preview failure as non-blocking state: users can still save the voice, including metadata that records a failed preview result.
- Preserved character references during force-delete by soft-deleting the voice and returning readable referents.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected Web UI STT client endpoint**
- **Found during:** Task 2 (Expose voice API routes)
- **Issue:** `AiBackendClient.transcribe_sample()` still targeted `/transcribe`, while plan 02-07 implemented the AI backend route at `/stt/transcribe`. The Voice API would send stored sample bytes to a non-existent endpoint.
- **Fix:** Updated the client endpoint and the existing AI backend client contract test to use `/stt/transcribe`.
- **Files modified:** `web-ui/server/app/domain/ai_backend_client.py`, `web-ui/server/tests/test_health_settings.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_app.py -q`; `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q`
- **Committed in:** `8d0621c`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix was required for actual Web UI-to-AI-backend transcription integration and did not add new product scope.

## Issues Encountered

None beyond the endpoint bug documented above.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. Stub-pattern scan hits were required nullable fields, test fixtures, `tts_failed` status handling, and required `Voice unavailable` tombstone copy rather than runtime placeholders.

## Threat Flags

None. The `/api/voices` browser boundary and Web UI-to-AI-backend processing boundary are the planned surfaces in this plan's threat model and include validation/sanitized-error coverage.

## Next Phase Readiness

Voice Lab server routes are ready for client Voice Lab wiring, character default voice hydration polish, Settings status integration, and live OMEN-PC verification in later Phase 2 plans.

## TDD Gate Compliance

- RED gate commits present: `cb42993`, `f8b6560`
- GREEN gate commits present after RED commits: `175695e`, `8d0621c`

## Self-Check: PASSED

- Verified key files exist: `voice_service.py`, `voices.py`, `ai_backend_client.py`, `test_voices.py`, `test_health_settings.py`, and this summary.
- Verified task commits exist: `cb42993`, `175695e`, `f8b6560`, `8d0621c`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
