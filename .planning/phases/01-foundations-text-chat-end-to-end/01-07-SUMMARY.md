---
phase: 01-foundations-text-chat-end-to-end
plan: "07"
subsystem: infra
tags: [fastapi, uvicorn, https, llm, mkcert]

requires:
  - phase: 00-measurement-gate
    provides: mkcert LAN HTTPS validation and direct-IP Android acceptance
provides:
  - Health-only AI backend FastAPI service
  - Direct-IP HTTPS runner for AI backend port 9443
  - Docs-only external OpenAI-compatible LLM configuration contract
  - LAN HTTPS configuration examples for Web UI and AI backend
affects: [web-ui-settings, ai-backend, llm, lan-https]

tech-stack:
  added: [fastapi==0.136.1, uvicorn==0.46.0, httpx==0.28.1, pytest==9.0.3]
  patterns:
    - Health-only FastAPI app factory with exact `/health` contract
    - Direct LAN IP HTTPS configuration with explicit bind host

key-files:
  created:
    - ai-backend/pyproject.toml
    - ai-backend/app/__init__.py
    - ai-backend/app/main.py
    - ai-backend/scripts/run_https.py
    - ai-backend/tests/test_health.py
    - ai-backend/uv.lock
    - llm/README.md
    - llm/openai-compatible.example.env
    - web-ui/server/config.example.env
    - docs/phase1-https-lan.md
  modified:
    - .gitignore

key-decisions:
  - "AI backend exposes only `/health` in Phase 1; no model service fields or endpoints were added."
  - "LLM remains external and OpenAI-compatible; `llm/` contains docs/config only."
  - "Direct LAN IP HTTPS is the supported Phase 1 path; `rayme.local` is optional unless DNS/mDNS is configured."

patterns-established:
  - "AI backend runner rejects wildcard bind, requires cert/key files, and validates configuration before serving."
  - "Committed environment examples keep LLM API keys blank and server-side."

requirements-completed: [REQ-01, REQ-03, REQ-04, REQ-A0, REQ-A1]

duration: 8min
completed: 2026-04-24
---

# Phase 01 Plan 07: AI Backend Health, External LLM, And LAN HTTPS Summary

**Health-only FastAPI AI backend with direct-IP HTTPS runner, docs-only external LLM config, and Phase 1 LAN HTTPS guidance.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-24T03:24:44Z
- **Completed:** 2026-04-24T03:31:49Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Added `rayme-ai-backend` as a uv-managed FastAPI project with exact `/health` JSON and pytest coverage.
- Added an HTTPS runner for the AI backend that requires TLS files, rejects `0.0.0.0`, and documents `https://192.168.1.199:9443/health`.
- Added docs/config showing that RayMe does not ship local inference and that LLM status is tested through `POST /api/settings/test/llm`.
- Added Phase 1 LAN HTTPS guidance using the Phase 0 mkcert direct-IP path for Web UI and AI-backend health.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement AI backend health and HTTPS runner** - `4201507` (feat)
2. **Task 2: Document external LLM and LAN HTTPS config** - `e8acd4a` (docs)

## Files Created/Modified

- `.gitignore` - Added Python environment/cache ignore rules generated during uv verification.
- `ai-backend/pyproject.toml` - Defines the `rayme-ai-backend` uv project and pinned dependencies.
- `ai-backend/app/__init__.py` - Exports the FastAPI app factory.
- `ai-backend/app/main.py` - Implements the health-only `/health` endpoint.
- `ai-backend/scripts/run_https.py` - Validates explicit bind/TLS settings and starts uvicorn with cert/key files.
- `ai-backend/tests/test_health.py` - Covers exact health JSON, wildcard host rejection, required cert/key paths, and runner help text.
- `ai-backend/uv.lock` - Locks the AI backend Python dependency graph.
- `llm/README.md` - Documents the external OpenAI-compatible LLM boundary and Settings probe.
- `llm/openai-compatible.example.env` - Provides the minimal server-side LLM environment shape with a blank key.
- `web-ui/server/config.example.env` - Provides direct LAN HTTPS examples for Web UI, AI backend, allowed origins, TLS files, and LLM settings.
- `docs/phase1-https-lan.md` - Adapts the Phase 0 mkcert workflow for Phase 1 direct-IP HTTPS.

## Decisions Made

- Followed the plan's health-only scope for `ai-backend`; no STT/TTS/VAD/WebRTC/GPU/voice fields were added.
- Kept `llm/` docs/config only, with no local `llm/app.py` or `llm/server.py`.
- Used explicit LAN host examples instead of wildcard bind or wildcard CORS.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Preserved generated Python environment/cache ignore rules**
- **Found during:** Task 1 (verification with `uv run`)
- **Issue:** Running the uv-managed tests generated local Python environment/cache directories that must not be committed.
- **Fix:** Kept `.venv/` and `.ruff_cache/` ignore entries in `.gitignore` so generated runtime artifacts stay out of task commits.
- **Files modified:** `.gitignore`
- **Verification:** `git status --short --untracked-files=all` did not list AI-backend `.venv` or cache files.
- **Committed in:** `4201507`

---

**Total deviations:** 1 auto-fixed (Rule 3)
**Impact on plan:** No product scope change; the deviation only protects generated verification artifacts.

## Issues Encountered

- A shared-index race initially pulled unrelated staged `web-ui/server` files into the Task 1 commit. The commit was amended immediately to remove those paths while leaving the files on disk for the parallel executor. That executor later landed them separately as `64c6ae6`.

## User Setup Required

None - no external service configuration is required to use the health stub or docs. Operators still need to provide real TLS cert/key files and runtime LLM credentials when running the services.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_health.py -q` -> 5 passed.
- `uv run --project ai-backend python ai-backend/scripts/run_https.py --check-config --host 127.0.0.1 --port 9443 --cert ai-backend/pyproject.toml --key ai-backend/pyproject.toml` -> passed.
- `! rg "STT|TTS|VAD|WebRTC|gpu|voice" ai-backend/app/main.py` -> passed.
- `test -f llm/README.md && test -f llm/openai-compatible.example.env && test ! -f llm/app.py && test ! -f llm/server.py` -> passed.
- `rg 'direct LAN IP HTTPS is sufficient|RayMe does not ship local inference|/api/settings/test/llm|https://192\.168\.1\.199:8443|https://192\.168\.1\.199:9443/health' llm web-ui/server/config.example.env docs/phase1-https-lan.md` -> passed.
- Stub scan found no incomplete UI/rendering stand-ins or unresolved marker text in plan-created files.

## Threat Flags

None - the new `/health` endpoint, HTTPS runner, docs-only LLM boundary, and server-side key guidance are all covered by the plan threat model.

## Next Phase Readiness

Settings can now point at `https://192.168.1.199:9443/health` for AI-backend status, and Web UI/server plans can use `web-ui/server/config.example.env` as the LAN HTTPS and LLM configuration contract.

## Self-Check: PASSED

- All created files listed in `key-files.created` exist on disk.
- Task commits `4201507` and `e8acd4a` exist in git history.
- No tracked file deletions were introduced by task commits.
- Shared orchestrator files `.planning/STATE.md` and `.planning/ROADMAP.md` were not modified by this plan.

---
*Phase: 01-foundations-text-chat-end-to-end*
*Completed: 2026-04-24*
