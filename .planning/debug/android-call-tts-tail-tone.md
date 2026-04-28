---
status: awaiting_human_verify
trigger: "Android live call playback improved after paced TTS frames, but mic input stops truly listening after about five seconds of either continuous speech or pre-speech idle while the UI still says Listening."
created: 2026-04-27T18:42:11Z
updated: 2026-04-28T13:10:00Z
---

# Debug Session: Android Call TTS Tail And Tone

## Current Focus

reasoning_checkpoint:
  hypothesis: "The backend data-channel keepalive never starts on Android because `peer.on_datachannel` receives the browser-created channel with `readyState=open`, while `_attach_peer_handlers()` only starts `_data_channel_keepalive()` from a future `open` event."
  confirming_evidence:
    - "Live AI log for `rtc_233c9e43bf9c4a5696822cc8060416e3` shows `peer.on_datachannel ... readyState=open`, but no backend `datachannel.open` log for that channel."
    - "Live web log has no `datachannel.message` ping events from the backend before the failed long listening span."
    - "The red test `test_data_channel_keepalive_starts_when_browser_channel_already_open` fails because the already-open fake channel sends `[]` instead of the expected first ping."
    - "Quick short turns create normal data-channel traffic (`state`, `user_final`, `ai_audio_started`, `ai_done`), while waiting or speaking longer leaves the data channel idle after `ai_done`."
  falsification_test: "If starting keepalive immediately for already-open channels does not send pings in the focused unit test, or live logs after deployment still show no ping events, this hypothesis is wrong or incomplete."
  fix_rationale: "Starting `_data_channel_keepalive()` when the channel is already open closes the missed-event gap without changing media tracks, VAD, TTS, or frontend state handling."
  blind_spots: "This does not prove Android Chrome will keep the entire peer alive until a deployed live repro; it only proves the missing keepalive mechanism that matches the control-channel idle pattern."
next_action: "Parent should deploy through `scripts/deploy-omen.sh` only, then live-verify Android Chrome quick turns, >5s idle-before-speech, and >5s continuous speech; live logs should show backend `datachannel.open ... already_open=True` plus browser ping messages."

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
  - After OMEN deployment of commits `d995d22` and `8d27249`, the same failure remains unchanged: quick short messages work; waiting about five seconds before speaking or speaking for more than five seconds fails.
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
- timestamp: 2026-04-27T21:24:46Z
  checked: User live Android Chrome repro after OMEN deployment of commit `5e237bc`
  found: Behavior is exactly the same as before the mic-track keepalive fix. Quick short-turn calls still work. Waiting more than five seconds before speaking does not work and freezes the call. Speaking for more than five seconds also does not work and freezes the call.
  implication: The frontend mic-track disabling hypothesis is falsified as the live root cause. Continue debugging a distinct five-second input freeze path while preserving the already-improved TTS playback behavior.
- timestamp: 2026-04-27T21:26:34Z
  checked: Source search and full read of call input path
  found: No remaining source `5000` VAD cap is active after `vad_max_turn_ms` was raised to 30000. The remaining input-side freeze candidate is `_receive_audio_track()`: on any `track.recv()` exception while ICE/connection are still live, it logs `track.recv.inbound_ended` and returns permanently without failing the session.
  implication: A transient Android Chrome RTP/read gap can kill backend input processing while preserving UI `Listening` and outbound playback. This matches quick turns working but the call freezing after a longer idle/speech boundary.
- timestamp: 2026-04-27T21:27:24Z
  checked: `uv run pytest tests/test_webrtc_signaling.py::test_receive_audio_track_recovers_from_transient_live_ice_recv_errors -q` before fix
  found: Test failed red. The scripted track raised one live-ICE recv exception, `_receive_audio_track()` returned, `recv_calls` was 1 instead of at least 4, and no resumed audio frame was processed.
  implication: The code has the exact permanent input-loop death behavior needed to explain the live five-second freeze once Android Chrome/aiortc emits a transient recv exception.
