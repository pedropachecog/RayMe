---
phase: 03-first-working-call-mvp
plan: "08"
subsystem: client-ui
tags: [sveltekit, playwright, call-ui, browser-media, mobile-layout]
requires:
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-03 RED browser contracts for the client call UI."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-07 client call API, FSM, audio unlock, and RMS helpers."
provides:
  - "Operational call route with fixed recovery panels, toolbar controls, live transcript, and RMS visualizer."
  - "Thread and character-card Start Call entry points."
  - "Thread scrollback rendering for call_start, user_speech, ai_speech, and call_end rows."
  - "Desktop and mobile Playwright coverage for the Phase 3 call surface."
affects: [phase-03-call-client, call-ui, thread-scrollback, mobile-browser-acceptance]
tech-stack:
  added: []
  patterns:
    - "Call UI uses fixed public recovery copy and does not render raw backend/browser exceptions."
    - "Playwright call contracts mock the canonical same-origin /api/calls/start route."
key-files:
  created:
    - web-ui/client/src/lib/components/call/VoiceVisualizer.svelte
    - web-ui/client/src/lib/components/call/CallToolbar.svelte
    - web-ui/client/src/lib/components/call/CallTranscript.svelte
    - web-ui/client/src/routes/call/[threadId]/+page.svelte
  modified:
    - web-ui/client/src/app.css
    - web-ui/client/src/lib/api/calls.ts
    - web-ui/client/src/lib/components/AppShell.svelte
    - web-ui/client/src/lib/components/CharacterCard.svelte
    - web-ui/client/src/lib/components/ChatMessageBubble.svelte
    - web-ui/client/src/routes/chat/[threadId]/+page.svelte
    - web-ui/client/tests/e2e/call-start.spec.ts
    - web-ui/client/tests/e2e/call-toolbar.spec.ts
    - web-ui/client/tests/e2e/call-permissions.spec.ts
    - web-ui/client/tests/e2e/call-visualizer.spec.ts
    - web-ui/client/tests/e2e/call-summary.spec.ts
    - web-ui/client/tests/e2e/call-mobile.spec.ts
key-decisions:
  - "The approved call entry route is /call/{threadId}; stale browser contracts were updated from /chat/{threadId} active-call expectations."
  - "Call browser tests mock /api/calls/start to match the Web UI server facade contract from Plan 03-05."
  - "Mobile call controls reserve space above the AppShell bottom navigation rather than hiding the navigation."
patterns-established:
  - "Call visual state separates listeningRms and speakingRms while keeping deterministic fallback animation for unavailable meters."
  - "Call row rendering maps known message_kind values to fixed render branches."
requirements-completed: [REQ-40, REQ-47, REQ-48, REQ-49, REQ-50, REQ-A0]
duration: 27m57s
completed: 2026-04-25T21:28:01Z
---

# Phase 03 Plan 08: Call UI Surface Summary

**Operational Svelte call surface with thread/character entry, RMS visual states, toolbar controls, live transcript, and durable call rows.**

## Performance

- **Duration:** 27m57s
- **Started:** 2026-04-25T21:00:04Z
- **Completed:** 2026-04-25T21:28:01Z
- **Tasks:** 3
- **Files modified:** 16

## Accomplishments

- Added reusable call components for the voice visualizer, toolbar, and transcript, including separate listening/speaking RMS inputs and reduced-motion handling.
- Added `/call/[threadId]` with fixed preflight/recovery panels, active call canvas, sticky toolbar, and return-to-thread behavior.
- Wired `Start call` in thread headers and `Start Call` on character cards.
- Rendered `call_start`, `user_speech`, `ai_speech`, and `call_end` messages as fixed call-specific rows in thread scrollback.
- Updated browser contracts to the approved call route and canonical `/api/calls/start` facade path.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add call components and visual states** - `6cbca57` (feat)
2. **Task 2: Add call route and entry points** - `e029a4c` (feat)
3. **Task 3: Render call rows in thread scrollback and preserve mobile layout** - `473aa8b` (feat)

## Files Created/Modified

- `web-ui/client/src/lib/components/call/VoiceVisualizer.svelte` - Listening, Thinking, and Speaking visual states driven by split RMS inputs with deterministic fallback.
- `web-ui/client/src/lib/components/call/CallToolbar.svelte` - Mute/Unmute, Interrupt, input/output picker fallback, and destructive End Call controls.
- `web-ui/client/src/lib/components/call/CallTranscript.svelte` - Empty, finalized, streaming, and interrupted transcript rows.
- `web-ui/client/src/routes/call/[threadId]/+page.svelte` - Operational call page, fixed recovery panels, toolbar wiring, and return-to-thread flow.
- `web-ui/client/src/routes/chat/[threadId]/+page.svelte` - Thread header `Start call` icon entry.
- `web-ui/client/src/lib/components/CharacterCard.svelte` - Character card `Start Call` action.
- `web-ui/client/src/lib/components/ChatMessageBubble.svelte` - Fixed render branches for call boundary and speech rows.
- `web-ui/client/src/lib/components/AppShell.svelte` - Mobile bottom navigation test marker.
- `web-ui/client/src/lib/api/calls.ts` - Start-call error parsing with fixed public error propagation and legacy test fallback.
- `web-ui/client/tests/e2e/call-*.spec.ts` - Updated call route/API mocks and mobile control assertions.

