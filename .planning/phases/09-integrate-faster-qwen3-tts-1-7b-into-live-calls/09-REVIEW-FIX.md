---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
fixed_at: 2026-08-01T14:51:04Z
review_path: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-REVIEW.md
iteration: 3
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-08-01T14:51:04Z
**Source review:** `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-REVIEW.md`
**Iteration:** 3

**Summary:**

- Findings in scope: 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### CR-01: Changing metadata source re-exposes stale Qwen authorization data

**Status:** fixed: requires human verification
**Files modified:** `web-ui/server/app/domain/voice_service.py`, `web-ui/server/tests/test_voices.py`
**Commit:** d9d2a46
**Applied fix:** `merge_voice_metadata` now sanitizes persisted metadata using its original engine/source provenance before normalizing and applying the patch, then sanitizes the merged result again. A source-only patch can no longer reclassify stale Qwen tracer authorization data before retirement. The regression seeds a stale tracer row, proves read/list hide the private containers, patches only the source classification plus a safe flag, and proves response and stored JSON remain clean. A separate Qwen non-tracer patch proves newly supplied generic licensing authorization remains preserved, while the existing F5 and VoxCPM2 preservation cases continue to pass.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_migrations.py -q`: 55 passed.
- Full `web-ui/server/tests/test_calls.py` split into bounded groups: 17 Qwen/voice/reference tests passed and 56 complementary tests passed (73 total).
- `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py -q`: 32 passed.
- Focused live-call invariant regressions: 8 passed, covering bounded startup without final-only metrics, Qwen and VoxCPM2 playback before slow-stream completion, exact-request termination, late-chunk rejection, and no whole-synthesis fallback.
- Python AST parsing passed for both modified files.
- `git diff --check`: passed.

---

_Fixed: 2026-08-01T14:51:04Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 3_