- timestamp: 2026-04-27T21:31:21Z
  checked: Focused receive-loop fix and regression tests
  found: `_receive_audio_track()` now retries live-ICE recv exceptions with bounded backoff instead of returning, while still failing on failed/closed peer states and preserving outbound audio. The old media-stream-error regression was updated to verify the session is not failed/closed and the loop exits when the session ends. New regression coverage proves resumed frames after transient live-ICE recv errors are processed.
  implication: Backend listening no longer silently dies after a transient Android Chrome/aiortc inbound read gap, which is the concrete mechanism behind UI `Listening` diverging from actual input processing.
- timestamp: 2026-04-27T21:31:21Z
  checked: Automated verification
  found: `uv run pytest tests/test_webrtc_signaling.py::test_receive_audio_track_recovers_from_transient_live_ice_recv_errors tests/test_webrtc_signaling.py::test_receive_audio_track_media_stream_error_with_live_ice_does_not_fail_session -q` passed 2 tests; `uv run pytest tests/test_webrtc_signaling.py -q` passed 11 tests; `uv run pytest tests/test_call_session.py -q` passed 24 tests; `uv run pytest -q` passed 79 tests with the existing torch/cuda deprecated `pynvml` warning.
  implication: Focused red/green regression and adjacent backend coverage pass locally. Live Android Chrome verification still requires parent deployment.
- timestamp: 2026-04-27T22:01:34Z
  checked: User live Android Chrome repro after latest attempted fix
  found: The listening animation now fires while speaking, but if the user takes longer than five seconds it still freezes the call. The UI remains stuck in Listening, but the app does not actually listen or progress. The first F5 generation also takes a couple of seconds to start.
  implication: Frontend capture/animation and previous receive-loop retry work changed the visible symptom but did not fix backend turn completion. Continue investigation after capture: backend VAD/STT end-of-turn, session state, timers, and model warmup.
- timestamp: 2026-04-27T22:02:36Z
  checked: `CallSession._accept_vad_frame()` and model startup paths
  found: With a Silero-style VAD adapter, every 20ms inbound frame calls `adapter.speech_timestamps(self._buffered_turn_samples())`, where `_buffered_turn_samples()` contains the entire accumulated turn. The full turn buffer is also retained for STT, so idle-before-speech and continuous-speech both make per-frame VAD work grow with total turn length. Separately, `ModelManager.startup()` calls `F5TtsAdapter.load()`, but `load()` does not build `F5TTS()`; the heavy runtime is built lazily on first `synthesize()`.
  implication: The remaining freeze can be a backend event-loop/receive-loop stall from unbounded per-frame VAD analysis rather than missing capture. The first F5 generation delay is explained by lazy runtime construction despite startup load.
- timestamp: 2026-04-27T22:03:21Z
  checked: `uv run pytest tests/test_call_session.py::test_silero_vad_analysis_window_stays_bounded_after_five_seconds -q` before fix
  found: Test failed red: after 300 frames / six seconds, the fake Silero adapter received up to 96000 samples instead of a bounded <=32000 sample analysis window, while the full turn buffer contained 300 frames.
  implication: The code directly reproduces unbounded per-frame VAD analysis past the five-second boundary without needing Android-specific capture failure.
- timestamp: 2026-04-27T22:06:30Z
  checked: Focused VAD-window and F5 warmup fixes
  found: `_accept_vad_frame()` now passes only a recent VAD analysis window to Silero while preserving the complete `_turn_frames` buffer for STT. `F5TtsAdapter.load()` now builds and retains the F5 runtime, and `unload()` releases it.
  implication: Live-call VAD work no longer grows unbounded after five seconds, and startup residency now actually warms F5 instead of deferring heavy runtime creation to the first generated reply.
- timestamp: 2026-04-27T22:06:30Z
  checked: Automated verification
  found: `uv run pytest tests/test_call_session.py::test_silero_vad_analysis_window_stays_bounded_after_five_seconds tests/test_call_session.py::test_silero_silence_gap_finalizes_turn_even_with_loud_ambient_noise tests/test_call_session.py::test_default_vad_max_turn_does_not_force_end_at_five_seconds tests/test_tts_registry.py::test_f5_adapter_load_builds_runtime_before_first_synthesis tests/test_gpu_runtime.py::test_f5_production_load_requires_torch_cuda -q` passed 5 tests. `uv run pytest tests/test_call_session.py tests/test_tts_registry.py tests/test_model_manager.py tests/test_webrtc_signaling.py -q` passed 55 tests with the existing torch/pynvml warning. `uv run pytest -q` passed 81 tests with the same existing warning. `git diff --check` passed.
  implication: Focused red/green tests and adjacent backend suites pass locally. Live Android Chrome verification still requires parent deployment.
