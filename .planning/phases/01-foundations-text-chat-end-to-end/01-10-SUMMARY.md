---
phase: 01-foundations-text-chat-end-to-end
plan: "10"
subsystem: infra
tags: [fastapi, pydantic, cors, csp, https, mkcert, static-host]

requires:
  - phase: 00-measurement-gate
    provides: mkcert LAN HTTPS validation and direct-IP Android acceptance
  - phase: 01-foundations-text-chat-end-to-end
    provides: backend app harness, SvelteKit static build shape, and LAN HTTPS config examples
provides:
  - Validated Web UI runtime settings for explicit bind host, TLS, CORS origins, AI backend URL, and LLM config
  - Explicit FastAPI CORS allowlist and CSP/security headers
  - Conditional SvelteKit static host mount with `200.html` SPA fallback
  - Web UI mkcert HTTPS runner with direct-IP help text and `--check-config`
affects: [web-ui-server, web-ui-client, settings, lan-https, static-hosting]

tech-stack:
  added: []
  patterns:
    - Pydantic model plus environment mapping for Web UI runtime config
    - FastAPI middleware setup isolated in `app/security.py`
    - Direct-IP mkcert HTTPS runner that refuses wildcard binds

key-files:
  created:
    - web-ui/server/app/security.py
    - web-ui/server/scripts/run_dev_https.py
    - web-ui/server/tests/test_config.py
  modified:
    - web-ui/server/app/config.py
    - web-ui/server/app/main.py

key-decisions:
  - "Runtime Web UI bind defaults to `127.0.0.1`; LAN docs/help examples use the validated `192.168.1.199:8443` direct-IP path."
  - "CORS origins must be explicit and credentials stay disabled for the unauthenticated LAN app APIs."
  - "The static client mount is conditional on `web-ui/client/build/200.html` existing so backend tests can run without a client build."

patterns-established:
  - "Use `load_settings()` for deterministic config tests and `get_settings()` for cached runtime config."
  - "Use `configure_cors()` and `configure_security_headers()` from `app/security.py` when building the FastAPI host."
  - "Use `web-ui/server/scripts/run_dev_https.py --check-config` before serving LAN HTTPS."

requirements-completed: [REQ-01, REQ-03, REQ-04, REQ-A0, REQ-A1]

duration: 8min
completed: 2026-04-24
---

# Phase 01 Plan 10: Web Host Config And HTTPS Runner Summary

**Explicit Web UI bind/origin validation, FastAPI CORS/CSP middleware, conditional SvelteKit static hosting, and mkcert HTTPS startup.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-24T05:05:00Z
- **Completed:** 2026-04-24T05:12:42Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Replaced the minimal dataclass config shell with validated Pydantic settings for Web UI host/port, public URL, TLS paths, allowed origins, AI backend URL, and OpenAI-compatible LLM settings.
- Added FastAPI security wiring: explicit CORS allowlist with credentials disabled, CSP headers, nosniff, and referrer policy.
- Added conditional static hosting for the built SvelteKit client with `200.html` SPA fallback when build output exists.
- Added a Web UI HTTPS runner that reads config defaults, rejects `0.0.0.0`, requires cert/key files, supports `--check-config`, and passes `ssl_certfile`/`ssl_keyfile` to uvicorn.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement explicit LAN config, CORS, CSP, and static serving** - `0d4ec92` (feat)
2. **Task 2: Add web HTTPS dev runner** - `3326a0a` (feat)

**Plan metadata:** committed separately with this summary.

## Files Created/Modified

- `web-ui/server/app/config.py` - Pydantic settings, env mapping, wildcard bind rejection, and explicit allowed-origin parsing.
- `web-ui/server/app/main.py` - FastAPI factory wiring for CORS, security headers, and conditional SvelteKit static hosting.
- `web-ui/server/app/security.py` - CORS allowlist helper and CSP/security header middleware.
- `web-ui/server/scripts/run_dev_https.py` - mkcert-oriented HTTPS runner with `--check-config` and uvicorn SSL arguments.
- `web-ui/server/tests/test_config.py` - Config, CORS, CSP, static-host, and HTTPS-runner contract tests.

## Decisions Made

- Kept runtime defaults conservative at localhost while preserving the validated direct LAN IP in examples and help text.
- Validated cert/key paths by file existence in `--check-config`; the runner does not parse certificate contents because mkcert trust is verified manually on the browser/device path.
- Kept CORS credentials disabled because Phase 1 is unauthenticated LAN usage and wildcard origins are explicitly forbidden.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None - stub scan found no TODO/FIXME/placeholder markers or hardcoded empty UI data in the created/modified files.

## Threat Flags

None - the new network/config surfaces are covered by `T-01-10-BIND`, `T-01-10-CORS`, and `T-01-10-XSS` in the plan threat model.

## User Setup Required

No application credentials are required for this plan. To actually run HTTPS on LAN, provide mkcert-generated cert/key paths via `RAYME_TLS_CERT` and `RAYME_TLS_KEY` or the runner's `--cert` and `--key` flags.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_config.py -q` -> PASS, 12 tests.
- `uv run --project web-ui/server python web-ui/server/scripts/run_dev_https.py --check-config --host 127.0.0.1 --port 8443 --cert web-ui/server/config.example.env --key web-ui/server/config.example.env` -> PASS.
- `rg "RAYME_WEB_BIND_HOST|RAYME_ALLOWED_ORIGINS|configure_cors|default-src 'self'|https://192\\.168\\.1\\.199:8443|ssl_certfile|ssl_keyfile" web-ui/server/app web-ui/server/scripts/run_dev_https.py web-ui/server/tests/test_config.py` -> PASS.
- `uv run --project web-ui/server ruff check web-ui/server/app/config.py web-ui/server/app/main.py web-ui/server/app/security.py web-ui/server/scripts/run_dev_https.py web-ui/server/tests/test_config.py` -> PASS.

## Next Phase Readiness

Plan 11 can register `/health` and Settings routes on the FastAPI app before the root static mount. The HTTPS runner and config example now provide the concrete Web UI startup path for later Android Chrome verification.

## Self-Check: PASSED

- Summary file exists at `.planning/phases/01-foundations-text-chat-end-to-end/01-10-SUMMARY.md`.
- Key files exist on disk: `config.py`, `main.py`, `security.py`, `run_dev_https.py`, and `test_config.py`.
- Task commits `0d4ec92` and `3326a0a` exist in git history.
- No tracked file deletions were introduced by task commits.
- Shared orchestrator files `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` were not modified.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
