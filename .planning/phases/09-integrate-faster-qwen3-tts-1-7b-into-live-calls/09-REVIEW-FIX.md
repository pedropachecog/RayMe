---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
fixed_at: 2026-08-02T12:52:51Z
review_path: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-REVIEW.md
iteration: 28
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-08-02T12:52:51Z
**Source review:** `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-REVIEW.md`
**Iteration:** 28

**Summary:**

- Findings in scope: 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-01: TLS artifact validation happens after service shutdown and accepts directories

**Status:** fixed
**Files modified:** `scripts/deploy-omen.sh`, `ai-backend/tests/test_omen_deploy_contract.py`
**Commit:** 614520e
**Applied fix:** The canonical OMEN deploy now derives its durable state root, Phase 1 serving certificate, private key, CA bundle, and service-token path immediately after checkout commit verification. Certificate, key, and CA must each pass `Test-Path -LiteralPath ... -PathType Leaf` before the teardown function, every service/port-owner stop, launcher write, or scheduled-task mutation. The single preflight path definitions remain in PowerShell scope for token rotation, both launchers, strict CA probes, and health verification; token generation retains its original later ordering. Deployment contracts enforce single definitions, strict leaf validation, preflight-before-teardown/write ordering, repo-derived launcher paths, and token-rotation ordering.

## Verification

- OMEN deployment contract: 7 passed.
- `bash -n scripts/deploy-omen.sh` passed.
- Ruff passed for the changed deploy-contract test.
- Safety scans confirmed one repo-derived state root, one strict TLS leaf gate, no obsolete mkcert path, no insecure `curl -k`, no hidden `Start-Process`, and no `schtasks /Create` path.
- `git diff --check b8d79b9..614520e` passed.
- No push or deployment was performed.

---

_Fixed: 2026-08-02T12:52:51Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 28_