- timestamp: 2026-04-28T12:17:38Z
  checked: User live Android Chrome repro after OMEN deployment of commits `d995d22` and `8d27249`
  found: Nothing changed. Exact same symptoms remain: quick short messages work, but either waiting about five seconds before speaking or speaking continuously for more than five seconds freezes the call.
  implication: The bounded Silero VAD analysis fix and F5 startup warmup are not sufficient to fix the live input freeze.
- timestamp: 2026-04-28T12:17:38Z
  checked: OMEN runtime state and logs after failed repro
  found: OMEN is running deployed HEAD `8d27249` with listeners on ports 9443 and 8443. AI logs for `rtc_233c9e43bf9c4a5696822cc8060416e3` show a successful first turn, then second-turn listening with bounded `analysis_samples=3200`, continuous `track.recv.progress` until frame 2000, followed by peer signaling closed, `MediaStreamError`, datachannel close, ICE closed, and connection closed.
  implication: The deployed code is active, VAD analysis is bounded, and the next failure is not explained by unbounded VAD compute. The browser/peer connection is being closed/failing after the first AI turn while the backend is waiting for the next user turn.
- timestamp: 2026-04-28T12:17:38Z
  checked: OMEN web debug logs for `call_3f179096348e437387c98bd837368bae`
  found: Browser debug logs show datachannel `ai_done`, then a delayed duplicate turn-stream `call.ai_audio_started` for the same turn, then state debug `mic.keep_live` changes from listening to speaking, then `pc.iceconnectionstatechange` disconnected, `pc.connectionstatechange` disconnected, `pc.connection.failed`, later `connectionState=failed`, and `/end`.
  implication: Investigate client/server turn-stream event ordering and frontend call-state handling after `ai_done`; a stale `ai_audio_started` may be putting the UI back into Speaking or otherwise interfering with the live peer connection after the turn completes.
- timestamp: 2026-04-28T12:55:00Z
  checked: `web-ui/client/src/routes/call/[threadId]/+page.svelte`
  found: The delayed turn-stream `ai_audio_started` is accepted without turn-order guarding and can cause a stale `listening` -> `speaking` UI transition, but that path only calls `keepCallMicrophoneTracksLive()` and `ensureRemoteCallAudioAudible()`; the page only closes browser media on startup failure, explicit hangup, or route destroy.
  implication: The stale SSE event is a real invalid UI transition but does not provide a direct app-code path for closing the peer connection.
- timestamp: 2026-04-28T12:55:00Z
  checked: Live OMEN AI/web logs for `rtc_233c9e43bf9c4a5696822cc8060416e3` / `call_3f179096348e437387c98bd837368bae`
  found: Backend logs `peer.on_datachannel ... readyState=open`, but there is no backend `datachannel.open` log and no browser `datachannel.message` ping events. `_data_channel_keepalive()` is only started by the backend `open` handler, so this already-open channel never starts keepalive. The failure occurs after the first-turn `ai_done` when no further data-channel events are emitted during the next idle/listening span.
  implication: This matches quick short turns working while >5s idle or >5s continuous speech fails: short turns produce normal data-channel traffic before the idle gap, but long silent/listening spans do not.
- timestamp: 2026-04-28T13:02:00Z
  checked: `uv run pytest tests/test_webrtc_signaling.py::test_data_channel_keepalive_starts_when_browser_channel_already_open -q`
  found: Test failed red: the already-open fake data channel sent `[]` instead of `['{\"type\":\"ping\"}']`.
  implication: The current backend definitely misses keepalive startup for the exact `readyState=open` ordering observed in the live Android repro logs.
