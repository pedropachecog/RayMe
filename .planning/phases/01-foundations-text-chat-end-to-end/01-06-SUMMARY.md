---
phase: 01-foundations-text-chat-end-to-end
plan: "06"
subsystem: testing
tags: [sveltekit, vitest, playwright, marked, dompurify, xss]

# Dependency graph
requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: SvelteKit client scaffold and frontend test tooling from plan 01-05
provides:
  - Sanitized Markdown rendering boundary for untrusted character prose
  - Vitest coverage for malicious card HTML, dangerous URL protocols, data attributes, styles, and safe Markdown
  - Unskipped Playwright acceptance shell specs for Phase 1 browser flows
affects: [phase-01-client-ui, phase-01-character-rendering, phase-01-e2e-acceptance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "marked.parse(..., { async: false }) followed by DOMPurify.sanitize for untrusted Markdown"
    - "Strict DOM allow-list enforcement for the Phase 1 character-prose Markdown subset"
    - "Unskipped Playwright shell specs that name backend-generated regenerate, swipe, and continue contracts"

key-files:
  created:
    - web-ui/client/src/lib/sanitizer/renderMarkdown.ts
    - web-ui/client/tests/unit/sanitizer.test.ts
    - web-ui/client/tests/e2e/import-chat-reload.spec.ts
    - web-ui/client/tests/e2e/home-start-chat.spec.ts
    - web-ui/client/tests/e2e/https-status.spec.ts
    - web-ui/client/tests/e2e/mobile-text.spec.ts
    - web-ui/client/tests/e2e/ui-contract.spec.ts
  modified:
    - web-ui/client/vitest.config.ts

key-decisions:
  - "Keep the sanitizer boundary narrowly scoped to prose-safe Markdown tags and link attributes."
  - "Discover plan-mandated `tests/unit` files through Vitest instead of moving the test under `src`."
  - "Keep E2E acceptance shells unskipped while naming backend-generated response contracts for later implementation plans."

patterns-established:
  - "Character prose must flow through `renderTrustedMarkdown` before any HTML rendering."
  - "E2E shell specs may name future acceptance contracts without `test.skip`, `test.fixme`, or `test.todo`."

requirements-completed: [REQ-13, REQ-16, REQ-17, REQ-30, REQ-32, REQ-34, REQ-35, REQ-36, REQ-90, REQ-A0, REQ-A1]

# Metrics
duration: 8min
completed: 2026-04-24
---

# Phase 01 Plan 06: Sanitizer Boundary And Acceptance Shells Summary

**Sanitized Markdown boundary for imported character prose plus unskipped Playwright shells for Phase 1 text-chat acceptance flows.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-24T04:06:12Z
- **Completed:** 2026-04-24T04:14:07Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added `renderTrustedMarkdown` for untrusted character/card prose using `marked` and `DOMPurify`, restricted to the Phase 1 prose-safe Markdown subset.
- Added sanitizer unit tests covering image handlers, script tags, dangerous link protocols, `data-*` attributes, inline styles, and safe Markdown formatting.
- Added five unskipped Playwright acceptance shell specs with exact Phase 1 test titles and backend-generated regenerate/swipe/continue contract text.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement sanitized Markdown rendering** - `0440f16` (feat)
2. **Task 2: Add unskipped Playwright acceptance shells** - `3fc6a61` (test)

**Plan metadata:** committed separately with this summary.

## Files Created/Modified

- `web-ui/client/src/lib/sanitizer/renderMarkdown.ts` - untrusted Markdown to sanitized HTML boundary.
- `web-ui/client/tests/unit/sanitizer.test.ts` - Vitest coverage for XSS and safe Markdown behavior.
- `web-ui/client/vitest.config.ts` - includes plan-mandated `tests/unit` specs.
- `web-ui/client/tests/e2e/import-chat-reload.spec.ts` - imported character chat/reload/continue shell.
- `web-ui/client/tests/e2e/home-start-chat.spec.ts` - Home to real character selection chat shell.
- `web-ui/client/tests/e2e/https-status.spec.ts` - secure-context and media-device status shell.
- `web-ui/client/tests/e2e/mobile-text.spec.ts` - mobile import/chat/reload/continue shell.
- `web-ui/client/tests/e2e/ui-contract.spec.ts` - Phase 1 no-future-controls shell.

## Decisions Made

- Preserved only `p`, `br`, `strong`, `em`, `code`, `pre`, `blockquote`, `ul`, `ol`, `li`, and `a` in rendered Markdown, with only `href` and `title` attributes.
- Allowed safe relative links plus `http`, `https`, and `mailto` protocols; stripped dangerous protocols such as `javascript:`.
- Kept acceptance shells unskipped and contract-focused so later screen/API plans can replace shell assertions with browser-visible behavior.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Included plan-mandated unit test directory in Vitest discovery**
- **Found during:** Task 1 (Implement sanitized Markdown rendering)
- **Issue:** The existing Vitest config only discovered `src/**/*.{test,spec}.{js,ts}`, while the plan required `web-ui/client/tests/unit/sanitizer.test.ts`.
- **Fix:** Added `tests/unit/**/*.{test,spec}.{js,ts}` to the Vitest include patterns.
- **Files modified:** `web-ui/client/vitest.config.ts`
- **Verification:** `npm --prefix web-ui/client run test:unit -- --run sanitizer`
- **Committed in:** `0440f16`

**2. [Rule 1 - Bug] Added strict DOM allow-list enforcement after DOMPurify**
- **Found during:** Task 1 (Implement sanitized Markdown rendering)
- **Issue:** In the Happy DOM Vitest environment, DOMPurify did not enforce the configured tag/attribute allow-list, leaving script and styled span markup in the rendered output.
- **Fix:** Kept the required `marked -> DOMPurify.sanitize` path and added a DOM-based allow-list pass that removes dangerous raw-text tags, unwraps unsupported formatting tags, removes disallowed attributes, and strips unsafe link protocols.
- **Files modified:** `web-ui/client/src/lib/sanitizer/renderMarkdown.ts`
- **Verification:** `npm --prefix web-ui/client run test:unit -- --run sanitizer`
- **Committed in:** `0440f16`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes were required for the planned test location and for the sanitizer boundary to be provable in the current unit environment. The shipped boundary still follows the required `marked.parse` then `DOMPurify.sanitize` flow.

## Issues Encountered

- The first sanitizer test failed because DOMPurify returned raw script/span markup under Happy DOM. The strict DOM allow-list pass resolved it and the sanitizer tests now pass.

## Known Stubs

None - no TODO/FIXME/placeholder UI stubs were introduced. The Playwright files are intentionally acceptance shell specs per this plan.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run sanitizer` - PASS, 1 file and 3 tests passed.
- `rg "imported character chat reloads and continues|home starts chat through real character selection|secure context and media device status are visible|mobile viewport can import chat reload and continue|phase 1 ui omits future controls|backend-generated|regenerate|swipe|continue" web-ui/client/tests/e2e` - PASS.
- `test "$(rg "test\\.(skip|fixme|todo)" web-ui/client/tests/e2e -c | awk -F: '{s+=$2} END {print s+0}')" = "0"` - PASS.
- `npm --prefix web-ui/client run test:e2e -- --list` - PASS, 10 tests listed across desktop and mobile projects.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The sanitizer boundary is ready for Gallery, Editor, and Chat rendering plans. The E2E shell specs now name the Phase 1 browser acceptance flows without skipped placeholders and can be expanded as the real screens and backend APIs land.

## Self-Check: PASSED

- Verified every created sanitizer/test/spec/summary file exists on disk.
- Verified task commits `0440f16` and `3fc6a61` exist in git history.
- Verified no tracked files were deleted by the task commits.
- Verified `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified by this plan.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
