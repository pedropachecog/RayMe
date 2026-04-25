---
phase: 02-ai-backend-skeleton-voice-lab
plan: "08"
subsystem: ai-backend
tags: [fastapi, tts, registry, f5-tts, coqui-tts, qwen-tts, pytest]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: AI backend model manager, health payload, STT route, and RED TTS registry contracts from plans 02-02, 02-06, and 02-07
provides:
  - Metadata-driven six-engine TTS registry with F5 as the only default and per-engine caveats/licenses/runtime evidence
  - Optional TTS runtime dependency pins for F5-TTS, XTTS v2 through coqui-tts, and Qwen3-TTS 0.6B-Base
  - Transient `/tts/synthesize` API with engine switching, JSON WAV payloads, and fixed public `tts_failed` errors
affects: [02-09, 02-12, 02-13, 02-14, 02-16, 02-18]

tech-stack:
  added: [f5-tts==1.1.17, coqui-tts==0.27.5, qwen-tts==0.1.1]
  patterns: [metadata-driven TTS registry, optional runtime extras, import-gated adapters, sanitized transient synthesis route]

key-files:
  created:
    - ai-backend/app/models/tts_registry.py
    - ai-backend/app/models/tts_f5.py
    - ai-backend/app/models/tts_xtts.py
    - ai-backend/app/models/tts_qwen3.py
    - ai-backend/app/models/tts_luxtts.py
    - ai-backend/app/models/tts_chatterbox.py
    - ai-backend/app/models/tts_tada.py
    - ai-backend/app/api/tts.py
  modified:
    - ai-backend/pyproject.toml
    - ai-backend/uv.lock
    - ai-backend/app/main.py
    - ai-backend/app/models/model_manager.py
    - ai-backend/tests/test_tts_registry.py
    - web-ui/server/app/domain/ai_backend_client.py
    - web-ui/server/tests/test_health_settings.py

key-decisions:
  - "TTS runtime packages are locked behind the `tts` optional extra so default unit-test runs remain model-download-free."
  - "The AI backend canonical synthesis route is `/tts/synthesize`; the Web UI AI backend client now targets the same path."
  - "Per-engine adapter modules are import-gated and degrade through sanitized 502 responses until live runtime evidence enables real synthesis paths."

patterns-established:
  - "TTS metadata stores code license, model license, caveat chips, transcript/streaming flags, runtime evidence, quality notes, and availability state in one registry."
  - "Synthesis routes switch through `ModelManager.switch_tts_engine()` before adapter invocation and never persist audio in the AI backend."
  - "Browser-facing synthesis failures return fixed `tts_failed` details without local paths, tracebacks, or adapter exception text."

requirements-completed: [REQ-02, REQ-22, REQ-23]

duration: 15 min
completed: 2026-04-25
---

# Phase 02 Plan 08: TTS Registry and Transient Synthesis Summary

**Six-engine TTS registry with optional runtime pins and a sanitized transient `/tts/synthesize` API.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-25T00:44:22Z
- **Completed:** 2026-04-25T00:58:54Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- Added `TtsEngineRegistry` with the full measured roster: F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base, LuxTTS, Chatterbox Turbo, and TADA 1B.
- Added metadata fields for licenses, caveat chips, runtime evidence, transcript requirements, streaming support, quality notes, and availability.
- Added import-gated per-engine adapter modules and wired the default `ModelManager` adapter map to them.
- Added `POST /tts/synthesize` for transient TTS synthesis requests, engine switching, base64 WAV JSON responses, and sanitized `tts_failed` errors.
- Updated the Web UI server AI backend client to call `/tts/synthesize` instead of the older placeholder `/synthesize`.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add TTS registry metadata contracts** - `fdffd88` (test)
2. **Task 1 GREEN: Add metadata-driven TTS registry** - `dfdf61b` (feat)
3. **Task 2: Gate TTS registry metadata** - `dbcb868` (test, empty verification commit)
4. **Task 3 RED: Add transient TTS synthesis contracts** - `0dd516f` (test)
5. **Task 3 GREEN: Add transient TTS synthesis API** - `30d7d45` (feat)

## Files Created/Modified