## Decisions Made

- Kept the call page as the first operational surface instead of adding an explanatory pre-call screen.
- Used fixed UI-SPEC recovery copy for all blocking states and mapped backend error codes to public panels.
- Kept AppShell bottom navigation visible on mobile while reserving enough space for sticky call controls.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 Playwright verification required Task 2 route wiring**
- **Found during:** Task 1
- **Issue:** `call-toolbar` and `call-visualizer` specs blocked on the missing `Start call` entry and call route, which were assigned to Task 2.
- **Fix:** Verified Task 1 static acceptance before commit, then reran the Playwright specs after Task 2 added the route and entry points.
- **Files modified:** Call component files only for Task 1; route files in Task 2.
- **Verification:** `call-toolbar.spec.ts` and `call-visualizer.spec.ts` passed after Task 2.
- **Committed in:** `6cbca57`, cleared by `e029a4c`

**2. [Rule 3 - Blocking] Aligned stale browser contracts with approved call route/API contract**
- **Found during:** Task 2
- **Issue:** Existing RED Playwright contracts mocked `/api/calls` and expected character-card starts to land on `/chat/{threadId}`, while the approved Plan 03-08 and server facade use `/api/calls/start` and `/call/{threadId}`.
- **Fix:** Updated call specs to mock `/api/calls/start`, assert `/call/{threadId}`, scope state text assertions to the visualizer, and stub portrait fixture requests so unrelated image 404s do not fail the browser error guard.
- **Files modified:** `web-ui/client/tests/e2e/call-start.spec.ts`, `call-toolbar.spec.ts`, `call-permissions.spec.ts`, `call-visualizer.spec.ts`, `call-summary.spec.ts`, `call-mobile.spec.ts`
- **Verification:** Desktop call-start, toolbar, permissions, visualizer, and summary specs passed.
- **Committed in:** `e029a4c`

**3. [Rule 3 - Blocking] Added AppShell bottom navigation marker for mobile layout verification**
- **Found during:** Task 3
- **Issue:** `call-mobile.spec.ts` expected `data-testid="bottom-navigation"` but the AppShell bottom nav did not expose a stable locator.
- **Fix:** Added the test marker and expanded the mobile spec to assert Mute, Interrupt, End Call, and both device pickers have visible 44px touch targets above the bottom navigation.
- **Files modified:** `web-ui/client/src/lib/components/AppShell.svelte`, `web-ui/client/tests/e2e/call-mobile.spec.ts`
- **Verification:** Mobile Chromium call spec passed.
- **Committed in:** `473aa8b`

---

**Total deviations:** 3 auto-fixed (3 blocking).
**Impact on plan:** All fixes were required to satisfy the approved call route, API facade, and mobile acceptance contracts. No architectural changes were introduced.

## Issues Encountered

- Running desktop summary and mobile Playwright specs in parallel caused a Vite/SvelteKit build-directory race (`ENOTEMPTY: directory not empty, rmdir 'build/_app/immutable'`). The specs passed when rerun sequentially.

## Known Stubs

None. Empty arrays/strings in the call components and route are runtime initial state, not mock UI data.

## Threat Flags

None. New call UI surfaces are covered by the plan threat model: fixed recovery copy prevents raw exception disclosure, known message kinds map to fixed render paths, and mobile overlap is guarded by Playwright.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run` - 86 passed.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts tests/e2e/call-toolbar.spec.ts tests/e2e/call-permissions.spec.ts tests/e2e/call-visualizer.spec.ts tests/e2e/call-summary.spec.ts --project=desktop-chromium` - 6 passed.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-mobile.spec.ts --project=mobile-chromium` - 1 passed.
- `npm --prefix web-ui/client run check` - passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 03-09 can wire live turn submission and richer event handling into the established call route, toolbar, transcript, and thread scrollback surfaces.

## Self-Check: PASSED

- Found expected files: `VoiceVisualizer.svelte`, `CallToolbar.svelte`, `CallTranscript.svelte`, `call/[threadId]/+page.svelte`, and this summary.
- Found task commits: `6cbca57`, `e029a4c`, `473aa8b`.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
