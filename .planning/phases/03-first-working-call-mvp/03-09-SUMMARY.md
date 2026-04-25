---
phase: 03-first-working-call-mvp
plan: "09"
subsystem: call-loop
tags: [fastapi, sse, webrtc, tts, sveltekit, playwright]
requires:
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-04 AI backend call sessions and rayme-events data channel."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-05 Web UI server call facade and active call/session registry."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-07 client call transport and call FSM helpers."
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-08 operational call UI surface."
provides:
  - "Full user_final to ai_token to AI TTS playback to durable ai_speech turn orchestration."
  - "AI backend /webrtc session speak endpoint with deterministic TTS cancellation."
  - "Server-owned call/session validation for repeated turns and interrupt-safe LLM cancellation."
  - "Browser call route turn submission, SSE token consumption, and interrupted transcript chips."
affects: [03-first-working-call-mvp, ai-backend, web-ui-server, web-ui-client, call-loop]
tech-stack:
  added: []
  patterns:
    - "Server /api/calls/{call_id}/turns maps internal chat stream events to call-specific ai_token and ai_done SSE events."
    - "Call TTS playback uses saved voice reference audio from the Web UI server instead of browser-supplied voice data."
    - "Browser turn streaming uses AbortController and reader cancellation for button interrupt."
key-files:
  created:
    - .planning/phases/03-first-working-call-mvp/03-09-SUMMARY.md
  modified:
    - ai-backend/app/api/webrtc.py
    - ai-backend/app/call/session.py
    - ai-backend/tests/test_call_session.py
    - ai-backend/tests/test_webrtc_signaling.py
    - web-ui/server/app/api/calls.py
    - web-ui/server/app/domain/call_service.py
    - web-ui/server/app/domain/ai_backend_client.py
    - web-ui/server/tests/test_calls.py
    - web-ui/client/src/lib/api/calls.ts
    - web-ui/client/src/lib/api/types.ts
    - web-ui/client/src/lib/call/client.ts
    - web-ui/client/src/lib/call/store.svelte.ts
    - web-ui/client/src/lib/components/call/CallTranscript.svelte
    - web-ui/client/src/routes/call/[threadId]/+page.svelte
    - web-ui/client/tests/e2e/call-start.spec.ts
key-decisions:
  - "The Web UI server remains the owner of call_id to session_id correlation and rejects posted session mismatches before writeback or playback."
  - "The visible accumulated ai_token stream is the exact source persisted as the final ai_speech row."
  - "AI backend generic TTS adapters require real saved voice reference audio; placeholder audio is treated as a correctness bug."
patterns-established:
  - "Call interrupt cancels the server LLM stream task, AI backend playback, and the browser SSE reader."
  - "Plan 03-09 local Playwright verifies two user to AI cycles in one call before thread writeback."
requirements-completed: [REQ-40, REQ-47, REQ-49, REQ-50, REQ-63, REQ-A0]
duration: 20m 14s
completed: 2026-04-25
---

# Phase 03 Plan 09: Full MVP Call Loop Summary

**Multi-turn call loop from WebRTC user_final events through streamed AI text, saved-voice TTS playback, durable speech rows, and interrupt-safe return to listening.**

## Performance

- **Duration:** 20m 14s
- **Started:** 2026-04-25T21:31:33Z
- **Completed:** 2026-04-25T21:51:47Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- Added AI backend `/webrtc/sessions/{session_id}/speak`, `CallSession.speak_text`, and `cancel_ai_turn` with `ai_audio_started`, `ai_done`, and fixed `call_tts_failed` behavior.
- Added Web UI server `/api/calls/{call_id}/turns` that validates session ownership, writes `user_speech`, builds 24-turn call context, streams `ai_token`, forwards final visible text to TTS, and writes exact `ai_speech`.
- Wired browser call turns so `user_final` events submit to `/turns`, SSE `ai_token` appends forward-stably, `ai_done` returns to listening, and interrupt aborts local stream work.
- Added automated coverage for two sequential user to AI cycles in one call session before `call_end`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add backend speech playback and cancellation session hooks** - `9bde0a1` (feat)
2. **Task 2: Add server turn orchestration stream** - `f8ab977` (feat)
3. **Task 3: Wire browser turn stream, transcript, and controls end-to-end** - `e2c5443` (feat)

Additional corrective commit:

- **Reference audio fix** - `a89bd06` (fix)

## Files Created/Modified

