---
phase: 01-foundations-text-chat-end-to-end
plan: "05"
subsystem: ui
tags: [sveltekit, svelte, vite, vitest, playwright, static-spa]

# Dependency graph
requires:
  - phase: 00-measurement-gate
    provides: HTTPS/LAN decisions and Phase 1 stack constraints
provides:
  - SvelteKit 2 / Svelte 5 static SPA scaffold under web-ui/client
  - adapter-static fallback build with SSR disabled for browser-only client execution
  - pinned frontend dependencies and unit/e2e/build/check scripts
  - minimal RayMe app-shell entry route without future-scope controls
affects: [phase-01-client-ui, phase-01-shell, phase-01-client-tests]

# Tech tracking
tech-stack:
  added:
    - "@sveltejs/kit@2.58.0"
    - "svelte@5.55.5"
    - "@sveltejs/adapter-static@3.0.10"
    - "vite@8.0.10"
    - "lucide-svelte@1.0.1"
    - "marked@18.0.2"
    - "dompurify@3.4.1"
    - "@tanstack/svelte-virtual@3.13.24"
    - "vitest@4.1.5"
    - "happy-dom@20.9.0"
    - "@playwright/test@1.59.1"
  patterns:
    - adapter-static SPA fallback with `fallback: '200.html'`
    - route-level `ssr = false` for static browser execution
    - local True Dark app-shell styling with lucide-svelte icons

key-files:
  created:
    - web-ui/client/package.json
    - web-ui/client/package-lock.json
    - web-ui/client/svelte.config.js
    - web-ui/client/vite.config.ts
    - web-ui/client/vitest.config.ts
    - web-ui/client/playwright.config.ts
    - web-ui/client/tsconfig.json
    - web-ui/client/src/app.html
    - web-ui/client/src/routes/+layout.ts
    - web-ui/client/src/routes/+layout.svelte
    - web-ui/client/src/routes/+page.svelte
    - web-ui/client/src/tests/app-entry.test.ts
  modified:
    - .gitignore

key-decisions:
  - "Use adapter-static with `fallback: '200.html'` and `ssr = false` for the Phase 1 static SPA."
  - "Keep the first visible route as an operational RayMe shell entry, not a marketing page."
  - "Use an npm override for transitive `cookie@0.7.2` while preserving all direct plan-pinned dependency versions."

patterns-established:
  - "Client generated artifacts are ignored under `web-ui/client/node_modules`, `.svelte-kit`, `build`, `playwright-report`, and `test-results`."
  - "Vitest smoke tests live outside SvelteKit `src/routes` so reserved `+` route filenames are not used for tests."

requirements-completed: [REQ-10, REQ-30, REQ-70, REQ-90, REQ-A0, REQ-A1]

# Metrics
duration: 11min
completed: 2026-04-24
---

# Phase 01 Plan 05: SvelteKit Static Client Scaffold Summary

**SvelteKit 2 / Svelte 5 static SPA scaffold with adapter-static fallback, SSR disabled, pinned test tooling, and a scoped RayMe app entry.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-24T03:24:53Z
- **Completed:** 2026-04-24T03:36:08Z
- **Tasks:** 1
- **Files modified:** 13

## Accomplishments

- Created the `web-ui/client` SvelteKit static SPA project with exact plan-pinned dependency versions and reproducible npm lockfile.
- Configured `adapter-static` with `fallback: '200.html'` and disabled SSR in `+layout.ts`.
- Added a minimal True Dark RayMe app-shell route with Home, Gallery, and Settings navigation only.
- Added Vitest, Playwright, Vite, and SvelteKit config files plus a unit smoke test for the app entry.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create SvelteKit static app scaffold** - `288ab43` (feat)

**Plan metadata:** committed separately with this summary.

## Files Created/Modified

- `.gitignore` - ignores generated client dependencies, SvelteKit output, build output, and browser test artifacts.
- `web-ui/client/package.json` - pinned SvelteKit/Svelte/Vite/runtime/test dependencies and scripts.
- `web-ui/client/package-lock.json` - npm lockfile for the pinned client dependency graph.
- `web-ui/client/svelte.config.js` - static adapter config with SPA fallback.
- `web-ui/client/vite.config.ts` - SvelteKit Vite plugin config.
- `web-ui/client/vitest.config.ts` - Vitest config using `happy-dom`.
- `web-ui/client/playwright.config.ts` - desktop/mobile browser project config and static preview server.
- `web-ui/client/tsconfig.json` - SvelteKit TypeScript project config.
- `web-ui/client/src/app.html` - required SvelteKit document shell.
- `web-ui/client/src/routes/+layout.ts` - disables SSR for static client execution.
- `web-ui/client/src/routes/+layout.svelte` - RayMe app shell, nav rail, mobile nav, and status chips.
- `web-ui/client/src/routes/+page.svelte` - operational Home entry route with empty thread state and Phase 1 actions.
- `web-ui/client/src/tests/app-entry.test.ts` - Vitest smoke coverage for the app entry copy.

