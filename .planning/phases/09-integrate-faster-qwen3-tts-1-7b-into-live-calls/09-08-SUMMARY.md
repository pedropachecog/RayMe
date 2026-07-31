---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 08
subsystem: client-ui
tags: [qwen3-tts, voice-cloning, readiness, accessibility, live-calls, svelte]

requires:
  - phase: 09-07
    provides: Canonical Qwen identity, authorized saved references, and authoritative model/prompt preparation state
provides:
  - Canonical Qwen3-TTS 1.7B identity and model residency in Settings and voice selectors
  - Explicit reference authorization and distinct model/prompt readiness in Voice Lab
  - Call connection gate that cannot claim Listening before selected Qwen voice preparation succeeds
  - Voice-id-scoped saved-row preparation, synthesis, retry, status, and error behavior
affects: [09-09, 09-acceptance, settings, voice-lab, voice-library, live-calls]

actuals:
  tokens: 18226
  tasks: 3
  commits: 9

tech-stack:
  added: []
  patterns: [server-metadata-label-normalization, separate-model-prompt-readiness, authoritative-call-preparation-gate, voice-id-scoped-operations, fixed-public-error-copy]

key-files:
  created: []
  modified:
    - web-ui/client/src/lib/api/types.ts
    - web-ui/client/src/lib/api/voices.ts
    - web-ui/client/src/lib/components/EndpointSettingsPanel.svelte
    - web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte
    - web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte
    - web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte
    - web-ui/client/src/lib/components/voice/VoiceLibraryList.svelte
    - web-ui/client/src/lib/components/voice/VoiceLibraryRow.svelte
    - web-ui/client/src/routes/call/[threadId]/+page.svelte
    - web-ui/client/src/routes/voice-lab/+page.svelte
    - web-ui/client/tests/unit/character-editor.test.ts
    - web-ui/client/tests/unit/settings.test.ts
    - web-ui/client/tests/unit/voice-lab.test.ts

key-decisions:
  - "Browser engine rosters preserve server order and metadata, append unavailable fallbacks only when absent, and map qwen3_1_7b to canonical 1.7B copy everywhere."
  - "Model residency and selected-reference prompt readiness remain separate visible states; neither is inferred from the other."
  - "A Qwen call remains Connecting/Preparing until the authoritative offer response confirms both a resident model and ready prompt."
  - "Saved-library preparation, synthesis, audio, errors, polling tokens, and retry payloads are keyed by opaque saved voice id so unrelated rows remain usable."
  - "Qwen preparation and generation codes are converted to fixed public copy before any server message can reach the call transcript or blocking panel."

patterns-established:
  - "Readiness display pattern: model loading/resident/unavailable and prompt none/prewarming/ready/failed are independent typed records with polite state changes and fixed alerts."
  - "Saved-row operation pattern: one stable button progresses Test Voice to Preparing voice to Testing voice, with inline retry and row-scoped state maps."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "Settings, Voice Lab, and assignment controls render canonical Qwen3-TTS 1.7B identity and truthful model residency from server metadata."
    requirement: REQ-22
    verification:
      - kind: component
        ref: "web-ui/client/tests/unit/settings.test.ts (6 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Qwen voice actions require the three explicit authorization fields and calls cannot enter Listening before authoritative model and prompt readiness."
    requirement: REQ-45
    verification:
      - kind: component
        ref: "web-ui/client/tests/unit/voice-lab.test.ts (17 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Saved Qwen rows distinguish preparation from synthesis, retry in place, announce fixed state/error copy, preserve unrelated controls, and honor mobile/reduced-motion constraints."
    requirement: REQ-46
    verification:
      - kind: unit
        ref: "web-ui/client full unit suite (101 passed)"
        status: pass
      - kind: build
        ref: "web-ui/client production build"
        status: pass
    human_judgment: false

duration: 26min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 08: Qwen Readiness UI Summary

**RayMe now shows canonical Qwen3-TTS 1.7B model and saved-voice preparation honestly, requires explicit reference authorization, and keeps calls in Preparing until the selected cloned voice is actually ready.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-07-31T19:09:49Z
- **Completed:** 2026-07-31T19:35:25Z
- **Tasks:** 3
- **Files modified:** 13

