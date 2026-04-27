---
status: awaiting_human_verify
trigger: "Android live call playback improved after paced TTS frames, but mic input stops truly listening after about five seconds of either continuous speech or pre-speech idle while the UI still says Listening."
created: 2026-04-27T18:42:11Z
updated: 2026-04-27T21:13:59Z
---

# Debug Session: Android Call TTS Tail And Tone

## Current Focus

reasoning_checkpoint:
  hypothesis: "The client disables the actual WebRTC microphone MediaStreamTrack during `understanding`/`thinking`/`speaking`; on Android Chrome that can make aiortc's inbound `track.recv()` raise after a short no-audio interval, and RayMe's backend currently returns from `_receive_audio_track()` while the session remains non-failed. When `ai_done` later puts the UI back into `Listening`, the browser mic meter can still run locally, but the backend has no active inbound receive loop for future audio, so the ongoing call is effectively frozen."
  confirming_evidence:
    - "`applyCallState()` calls `disableMicrophone()` whenever it leaves `listening` for `understanding`, `thinking`, or `speaking`, and `disableMicrophone()` sets every local audio track's `enabled` to `false`."
    - "The backend already drops inbound frames during `understanding`/`thinking`/`speaking`, so frontend track disabling is not required to prevent phantom STT turns."
    - "`_receive_audio_track()` catches recv exceptions while ICE/connection are live and returns without failing the session, explicitly keeping outbound audio alive. That preserves playback, but it also permanently ends input receiving for the session."
    - "The only remaining source 5s cap found in call/VAD code is `vad_max_turn_ms`, now defaulted to 30000; no repository env/config override for a 5000ms VAD max was found."
  falsification_test: "A regression test should show call state transitions no longer disable the local MediaStreamTrack. Existing backend tests already demonstrate a live ICE recv error exits input receiving without failing the session; after removing client track toggling, Android should no longer trigger that path during normal AI turns."
  fix_rationale: "Keep the WebRTC microphone sender continuously live for the lifetime of the call and rely on backend session-state guards to ignore audio while RayMe is understanding/thinking/speaking. This preserves inbound media liveness across mobile Chrome's short no-sending/disabled-track behavior and prevents UI Listening from diverging from backend input processing."
  blind_spots: "Cannot live-test Android Chrome before deployment. If Android still ends inbound media without frontend disabling, backend needs a second fix to surface receiver death to the UI or renegotiate input."
next_action: Await deployment via the parent workflow and Android Chrome verification that post-AI listening remains active after more than five seconds of idle and continuous speech.

## Symptoms

expected: After the AI text is generated, the selected TTS voice should be audible for the full response. The user should not hear the idle carrier tone.
actual: On Android Chrome after commit `fa12a49`, playback is much better: quick back-and-forth works and long AI messages apparently keep reading. The current failure is that input stops truly listening after about five seconds of continuous speech or about five seconds of idle before speaking while the UI still says Listening.
errors:
  - No explicit user-facing error reported.
  - Audible idle carrier tone leaks briefly.
  - Only a short tail/fragment of TTS voice plays.
  - After ef08e6a, transcript shows the full LLM text, but voice still plays only part of it.
  - A translation-to-Chinese request generated LLM text, then RayMe reported it could not play audio. Chinese support is not required now, but this may reveal non-Latin TTS failure handling.
  - Voice input appears to stop recognizing the user's utterance before the user is done; investigate suspected short capture/VAD duration cap, possibly around 5 seconds.
  - After commit `fa12a49`, the UI can remain in Listening while the listening animation no longer reacts as if sound is being recognized.
  - Waiting about five seconds before speaking can cause input to be ignored.
  - Speaking continuously for more than about five seconds can cause input to stop being recognized.
  - After this failure, the previously successful ongoing call flow appears frozen or broken.
timeline:
  - After commit 3cde3bc deployed to OMEN, Whisper warmup and Qwen no-think improved turn latency.
  - The audio problem changed from silent or last-word-only to brief tone/brief TTS fragment.
  - After commit `fa12a49` deployed, playback improved substantially, but a remaining input/listening freeze appears around a five-second boundary.
