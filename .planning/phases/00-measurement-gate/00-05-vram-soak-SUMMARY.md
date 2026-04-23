---
phase: 00-measurement-gate
plan: "05"
subsystem: infra
tags: [tts, vram, whisper, silero-vad, soak]
requires:
  - phase: "00"
    provides: "00-03 default Whisper rung"
  - phase: "00"
    provides: "00-04 short reference audio fixture and TTS probe paths"
provides:
  - "30-minute VRAM soak results for F5, XTTS, and Qwen3"
  - "Stable/no-growth verdict for all three candidate TTS engines on the target RTX 3060"
affects: [phase-00-writeback, tts-engine-selection, req-02]
tech-stack:
  added: []
  patterns: [slope-based VRAM growth detection, realistic cycling soak with Whisper + VAD + TTS]
key-files:
  created:
    - .planning/phases/00-measurement-gate/probes/vram_soak.py
    - .planning/phases/00-measurement-gate/probes/test_vram_soak.py
    - .planning/phases/00-measurement-gate/results/vram_soak_f5.json
    - .planning/phases/00-measurement-gate/results/vram_soak_xtts.json
    - .planning/phases/00-measurement-gate/results/vram_soak_qwen3.json
key-decisions:
  - "All three measured TTS engines fit inside the 11 GB RTX 3060 budget during a 30-minute realistic soak."
  - "No engine showed fragmentation growth; all final slopes were negative."
patterns-established:
  - "Use minute-sampled VRAM time series plus a last-20-minute slope, not a single peak, to decide whether an engine is soak-safe."
  - "Smoke-run the soak harness before committing to the full 90-minute measurement block."
requirements-completed: [REQ-02]
duration: 92 min
completed: 2026-04-23
---

# Phase 00 Plan 05: VRAM Soak Summary

**Executed the 30-minute Whisper + Silero + TTS soak for all three engines and confirmed they all fit and stay stable on the target RTX 3060**

## Performance

- **Duration:** 92 min
- **Started:** 2026-04-23T04:28:39Z
- **Completed:** 2026-04-23T06:00:05Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Built a portable soak harness and pure helper tests for slope-based growth detection.
- Validated the harness in the authoritative Windows Phase 0 venv (`5 passed`).
- Caught and fixed the Silero fixed-frame input bug during smoke runs before the full measurements.
- Recorded complete 30-minute soak artifacts for F5, XTTS, and Qwen3 on OMEN-PC’s RTX 3060.

## Task Commits

No dedicated task commits were present in the current worktree when this summary was written. The soak harness, tests, and three result artifacts are present locally and recorded here as completed work.

## Files Created/Modified

- `.planning/phases/00-measurement-gate/probes/vram_soak.py` - 30-minute multi-engine soak harness with slope-based growth detection.
- `.planning/phases/00-measurement-gate/probes/test_vram_soak.py` - Pure helper coverage for growth detection and result shaping.
- `.planning/phases/00-measurement-gate/results/vram_soak_f5.json` - F5 soak result.
- `.planning/phases/00-measurement-gate/results/vram_soak_xtts.json` - XTTS soak result.
- `.planning/phases/00-measurement-gate/results/vram_soak_qwen3.json` - Qwen3 soak result.

## Per-Engine Results

| Engine | Peak VRAM (MB) | Growth | Slope (MB/min) | Cycles | Fits 3060 |
|---|---:|---|---:|---:|---|
| F5 | 1990.2 | no | -1.25 | 180 | yes |
| XTTS | 2104.0 | no | -2.04 | 180 | yes |
| Qwen3 | 3010.0 | no | -9.86 | 180 | yes |

## Decisions Made

- No engine exceeded the 11 GB Phase 0 ceiling, so VRAM budget alone does not eliminate any of the three candidates on the actual target GPU.
- No fragmentation-growth remediation is needed right now because every soak ended with a negative slope.
- Qwen3 still remains out of the v1 roster, but for latency/quality reasons from `00-04`, not because of VRAM.

## Issues Encountered

- The first smoke run surfaced a Silero VAD framing bug because the model expects a fixed 512-sample window at 16 kHz. The harness was patched before the full runs started.

## User Setup Required

None - the long runs have already been executed and copied into the repo.

## Next Phase Readiness

- `00-08` now has the missing VRAM inputs it needed for Phase 0 synthesis.
- Phase 1 can assume that F5, XTTS, and Qwen3 all fit the 3060 from a soak perspective, while still honoring the TTFA and Qwen acceptance-gate decisions from the earlier plans.

---
*Phase: 00-measurement-gate*
*Completed: 2026-04-23*
