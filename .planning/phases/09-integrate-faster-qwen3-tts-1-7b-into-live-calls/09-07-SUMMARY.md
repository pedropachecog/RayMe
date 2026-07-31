---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 07
subsystem: web-api
tags: [qwen3-tts, voice-cloning, authorization, provenance, webrtc, readiness]

requires:
  - phase: 09-04
    provides: Pinned Qwen3-TTS 1.7B runtime, hash-bound reference authorization contract, and hardware-proven WebRTC streaming
provides:
  - Exact idempotent qwen3_0_6b to qwen3_1_7b durable identity migration
  - Hash-bound saved Qwen voice provenance and authorization gates across preview, save, and test-play
  - Contained authorized Qwen call preparation with opaque prompt keys and separate model/prompt readiness
affects: [09-08, voice-lab, voice-library, live-calls, call-acceptance]

actuals:
  tokens: 22502
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns: [exact-identity-migration, hash-bound-authorization, content-derived-opaque-voice-key, one-shot-prepare-readiness-poll]

key-files:
  created:
    - web-ui/server/alembic/versions/0003_qwen3_engine_identity.py
  modified:
    - web-ui/server/app/domain/voice_service.py
    - web-ui/server/app/domain/call_service.py
    - web-ui/server/app/domain/ai_backend_client.py
    - web-ui/server/app/api/voices.py
    - web-ui/server/app/api/calls.py
    - web-ui/server/app/domain/settings_service.py
    - web-ui/server/tests/test_migrations.py
    - web-ui/server/tests/test_voices.py
    - web-ui/server/tests/test_calls.py

key-decisions:
  - "Only the exact persisted qwen3_0_6b identifier is translated; unknown values and unrelated settings remain untouched, and migrated voices require fresh authorization confirmation."
  - "Qwen authorization lives in existing voice metadata and binds the named steward, authorization basis, LAN-only scope, saved reference SHA-256, and exact transcript SHA-256 without fabricating consent."
  - "Live call sessions use a content-derived opaque Qwen voice key internally while RayMe's public call record retains the durable saved voice id."
  - "Call preparation is invoked once, then only shared model/prompt readiness is polled; failures expose allowlisted codes and fixed copy."

patterns-established:
  - "Saved Qwen boundary pattern: resolve the active sample beneath RayMe blob storage, read exact bytes, validate asset and authorization hashes, then derive an opaque content identity."
  - "Call preparation pattern: locally authorize before backend readiness, create the backend session with the opaque key, prepare once, and poll readiness without duplicating model or prompt work."

requirements-completed: [REQ-22, REQ-45]

coverage:
  - id: D1
    description: "Exact legacy Qwen engine identities migrate idempotently to qwen3_1_7b while preserving unknown values, unrelated settings, and truthful pending authorization."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "web-ui/server/tests/test_migrations.py and test_voices.py (42 passed); Alembic upgrade head"
        status: pass
    human_judgment: false
  - id: D2
    description: "Qwen save, preview, test-play, and status operations require contained reference bytes, exact transcript text, explicit provenance, matching hashes, and safe backend errors."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "web-ui/server/tests/test_voices.py (36 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Qwen call start and offer preparation carry the authorized saved reference into one opaque prompt preparation, expose separate readiness, fail safely, and remain retryable."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "web-ui/server/tests/test_calls.py (53 passed)"
        status: pass
      - kind: integration
        ref: "web-ui/server/tests (203 passed)"
        status: pass
      - kind: integration
        ref: "ai-backend/tests/test_call_session.py slow Qwen/VoxCPM2 streaming regressions (2 passed)"
        status: pass
    human_judgment: false

duration: 26min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 07: Durable Qwen Voice Authorization Summary

**RayMe now preserves the selected Qwen3-TTS 1.7B identity durably and admits saved-voice operations and live calls only through contained, hash-bound, explicitly authorized references with truthful readiness.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-07-31T18:12:01Z
- **Completed:** 2026-07-31T18:37:49Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Added an exact, repeat-safe database migration and compatibility reads for `qwen3_0_6b` to `qwen3_1_7b` without broad aliases, unrelated setting changes, or invented permission.
- Bound every new saved Qwen voice to an explicit reference steward, authorization basis, LAN call-testing scope, exact saved-audio hash, and exact transcript hash; migrated rows remain `needs_confirmation`.
- Reused the same containment and authorization validator for preview, test-play, call start, call offer preparation, and live turn reference forwarding.
- Separated model residency from opaque prompt readiness, prepared a call prompt only once, polled shared state for pending work, and reduced all public failures to allowlisted codes and fixed copy.
- Preserved the live-call invariant: Qwen and VoxCPM2 slow-stream regressions still begin playback before stream completion and reject whole-synthesis fallback.

