---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
fixed_at: 2026-08-01T10:01:24Z
review_path: .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-REVIEW.md
iteration: 4
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-08-01T10:01:24Z
**Source review:** `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-REVIEW.md`
**Iteration:** 4

**Summary:**

- Findings in scope: 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### CR-01: Spoken barge-in never reaches VAD or interruption

**Files modified:** `ai-backend/app/call/session.py`, `ai-backend/tests/test_call_session.py`
**Commit:** 4f6efd9
**Status:** Fixed — requires human verification because this repairs live-call state and interruption logic.
**Applied fix:** Replaced the speaking-state microphone drop with a bounded one-second onset buffer guarded by WebRTC echo/noise suppression, a minimum RMS threshold, Silero-compatible current-frame VAD confirmation, and 120 ms of sustained speech. Confirmed onset frames are promoted into the next user turn before the exact `await interrupt(cause="vad_barge_in")` path runs. Additional frames arriving during delayed cancellation are preserved while the existing cancellation flow immediately stops and drains paced playout. The regression uses real non-silent PCM and a real `QueuedAudioOutputTrack`; it proves bounded noise rejection, early existing playback, spoken onset interruption, silence during delayed acknowledgement, no interrupted-turn `ai_done`, onset delivery to `user_final`, and normal subsequent Qwen playback.

**Verification:**

- New production-path regression repeated 5 times: 5/5 passed.
- `tests/test_call_session.py`, `tests/test_tts_voxcpm2.py`, and `tests/test_tts_qwen3.py`: 151 passed.
- Python AST parse passed for both modified files.
- `git diff --check` passed.
- Ruff surfaced only pre-existing project-wide findings in these files; no new syntax/import failure was introduced.

---

_Fixed: 2026-08-01T10:01:24Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 4_
