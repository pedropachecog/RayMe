---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
plan: 04
subsystem: evidence
tags: [voxcpm2, streaming, tts, webrtc, evidence]

# Dependency graph
requires:
  - phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
    provides: Internal VoxCPM2 streaming chunk adapter contract from plan 08-01
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Phase 7 evidence runner/verifier patterns and F5/VoxCPM2 call-flow baseline
provides:
  - Repeated warm live call-flow evidence runner for F5 versus VoxCPM2
  - Strict Phase 8 evidence verifier for streaming proof fields, fallback rejection, median comparison, and decision readiness
  - Result artifact inventory for Phase 8 live evidence
affects: [phase-08-live-evidence, voxcpm2-decision-writeback, omen-evidence]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Stdlib unittest RED gates for planning evidence scripts
    - Synthetic verifier contract mode that validates schema without live runtime files
    - Evidence TTFA sourced from backend event metrics rather than HTTP completion timing

key-files:
  created:
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/README.md
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_call_flow_runner.py
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_verify_evidence.py
  modified: []

key-decisions:
  - "Phase 8 call-flow evidence measures TTFA from ai_audio_started_event.tts_playback.ai_audio_started_ms, never HTTP request duration."
  - "The verifier requires immediate and final playback metric carriers to stay separate so whole-WAV fallback cannot satisfy streaming evidence."
  - "Decision-ready verification requires live call-flow evidence plus a separate voxcpm2-decision.json artifact."

patterns-established:
  - "Evidence scripts expose contract-only/synthetic verification where live OMEN artifacts do not yet exist."
  - "VoxCPM2 streaming success requires true streaming flags, false fallback flags, final chunk/playback timing, and median TTFA lower than F5."

requirements-completed: [P8-R2, P8-R5]

# Metrics
duration: 11 min
completed: 2026-05-11
---

# Phase 08 Plan 04: Evidence Tooling Summary

**Repeated warm live call-flow tooling with strict VoxCPM2 streaming proof and median F5 comparison gates**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-11T14:40:55Z
- **Completed:** 2026-05-11T14:51:28Z
- **Tasks:** 2 completed
- **Files modified:** 5

## Accomplishments

- Added a Phase 8 live call-flow evidence runner that creates WebRTC offers, runs one warm-up plus repeated measured speak calls for `f5` then `voxcpm2`, and writes `results/voxcpm2-live-streaming-call-flow.json`.
- Added a strict verifier that rejects missing streaming proof fields, whole-WAV fallback, raw runtime leaks, final-only fields copied into the immediate event carrier, and VoxCPM2 medians that do not beat F5.
- Added focused RED/GREEN contract tests for both evidence scripts and documented the expected Phase 8 result artifact inventory.

## Task Commits

Each TDD task was committed atomically:

1. **Task 1 RED: Call-flow runner contract test** - `a136470` (test)
2. **Task 1 GREEN: Live call-flow evidence runner** - `cf40e70` (feat)
3. **Task 2 RED: Evidence verifier contract tests** - `6e4cb7e` (test)
4. **Task 2 GREEN: Streaming evidence verifier** - `160cf55` (feat)

## Files Created/Modified

- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py` - Runs repeated warm live `/webrtc/offer` and `/webrtc/sessions/{session_id}/speak` samples and summarizes median TTFA.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py` - Enforces Phase 8 evidence schema, streaming proof, fallback rejection, median comparison, raw leak checks, and decision-ready fields.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/README.md` - Lists required Phase 8 result artifacts.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_call_flow_runner.py` - Locks runner extraction and summary behavior with fake RayMe API/WebRTC calls.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_verify_evidence.py` - Locks verifier acceptance/rejection behavior for synthetic call-flow evidence.

## Verification

- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --contract-only` - PASS
- `python3 -m py_compile .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py` - PASS
- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_call_flow_runner.py` - PASS
- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_verify_evidence.py` - PASS
- `git diff --check` - PASS
- Plan acceptance `rg` checks for runner, verifier, and results README required strings - PASS

## Decisions Made

- Used stdlib-only tests for the planning evidence scripts because root Python does not provide `pytest`, and the scripts do not need project test dependencies to validate their contract.
- Kept aiortc imports lazy inside the runner's offer creation helper so `py_compile` and unit contracts can run outside the AI-backend runtime environment.
- Made `--contract-only` validate a synthetic payload instead of reading live artifacts, preserving Wave 1 automation before OMEN live evidence exists.

## Deviations from Plan

None - plan executed as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope change.

## Issues Encountered

- During Task 2 GREEN, the verifier initially reported the summary boolean failure before the underlying slower-than-F5 median failure. The check order was adjusted before commit so failing medians produce the clearer evidence-gate error.
- The GSD state decision/metric handlers skipped this project's `STATE.md` because it uses `Current Decisions` and no `Performance Metrics` section. Roadmap/session updates used the SDK; the missing Phase 08-04 status and decision entries were applied directly to `STATE.md`.

## Authentication Gates

None.

## Known Stubs

None. Stub-pattern scan only matched local list initializations in executable test/tooling code.

## User Setup Required

None - no external service configuration required by this plan. Live OMEN execution remains a later plan and must use `scripts/deploy-omen.sh`.

## TDD Gate Compliance

- Task 1 RED commit present: `a136470`
- Task 1 GREEN commit present after RED: `cf40e70`
- Task 2 RED commit present: `6e4cb7e`
- Task 2 GREEN commit present after RED: `160cf55`
- REFACTOR commits: not needed

## Next Phase Readiness

Plan 08-05 can run the Phase 8 evidence runner on OMEN after canonical deployment and then use `08-verify-evidence.py --call-flow-only` to gate live call-flow evidence. Plan 08-06 can use `--decision-ready` once `voxcpm2-decision.json` exists.

## Self-Check: PASSED

- Summary file exists.
- Key created files exist.
- Task commits `a136470`, `cf40e70`, `6e4cb7e`, and `160cf55` exist in git history.

---
*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Completed: 2026-05-11*
