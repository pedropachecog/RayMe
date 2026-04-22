---
phase: 00-measurement-gate
plan: "04"
subsystem: infra
tags: [tts, f5-tts, xtts, qwen3, latency]
requires:
  - phase: "00"
    provides: "Phase 0 backend environment and voice benchmark fixtures from plans 01 and 03"
provides:
  - "Measured TTFA/RTF for F5, XTTS, and Qwen3 on OMEN-PC"
  - "Current v1 default candidate pinned to F5"
affects: [phase-02-voice-lab, phase-04-call-feel, tts-engine-selection]
tech-stack:
  added: []
  patterns: [per-engine subprocess isolation, production-style F5 ack plus chunked remainder baseline]
key-files:
  created:
    - .planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt
    - .planning/phases/00-measurement-gate/probes/test_tts_ttfa.py
  modified:
    - .planning/phases/00-measurement-gate/probes/tts_ttfa.py
    - .planning/phases/00-measurement-gate/results/tts_ttfa.json
key-decisions:
  - "Keep F5 as the current default candidate because no engine hits the budget and it still has the best TTFA."
  - "Keep XTTS as the only native-streaming compatibility fallback."
patterns-established:
  - "Run each TTS engine in its own subprocess so a fatal engine crash cannot abort the full benchmark."
requirements-completed: []
duration: 133 min
completed: 2026-04-22
---

# Phase 00 Plan 04: TTS TTFA Summary

**Measured F5, XTTS, and Qwen3 TTS latency on OMEN-PC, keeping F5 as the default candidate while flagging the engine-budget miss**

## Performance

- **Duration:** 133 min
- **Started:** 2026-04-22T16:46:55Z
- **Completed:** 2026-04-22T18:59:55Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added the short reference transcript fixture and unit tests for the TTS benchmark rig.
- Measured all three candidate TTS engines against the builder recording on OMEN-PC.
- Persisted the current default decision and the Qwen rejection reasons for v1.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build TTS TTFA fixtures and tests** - `f207093` (feat)
2. **Task 2: Record real TTS benchmark outcomes** - `23b506e` (feat)

**Plan metadata:** captured in the two task commits above.

## Files Created/Modified
- `.planning/phases/00-measurement-gate/probes/tts_ttfa.py` - TTS benchmark harness for F5, XTTS, and Qwen3.
- `.planning/phases/00-measurement-gate/probes/fixtures/short_ref_transcript.txt` - Short voice-clone reference transcript.
- `.planning/phases/00-measurement-gate/probes/test_tts_ttfa.py` - Coverage for TTFA default-selection and Qwen gate helpers.
- `.planning/phases/00-measurement-gate/results/tts_ttfa.json` - Current Phase 0 TTS result set.

## Decisions Made
- Kept `f5` as the current v1 default because it still has the best TTFA when all engines miss the target.
- Rejected Qwen3 for v1 for now because TTFA and RTF both miss the gate and the accent check remains unapproved.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- F5 required runtime shims to avoid a Windows-only import crash during live benchmarking.
- XTTS needed explicit CPML approval on OMEN-PC before the native streaming path could be measured.
- The short-result artifact has since been refreshed by `00-07.1` with explicit backend labels, but the engine-selection outcome remains the same: F5 first, XTTS fallback, Qwen rejected.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 00 now has a persisted TTS default candidate and a rejected Qwen gate for v1.
- `00-07.1` extends this plan’s output with backend labeling, and `00-05` still needs the VRAM soak before final writeback.

---
*Phase: 00-measurement-gate*
*Completed: 2026-04-22*