reproduction: Start call on Android Chrome. Confirm quick short-turn back-and-forth works. Then either speak continuously for more than about five seconds or wait about five seconds before speaking. Observe that the UI still says Listening, but the listening animation does not react like mic audio is being recognized and the ongoing call stops progressing normally.

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
- timestamp: 2026-04-27T20:34:40Z
  checked: User live Android Chrome repro after OMEN deployment of commit ef08e6a
  found: Behavior improved but remains unacceptable. In one longer call, generated replies consistently played only the second sentence. In another call, the first one-sentence reply played fully, but later replies played only a partial slice of the text, not necessarily a full sentence and possibly not a whole audio chunk. The transcript shows the full LLM text correctly while audible voice plays only part of it. The app also failed audio playback after the LLM generated Chinese text. User input capture may also truncate utterances before the user is done speaking.
  implication: Previous audio-element mute and idle-carrier fix was incomplete. Current investigation must verify text and audio lengths at every boundary, inspect TTS chunking and WebRTC queue/drain behavior, and check hard caps on STT utterance duration, TTS generation, and playback.
- timestamp: 2026-04-27T20:37:54Z
  checked: `ai-backend/app/call/session.py`, `ai-backend/app/call/tracks.py`, `web-ui/server/app/api/calls.py`, `web-ui/server/app/domain/ai_backend_client.py`, `ai-backend/app/api/webrtc.py`, `ai-backend/app/models/tts_f5.py`, `ai-backend/app/config.py`
  found: Call turns pass the complete accumulated LLM `visible_text` into `_speak_call()` and `AiBackendClient.speak_call()`; `SpeakRequest.text` allows 5000 chars and no sentence/chunk slicing was found on the call path. F5 synthesis writes the full returned waveform into a WAV and `CallSession.speak_text()` enqueues the whole `wav_bytes` once. The remaining suspicious outbound path is `QueuedAudioOutputTrack.recv()`, which creates 20ms frames but has no wall-clock pacing. `AiBackendSettings.vad_max_turn_ms` defaults to 5000 and `_accept_vad_frame()` forces `end_of_turn` when `turn_duration_ms >= max_turn_ms`.
  implication: Text/TTS truncation is not evident before enqueue. Two falsifiable candidates remain: unpaced outbound media frames causing partial browser playout, and a default 5s VAD hard cap causing user utterance truncation.
- timestamp: 2026-04-27T20:38:47Z
  checked: Focused timing experiments with current code
  found: Enqueued 1.0s WAV on `QueuedAudioOutputTrack`; receiving 20 20ms frames (400ms media time) completed in 0.0042s wall time. A default live-call VAD loop with continuous speech forced `end_of_turn` at 5000ms. Local aiortc 1.14.0 `AudioStreamTrack.recv()` includes timestamp-based sleeps; RayMe's custom track does not.
  implication: Root cause confirmed for partial TTS playback: outbound audio frames are produced as a burst instead of real-time media. Root cause confirmed for suspected user utterance truncation: default VAD max-turn fallback is 5s.
- timestamp: 2026-04-27T20:40:40Z
  checked: Focused fix applied
  found: `QueuedAudioOutputTrack.recv()` now owns real-time pacing for all outbound frames and uses nonblocking queue reads; default `vad_max_turn_ms` is raised from 5000ms to 30000ms. Added regression tests for paced TTS frame delivery and no forced default turn end at five seconds.
  implication: The fix directly addresses the confirmed media-burst root cause and the confirmed 5s utterance cap while preserving a max-turn safety fallback.
- timestamp: 2026-04-27T20:41:17Z
  checked: `uv run pytest tests/test_call_session.py -q`
  found: 24 tests passed, including new outbound pacing and default VAD max-turn regression tests.
  implication: Focused backend call-session behavior is locally verified.
- timestamp: 2026-04-27T20:41:44Z
  checked: Post-fix timing experiment and `uv run pytest tests/test_webrtc_signaling.py -q`
  found: After pacing, receiving 20 20ms frames (400ms media time) took 0.3804s wall time instead of 0.0042s. WebRTC signaling tests passed: 10 tests.
  implication: The specific burst mechanism is fixed locally and adjacent WebRTC control behavior still passes.
- timestamp: 2026-04-27T20:42:28Z
  checked: `uv run pytest -q` in `ai-backend`
  found: 78 tests passed with the existing torch/cuda deprecated `pynvml` warning.
  implication: Full backend regression suite passes after the pacing and VAD max-turn changes.
- timestamp: 2026-04-27T21:09:23Z
  checked: User live Android Chrome repro after OMEN deployment of commit `fa12a49`
  found: Playback is much better for quick back-and-forth and can apparently keep reading long AI messages. The current failure is input/listening-side: speaking for more than about five seconds, or waiting about five seconds before speaking, causes the app to stop truly listening while the UI still says Listening. The listening animation no longer reacts like sound is being recognized. This can happen after a successful call turn and then freezes/breaks the ongoing call flow.
  implication: The previous TTS pacing fix likely addressed the main playback issue. Continue debugging a separate actual-mic-processing versus displayed-listening-state divergence around a five-second boundary. Inspect remaining 5s caps/timeouts beyond `vad_max_turn_ms`.
