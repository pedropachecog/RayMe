---
phase: 01-foundations-text-chat-end-to-end
plan: "21"
subsystem: ui
tags: [sveltekit, svelte, chat, sse, vitest, playwright]

# Dependency graph
requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 14 server-side SSE chat send endpoint with full done.message shape"
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 16 True Dark app shell and component conventions"
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 17 typed client API and SSE stream reader"
provides:
  - "GET /api/threads/{thread_id}-backed chat hydration route"
  - "Multiline text composer with Enter send and Shift+Enter newline"
  - "Sanitized message bubbles with selected alternates, alternate lists, stale flags, and streaming state"
  - "Client-side streaming send flow that replaces one AI draft bubble with the returned ThreadMessage"
affects: [phase-01-client-ui, text-chat, message-actions, e2e]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Chat route treats ThreadDetail as the canonical hydration and done-message shape"
    - "ChatMessageView extends ThreadMessage only with transient UI state"
    - "AI and alternate prose render through the existing sanitized Markdown renderer"

key-files:
  created:
    - web-ui/client/src/lib/api/chat.ts
    - web-ui/client/src/lib/components/ChatMessageBubble.svelte
    - web-ui/client/src/lib/components/Composer.svelte
    - web-ui/client/src/routes/chat/[threadId]/+page.svelte
    - web-ui/client/tests/unit/chat.test.ts
    - web-ui/client/tests/e2e/chat-stream.spec.ts
  modified: []

key-decisions:
  - "Chat displays persisted opening alternate state from thread hydration and has no post-create alternate-greeting switch path."
  - "The streaming send path keeps exactly one transient AI bubble and replaces it with the full ThreadMessage from onDone."
  - "Stream errors show the UI-SPEC LLM endpoint copy instead of provider/server error details."

patterns-established:
  - "Use loadThread(threadId) for chat route hydration rather than sharing Home thread summary state."
  - "Use selectedMessageContent() to resolve selected alternates consistently for opening greetings and later AI branches."
  - "Keep transient streaming/error fields outside persisted ThreadMessage fields so final done.message can be preserved exactly."

requirements-completed: [REQ-17, REQ-30, REQ-31, REQ-60, REQ-90, REQ-A0]

# Metrics
duration: 18min
completed: 2026-04-24
---

# Phase 01 Plan 21: Text Chat Route and Streaming Send Summary

**Thread-detail-backed Svelte chat route with sanitized message bubbles, multiline composer, one-bubble streaming, and done-message replacement.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-04-24T07:15:08Z
- **Completed:** 2026-04-24T07:33:01Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added `loadThread()` and `sendChatMessage()` client wrappers for exact thread hydration and SSE send routing.
- Implemented `/chat/[threadId]` with character portrait/name/title, chronological hydration, selected alternate rendering, stale indicators, no call action, and streaming send state.
- Added `ChatMessageBubble` and `Composer` components for sanitized AI/user prose, ordered alternates, opening selected-greeting labels, error recovery copy, multiline input, Enter send, and Shift+Enter newline.
- Added unit and browser E2E coverage for no call button, exact hydration route, persisted opening alternate display, one streaming bubble, final ThreadMessage replacement, and exact LLM error copy.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement chat route and streaming send** - `e51cf00` (feat)

**Plan metadata:** this summary is committed separately.

## Files Created/Modified

- `web-ui/client/src/lib/api/chat.ts` - Chat hydration/send API wrapper plus selected alternate and streaming draft helpers.
- `web-ui/client/src/lib/components/ChatMessageBubble.svelte` - Sanitized user/AI bubble rendering with alternates, selected greeting, stale state, streaming caret, and error affordance.
- `web-ui/client/src/lib/components/Composer.svelte` - Multiline composer with Enter send and Shift+Enter newline behavior.
- `web-ui/client/src/routes/chat/[threadId]/+page.svelte` - Text chat route with thread hydration, header, chronological messages, send flow, and error handling.
- `web-ui/client/tests/unit/chat.test.ts` - Unit contract coverage for chat API, hydration semantics, alternate handling, streaming replacement, error copy, and composer behavior.
- `web-ui/client/tests/e2e/chat-stream.spec.ts` - Playwright coverage for hydration, no call action, done-message replacement, preserved ThreadMessage fields, and stream failure UI.

## Decisions Made

- Used `GET /api/threads/{thread_id}` as the only initial chat hydration source so selected alternates, alternate lists, and stale flags match backend truth.
- Kept the opening alternate-greeting display read-only in Chat; alternate choice remains pre-create state from Home/Gallery thread creation.
- Reused `renderTrustedMarkdown()` in message bubbles to mitigate the plan's LLM-output-to-DOM threat boundary.

## Deviations from Plan

None - product implementation executed as planned.

## Issues Encountered

- The first Playwright run timed out waiting for its configured 60s webServer window because the production build took slightly longer than that in this environment. I verified `npm --prefix web-ui/client run build` separately, started `vite preview` from the built output, and reran the required `npm --prefix web-ui/client run test:e2e -- chat-stream.spec.ts` command successfully with Playwright reusing the live server.

## Known Stubs

None. Stub scan found only intentional transient empty-string resets, optional null props, and empty accumulators in tests.

## User Setup Required

None - no external service configuration required.

## Shared Orchestrator Artifacts

Per sequential wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run chat` - PASS, 6 tests.
- `npm --prefix web-ui/client run build` - PASS.
- `npm --prefix web-ui/client run test:e2e -- chat-stream.spec.ts` - PASS, 4 tests across desktop and mobile Chromium after preview reuse.
- `rg "loadThread|/api/threads/|selected_alternate_id|stale_after_edit|alternates|onDone" web-ui/client/src/lib/api/chat.ts web-ui/client/src/routes/chat/[threadId]/+page.svelte web-ui/client/tests/unit/chat.test.ts` - PASS.

## Next Phase Readiness

The base text chat route can hydrate persisted threads, stream a normal send, preserve backend-selected branches, and show recoverable LLM endpoint failures. Later message-action and virtualization plans can build on the `ThreadMessage`-preserving bubble and route state model.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-21-SUMMARY.md`.
- Key created files exist on disk.
- Task commit `e51cf00` exists in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remained untouched.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
