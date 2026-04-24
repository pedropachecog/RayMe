---
phase: 01-foundations-text-chat-end-to-end
plan: "18"
subsystem: ui
tags: [sveltekit, svelte, home, threads, api-client, vitest]

# Dependency graph
requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plans 12 and 13 character/thread APIs plus Plans 16 and 17 shell/API client foundation"
provides:
  - "Threads-first Home dashboard using real thread and character API wrappers"
  - "Recent thread rows with portrait/name/title/snippet/timestamp and rename/delete actions"
  - "Start Chat flow with character selection, alternate greeting selection, and /chat/{thread_id} navigation"
  - "Home contract tests for thread rows, Start Chat, alternate greetings, rename/delete, and scope controls"
affects: [phase-01-home, phase-01-chat, phase-01-gallery, phase-01-client-api]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Home route loads thread summaries through `listThreads()` on mount"
    - "Thread mutations route through `renameThread()` and `deleteThread()` wrappers"
    - "Raw-source plus API-contract Vitest coverage follows the existing client test pattern"

key-files:
  created:
    - web-ui/client/src/lib/components/ThreadListItem.svelte
    - web-ui/client/tests/unit/home.test.ts
  modified:
    - web-ui/client/src/routes/+page.svelte
    - web-ui/client/src/lib/api/threads.ts
    - web-ui/client/src/lib/api/characters.ts
    - web-ui/client/src/lib/api/types.ts

key-decisions:
  - "Start Chat opens a real character picker loaded from `listCharacters()` and routes to `/gallery` only when no characters exist."
  - "Alternate greeting indices are included in `createThread()` payloads only when the user selects an alternate."
  - "Client list wrappers now accept backend `{ items }` envelopes while preserving bare-array compatibility for tests/future adapters."

patterns-established:
  - "Thread list rows live in `ThreadListItem.svelte` and receive callback props for open/menu/rename/delete actions."
  - "Home destructive thread deletion uses the shared `ConfirmDialog` with the required copy."
  - "Home tests pair raw route/component assertions with exact API wrapper method/route assertions."

requirements-completed: [REQ-70, REQ-71, REQ-72, REQ-90, REQ-A0]

# Metrics
duration: 21min
completed: 2026-04-24
---

# Phase 01 Plan 18: Home Threads Dashboard Summary

**Threads-first Home dashboard with real thread CRUD actions, character-based chat creation, alternate greeting selection, and scoped Phase 1 controls.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-04-24T06:03:43Z
- **Completed:** 2026-04-24T06:23:55Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Replaced the placeholder Home route with a threads-first dashboard that fetches `GET /api/threads` through `listThreads()` and renders recent thread rows.
- Added `ThreadListItem.svelte` with portrait/fallback initials, character name, title fallback, snippet, relative timestamp, and contextual `Rename`/`Delete` actions.
- Implemented `Start Chat` through real character loading, `/gallery` routing when no characters exist, selected-character enforcement, optional alternate greeting selection, `createThread()`, and `/chat/{thread_id}` navigation.
- Added thread rename/delete API wrappers and destructive confirmation copy exactly matching the UI contract.
- Added Home unit coverage for thread row contract, no-character gallery routing, `POST /api/threads`, alternate greeting payloads, exact rename/delete routes, and required delete confirmation copy.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Home threads list and start-chat entry** - `9463ec3` (`feat`)

**Plan metadata:** this summary is committed separately.

## Files Created/Modified

- `web-ui/client/src/routes/+page.svelte` - Threads-first Home route with thread loading, character picker, alternate greeting picker, rename dialog, delete confirmation, and Phase 1 actions.
- `web-ui/client/src/lib/components/ThreadListItem.svelte` - Reusable recent-thread row with portrait/name/title/snippet/timestamp and contextual menu.
- `web-ui/client/src/lib/api/threads.ts` - Added list-envelope handling plus `renameThread()` and `deleteThread()` wrappers.
- `web-ui/client/src/lib/api/characters.ts` - Added list-envelope handling for Home's character picker.
- `web-ui/client/src/lib/api/types.ts` - Added list response, thread rename/delete, and backend portrait metadata types.
- `web-ui/client/tests/unit/home.test.ts` - Home contract tests for thread rows, Start Chat, alternate greetings, rename/delete, and confirmation copy.

## Decisions Made

- Home routes `Import Character` and `Create Character` to `/gallery` because the Gallery plan owns import/create focus handling.
- The Home tests use the repo's existing raw-source plus API-wrapper test style. A low-level Svelte mount test was attempted, but Vitest hung during collection for the route component in this setup.
- The stale static Home readiness panel from the shell placeholder was removed rather than carried forward as a documented stub; endpoint readiness belongs to Settings/shell wiring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed client list wrappers for backend envelope responses**
- **Found during:** Task 1 (Implement Home threads list and start-chat entry)
- **Issue:** `listThreads()` and `listCharacters()` expected bare arrays, but the implemented backend routes return `{ "items": [...] }`. Home would not render threads or characters correctly through the real APIs.
- **Fix:** Updated both wrappers to unwrap `{ items }` responses while preserving bare-array compatibility.
- **Files modified:** `web-ui/client/src/lib/api/threads.ts`, `web-ui/client/src/lib/api/characters.ts`, `web-ui/client/src/lib/api/types.ts`
- **Verification:** `npm --prefix web-ui/client run test:unit -- --run home`; `npm --prefix web-ui/client run test:unit -- --run api`; `npm --prefix web-ui/client run test:unit -- --run`
- **Committed in:** `9463ec3`

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** The fix was required for Home to use the real Phase 1 backend list routes. No new backend surface or architecture change was introduced.

## Issues Encountered

- Low-level DOM mounting of the Svelte route in Vitest hung during collection. The final tests follow the established client pattern by combining raw route/component assertions with exact API wrapper request assertions.

## Known Stubs

None. Stub scan found only internal state initializers (`[]`/`null`) and decorative empty `alt` attributes for hidden portrait images.

## User Setup Required

None - no external service configuration required.

## Shared Orchestrator Artifacts

Per sequential wave executor instructions, `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run home` - PASS, 5 tests.
- `rg "Start Chat|createThread|alternate_greeting_index|/chat/|Import Character|Create Character|Delete this thread\\? This removes the conversation history\\.|/api/threads" web-ui/client/src web-ui/client/tests/unit/home.test.ts` - PASS.
- `rg "Voice Lab|Call|Account|Billing|Logout|usage stats|quick-start" web-ui/client/src/routes/+page.svelte web-ui/client/src/lib/components` - PASS, no matches.
- `npm --prefix web-ui/client run test:unit -- --run api` - PASS, 7 tests.
- `npm --prefix web-ui/client run test:unit -- --run app-shell` - PASS, 3 tests.
- `npm --prefix web-ui/client run test:unit -- --run` - PASS, 23 tests across 6 files.
- `npm --prefix web-ui/client run build` - PASS.

## Threat Flags

None. The plan uses existing `/api/threads` and `/api/characters` client boundaries and adds no new network endpoints, auth paths, file access patterns, or schema changes.

## Next Phase Readiness

Chat can now receive `/chat/{thread_id}` navigation from Home-created threads. Gallery can provide richer import/create focus behavior later without changing Home's Start Chat contract.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-18-SUMMARY.md`.
- Key created files exist on disk.
- Task commit `9463ec3` exists in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` remained untouched.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
