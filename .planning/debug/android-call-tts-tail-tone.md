---
status: awaiting_human_verify
trigger: "Android live call is faster after STT warmup and Qwen thinking disable, but AI speech playback still only produces a brief tone or a fraction of the TTS voice before returning to listening."
created: 2026-04-27T18:42:11Z
updated: 2026-04-27T20:12:11Z
---

# Debug Session: Android Call TTS Tail And Tone

## Current Focus

reasoning_checkpoint:
  hypothesis: Android Chrome hears a brief 440Hz tone and only a near-tail TTS fragment because the remote WebRTC audio element is muted/unmuted from app-state events that are not synchronized to media playout, while the idle RTP keepalive content is itself an audible 440Hz sine wave.
  confirming_evidence:
    - "`QueuedAudioOutputTrack._next_samples()` emits amplitude-500 440Hz sine frames whenever no TTS is queued."
    - "`+page.svelte` creates the remote audio element muted unless `callState === 'speaking'`, unmutes only while speaking, and remutes immediately when `ai_done` calls `finishAiTurn()`."
    - "`web-ui/server/app/api/calls.py` yields the reliable SSE `ai_audio_started` only after `_speak_call()` completes; `_speak_call()` returns after backend `speak_text()` waits for playback and emits `ai_done`."
    - "Live Android Chrome after commit c5970c8 still hears a short sine wave and then a near-tail speech fragment, matching late unmute of an already-playing WebRTC stream."
  falsification_test: If idle `recv()` frames are silent and the client keeps the remote media element unmuted independent of `callState`, then late/duplicate `ai_audio_started` and `ai_done` events can no longer expose the carrier or cut off media playout; focused tests should fail on the current code and pass after the fix.
  fix_rationale: Make the WebRTC media stream safe to keep audible continuously by changing idle frames to silence, then remove state-based muting of the remote element so media playout is not controlled by delayed SSE/data-channel events.
  blind_spots: This is verified by code path and regression tests, not by a fresh Android Chrome live deployment; actual transport behavior still needs parent-agent OMEN deployment and phone verification.
next_action: Parent agent should review, commit, deploy via `scripts/deploy-omen.sh` only, then verify on Android Chrome that generated speech plays fully with no 440Hz tone or tail-only fragment.
verification_status: Live Android Chrome verification failed after OMEN deployment of commit c5970c8; continue investigation.

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
- timestamp: 2026-04-27T19:18:00Z
  checked: User live Android Chrome repro after OMEN deployment of commit c5970c8
  found: Calls mostly work except audio playback. The user consistently hears the sine wave for a fraction of a second, followed by the TTS voice for a fraction of a second. The audible TTS is no longer the last word; it is part of a word near the end, possibly around five words before the end.
  implication: The prior timing fix moved the audible fragment earlier but did not prevent early client mute or carrier leakage. The remaining root cause is likely not just pre-enqueue event order; investigate client audibility gating, RTP timestamp/drain accounting, track buffer semantics, and whether `wait_until_idle()` finishes before packets are actually sent/played.
- timestamp: 2026-04-27T20:06:20Z
  checked: Resume context, project skills discovery, active worktree
  found: No project-local skill files were found under `.claude/skills/` or `.agents/skills/`; worktree already has unrelated dirty files plus this debug session file. The prior root-cause/fix fields describe the failed commit c5970c8 hypothesis, so they are no longer a verified resolution.
  implication: Continue with repository-local investigation only; preserve unrelated dirty files and replace the resolution only after a newly confirmed root cause is tested.
- timestamp: 2026-04-27T20:07:13Z
  checked: `web-ui/client/src/routes/call/[threadId]/+page.svelte`
  found: The remote audio element is created muted unless the state is already `speaking`; `syncRemoteAudioAudibility()` unmutes only for `callState === 'speaking'`; `finishAiTurn()` immediately applies `listening` on `ai_done`, muting the element again.
  implication: If `ai_audio_started` arrives after WebRTC RTP playback has already advanced, Android will hear only the remaining tail. If `ai_done` follows closely, playback is cut off again.
- timestamp: 2026-04-27T20:08:27Z
  checked: `web-ui/server/app/api/calls.py` `/api/calls/{call_id}/turns` implementation
  found: The route starts `_speak_call()` as a task, yields only SSE keepalive comments while it runs, then extracts and yields nested `ai_audio_started_event` only after `await tts_task` completes. The AI backend `/speak` response is produced after `CallSession.speak_text()` has waited for outbound playback and emitted `ai_done`.
  implication: The reliable SSE `ai_audio_started` path is late by design. The early path depends on WebRTC data channel delivery, so browser audio playback must not be hard gated by these app-state events.
- timestamp: 2026-04-27T20:12:11Z
  checked: Focused fix and regression tests
  found: `QueuedAudioOutputTrack` idle frames now return silence instead of a 440Hz carrier; the browser remote audio element is created unmuted and `syncRemoteAudioAudibility()` only ensures it remains audible. Added tests proving silent idle keepalive and state-independent remote audio audibility.
  implication: Late or duplicate `ai_audio_started`/`ai_done` events can no longer expose a carrier tone or mute the media stream before Android finishes playout.
- timestamp: 2026-04-27T20:12:11Z
  checked: Automated verification
  found: `uv run pytest tests/test_call_session.py -q` passed 22 tests; `uv run pytest tests/test_webrtc_signaling.py -q` passed 10 tests; `uv run pytest -q` passed 76 tests with the existing torch/pynvml warning; `npm run test:unit -- tests/unit/call-audio.test.ts --run` passed 5 tests; `npm run check` passed; `npm run test:unit -- --run` passed 87 tests.
  implication: The targeted regression coverage and adjacent backend/frontend suites pass locally; live Android verification still requires deployment by the parent agent.

## Eliminated

- hypothesis: Whisper cold start is the primary cause of this audio failure.
  reason: STT warmup improved first-turn latency, but audio playback still fails.
- hypothesis: The WebRTC remote audio path is completely blocked.
  reason: User hears both a carrier tone and occasional TTS fragments, and the client has a remote media element plus nonzero audio path instrumentation.
- hypothesis: The original pre-enqueue 80ms `ai_audio_started` gap plus only a fixed 750ms post-drain cushion fully explains the current live failure.
  evidence: After commit c5970c8 was deployed, live Android Chrome still consistently hears the 440Hz carrier and only a short near-tail TTS fragment, so the previous fix was insufficient.
  timestamp: 2026-04-27T20:06:20Z

## Resolution

root_cause:
  Android Chrome playback was controlled by app-state events instead of the media timeline. The remote WebRTC audio element was muted except during `speaking`, but the reliable SSE `ai_audio_started` event is yielded only after backend speech playback has already completed or nearly completed, and `ai_done` immediately remutes the element. The media stream kept flowing underneath with an audible 440Hz idle carrier, so a late unmute exposed the carrier plus only the remaining tail of TTS.
fix:
  Changed idle outbound WebRTC frames from an audible 440Hz sine carrier to silent frames, and changed the browser remote audio policy to keep the media element unmuted independent of call state. Added regression coverage for silent idle keepalive and state-independent remote audio audibility.
verification:
  Self-verified with focused and broader local tests: backend call session, backend WebRTC signaling, full ai-backend pytest, client call-audio unit test, Svelte check, and full client unit test suite. Pending live Android Chrome verification after OMEN deployment.
files_changed:
  - ai-backend/app/call/tracks.py
  - ai-backend/tests/test_call_session.py
  - web-ui/client/src/lib/call/audio.ts
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/unit/call-audio.test.ts
