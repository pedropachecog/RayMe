---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
plan: 06
subsystem: decision-writeback
tags: [voxcpm2, tts, live-call, evidence, docs]

# Dependency graph
requires:
  - phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
    provides: Phase 8 live repeated warm F5 versus VoxCPM2 call-flow evidence
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Phase 7 selectable-with-caveats decision and quality/runtime context
provides:
  - Evidence-gated Phase 8 VoxCPM2 live-call promotion decision
  - Machine-readable preferred/default live-call TTS decision artifact
  - PROJECT, STATE, and ROADMAP wording aligned on VoxCPM2 as preferred/default live-call TTS
affects: [voxcpm2-default-decision, live-call-tts, phase-8-closeout]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Decision writeback is gated by `08-verify-evidence.py --decision-ready`
    - Durable engine decisions cite same-run live call-flow evidence paths and median TTFA values

key-files:
  created:
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-PROMOTION-DECISION.md
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-decision.json
  modified:
    - .planning/PROJECT.md
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "VoxCPM2 is promoted as the preferred/default live-call TTS engine after Phase 8 same-run warm median first-audio beat F5."
  - "F5 remains available as fallback/comparator, but no longer wins the live-call default decision on call-feel speed."
  - "Phase 8 durable decisions cite `results/voxcpm2-live-streaming-call-flow.json` with VoxCPM2 `762.7 ms` versus F5 `948.0 ms`."

patterns-established:
  - "Final TTS default changes require both human-readable and machine-readable decision artifacts plus durable project doc alignment."

requirements-completed: [P8-R5]

# Metrics
duration: 4 min
completed: 2026-05-11
---

# Phase 08 Plan 06: Evidence-Gated VoxCPM2 Live-Call Default Decision Summary

**VoxCPM2 promoted to preferred/default live-call TTS using Phase 8 same-run streaming call evidence**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-11T19:11:20Z
- **Completed:** 2026-05-11T19:15:55Z
- **Tasks:** 2 completed
- **Files modified:** 5

## Accomplishments

- Created `08-PROMOTION-DECISION.md` and `results/voxcpm2-decision.json` with outcome `promoted_for_live_call_default`.
- Promoted `voxcpm2` as the preferred/default live-call TTS engine after verified live evidence showed `762.7 ms` median TTFA versus F5 `948.0 ms`.
- Updated PROJECT, STATE, and ROADMAP so durable project decision surfaces agree on the Phase 8 live-call default and evidence path.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Phase 8 promotion decision artifacts** - `5766306` (docs)
2. **Task 2: Update durable project decision wording** - `c4513d3` (docs)

## Files Created/Modified

- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-PROMOTION-DECISION.md` - Human-readable Phase 8 promotion decision.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-decision.json` - Machine-readable live-call TTS default decision.
- `.planning/PROJECT.md` - Adds `TTS live-call default (Phase 8): voxcpm2` and removes the stale Phase 7 speed caveat.
- `.planning/STATE.md` - Adds Phase 8 completion and current live-call TTS default decisions.
- `.planning/ROADMAP.md` - Adds Phase 8 final outcome and live evidence proof fields.

## Decisions Made

- VoxCPM2 is now the preferred/default live-call TTS engine because Phase 8 live streaming playback evidence beat F5 by same-run warm median first-audio time.
- F5 remains available as fallback/comparator, not as the current speed-based default.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `gsd-sdk query state.advance-plan`, `state.update-progress`, `state.record-metric`, and `state.add-decision` could not parse this project's current STATE section names. The session handler updated top-level counters/session fields, and the required Phase 8 decision/status lines were already applied directly in `STATE.md`.
- `gsd-sdk query requirements.mark-complete P8-R5` reported `P8-R5` as not found in `.planning/REQUIREMENTS.md`; no requirements file change was made.

## Authentication Gates

None.

## Known Stubs

None. Stub-pattern scan only matched pre-existing policy text in `STATE.md`, not stubs introduced by this plan.

## Verification

- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --decision-ready` - PASS
- `rg -n "TTS live-call default \\(Phase 8\\).*voxcpm2|results/voxcpm2-live-streaming-call-flow.json" .planning/PROJECT.md` - PASS
- `rg -n "Phase 08 completed on 2026-05-11|TTS live-call default: voxcpm2" .planning/STATE.md` - PASS
- `rg -n "Final outcome.*promoted_for_live_call_default|streaming_used=true|whole_wav_fallback_used=false" .planning/ROADMAP.md` - PASS
- `rg -n "TTS live-call default|promoted_for_live_call_default|preferred_call_tts_engine" .planning/PROJECT.md .planning/STATE.md .planning/ROADMAP.md .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-PROMOTION-DECISION.md .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-decision.json` - PASS
- `git diff --check` - PASS
- `gsd-sdk query roadmap.update-plan-progress 08` - PASS
- `gsd-sdk query state.record-session --stopped-at "Completed 08-06-PLAN.md" --resume-file "None"` - PASS

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 8 is complete. The project is ready for Phase 8 verification/closeout with durable decision artifacts and project docs aligned on VoxCPM2 as the preferred/default live-call TTS engine.

## Self-Check: PASSED

- Summary, promotion decision, and decision JSON files exist.
- Task commits `5766306` and `c4513d3` exist in git history.
- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --decision-ready` still passes.

---
*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Completed: 2026-05-11*