## Task Commits

Each TDD task was committed atomically as RED then GREEN:

1. **Task 1 RED: Define identity and provenance contracts** - `9f041e8` (test)
2. **Task 1 GREEN: Persist truthful Qwen identity and provenance** - `27288a5` (feat)
3. **Task 2 RED: Define authorized saved-voice operation gates** - `2f91842` (test)
4. **Task 2 GREEN: Gate Qwen operations on authorized references** - `74377a3` (feat)
5. **Task 3 RED: Define authorized call preparation contracts** - `30c14f3` (test)
6. **Task 3 GREEN: Authorize and prepare Qwen calls** - `bec82dd` (feat)

## Files Created/Modified

- `web-ui/server/alembic/versions/0003_qwen3_engine_identity.py` - Exact engine/settings translation and pending-authorization migration.
- `web-ui/server/app/domain/settings_service.py` - Narrow compatibility normalization for endpoint settings.
- `web-ui/server/app/domain/voice_service.py` - Canonical identity, provenance construction, containment, hash validation, and opaque Qwen key derivation.
- `web-ui/server/app/api/voices.py` - Typed authorization inputs and separate preparation-status API.
- `web-ui/server/app/domain/ai_backend_client.py` - Safe processing-error parsing, readiness normalization, and call preparation client.
- `web-ui/server/app/domain/call_service.py` - Pre-backend saved-voice authorization and exact call reference preparation.
- `web-ui/server/app/api/calls.py` - Production offer/preparation wiring, shared readiness polling, and safe retry behavior.
- `web-ui/server/tests/test_migrations.py` - Exact, malformed, zero-row, repeated-run, and unknown-value migration coverage.
- `web-ui/server/tests/test_voices.py` - Provenance, tamper, containment, readiness, and error-leak regressions.
- `web-ui/server/tests/test_calls.py` - Qwen preflight, exact-reference forwarding, one-shot preparation, readiness polling, safe failure, retry, and opaque-key coverage.

## Decisions Made

- Kept provenance in the existing metadata JSON because the locked record fits without a schema column; the migration adds only `authorization_status=needs_confirmation` to legacy Qwen rows.
- Left downgrade as a documented no-op because a reverse rewrite cannot distinguish migrated legacy rows from voices created natively with the canonical identity.
- Kept the durable saved voice id in RayMe's public call state and used the content-derived opaque key only at the AI backend boundary, preventing authorization details or raw content from becoming identity.
- Required local authorization before the initial backend readiness request and revalidated at offer/turn boundaries so deletion, tampering, path substitution, or stale transcripts fail closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Wired preparation through the existing call API facade**
- **Found during:** Task 3 (Carry authorization and readiness into call preparation)
- **Issue:** The plan listed domain call/client files, but production calls enter through `app/api/calls.py`; domain-only implementation would leave real calls able to bypass the new preparation contract.
- **Fix:** Added pre-backend local preflight to `/api/calls/start`, opaque-key session creation plus one-shot preparation to `/api/calls/{call_id}/offer`, and exact validated Qwen reference forwarding for turns.
- **Files modified:** `web-ui/server/app/api/calls.py`
- **Verification:** The 53-test call suite and full 203-test Web server suite passed, including safe failure and later retry.
- **Committed in:** `bec82dd`

---

**Total deviations:** 1 auto-fixed (1 missing critical production wiring requirement).
**Impact on plan:** The change closed the actual server entry point required by the planned behavior; it did not add a new browser route, hosted service, deployment path, or non-live synthesis fallback.

## Issues Encountered

- The existing call facade initially created backend sessions with the durable database voice id and had no preparation step. The implementation now uses the authorized content-derived key consistently for offer, preparation, and speech while preserving the public saved voice id.
- Existing call-reference logging included local blob paths and directory contents. The shared contained-asset path replaced those diagnostics with opaque saved voice ids and fixed event names.

## User Setup Required

None - no new package, service, secret, or manual configuration is required.

## Next Phase Readiness

- The server-side identity, saved-reference authorization, and live-call preparation contracts are complete and fully covered by the Web server suite.
- Qwen remains non-default; final RayMe call listening/acceptance can now exercise the exact 1.7B saved-voice path without bypassing authorization or readiness.
- No known stubs, skipped tests, unrun verification commands, or blockers remain.

## Self-Check: PASSED

- All ten implementation/test files and this summary exist.
- Commits `9f041e8`, `27288a5`, `2f91842`, `74377a3`, `30c14f3`, and `bec82dd` are present in git history.
- Migration/voice tests passed (42), Alembic reached head, voice tests passed (36), call tests passed (53), the full Web server suite passed (203), both slow-stream live-call regressions passed, and `git diff --check` passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
