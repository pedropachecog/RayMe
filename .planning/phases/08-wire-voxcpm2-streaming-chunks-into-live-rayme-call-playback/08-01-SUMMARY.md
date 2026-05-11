---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
plan: 01
subsystem: ai-backend-tts
tags: [voxcpm2, tts, streaming, wav, pytest]

# Dependency graph
requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: VoxCPM2 registry metadata, bounded synthesis options, CUDA-only adapter loading, and whole-WAV call caveat evidence
provides:
  - Internal TTS streaming chunk contract for AI-backend adapters
  - VoxCPM2 generate_streaming adapter that yields validated WAV chunks
  - Regression tests for valid streaming chunks, empty-stream rejection, and no whole-generation fallback
affects: [ai-backend-tts, call-playback, phase-08-streaming]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Internal streaming adapter Protocol next to existing TTS synthesis Protocol
    - Per-chunk soundfile WAV serialization with VoxCPM2 runtime sample-rate extraction

key-files:
  created: []
  modified:
    - ai-backend/app/models/tts_registry.py
    - ai-backend/app/models/tts_voxcpm2.py
    - ai-backend/tests/test_tts_voxcpm2.py

key-decisions:
  - "VoxCPM2 streaming stays internal to the AI backend through TtsAudioChunk and TtsStreamingAdapter."
  - "VoxCPM2 stream() calls generate_streaming() directly and rejects empty streams instead of falling back to runtime.generate()."

patterns-established:
  - "Streaming chunks are validated, flattened float32 waveform arrays serialized as standalone WAV payloads."
  - "Missing or empty VoxCPM2 streaming output raises the fixed VoxCPM2 streaming synthesis failed error."

requirements-completed: [P8-R1, P8-R3]

# Metrics
duration: 6 min
completed: 2026-05-11
---

# Phase 08 Plan 01: VoxCPM2 Streaming Adapter Summary

**Internal VoxCPM2 streaming chunks with timed WAV payloads and no whole-response fallback**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-11T14:30:10Z
- **Completed:** 2026-05-11T14:36:20Z
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments

- Added `TtsAudioChunk` and `TtsStreamingAdapter` exports to the AI-backend TTS registry.
- Added RED VoxCPM2 streaming tests covering timed WAV chunks, empty-stream rejection, and contract exports.
- Implemented `VoxCpm2TtsAdapter.stream(...)` using `runtime.generate_streaming(...)`, per-chunk WAV serialization, timing metadata, sample-rate extraction, and fixed empty-stream failure behavior.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define streaming contract and RED adapter tests** - `0086a4e` (test)
2. **Task 2: Implement VoxCPM2 generate_streaming chunk output** - `5c40ed9` (feat)

_TDD note: Task 1 was the RED gate. The targeted suite failed with 2 expected `VoxCpm2TtsAdapter.stream` AttributeErrors before Task 2. Task 2 was the GREEN gate._

## Files Created/Modified

- `ai-backend/app/models/tts_registry.py` - Defines and exports `TtsAudioChunk` plus `TtsStreamingAdapter`.
- `ai-backend/app/models/tts_voxcpm2.py` - Adds the VoxCPM2 streaming adapter path and chunk conversion helper.
- `ai-backend/tests/test_tts_voxcpm2.py` - Extends the scripted runtime and covers streaming contract behavior.

## Verification

- `rg -n "class TtsAudioChunk|class TtsStreamingAdapter|TtsAudioChunk|TtsStreamingAdapter" ai-backend/app/models/tts_registry.py` - PASS
- `rg -n "test_voxcpm2_stream_yields_wav_chunks_with_timing|test_voxcpm2_stream_rejects_empty_chunks_without_generate_fallback|test_tts_streaming_contract_exports_chunk_types" ai-backend/tests/test_tts_voxcpm2.py` - PASS
- `rg -n "def stream\\(|generate_streaming|TtsAudioChunk|VoxCPM2 streaming synthesis failed" ai-backend/app/models/tts_voxcpm2.py` - PASS
- `rg -n "REQUIRED_PACKAGE = \"voxcpm==2.0.2\"|MODEL_ID = \"openbmb/VoxCPM2\"|require_torch_cuda_runtime\\(\"VoxCPM2\"\\)" ai-backend/app/models/tts_voxcpm2.py` - PASS
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py -q` - PASS, 11 passed
- `git diff --check` - PASS

## Decisions Made

- Followed D-01 by keeping the streaming contract internal to `ai-backend/app/models`.
- Kept VoxCPM2 on the Phase 7 proven `voxcpm==2.0.2` and `openbmb/VoxCPM2` path with the existing CUDA guard intact.
- Treated invalid or empty stream chunks as ineligible for playback evidence by skipping invalid chunks and raising a fixed failure if none are valid.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope change.

## Issues Encountered

- Metadata note: `gsd-sdk query requirements.mark-complete P8-R1 P8-R3` returned `not_found` because these are Phase 8 SPEC requirement IDs, not global `.planning/REQUIREMENTS.md` IDs. The IDs remain copied verbatim in summary frontmatter for traceability.

## Authentication Gates

None.

## Known Stubs

None. Stub-pattern scan only found deliberate blank-transcript test inputs used to verify reference-only warning behavior.

## User Setup Required

None - no external service configuration required.

## TDD Gate Compliance

- RED commit present: `0086a4e`
- GREEN commit present after RED: `5c40ed9`
- REFACTOR commit: not needed

## Next Phase Readiness

Plan 08-02 can wire this internal streaming adapter into call-session playback while preserving interrupt and single-turn semantics.

## Self-Check: PASSED

- Summary file exists.
- Key modified files exist.
- Task commits `0086a4e` and `5c40ed9` exist in git history.

---
*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Completed: 2026-05-11*