- timestamp: 2026-04-28T13:10:00Z
  checked: Focused keepalive fix in `ai-backend/app/api/webrtc.py`
  found: `_attach_peer_handlers()` now starts `_data_channel_keepalive()` immediately when the browser-created `rayme-events` data channel is already `readyState=open`, while preserving the existing future `open` handler and close cancellation.
  implication: The backend no longer depends on an `open` event that aiortc may have already missed before handler registration.
- timestamp: 2026-04-28T13:10:00Z
  checked: Automated verification
  found: `uv run pytest tests/test_webrtc_signaling.py::test_data_channel_keepalive_starts_when_browser_channel_already_open -q` passed after failing red. `uv run pytest tests/test_webrtc_signaling.py -q` passed 12 tests. `uv run pytest tests/test_call_session.py -q` passed 25 tests. `uv run pytest -q` passed 82 tests with the existing torch/cuda deprecated `pynvml` warning. `git diff --check` passed.
  implication: The focused regression and adjacent backend suites pass locally. Live Android Chrome verification still requires parent deployment.

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
- hypothesis: Keeping the WebRTC microphone MediaStreamTrack enabled across non-listening states fully fixes the Android input freeze.
  reason: After commit 5e237bc was deployed, user live Android Chrome repro showed no behavior change: quick turns work, but waiting more than five seconds before speaking or speaking more than five seconds still freezes the call.
  timestamp: 2026-04-27T21:24:46Z
- hypothesis: Retrying transient live-ICE `track.recv()` exceptions fully fixes the Android input freeze.
  evidence: After the latest attempted fix, the listening animation now fires while speaking, so capture is visibly alive, but taking longer than five seconds still leaves the call stuck in Listening with no turn progress.
  timestamp: 2026-04-27T22:01:34Z
- hypothesis: Bounding Silero VAD analysis to a recent window fully fixes the Android five-second input freeze.
  reason: After deployment of commit `d995d22` and deploy-script commit `8d27249`, user live repro reports no behavior change. OMEN logs prove the bounded VAD code is active (`analysis_samples=3200`) during the second listening turn before the peer connection closes.
  timestamp: 2026-04-28T12:17:38Z
- hypothesis: The delayed duplicate turn-stream `ai_audio_started` directly closes the browser peer connection.
  evidence: Frontend inspection shows that `ai_audio_started` only applies the UI state `speaking`, keeps microphone tracks enabled, and ensures the remote audio element is unmuted. The only frontend peer-closing paths are startup failure, explicit hangup, or route destroy.
  timestamp: 2026-04-28T12:55:00Z

## Resolution

root_cause:
  The live Android Chrome freeze is caused by missed backend data-channel keepalive startup for browser-created data channels that arrive at aiortc already open. In the failed live session, the backend logged `peer.on_datachannel ... readyState=open`, but never logged backend `datachannel.open` and the browser never received data-channel ping messages. `_attach_peer_handlers()` only started `_data_channel_keepalive()` from a future `open` event, so this path left the app/control channel idle after first-turn `ai_done`. Quick short turns still worked because normal `state`/`user_final`/`ai_audio_started`/`ai_done` events refreshed the data channel before the idle gap; waiting about five seconds or speaking continuously longer than that produced no data-channel events and the Android peer eventually disconnected/failed.
fix:
  Added duplicate-safe immediate keepalive startup when the incoming `rayme-events` data channel is already `readyState=open`, while preserving the existing future `open` event handler and close cancellation. Added a regression test that failed before the fix because an already-open channel sent no ping, then passed after the fix.
verification:
  `uv run pytest tests/test_webrtc_signaling.py::test_data_channel_keepalive_starts_when_browser_channel_already_open -q` failed red before the fix and passed after. `uv run pytest tests/test_webrtc_signaling.py -q` passed 12 tests. `uv run pytest tests/test_call_session.py -q` passed 25 tests. `uv run pytest -q` passed 82 tests with the existing torch/cuda deprecated `pynvml` warning. `git diff --check` passed. Live Android Chrome verification is pending parent deployment.
files_changed:
  - ai-backend/app/api/webrtc.py
  - ai-backend/tests/test_webrtc_signaling.py
