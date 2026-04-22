---
phase: 00-measurement-gate
plan: "03"
subsystem: infra
tags: [whisper, faster-whisper, stt, wer, vram]
requires:
  - phase: "00"
    provides: "Phase 0 backend environment and cached Whisper checkpoints from plan 01"
provides:
  - "Measured Whisper WER/latency/VRAM across three rungs"
  - "Default STT rung pinned to distil-large-v3"
affects: [phase-02-ai-backend, phase-04-call-feel, stt-default-selection]
tech-stack:
  added: []
  patterns: [NVML delta VRAM tracking for non-torch allocators]
key-files:
  created:
    - .planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt
    - .planning/phases/00-measurement-gate/probes/test_whisper_bench.py
  modified:
    - .planning/phases/00-measurement-gate/probes/whisper_bench.py
    - .planning/phases/00-measurement-gate/results/whisper.json
key-decisions:
  - "distil-large-v3 is the default Whisper rung because it stays inside the 2pp WER rule and is materially faster than the larger models."
  - "VRAM must be tracked with NVML delta rather than torch allocator stats because faster-whisper allocates outside torch."
patterns-established:
  - "Persist per-rung hypotheses so WER can be recomputed later."
requirements-completed: []
duration: 133 min
completed: 2026-04-22
---

# Phase 00 Plan 03: Whisper WER Summary

**Measured Whisper WER, latency, and VRAM on the builder recording, with distil-large-v3 selected as the default STT rung**

## Performance

- **Duration:** 133 min
- **Started:** 2026-04-22T16:46:55Z
- **Completed:** 2026-04-22T18:59:55Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added the reference transcript fixture and unit tests for the Whisper benchmark rig.
- Ran the real builder-voice benchmark on OMEN-PC for `distil-large-v3`, `large-v3-turbo`, and `large-v3`.
- Selected `distil-large-v3` as the default rung based on the roadmap’s speed-vs-WER rule.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build whisper benchmark fixtures and tests** - `f207093` (feat)
2. **Task 2: Record real Whisper benchmark outcomes** - `23b506e` (feat)

**Plan metadata:** captured in the two task commits above.

## Files Created/Modified
- `.planning/phases/00-measurement-gate/probes/whisper_bench.py` - Whisper benchmark harness with latency and NVML VRAM sampling.
- `.planning/phases/00-measurement-gate/probes/fixtures/reference_transcript.txt` - Builder read-aloud script.
- `.planning/phases/00-measurement-gate/probes/test_whisper_bench.py` - Pure-Python coverage for the benchmark helpers.
- `.planning/phases/00-measurement-gate/results/whisper.json` - Three-rung result set with per-rung WER, latency, hypotheses, and peak VRAM.

## Decisions Made
- Defaulted Phase 2 STT to `distil-large-v3` with `int8_float16`.
- Recorded VRAM as NVML delta from baseline because torch allocator stats understated real usage.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The initial live run exposed bogus peak-VRAM readings from torch allocator stats; the probe was corrected to track NVML delta instead before the final result was persisted.
- `ctranslate2` had to be downgraded to `3.24.0` on OMEN-PC to match the CUDA 11.8 backend stack used in Phase 0.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The STT default rung is pinned for downstream backend work.
- `whisper.json` is ready for `00-05-vram-soak` and `00-08-synthesis-writeback`.

---
*Phase: 00-measurement-gate*
*Completed: 2026-04-22*