## Accomplishments

- Replaced the retired browser identity with `qwen3_1_7b`, preserved server-returned engine metadata and order, and added exact loading, loaded, and unavailable copy to Settings and voice selectors.
- Added separate typed model and prompt readiness, three explicit required authorization controls, bounded preparation polling, fixed safe failures, validation focus, and retry without clearing the user's sample, transcript, name, or engine choice.
- Kept a selected Qwen call visibly Connecting/Preparing until the authoritative offer confirms both resident model and ready prompt; failure actions route to retry, Voice Lab, or Settings without bypassing the existing call FSM.
- Reworked the saved Voice Library from one global testing flag to per-voice preparation and synthesis maps with exact button progression, one row-local status/alert, accessible 44 px controls, responsive wrapping, and static reduced-motion feedback.
- Closed the turn-time disclosure path so Qwen error events are mapped to fixed public copy before raw server messages are considered.

## Task Commits

Each planned TDD task was committed as RED then GREEN, followed by narrow verification fixes:

1. **Task 1 RED: Define canonical Qwen Settings readiness** - `e89655c` (test)
2. **Task 1 GREEN: Render canonical Qwen model readiness** - `fef063d` (feat)
3. **Task 2 RED: Define Qwen preparation UI contracts** - `630c68c` (test)
4. **Task 2 GREEN: Gate Qwen calls on visible voice preparation** - `b1ab521` (feat)
5. **Task 3 RED: Define row-scoped Qwen voice operations** - `460923d` (test)
6. **Task 3 GREEN: Scope Qwen preparation to saved voice rows** - `e755111` (feat)
7. **Suite fix: Align Character Editor canonical label assertion** - `6720170` (fix)
8. **Semantic fix: Mark all authorization controls required** - `77c33b9` (fix)
9. **Disclosure fix: Sanitize in-call Qwen failure copy** - `522dae6` (fix)

## Files Created/Modified

- `web-ui/client/src/lib/api/types.ts` - Canonical engine id plus separate model, prompt, and voice-preparation types.
- `web-ui/client/src/lib/api/voices.ts` - Existing preparation-status API facade for browser consumers.
- `web-ui/client/src/lib/components/EndpointSettingsPanel.svelte` - Canonical server-metadata labels and visible model residency states.
- `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` and `VoiceAssignmentSelect.svelte` - Canonical picker and saved-assignment identity.
- `web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte` - Distinct preparation and synthesis button feedback.
- `web-ui/client/src/routes/voice-lab/+page.svelte` - Required reference authorization, separate readiness, bounded polling, fixed errors, and per-row orchestration.
- `web-ui/client/src/lib/components/voice/VoiceLibraryList.svelte` and `VoiceLibraryRow.svelte` - Voice-id-scoped row state, retry, responsive controls, status, and alert presentation.
- `web-ui/client/src/routes/call/[threadId]/+page.svelte` - Authoritative preparation gate, visible call readiness, focused recovery, and fixed Qwen event copy.
- `web-ui/client/tests/unit/settings.test.ts`, `voice-lab.test.ts`, and `character-editor.test.ts` - Fast identity, readiness, authorization, row isolation, disclosure, and cross-component regression contracts.

## Decisions Made

- Kept engine labels driven by server metadata and normalized only known canonical ids, so future server-provided engines remain visible rather than being filtered by a browser fallback list.
- Used the existing `/api/voices/preparation-status` and call offer contracts instead of introducing an engine-specific browser endpoint or a parallel readiness dashboard.
- Treated the call offer's final readiness as authoritative; polling improves visible progress but cannot promote the call to Listening by itself.
- Preserved form and row control state across Qwen failures. Retry reuses the exact row payload and opaque saved voice id without exposing prompt keys or reference hashes.
- Left Playwright call acceptance to its later wave-owned plan; this plan's gate is the focused component contracts, complete client unit suite, and production build.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Wired existing browser API and preview companions**
- **Found during:** Task 2
- **Issue:** The planned route files needed the existing voice preparation facade and preview button component to represent preparation separately from synthesis in production.
- **Fix:** Added the typed status read to `voices.ts` and a dedicated `preparing` state to `SynthPreviewPanel.svelte`; no new endpoint or dashboard was created.
- **Files modified:** `web-ui/client/src/lib/api/voices.ts`, `web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte`
- **Committed in:** `b1ab521`

