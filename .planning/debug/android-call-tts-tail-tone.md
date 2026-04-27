---
status: awaiting_human_verify
trigger: "Android live call is faster after STT warmup and Qwen thinking disable, but AI speech playback still only produces a brief tone or a fraction of the TTS voice before returning to listening."
created: 2026-04-27T18:42:11Z
updated: 2026-04-27T18:49:05Z
---

# Debug Session: Android Call TTS Tail And Tone

## Current Focus

reasoning_checkpoint:
  hypothesis: Android Chrome hears a brief carrier or TTS fragment because `CallSession.speak_text()` emits `ai_audio_started` and waits 80ms before enqueueing real speech, so the UI unmutes while `QueuedAudioOutputTrack` is still sending the 440Hz idle carrier; after enqueue, final `ai_done`/Listening is emitted after the server track drains, not after Android browser playout latency, so the client mutes the media element before the queued RTP audio is fully audible.
  confirming_evidence:
    - "`ai-backend/app/call/session.py` sets state to `speaking`, emits `ai_audio_started`, sleeps 80ms, and only then calls `_queue_outbound_audio(wav_bytes)`."
    - "`QueuedAudioOutputTrack._next_samples()` sends a 440Hz amplitude-500 carrier whenever no AI audio is queued."
    - "`web-ui/client/src/routes/call/[threadId]/+page.svelte` unmutes only when `callState === 'speaking'` and `finishAiTurn()` immediately applies `listening`, which mutes the remote element on `ai_done`."
    - "`CallSession._wait_for_outbound_audio_playback()` waits for the backend track queue/buffer to empty; it does not observe Android Chrome's jitter buffer or speaker playout."
  falsification_test: A focused unit test that records event/enqueue order would disprove the first half if real audio is queued before `ai_audio_started`; a playout-hold test would disprove the second half if `ai_done` is already delayed beyond track drain plus a browser playout cushion.
  fix_rationale: Queue a short silent pre-roll together with speech before emitting `ai_audio_started`, then keep the session in speaking long enough for backend drain plus a browser playout cushion; this gives Android time to unmute on silence instead of the carrier and prevents the UI from muting before buffered RTP playout completes.
  blind_spots: This is verified from code and unit timing behavior, not from a live Android Chrome trace; actual device jitter could require tuning the cushion after deployment.
next_action: Deploy only via `scripts/deploy-omen.sh`, then verify on Android Chrome that a short two-sentence response plays fully without the 440Hz tone before marking resolved.
verification_status: Self-verified by backend unit suite; awaiting Android Chrome/OMEN live-call verification after deployment via `scripts/deploy-omen.sh`.

## Symptoms

expected: After the AI text is generated, the selected TTS voice should be audible for the full response. The user should not hear the idle carrier tone.
actual: On Android Chrome, the first turn is much faster, but after Composing the user hears either a fraction-of-a-second tone or a fraction of the TTS voice, then the call returns to Listening. Repeating the same prompt shows similar behavior.
errors:
  - No explicit user-facing error reported.
  - Audible idle carrier tone leaks briefly.
  - Only a short tail/fragment of TTS voice plays.
timeline:
  - After commit 3cde3bc deployed to OMEN, Whisper warmup and Qwen no-think improved turn latency.
  - The audio problem changed from silent or last-word-only to brief tone/brief TTS fragment.
reproduction: Start call on Android Chrome, speak a short prompt to a character configured to answer in two sentences or less, wait through Understanding and Composing, observe audio playback.

## Evidence

- timestamp: 2026-04-27T18:42:11Z
  checked: User live repro after commit 3cde3bc
  found: First turn is fast; later STT takes around 1-2s; audio output is only a short tone or short TTS fragment.
  implication: WebRTC remote audio path is no longer fully blocked, but playback timing/state gating is still wrong.
- timestamp: 2026-04-27T18:44:51Z
  checked: `.planning/debug/knowledge-base.md`
  found: No knowledge base file exists.
  implication: No prior resolved debug pattern can be tested first.
- timestamp: 2026-04-27T18:44:51Z
  checked: `ai-backend/app/call/session.py`
  found: `speak_text()` emits `ai_audio_started`, sleeps 80ms, then enqueues WAV bytes to the outbound track.
  implication: During the speaking/unmuted pre-roll, the outbound track still has no TTS audio queued.
- timestamp: 2026-04-27T18:44:51Z
  checked: `ai-backend/app/call/tracks.py`
  found: When no queued audio exists, `_next_samples()` emits a 440Hz amplitude-500 keepalive carrier.
  implication: The 80ms pre-enqueue speaking window can leak the audible tone the user reports.
- timestamp: 2026-04-27T18:44:51Z
  checked: `web-ui/client/src/routes/call/[threadId]/+page.svelte`
  found: `syncRemoteAudioAudibility()` mutes the remote media element unless `callState === 'speaking'`; `finishAiTurn()` applies `listening` immediately on `ai_done`.
  implication: Any `ai_done` delivered before Android Chrome finishes playout will mute the remaining queued RTP audio.
- timestamp: 2026-04-27T18:44:51Z
  checked: `CallSession._wait_for_outbound_audio_playback()` and `QueuedAudioOutputTrack.wait_until_idle()`
  found: Playback wait completes when the backend queue and local buffer are empty, not when the browser has rendered the audio.
  implication: The backend can legally emit `ai_done` while the browser still has decoded/jitter-buffered audio to play.
- timestamp: 2026-04-27T18:49:05Z
  checked: Focused fix in `ai-backend/app/call/session.py` and `ai-backend/app/call/tracks.py`
  found: Real TTS audio is now queued with 250ms of silence before `ai_audio_started`, and backend speaking state is held for a 750ms browser playout cushion after the track drains.
  implication: Android Chrome should unmute onto silence instead of the 440Hz carrier and should not be muted immediately when server-side RTP enqueue/drain completes.
- timestamp: 2026-04-27T18:49:05Z
  checked: `uv run pytest -q` in `ai-backend`
  found: 76 tests passed, 1 existing warning from `torch/cuda` importing deprecated `pynvml`.
  implication: Backend regression coverage passed, including new call-audio timing tests.

## Eliminated

- hypothesis: Whisper cold start is the primary cause of this audio failure.
  reason: STT warmup improved first-turn latency, but audio playback still fails.
- hypothesis: The WebRTC remote audio path is completely blocked.
  reason: User hears both a carrier tone and occasional TTS fragments, and the client has a remote media element plus nonzero audio path instrumentation.

## Resolution

root_cause:
  Backend speech state was not aligned with actual browser playout. `speak_text()` emitted `ai_audio_started` and waited 80ms before queueing TTS, so the UI unmuted while the outbound track still emitted the 440Hz keepalive carrier. After enqueue, `ai_done` was emitted after backend queue drain, while Android Chrome could still have audio buffered, so the UI switched to Listening and muted the remote element before the full TTS played.
fix:
  Queue TTS with a 250ms silent pre-roll before emitting `ai_audio_started`, remove the audible pre-enqueue unmute gap, and hold speaking for a 750ms remote playout cushion after backend track drain.
verification:
  Self-verified with `uv run pytest tests/test_call_session.py -q` (22 passed), `uv run pytest tests/test_webrtc_signaling.py -q` (10 passed), and `uv run pytest -q` in `ai-backend` (76 passed, 1 warning).
files_changed:
  - ai-backend/app/call/session.py
  - ai-backend/app/call/tracks.py
  - ai-backend/tests/test_call_session.py
