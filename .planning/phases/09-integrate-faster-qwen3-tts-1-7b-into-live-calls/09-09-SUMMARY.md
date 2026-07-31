---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 09
subsystem: browser-acceptance
tags: [playwright, qwen3-tts, voice-cloning, readiness, provenance, live-calls]

requires:
  - phase: 09-08
    provides: Canonical Qwen identity, authorization controls, separate readiness, row-local retry, and call preparation gate
provides:
  - Saved mocked browser acceptance for canonical Qwen model and prompt readiness across Settings, Voice Lab, Voice Library, and calls
  - Production-only Qwen live-call suite gated by canonical OMEN URLs, exact deployed commit, and hash-bound permitted fixtures
  - Fail-closed local provenance validation that never fabricates speaker permission
affects: [09-14, 09-15, browser-release-evidence, physical-call-handoff]

actuals:
  tokens: 11489
  tasks: 2
  commits: 5

tech-stack:
  added: []
  patterns: [mocked-contract-annotation, controllable-route-gates, focus-preserving-aria-disabled, hash-bound-live-fixture, commit-matched-live-e2e]

key-files:
  created:
    - web-ui/client/tests/e2e/qwen3-readiness.spec.ts
  modified:
    - web-ui/client/tests/e2e/live-call.spec.ts
    - web-ui/client/tests/e2e/call-start.spec.ts
    - web-ui/client/tests/e2e/voice-lab.spec.ts
    - web-ui/client/tests/e2e/settings-connection.spec.ts
    - web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte
    - web-ui/client/src/lib/components/voice/VoiceLibraryRow.svelte
    - web-ui/client/tests/unit/voice-lab.test.ts

key-decisions:
  - "Saved readiness results carry environment=mocked_contract and can never satisfy the deployed browser/live release gate."
  - "The production live suite defaults to qwen3_1_7b and fails closed unless canonical OMEN URLs, an exact 40-character deployed commit, local fixture files, an exact transcript file, and hash-bound provenance are supplied."
  - "Busy preview/test actions use guarded aria-disabled state so duplicate work remains blocked without ejecting keyboard focus from the initiating control."
  - "Product-owner direction/listening and a permission_confirmed flag are explicitly rejected as speaker authorization; generated non-person fixtures identify their basis and data steward."

patterns-established:
  - "Mocked readiness pattern: route gates hold synthesis/offer completion while browser assertions observe loading, prewarming, ready, failed, retry, and no-premature-Listening states."
  - "Deployed fixture pattern: read private audio/transcript/provenance only from explicit local files, verify exact SHA-256 and LAN scope, then send only typed authorization fields through RayMe's production API."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "Desktop and mobile browser contracts prove canonical Qwen identity, authorization persistence, separate readiness, row-local retry, sanitized failures, focus, responsive targets, reduced motion, and no premature Listening."
    requirement: REQ-22
    verification:
      - kind: e2e
        ref: "Playwright qwen3-readiness.spec.ts, voice-lab.spec.ts, call-start.spec.ts: 66 passed"
        status: pass
      - kind: unit
        ref: "Focused client readiness tests: 31 passed"
        status: pass
    human_judgment: false
  - id: D2
    description: "The opt-in production browser suite accepts qwen3_1_7b only with commit-matched deployed RayMe and a permitted hash-bound reference/transcript/provenance fixture."
    requirement: REQ-45
    verification:
      - kind: e2e
        ref: "live-call.spec.ts provenance contract: 2 passed; deployed Qwen cases structurally listed and intentionally skipped until Plan 09-15"
        status: pass
    human_judgment: false
  - id: D3
    description: "Call readiness remains live: Connecting/Preparing is visible before the authoritative offer and transitions directly to Listening without introducing whole-synthesis playback behavior."
    requirement: REQ-46
    verification:
      - kind: e2e
        ref: "call-start.spec.ts delayed Qwen preparation and fixed failure cases in the 66-test saved acceptance run"
        status: pass
    human_judgment: false

duration: 23min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 09: Qwen Browser Acceptance Summary

**RayMe now has an honest mocked Qwen readiness contract and a separate production-only, commit-matched live-call path that refuses unpermitted voice fixtures.**

## Performance

- **Duration:** 23 min
- **Started:** 2026-07-31T20:09:20Z
- **Completed:** 2026-07-31T20:32:11Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added four saved mocked Playwright scenarios covering dynamic Settings identity, Voice Lab authorization and failure preservation, row-local preparation/testing/retry, 320px layout, 44px targets, reduced motion, and clean browser error guards. Every result is labeled `environment=mocked_contract`.
- Added Qwen call-start browser coverage proving the route remains Connecting with a visible Preparing voice panel until the offer authoritatively reports resident model plus ready prompt, then transitions once to Listening; the failure path stays fixed, focused, and sanitized.
- Extended the canonical production live suite to accept `qwen3_1_7b`, assert the exact deployed commit and WebRTC readiness, create the voice through production APIs, wait for selected prompt readiness, and require two early-audio plus normal-completion cycles.
- Added fail-closed provenance handling for missing/malformed metadata, wrong reference/transcript hashes, wrong scope, fabricated `permission_confirmed`, and product-owner-listening claims. Private reference material stays in explicit local files.

## Task Commits

