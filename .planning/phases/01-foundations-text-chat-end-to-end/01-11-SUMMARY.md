---
phase: 01-foundations-text-chat-end-to-end
plan: "11"
subsystem: api
tags: [fastapi, settings, health, httpx, llm-probe]

requires:
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 08 app_settings table and async SQLAlchemy session helpers"
  - phase: 01-foundations-text-chat-end-to-end
    provides: "Plan 10 runtime config, CORS/CSP wiring, and FastAPI app factory"
provides:
  - "Web UI `/health` route with Phase 1 service status payload"
  - "Persisted Settings read/update API for Web UI, AI backend, and LLM endpoint config"
  - "Connection-test routes for Web UI, AI backend `/health`, and OpenAI-compatible LLM Chat Completions"
  - "Server-side LLM secret handling with key-configured boolean only"
affects: [web-ui-server, settings-screen, ai-backend-status, llm-status, text-chat]

tech-stack:
  added: []
  patterns:
    - "Use app_settings row `endpoint_settings` for persisted endpoint configuration overlays"
    - "Return only exact connection status enum values from Settings test endpoints"
    - "Probe external LLM readiness via server-side Chat Completions request, not a local LLM `/health` service"

key-files:
  created:
    - web-ui/server/app/api/health.py
    - web-ui/server/app/api/settings.py
    - web-ui/server/app/domain/llm_probe.py
    - web-ui/server/app/domain/settings_service.py
  modified:
    - web-ui/server/app/main.py
    - web-ui/server/tests/test_health_settings.py

key-decisions:
  - "Settings exposes `llm_api_key_configured` instead of any raw or masked key string."
  - "LLM status is tested by posting to the configured OpenAI-compatible `/chat/completions` endpoint server-side."
  - "Blank endpoint URLs return `Not configured` before any probe is attempted."

patterns-established:
  - "Settings API dependencies expose probe callables so route tests can verify status mapping without live network calls."
  - "Connection tests suppress provider error text and return only `Connected`, `Unreachable`, `Unauthorized`, or `Not configured`."

requirements-completed: [REQ-01, REQ-03, REQ-04, REQ-A0, REQ-A1]

duration: 6min
completed: 2026-04-24
---

# Phase 01 Plan 11: Web Health and Settings APIs Summary

**FastAPI health and persisted endpoint Settings APIs with server-side AI backend and OpenAI-compatible LLM connection probes.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-24T05:32:05Z
- **Completed:** 2026-04-24T05:38:04Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added `GET /health` returning the exact Web UI Phase 1 payload.
- Added `GET /api/settings` and `PATCH /api/settings` backed by the existing `app_settings` table.
- Added `POST /api/settings/test/web`, `/api/settings/test/ai-backend`, and `/api/settings/test/llm` with the required four status values only.
- Added HTTPX probes for AI backend `/health` and OpenAI-compatible `/chat/completions`.
- Expanded tests to prove status mapping, LLM route shape, server-side probe settings, and API-key non-exposure.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement health and Settings APIs** - `4484f2a` (`feat`)

**Plan metadata:** committed separately with this summary.

## Files Created/Modified

- `web-ui/server/app/api/health.py` - Web UI health route.
- `web-ui/server/app/api/settings.py` - Settings read/update routes and connection-test endpoints.
- `web-ui/server/app/domain/settings_service.py` - Persisted endpoint settings overlay service.
- `web-ui/server/app/domain/llm_probe.py` - AI backend health and OpenAI-compatible LLM probes.
- `web-ui/server/app/main.py` - Registers health/settings routers and stores runtime settings on app state.
- `web-ui/server/tests/test_health_settings.py` - Contract tests for settings persistence, statuses, probes, and secret handling.

## Decisions Made

- Stored endpoint settings as one JSON value under `app_settings.endpoint_settings` to reuse the Plan 08 schema without a migration.
- Kept connection-test responses intentionally small: only `{ "status": ... }`, with no provider error body or secret-bearing diagnostic text.
- Treated the LLM as an external OpenAI-compatible service by probing Chat Completions through the Web UI server.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added HTTP(S)-only URL validation and not-configured guards**
- **Found during:** Task 1 (Implement health and Settings APIs)
- **Issue:** Browser-editable endpoint URLs would otherwise allow malformed or non-HTTP probe targets.
- **Fix:** Added Pydantic validation for absolute `http(s)` endpoint URLs and route-level blank checks before network probes.
- **Files modified:** `web-ui/server/app/api/settings.py`, `web-ui/server/tests/test_health_settings.py`
- **Verification:** `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q`
- **Committed in:** `4484f2a`

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Security-hardening only; no scope expansion or API contract change.

## Issues Encountered

- The first test run showed an injected AI-backend probe could mask a blank URL as `Connected`; route-level `Not configured` handling was added before committing.

## Known Stubs

None - stub scan found no TODO/FIXME/placeholder markers or hardcoded empty UI data in the created/modified files. The one empty string in tests is an intentional `Not configured` assertion.

## Threat Flags

None - the new browser Settings API, AI-backend probe, and LLM probe surfaces are covered by `T-01-11-KEY`, `T-01-11-LLMHEALTH`, and `T-01-11-STATUS`.

## User Setup Required

None - no external service configuration is required to run tests. Real connection tests use the persisted Web UI, AI backend, and LLM endpoint values at runtime.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` - PASS, 8 tests.
- `rg "Connected|Unreachable|Unauthorized|Not configured|/api/settings/test/llm|llm_api_key_configured" web-ui/server/app web-ui/server/tests/test_health_settings.py` - PASS.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_config.py web-ui/server/tests/test_app.py web-ui/server/tests/test_health_settings.py -q` - PASS, 22 tests.
- `uv run --project web-ui/server ruff check web-ui/server/app/api/health.py web-ui/server/app/api/settings.py web-ui/server/app/domain/settings_service.py web-ui/server/app/domain/llm_probe.py web-ui/server/app/main.py web-ui/server/tests/test_health_settings.py` - PASS.

## Next Phase Readiness

The Settings screen can now load/save endpoint configuration and run real connection tests. Text-chat plans can reuse the same server-side LLM configuration path without exposing API keys to the browser.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-11-SUMMARY.md`.
- Key API, domain, and test files exist on disk.
- Task commit `4484f2a` exists in git history.
- Shared orchestrator files `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` were not modified.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
