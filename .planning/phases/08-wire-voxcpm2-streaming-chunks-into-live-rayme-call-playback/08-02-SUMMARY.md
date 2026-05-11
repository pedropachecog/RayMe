---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
plan: 02
subsystem: ai-backend-call-playback
tags: [voxcpm2, streaming, tts, call-session, pytest]

# Dependency graph
requires:
  - phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
    provides: Internal TTS streaming chunk contract and VoxCPM2 stream adapter from plan 08-01
provides:
  - VoxCPM2 streamed chunk consumption inside CallSession.speak_text
  - Immediate first-audio tts_playback metrics separated from final tts_playback_final metrics
  - Interrupt-safe late streamed chunk discard coverage and single ai_done completion coverage
affects: [phase-08-live-evidence, webrtc-speak, voxcpm2-call-playback]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Sync TTS stream producer bridged into async call playback with asyncio.Queue
    - First streamed chunk uses call preroll; later chunks enqueue without preroll
    - Immediate playback metrics exclude final-only generation/playback totals

key-files:
  created: []
  modified:
    - ai-backend/app/call/session.py
    - ai-backend/tests/test_call_session.py

key-decisions:
  - "CallSession uses adapter.stream only for engine_id voxcpm2 adapters that expose a callable stream method."
  - "VoxCPM2 streaming call playback does not fall back to whole-WAV synthesis after selecting the streaming branch."
  - "First-audio tts_playback and final tts_playback_final metric carriers remain separate for Phase 8 evidence."

patterns-established:
  - "Streaming producer threads hand chunks to the async call session through an asyncio.Queue sentinel protocol."
  - "Cancellation is checked before every outbound streamed chunk enqueue, while the existing interrupt path still cancels the active speech task and stops the track."

requirements-completed: [P8-R1, P8-R3, P8-R4]

# Metrics
duration: 13 min
completed: 2026-05-11
---

# Phase 08 Plan 02: CallSession Streaming Playback Summary

**VoxCPM2 call playback now starts from the first streamed chunk and returns final playback proof once generation and queued audio finish**

## Performance

- **Duration:** 13 min
- **Started:** 2026-05-11T14:57:29Z
- **Completed:** 2026-05-11T15:09:59Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments

- Added RED call-session tests for VoxCPM2 first streamed enqueue before stream completion, one final `ai_done`, and interrupt-after-first-chunk behavior.
- Implemented a VoxCPM2-only streaming branch in `CallSession.speak_text(...)` that consumes `TtsAudioChunk` values from `adapter.stream(...)` without whole-synthesis fallback.
- Added immediate `ai_audio_started_event.tts_playback` fields and final `tts_playback_final` proof fields for both streamed and whole-WAV playback paths.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add call-session RED tests for streamed first audio and cancellation** - `e452c0b` (test)
2. **Task 2: Stream VoxCPM2 chunks through CallSession playback** - `b5ea507` (feat)

_TDD note: Task 1 was the RED gate. The targeted suite failed with 3 expected streaming test failures before Task 2. Task 2 was the GREEN gate._

## Files Created/Modified

- `ai-backend/tests/test_call_session.py` - Adds the scripted VoxCPM2 streaming adapter, first-audio synchronization, single-completion assertions, and interrupt discard coverage.
- `ai-backend/app/call/session.py` - Adds VoxCPM2 streaming selection, async queue consumption, first/final playback metrics, and shared `TtsSynthesisInput` construction.

## Verification

- `rg -n "ScriptedStreamingTtsAdapter|test_voxcpm2_streaming_speak_enqueues_first_chunk_before_stream_completion|test_voxcpm2_streaming_speak_returns_one_done_event_for_final_turn|test_interrupt_after_first_voxcpm2_stream_chunk_discards_late_chunks|tts_playback_final|chunk_count_at_start" ai-backend/tests/test_call_session.py` - PASS
- `rg -n "_speak_streaming_speech|_adapter_supports_streaming|tts_playback|tts_playback_final|chunk_count_at_start|whole_wav_fallback_used|inter_chunk_gaps_ms" ai-backend/app/call/session.py` - PASS
- `rg -n "AssertionError\(\"whole synthesis fallback was used\"\)" ai-backend/tests/test_call_session.py` - PASS
- `rg -n "time\.sleep" ai-backend/tests/test_call_session.py || true` - PASS, no `time.sleep` usage
- `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` - PASS, 44 passed
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py -q` - PASS, 55 passed
- `git diff --check` - PASS

## Decisions Made

- Kept streaming internal to the AI backend and limited automatic streaming selection to VoxCPM2 adapters exposing `stream(...)`.
- Preserved existing interrupt semantics: `interrupt()` cancels the active speech task, stops the outbound track, and prevents a later `ai_done`.
- Added final playback metrics to done/failure responses as `tts_playback_final` while keeping the immediate `tts_playback` carrier free of final-only totals.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope change.

## Issues Encountered

- During GREEN, the new interrupt test initially expected `speak_text(...)` to return a cancellation object. The existing call contract cancels the active speech task on interrupt, so the test was adjusted to assert the required observable behavior: one first chunk, stopped track, interrupted event, and no `ai_done`.
- Metadata note: the GSD state plan-counter, metric, and decision handlers did not match this project's `STATE.md` structure. Roadmap/session/progress updates were applied through the SDK where supported, and the Phase 08-02 status plus decisions were applied directly to `STATE.md`.
- Metadata note: `gsd-sdk query requirements.mark-complete P8-R1 P8-R3 P8-R4` returned `not_found` because these are Phase 8 SPEC requirement IDs, not global `.planning/REQUIREMENTS.md` IDs. The IDs remain copied verbatim in summary frontmatter for traceability.

## Authentication Gates

None.

## Known Stubs

None. Stub-pattern scan only matched normal list initializers and optional `None` fields in test/session state.

## User Setup Required

None - no external service configuration required. This plan did not deploy to OMEN.

## TDD Gate Compliance

- RED commit present: `e452c0b`
- GREEN commit present after RED: `b5ea507`
- REFACTOR commit: not needed

## Next Phase Readiness

Plan 08-03 can now preserve `/webrtc` and Web UI call semantics around the new nested immediate/final playback metric carriers.

## Self-Check: PASSED

- Summary file exists.
- Key modified files exist.
- Task commits `e452c0b` and `b5ea507` exist in git history.

---
*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Completed: 2026-05-11*
