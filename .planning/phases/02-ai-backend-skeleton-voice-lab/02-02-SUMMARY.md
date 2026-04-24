---
phase: 02-ai-backend-skeleton-voice-lab
plan: "02"
subsystem: testing
tags: [pytest, fastapi, ai-backend, stt, vad, tts, contracts]

requires:
  - phase: 00-measurement-gate
    provides: Phase 0 STT/TTS defaults, RTX 3060 VRAM evidence, and model roster decisions
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: Phase 2 context and Wave 0 Web UI voice/settings contracts from plan 02-01
provides:
  - AI backend RED contracts for Phase 2 health, one-hot TTS residency, and typed degradation reasons
  - English-only faster-whisper STT/VAD contract with hallucination filtering and manual transcript fallback
  - Six-engine TTS registry metadata contract with F5 as the only default
affects: [02-05, 02-06, 02-07, 02-08, 02-10, 02-14, 02-18]

tech-stack:
  added: []
  patterns: [Wave 0 RED contract tests, fake adapter test doubles, metadata-driven engine roster assertions]

key-files:
  created:
    - ai-backend/tests/test_model_manager.py
    - ai-backend/tests/test_stt.py
    - ai-backend/tests/test_tts_registry.py
  modified:
    - ai-backend/tests/test_health.py

key-decisions:
  - "AI backend health must expose Phase 2 STT/VAD/TTS residency status, VRAM/headroom, and typed unavailable reasons without raw exception text."
  - "STT contracts pin faster-whisper to English transcribe mode with condition_on_previous_text disabled and manual transcript fallback for silence or hallucination filters."
  - "TTS registry contracts require the full six-engine roster with F5 as the only default before adapter/API work proceeds."

patterns-established:
  - "AI backend RED tests import future implementation modules inside tests so pytest collection stays clean before implementation."
  - "Registry tests use exact engine IDs and labels to prevent three-engine-only regressions."

requirements-completed: [REQ-02, REQ-21, REQ-22, REQ-23, REQ-A3]

duration: 7 min
completed: 2026-04-24
---

# Phase 02 Plan 02: AI Backend Wave 0 Contracts Summary

**RED pytest contracts for AI backend health residency, English-only STT/VAD behavior, and full six-engine TTS registry metadata.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-24T23:04:59Z
- **Completed:** 2026-04-24T23:11:38Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `ai-backend/tests/test_model_manager.py` covering Phase 0 STT defaults, one resident TTS engine, switch unload-before-load behavior, per-engine degradation, VRAM/headroom payloads, and sanitized unavailable reasons.
- Expanded `ai-backend/tests/test_health.py` from the Phase 1 health stub to the Phase 2 `/health` residency contract while preserving HTTPS runner tests.
- Added `ai-backend/tests/test_stt.py` covering faster-whisper options, VAD-gated transcription, hallucination blocklist filtering, and retry/manual transcript fallback shape.
- Added `ai-backend/tests/test_tts_registry.py` covering the exact six-engine roster, labels, required metadata fields, F5-only default status, and switch states `idle|loading|resident|unavailable`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add model manager and health contract tests** - `b2dc485` (test)
2. **Task 2: Add STT/VAD and TTS registry contract tests** - `7cdc151` (test)

## Files Created/Modified

- `ai-backend/tests/test_model_manager.py` - New model manager and health payload contract tests.
- `ai-backend/tests/test_health.py` - Updated `/health` assertions to Phase 2 residency/status fields.
- `ai-backend/tests/test_stt.py` - New STT/VAD contract tests for English-only transcription and fallback semantics.
- `ai-backend/tests/test_tts_registry.py` - New metadata-driven six-engine TTS registry contract tests.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py ai-backend/tests/test_health.py -q` - RED as expected: 6 failures, 4 passes. Failures are missing `app.config`, missing model manager modules, and the current Phase 1 health payload.
- `uv run --project ai-backend pytest ai-backend/tests/test_stt.py ai-backend/tests/test_tts_registry.py -q` - RED as expected: 8 failures, all from missing `app.models.stt` and `app.models.tts_registry`.
- `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py ai-backend/tests/test_stt.py ai-backend/tests/test_tts_registry.py ai-backend/tests/test_health.py -q` - RED as expected: 14 failures, 4 passes. Failures match the intentional Wave 0 implementation gaps.
- Acceptance `rg` checks passed for health/model residency terms, raw traceback blocking assertions, STT option/fallback terms, and six-engine registry metadata terms.

## Decisions Made

- Followed the Phase 2 locked full-roster rule: tests require `f5`, `xtts_v2`, `qwen3_0_6b`, `luxtts`, `chatterbox_turbo`, and `tada_1b`.
- Kept this plan RED-only. No AI backend runtime implementation, dependencies, routes, or model adapters were added because later Phase 2 plans own those changes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed collection-blocking pytest helper syntax**
- **Found during:** Task 1 (Add model manager and health contract tests)
- **Issue:** The initial helper used invalid Python syntax when trying to chain `pytest.fail(...)` from an `AttributeError`.
- **Fix:** Replaced the invalid exception-chaining expression with a direct `pytest.fail(...)` call.
- **Files modified:** `ai-backend/tests/test_model_manager.py`
- **Verification:** Re-ran Task 1 pytest; tests collected and produced only the expected RED implementation failures.
- **Committed in:** `b2dc485`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** No scope change. The fix was required so the RED contract suite could collect cleanly.

## Issues Encountered

Expected RED verification failures only after the collection syntax fix. No runtime implementation was attempted in this plan.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. Test doubles in the new contract tests are intentional fake adapters/models for future unit tests, not runtime stubs.

## Threat Flags

None. This plan adds security-relevant tests for future health/status and model-processing behavior but does not introduce runtime endpoints, file access, network calls, or schema changes.

## Next Phase Readiness

Ready for later Phase 2 AI backend implementation plans to make the RED contracts pass: plan 02-06 for config/model manager/health, plan 02-07 for STT/VAD, and plan 02-08 for the TTS registry and adapters.

## Self-Check: PASSED

- Verified created/modified files exist: `test_model_manager.py`, `test_stt.py`, `test_tts_registry.py`, `test_health.py`, and this summary.
- Verified task commits exist: `b2dc485`, `7cdc151`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-24*