- `ai-backend/app/models/tts_registry.py` - Registry metadata models, adapter protocol, import-gated base adapter, roster validation, and default adapter factory.
- `ai-backend/app/models/tts_f5.py` - F5-TTS adapter module.
- `ai-backend/app/models/tts_xtts.py` - XTTS v2 adapter module.
- `ai-backend/app/models/tts_qwen3.py` - Qwen3-TTS 0.6B adapter module.
- `ai-backend/app/models/tts_luxtts.py` - LuxTTS adapter module.
- `ai-backend/app/models/tts_chatterbox.py` - Chatterbox Turbo adapter module.
- `ai-backend/app/models/tts_tada.py` - TADA 1B adapter module.
- `ai-backend/app/api/tts.py` - Transient synthesis route with input validation, engine switching, and sanitized failure handling.
- `ai-backend/app/main.py` - Includes the TTS router.
- `ai-backend/app/models/model_manager.py` - Uses the registry-backed default TTS adapter map.
- `ai-backend/tests/test_tts_registry.py` - Registry, adapter/API, sanitized error, and no-persistence route coverage.
- `ai-backend/pyproject.toml` and `ai-backend/uv.lock` - Add optional TTS runtime packages and align pydantic with the measured F5 pin.
- `web-ui/server/app/domain/ai_backend_client.py` and `web-ui/server/tests/test_health_settings.py` - Align Web UI synthesis calls with `/tts/synthesize`.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py -q` - PASS, 10 tests after Task 3.
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_health.py -q` - PASS, 16 tests with the existing `pynvml` deprecation warning.
- `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py -q` - PASS, 4 tests.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` - PASS, 17 tests.
- `rg "f5|xtts_v2|qwen3_0_6b|luxtts|chatterbox_turbo|tada_1b|F5-TTS|XTTS v2|Qwen3-TTS 0.6B-Base|LuxTTS|Chatterbox Turbo|TADA 1B|CC-BY-NC|CPML|Apache-2.0|runtime_evidence" ai-backend/app ai-backend/tests/test_tts_registry.py` - PASS.
- `rg "POST.*/tts/synthesize|use_default_engine|switch_tts_engine|loading_engine|tts_failed|Synthesis failed|include_router\\(tts" ai-backend/app ai-backend/tests/test_tts_registry.py` - PASS.

## Decisions Made

- Kept heavyweight TTS packages in an optional `tts` extra while still locking the measured package names required by research.
- Downgraded the AI backend pydantic pin to `2.10.6` because `f5-tts==1.1.17` cannot resolve with `pydantic==2.13.3`.
- Treated `/tts/synthesize` as the canonical AI backend TTS route and updated the Web UI server client to match it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Resolved F5 runtime dependency conflict**
- **Found during:** Task 1 (Build metadata-driven TTS registry contract)
- **Issue:** Adding `f5-tts==1.1.17` exposed a resolver conflict because that measured pin requires `pydantic<=2.10.6`, while the AI backend had `pydantic==2.13.3`.
- **Fix:** Changed the AI backend pydantic pin to `2.10.6` and placed heavyweight TTS packages behind `[project.optional-dependencies].tts`.
- **Files modified:** `ai-backend/pyproject.toml`, `ai-backend/uv.lock`
- **Verification:** AI backend registry, health, and model-manager tests passed.
- **Committed in:** `dfdf61b`

**2. [Rule 1 - Bug] Aligned Web UI synthesis client with canonical AI backend route**
- **Found during:** Task 3 (Add transient synthesis API, adapters, and switch status)
- **Issue:** The Web UI AI backend client still targeted `/synthesize`, but this plan creates the canonical AI backend route at `/tts/synthesize`.
- **Fix:** Updated `AiBackendClient.synthesize()` and its existing contract test to use `/tts/synthesize`.
- **Files modified:** `web-ui/server/app/domain/ai_backend_client.py`, `web-ui/server/tests/test_health_settings.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` passed.
- **Committed in:** `30d7d45`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes were required for correctness. The pydantic change keeps the measured F5 package resolvable; the Web UI client change prevents the completed voice API path from calling a non-existent synthesis endpoint.

## Issues Encountered

- Syncing the optional TTS packages downloaded and installed large ML/audio dependencies in the local environment.
- Import inspection for F5 is heavy and begins loading model-adjacent libraries, so runtime enablement remains evidence-gated rather than part of unit tests.
- The existing `pynvml` deprecation warning still appears in health tests and is unchanged by this plan.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. The per-engine adapter modules are intentional import-gated runtime boundaries; they do not persist audio or fabricate synthesis output. Live model self-tests and evidence-based runtime enablement remain owned by later Phase 02 runtime evidence plans.

## Threat Flags

None. The new `/tts/synthesize` endpoint is the planned trust-boundary surface in this plan's threat model and includes bounded input validation, transient audio handling, engine-local degradation, and fixed public error details.

## Next Phase Readiness

Voice Lab and Voice Library paths can call a stable `/tts/synthesize` backend route. Later plans can render registry caveats in the UI, add license notices, and replace import-gated adapter boundaries with live OMEN-PC-verified runtime synthesis paths.

## TDD Gate Compliance

- RED gate commits present: `fdffd88`, `0dd516f`
- GREEN gate commits present after RED commits: `dfdf61b`, `30d7d45`
- Registry-only Task 2 gate commit present between registry implementation and adapter/API work: `dbcb868`

## Self-Check: PASSED

- Verified key created files exist: `02-08-SUMMARY.md`, `tts_registry.py`, `api/tts.py`, and all six `tts_*.py` adapter modules.
- Verified task commits exist: `fdffd88`, `dfdf61b`, `dbcb868`, `0dd516f`, and `30d7d45`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
