---
phase: 03-first-working-call-mvp
plan: "07"
subsystem: client
tags: [sveltekit, typescript, webrtc, browser-media, call-fsm]
requires:
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-03 RED client call FSM/audio contracts."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-05 same-origin Web UI server call facade and rayme-events contract."
provides:
  - "Typed browser `/api/calls` wrappers for start, offer, turns, mute, interrupt, and end."
  - "Reusable RTCPeerConnection helper with microphone tracks, remote stream callback, and rayme-events parsing."
  - "Client call FSM with forward-stable transcript append semantics and server-side mute state."
  - "Browser audio unlock, device picker capability helpers, and separate mic/AI RMS meters."
affects: [phase-03-call-client, call-ui, browser-media, webrtc-turn-orchestration]
tech-stack:
  added: []
  patterns:
    - "Browser call transport uses same-origin Web UI server routes only."
    - "AI-backend-originated data-channel events are parsed narrowly and malformed JSON is ignored."
    - "Call transcript text is append-only for active AI output."
key-files:
  created:
    - web-ui/client/src/lib/api/calls.ts
    - web-ui/client/src/lib/call/client.ts
    - web-ui/client/src/lib/call/store.svelte.ts
    - web-ui/client/src/lib/call/audio.ts
  modified:
    - web-ui/client/src/lib/api/types.ts
key-decisions:
  - "Client-side mute state tracks server consumption separately from local microphone track enabled state."
  - "The WebRTC helper accepts malformed rayme-events messages as no-ops instead of surfacing parser errors to the call UI."
  - "Audio device unsupported states use fixed UI contract copy rather than raw browser exception details."
patterns-established:
  - "Call FSM exposes canonical plan methods plus compatibility aliases used by the existing RED tests."
  - "RMS metering keeps microphone listening and AI speaking energy independent for the visualizer."
requirements-completed: [REQ-47, REQ-48, REQ-49, REQ-A0, REQ-A1]
duration: 5m35s
completed: 2026-04-25T20:56:46Z
---

# Phase 03 Plan 07: Client Call Transport and FSM Summary

**Typed browser call transport, rayme-events WebRTC handling, call FSM, audio unlock, device fallback copy, and split RMS metering are now implemented against the RED contracts.**

## Performance

- **Duration:** 5m35s
- **Started:** 2026-04-25T20:51:11Z
- **Completed:** 2026-04-25T20:56:46Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added typed client call API wrappers for `/api/calls/start`, `/offer`, `/turns`, `/mute`, `/interrupt`, and `/end`.
- Added a WebRTC helper that attaches microphone tracks with `addTrack`, handles `ontrack`, and listens for `rayme-events` data-channel messages.
- Implemented the call state machine with connecting/listening/thinking/speaking/interrupted/ended/failed flow, transcript updates, interrupt cleanup, hangup cleanup, and server mute state.
- Implemented AudioContext unlock with a one-sample silent buffer, fixed unsupported device picker copy, audio input listing, output sink selection, and separate mic/AI RMS meters.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add typed call API and WebRTC client helper** - `c0b8b17` (feat)
2. **Task 2: Implement call FSM and AudioContext/device helpers** - `706caf0` (feat)

## Files Created/Modified

- `web-ui/client/src/lib/api/types.ts` - Added call request/response, event, transcript, state, and public error-code types.
- `web-ui/client/src/lib/api/calls.ts` - Added typed same-origin call route wrappers.
- `web-ui/client/src/lib/call/client.ts` - Added reusable RTCPeerConnection helper, microphone track attachment, offer negotiation, cleanup, and rayme-events parsing.
- `web-ui/client/src/lib/call/store.svelte.ts` - Added call FSM, transcript state, AI append semantics, interrupt/end cleanup, and server-muted state.
- `web-ui/client/src/lib/call/audio.ts` - Added AudioContext unlock, fixed picker fallback copy, device helpers, and split RMS metering.

## Decisions Made

- Kept call transport client-owned but same-origin only; the browser calls the Web UI server facade, not the AI backend directly.
- Treated malformed or unknown data-channel payloads as ignored events, preserving call continuity and avoiding raw parser errors in UI state.
- Preserved RED-test compatibility method names while exposing the canonical method names required by this plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 verification depended on Task 2**
- **Found during:** Task 1
- **Issue:** The Task 1 verification command imported `src/lib/call/store.svelte`, which was assigned to Task 2 and did not exist yet.
- **Fix:** Verified Task 1 with static acceptance criteria, committed it atomically, then ran the full plan verification after Task 2 implemented the store.
- **Files modified:** `web-ui/client/src/lib/api/types.ts`, `web-ui/client/src/lib/api/calls.ts`, `web-ui/client/src/lib/call/client.ts`
- **Verification:** Final `npm --prefix web-ui/client run test:unit -- --run tests/unit/call-state.test.ts tests/unit/call-audio.test.ts` passed.
- **Committed in:** `c0b8b17`, cleared by `706caf0`

**2. [Rule 2 - Missing Critical] Guarded audio helpers outside full browser contexts**
- **Found during:** Task 2
- **Issue:** Browser media helpers can be imported under SSR/unit-test contexts where `navigator` or `AudioContext` may be absent.
- **Fix:** Added explicit availability checks so device listing returns an empty list when media devices are unavailable and audio unlock fails with a fixed public error instead of a reference error.
- **Files modified:** `web-ui/client/src/lib/call/audio.ts`
- **Verification:** Targeted call audio/state unit tests passed.
- **Committed in:** `706caf0`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical).
**Impact on plan:** Both fixes stayed within the planned client call transport and browser media helper surface.

## Issues Encountered

- Task 1's automated test could not pass before Task 2 added the FSM module. The final combined verification passes.

## Known Stubs

None. Empty initial transcript/active-text values are local runtime state, not UI stubs or mock data sources.

## Threat Flags

None. The new browser call bootstrap, transcript streaming, and device picker surfaces are covered by the plan threat model.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run tests/unit/call-state.test.ts tests/unit/call-audio.test.ts` - 8 passed.
- `rg -n "addStream\\(" web-ui/client/src web-ui/client/tests` - no matches.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 03-08 can wire these helpers into the call UI surface, and Plan 03-09 can use `submitCallTurn` plus the `user_final` data-channel event path for turn orchestration.

## Self-Check: PASSED

- Found expected files: `web-ui/client/src/lib/api/types.ts`, `web-ui/client/src/lib/api/calls.ts`, `web-ui/client/src/lib/call/client.ts`, `web-ui/client/src/lib/call/store.svelte.ts`, `web-ui/client/src/lib/call/audio.ts`, `.planning/phases/03-first-working-call-mvp/03-07-SUMMARY.md`.
- Found task commits: `c0b8b17`, `706caf0`.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
