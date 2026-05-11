---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 07
subsystem: ui
tags: [web-ui, voice-lab, voxcpm2, svelte, vitest, playwright]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: "Plan 07-02 RED client contracts and Plan 07-06 Web UI server VoxCPM2 metadata support"
provides:
  - "Client fallback roster and labels for VoxCPM2 candidate metadata"
  - "Typed Voice Lab metadata payloads for metadata.engine_settings.voxcpm2"
  - "Conditional VoxCPM2 mode/style controls with bounded browser inputs"
affects: [voice-lab, voice-metadata, voxcpm2-runtime, phase-07]

tech-stack:
  added: []
  patterns:
    - "Engine-specific controls render only when their engine is selected"
    - "Voice-level VoxCPM2 settings remain under metadata.engine_settings.voxcpm2"

key-files:
  created:
    - "web-ui/client/src/lib/components/voice/VoxCpm2Controls.svelte"
    - ".planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-07-SUMMARY.md"
  modified:
    - "web-ui/client/src/lib/api/types.ts"
    - "web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte"
    - "web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte"
    - "web-ui/client/src/routes/voice-lab/+page.svelte"
    - "web-ui/client/tests/unit/voice-lab.test.ts"
    - "web-ui/client/tests/e2e/voice-lab.spec.ts"

key-decisions:
  - "VoxCPM2 client metadata remains opt-in under metadata.engine_settings.voxcpm2 and is only sent on preview when VoxCPM2 is selected."
  - "Voice Lab keeps VoxCPM2 settings in route state across engine switches, while non-VoxCPM2 preview payloads omit VoxCPM2 metadata."
  - "VoxCPM2 client defaults mirror the server defaults from Plan 07-06: reference_only, cfg 2.0, 10 timesteps, normalize false, denoise false."

patterns-established:
  - "Dedicated engine settings component bound to route-owned engineSettings state."
  - "Fallback roster entries include fixed caveats instead of raw backend error text."

requirements-completed: [REQ-20, REQ-21, REQ-22, REQ-23, REQ-80]

duration: 12min
completed: 2026-05-11
---

# Phase 07 Plan 07: VoxCPM2 Voice Lab Client Summary

**VoxCPM2 candidate roster metadata and conditional Voice Lab controls wired to typed voice metadata payloads**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-11T03:00:51Z
- **Completed:** 2026-05-11T03:12:54Z
- **Tasks:** 2
- **Files modified:** 7 source/test files plus this summary

## Accomplishments

- Added VoxCPM2 to the client engine union, fallback Voice Lab roster, picker caveats, and voice-assignment labels.
- Added typed `VoxCpm2EngineSettings` metadata support for saved and preview voice payloads.
- Created `VoxCpm2Controls.svelte` with reference-only/transcript-guided modes, style prompt, bounded CFG/timesteps inputs, and Normalize/Denoise toggles.
- Wired Voice Lab to render VoxCPM2 controls only for `selectedEngine === 'voxcpm2'`, preserve settings across engine switches, and omit VoxCPM2 metadata from non-VoxCPM2 preview payloads.
- Updated unit and browser coverage for the dedicated controls component and explicit VoxCPM2 save payload behavior.

## Task Commits

1. **Task 1: Add VoxCPM2 fallback roster labels and typed payloads** - `78f2718` (test), `92408d6` (feat)
2. **Task 2: Add and wire conditional VoxCPM2 controls** - `70ceed2` (test), `12c3da3` (test), `7d93d11` (feat)

**Plan metadata:** pending final docs commit

## Files Created/Modified

- `web-ui/client/src/lib/components/voice/VoxCpm2Controls.svelte` - New conditional VoxCPM2 control panel.
- `web-ui/client/src/routes/voice-lab/+page.svelte` - Added VoxCPM2 fallback roster entry, route-owned settings state, conditional rendering, and save/preview metadata wiring.
- `web-ui/client/src/lib/api/types.ts` - Added `voxcpm2` to `TtsEngineId` and typed VoxCPM2 voice metadata.
- `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` - Added VoxCPM2 fallback caveats and candidate copy.
- `web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte` - Added VoxCPM2 label fallback.
- `web-ui/client/tests/unit/voice-lab.test.ts` - Added typed-payload and dedicated controls source contracts.
- `web-ui/client/tests/e2e/voice-lab.spec.ts` - Added explicit VoxCPM2 control interactions for normalize and speech speed.

## Decisions Made

- VoxCPM2 is visible in client fallback metadata with `Candidate`, `48 kHz`, and `RTX 3060 gate pending` caveats.
- VoxCPM2 settings are route-owned and preserved even when the selected engine changes.
- Preview payloads include VoxCPM2 metadata only when VoxCPM2 is the active engine; saved metadata carries the active engine's settings.

## Verification

- `npm --prefix web-ui/client run test:unit -- voice-lab` - passed, 13 tests.
- `npm --prefix web-ui/client run test:e2e -- voice-lab` - passed, 14 Playwright tests.
- `git diff --check` - passed.
- `rg -n "voxcpm2|VoxCPM2|RTX 3060 gate pending" web-ui/client/src/lib web-ui/client/src/routes/voice-lab/+page.svelte` - returned matches in fallback/types/component paths.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed VoxCPM2 browser test setup for explicit controls**
- **Found during:** Task 2 (Add and wire conditional VoxCPM2 controls)
- **Issue:** The browser test expected `normalize: true` and `speech_speed: 0.75` in the saved metadata without driving those UI controls.
- **Fix:** Updated the E2E flow to check `Normalize` and set `Speech speed` before asserting the save payload.
- **Files modified:** `web-ui/client/tests/e2e/voice-lab.spec.ts`
- **Verification:** `npm --prefix web-ui/client run test:e2e -- voice-lab` passed.
- **Committed in:** `12c3da3`, `7d93d11`

---

**Total deviations:** 1 auto-fixed bug
**Impact on plan:** The fix kept the browser contract aligned with server defaults and did not expand runtime scope.

## Known Stubs

None. Stub scan found only fixed UI fallback copy for unavailable engines, not placeholder data.

## Threat Flags

None. The changed files only add browser UI state and typed metadata wiring for trust boundaries already identified in the plan.

## Issues Encountered

- Task 1's full unit target still had expected Task 2 RED failures until the conditional controls were implemented. Focused Task 1 unit assertions passed before the Task 1 feat commit; the full unit target passed after Task 2.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Voice Lab can now expose VoxCPM2 as a candidate engine and save its browser-selected metadata. Later Phase 07 runtime and call-flow plans can consume the existing `metadata.engine_settings.voxcpm2` shape without adding browser-visible VoxCPM2-specific routes.

## Self-Check: PASSED

- Found summary file: `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-07-SUMMARY.md`
- Found created component: `web-ui/client/src/lib/components/voice/VoxCpm2Controls.svelte`
- Found route wiring: `web-ui/client/src/routes/voice-lab/+page.svelte`
- Found task commit: `78f2718`
- Found task commit: `92408d6`
- Found task commit: `70ceed2`
- Found task commit: `12c3da3`
- Found task commit: `7d93d11`

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