1. **Task 1 RED: Define mocked Qwen readiness acceptance** - `abd08da` (test)
2. **Task 1 GREEN: Save Qwen readiness browser contracts** - `0fb5f5f` (feat)
3. **Task 2 RED: Define deployed Qwen call prerequisites** - `6ccd094` (test)
4. **Task 2 GREEN: Gate deployed Qwen browser acceptance** - `c263404` (feat)
5. **Verification fix: Align saved-row progress assertion** - `ab1bfe7` (fix)

## Files Created/Modified

- `web-ui/client/tests/e2e/qwen3-readiness.spec.ts` - Mocked-contract readiness, authorization, retry, focus, mobile, and reduced-motion acceptance.
- `web-ui/client/tests/e2e/call-start.spec.ts` - Delayed Qwen preparation and focused fixed-failure call-start cases.
- `web-ui/client/tests/e2e/live-call.spec.ts` - Canonical deployed Qwen acceptance, exact-commit checks, permitted fixture builder, and provenance negative matrix.
- `web-ui/client/tests/e2e/voice-lab.spec.ts` and `settings-connection.spec.ts` - Canonical 1.7B fixtures and stable live-region assertions.
- `web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte` and `VoiceLibraryRow.svelte` - Focus-preserving busy state with guarded duplicate actions.
- `web-ui/client/tests/unit/voice-lab.test.ts` - Fast contract for the guarded focus-preserving saved-row action.

## Decisions Made

- Mocked browser acceptance is useful regression proof, but is explicitly not deployment evidence. Plan 09-15 must execute the live case after the canonical deployment.
- The live suite reads punctuation-rich transcript text from a file without shell interpolation and verifies the provenance transcript hash against those exact bytes before sending the exact text to RayMe.
- The live suite does not infer consent from upload, listening, or product-owner direction and never emits `permission_confirmed`.
- Native `disabled` remains for locally invalid actions. Only an already-initiated busy action changes to guarded `aria-disabled`, preserving focus while preventing duplicate requests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved focus on the initiating action during asynchronous progress**
- **Found during:** Task 1 desktop Playwright GREEN run
- **Issue:** Native `disabled` removed keyboard focus as soon as preview/test-play entered Preparing or Testing, violating the approved focus contract even though duplicate clicks were correctly blocked.
- **Fix:** Used guarded `aria-disabled` only for the busy state and retained native `disabled` for invalid form state; handlers reject repeat activation while the operation is active.
- **Files modified:** `SynthPreviewPanel.svelte`, `VoiceLibraryRow.svelte`, `voice-lab.test.ts`
- **Verification:** Focus assertions passed in Qwen readiness Playwright; focused unit suite passed 31 tests.
- **Committed in:** `0fb5f5f`

**2. [Rule 1 - Bug] Repaired a stale saved-row progress assertion**
- **Found during:** Plan-level saved Playwright acceptance
- **Issue:** The older E2E expected three ASCII periods and used a non-unique text locator after the approved UI moved to a Unicode ellipsis and one dedicated status live region.
- **Fix:** Assert the exact `Testing voice…` copy through the row's single `role=status` locator.
- **Files modified:** `web-ui/client/tests/e2e/voice-lab.spec.ts`
- **Verification:** Focused desktop/mobile case passed 2/2; full saved acceptance then passed 66/66.
- **Committed in:** `ab1bfe7`

---

**Total deviations:** 2 auto-fixed bugs.
**Impact on plan:** Both fixes enforce the approved accessibility/status contract without changing call transport, engine behavior, API architecture, or deployment scope.

## Issues Encountered

- The pinned Playwright package was present but its matching Chromium 1217 binary was absent. The official pinned browser binary was downloaded through the existing Playwright CLI; no package or repository dependency changed.
- The first plan-level run surfaced the stale row copy/locator and finished 66 passed, 2 failed. After the one-line assertion repair, the exact saved acceptance passed 66/66.

## TDD Gate Compliance

- Both planned tasks have RED `test(...)` commits followed by GREEN `feat(...)` commits.
- Task 1: focused readiness component tests passed 31/31; desktop mocked Qwen/call acceptance passed 26/26; final desktop/mobile saved wave acceptance passed 66/66.
- Task 2: live provenance negative contract passed on desktop/mobile (2/2); the production Qwen cases list for both projects and remain intentionally opt-in until post-deploy Plan 09-15.
- Client production build passed after the final implementation.

## User Setup Required

None for this plan. The final autonomous deployment/evidence plan supplies the explicit live environment and private permitted fixture files when it executes the opt-in suite.

## Next Phase Readiness

- Plan 09-14 can deploy a commit containing the exact browser contracts.
- Plan 09-15 can run the production Qwen live case with `RAYME_ENABLE_LIVE_E2E=1`, canonical URLs, expected commit, exact transcript file, provenance sidecar, reference WAV, and fake-mic WAV.
- No mocked result is represented as real OMEN proof, and no physical-call/product-owner acceptance is claimed here.

## Self-Check: PASSED

- All eight implementation/test files and this summary exist.
- Commits `abd08da`, `0fb5f5f`, `6ccd094`, `c263404`, and `ab1bfe7` are present in git history.
- Focused client tests passed 31/31, saved desktop/mobile Playwright passed 66/66, live provenance checks passed 2/2 with deployed tests opt-in, production build passed, and `git diff --check` passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