- timestamp: 2026-04-27T21:11:48Z
  checked: `web-ui/client/src/routes/call/[threadId]/+page.svelte`, `ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`, repository search for 5s caps
  found: The frontend disables the real local WebRTC microphone track when leaving `listening`; the backend already drops audio in non-listening states; and `_receive_audio_track()` returns on live-ICE recv errors without failing the session. No remaining repository 5000ms VAD max override was found after `AiBackendSettings.vad_max_turn_ms` was raised to 30000.
  implication: The likely state divergence is caused by killing or starving the mobile WebRTC input sender during AI turns, then silently losing the backend receive loop while UI later reports `Listening`.
- timestamp: 2026-04-27T21:13:59Z
  checked: Focused fix and automated regression tests
  found: Frontend call state transitions now keep local WebRTC microphone tracks enabled instead of toggling them off during AI turns. Added unit coverage for keeping call microphone tracks live. `npm run test:unit -- tests/unit/call-audio.test.ts --run` passed 6 tests; `npm run check` passed; `npm run test:unit -- --run` passed 88 tests; `uv run pytest tests/test_webrtc_signaling.py -q` passed 10 tests; `uv run pytest tests/test_call_session.py -q` passed 24 tests; `uv run pytest -q` passed 78 tests with the existing torch/cuda deprecated `pynvml` warning.
  implication: The focused fix is locally verified; live Android Chrome verification is still required after deployment.

## Eliminated

- hypothesis: Whisper cold start is the primary cause of this audio failure.
  reason: STT warmup improved first-turn latency, but audio playback still fails.
- hypothesis: The WebRTC remote audio path is completely blocked.
  reason: User hears both a carrier tone and occasional TTS fragments, and the client has a remote media element plus nonzero audio path instrumentation.
- hypothesis: The original pre-enqueue 80ms `ai_audio_started` gap plus only a fixed 750ms post-drain cushion fully explains the current live failure.
  evidence: After commit c5970c8 was deployed, live Android Chrome still consistently hears the 440Hz carrier and only a short near-tail TTS fragment, so the previous fix was insufficient.
  timestamp: 2026-04-27T20:06:20Z
- hypothesis: Keeping the WebRTC audio element unmuted and replacing idle carrier frames with silence fully fixes Android playback.
  reason: After commit ef08e6a was deployed, the tone issue improved, but longer generated replies still play only a partial audible slice while the transcript contains the full LLM text.
  timestamp: 2026-04-27T20:34:40Z

## Resolution

root_cause:
  The remaining input/listening freeze was caused by the frontend disabling the actual WebRTC microphone MediaStreamTrack when leaving `listening` for `understanding`, `thinking`, or `speaking`. On Android Chrome this can starve/end the inbound media sender after a short interval. The backend's `_receive_audio_track()` then treats live-ICE recv errors as nonfatal and returns without failing the session, preserving outbound playback but permanently stopping backend mic frame processing while the UI later returns to `Listening`. The earlier playback issue was separately caused by unpaced outbound TTS frames, and the earlier continuous-speech 5s cap was addressed by raising `vad_max_turn_ms` to 30000.
fix:
  Kept the WebRTC microphone sender live for the whole call by replacing frontend mic disable/enable state gating with `keepCallMicrophoneTracksLive()`. Backend session-state guards continue to drop inbound frames while RayMe is understanding/thinking/speaking, so phantom STT prevention stays backend-owned without tearing down mobile WebRTC input. Added regression coverage for keeping call microphone tracks enabled.
verification:
  `npm run test:unit -- tests/unit/call-audio.test.ts --run` passed 6 tests; `npm run check` passed; `npm run test:unit -- --run` passed 88 tests; `uv run pytest tests/test_webrtc_signaling.py -q` passed 10 tests; `uv run pytest tests/test_call_session.py -q` passed 24 tests; `uv run pytest -q` passed 78 tests with the existing torch/cuda deprecated `pynvml` warning. Live Android Chrome verification is pending deployment by the parent workflow.
files_changed:
  - web-ui/client/src/lib/call/audio.ts
  - web-ui/client/src/routes/call/[threadId]/+page.svelte
  - web-ui/client/tests/unit/call-audio.test.ts
