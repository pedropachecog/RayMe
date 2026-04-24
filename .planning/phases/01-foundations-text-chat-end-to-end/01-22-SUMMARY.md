---
phase: 01-foundations-text-chat-end-to-end
plan: "22"
subsystem: ui
tags: [sveltekit, svelte, chat, message-actions, branching, vitest]

# Dependency graph
requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 15 LLM-backed message action routes returning ThreadMessageShape payloads"
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 21 thread-detail-backed chat route, composer, and message bubble conventions"
provides:
  - "Backend-backed per-message Regenerate, Swipe, Edit, and Continue actions"
  - "Swipe stepper that selects/generates backend alternates while keeping only the selected response canonical"
  - "Inline edit flow with downstream stale UI and truncate-or-keep confirmation before Continue"
affects: [phase-01-client-ui, text-chat, message-actions, branching, mobile-chat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Message action UI consumes backend-returned ThreadMessage objects through typed client wrappers"
    - "Visible chat turns are updated by replacing/upserting backend message shapes rather than fabricating local alternates"
    - "Continue uses the composer draft as backend composer_text and clears it only after success"

key-files:
  created:
    - web-ui/client/src/lib/components/MessageActionMenu.svelte
    - web-ui/client/src/lib/components/SwipeStepper.svelte
  modified:
    - web-ui/client/src/lib/api/chat.ts
    - web-ui/client/src/lib/components/ChatMessageBubble.svelte
    - web-ui/client/src/lib/components/Composer.svelte
    - web-ui/client/src/routes/chat/[threadId]/+page.svelte
    - web-ui/client/tests/unit/chat.test.ts

key-decisions:
  - "Keep message action mutations backend-backed: regenerate, swipe, edit, stale resolution, and continue all use /api/messages routes."
  - "Render only the selected AI alternate as canonical content; expose previous/current/next/generate controls through SwipeStepper."
  - "When Continue is triggered with stale downstream turns, require the truncate-or-keep choice before calling backend continue."

patterns-established:
  - "Use messageActionsForRole() as the single role-to-action contract for chat message menus."
  - "Use upsertBackendMessage() and applyEditedBackendMessage() to keep route state aligned with returned ThreadMessage payloads."
  - "Use Composer value/onDraftChange only where parent route logic needs the current draft, such as Continue."

requirements-completed: [REQ-32, REQ-33, REQ-34, REQ-35, REQ-90, REQ-A0]

# Metrics
duration: 14min
completed: 2026-04-24
---

# Phase 01 Plan 22: Chat Message Actions Summary

**Backend-backed chat message actions with generated alternates, selected-branch swipes, inline edit stale-state UI, and composer-driven Continue.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-04-24T07:38:30Z
- **Completed:** 2026-04-24T07:51:39Z
- **Tasks:** 1
- **Files modified:** 7

## Accomplishments

- Added typed client wrappers for regenerate, generated swipe, alternate selection, edit, truncate stale, keep stale, and continue.
- Added `MessageActionMenu` and `SwipeStepper` components matching the Phase 1 chat action contract.
- Wired the chat route to replace visible turns with backend-returned messages, open inline editing, mark downstream stale rows, and prompt with the exact truncate-or-keep copy before continuing stale branches.
- Expanded chat unit coverage for role-specific menus, regenerate replacement, swipe generation/selection, continue composer payloads, and stale UI behavior.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement backend-backed message action UI** - `267a1c4` (`feat`)

**Plan metadata:** this summary is committed separately.

## Files Created/Modified

- `web-ui/client/src/lib/api/chat.ts` - Message-action API wrappers, role action metadata, selected-alternate helpers, and backend message replacement helpers.
- `web-ui/client/src/lib/components/MessageActionMenu.svelte` - Per-role overflow menu for Regenerate, Swipe, Edit, Continue, and user Edit-only action surfaces.
- `web-ui/client/src/lib/components/SwipeStepper.svelte` - Compact previous/current/next/generate alternate control for AI turns.
- `web-ui/client/src/lib/components/ChatMessageBubble.svelte` - Inline edit UI, action menu anchor, stale chip/rail integration, and selected-only swipe rendering.
- `web-ui/client/src/lib/components/Composer.svelte` - Optional controlled draft callback so Continue can consume current composer text.
- `web-ui/client/src/routes/chat/[threadId]/+page.svelte` - Backend-backed action handlers, stale truncate/keep confirmation, and composer-driven Continue flow.
- `web-ui/client/tests/unit/chat.test.ts` - Unit contract coverage for message actions, backend-returned generated responses, stale flags, and continue payloads.

## Decisions Made

- Used the backend `/api/messages/{message_id}` action routes from Plan 15 for every message mutation instead of local-only UI state.
- Replaced the previous visible alternate list with a swipe stepper so only the selected alternate is canonical in the message stack.
- Kept stale downstream marking immediate in the route by applying backend edit semantics locally to existing hydrated messages after the edit response.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Svelte warnings in new action UI**
- **Found during:** Task 1 (Implement backend-backed message action UI)
- **Issue:** The first build passed but warned about a noninteractive `section` using `role="dialog"` and Composer initializing `$state` from a prop.
- **Fix:** Changed the stale confirmation container to a `div` with dialog role and initialized Composer draft state independently before syncing from the value prop.
- **Files modified:** `web-ui/client/src/routes/chat/[threadId]/+page.svelte`, `web-ui/client/src/lib/components/Composer.svelte`
- **Verification:** `npm --prefix web-ui/client run build` reran successfully without those Svelte warnings.
- **Committed in:** `267a1c4`

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** The auto-fix removed warnings caused by the planned implementation. No scope expansion or architecture change.

## Issues Encountered

- Initial client build surfaced two Svelte warnings from the new modal/composer code. They were fixed before the task commit and the build was rerun successfully.

## Known Stubs

None. Stub scan only found intentional empty defaults, null UI state resets, and test accumulators.

## Threat Flags

None. The new network calls are the planned message action UI -> backend trust boundary already covered by T-01-22-BRANCH, T-01-22-STREAM, and T-01-22-MOBILE.

## User Setup Required

None - no external service configuration required.

## Shared Orchestrator Artifacts

Per sequential wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run chat` - PASS, 11 tests.
- `rg "Regenerate|Swipe|Edit|Continue|Stale|Remove stale turns after this edit\\?|generated alternate|selected_alternate_id" web-ui/client/src web-ui/client/tests/unit/chat.test.ts` - PASS.
- `npm --prefix web-ui/client run build` - PASS.
- `git diff --check -- web-ui/client/src/lib/api/chat.ts web-ui/client/src/lib/components/ChatMessageBubble.svelte web-ui/client/src/lib/components/Composer.svelte web-ui/client/src/lib/components/MessageActionMenu.svelte web-ui/client/src/lib/components/SwipeStepper.svelte web-ui/client/src/routes/chat/[threadId]/+page.svelte web-ui/client/tests/unit/chat.test.ts` - PASS.

## Next Phase Readiness

The chat route now exposes the complete Phase 1 text action surface against backend-generated action responses. Later virtualization or E2E plans can treat `ThreadMessage` replacement/upsert helpers and the role action contract as the frontend boundary for branch-safe message mutations.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-22-SUMMARY.md`.
- Key created and modified files exist on disk.
- Task commit `267a1c4` exists in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remained untouched.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
