---
phase: 01-foundations-text-chat-end-to-end
plan: "03"
subsystem: backend-contracts
tags: [pytest, fastapi, character-cards, settings, health]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 01 backend FastAPI/pytest harness"
provides:
  - "Character-card import and v2 export interface modules"
  - "Collectable contracts for v2/v3 JSON, v2/v3 PNG, ccv3 precedence, malformed rejection, raw source preservation, and lorebook preservation"
  - "Collectable contracts for character delete snapshot preservation and health/settings status behavior"
affects: [web-ui-server, character-import, character-export, settings-api, prompt-boundaries]

tech-stack:
  added: []
  patterns:
    - "Contract-first backend tests collect before parser, CRUD, and settings route implementation"
    - "Card import results keep untrusted stored data separate from rendered HTML"
    - "LLM status is represented by a server-side Settings probe, not a local LLM service"

key-files:
  created:
    - web-ui/server/app/domain/cards.py
    - web-ui/server/app/domain/card_export.py
    - web-ui/server/tests/test_card_import.py
    - web-ui/server/tests/test_card_export.py
    - web-ui/server/tests/test_characters.py
    - web-ui/server/tests/test_health_settings.py
  modified: []

key-decisions:
  - "Card parsing contracts preserve raw source JSON and mark card prose as untrusted data for later sanitized rendering."
  - "Imported lorebook/world-info data is preserved and reported as present, but excluded from prompt-ready character fields in v1."
  - "Settings contracts use exactly Connected, Unreachable, Unauthorized, and Not configured for endpoint status."
  - "LLM connection status is tested through POST /api/settings/test/llm against the configured OpenAI-compatible endpoint."

patterns-established:
  - "PNG card import prefers the ccv3 tEXt chunk before chara and rejects malformed metadata without traceback leakage."
  - "Character delete contracts require soft-delete or detach behavior that preserves existing thread snapshots."
  - "Browser-facing settings payloads must never include the raw LLM API key."

requirements-completed: [REQ-01, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-16]

duration: 5min
completed: 2026-04-24
---

# Phase 01 Plan 03: Backend Card, Character, And Settings Contract Summary

**Collectable backend contracts for safe SillyTavern card import/export, character delete preservation, and Settings-based endpoint health probes.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-24T03:51:27Z
- **Completed:** 2026-04-24T03:56:55Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added `parse_character_card_bytes` and related card import result types covering JSON/PNG source formats, raw source preservation, lorebook preservation, untrusted field tracking, and safe malformed rejection.
- Added `export_character_v2_json` as the Phase 1 JSON-only export interface and test coverage that keeps v3 PNG export out of scope.
- Added non-skipped backend tests for v2/v3 JSON cards, v2/v3 PNG cards, `ccv3` precedence over `chara`, malicious HTML as stored data only, safe character delete snapshot preservation, and lorebook present-not-used behavior.
- Added health/settings contract tests for Web UI health, AI-backend `/health` probing, exact endpoint status labels, server-side LLM probing, and raw API key masking.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write card and character contracts** - `30d4933` (`feat(01-03)`)
2. **Task 2: Write health and settings contracts** - `b2c5412` (`feat(01-03)`)

**Plan metadata:** recorded in the final `docs(01-03)` summary commit.

## Files Created/Modified

- `web-ui/server/app/domain/cards.py` - Character-card import result types, parser interface, safe delete result type, and delete preservation interface.
- `web-ui/server/app/domain/card_export.py` - v2 JSON export interface and export error type.
- `web-ui/server/tests/test_card_import.py` - Card parser contracts for v2/v3 JSON, v2/v3 PNG, `ccv3` precedence, malformed rejection, malicious HTML data preservation, and lorebook preservation.
- `web-ui/server/tests/test_card_export.py` - v2 JSON export contract that omits v3 PNG export and rendered HTML fields.
- `web-ui/server/tests/test_characters.py` - Character delete contract requiring existing thread snapshots to survive deletion.
- `web-ui/server/tests/test_health_settings.py` - Health/settings contracts for status values, AI-backend probing, raw key masking, and server-side LLM probe behavior.
- `.planning/phases/01-foundations-text-chat-end-to-end/01-03-SUMMARY.md` - Execution summary.

## Decisions Made

- Kept the backend modules as importable contract interfaces with intentional `NotImplementedError` bodies, matching the plan's "contracts before feature code lands" scope.
- Represented parser output as storage-oriented data rather than render output so malicious card HTML remains inert until the later sanitized UI boundary.
- Locked the LLM status interpretation to `POST /api/settings/test/llm`; no local `llm` FastAPI app or local LLM `/health` endpoint was created.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests --collect-only -q` - PASS, 29 tests collected.
- `rg "test_png_prefers_ccv3_over_chara|test_malformed_png_metadata_rejected_without_traceback|test_malicious_card_html_is_preserved_as_data_not_executed|test_v2_export_omits_v3_png_export|test_character_delete_preserves_existing_thread_snapshot|test_import_response_reports_lorebook_present_not_used" web-ui/server/tests` - PASS.
- `rg "Connected|Unreachable|Unauthorized|Not configured|/api/settings/test/llm|raw_llm_api_key" web-ui/server/tests/test_health_settings.py` - PASS.
- `rg -n "skip|xfail|todo" web-ui/server/tests || true` - PASS, no matches.
- `git diff --check` for the created plan files - PASS.

Full test execution was not run because this plan intentionally creates contract tests and importable stubs; the required verification gate is collect-only.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

- `web-ui/server/app/domain/cards.py:97` - `delete_character_preserving_thread_snapshots` raises `NotImplementedError`; later character CRUD work implements durable soft-delete or detach behavior.
- `web-ui/server/app/domain/cards.py:108` - `parse_character_card_bytes` raises `NotImplementedError`; later card import work implements JSON/PNG parsing and normalization.
- `web-ui/server/app/domain/card_export.py:25` - `export_character_v2_json` raises `NotImplementedError`; later card export work implements v2 JSON serialization.

These stubs are intentional contract boundaries and do not block this plan's goal.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Later parser, CRUD, settings, and UI plans can now implement against executable backend contracts for card safety, lorebook preservation, safe character deletion, and endpoint health reporting. The orchestrator owns shared STATE and ROADMAP updates after the wave.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-03-SUMMARY.md`.
- Key created backend contract files exist on disk.
- Task commits `30d4933` and `b2c5412` exist in git history.
- `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