## Decisions Made

- Used the plan's exact direct dependency versions and added only a transitive npm override for `cookie@0.7.2` to clear the audit finding.
- Added `src/app.html` even though it was not listed in the plan files because SvelteKit cannot build without it.
- Added `package-lock.json` for reproducible installs from the pinned package graph.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added required SvelteKit document shell and generated-output ignores**
- **Found during:** Task 1 (Create SvelteKit static app scaffold)
- **Issue:** The plan listed route and config files but not `src/app.html`, which SvelteKit requires for a successful build. Installing/building also produced generated directories that needed to stay out of git.
- **Fix:** Added `web-ui/client/src/app.html` and `.gitignore` entries for generated client output.
- **Files modified:** `.gitignore`, `web-ui/client/src/app.html`
- **Verification:** `npm --prefix web-ui/client run build`
- **Committed in:** `288ab43`

**2. [Rule 2 - Missing Critical] Cleared transitive npm audit vulnerability**
- **Found during:** Task 1 (Create SvelteKit static app scaffold)
- **Issue:** `npm audit` reported a low-severity `cookie` advisory through the pinned SvelteKit dependency graph.
- **Fix:** Added an npm `overrides` entry for `cookie@0.7.2`, preserving all direct plan-pinned dependency versions.
- **Files modified:** `web-ui/client/package.json`, `web-ui/client/package-lock.json`
- **Verification:** `npm --prefix web-ui/client audit --json` reports zero vulnerabilities.
- **Committed in:** `288ab43`

**3. [Rule 1 - Bug] Moved unit smoke test out of reserved route filename**
- **Found during:** Task 1 (Create SvelteKit static app scaffold)
- **Issue:** An initial smoke test named with a `+` route prefix triggered SvelteKit's reserved route-file warning and failed under Vitest.
- **Fix:** Moved the test to `src/tests/app-entry.test.ts` and used a Vite raw import for the Svelte page source.
- **Files modified:** `web-ui/client/src/tests/app-entry.test.ts`
- **Verification:** `npm --prefix web-ui/client run test:unit -- --run`
- **Committed in:** `288ab43`

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 missing critical, 1 bug)
**Impact on plan:** The fixes were required for buildability, security hygiene, and a non-empty unit test gate. The scaffold scope stayed limited to plan 01-05.

## Issues Encountered

- `npm audit` initially reported 3 low-severity findings via `cookie`; resolved with an override.
- Vitest initially failed when the smoke test lived under a reserved `+page.test.ts` route filename; resolved by moving it to `src/tests`.

## Known Stubs

- `web-ui/client/src/routes/+layout.svelte` uses static `Secure pending` and `Endpoints pending` chips. These are intentional scaffold placeholders for later browser readiness and endpoint-health wiring in plans 01-16, 01-17, and 01-20.
- `web-ui/client/src/routes/+page.svelte` uses a static empty thread state and readiness list. This is intentional for the scaffold plan; backend data wiring is owned by later Home/API plans.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run` - PASS, 1 test passed.
- `npm --prefix web-ui/client run build` - PASS, adapter-static wrote site to `build`.
- `npm --prefix web-ui/client run check` - PASS.
- `npm --prefix web-ui/client audit --json` - PASS, 0 vulnerabilities.
- Exact package version assertion - PASS.
- `rg "adapter-static|fallback: '200.html'" web-ui/client/svelte.config.js` - PASS.
- `rg "ssr = false" web-ui/client/src/routes/+layout.ts` - PASS.
- `rg "Voice Lab|Call|Account|Billing|Logout" web-ui/client/src` - PASS, no matches.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The static client scaffold is ready for the Phase 1 client shell, sanitizer, API wrapper, Home, Gallery, Editor, Chat, and Settings plans. Shared orchestrator files were not updated by this executor.

## Self-Check: PASSED

- Verified every created summary/client file exists on disk.
- Verified task commit `288ab43` exists in git history.
- Verified no tracked files were deleted by the task commit.
- Verified `.planning/STATE.md` and `.planning/ROADMAP.md` were not staged or updated by this plan.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
