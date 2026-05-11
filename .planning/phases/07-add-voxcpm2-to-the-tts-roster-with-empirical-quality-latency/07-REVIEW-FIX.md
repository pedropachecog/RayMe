---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
fixed_at: 2026-05-11T11:42:18Z
review_path: .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-05-11T11:42:18Z
**Source review:** .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: VoxCPM2 Style Prompt Is Sent as an Unsupported Runtime Keyword

**Files modified:** `ai-backend/app/models/tts_voxcpm2.py`, `ai-backend/tests/test_tts_voxcpm2.py`
**Commit:** 81d68e4
**Applied fix:** Folded non-transcript-guided style prompts into the generated `text` value and tightened the fake VoxCPM2 runtime to reject unsupported kwargs.

### WR-02: Transcript-Guided VoxCPM2 Mode Drops the Reference Cloning Input

**Files modified:** `ai-backend/app/models/tts_voxcpm2.py`, `ai-backend/tests/test_tts_voxcpm2.py`
**Commit:** ebc47a2
**Applied fix:** Added `reference_wav_path` alongside `prompt_wav_path` and `prompt_text` for transcript-guided cloning, with a test assertion for both path roles.

### WR-03: Invalid TTS Engine Requests Can Mask the Intended Public Error

**Files modified:** `ai-backend/app/api/tts.py`, `ai-backend/tests/test_tts_registry.py`
**Commit:** 16c9f49
**Applied fix:** Guarded unavailable marking for unknown engine ids, logged marker failures without replacing the public error, and added an unknown-engine `/tts/synthesize` regression test.

---

_Fixed: 2026-05-11T11:42:18Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
