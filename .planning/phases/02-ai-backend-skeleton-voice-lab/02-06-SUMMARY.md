---
phase: 02-ai-backend-skeleton-voice-lab
plan: "06"
subsystem: ai-backend
tags: [fastapi, pydantic, pynvml, model-manager, health, tts-residency]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: AI backend RED health/model residency contracts from plan 02-02 and Web UI status bridge from plan 02-05
provides:
  - Lifespan-owned AI backend `ModelManager` with one resident TTS engine
  - Phase 0 STT/VAD/TTS runtime defaults centralized in `AiBackendSettings`
  - Expanded `/health` payload with residency, engine roster, loading state, and VRAM/headroom
affects: [02-07, 02-08, 02-10, 02-14, 02-18]

tech-stack:
  added: [pydantic==2.13.3, pynvml==13.0.1, soundfile==0.13.1, numpy==2.2.6]
  patterns: [FastAPI lifespan model ownership, metadata-driven six-engine roster, sanitized engine degradation reasons]

key-files:
  created:
    - ai-backend/app/config.py
    - ai-backend/app/models/__init__.py
    - ai-backend/app/models/model_manager.py
    - ai-backend/app/models/engine_metadata.py
    - ai-backend/app/api/__init__.py
    - ai-backend/app/api/health.py
  modified:
    - ai-backend/pyproject.toml
    - ai-backend/uv.lock
    - ai-backend/app/main.py

key-decisions:
  - "AI backend model residency now starts from a metadata-driven six-engine roster with F5 as the default resident engine."
  - "Unit tests use lightweight adapters and the default runtime manager uses no-op adapters until later STT/TTS implementation plans wire real models."
  - "Public health degradation reasons are sanitized fixed strings, not raw adapter exceptions or model paths."

patterns-established:
  - "FastAPI app state owns `ModelManager`; lifespan starts and shuts it down."
  - "Model health serializes plain dict payloads so browser/server bridges do not receive Python objects."
  - "Engine switching unloads the prior resident adapter before loading the requested target."

requirements-completed: [REQ-02, REQ-22, REQ-80, REQ-A3]

duration: 5 min
completed: 2026-04-25
---

# Phase 02 Plan 06: AI Backend Model Manager and Health Summary

**Lifespan-managed AI backend model residency with Phase 0 STT defaults, six-engine TTS status, and VRAM/headroom health reporting.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-24T23:57:16Z
- **Completed:** 2026-04-25T00:02:22Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Added `AiBackendSettings` with Phase 0 defaults for `distil-large-v3`, `int8_float16`, English STT, F5 default TTS, 11 GB VRAM budget, and VAD thresholds.
- Added `EngineMetadata`, `EngineStatus`, and `ModelManager` with the full six-engine roster, sanitized unavailable reasons, one-resident TTS state, switch unload-before-load behavior, and VRAM probing.
- Moved `/health` into `app/api/health.py`, wired `FastAPI(..., version="0.2.0", lifespan=lifespan)`, and exposed Phase 2 capabilities plus residency and VRAM fields.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add config and model manager foundation** - `4f6c279` (feat)
2. **Task 2: Wire FastAPI lifespan and expanded health router** - `166f571` (feat)

Existing RED contracts from plan 02-02 were used as the TDD baseline for this implementation plan.

## Files Created/Modified

- `ai-backend/pyproject.toml` - Adds required AI backend dependency pins.
- `ai-backend/uv.lock` - Locks added runtime packages.
- `ai-backend/app/config.py` - Defines `AiBackendSettings`.
- `ai-backend/app/models/engine_metadata.py` - Defines engine metadata/status models and six-engine roster.
- `ai-backend/app/models/model_manager.py` - Coordinates startup, shutdown, engine switching, residency health, and VRAM probing.
- `ai-backend/app/models/__init__.py` - Exports model manager and metadata types.
- `ai-backend/app/api/health.py` - Serves the expanded Phase 2 health payload.
- `ai-backend/app/api/__init__.py` - Initializes the API package.
- `ai-backend/app/main.py` - Wires FastAPI lifespan and includes the health router.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py -q` - PASS, 4 tests.
- `uv run --project ai-backend pytest ai-backend/tests/test_health.py ai-backend/tests/test_model_manager.py -q` - PASS, 10 tests with one `pynvml` deprecation warning from the requested dependency.
- `uv run --project ai-backend pytest ai-backend/tests/test_health.py -q` - PASS, 6 tests with the same warning.
- Acceptance `rg` checks passed for Phase 0 defaults, model manager symbols, lifespan/app-state wiring, Phase 2 health fields, capabilities, and VRAM headroom.

## Decisions Made

- Used no-op default TTS adapters so the AI backend can boot and report residency without downloading GPU models during unit tests; later adapter plans own real model loading.
- Kept health payload reasons fixed and sanitized to satisfy the information-disclosure threat mitigation.
- Added a health-route startup guard because the existing tests instantiate `TestClient(create_app())` without a context manager, while runtime lifespan still owns normal startup/shutdown.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Initial health serialization returned Pydantic objects inside a plain dict; corrected `ModelManager.health()` to emit JSON-serializable mappings before committing Task 1.
- `TestClient(create_app())` does not enter lifespan in the existing test style, so the health route now starts the app-state manager if it has not already been started.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. The default no-op adapters are intentional test/lightweight residency scaffolding for this plan; real STT/TTS adapters are owned by later Phase 2 plans.

## Next Phase Readiness

Plan 02-07 can add STT/VAD processing against the centralized `AiBackendSettings`. Plan 02-08 can replace no-op TTS adapters with registry-backed real adapters while preserving the one-resident switching contract and `/health` payload shape.

## TDD Gate Compliance

- RED contracts were previously committed by plan 02-02 (`b2dc485` for model manager/health contracts).
- GREEN implementation commits for this plan are present: `4f6c279`, `166f571`.

## Self-Check: PASSED

- Verified key created files exist: `config.py`, `models/__init__.py`, `model_manager.py`, `engine_metadata.py`, `api/__init__.py`, `health.py`, and this summary.
- Verified task commits exist: `4f6c279`, `166f571`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
