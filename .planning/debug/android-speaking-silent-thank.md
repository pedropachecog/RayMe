---
status: fixing
trigger: "Android Chrome call now stops listening when generation begins, but the UI shows speaking with no audible audio; silence is still transcribed as 'thank you' and generates more silent responses; controls dialog blocks the status/transcript area."
created: 2026-04-27T00:00:00Z
updated: 2026-04-27T17:20:00Z
---

# Debug Session: Android Speaking Silent And Phantom Thank You

## Current Focus

hypothesis: "The backend emits ai_audio_started before TTS exists, then emits ai_done and returns to listening immediately after enqueueing audio rather than after the outbound WebRTC track drains."
test: "Inspect OMEN web/AI logs for event ordering around tts.enqueue, ai_done, outbound track buffer_size, browser speakingRms, and subsequent user_final events."
expecting: "If true, logs will show ai_done before queued audio is drained, followed by a new turn while buffer_size is still nonzero or immediately after playback, causing Whisper to transcribe silence/echo."
next_action: "deploy the playback-boundary fix to OMEN through scripts/deploy-omen.sh and ask for one live Android reproduction"
reasoning_checkpoint:
tdd_checkpoint: "Focused backend/server/client tests pass locally; mobile e2e was corrected to mock the diagnostic route and passes."

## Symptoms

expected: "On Android Chrome, after the user speaks and pauses, the app should stop listening while generating, play audible AI speech during the speaking state, then return to listening only after speech playback completes. Silence should not be transcribed as user speech. Call controls should not obscure the status and transcript."
actual: "Last reproduction improved because the app no longer keeps listening after it starts generating. It still shows speaking but no audio is heard. It still hears silence as 'thank you', keeps generating text answers, and repeatedly enters speaking without audible speech. The controls dialog for mute and related actions blocks the status/transcript window, forcing horizontal scrolling."
errors: "No explicit user-facing error is useful. Prior logs included TTS cancellation, queued audio/progress anomalies, and silence/ambient audio being transcribed."
timeline: "Ongoing Phase 3 live Android call debugging across multiple sessions. Current symptom was observed in the latest Android Chrome reproduction on 2026-04-27 after prior fixes."
reproduction: "Open the deployed RayMe web UI on Android Chrome, start a call, allow microphone, wait until actual listening is indicated by the mute button becoming pressable, speak and pause, then observe text generation and speaking state with no audible AI audio. Leave silence and observe phantom 'thank you' user turns."

## Prior Session Context

- `.planning/debug/android-call-speaking-stuck.md`: prior agent marked root cause/fixes around SSE keepalive during `_speak_call()`, explicit `CancelledError` handling, client mic gating, and server frame drops during thinking/speaking. User's latest repro indicates partial improvement only: listening no longer continues through generation, but audio is still inaudible and phantom silence turns remain.
- `.planning/debug/android-call-vad-silence-handoff.md`: previous VAD bug was `_silence_ms` driven incorrectly; commit `0bc6f9d` fixed Silero silence gap handling. That moved the failure past stuck-listening toward STT/LLM/TTS boundaries.
- `.planning/debug/android-call-listening-stuck-handoff.md`: post-offer transport was proven to reach offer 200 OK, with focus shifted to post-offer media, VAD/STT, events, TTS enqueue, and browser playback.
- `.planning/debug/android-call-single-channel-handoff.md`: later evidence showed audio frames and data channel open, but VAD end-of-turn failed; local fixes around max turn duration and keepalive were discussed in that session.
- `.planning/debug/call-working-incident.md`: working-call criteria require microphone media, `user_final`, LLM text, TTS synthesis, outbound WebRTC audio enqueue, browser remote track playback, and live controls against the same session. Synthetic shortcuts must not be reintroduced.

## Constraints

- Deploy to OMEN only through `scripts/deploy-omen.sh`.
- Do not create ad-hoc OMEN deployment scripts or manually manipulate scheduled tasks.
- Do not reintroduce fake/synthetic call success paths.
- Do not claim the call works until live Android path is proven end to end.
- User-facing errors and state indicators are currently poor; improve evidence and UX where it directly helps the debug outcome.
- Controls dialog layout bug is in scope as a secondary UX defect after or alongside the call-state/audio diagnosis.

