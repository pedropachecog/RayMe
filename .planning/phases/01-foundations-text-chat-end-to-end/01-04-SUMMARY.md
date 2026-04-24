---
phase: 01-foundations-text-chat-end-to-end
plan: "04"
subsystem: testing
tags: [character-cards, fixtures, png, pillow, xss]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Backend harness and card-import contracts from prior Phase 1 plans"
provides:
  - "Deterministic SillyTavern v2/v3 JSON card fixtures"
  - "Tiny valid PNG card fixtures with chara, ccv3, and dual-key metadata"
  - "Literal malicious card payload fixture for sanitizer and parser tests"
affects: [web-ui-server, character-import, sanitizer-tests, acceptance-fixtures]

tech-stack:
  added: []
  patterns: ["Pillow PngInfo tEXt chunk fixture generation", "read-only fixture verifier"]

key-files:
  created:
    - web-ui/server/tests/fixtures/make_card_fixtures.py
    - web-ui/server/tests/fixtures/cards/v2_card.json
    - web-ui/server/tests/fixtures/cards/v3_card.json
    - web-ui/server/tests/fixtures/cards/malicious_card.json
    - web-ui/server/tests/fixtures/cards/v2_card.png
    - web-ui/server/tests/fixtures/cards/v3_card.png
    - web-ui/server/tests/fixtures/cards/dual_chunk_prefers_ccv3.png
  modified: []

key-decisions:
  - "The fixture generator is the source of truth for both JSON payloads and PNG metadata fixtures."
  - "The dual PNG stores different names in chara and ccv3 so parser precedence is observable."
  - "Malicious payloads are preserved literally as fixture data for later sanitizer tests."

patterns-established:
  - "Card fixtures are regenerated with `make_card_fixtures.py` and verified with read-only `--verify`."
  - "PNG card fixtures embed base64 JSON in SillyTavern-compatible tEXt chunks."

requirements-completed: [REQ-13, REQ-16]

duration: 4 min
completed: 2026-04-24
---

# Phase 01 Plan 04: Card Fixture Corpus Summary

**Deterministic SillyTavern card fixture corpus covering v2/v3 JSON, PNG metadata, lorebook preservation, ccv3 precedence, and malicious payloads.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-24T03:59:33Z
- **Completed:** 2026-04-24T04:03:25Z
- **Tasks:** 1
- **Files modified:** 7

## Accomplishments

- Added a deterministic fixture generator with read-only verification for all card fixtures.
- Created v2 and v3 JSON fixtures containing core card fields, alternate greetings, and preserved lorebook/world-info data.
- Created v2, v3, and dual-key PNG fixtures with Pillow-generated tEXt metadata; the dual fixture includes both `chara` and `ccv3` with different names.
- Added a malicious JSON card fixture containing literal `<img src=x onerror=alert(1)>` and `javascript:alert(1)` payloads.

## Task Commits

1. **Task 1: Build JSON and PNG card fixtures** - `0b85120` (`feat(01-04)`)

**Plan metadata:** recorded in the final `docs(01-04)` summary commit.

## Files Created/Modified

- `web-ui/server/tests/fixtures/make_card_fixtures.py` - Generates JSON fixtures and Pillow PNG fixtures, then verifies them without writing in `--verify` mode.
- `web-ui/server/tests/fixtures/cards/v2_card.json` - Deterministic v2 card payload with alternate greetings and preserved lorebook/world-info data.
- `web-ui/server/tests/fixtures/cards/v3_card.json` - Deterministic v3 card payload with v3-only fields, alternate greetings, tags, and lorebook data.
- `web-ui/server/tests/fixtures/cards/malicious_card.json` - XSS payload fixture preserving dangerous HTML and JavaScript URL strings as inert data.
- `web-ui/server/tests/fixtures/cards/v2_card.png` - 1x1 PNG with a base64-encoded `chara` tEXt chunk.
- `web-ui/server/tests/fixtures/cards/v3_card.png` - 1x1 PNG with a base64-encoded `ccv3` tEXt chunk.
- `web-ui/server/tests/fixtures/cards/dual_chunk_prefers_ccv3.png` - 1x1 PNG with both `chara` and `ccv3` chunks and distinct character names.

## Decisions Made

- Kept fixture creation deterministic and script-owned so later parser and acceptance tests can regenerate identical files.
- Made `--verify` read-only and strict enough to detect drift in JSON text, PNG size/mode, expected metadata keys, literal malicious payloads, and dual-key names.
- Stored lorebook/world-info fixture data in card payloads only; no prompt or UI behavior was added in this plan.

## Verification

- `uv run --project web-ui/server python web-ui/server/tests/fixtures/make_card_fixtures.py` - PASS, generated 6 card fixture files.
- `uv run --project web-ui/server python web-ui/server/tests/fixtures/make_card_fixtures.py --verify` - PASS, verified 6 card fixture files.
- `rg "onerror=alert\\(1\\)|javascript:alert\\(1\\)|ccv3|chara|alternate_greetings" web-ui/server/tests/fixtures` - PASS.
- `uv run --project web-ui/server ruff check web-ui/server/tests/fixtures/make_card_fixtures.py` - PASS.
- `uv run --project web-ui/server python -c "... assert keys == ['ccv3', 'chara']"` - PASS for `dual_chunk_prefers_ccv3.png`.
- Fixture file existence check for all plan-listed paths - PASS.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

None.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The fixture corpus is ready for parser implementation, sanitizer tests, lorebook preservation checks, and imported-character acceptance flows. The orchestrator owns shared STATE and ROADMAP updates after the wave.

## Self-Check: PASSED

- Required fixture and summary files exist on disk.
- Task commit `0b85120` exists in git history.
- Verification commands passed after the task commit.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
