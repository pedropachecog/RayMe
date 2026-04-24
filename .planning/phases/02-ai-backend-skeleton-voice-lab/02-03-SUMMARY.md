---
phase: 02-ai-backend-skeleton-voice-lab
plan: "03"
subsystem: testing
tags: [vitest, playwright, sveltekit, voice-lab, settings, ui-contracts]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: Wave 0 server and AI backend RED contracts from plans 02-01 and 02-02
provides:
  - Client RED contracts for Voice Lab, Voice Library, Gallery voice states, Settings Phase 2 controls, and top-level navigation
  - Local Playwright browser contract for upload, transcript edit, optional preview, save, library actions, force delete, and `Voice unavailable`
  - Opt-in live OMEN-PC Voice Lab acceptance spec gated by live LAN environment variables
affects: [02-10, 02-12, 02-13, 02-14, 02-15, 02-18]

tech-stack:
  added: []
  patterns: [Wave 0 RED client contracts, defensive source-contract tests, RayMe-only Playwright request guards, opt-in live E2E gating]

key-files:
  created:
    - web-ui/client/tests/unit/voice-lab.test.ts
    - web-ui/client/tests/e2e/voice-lab.spec.ts
    - web-ui/client/tests/e2e/live-voice-lab.spec.ts
  modified:
    - web-ui/client/tests/unit/app-shell.test.ts
    - web-ui/client/tests/unit/settings.test.ts

key-decisions:
  - "Client Voice Lab validation remains RED-only in Wave 0; later Phase 2 UI plans must satisfy these contracts."
  - "Live Voice Lab acceptance is excluded from default Playwright runs and only activates with explicit LAN environment variables."

patterns-established:
  - "Missing future Svelte sources are read defensively in Vitest so RED contracts collect cleanly before implementation."
  - "Voice Lab browser tests assert RayMe-owned `/api/voices` flows and block direct provider/backend browser calls with `expectRayMeApiRequest`."

requirements-completed: [REQ-05, REQ-15, REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-80, REQ-90]

duration: 8 min
completed: 2026-04-24
---

# Phase 02 Plan 03: Client Voice Lab Validation Contracts Summary

**RED Vitest and Playwright contracts for the Phase 2 Voice Lab, Voice Library, Settings extensions, navigation, and live OMEN-PC acceptance path.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-24T23:18:45Z
- **Completed:** 2026-04-24T23:26:55Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `voice-lab.test.ts` source contracts requiring Voice Lab/Library labels, all six TTS engines, caveat metadata, optional preview save behavior, preserved preview-failure state, and `Voice unavailable`.
- Updated app shell and Settings unit contracts for four top-level destinations including `/voice-lab`, save-audio toggles, VAD placeholders, and resident TTS status.
- Added local Playwright coverage for upload, transcript auto-fill/edit, six-engine picker, preview failure, save without preview, library rename/delete/test-play, Gallery voice badges, `force=true`, and RayMe-only request boundaries.
- Added opt-in live OMEN-PC Voice Lab acceptance gated by `RAYME_ENABLE_LIVE_E2E`, `RAYME_LIVE_WEB_URL`, and `RAYME_LIVE_AI_HEALTH_URL`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Voice Lab unit/source contracts** - `9119612` (test)
2. **Task 2: Add Voice Lab local and live Playwright contracts** - `7bb21fc` (test)

## Files Created/Modified

- `web-ui/client/tests/unit/voice-lab.test.ts` - New defensive source-contract suite for future Voice Lab UI and API wrappers.
- `web-ui/client/tests/unit/app-shell.test.ts` - Updated top-level navigation contract from Phase 1 to Phase 2.
- `web-ui/client/tests/unit/settings.test.ts` - Updated Settings contract for Phase 2 audio/VAD/model-residency controls and sanitized status copy.
- `web-ui/client/tests/e2e/voice-lab.spec.ts` - New local browser contract for Voice Lab, Voice Library, Gallery badge states, and `/api/voices` request semantics.
- `web-ui/client/tests/e2e/live-voice-lab.spec.ts` - New opt-in live LAN acceptance path for `https://192.168.1.199:8443/voice-lab` and `https://192.168.1.199:9443/health`.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run tests/unit/voice-lab.test.ts tests/unit/app-shell.test.ts tests/unit/settings.test.ts` - RED as expected: 8 failures, 4 passes. Failures are missing `/voice-lab` navigation/source files and missing Phase 2 Settings/Voice Lab UI implementation.
- `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts` - RED as expected: 2 failures, both desktop/mobile Playwright projects reached `/voice-lab` and failed on missing `Voice Lab` heading after current app returned 404.
- `npm --prefix web-ui/client run test:e2e -- --list` - PASS for live gating: default test list includes `voice-lab.spec.ts` but does not include `live-voice-lab.spec.ts`.
- Plan-level command `npm --prefix web-ui/client run test:unit -- --run tests/unit/voice-lab.test.ts tests/unit/app-shell.test.ts tests/unit/settings.test.ts && npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts` - RED as expected; the unit command failed first, so the `&&` chain did not invoke E2E in that combined run.
- Acceptance `rg` checks passed for all required unit strings, app-shell `/voice-lab` expectations, E2E guard/live env strings, LAN URLs, `force=true`, `Voice unavailable`, and `Save Voice`.

## Decisions Made

- Kept this plan RED-only. No Voice Lab route, UI components, API wrappers, Settings implementation, or navigation implementation was added because later Phase 2 plans own those changes.
- Treated the full six-engine roster as the durable UI contract, including future engine labels beyond the v1 default path.
- Required live Voice Lab acceptance to use explicit canonical LAN URLs instead of implicit local defaults.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Expected RED verification failures only. No TypeScript collection, Playwright syntax, or helper setup errors remained.

## User Setup Required

None - no external service configuration required for default runs. Live Voice Lab acceptance remains opt-in and documented in the spec/env gate.

## Known Stubs

None. Stub-pattern scan only found the existing `llmApiKey = ''` Settings test assertion, which verifies masked API-key handling rather than a runtime stub.

## Threat Flags

None. This plan adds security-relevant client tests for future upload/delete/text-rendering behavior but does not introduce runtime endpoints, network surfaces, file access, or schema changes.

## Next Phase Readiness

Ready for Phase 2 implementation plans to satisfy these RED contracts: Settings API/UI fields, Voice Lab route/components/API wrappers, Voice Library actions, character default voice hydration, Gallery voice badges, and live OMEN-PC acceptance.

## Self-Check: PASSED

- Verified created/modified files exist: `voice-lab.test.ts`, `app-shell.test.ts`, `settings.test.ts`, `voice-lab.spec.ts`, `live-voice-lab.spec.ts`, and this summary.
- Verified task commits exist: `9119612`, `7bb21fc`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-24*
