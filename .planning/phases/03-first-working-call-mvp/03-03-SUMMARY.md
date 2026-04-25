---
phase: 03-first-working-call-mvp
plan: "03"
subsystem: testing
tags: [sveltekit, vitest, playwright, webrtc, call-ui]
requires:
  - phase: 03-first-working-call-mvp
    provides: "Phase 03 plans 01-02 established AI backend and Web UI server call contracts."
provides:
  - "RED client unit contracts for call FSM, interruption, hangup, server mute, audio unlock, device fallback copy, and RMS metering."
  - "RED Playwright browser contracts for call entry, permissions, toolbar, visualizer, summary rows, mobile layout, and opt-in live LAN call acceptance."
affects: [phase-03-call-client, call-ui, browser-media, android-acceptance]
tech-stack:
  added: []
  patterns: ["Vitest RED tests import future call modules directly", "Playwright call specs mock same-origin local call routes but keep live LAN call spec unmocked"]
key-files:
  created:
    - web-ui/client/tests/unit/call-state.test.ts
    - web-ui/client/tests/unit/call-audio.test.ts
    - web-ui/client/tests/e2e/call-start.spec.ts
    - web-ui/client/tests/e2e/call-toolbar.spec.ts
    - web-ui/client/tests/e2e/call-permissions.spec.ts
    - web-ui/client/tests/e2e/call-visualizer.spec.ts
    - web-ui/client/tests/e2e/call-summary.spec.ts
    - web-ui/client/tests/e2e/call-mobile.spec.ts
    - web-ui/client/tests/e2e/live-call.spec.ts
  modified: []
key-decisions:
  - "Client call implementation remains RED-gated by browser-facing tests before building the Svelte call surface."
  - "Live call acceptance is opt-in through RAYME_ENABLE_LIVE_E2E and avoids mocked call, WebRTC, or media routes."
patterns-established:
  - "Local deterministic call acceptance specs mock RayMe-owned same-origin routes only."
  - "Mobile call parity is enforced by a mobile-chromium Playwright project spec."
requirements-completed: [REQ-40, REQ-47, REQ-48, REQ-49, REQ-50, REQ-A0, REQ-A1]
duration: 10m17s
completed: 2026-04-25T20:19:04Z
---

# Phase 03 Plan 03: Client Call RED Test Contracts Summary

**Client call FSM, audio helper, desktop/mobile browser, and opt-in live LAN acceptance contracts are now RED before implementation.**

## Performance

- **Duration:** 10m17s
- **Started:** 2026-04-25T20:08:47Z
- **Completed:** 2026-04-25T20:19:04Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Added Vitest contracts for the future call state machine, including connecting/listening/thinking/speaking/interrupted/ended/failed states, button interruption, end-call cleanup, and server mute independence.
- Added Vitest contracts for call audio unlock, unsupported output picker copy, and separate listening/speaking RMS metering.
- Added Playwright contracts for call start, toolbar, permission recovery, visualizer state, chronological summary rows, mobile control layout, and live OMEN-PC call acceptance.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add RED client unit tests for call FSM and audio helpers** - `334e0f1` (test)
2. **Task 2: Add RED Playwright call acceptance specs** - `5c6a890` (test)

## Files Created/Modified

- `web-ui/client/tests/unit/call-state.test.ts` - Future call FSM contract for state transitions, interrupt cancellation, hangup cleanup, and server mute behavior.
- `web-ui/client/tests/unit/call-audio.test.ts` - Future call audio helper contract for AudioContext unlock, output picker copy, and RMS metering.
- `web-ui/client/tests/e2e/call-start.spec.ts` - Thread-header and character-card Start Call acceptance paths.
- `web-ui/client/tests/e2e/call-toolbar.spec.ts` - Mute, Unmute, Interrupt, End Call, and unsupported device picker copy acceptance.
- `web-ui/client/tests/e2e/call-permissions.spec.ts` - Microphone-denied recovery copy and retry action acceptance.
- `web-ui/client/tests/e2e/call-visualizer.spec.ts` - Listening, Thinking, and Speaking visualizer state acceptance.
- `web-ui/client/tests/e2e/call-summary.spec.ts` - Chronological `call_start`, `user_speech`, `ai_speech`, and `call_end` row acceptance.
- `web-ui/client/tests/e2e/call-mobile.spec.ts` - Mobile Chromium call controls and bottom-navigation non-overlap contract.
- `web-ui/client/tests/e2e/live-call.spec.ts` - Opt-in live LAN call acceptance gated by `RAYME_ENABLE_LIVE_E2E`, `RAYME_LIVE_WEB_URL`, and `RAYME_LIVE_AI_HEALTH_URL`.

## Decisions Made

- Kept local Playwright specs deterministic by mocking same-origin RayMe call/WebRTC routes where local implementation is not yet present.
- Kept the live call spec unmocked for `/api/calls/*`, `/webrtc/*`, and media paths so OMEN-PC acceptance can validate the real LAN call route.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The first character-card Playwright draft visited `/`, which does not render `CharacterCard`; it was corrected to `/gallery` before committing Task 2.
- The combined desktop-and-mobile verification command stopped after the expected desktop RED failure, so the mobile target was run separately.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run tests/unit/call-state.test.ts tests/unit/call-audio.test.ts` - expected RED failure: Vitest could not resolve future `src/lib/call/store.svelte` and `src/lib/call/audio` implementation modules.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts tests/e2e/call-toolbar.spec.ts tests/e2e/call-permissions.spec.ts tests/e2e/call-visualizer.spec.ts tests/e2e/call-summary.spec.ts --project=desktop-chromium` - expected RED failure: desktop specs reached browser execution and timed out on missing `Start call` / `Start Call` UI.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-mobile.spec.ts --project=mobile-chromium` - expected RED failure: mobile spec reached browser execution and timed out on missing `Start call` UI.

## User Setup Required

None - no external service configuration required for local RED contracts. The live call spec remains opt-in through environment variables.

## Next Phase Readiness

Client implementation plans can now build `src/lib/call/store.svelte.ts`, `src/lib/call/audio.ts`, and the browser call surface against explicit RED contracts. Expected failures are missing implementation, not malformed tests.

## Self-Check: PASSED

- Confirmed all 9 created test files and this summary file exist.
- Confirmed task commits `334e0f1` and `5c6a890` are present in git history.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
