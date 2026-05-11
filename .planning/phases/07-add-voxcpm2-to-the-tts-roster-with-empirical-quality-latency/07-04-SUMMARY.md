---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 04
subsystem: testing
tags: [voxcpm2, tts, scenario-matrix, evidence, nyquist]

requires:
  - phase: 00-measurement-gate
    provides: Shared TTS scenario matrix harness, chunk planner, and prior roster evidence schema.
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Phase 07 VoxCPM2 roster, Voice Lab, and call-flow RED contracts from plans 07-01 through 07-03.
provides:
  - VoxCPM2 scenario-matrix RED tests for shared chunk planner rows and F5 promotion comparison.
  - Phase-local evidence templates for manual quality, OMEN runtime smoke, matrix, WAV, VRAM soak, and call-flow artifacts.
  - Contract verifier for static evidence headers/path declarations and future live evidence modes.
affects: [phase-07, tts, voxcpm2, measurement-gate, omen-evidence]

tech-stack:
  added: [pytest user-site availability for local verification environment]
  patterns: [RED evidence contracts, deterministic phase result paths, contract-only verifier mode]

key-files:
  created:
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/MANUAL-QUALITY.csv
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-OMEN-EVIDENCE.md
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/README.md
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/.gitkeep
  modified:
    - .planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py

key-decisions:
  - "VoxCPM2 promotion evidence uses `sample_path` as the future matrix/audio link field, leaving the current `output_wav` harness gap as an intentional RED failure."
  - "Phase 07 evidence verification starts with `--contract-only` and also reserves `--matrix-only`, `--call-flow-only`, and `--decision-ready` modes for later live evidence plans."

patterns-established:
  - "Phase evidence templates must name deterministic relative artifact paths before live OMEN runs."
  - "Promotion comparisons must name F5 explicitly rather than relying only on generic fastest-row summaries."

requirements-completed: [REQ-02, REQ-45, REQ-A3]

duration: 4min
completed: 2026-05-11
---

# Phase 07 Plan 04: VoxCPM2 Evidence Contract Summary

**VoxCPM2 promotion gate scaffolding with RED scenario-matrix contracts, deterministic evidence paths, and a contract-only verifier**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-11T02:31:34Z
- **Completed:** 2026-05-11T02:35:51Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added three RED scenario matrix tests requiring explicit VoxCPM2 chunk limits, short/medium/long rows, required row fields, and F5-named promotion comparison.
- Created Phase 07 manual quality and OMEN runtime evidence templates with the required VoxCPM2 package/model/CUDA/deploy fields.
- Added `07-verify-evidence.py --contract-only`, plus future live evidence modes for matrix, call-flow, and decision readiness.

## Task Commits

1. **Task 1: Add scenario matrix RED tests for VoxCPM2 rows** - `e7998f3` (test)
2. **Task 2: Create phase evidence templates and verifier contract** - `51b7a35` (docs)

## Files Created/Modified

- `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py` - Adds VoxCPM2 RED tests and repo-root import setup for the probe test command.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/MANUAL-QUALITY.csv` - Defines exact manual quality scoring header.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-OMEN-EVIDENCE.md` - Defines OMEN runtime evidence fields and required artifact paths.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py` - Verifies static contract headers/path declarations and future live artifacts.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/README.md` - Documents deterministic result paths and matrix row contract.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/.gitkeep` - Preserves the required generated audio directory.

## Verification

- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --contract-only` - PASS.
- `python3 -m pytest .planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py -q` - expected RED failure: 6 existing tests pass; 3 VoxCPM2 tests fail because VoxCPM2 is not yet in `ENGINE_CHUNK_LIMITS`/`ENGINE_ORDER`, matrix rows do not yet expose `sample_path` or chunk playback fields for the simulated VoxCPM2 rows, and `build_summary()` does not yet expose `promotion_comparison`.

## Decisions Made

- VoxCPM2 matrix rows must link audio through `sample_path`; current `output_wav` behavior remains a RED schema gap for implementation plans.
- The verifier owns deterministic evidence path checks now, while later live plans can reuse its `--matrix-only`, `--call-flow-only`, and `--decision-ready` modes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed pytest into the user Python environment**
- **Found during:** Task 1 verification
- **Issue:** The planned command `python3 -m pytest ...` failed before collection because `pytest` was not installed for `python3`.
- **Fix:** Installed `pytest==9.0.3` with `python3 -m pip install --user --break-system-packages pytest`.
- **Files modified:** None in the repo.
- **Verification:** The planned pytest command reached the intended RED assertions afterward.
- **Committed in:** Not applicable; environment-only fix.

**2. [Rule 3 - Blocking] Made probe tests importable from repo root**
- **Found during:** Task 1 verification
- **Issue:** The planned repo-root pytest command could not import `tts_scenario_matrix`.
- **Fix:** Added the probe directory to `sys.path` at test module import time.
- **Files modified:** `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py`
- **Verification:** The planned pytest command collected and ran all 9 tests, reaching only the intended VoxCPM2 RED failures.
- **Committed in:** `e7998f3`

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes were required to make the planned verification command execute the RED contract. No implementation support was added.

## Issues Encountered

- The scenario matrix verification is intentionally red. The failures are the contract output for later Phase 07 implementation plans, not a blocker for this scaffolding plan.

## Known Stubs

None. Evidence templates intentionally contain blank fields for later live OMEN and manual-listening runs, but the contract verifier now checks the required headers and path declarations.

## User Setup Required

None - no external service configuration required for this plan.

## Next Phase Readiness

Phase 07 now has deterministic evidence paths and RED scenario-matrix failures ready for implementation/runtime plans. Later plans must add VoxCPM2 to the scenario harness, emit `sample_path`/chunk playback fields, and populate live OMEN/manual evidence before promotion.

## Self-Check: PASSED

- Verified all created/modified files exist.
- Verified task commits `e7998f3` and `51b7a35` exist in git history.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
