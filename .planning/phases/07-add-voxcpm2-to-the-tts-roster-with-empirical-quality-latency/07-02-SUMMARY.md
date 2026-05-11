---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 02
subsystem: testing
tags: [web-ui, voice-lab, voxcpm2, pytest, vitest, playwright]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: "Phase 07 context and Plan 07-01 backend VoxCPM2 RED contracts"
provides:
  - "Web UI server RED contracts for durable VoxCPM2 voice metadata and synthesis payloads"
  - "Client unit and browser RED contracts for VoxCPM2 fallback roster and conditional Voice Lab controls"
  - "Expected failing verification evidence for Plan 07-02 implementation follow-up"
affects: [voice-lab, voices-api, voxcpm2-runtime, phase-07]

tech-stack:
  added: []
  patterns:
    - "RED contract tests before implementation"
    - "VoxCPM2-specific metadata stored under metadata.engine_settings.voxcpm2"

key-files:
  created:
    - ".planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-02-SUMMARY.md"
  modified:
    - "web-ui/server/tests/test_voices.py"
    - "web-ui/client/tests/unit/voice-lab.test.ts"
    - "web-ui/client/tests/e2e/voice-lab.spec.ts"

key-decisions:
  - "VoxCPM2 Voice Lab contracts use engine id voxcpm2 and persist settings under metadata.engine_settings.voxcpm2."
  - "Reference-only fallback without transcript is expected to emit warning code voxcpm2_reference_only_without_transcript."

patterns-established:
  - "Server preview and test-play contracts assert engine-scoped VoxCPM2 settings are forwarded only for voxcpm2."
  - "Client contracts require VoxCPM2 controls to be conditional on selectedEngine === 'voxcpm2'."

requirements-completed: [REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-80]

duration: 6min
completed: 2026-05-11
---

# Phase 07 Plan 02: Web UI VoxCPM2 RED Contracts Summary

**Executable Web UI contracts for durable VoxCPM2 voice metadata, conditional controls, fallback roster visibility, and save/preview/test-play payload behavior**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-11T02:09:27Z
- **Completed:** 2026-05-11T02:15:35Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added server RED tests for `metadata.engine_settings.voxcpm2` persistence, update behavior, bounded style/control fields, reference-only warning behavior, and ignoring VoxCPM2 settings for non-VoxCPM2 engines.
- Added client unit RED tests for the `voxcpm2` fallback roster entry, conditional controls, missing-transcript guidance, numeric bounds, and engine-switch metadata preservation.
- Added desktop/mobile Playwright RED coverage requiring the browser Voice Lab to render VoxCPM2 from backend metadata, hide VoxCPM2 controls while F5 is selected, show them after selecting VoxCPM2, and save `metadata.engine_settings.voxcpm2.cloning_mode`.

## Task Commits

1. **Task 1: Add server voice metadata RED tests** - `ce14fbe` (test)
2. **Task 2: Add client conditional-control RED tests** - `e80bc2e` (test)

## Files Created/Modified

- `web-ui/server/tests/test_voices.py` - Added VoxCPM2 metadata, preview payload, warning, bounds, and non-VoxCPM2 ignore contracts.
- `web-ui/client/tests/unit/voice-lab.test.ts` - Added VoxCPM2 source/API contracts for fallback metadata, controls, bounds, and save payload shape.
- `web-ui/client/tests/e2e/voice-lab.spec.ts` - Added browser-level conditional-control and save-payload coverage with mocked backend VoxCPM2 metadata.

## Decisions Made

- VoxCPM2-specific Voice Lab state is contracted under `metadata.engine_settings.voxcpm2`.
- `voxcpm2_reference_only_without_transcript` is the warning code for transcript-guided preference with blank transcript.
- The fallback roster copy is locked to `VoxCPM2`, `Candidate`, `48 kHz`, and `RTX 3060 gate pending`.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q` - expected RED failure: 3 new VoxCPM2 tests fail; 17 existing tests pass.
  - Missing behavior: metadata patch/update support, preview metadata acceptance/forwarding, and explicit empty `engine_settings`/`warnings` payload for non-VoxCPM2 test-play.
- `npm --prefix web-ui/client run test:unit -- voice-lab` - expected RED failure: 3 tests fail.
  - Missing behavior: VoxCPM2 fallback/source copy and route-owned `engine_settings.voxcpm2` preservation.
- `npm --prefix web-ui/client run test:e2e -- voice-lab` - expected RED failure: 2 failures across desktop/mobile for the new browser contract; 12 existing specs pass.
  - Missing behavior: mocked backend VoxCPM2 metadata is not rendered as a selectable engine.
- `git diff --check` passed for all modified test files.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. Stub scan only found normal test initializers and assertions in touched test files.

## Threat Flags

None. The changed files add tests for the trust boundaries already declared in the plan threat model and introduce no new runtime endpoint, file access, auth, or schema surface.

## Issues Encountered

None beyond the expected RED failures.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 07-02 is ready for implementation follow-up. The next implementation plan should make the server and client behavior satisfy these failing contracts without weakening existing Voice Lab behavior for F5, XTTS, Qwen3, LuxTTS, Chatterbox, or TADA.

## Self-Check: PASSED

- Found summary file: `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-02-SUMMARY.md`
- Found task commit: `ce14fbe`
- Found task commit: `e80bc2e`

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
