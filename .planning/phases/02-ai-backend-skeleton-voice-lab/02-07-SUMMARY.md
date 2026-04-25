---
phase: 02-ai-backend-skeleton-voice-lab
plan: "07"
subsystem: ai-backend
tags: [fastapi, faster-whisper, silero-vad, stt, vad, pytest, multipart]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: AI backend model manager, health payload, and RED STT/VAD contracts from plans 02-02 and 02-06
provides:
  - English-only faster-whisper STT adapter with Phase 0 defaults and hallucination filtering
  - Silero VAD adapter and generated temporary WAV decoding for transient uploaded samples
  - Multipart `/stt/transcribe` route with retry/manual transcript fallback and sanitized failure details
affects: [02-09, 02-10, 02-12, 02-14, 02-18]

tech-stack:
  added: [faster-whisper==1.2.1, silero-vad==6.2.1, python-multipart==0.0.26]
  patterns: [lazy real-model adapter loading, generated temp WAV normalization, sanitized processing error envelope]

key-files:
  created:
    - ai-backend/app/audio/__init__.py
    - ai-backend/app/audio/filters.py
    - ai-backend/app/audio/io.py
    - ai-backend/app/models/stt.py
    - ai-backend/app/models/vad.py
    - ai-backend/app/api/stt.py
  modified:
    - ai-backend/app/models/__init__.py
    - ai-backend/app/main.py
    - ai-backend/pyproject.toml
    - ai-backend/uv.lock
    - ai-backend/tests/test_stt.py

key-decisions:
  - "STT processing uses generated temporary WAV paths so uploaded filenames never influence filesystem paths."
  - "The route returns fixed public `stt_failed` details with retry/manual fallback flags rather than raw adapter exceptions."
  - "Real faster-whisper and Silero dependencies are installed, but adapters lazily load models so unit tests remain model-download-free."

patterns-established:
  - "AI backend processing routes can accept fake adapters through `app.state` for deterministic unit tests."
  - "Manual transcript fallback responses use the same shape for no-speech, hallucination, and processing failure paths."

requirements-completed: [REQ-02, REQ-21, REQ-A3]

duration: 15 min
completed: 2026-04-25
---

# Phase 02 Plan 07: AI Backend STT/VAD Processing Summary

**English-only faster-whisper transcription behind Silero VAD gating with safe retry/manual transcript semantics.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-25T00:05:52Z
- **Completed:** 2026-04-25T00:20:22Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Added audio helpers that decode uploaded bytes into generated temporary WAV files without trusting user filenames.
- Added `SileroVadAdapter` and `WhisperSttAdapter` with Phase 0 defaults: `distil-large-v3`, `int8_float16`, English `transcribe`, beam size 5, VAD parameters, and `condition_on_previous_text=False`.
- Added hallucination blocklist filtering for common Whisper filler phrases, returning `needs_manual_transcript` with retry allowed.
- Added `POST /stt/transcribe` with multipart upload, optional VAD form controls, stable response fields, invalid-audio validation, and sanitized 502 failures.

## Task Commits

TDD tasks produced RED and GREEN commits:

1. **Task 1 RED: Add STT adapter contracts** - `eb9478d` (test)
2. **Task 1 GREEN: Add audio IO, VAD, and STT adapters** - `464649e` (feat)
3. **Task 2 RED: Add STT route contracts** - `77dae36` (test)
4. **Task 2 GREEN: Add transient STT route** - `1459c3a` (feat)

## Files Created/Modified

- `ai-backend/app/audio/__init__.py` - Exports audio helper APIs.
- `ai-backend/app/audio/filters.py` - Defines `HALLUCINATION_BLOCKLIST` and transcript normalization/filter helpers.
- `ai-backend/app/audio/io.py` - Decodes uploaded audio bytes and writes generated temporary WAV files.
- `ai-backend/app/models/stt.py` - Adds faster-whisper STT adapter and manual transcript fallback response shape.
- `ai-backend/app/models/vad.py` - Adds configurable Silero VAD adapter.
- `ai-backend/app/api/stt.py` - Adds multipart transient transcription route and sanitized error handling.
- `ai-backend/app/main.py` - Registers the STT router.
- `ai-backend/app/models/__init__.py` - Exports STT/VAD adapter symbols.
- `ai-backend/tests/test_stt.py` - Adds adapter and route coverage.
- `ai-backend/pyproject.toml` and `ai-backend/uv.lock` - Add faster-whisper, Silero VAD, and multipart runtime dependencies.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_stt.py ai-backend/tests/test_health.py -q` - PASS, 15 tests with one existing `pynvml` deprecation warning.
- `rg "WhisperModel|distil-large-v3|int8_float16|language=.en|task=.transcribe|condition_on_previous_text=False|HALLUCINATION_BLOCKLIST|needs_manual_transcript|SileroVadAdapter" ai-backend/app ai-backend/tests/test_stt.py` - PASS.
- `rg "POST.*/stt/transcribe|manual_transcript_allowed|retry_allowed|stt_failed|Transcription failed|include_router\\(stt" ai-backend/app ai-backend/tests/test_stt.py` - PASS.

## Decisions Made

- Kept STT/VAD model loading lazy so `create_app()` and `/health` remain lightweight in unit tests while real route calls can load the installed runtime libraries.
- Added retry/manual fallback flags to the sanitized 502 detail because the plan requires retry/manual transcript flow even when transcription fails.
- Used generated `rayme-stt-*.wav` temp files for route processing to preserve faster-whisper path compatibility without exposing uploaded filenames.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added missing STT/VAD and multipart runtime dependencies**
- **Found during:** Task 1 and Task 2 implementation
- **Issue:** The plan required real faster-whisper, Silero VAD, and multipart route handling, but the AI backend dependencies did not include `faster-whisper`, `silero-vad`, or `python-multipart`.
- **Fix:** Added `faster-whisper==1.2.1`, `silero-vad==6.2.1`, and `python-multipart==0.0.26` through `uv add`.
- **Files modified:** `ai-backend/pyproject.toml`, `ai-backend/uv.lock`
- **Verification:** Full plan pytest and acceptance grep checks passed.
- **Committed in:** `464649e`, `1459c3a`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Required for the route and real-model adapters to function. No architecture change.

## Issues Encountered

- Installing the STT/VAD dependencies downloaded and installed large CUDA/PyTorch wheels. The sync completed successfully and tests passed afterward.
- The required health test still emits the existing `pynvml` deprecation warning from plan 02-06; it does not affect this plan's behavior.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. Fake adapters in tests are intentional test doubles; runtime adapters are wired to real libraries with lazy model loading.

## Threat Flags

None. The new upload/transcription endpoint and transient temp-file decode path are the planned trust-boundary surfaces in this plan's threat model and include the required invalid-input and sanitized-error handling.

## Next Phase Readiness

Ready for Web UI Voice Lab server calls to use `/stt/transcribe` for transient sample transcription, and for later live OMEN-PC validation to exercise the real model-loading path.

## TDD Gate Compliance

- RED gate commits present: `eb9478d`, `77dae36`
- GREEN gate commits present after RED commits: `464649e`, `1459c3a`

## Self-Check: PASSED

- Verified key files exist: `audio/__init__.py`, `audio/filters.py`, `audio/io.py`, `models/stt.py`, `models/vad.py`, `api/stt.py`, and this summary.
- Verified task commits exist: `eb9478d`, `464649e`, `77dae36`, `1459c3a`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
