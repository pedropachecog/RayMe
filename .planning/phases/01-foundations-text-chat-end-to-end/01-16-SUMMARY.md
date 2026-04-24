---
phase: 01-foundations-text-chat-end-to-end
plan: "16"
subsystem: ui
tags: [sveltekit, svelte, true-dark, app-shell, vitest]

# Dependency graph
requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: SvelteKit static client scaffold from plan 01-05
provides:
  - True Dark CSS custom-property token system for the client
  - Shared AppShell with desktop rail, mobile bottom navigation, and status chip area
  - Shared StatusChip, GlassPanel, ConfirmDialog, and ToastStack primitives
  - Unit coverage for app-shell tokens, top-level routes, and mobile bottom navigation
affects: [phase-01-client-ui, phase-01-home, phase-01-gallery, phase-01-settings]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Svelte 5 runes-mode AppShell using `$app/state` and `$app/environment`
    - True Dark tokens centralized in `src/app.css`
    - Raw-source Vitest contract tests for shell labels and CSS token presence

key-files:
  created:
    - web-ui/client/src/app.css
    - web-ui/client/src/lib/components/AppShell.svelte
    - web-ui/client/src/lib/components/StatusChip.svelte
    - web-ui/client/src/lib/components/GlassPanel.svelte
    - web-ui/client/src/lib/components/ConfirmDialog.svelte
    - web-ui/client/src/lib/components/ToastStack.svelte
    - web-ui/client/tests/unit/app-shell.test.ts
  modified:
    - web-ui/client/src/routes/+layout.svelte
    - web-ui/client/src/routes/+page.svelte

key-decisions:
  - "Use a 240px desktop rail and fixed 64px mobile bottom nav with only Home, Gallery, and Settings."
  - "Expose real browser secure-context and media-device readiness in the shell, while leaving endpoint health as pending until the endpoint wiring plan."
  - "Keep shared primitives local Svelte components with accessible labels, focus states, and no additional dependencies."

patterns-established:
  - "Routes are wrapped by `AppShell` from `+layout.svelte`; route files should provide screen content only."
  - "Phase 1 shell navigation is scope-gated by tests and forbidden-label grep."
  - "Global UI values should use `src/app.css` custom properties instead of duplicating hex values in route styles."

requirements-completed: [REQ-70, REQ-90, REQ-A0, REQ-A1]

# Metrics
duration: 14min
completed: 2026-04-24
---

# Phase 01 Plan 16: True Dark App Shell Summary

**True Dark Svelte app shell with scoped Home/Gallery/Settings navigation, shared status/dialog/toast primitives, and unit coverage for the mobile nav contract.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-04-24T04:17:35Z
- **Completed:** 2026-04-24T04:31:19Z
- **Tasks:** 1
- **Files modified:** 9

## Accomplishments

- Centralized the Phase 1 True Dark palette, spacing scale, type sizes, focus treatment, and reduced-motion behavior in `web-ui/client/src/app.css`.
- Replaced the scaffolded inline layout shell with `AppShell`, including a 240px desktop rail, fixed 64px mobile bottom nav, active-route highlighting, and browser readiness status chips.
- Added shared `StatusChip`, `GlassPanel`, `ConfirmDialog`, and `ToastStack` primitives with accessible labels, keyboard focus, and destructive confirmation affordances.
- Kept Home operational and scope-correct: threads-first empty state, Phase 1 actions, and no marketing or future-feature navigation.
- Added `app-shell` unit tests that prove token presence, allowed top-level labels/routes, and exactly three mobile bottom navigation items.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement shell tokens and shared primitives** - `0031ee1` (feat)

**Plan metadata:** committed separately with this summary.

## Files Created/Modified

- `web-ui/client/src/app.css` - True Dark CSS custom properties and global app reset/focus/reduced-motion rules.
- `web-ui/client/src/lib/components/AppShell.svelte` - Desktop rail, mobile bottom nav, active route handling, browser readiness status area, and main content frame.
- `web-ui/client/src/lib/components/StatusChip.svelte` - Accessible compact status indicator with neutral, healthy, warning, and danger tones.
- `web-ui/client/src/lib/components/GlassPanel.svelte` - Reusable tonal glass panel primitive for later floating and panel surfaces.
- `web-ui/client/src/lib/components/ConfirmDialog.svelte` - Destructive confirmation dialog with Escape handling, backdrop close, focus cycling, and explicit destructive action styling.
- `web-ui/client/src/lib/components/ToastStack.svelte` - Accessible toast stack with live region and per-toast dismiss controls.
- `web-ui/client/src/routes/+layout.svelte` - Thin route wrapper that imports global CSS and delegates shell rendering to `AppShell`.
- `web-ui/client/src/routes/+page.svelte` - Scope-correct Home shell content using True Dark tokens and Phase 1 actions.
- `web-ui/client/tests/unit/app-shell.test.ts` - Contract tests for app-shell tokens, allowed nav routes, and mobile nav item count.

## Decisions Made

- Used the expanded 240px desktop rail option from the UI-SPEC for clearer first-pass navigation while preserving the required 64px mobile bottom nav.
- Used Svelte 5 runes mode in `AppShell` because `$app/state` is the current SvelteKit page-state API for reactive active-route behavior.
- Left endpoint health as a visible pending status because endpoint test wiring belongs to later Phase 1 Settings/API plans; browser secure-context and media-device readiness are checked directly in this plan.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Vitest's `?raw` CSS import returned an empty string in the token test; the test now reads `src/app.css` with Node `readFileSync`.
- Svelte rejected an initial dynamic icon cleanup because `{@const}` must be an immediate `{#each}` child; moving the declarations one level up resolved the build.

## Known Stubs

- `web-ui/client/src/lib/components/AppShell.svelte:77` - `Endpoint checks pending` is intentionally static until endpoint health wiring lands in the later Settings/API plan.
- `web-ui/client/src/routes/+page.svelte:56` - `Web UI status pending` is an intentional Home readiness placeholder until service status data is wired.
- `web-ui/client/src/routes/+page.svelte:60` - `AI backend pending` is an intentional Home readiness placeholder until service status data is wired.
- `web-ui/client/src/routes/+page.svelte:64` - `LLM endpoint pending` is an intentional Home readiness placeholder until service status data is wired.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run app-shell` - PASS, 3 tests passed.
- `npm --prefix web-ui/client run build` - PASS, adapter-static wrote the site to `build`.
- `npm --prefix web-ui/client run test:unit -- --run` - PASS, 7 tests passed across 3 files.
- True Dark token check - PASS, `app.css` contains all required hex values.
- Top-level nav label check - PASS, `AppShell.svelte` contains only `Home`, `Gallery`, and `Settings` route labels.
- Forbidden future-feature grep - PASS, `rg "Voice Lab|Call|Account|Billing|Logout|Subscribe" web-ui/client/src` returned no matches.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The client shell and shared UI primitives are ready for route-specific Home, Gallery, Settings, and Chat plans. Later endpoint-health wiring should replace the documented pending status copy without changing the shell navigation contract.

## Self-Check: PASSED

- Verified the summary and all created component/test/token files exist on disk.
- Verified task commit `0031ee1` exists in git history.
- Verified the task commit did not delete tracked files.
- Verified `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` were not modified by this executor.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