## Evidence

- timestamp: 2026-04-27T00:00:00Z
  observation: "User reported current live repro: generating stops active listening, but speaking remains silent and silence is still interpreted as 'thank you'."
  source: "user report"
- timestamp: 2026-04-27T17:02:00Z
  observation: "OMEN AI log for rtc_6fac3f67225a4fb4b62c2c6177aefbe6 shows `tts.enqueue ... wav_bytes=137260 target=track`, then `event.sent ... type=ai_done`, then outbound `track.send.progress ... buffer_size=123776/75776/27776`, then `turn.started` and later `stt.result ... transcript_len=21` for the next user turn."
  source: "C:\\Users\\pmpg\\rayme\\logs\\ai-backend.run.log via ssh rayme-pmpg"
- timestamp: 2026-04-27T17:03:00Z
  observation: "Same session repeats the pattern for later turns: `ai_done` is sent immediately after enqueue, server state returns to listening, new VAD/STT turns begin while the previous response buffer is still draining or immediately after. Later generated text includes `You're welcome`, matching phantom thank-you turns."
  source: "C:\\Users\\pmpg\\rayme\\logs\\ai-backend.run.log via ssh rayme-pmpg"
- timestamp: 2026-04-27T17:04:00Z
  observation: "OMEN browser mirrored diagnostics showed remote audio setup succeeded (`remote_audio.play.ok` with AudioContext running), but `pc.connection.failed` snapshots reported `speakingRms:0.04` and `remoteAudioElementPlaying:false`, consistent with UI being in speaking during silent TTS/keepalive rather than audible queued speech."
  source: "C:\\Users\\pmpg\\rayme\\logs\\web-ui.run.log via ssh rayme-pmpg"
- timestamp: 2026-04-27T17:18:00Z
  observation: "Patched local code so backend stays thinking during synthesis, emits ai_audio_started only after WAV bytes are queued, waits for QueuedAudioOutputTrack to drain before emitting ai_done/listening, and routes client state transitions through applyCallState so mic gating runs for data-channel/SSE events."
  source: "local code changes"

## Eliminated

- hypothesis: "The current blocker is the original offer 502."
  reason: "Previous handoffs show later Android reproductions reached `POST /offer` 200 OK and moved into post-offer media/turn/audio handling."
- hypothesis: "The backend is failing to synthesize TTS bytes."
  reason: "OMEN logs show successful F5 synthesis and non-empty WAV enqueue sizes around 128 KB to 146 KB for affected turns."
- hypothesis: "The browser never attaches the remote audio track."
  reason: "Mirrored Android browser diagnostics show `pc.ontrack`, `remote_audio.attach`, and `remote_audio.play.ok` for the affected call."

## Resolution

root_cause: "Call state and media events were tied to TTS request lifecycle instead of actual playback lifecycle. `ai_audio_started` was emitted before synthesis, so Android showed Speaking while only keepalive/silence was flowing. `ai_done` was emitted immediately after enqueue, so server/client returned to listening and reopened/accepted mic input while the AI response was still buffered or just draining. That produced silence/echo turns that Whisper hallucinated as `thank you`."
fix: "Delay ai_audio_started until audio bytes are queued, wait for outbound WebRTC track idle before ai_done/listening, keep client tokens in thinking until ai_audio_started, and ensure all data-channel/SSE state transitions run mic gating."
verification: "Passed: `uv run pytest tests/test_call_session.py tests/test_webrtc_signaling.py` in ai-backend; `uv run pytest tests/test_calls.py` in web-ui/server; `npm run test:unit -- --run tests/unit/call-state.test.ts`; `npm run test:unit -- --run tests/unit/call-audio.test.ts`; `npm run build`; `npm run test:e2e -- tests/e2e/call-mobile.spec.ts --project=mobile-chromium`. Initial Playwright command used a wrong project name (`chromium`) and failed before running tests; rerun used configured project names."
files_changed: "ai-backend/app/call/tracks.py; ai-backend/app/call/session.py; ai-backend/tests/test_call_session.py; web-ui/client/src/routes/call/[threadId]/+page.svelte; web-ui/client/tests/e2e/call-mobile.spec.ts; web-ui/server/app/api/calls.py; .planning/debug/android-speaking-silent-thank.md"