**2. [Rule 1 - Bug] Corrected an invalid Svelte component class directive**
- **Found during:** Task 3 production build
- **Issue:** Svelte rejected `class:` on the `RefreshCw` component.
- **Fix:** Passed the conditional class through the component's `class` prop and kept the reduced-motion CSS contract intact.
- **Files modified:** `web-ui/client/src/lib/components/voice/VoiceLibraryRow.svelte`
- **Committed in:** `e755111`

**3. [Rule 1 - Bug] Updated a stale cross-component engine-label assertion**
- **Found during:** Full client unit verification
- **Issue:** Character Editor's unit test still required the retired 0.6B label after its assignment component correctly moved to 1.7B.
- **Fix:** Updated the assertion to the canonical `Qwen3-TTS 1.7B-Base` label.
- **Files modified:** `web-ui/client/tests/unit/character-editor.test.ts`
- **Committed in:** `6720170`

**4. [Rule 2 - Missing Critical] Made authorization requirements semantic**
- **Found during:** Accessibility contract audit
- **Issue:** Qwen actions enforced all three values in route state, but the controls did not expose their required nature to browser form and accessibility APIs.
- **Fix:** Marked exactly the three authorization controls required and added a focused regression assertion.
- **Files modified:** `web-ui/client/src/routes/voice-lab/+page.svelte`, `web-ui/client/tests/unit/voice-lab.test.ts`
- **Committed in:** `77c33b9`

**5. [Rule 2 - Missing Critical] Sanitized turn-time Qwen errors before rendering**
- **Found during:** Threat-surface scan
- **Issue:** Startup preparation errors used fixed copy, but a later call error event could prefer a raw server message in the transcript notice.
- **Fix:** Added an allowlisted Qwen/preparation mapper before the generic message path and covered unknown Qwen codes with a fixed safe fallback.
- **Files modified:** `web-ui/client/src/routes/call/[threadId]/+page.svelte`, `web-ui/client/tests/unit/voice-lab.test.ts`
- **Committed in:** `522dae6`

---

**Total deviations:** 5 auto-fixed (2 bugs, 3 missing critical production/accessibility/security requirements).
**Impact on plan:** All fixes close planned identity, readiness, accessibility, or disclosure contracts without adding a new architecture, dependency, browser endpoint, deployment path, or non-live audio fallback.

## TDD Gate Compliance

- RED and GREEN commits exist in order for all three planned tasks.
- Focused Settings tests passed: 6 tests.
- Focused Voice Lab tests passed: 17 tests.
- Full client unit suite passed: 15 files, 101 tests.
- Production build passed with the static adapter.

## Issues Encountered

- The focused component tests intentionally run from the repository root and create a transient root Vitest cache; it was removed after each run and was never committed.
- The first full unit run exposed the stale Character Editor assertion; the corrected suite then passed twice, including after the final disclosure fix.

## User Setup Required

None - no new dependency, secret, service, deployment change, or manual configuration is required.

## Next Phase Readiness

- The browser now exposes the server-side 1.7B identity, authorization, model residency, prompt preparation, and safe failure contracts without hidden cold-call transitions.
- The later acceptance wave can exercise Playwright and real RayMe calls against these stable visible states.
- No known stubs, skipped tests, unrun plan verification commands, or blockers remain.

## Self-Check: PASSED

- All thirteen implementation/test files and this summary exist.
- Commits `e89655c`, `fef063d`, `630c68c`, `b1ab521`, `460923d`, `e755111`, `6720170`, `77c33b9`, and `522dae6` are present in git history.
- Focused Settings tests passed (6), focused Voice Lab tests passed (17), the complete client unit suite passed (101), the final production build passed, and `git diff --check` passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
