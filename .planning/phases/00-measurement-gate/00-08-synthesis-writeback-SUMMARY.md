---
phase: 00-measurement-gate
plan: "08"
subsystem: docs
tags: [phase0, writeback, decisions, project-state]
requires:
  - phase: "00"
    provides: "All Phase 0 result JSONs, including the runtime matrix and VRAM soak artifacts"
provides:
  - "Frozen Phase 0 decisions in KEY_DECISIONS.md"
  - "Machine-readable phase0_summary.json roll-up"
  - "Updated PROJECT.md and STATE.md pointing the project at Phase 1"
affects: [project-state, roadmap-readiness, phase-01]
tech-stack:
  added: []
  patterns: [measurement-driven writeback, frozen-decision section in project docs]
key-files:
  created:
    - .planning/phases/00-measurement-gate/KEY_DECISIONS.md
    - .planning/phases/00-measurement-gate/results/phase0_summary.json
    - .planning/phases/00-measurement-gate/00-08-synthesis-writeback-SUMMARY.md
  modified:
    - .planning/PROJECT.md
    - .planning/STATE.md
    - .planning/phases/00-measurement-gate/00-VALIDATION.md
key-decisions:
  - "Freeze mkcert as the LAN HTTPS strategy for v1."
  - "Freeze distil-large-v3 int8_float16 as the STT default."
  - "Freeze F5-TTS as the v1 TTS default while keeping XTTS v2 as the second v1 engine."
  - "Exclude Qwen3-TTS from the v1 roster because its acceptance gate failed and FA2 is not installed on Windows."
patterns-established:
  - "Cross-runtime TTS claims must cite results/tts_runtime_matrix.json."
  - "Long-form TTS claims must use the shared chunk planner once implemented; raw whole-generation fallback rows are not final comparisons."
  - "Phase-freezing writeback should be driven from result artifacts, not from remembered console output."
requirements-completed: []
duration: 1 min
completed: 2026-04-23
---

# Phase 00 Plan 08: Synthesis + Writeback Summary

**Consolidated Phase 0 into a frozen decision set and wrote the results back into the project state so Phase 1 can start from measured defaults**

## Performance

- **Duration:** 1 min
- **Started:** 2026-04-23T06:02:49Z
- **Completed:** 2026-04-23T06:03:24Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Built `results/phase0_summary.json` as the machine-readable roll-up for every Phase 0 result artifact.
- Wrote `KEY_DECISIONS.md` with the human-readable synthesis, including the runtime matrix and the completed 30-minute soak results.
- Added a frozen `Phase 0 Key Decisions` section to `PROJECT.md`.
- Replaced the stale minimal `STATE.md` with a Phase 0 complete snapshot that points to Phase 1.
- Refreshed the validation sheet so the completed 05/08 work is no longer shown as pending.

## Builder Decision Handling

- Applied the plan as `approve-all`. No manual overrides were introduced because the measured artifacts were internally consistent and the user explicitly asked to run the writeback plan.

## Decisions Frozen

- HTTPS strategy: `mkcert`
- STT default: `distil-large-v3` (`int8_float16`)
- TTS v1 default: `f5`
- TTS v1 roster: `F5-TTS`, `XTTS v2`
- Qwen3-TTS disposition: rejected for v1
- FA2 / Qwen 1.7B: not installed, ineligible for v1

## Cascades Triggered

- Qwen3 gate rejected: Voice Lab and Settings should ship with a two-engine roster in v1.
- FA2 install failed: native-Windows Qwen remains an eager-only baseline and 1.7B stays out of scope.

## Next Phase Readiness

- Phase 0 is now frozen and Phase 1 should start from the measured defaults in `PROJECT.md`, `STATE.md`, and `KEY_DECISIONS.md`.

## Post-Writeback Addendum: TTS Chunking

- 2026-04-23 follow-up found that XTTS long-form native streaming hit the `inference_stream` 400-token cap and fell back to full-render timing.
- Future long-form TTS benchmarks and runtime code must implement shared, engine-agnostic chunking before making final engine comparisons.
- The chunk planner must enforce model-specific token/character caps, prefer sentence boundaries, avoid tiny fragments, measure first-chunk TTFA, total stitched playback time, inter-chunk gaps, and emit stitched WAVs for listening.

---
*Phase: 00-measurement-gate*
*Completed: 2026-04-23*
