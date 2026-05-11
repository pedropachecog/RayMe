---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
fixed_at: 2026-05-11T12:06:11Z
review_path: .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-REVIEW.md
iteration: 3
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-05-11T12:06:11Z
**Source review:** .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-REVIEW.md
**Iteration:** 3

**Summary:**
- Findings in scope: 2
- Fixed: 2
- Skipped: 0

## Fixed Issues

### WR-01: `/tts/synthesize` accepts unbounded reference audio

**Files modified:** `ai-backend/app/models/tts_registry.py`, `ai-backend/app/api/tts.py`, `ai-backend/tests/test_tts_registry.py`
**Commit:** e430e1c
**Applied fix:** Added the shared 25 MiB reference-audio byte limit and 36 MiB base64 request-field limit, bounded `/tts/synthesize` request validation, rejected decoded reference audio above policy with HTTP 413, and added focused endpoint coverage.

### WR-02: WebRTC speak also accepts unbounded reference audio

**Files modified:** `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`, `ai-backend/tests/test_webrtc_signaling.py`
**Commit:** 73c2fe8
**Applied fix:** Reused the shared reference-audio limits for WebRTC speak, rejected oversized inline reference audio before synthesis, enforced the decoded-byte guard in generic call-session synthesis, and added focused WebRTC speak coverage.

---

_Fixed: 2026-05-11T12:06:11Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 3_
