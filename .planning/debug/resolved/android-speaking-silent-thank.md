---
status: resolved
trigger: "Android Chrome call now stops listening when generation begins, but the UI shows speaking with no audible audio; silence is still transcribed as 'thank you' and generates more silent responses; controls dialog blocks the status/transcript area."
created: 2026-04-27T00:00:00Z
updated: 2026-04-29T02:39:02Z
closure_reason: superseded by solved Android live-call debug session
---

# Debug Session: Android Speaking Silent And Phantom Thank You

## Current Focus

known_pattern_candidate: "Async/timing and state-management boundary: backend media lifecycle, browser remote-track mute state, and UI state indicators are still out of sync."
hypothesis: "Confirmed boundary: TTS bytes are synthesized, enqueued, and drained by the backend track, and Android attaches a remote AudioContext path, but current client logs do not prove the remote track ever unmuted or delivered nonzero audio samples. The remaining root cause is at the outbound WebRTC receiver/playback boundary or hidden by insufficient client diagnostics."
test: "Compared latest OMEN AI/web logs with `CallSession.speak_text`, `QueuedAudioOutputTrack`, browser remote-audio attachment, and toolbar layout code."
expecting: "Patch next should add remote track unmute/RMS evidence and compact controls; if track stays muted/RMS zero while server sends nonzero frames, focus on SDP/transceiver/aiortc outbound media; if RMS positive but inaudible, focus on Android output routing/autoplay."
next_action: "Implement focused diagnostics and UI compact-bar patch; run backend call-session tests plus web unit/e2e call toolbar/mobile tests before canonical deploy."
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

- timestamp: 2026-04-27T17:30:24Z
  observation: "Current local status has unrelated dirty files plus this debug file. Code search identifies the active boundaries in `ai-backend/app/call/session.py`, `ai-backend/app/call/tracks.py`, `web-ui/client/src/routes/call/[threadId]/+page.svelte`, and `web-ui/client/src/lib/components/call/CallToolbar.svelte`."
  source: "git status and rg over ai-backend/web-ui"
- timestamp: 2026-04-27T17:30:24Z
  observation: "Latest OMEN AI log for `rtc_5fb89604e4064a9eb36e9ae99add90a6` shows `tts.enqueue wav_bytes=116780 target=track`, `ai_audio_started`, `tts.playback_wait expected_ms=2432`, outbound `buffer_size` draining from 105216 to 9216, `tts.playback_wait.done completed=True`, then `ai_done`."
  source: "C:\\Users\\pmpg\\rayme\\logs\\ai-backend.run.log via ssh rayme-pmpg"
- timestamp: 2026-04-27T17:30:24Z
  observation: "Matching OMEN web log for `call_c3a56800de5247b7a26a97ab0880af5e` / `rtc_5fb89604e4064a9eb36e9ae99add90a6` shows `pc.ontrack`, `remote_audio.attach`, `remote_audio.track ... muted:true enabled:true`, and `remote_audio.play.ok ... AudioContext state=running`, followed by `ai_audio_started` and `ai_done`; no `remote_audio.track.unmute` or positive remote audio evidence appears in the tailed log."
  source: "C:\\Users\\pmpg\\rayme\\logs\\web-ui.run.log via ssh rayme-pmpg"
- timestamp: 2026-04-27T17:30:24Z
  observation: "Latest user report says phantom thank-you appears gone or improved. The latest backend log still contains one post-playback low-energy phantom-like turn (`rms=0.1/0.5`, `transcript_len=9`) after `ai_done`, but it is not shown as repeated `You're welcome` loops in the latest visible log tail."
  source: "user report plus latest ai-backend.run.log tail"
- timestamp: 2026-04-27T17:30:24Z
  observation: "`CallSession.speak_text` now queues WAV bytes, emits `ai_audio_started`, waits on `outbound_audio_track.wait_until_idle`, then emits `ai_done`; `QueuedAudioOutputTrack.recv` returns queued samples and logs queue/buffer drain. This confirms the old premature-ai_done lifecycle bug is no longer the current audible-audio boundary."
  source: "ai-backend/app/call/session.py and ai-backend/app/call/tracks.py"
- timestamp: 2026-04-27T17:30:24Z
  observation: "Browser `attachRemoteAudio` connects `MediaStreamSource -> Analyser -> destination`, but only logs initial `track.muted`, `mute`, `ended`, and `play.ok`; it does not listen for `unmute`, does not log periodic analyser RMS, and clamps `speakingRms` to at least 0.04. Therefore current logs can show `play.ok` and a visible speaking meter even if actual received audio is zero."
  source: "web-ui/client/src/routes/call/[threadId]/+page.svelte"
