---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 06
subsystem: web-ui-server
tags: [web-ui, voices-api, voice-library, voxcpm2, pytest]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: "Plan 07-02 Web UI RED contracts and Plan 07-05 backend VoxCPM2 synthesis contract"
provides:
  - "Durable bounded metadata.engine_settings.voxcpm2 persistence"
  - "Preview and Voice Library test-play reuse of saved VoxCPM2 mode/style settings"
  - "Flat voxcpm2_* synthesis payload bridge to the existing AI backend API"
affects: [voice-lab, voice-library, voices-api, voxcpm2-call-flow, phase-07]

tech-stack:
  added: []
  patterns:
    - "Engine-specific voice settings stay under metadata.engine_settings.<engine>"
    - "Web UI server normalizes VoxCPM2 settings before durable storage or backend forwarding"

key-files:
  created:
    - ".planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-06-SUMMARY.md"
  modified:
    - "web-ui/server/app/domain/voice_service.py"
    - "web-ui/server/app/api/voices.py"
    - "web-ui/server/tests/test_voices.py"

key-decisions:
  - "VoxCPM2 Web UI metadata defaults to reference_only, empty style_prompt, cfg_value 2.0, inference_timesteps 10, normalize false, and denoise false."
  - "VoxCPM2 settings are forwarded to the AI backend only when the target engine is voxcpm2."

patterns-established:
  - "Voice metadata patches merge engine_settings instead of replacing unrelated engine-specific settings."
  - "Blank transcript with transcript-guided VoxCPM2 preference is downgraded to reference_only with warning code voxcpm2_reference_only_without_transcript."

requirements-completed: [REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-80]

duration: 6min
completed: 2026-05-11
---

# Phase 07 Plan 06: VoxCPM2 Web UI Server Metadata Summary

**Durable VoxCPM2 voice metadata normalization with preview/test-play reuse through the existing AI backend synthesis bridge**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-11T02:51:09Z
- **Completed:** 2026-05-11T02:56:38Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added bounded server-side normalization for `metadata.engine_settings.voxcpm2`, including enum, text length, numeric range, and boolean checks.
- Preserved VoxCPM2 metadata through voice saves and metadata patches while keeping rename/delete semantics unchanged.
- Forwarded VoxCPM2 settings as the six flat `voxcpm2_*` AI backend payload fields only for the `voxcpm2` engine.
- Reused saved VoxCPM2 settings for Voice Library test-play and preserved missing-transcript warning propagation.

## Task Commits

1. **Task 1: Normalize and persist VoxCPM2 engine settings** - `0aac272` (feat)
2. **Task 2 RED: Add synthesis payload contracts** - `98d47e0` (test)
3. **Task 2 GREEN: Forward VoxCPM2 settings for preview and test-play** - `087b3c2` (feat)

_Note: Task 1 implemented the already-committed Plan 07-02 RED contracts. Task 2 added an additional RED commit for the flat AI-backend payload bridge before implementation._

## Files Created/Modified

- `web-ui/server/app/domain/voice_service.py` - Adds VoxCPM2 metadata defaults, validation, patch merge behavior, preview/test-play settings selection, and missing-transcript warning handling.
- `web-ui/server/app/api/voices.py` - Allows metadata on preview/patch requests, maps metadata validation to public 422 responses, and flattens VoxCPM2 options into synthesis payloads.
- `web-ui/server/tests/test_voices.py` - Adds direct synthesis payload and backend warning propagation contracts.

## Decisions Made

- VoxCPM2 `normalize` and `denoise` default to `false` at the Web UI voice metadata layer per Plan 07-06, even though backend runtime requests have their own defaults.
- Non-VoxCPM2 synthesis payloads omit every `voxcpm2_*` field, even when saved voice metadata contains VoxCPM2 settings for later switch-back.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q` - passed, `22 passed`.
- `git diff --check` - passed.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. Stub scan only found normal test initializers/assertions and intentional default empty containers used by metadata normalization.

## Threat Flags

None. The changed files implement mitigations for the plan's Browser -> Web UI voice API and Web UI server -> AI backend boundaries without adding new endpoints, schema tables, file access patterns, or auth surfaces.

## Issues Encountered

The pre-existing RED contracts already covered Task 1 persistence behavior. Task 2 needed additional direct payload coverage to prove the exact flat `voxcpm2_*` bridge keys; those tests were added before the GREEN implementation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 07-06 is ready for downstream client/call-flow implementation. The Web UI server now owns bounded saved VoxCPM2 metadata and forwards the same normalized settings through preview and Voice Library test-play without changing non-VoxCPM2 behavior.

## Self-Check: PASSED

- Found summary file: `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-06-SUMMARY.md`
- Found task commit: `0aac272`
- Found task commit: `98d47e0`
- Found task commit: `087b3c2`

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