- `ai-backend/app/api/webrtc.py` - Added session speak request model and route, including reference-audio fields and fixed TTS failure mapping.
- `ai-backend/app/call/session.py` - Added speech synthesis/playback queueing, cancellation, outbound audio buffering, and AI audio lifecycle events.
- `web-ui/server/app/api/calls.py` - Added `/turns`, call-specific SSE event mapping, active LLM task cancellation, and saved-voice reference forwarding.
- `web-ui/server/app/domain/call_service.py` - Added active call lookup, user/AI speech writeback helpers, and saved voice sample lookup.
- `web-ui/server/app/domain/ai_backend_client.py` - Added `speak_call` proxy to AI backend session playback.
- `web-ui/client/src/routes/call/[threadId]/+page.svelte` - Added user_final handling, turn SSE reader, interrupt cancellation, and transcript prop fix.
- `web-ui/client/src/lib/api/calls.ts` - Made `submitCallTurn` abortable.
- `web-ui/client/src/lib/api/types.ts` - Added `ai_done` call event and persistent interrupted transcript marker.
- `web-ui/client/src/lib/call/client.ts` - Accepted `ai_done` on `rayme-events`.
- `web-ui/client/src/lib/call/store.svelte.ts` - Marks the active AI transcript as interrupted on button interrupt.
- `web-ui/client/src/lib/components/call/CallTranscript.svelte` - Renders persisted interrupted chips.
- Tests in `ai-backend/tests/`, `web-ui/server/tests/test_calls.py`, and `web-ui/client/tests/e2e/call-start.spec.ts` cover the new loop.

## Decisions Made

- The server streams visible text to the browser as `ai_token` and persists exactly the joined token text as `ai_speech`; backend TTS receives the same text.
- The server forwards saved voice reference audio and transcript to AI backend speak calls because the AI backend does not own durable voice blobs.
- Browser interrupt cancels the local SSE reader immediately, then calls the server interrupt route to cancel LLM generation and backend playback.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Passed real saved voice references to call TTS**
- **Found during:** Summary stub scan after Task 3
- **Issue:** The first implementation used placeholder reference audio for generic AI backend TTS adapters, which would make live saved-voice playback fail or synthesize against invalid data.
- **Fix:** Added server voice sample lookup and base64 forwarding to `/webrtc/sessions/{session_id}/speak`; AI backend now requires real reference audio for generic adapters.
- **Files modified:** `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`, `ai-backend/tests/test_call_session.py`, `web-ui/server/app/api/calls.py`, `web-ui/server/app/domain/call_service.py`, `web-ui/server/tests/test_calls.py`
- **Verification:** Full plan verification passed after the fix.
- **Committed in:** `a89bd06`

**2. [Rule 1 - Bug] Fixed call transcript prop wiring**
- **Found during:** Task 3
- **Issue:** The call route passed a `transcript` prop to `CallTranscript`, but the component exports `turns`, so live turn rows would not render.
- **Fix:** Changed the route to pass `turns={transcript}` and added multi-turn Playwright coverage.
- **Files modified:** `web-ui/client/src/routes/call/[threadId]/+page.svelte`, `web-ui/client/tests/e2e/call-start.spec.ts`
- **Verification:** Client call Playwright target passed.
- **Committed in:** `e2c5443`

**3. [Rule 3 - Blocking] Stubbed portrait requests in new multi-turn Playwright fixture**
- **Found during:** Task 3 verification
- **Issue:** The new multi-turn spec omitted the existing portrait stub, causing unrelated 404 console errors to fail the browser error guard.
- **Fix:** Added the same 204 portrait route stub used by adjacent call specs.
- **Files modified:** `web-ui/client/tests/e2e/call-start.spec.ts`
- **Verification:** Client call Playwright target passed on rerun.
- **Committed in:** `e2c5443`

---

**Total deviations:** 3 auto-fixed (1 missing critical, 1 bug, 1 blocking).
**Impact on plan:** All fixes were required to make the planned call loop functional and verifiable; no architectural scope expansion beyond the existing Web UI server to AI backend voice/TTS boundary.

## Issues Encountered

- The first client E2E run failed only because of an unmocked portrait fixture request; the call-loop assertions themselves were correct after the fixture stub.
- Playwright emitted Node `NO_COLOR` and Vite plugin timing warnings; these did not fail verification.

## Known Stubs

None. Stub scan found only runtime empty initial state and test fake collections. The prior placeholder reference-audio path was removed in `a89bd06`.

## Threat Flags

None. New reference-audio forwarding reuses the existing server-to-AI-backend TTS trust boundary, and public failures remain fixed-code (`call_generation_failed`, `call_tts_failed`) without raw exception details.

## Auth Gates

None.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` - 19 passed.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_prompt_builder.py -q` - 25 passed.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts tests/e2e/call-toolbar.spec.ts tests/e2e/call-summary.spec.ts --project=desktop-chromium` - 5 passed.
- Full combined plan verification command passed with the same results.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 03-10 can build on a complete local MVP call loop. Live OMEN/Android acceptance still belongs to the later Phase 3 verification plans that deploy and validate against real LAN/GPU/browser runtime.

## Self-Check: PASSED

- Created/modified files exist: `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`, `web-ui/server/app/api/calls.py`, `web-ui/server/app/domain/call_service.py`, `web-ui/server/app/domain/ai_backend_client.py`, `web-ui/client/src/lib/api/calls.ts`, `web-ui/client/src/lib/api/types.ts`, `web-ui/client/src/lib/call/client.ts`, `web-ui/client/src/lib/call/store.svelte.ts`, `web-ui/client/src/lib/components/call/CallTranscript.svelte`, `web-ui/client/src/routes/call/[threadId]/+page.svelte`, `web-ui/client/tests/e2e/call-start.spec.ts`, and this summary.
- Task and corrective commits exist in git history: `9bde0a1`, `f8ab977`, `e2c5443`, `a89bd06`.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-04-25*