- timestamp: 2026-04-27T17:30:24Z
  observation: "`CallToolbar.svelte` renders mute, interrupt, end, input selector, output selector, and fallback copy in one sticky panel. The mobile E2E test currently asserts both comboboxes are visible, so tests encode the large blocking control surface the user wants replaced."
  source: "web-ui/client/src/lib/components/call/CallToolbar.svelte and web-ui/client/tests/e2e/call-mobile.spec.ts"
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
- timestamp: 2026-04-27T17:35:00Z
  observation: "Deployed through canonical `scripts/deploy-omen.sh`. OMEN fast-forwarded to the playback-boundary fix, rebuilt the web client, recreated canonical `RayMePhase1AI` and `RayMePhase1Web` scheduled tasks, verified listeners on 9443 and 8443, and health checks returned resident TTS engine `f5`."
  source: "scripts/deploy-omen.sh output"
- timestamp: 2026-04-27T00:00:00Z
  observation: "Deployment was rechecked after user reported no improvement. Local HEAD and OMEN checkout both report `aae9523`; scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` are running; `/webrtc/status` reports ready with live media transport; `/health` reports resident TTS engine `f5`. The AI log contains new `tts.playback_wait` / `tts.playback_wait.done` markers from commit `21d1a6d`, proving the running backend picked up the deployed fix."
  source: "ssh rayme-pmpg, OMEN health endpoints"
- timestamp: 2026-04-27T00:00:00Z
  observation: "The same post-deploy call `rtc_5fb89604e4064a9eb36e9ae99add90a6` still produced a phantom follow-up turn: after `tts.playback_wait.done completed=True` and `ai_done`, backend returned to listening, then VAD fired on near-zero RMS audio (`rms=0.1`, `peak=1.0`) and STT emitted `transcript_len=9`. Browser logs also show remote audio track attached and AudioContext running, but the track remained `muted:true` and no audible remote playback evidence was recorded."
  source: "C:\\Users\\pmpg\\rayme\\logs\\ai-backend.run.log and web-ui.run.log"
- timestamp: 2026-04-27T00:00:00Z
  observation: "User reports the phantom thank-you problem seems gone or at least improved, but AI speech is still inaudible. User also reports the call controls still block the status/transcript view; current UX makes the mute button becoming clickable the only reliable indication that speaking may begin. Desired UI direction: compact top bar with mute/end-call visible and secondary controls hidden behind an icon/menu."
  source: "user report"

## Eliminated

- hypothesis: "The current blocker is the original offer 502."
  reason: "Previous handoffs show later Android reproductions reached `POST /offer` 200 OK and moved into post-offer media/turn/audio handling."
- hypothesis: "The backend is failing to synthesize TTS bytes."
  reason: "OMEN logs show successful F5 synthesis and non-empty WAV enqueue sizes around 128 KB to 146 KB for affected turns."
- hypothesis: "The browser never attaches the remote audio track."
  reason: "Mirrored Android browser diagnostics show `pc.ontrack`, `remote_audio.attach`, and `remote_audio.play.ok` for the affected call."

## Resolution

root_cause: "Current confirmed boundary is not TTS synthesis or browser track attachment. Backend logs prove non-empty TTS WAV is enqueued and the outbound track buffer drains before `ai_done`; browser logs prove `pc.ontrack`, `remote_audio.attach`, and AudioContext `play.ok`. The remaining unproven link is Android receiving/unmuting nonzero remote audio samples and routing them audibly. Client diagnostics currently mask this because `speakingRms` is clamped to 0.04 and no `unmute`/periodic RMS evidence is logged."
fix: "Recommended next patch: add server outbound-audio sample stats, add browser remote-track `unmute` plus periodic RMS/audio-state diagnostics, gate/label speaking UI based on actual audio evidence where possible, reject near-silent phantom STT turns, and replace the large toolbar with a compact top call bar plus menu."
verification: "Diagnosis only in this pass; no code patch or test run was performed. Proposed verification: backend call-session/webrtc tests, web unit call-audio/call-state tests, Playwright call-toolbar and mobile Chromium layout tests, then one live Android reproduction after canonical deployment."
files_changed: ".planning/debug/android-speaking-silent-thank.md"

## Failed Fix Checkpoint

- The OMEN deploy did happen and the new code is running.
- The fix did not resolve the live Android symptom.
- Next investigation should focus on:
  - why the browser remote audio track remains muted/no audible signal despite backend track buffer drain;
  - whether VAD still treats near-zero RMS silence as speech after returning to listening, now that the user reports phantom thank-you may be gone;
  - why client state transitions still show SSE/data-channel ordering oddities around `ai_done`, `speaking`, and `listening`.
  - replacing the large controls dialog with a compact call control bar that preserves a clear "ready to speak/listening" indicator.
