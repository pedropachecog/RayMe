---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 09
subsystem: testing
tags: [voxcpm2, tts, scenario-matrix, evidence, pytest]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-04 RED scenario matrix and evidence verifier contracts.
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-05 CUDA-only standard Python VoxCPM2 adapter and runtime-path decision.
provides:
  - VoxCPM2 scenario matrix rows through the shared short/medium/long chunk planner.
  - Standard Python VoxCPM2 benchmark runner labels and generated audio path fields.
  - F5 promotion comparison summary fields for VoxCPM2 decision evidence.
  - Runtime, matrix, call-flow, and decision-ready evidence verification modes.
affects: [phase-07, tts, voxcpm2, measurement-gate, omen-evidence]

tech-stack:
  added: []
  patterns: [TDD RED/GREEN probe contract, machine-verifiable evidence schemas, F5-named promotion comparator]

key-files:
  created:
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-09-SUMMARY.md
  modified:
    - .planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py
    - .planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/README.md

key-decisions:
  - "VoxCPM2 scenario matrix measurements use the standard Python `VoxCPM.from_pretrained(MODEL_ID_VOXCPM2, load_denoiser=False, device=\"cuda\")` path as the benchmark baseline."
  - "VoxCPM2 `generate_streaming` rows are labeled `standard_python_streaming_collected` and marked benchmark-only until call playback consumes chunks live."
  - "Decision-ready evidence now requires matrix, runtime, call-flow, and manual quality checks."

patterns-established:
  - "Scenario rows expose both `output_wav` and `sample_path` so existing Phase 0 consumers keep working while Phase 07 evidence can verify audio links."
  - "Promotion summaries name F5 as the baseline and VoxCPM2 as the candidate rather than relying on generic fastest-row summaries."

requirements-completed: [REQ-02, REQ-45, REQ-A3]

duration: 6min
completed: 2026-05-11
---

# Phase 07 Plan 09: VoxCPM2 Scenario Matrix and Evidence Schema Summary

**VoxCPM2 now has shared-planner scenario matrix support, F5 promotion comparison fields, and stricter promotion evidence verification modes.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-11T03:29:56Z
- **Completed:** 2026-05-11T03:35:57Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added VoxCPM2 to `ENGINE_ORDER` and `ENGINE_CHUNK_LIMITS`, so short, medium, and long replies use the same sentence-aware chunk planner as the rest of the roster.
- Added a standard Python VoxCPM2 scenario runner using `openbmb/VoxCPM2`, `device="cuda"`, runtime-reported sample rates, generated WAV sample paths, TTFA/RTF/VRAM metrics, and benchmark-only streaming collection labels.
- Added `sample_path`, chunk playback defaults, and `summary.promotion_comparison` fields so generated samples and F5 comparator metrics are machine-verifiable.
- Extended `07-verify-evidence.py` with `--runtime-only`, strengthened `--matrix-only` and `--call-flow-only`, and made `--decision-ready` require matrix, runtime, call-flow, and manual quality evidence.
- Updated `results/README.md` with exact JSON fields and accepted final outcome values.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add VoxCPM2 runner contract** - `f71e92f` (test)
2. **Task 1 GREEN: Add VoxCPM2 scenario matrix support** - `f6b5806` (feat)
3. **Task 2: Enforce promotion evidence schema** - `4f3323f` (feat)

_Note: Task 1 was marked `tdd="true"`, so it produced separate RED and GREEN commits._

## Files Created/Modified

- `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py` - Adds VoxCPM2 planner support, standard Python runner, benchmark-only streaming collection rows, `sample_path`, and F5 promotion comparison summary fields.
- `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py` - Adds the RED contract for official model id, CUDA standard Python runner labels, and runtime sample-rate discovery.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py` - Adds runtime-only verification and tightens matrix/call-flow/decision-ready evidence checks.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/README.md` - Documents exact matrix, runtime smoke, VRAM soak, call-flow, and final outcome fields.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-09-SUMMARY.md` - This execution summary.

## Verification

- `python3 -m pytest .planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py -q` - PASS (`11 passed`, one pre-existing pytest config warning).
- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --contract-only` - PASS.
- `git diff --check` - PASS.
- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --help | rg -- "--runtime-only|--call-flow-only"` - PASS.
- Acceptance grep for `voxcpm2|standard_python|openbmb/VoxCPM2` in the scenario matrix - PASS.
- Acceptance grep for VoxCPM2 hard-coded `16000`/`24000` sample rates - PASS, no matches.

## Decisions Made

- The scenario harness keeps `output_wav` for older Phase 0 outputs and adds `sample_path` for Phase 07 evidence verification.
- VoxCPM2 streaming collection is explicitly benchmark-only with `true_streaming=false`; call-flow streaming remains unclaimed until a later plan consumes live chunks.
- Runtime smoke evidence uses exact fields `package`, `model_id`, `device`, `runtime_sample_rate`, and `cpu_fallback_detected`; VRAM soak uses `peak_vram_mb`, `vram_budget_mb`, and `within_11gb_budget`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The expected TDD RED gate failed before implementation, then passed after the green commit.

## Known Stubs

None. Stub-pattern scan found existing/test-local empty lists, `None` values for failed measurement rows, and normal type defaults only; none block the plan goal.

## User Setup Required

None - no external service configuration required for this plan.

## Threat Flags

None - no new network endpoint, auth path, file-write trust boundary, or schema boundary was introduced beyond the planned local evidence artifact checks.

## Next Phase Readiness

The matrix runner and verifier are ready for later live OMEN evidence plans to generate VoxCPM2 rows, WAV samples, VRAM smoke/soak JSON, call-flow JSON, and manual quality rows before the final promotion decision.

## Self-Check: PASSED

- Verified all created/modified files listed in this summary exist.
- Verified task commits `f71e92f`, `f6b5806`, and `4f3323f` exist in git history.
- Verified plan-level tests and `git diff --check` passed before summary creation.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
