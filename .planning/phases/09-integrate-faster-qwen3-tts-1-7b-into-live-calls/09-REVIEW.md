---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
reviewed: 2026-08-01T15:23:32Z
depth: deep
files_reviewed: 18
files_reviewed_list:
  - ai-backend/app/models/model_manager.py
  - ai-backend/tests/test_model_manager.py
  - web-ui/client/src/lib/api/types.ts
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/src/routes/voice-lab/+page.svelte
  - web-ui/client/tests/e2e/live-call.spec.ts
  - web-ui/client/tests/e2e/qwen3-readiness.spec.ts
  - web-ui/client/tests/unit/voice-lab.test.ts
  - web-ui/server/app/api/voices.py
  - web-ui/server/app/domain/call_service.py
  - web-ui/server/app/domain/voice_service.py
  - web-ui/server/alembic/versions/0008_remove_qwen3_authorization.py
  - web-ui/server/tests/test_calls.py
  - web-ui/server/tests/test_migrations.py
  - web-ui/server/tests/test_voices.py
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py
  - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 09: Code Review Report

**Reviewed:** 2026-08-01T15:23:32Z
**Depth:** deep
**Files Reviewed:** 18
**Status:** clean

## Summary

The final focused re-review of continuation commit `50d2313` is clean. The exception boundary in `09-run-omen-evidence.py` now emits full messages only for the runner's curated `EvidenceRunnerError` domain failures. Every other `Exception` is reduced to its class name, so paths, transcripts, and other private exception details do not reach the canonical deployment output. `KeyboardInterrupt` and `SystemExit` continue to propagate, successful runs still emit `PASS` and return zero, and unexpected failures return nonzero.

The stale saved-voice helper call is also closed: both the evidence runner and hardware tracer call `_create_saved_voice(api, *, reference_audio, transcript)` without the removed `selection` argument. Authorization remains enforced by hash-bound preflight and retained in permitted evidence rather than being written into saved-voice metadata. The canonical deployment captures the runner status, republishes only `PASS*`/`FAIL:*` lines, aborts on nonzero status, and requires independent same-commit core-ready verification before evidence copyback.

The earlier 17-file deep review remains clean through `d9d2a46`: transcript alignment, Qwen-scoped metadata cleanup, migration behavior, API compatibility, and live-call streaming invariants remain closed.

All reviewed files meet quality standards. No issues found.

## Narrative Findings (AI reviewer)

No Critical, Warning, or Info findings.

## Verification

### Final continuation `50d2313`

- Audited every `EvidenceRunnerError` construction in the runner. Dynamic values are bounded runner labels, manifest scenario IDs, turn numbers, artifact keys, and stream names; private paths, transcript contents, and underlying exception messages are not interpolated.
- Confirmed the handler order is `EvidenceRunnerError` first, followed by class-name-only `Exception`; the previous raw `OSError`/`RuntimeError`/`ValueError` leak is closed.
- Confirmed `KeyboardInterrupt` and `SystemExit` remain outside the handler because they inherit from `BaseException`.
- Confirmed success returns `0` with `PASS`; domain and unexpected failures return `1` with a sanitized `FAIL:` line.
- Traced `_create_saved_voice(api, *, reference_audio, transcript)` from both call sites to the current hardware-tracer signature. No stale `selection` argument remains at the saved-voice boundary.
- Confirmed the saved-voice payload contains only `metadata.source=phase09_hardware_tracer`; retired authorization fields remain absent.
- Confirmed deployment aborts on a nonzero runner status and independently verifies the commit-bound core-ready bundle before copyback.
- `ai-backend/.venv/bin/pytest -q .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py`: 59 passed.
- Runner `--dry-run` at `50d23136a7d88efab8cc48696a2461f1941e04c8`: passed.
- `bash -n scripts/deploy-omen.sh`: passed.
- `git diff --check f999d33..50d2313`: passed.
- Conflict-marker scan across the continuation files and deployment script: none found.

### Earlier clean gate through `d9d2a46`

- Model-manager tests: 32 passed.
- Server voice/call/migration tests: 128 passed.
- Client type/Svelte check: passed.
- Voice Lab unit tests: 17 passed.
- Qwen readiness Playwright tests: 8 passed.
- Phase 09 evidence tests at that gate: 50 passed.
- Focused live-call streaming, cancellation, VoxCPM2 no-fallback, and WebRTC Qwen-carrier invariants: 7 passed.

---

_Reviewed: 2026-08-01T15:23:32Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
