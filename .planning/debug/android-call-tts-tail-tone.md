---
status: awaiting_human_verify
trigger: "Android live call playback improved after paced TTS frames, but mic input stops truly listening after about five seconds of either continuous speech or pre-speech idle while the UI still says Listening."
created: 2026-04-27T18:42:11Z
updated: 2026-04-27T22:06:30Z
---

# Debug Session: Android Call TTS Tail And Tone

## Current Focus

reasoning_checkpoint:
  hypothesis: "Live-call VAD work grows with total turn duration because `_accept_vad_frame()` calls Silero `speech_timestamps()` on the entire accumulated turn buffer every 20ms; after roughly five seconds of idle or speech this blocks the backend receive loop/turn finalization while the browser animation still reacts locally."
  confirming_evidence:
    - "New live repro says the listening animation now reacts while speaking, proving frontend capture is alive, but the call still sticks in Listening after longer than five seconds."
    - "`_accept_vad_frame()` passes `_buffered_turn_samples()` into `adapter.speech_timestamps()` on every inbound frame; `_buffered_turn_samples()` contains the full current turn."
    - "The red regression `test_silero_vad_analysis_window_stays_bounded_after_five_seconds` observed `max(vad.calls) == 96000` samples after six seconds, proving VAD input grows unbounded instead of staying near a recent window."
  falsification_test: "After bounding only the VAD analysis window, the red regression must pass while `len(session._turn_frames) == 300` still proves STT retains the full turn; existing VAD end-of-turn and >5s max-turn tests must still pass."
  fix_rationale: "Silero only needs a recent analysis window to detect current speech and trailing silence; bounding that window prevents event-loop stalls while preserving the complete turn buffer used for final Whisper transcription."
  blind_spots: "Local tests prove unbounded VAD input but do not measure OMEN GPU/CPU timing directly. Live Android verification is still required after deployment."
next_action: Await parent deployment and live Android Chrome verification of >5s idle-before-speech, >5s continuous speech, and first F5 generation startup latency.

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

## Resolution

root_cause:
  The remaining five-second Android Chrome input freeze was caused by unbounded backend live-call VAD work. For Silero-style VAD, `_accept_vad_frame()` called `adapter.speech_timestamps()` on `_buffered_turn_samples()` for every 20ms inbound frame, and `_buffered_turn_samples()` contained the entire accumulated turn. Both "wait more than five seconds before speaking" and "speak continuously for more than five seconds" therefore made synchronous per-frame VAD analysis grow with total turn duration on the backend event loop. The browser could still animate from local mic input, but backend receive/turn finalization stalled and the call stayed stuck in Listening. The first F5 generation delay had a separate startup cause: `ModelManager.startup()` selected F5 as resident, but `F5TtsAdapter.load()` did not construct the heavy `F5TTS()` runtime until first synthesis.
fix:
  Bounded the Silero VAD analysis input to a recent window large enough for end-of-utterance detection, while preserving the full `_turn_frames` buffer for final Whisper transcription. Added a regression proving six seconds of frames no longer makes VAD receive more than a two-second window while STT still retains all 300 frames. Changed `F5TtsAdapter.load()` to build and retain the runtime at startup, and `unload()` to release it. Added a regression proving `load()` builds the runtime before first synthesis.
verification:
  `uv run pytest tests/test_call_session.py::test_silero_vad_analysis_window_stays_bounded_after_five_seconds tests/test_call_session.py::test_silero_silence_gap_finalizes_turn_even_with_loud_ambient_noise tests/test_call_session.py::test_default_vad_max_turn_does_not_force_end_at_five_seconds tests/test_tts_registry.py::test_f5_adapter_load_builds_runtime_before_first_synthesis tests/test_gpu_runtime.py::test_f5_production_load_requires_torch_cuda -q` passed 5 tests. `uv run pytest tests/test_call_session.py tests/test_tts_registry.py tests/test_model_manager.py tests/test_webrtc_signaling.py -q` passed 55 tests with the existing torch/cuda deprecated `pynvml` warning. `uv run pytest -q` passed 81 tests with the same existing warning. `git diff --check -- ai-backend/app/call/session.py ai-backend/app/models/tts_f5.py ai-backend/tests/test_call_session.py ai-backend/tests/test_tts_registry.py .planning/debug/android-call-tts-tail-tone.md` passed with no output. Live Android Chrome verification is pending parent deployment.
files_changed:
  - ai-backend/app/call/session.py
  - ai-backend/app/models/tts_f5.py
  - ai-backend/tests/test_call_session.py
  - ai-backend/tests/test_tts_registry.py
