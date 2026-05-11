---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 05
subsystem: ai-backend
tags: [ai-backend, tts, voxcpm2, cuda, pytest]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-01 VoxCPM2 backend RED contracts for metadata, CUDA adapter behavior, bounded options, and sanitized errors
provides:
  - VoxCPM2 runtime-path decision artifact selecting the standard Python API baseline
  - Metadata-visible VoxCPM2 roster entry with optional `voxcpm==2.0.2` runtime dependency
  - CUDA-forced VoxCPM2 adapter using `openbmb/VoxCPM2` and runtime sample-rate output
  - Bounded `/tts/synthesize` VoxCPM2 options with warning-code response propagation
affects: [phase-07-voxcpm2-runtime, ai-backend-tts-registry, ai-backend-tts-api, ai-backend-model-manager]

tech-stack:
  added: [voxcpm==2.0.2]
  patterns: [import-gated optional TTS adapter, CUDA-only runtime guard, sanitized transient synthesis failures]

key-files:
  created:
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-RUNTIME-PATH-DECISION.md
    - ai-backend/app/models/tts_voxcpm2.py
  modified:
    - ai-backend/pyproject.toml
    - ai-backend/uv.lock
    - ai-backend/app/models/tts_registry.py
    - ai-backend/app/models/engine_metadata.py
    - ai-backend/app/api/tts.py
    - ai-backend/tests/test_tts_registry.py

key-decisions:
  - "VoxCPM2 initial runtime path is the standard Python `generate` API behind the existing RayMe AI backend API."
  - "VoxCPM2 is metadata-visible and candidate-caveated before OMEN runtime, VRAM, quality, and call-flow promotion evidence."
  - "VoxCPM2 runtime loading is CUDA-only: `require_torch_cuda_runtime(\"VoxCPM2\")` plus `device=\"cuda\"`."

patterns-established:
  - "VoxCPM2 adapter uses RayMe-owned temporary reference files and never exposes runtime cache paths through public errors."
  - "VoxCPM2-specific request fields are bounded on both the public route model and internal `TtsSynthesisInput`."

requirements-completed: [REQ-02, REQ-22, REQ-45, REQ-80, REQ-A3]

duration: 8min
completed: 2026-05-11
---

# Phase 07 Plan 05: VoxCPM2 Backend Runtime Summary

**VoxCPM2 is now a metadata-visible optional TTS engine with a CUDA-only standard Python adapter and bounded transient synthesis options.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-11T02:39:34Z
- **Completed:** 2026-05-11T02:47:13Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Created the D-17 runtime-path decision artifact comparing `standard_python_generate`, `standard_python_generate_streaming`, `nanovllm_voxcpm`, and `vllm_omni_serving`; the baseline path is the in-process standard Python API while preserving one public AI backend API.
- Added `voxcpm==2.0.2` to the AI backend optional `tts` extra and updated the lockfile.
- Added `voxcpm2` to backend registry and health metadata with Apache-2.0 licenses, candidate caveats, 48 kHz notes, streaming support, and Phase 7 evidence wording.
- Implemented `VoxCpm2TtsAdapter` with import gating, CUDA guard, `VoxCPM.from_pretrained("openbmb/VoxCPM2", device="cuda")`, reference-only fallback warnings, transcript-guided prompt mapping, style/control options, and runtime sample-rate WAV output.
- Wired bounded VoxCPM2 options through `/tts/synthesize` and returned adapter warning codes in transient JSON responses while preserving fixed `tts_failed` public errors.

## Task Commits

Each task was committed atomically:

1. **Task 1: Decide runtime path and add metadata-visible VoxCPM2 roster entry** - `c411396` (feat)
2. **Task 2: Implement CUDA-forced VoxCPM2 adapter** - `124dcb7` (feat)
3. **Task 3: Wire bounded VoxCPM2 options through `/tts/synthesize`** - `ec9352f` (test)

## Files Created/Modified

- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-RUNTIME-PATH-DECISION.md` - D-17 runtime-path evaluation and baseline implementation decision.
- `ai-backend/pyproject.toml` - Adds `voxcpm==2.0.2` to the optional TTS extra.
- `ai-backend/uv.lock` - Locks the optional VoxCPM2 dependency closure.
- `ai-backend/app/models/tts_registry.py` - Adds `voxcpm2` metadata, bounded VoxCPM2 synthesis fields, warning fields, and adapter registration.
- `ai-backend/app/models/engine_metadata.py` - Mirrors `voxcpm2` in health/model-manager metadata with candidate caveat.
- `ai-backend/app/models/tts_voxcpm2.py` - Implements the import-gated CUDA-only VoxCPM2 adapter.
- `ai-backend/app/api/tts.py` - Accepts bounded VoxCPM2 synthesis options and returns warning codes.
- `ai-backend/tests/test_tts_registry.py` - Adds focused warning-code and 300-character style-bound coverage.

## Verification

Plan-level command:

```bash
uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py -q
```

Result: `29 passed, 1 warning`.

Additional checks:

- `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py -q` -> `22 passed, 1 warning`.
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py -q` -> `6 passed`.
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_tts_voxcpm2.py -q` -> `23 passed, 1 warning`.
- `git diff --check` -> passed.
- Acceptance grep confirmed the decision artifact contains all four candidate ids, `one public AI backend API`, and exactly one `selected`.
- Acceptance grep confirmed `voxcpm2`, `VoxCPM2`, and `voxcpm==2.0.2` in the required metadata/dependency files.

The recurring warning is from `torch.cuda` importing deprecated `pynvml`; it is pre-existing dependency noise and did not fail the tests.

## Decisions Made

- Kept the first implementation path in-process and import-gated. Streaming and serving variants remain evidence-gated benchmark/fallback paths.
- Kept F5 as the only default engine; VoxCPM2 is visible as a candidate with RTX 3060 evidence pending.
- Added warning propagation through the transient route now because the adapter may validly fall back to reference-only mode when transcript-guided mode has no transcript.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Advanced synthesis option plumbing to satisfy Task 1 gate**
- **Found during:** Task 1 (runtime decision and metadata roster)
- **Issue:** The required Task 1 test command included `test_tts_registry.py`, which already contained the Plan 07-01 RED contract requiring bounded VoxCPM2 `/tts/synthesize` fields. Metadata-only implementation failed that gate.
- **Fix:** Added bounded VoxCPM2 fields to `TtsSynthesisInput` and `/tts/synthesize`, added warning fields to `TtsSynthesisOutput`, and registered a minimal import-gated adapter before expanding it in Task 2.
- **Files modified:** `ai-backend/app/models/tts_registry.py`, `ai-backend/app/api/tts.py`, `ai-backend/app/models/tts_voxcpm2.py`
- **Verification:** `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py -q` passed.
- **Committed in:** `c411396`

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** The moved work was required by existing RED contracts and stayed within the planned backend VoxCPM2 API surface. No architectural change or new public route was introduced.

## Issues Encountered

- Initial Task 1 verification failed because the registry test suite already asserted bounded VoxCPM2 synthesis fields. The failure was resolved by the Rule 3 deviation above.

## Known Stubs

None. Stub-pattern scan only found normal Python optional type annotations, test-local empty lists, and intentional test defaults.

## User Setup Required

None - no external service configuration required. The optional `tts` extra now includes VoxCPM2, but live OMEN install/load evidence is handled by later Phase 07 plans.

## Threat Flags

None - the new optional package/model boundary, CUDA enforcement, bounded synthesis fields, and sanitized failure behavior were already covered by this plan's threat model.

## Next Phase Readiness

Ready for the next Phase 07 plans to wire Web UI voice metadata, call-flow propagation, scenario evidence, and OMEN runtime verification. Live VoxCPM2 model download/load, RTX 3060 VRAM soak, and promotion decisions are not claimed by this plan.

## Self-Check: PASSED

- Found created/modified files listed in this summary, including `07-RUNTIME-PATH-DECISION.md`, `ai-backend/app/models/tts_voxcpm2.py`, and `07-05-SUMMARY.md`.
- Found task commits: `c411396`, `124dcb7`, and `ec9352f`.
- `git diff --check` passed after summary creation.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
