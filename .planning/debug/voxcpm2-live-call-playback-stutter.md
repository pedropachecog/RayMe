---
status: fixing
created: 2026-05-15T20:00:08.530Z
updated: 2026-05-16T00:00:00.000Z
trigger: "User created a new VoxCPM2 voice; Voice Lab preview sounded fine, but live call playback was extremely choppy on two short exchanges: less than a second of audio, a few milliseconds of silence, then playback resumes repeatedly."
---

# Debug Session: VoxCPM2 Live Call Playback Stutter

## Current Focus

user_goal_preservation: "RayMe must play the generated AI response audibly and smoothly during the call. Fixes must not suppress generation, hide text, avoid VoxCPM2, or silently fall back to the wrong engine."
hypothesis: "Confirmed root cause: live VoxCPM2 streaming chunks can arrive slower than realtime playback. The invalid `1806eb0` fix buffered slow streams until completion, which removed stutter only by violating RayMe's live phone-call invariant."
test: "`uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q`, `uv run --project ai-backend pytest ai-backend/tests -q`, `scripts/operational-check.sh start`, `git diff --check`, canonical OMEN deploy, and physical Android retest with the same newly created VoxCPM2 voice."
expecting: "CallSession uses bounded live startup buffering only: first playback starts before slow stream completion, later chunks continue streaming, immediate first-audio metrics remain separate from final playback metrics, and no live-call code path reports or depends on `buffered_until_complete`."
next_action: "Finish Phase 08.1 incident repair, run full backend and startup verification, commit, push, deploy through `scripts/deploy-omen.sh`, then ask the user to retest."

## Symptoms

expected: A newly created VoxCPM2 voice that previews correctly in Voice Lab should play smoothly during live calls, including short AI responses.
actual: During a live call with the new VoxCPM2 voice, two short exchanges completed but audio playback was extremely choppy: it played for less than a second, briefly went silent for a few milliseconds, then resumed, repeating throughout playback. The user did not attempt the long poem because this is worse than the prior long-message failure.
errors:
  - No explicit user-facing error reported.
  - Voice Lab preview for the same VoxCPM2 voice worked fine.
timeline: Reported on 2026-05-15 immediately after creating a new VoxCPM2 voice to avoid the existing Beau Brown F5 default.
reproduction: Create a new voice in Voice Lab with engine `voxcpm2`, verify preview sounds fine, assign/start a call with that voice, perform two short exchanges, listen to live-call AI playback.

## Evidence

- timestamp: 2026-05-15T20:12:00Z
  checked: Latest OMEN logs for user report after creating a VoxCPM2 voice.
  found: The latest call is `call_4fc082d5e09649d691b45c946bf772f4` / `rtc_260159b693654e7cb73b449409c5590b`. Web logs show browser `call.ai_audio_started` and `remote_audio.rms.*` samples alternating between nonzero RMS and zero RMS during playback. AI backend logs show VoxCPM2 streaming chunks enqueued to the WebRTC track as repeated `wav_bytes=15404`, `samples=7680`, `duration_ms=160` chunks while the VoxCPM progress bar advanced around 3.4-3.6 chunks/s. The outbound track frequently logged `queue_size=0 buffer_size=0` and increasing `idle_frames` between chunk enqueues.
  implication: The live call did use VoxCPM2, and the audible choppiness is consistent with stream chunks arriving slower than realtime playback. The WebRTC track drains each 160 ms chunk before the next chunk arrives and fills the gap with silence. Voice Lab preview is smooth because it uses whole-result synthesis instead of playing each slow streamed chunk as it is generated.
- timestamp: 2026-05-15T20:20:00Z
  checked: Focused backend fix and regression tests.
  found: `CallSession._speak_streaming_speech()` now buffers the first two stream chunks and compares generated inter-chunk gap against playable chunk duration. If the stream is slower than realtime, it buffers until the stream completes before starting playback; otherwise it starts after the continuity check and keeps streaming. Added regression `test_voxcpm2_slow_stream_buffers_until_complete_before_playback` and updated WebRTC playback metrics expectations.
  implication: INVALIDATED on 2026-05-16. This patch preserved VoxCPM2 generation but traded away live phone-call behavior by waiting for full TTS stream completion before first playback. It must not be repeated as a live-call fix.
- timestamp: 2026-05-15T20:22:00Z
  checked: Local backend verification.
  found: `uv run --project ai-backend pytest ai-backend/tests -q` passed: 137 passed, 3 warnings.
  implication: INVALIDATED on 2026-05-16. The tests were green because they encoded the wrong invariant.
- timestamp: 2026-05-16T00:00:00Z
  checked: Phase 08.1 incident repair plan and focused backend regressions.
  found: Inserted Phase 08.1, added `08.1-01-PLAN.md`, replaced full-stream buffering with bounded live startup buffering, and added `test_voxcpm2_slow_stream_starts_playback_before_stream_completion`. Focused verification passed: `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` -> 75 passed, 3 warnings.
  implication: The bad full-response buffering behavior is removed locally. Full backend verification, startup guard, commit, push, OMEN deploy, and user retest remain required.
