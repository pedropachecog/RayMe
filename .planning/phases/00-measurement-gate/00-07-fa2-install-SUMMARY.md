---
phase: 00-measurement-gate
plan: "07"
subsystem: infra
tags: [flash-attn, qwen3, windows, cuda, build]
requires:
  - phase: "00"
    provides: "Phase 0 backend venv with torch installed from plan 01"
provides:
  - "Persisted FA2 install verdict for OMEN-PC"
  - "Qwen 1.7B recommendation forced off"
affects: [phase-00-writeback, qwen3-v1-disposition, phase-02-voice-lab]
tech-stack:
  added: []
  patterns: [Windows build verdict captured as JSON with stderr tail]
key-files:
  created: []
  modified:
    - .planning/phases/00-measurement-gate/probes/fa2_check.py
    - .planning/phases/00-measurement-gate/results/fa2_install.json
key-decisions:
  - "FlashAttention 2 is not available on OMEN-PC under the current Windows toolchain and torch stack."
  - "Qwen3 1.7B remains ineligible for v1 because FA2 is required to fit the 3060 budget."
patterns-established:
  - "Capture Windows source-build failures with stderr tails rather than reducing them to a boolean."
requirements-completed: []
duration: 1 min
completed: 2026-04-22
---

# Phase 00 Plan 07: FA2 Install Summary

**FlashAttention 2 install verdict recorded on OMEN-PC, keeping Qwen3 1.7B out of scope for the current 3060-backed runtime**

## Performance

- **Duration:** 1 min
- **Started:** 2026-04-22T16:26:28Z
- **Completed:** 2026-04-22T16:27:24Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added the FA2 install/verify probe for the Phase 0 backend venv.
- Recorded a concrete Windows compile failure instead of leaving FA2 as an assumption.
- Persisted the recommendation that Qwen 1.7B is not currently viable on this machine.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write fa2_check.py and record the install verdict** - `fd20ad2` (feat)

**Plan metadata:** captured in the task commit above.

## Files Created/Modified
- `.planning/phases/00-measurement-gate/probes/fa2_check.py` - FA2 install, timeout, import verification, and result writer.
- `.planning/phases/00-measurement-gate/results/fa2_install.json` - Install outcome, duration, failure reason, and Qwen recommendation flag.

## Decisions Made
- Keep `qwen17b_recommended` false until a successful FA2 path exists.
- Treat the current backend as eager-only for Qwen benchmarking.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The source build reached `cl.exe` successfully but failed inside CUTLASS headers with a Windows compile error, so this is not a simple “missing toolchain” case.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The FA2 verdict is available for `00-07.1` backend labeling and `00-08` synthesis.
- Any future Qwen comparison must explicitly state whether it is still the eager baseline or a genuinely FA2-enabled rerun.

---
*Phase: 00-measurement-gate*
*Completed: 2026-04-22*
