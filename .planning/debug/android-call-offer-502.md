---
status: fixing
trigger: "Android Chrome Phase 3 live call: microphone permission is granted and Android shows mic listening, then the RayMe call UI still fails or becomes unusable."
created: 2026-04-25T23:36:09Z
updated: 2026-04-26T19:00:00Z
---

# Debug Session: Android Call Offer 502

## Symptoms

- Expected behavior: on Android Chrome, starting a call to `ThickGiant` asks for
  microphone permission, enters `Listening`, shows visible microphone activity,
  accepts user speech, transcribes the turn, generates an AI response, and plays
  F5 speech.
- Actual behavior reported by product-owner testing:
  - Initial deploy: Android did not ask for microphone permission, UI showed no
    activity, and hangup showed `Failed`.
  - After `3226fd5`: Android asked for microphone permission, then failed after
    one or two seconds.
  - After `a325c35`: Android showed that the microphone was listening, then
    still failed.
  - After `66e2850`: not yet manually retested by product owner at the time this
    debug file was written.
- Android device/client IP seen in OMEN logs: `192.168.1.253`.
- Developer desktop/browser smoke IP seen in OMEN logs: `192.168.1.190`.

## Current Focus

- status: fixing — committing VAD max-turn safety net (already in working tree)
  and repairing test mock that is missing the `threshold` attribute.
- hypothesis (CONFIRMED): Silero VAD classifies all buffered audio as continuous
  speech (no silence gap), so `_silence_ms` never reaches `vad_end_silence_ms`
  and `end_of_turn` never fires. Fix: force `end_of_turn` after
  `vad_max_turn_ms` (5000 ms) of continuous turn duration.
- reasoning_checkpoint:
    hypothesis: "frame_idx * frame_ms >= vad_max_turn_ms forces end_of_turn
      when Silero never produces a silence gap"
    confirming_evidence:
      - "Boundary trace @ 9275e36: vad.speech_start fires on frame 15 but
        vad.silence/vad.end_of_turn NEVER fire over 450+ frames (~9 s)"
      - "vad.bufdiag confirms buf_rms > 0 (real speech-shaped audio reaching
        Silero)"
      - "Silero ts_count=0 at frame 10 then vad.speech_start fires — adapter
        classifies everything as one continuous segment"
    falsification_test: "after deploy, vad.end_of_turn log line must appear
      within 5-6 s of vad.speech_start"
    fix_rationale: "adds a hard ceiling on turn duration so the turn always
      finalizes even when Silero never produces a trailing silence gap"
    blind_spots: "ICE disconnect at ~9-10 s may still kill the session before
      STT/LLM/TTS completes; data-channel keepalive (faac744) is deployed and
      may address this"
- pre_commit_blocker: test mock ScriptedSileroVadAdapter is missing `threshold`
  attribute; `session.py` accesses `adapter.threshold` at frame 10 for
  diagnostic logging. Fix: add `threshold: float = 0.5` to mock.
- next_action: fix mock, run tests to green, commit, push, deploy, ask user to
  reproduce on Android Chrome and confirm vad.end_of_turn fires within ~5 s.

## Evidence

- timestamp: 2026-04-25T22:33Z
  observation: Commit `3226fd5` fixed the first startup defect.
  details:
    - `web-ui/client/src/routes/call/[threadId]/+page.svelte` now calls
      `navigator.mediaDevices.getUserMedia` before starting the call.
    - The browser now posts `/api/calls/{call_id}/offer`.
    - Android correctly asks for microphone permission after this commit.

- timestamp: 2026-04-25T22:44Z
  observation: Commit `a325c35` fixed the opaque client-side post-permission
  failure path.
  details:
    - Local mic metering starts immediately after microphone permission.
    - The call UI reaches `Listening` before WebRTC remote answer application.
    - `setRemoteDescription` failures no longer force the generic `Failed`
      panel.

- timestamp: 2026-04-25T23:00Z
  observation: OMEN hidden web logs captured the Android real failure.
  exact_lines:
    - `INFO: 192.168.1.253:41462 - "POST /api/calls/start HTTP/1.1" 201 Created`
    - `INFO: 192.168.1.253:41462 - "POST /api/calls/call_7348bdbc558449e09ea44a6d8e696802/offer HTTP/1.1" 502 Bad Gateway`
  interpretation: Android got past permission and call creation. The failing
  boundary was offer forwarding, not mic permission or thread loading.

- timestamp: 2026-04-25T23:00Z
  observation: AI backend hidden logs did not show a corresponding
  `/webrtc/offer` access line for the Android 502.
  details:
    - AI log tail showed health/status requests only.
    - `/webrtc/status` reported `active_sessions: 2`.
  interpretation: either the web facade timed out/failed before the request was
  logged by uvicorn, or the logging tail did not capture the request. This needs
  targeted instrumentation.

- timestamp: 2026-04-25T23:20Z
  observation: Commit `66e2850` was deployed to OMEN.
  details:
    - Deployed commit: `66e2850c32f6dc8a988941960899689eb5835672`.
    - Web listener: `192.168.1.199:8443`, pid `30876` before this handoff.
    - AI listener: `192.168.1.199:9443`, pid `36408` before this handoff.
    - Live desktop smoke after deploy reached `Listening`, posted
      `/api/calls/start` and `/api/calls/{id}/offer`, and had no browser errors.
  limitation: this smoke uses fake media on desktop Chromium and does not prove
  Android SDP, Android media transport, STT, LLM, or F5 playback.

- timestamp: 2026-04-25T23:59Z
  observation: Product-owner retest reports the latest change regressed UX.
  details:
    - Android starts a call and continues showing/listening.
    - Nothing progresses until the user hangs up.
    - Keeping the dialog alive is not an improvement.
  interpretation: failed offer negotiation must terminate the call attempt and
    surface the exact backend failure instead of leaving the user in an
    apparently active listening state.

- timestamp: 2026-04-25T23:59:30Z
  observation: Root cause confirmed and fixed in focused regression coverage.
  details:
    - `connectBrowserMedia` no longer catches and ignores `sendCallOffer`
      failures.
    - `sendCallOffer` now parses public error payloads and throws
      `CallApiError` with the backend code/message.
    - call startup failure stops local media, shows the failure panel, and
      sends `endCall(..., "setup_failed")` for cleanup.
    - media teardown is defensive so cleanup cannot block failure presentation.
    - the web AI backend client preserves sanitized `/webrtc/offer` 5xx
      `detail.code` and `detail.message`.
  interpretation: the user-visible regression was in the client startup error
    path, not microphone permission. Backend offer failures now terminate the
    attempt and show the precise sanitized reason.

- timestamp: 2026-04-26T00:25Z
  observation: Production call facade synthetic success branches were removed.
  details:
    - Missing `create_webrtc_offer` now raises
      `call_backend_client_misconfigured` instead of returning `answer: None`.
    - Missing `mute_call`, `interrupt_call`, `end_call`, and `speak_call` now
      raise `call_backend_client_misconfigured` instead of returning local
      success.
    - `end_call` still records the local call boundary for backend runtime
      control failures, but it no longer hides a misconfigured backend client.
    - Regression coverage was added to `web-ui/server/tests/test_calls.py`.
    - The production synthetic-path guard now rejects `answer: None`.
  interpretation: this fixes the identified fake call facade behavior. It does
    not prove the live Android call is working end to end.

## Eliminated

- hypothesis: Android Chrome did not receive or load the newest client bundle.
  evidence: hidden logs show Android loaded hashed bundle assets
  `start.DGM4CIoX.js` / `app.BSrKBRPv.js` after the `a325c35` deploy, and later
  deployments changed hashes again.

- hypothesis: microphone permission is the remaining blocker.
  evidence: product owner reports Android shows mic listening, and server logs
  show Android reaches `/api/calls/start` and `/api/calls/{id}/offer`.

- hypothesis: the Web UI cannot create call records on OMEN.
  evidence: Android got `201 Created` from `/api/calls/start`.

- hypothesis: the AI backend process is down.
  evidence: `/health` responds with `status: degraded`, `stt_model:
  distil-large-v3`, `vad_ready: True`, `resident_tts_engine: f5`; listeners are
  up on `8443` and `9443`.

## Code Changes Already Applied

- `e77b0e4 fix(03-11): support OMEN Python typing`
  - Fixed Python 3.10 `typing.NotRequired` import crash on OMEN.

- `3226fd5 fix(03-11): request mic and negotiate call session`
  - Added explicit microphone request.
  - Added browser WebRTC offer posting from the call route.

- `a325c35 fix(03-11): keep Android call UI alive after mic grant`
  - Added local mic meter.
  - Kept UI alive when remote SDP application fails.

- `66e2850 fix(03-11): keep call active when Android offer fails`
  - Client no longer fails the whole call if `/api/calls/{id}/offer` returns an
    error.
  - Server `end_call` records a local call end even if backend session control
    fails.
  - Product-owner retest says this is a regression: the call now appears to keep
    listening while no backend turn happens.

## Verification Already Run

- `npm --prefix web-ui/client run check` passed.
- `npm --prefix web-ui/client run build` passed.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts --project=desktop-chromium --workers=1`
  passed: `4 passed`.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q`
  passed: `17 passed`.
- OMEN deployment via `scripts/deploy-omen.sh` completed at `66e2850`.
- `npm --prefix web-ui/client run check` passed after fix.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_health_settings.py -q`
  passed: `37 passed`.
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts --project=desktop-chromium --workers=1`
  passed: `4 passed`.

## Important Files For Debugger

- `web-ui/client/src/routes/call/[threadId]/+page.svelte`
- `web-ui/client/src/lib/api/calls.ts`
- `web-ui/server/app/api/calls.py`
- `web-ui/server/app/domain/ai_backend_client.py`
- `ai-backend/app/api/webrtc.py`
- `ai-backend/app/call/session.py`
- `ai-backend/app/call/tracks.py`
- `web-ui/server/tests/test_calls.py`
- `ai-backend/tests/test_webrtc_signaling.py`
- `.planning/phases/03-first-working-call-mvp/OMEN-PC-LIVE-EVIDENCE.md`

## Operational Notes

- Use `ssh rayme-pmpg`, not raw hostnames.
- Deploy with `scripts/deploy-omen.sh`; do not hand-deploy.
- Push commits before deploy so OMEN can fast-forward pull.
- OMEN checkout: `C:\Users\pmpg\rayme\RayMe`.
- OMEN logs:
  - `C:\Users\pmpg\rayme\logs\web-ui.hidden.out.log`
  - `C:\Users\pmpg\rayme\logs\web-ui.hidden.err.log`
  - `C:\Users\pmpg\rayme\logs\ai-backend.hidden.out.log`
  - `C:\Users\pmpg\rayme\logs\ai-backend.hidden.err.log`
- Live URLs:
  - Web: `https://192.168.1.199:8443`
  - AI health: `https://192.168.1.199:9443/health`
  - AI WebRTC status: `https://192.168.1.199:9443/webrtc/status`

## Recommended Next Debug Steps

1. Add structured, safe logging around `web-ui/server/app/api/calls.py`
   `create_call_offer`:
   - call id
   - stored session id
   - offer SDP length
   - whether SDP includes `m=audio`, `a=ice-ufrag`, `a=fingerprint`
   - elapsed time for `backend.create_webrtc_offer`
   - sanitized exception class/code on failure
2. Add structured logging around `ai-backend/app/api/webrtc.py`
   `create_webrtc_offer_answer`:
   - session id
   - offer SDP length/features
   - whether aiortc peer connection was created
   - exception class from `_negotiate_answer`
3. Reproduce from Android and inspect hidden logs.
4. If aiortc rejects Android SDP, build a fixture from a sanitized Android SDP
   sample and add an `ai-backend/tests/test_webrtc_signaling.py` regression.
5. Only after offer negotiation succeeds, debug media track ingestion, VAD/STT,
   LLM turn generation, and F5 playback.

## Resolution

- root_cause: Web UI call startup entered `Listening` before WebRTC negotiation
  and then swallowed `/offer` failures, while `sendCallOffer` used generic
  `apiFetch` errors that discarded sanitized backend detail.
- fix: Propagate offer failures as typed `CallApiError`, fail startup through a
  blocking panel, stop local media, request setup cleanup with
  `reason="setup_failed"`, and preserve sanitized backend WebRTC failure
  code/message through the web server AI client.

## FOLLOW-UP ROOT CAUSE FOUND (2026-04-26)

### Captured Boundary Trace (commit 6f96c4e, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `6f96c4e` |
| Android client | `192.168.1.253` |
| `/api/calls/start` | 201 Created |
| `/api/calls/{id}/offer` | 200 OK |
| `offer.received` -> `offer.answered` | OK |
| `iceconnectionstatechange: checking -> completed` | OK |
| `connectionstatechange: connecting -> connected` | OK |
| `peer.on_datachannel rayme-events readyState=open` | OK |
| `track.recv.first_frame sample_rate=48000 samples=960` | OK |
| `turn.started frame_count=1 sample_rate=16000 pcm_bytes=1280` | OK |
| `track.recv.progress` 50,100,150,200,250,300,350 | OK |
| `vad.speech_start` / `vad.silence` / `vad.end_of_turn` | NEVER |
| `stt.begin` / `stt.result` / LLM / TTS | NEVER |

### Root Cause

The live call path was still collapsing some PyAV audio buffers before VAD could inspect them. `normalize_inbound_audio_frame()` scaled integer PCM correctly, but it still averaged every 2D ndarray on axis 0. That is correct for channel-first audio, but wrong for channel-last audio. When `to_ndarray()` exposed samples x channels, the normalizer compressed the waveform into the wrong shape, and Silero never saw usable speech, so the session never reached `vad.speech_start`.

### Fix

Make PyAV normalization shape-aware in `ai-backend/app/call/tracks.py` so 2D arrays are mixed on the channel axis whether the layout is channel-first or channel-last.

Regression tests:

- `ai-backend/tests/test_call_session.py::test_inbound_audio_normalizer_scales_integer_channels_before_mixing`
- `ai-backend/tests/test_call_session.py::test_inbound_audio_normalizer_handles_channel_last_integer_audio`

Verification:
`uv run --project ai-backend pytest ai-backend/tests -q` -> **67 passed**.

next_action: deploy and ask user to reproduce; expected trace is still `vad.speech_start -> vad.silence -> vad.end_of_turn -> stt.begin -> stt.result`.

## FOLLOW-UP ROOT CAUSE FOUND (2026-04-26)

### Captured Boundary Trace (commit 785414e, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `785414e` |
| Android client | `192.168.1.253` |
| `/api/calls/start` | 201 Created |
| `/api/calls/{id}/offer` | 200 OK |
| `offer.received` -> `offer.answered` | OK |
| `iceconnectionstatechange: checking -> completed` | OK |
| `connectionstatechange: connecting -> connected` | OK |
| `peer.on_datachannel rayme-events readyState=open` | OK |
| `track.recv.first_frame sample_rate=48000 samples=960` | OK |
| `turn.started frame_count=1 sample_rate=16000 pcm_bytes=1280` | WRONG |
| `track.recv.progress` 50,100,150,200,250,300,350 | OK |
| `vad.speech_start` / `vad.silence` / `vad.end_of_turn` | NEVER |
| `stt.begin` / `stt.result` / LLM / TTS | NEVER |

### Root Cause

`normalize_inbound_audio_frame()` was still mis-handling packed stereo PyAV audio. The live frame shape is packed interleaved stereo: `format=s16`, `layout=stereo`, `to_ndarray().shape == (1, 1920)`. The previous normalization logic treated any 2D array as channel-first or channel-last and averaged along the wrong axis, which doubled the effective sample count to 640 resampled samples and produced `pcm_bytes=1280` instead of the expected 640 bytes for a 20 ms 48 kHz frame. That left VAD with the wrong waveform length and it never reported speech.

### Fix

Use PyAV frame metadata to distinguish planar from packed audio, deinterleave packed multi-channel buffers before mixing, and keep the old shape heuristic only as a fallback for mocked test frames.

Regression tests:

- `ai-backend/tests/test_call_session.py::test_inbound_audio_normalizer_handles_packed_stereo_audio`
- `ai-backend/tests/test_call_session.py::test_inbound_audio_normalizer_scales_integer_channels_before_mixing`
- `ai-backend/tests/test_call_session.py::test_inbound_audio_normalizer_handles_channel_last_integer_audio`

Verification:
`uv run --project ai-backend pytest ai-backend/tests -q` -> **68 passed**.

next_action: deploy and ask user to reproduce; expected trace remains `vad.speech_start -> vad.silence -> vad.end_of_turn -> stt.begin -> stt.result`.

## FOLLOW-UP ROOT CAUSE FOUND (2026-04-26)

### Captured Boundary Trace (commit f144354, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `f144354` |
| `turn.started frame_count=1 sample_rate=16000 pcm_bytes=640` | OK |
| `vad.speech_start` | OK |
| `vad.silence` | OK |
| `vad.end_of_turn` | OK |
| `stt.begin frames=372 pcm_bytes=238080` | OK |
| `stt.result transcript_len=0 language=en` | FAIL |
| `event.sent type=user_final readyState=open` | WRONG |
| LLM / TTS | NEVER |

### Root Cause

The call path was applying VAD twice. RayMe call VAD had already finalized the turn, but `WhisperSttAdapter.transcribe()` still invoked faster-whisper with `vad_filter=True`. On the live Android call this second VAD pass returned no usable transcript, which produced `status=needs_manual_transcript` and an empty transcript. `CallSession.finalize_user_turn()` then incorrectly emitted an empty `user_final` event, so the client ignored it and the call appeared to hang.

### Fix

- Disable faster-whisper internal VAD for pre-segmented call turns by passing `apply_vad_filter=False` from `CallSession._transcribe_turn()`.
- Treat non-accepted or empty STT results as `call_stt_failed` instead of emitting an empty `user_final`.

Regression tests:

- `ai-backend/tests/test_stt.py::test_stt_adapter_can_disable_internal_whisper_vad_for_presegmented_audio`
- `ai-backend/tests/test_call_session.py::test_inbound_audio_emits_failed_event_when_stt_needs_manual_transcript`

Verification:
`uv run --project ai-backend pytest ai-backend/tests -q` -> **70 passed**.

next_action: deploy and ask user to reproduce; expected next boundary is either non-empty `stt.result` followed by LLM/TTS, or a new failure after `user_final`.
- verification: `npm --prefix web-ui/client run check`; `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_health_settings.py -q`; `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts --project=desktop-chromium --workers=1`.
- files_changed: `web-ui/client/src/lib/api/calls.ts`, `web-ui/client/src/routes/call/[threadId]/+page.svelte`, `web-ui/client/tests/e2e/call-start.spec.ts`, `web-ui/server/app/domain/ai_backend_client.py`, `web-ui/server/tests/test_calls.py`, `web-ui/server/tests/test_health_settings.py`, `.planning/debug/android-call-offer-502.md`.

---

## 2026-04-26T01:10:00Z — New Symptom: stuck in Listening after offer 200 OK

### New User-Visible Symptom

User reports on Android Chrome at https://192.168.1.199:8443:
- /api/calls/start -> 201 Created
- /api/calls/{id}/offer -> 200 OK
- AI backend /webrtc/offer -> 200 OK
- Call UI stays in `Listening` indefinitely
- No transcript appears, no AI response, no audible TTS
- User must manually hang up
- No alternation pattern reported by user: "alternating back and forth and back and forth between it failing quickly or not failing but not answering either"

### Operational Constraint Discovered (Blocker For Live Reproduction)

The SSH alias `rayme-pmpg` is NOT resolvable from the current debugging environment.
- `ssh rayme-pmpg 'echo ok'` -> `ssh: Could not resolve hostname rayme-pmpg: Name or service not known`
- `~/.ssh/config` does not exist for this user
- `scripts/bootstrap-rayme-ssh.sh` configures alias `rayme-ssh` (not `rayme-pmpg`)
- Even with `dangerouslyDisableSandbox=true` SSH cannot reach OMEN

This means:
- I cannot start background log tails on OMEN myself
- I cannot run `scripts/deploy-omen.sh` (it requires SSH)
- I cannot read OMEN log files directly

The user has SSH access (commits 1be53a7 and earlier were verified deployed via SSH, and OMEN /webrtc/status responds at https://192.168.1.199:9443/webrtc/status with status: ready, live_call_ready: true, media_transport_ready: true, active_sessions: 0).

The visibility-first plan must be done by the user, OR by an environment that has SSH. I will instrument the code so when it IS deployed and the user reproduces, the post-offer path is fully observable. I will hand the deploy + tail commands to the user as a checkpoint.

### Local vs Deployed State

- Local HEAD: `94150d4 docs: replace Android call handoff` (one commit ahead of origin)
- Origin HEAD: `1be53a7 fix: remove synthetic call facade fallbacks` (per `git log origin/main..HEAD`)
- OMEN deployed HEAD per handoff: `1be53a7`
- AI backend `/webrtc/status` reachable from local: ready, 0 active sessions

### Post-Offer Code Path Mapped (No Code Changes Yet)

Browser side (`web-ui/client/src/routes/call/[threadId]/+page.svelte`):
- `connectBrowserMedia` creates `RTCPeerConnection` (no STUN/TURN/iceServers config)
- Browser creates outbound data channel `eventsChannel = connection.createDataChannel('rayme-events')`
- Browser registers `connection.ondatachannel` handler that swaps in remote channel of same label
- Browser registers `connection.ontrack` handler that calls `attachRemoteAudio(stream)`
- Browser adds local mic tracks via `connection.addTrack(track, localMediaStream)`
- Browser createOffer -> setLocalDescription -> waitForIceGathering(1500ms cap) -> POST offer
- Browser setRemoteDescription on response.answer

Backend side (`ai-backend/app/api/webrtc.py`):
- `_create_peer_connection(offer)` constructs aiortc `RTCPeerConnection()` (no iceServers)
- `_create_data_channel(peer_connection)` -> calls `peer_connection.createDataChannel("rayme-events")` BACKEND ALSO CREATES A CHANNEL
- `_attach_outbound_audio_track(peer_connection)` -> adds `QueuedAudioOutputTrack` BEFORE setRemoteDescription
- `manager.create_session(...)` (data_channel passed in is the backend-created one)
- `_attach_peer_handlers(peer_connection, session)` registers:
  - `on_datachannel` -> overwrites `session.data_channel` with browser's channel when it arrives
  - `on_track` -> spawns `_receive_audio_track` task that calls `track.recv()` in a loop
  - `on_connectionstatechange`
- `_negotiate_answer(peer_connection, payload.offer)` setRemoteDescription, createAnswer, setLocalDescription
- Returns `{session_id, answer, event_channel, data_channel}`

Inbound audio loop (`_receive_audio_track`):
- `await track.recv()` -> `session.handle_inbound_audio_frame(frame)`
- `handle_inbound_audio_frame` runs VAD (`_accept_vad_frame`), only finalizes turn when `end_of_turn=True`
- `finalize_user_turn` runs STT, emits `user_final` event via `emit_event`

`emit_event` send path:
- if data channel exists and `readyState == "open"`, channel.send(json) (NOT awaited)

### Observations Worth Treating As Hypothesis Candidates (NOT Confirmed)

H1. NO ICE SERVERS configured on either side. Both `new RTCPeerConnection()` (browser) and `RTCPeerConnection()` (aiortc backend) use no STUN/TURN. On Android Chrome over local LAN with both peers on the same /24 subnet (192.168.1.0/24), host candidates should still discover each other and form an ICE pair, so this is plausibly OK. But on Android, host candidates from cellular interfaces or VPNs can interfere. No live ICE state evidence yet.

H2. DUPLICATE DATA CHANNEL CREATION. Both browser AND backend create a data channel named `rayme-events`. WebRTC convention is that exactly ONE side creates the channel and the other receives it via `ondatachannel`. With both sides creating, the browser holds its OWN local outgoing channel as `eventsChannel` and never reattaches via its `ondatachannel` (because backend's channel won't necessarily appear as a remote channel that triggers the browser's handler — depends on negotiation order). The backend will eventually swap `session.data_channel` to the browser-created channel through its `on_datachannel`. Net effect: backend sends events on the browser-created channel; browser listens on its OWN created channel; these are the same channel object on the wire (browser-initiated). This MIGHT actually work, but is an unnecessary risk and complicates diagnosis. Worth eliminating.

H3. NO INBOUND TRACK EVER ARRIVES on backend. If aiortc's ICE/DTLS does not complete with Android Chrome, `on_track` never fires, `_receive_audio_track` never runs, no VAD, no STT, no `user_final`, and the browser sees no data channel events. Browser would stay in `Listening` forever. This is the most parsimonious explanation given the symptom.

H4. INBOUND TRACK ARRIVES BUT VAD NEVER ENDS THE TURN. aiortc decodes Opus frames at 48kHz; `normalize_inbound_audio_frame` resamples to 16kHz. If the VAD threshold is too high or end-of-turn silence threshold is too long, the user's speech might never finalize. Browser stays in `Listening`. This is also possible.

H5. STT RUNS BUT EMITS EMPTY TRANSCRIPT, then `user_final` event with `text=""` is sent — `appendUserFinal('')` would still trigger `submitUserTurn`, which would `submitCallTurn` with `text=""` (which would 422 due to `min_length=1`). UI would not visibly progress. Less likely but not ruled out.

H6. EVENT IS EMITTED BUT BROWSER NEVER SEES IT. Backend's `emit_event` checks `getattr(channel, "readyState", "open") == "open"`. If the channel is the backend-created one and browser-created channel never matched, the channel's readyState may not be "open" from the browser's viewpoint. Browser receives nothing. Stuck in `Listening`.

H7. `pc.iceConnectionState` reaches `failed` or `disconnected` silently. There is no listener attached on the browser, so the user sees no failure. The session quietly does nothing. This is consistent with the symptom.

### Why Visibility Comes First

The symptom is identical for at least four of these hypotheses (H3, H4, H6, H7 all produce "stuck in Listening, no progress"). Choosing the wrong fix without evidence will burn another iteration and the user has explicitly said they're sick of the back-and-forth. The first deliverable MUST be visibility, then ONE reproduction, then ONE fix.

### Next Concrete Action (Pending User-Side SSH)

I will write structured-logging instrumentation in a single commit covering BOTH ends:

Browser (`+page.svelte`): subscribe to all four state-change events, data channel open/message/close/error, mic track end, audio play() rejection. Forward all events to a small in-memory ring buffer AND `console.log('[rayme-call] ...')` so they appear in adb chrome remote inspector AND get POSTed to a new `/api/calls/_debug/event` endpoint that uvicorn will print to stdout. This makes the browser-side state visible WITHOUT requiring the user to attach a desktop debugger to Android.

Backend (`webrtc.py`, `session.py`): structured logger calls at every boundary (peer connection state, track received, periodic frame count, VAD decision summary, STT call, transcript length, event emit, TTS enqueue). Use existing logger (do not add prints).

Then ONE deploy, ONE Android reproduction, READ logs, FORM the real hypothesis, FIX exactly that.

### Checkpoint Reason

Cannot deploy or tail OMEN logs from this environment. Need user to (a) run deploy, (b) start log tails, (c) reproduce on Android, (d) paste the result. Returning checkpoint to orchestrator with exact instructions before writing any instrumentation code, so the user can decide whether to continue with this approach or hand back SSH access.

---

## 2026-04-26T(now)Z — SSH Restored, Instrumentation Round

### Operational Update

SSH alias `rayme-pmpg` is now resolvable from this environment. Verified:
`ssh rayme-pmpg 'echo ok-pmpg && hostname'` returns `ok-pmpg / OMEN-PC`. OMEN
deployed HEAD verified `1be53a7`. Path A check (orchestrator-run): tail of
`ai-backend.hidden.out.log` shows only uvicorn access lines on the post-offer
path — `POST /webrtc/offer 200 OK` followed by `POST /webrtc/sessions/.../end
200 OK`. No peer-connection-state, no on_track, no inbound frame counts, no VAD,
no STT, no event publish. **Confirmed: post-offer observability is missing.
That IS the first bug to address — visibility, not a speculative fix.**

### Instrumentation Plan (Single Atomic Commit, Behavior-Neutral)

Add structured logger calls (no `print`) at every post-offer boundary on both
ends. Mirror browser-side state changes to OMEN via a new diagnostic POST
endpoint `POST /api/calls/{call_id}/_debug/event` so Android Chrome (no remote
devtools attached) becomes observable in OMEN logs.

Backend (`ai-backend/app/api/webrtc.py`, `ai-backend/app/call/session.py`):
- `webrtc.py::create_webrtc_offer_answer` — log session_id, sdp length, has
  m=audio / a=ice-ufrag / a=fingerprint, elapsed for negotiate, answer sdp
  length on success.
- `_attach_peer_handlers` — log `connectionstatechange`, register
  `iceconnectionstatechange` and `signalingstatechange` listeners and log them.
- `on_track` — log kind/id when fired.
- `_receive_audio_track` — log first frame received; log periodic frame count
  every 50 frames; log on track recv exception with class name.
- `session.py::handle_inbound_audio_frame` — log every Nth frame normalized
  (sample rate, byte length).
- `_accept_vad_frame` — log speech_start once per turn, end_of_turn once per
  turn, with energy/threshold and silence_ms.
- `finalize_user_turn` — log STT begin (frame count, total ms), STT result
  (transcript length, language), event emit.
- `emit_event` — log channel state, event type, send success/failure.
- `speak_text` / `_queue_outbound_audio` — log TTS enqueue (wav byte count).

Browser (`web-ui/client/src/routes/call/[threadId]/+page.svelte`):
- After `new RTCPeerConnection()` register listeners for
  `iceconnectionstatechange`, `connectionstatechange`,
  `signalingstatechange`, `icegatheringstatechange`. Each fires:
  console.log AND POST to `/api/calls/{call_id}/_debug/event` with
  `{event, detail}`.
- `eventsChannel`/`event.channel` open/close/error/message: log all four.
- `connection.ontrack`: log kind/id of remote track and stream count.
- `attachRemoteAudio`: log play() success or rejection class name.
- Mic local track readyState at start.

Web facade (`web-ui/server/app/api/calls.py`): add a new minimal route
`POST /api/calls/{call_id}/_debug/event` that calls `logger.info("[browser-call]
%s call=%s detail=%s", event, call_id, json.dumps(detail))`. No DB, no
forwarding. Only purpose: surface Android browser state in OMEN web log file.

### Sanitization Constraints

- Never log full SDP body. Only length and presence of well-known a-lines.
- Never log audio bytes. Only frame counts and rates.
- Never log API keys, voice references, or transcript text content (length
  only). Transcript text content is acceptable to log because the user already
  authorized the call session to receive it; but to be safe-by-default, log
  only length until proven we need text.
- Guard at INFO level so it can be turned off later via uvicorn log config.

### Why Visibility, Not A Fix, This Round

Same hypothesis-uncertainty as previous round (H3/H4/H6/H7 all produce identical
"stuck in Listening" symptom). Speculative fixes have already burned several
deploys. Deliverable for this round = visibility shipped to OMEN; user
reproduces ONCE on Android; logs reveal which boundary fails first; next round
applies a targeted fix at exactly that boundary.

### Deploy Confirmation (2026-04-26)

- Local commit pushed: `6751631 chore(03-debug): instrument post-offer call lifecycle`.
- `scripts/deploy-omen.sh` completed: `OMEN deploy complete: 675163124bc81cf509c304225a226c531873caae`.
- OMEN `git rev-parse --short HEAD` = `6751631` (matches local).
- `https://192.168.1.199:9443/webrtc/status` returns
  `{"status":"ready","phase":"03","live_call_ready":true,"media_transport_ready":true,"active_sessions":0}`.
- Three background tails attached to OMEN log files:
  - `ai-backend.hidden.out.log` (background ID `bedrpdfen`)
  - `ai-backend.hidden.err.log` (background ID `bn14oguk1`)
  - `web-ui.hidden.out.log` (background ID `bkfwvq4c5`)
- Deploy result note: web/ai both report `degraded` in deploy health (existing
  pre-instrumentation state — STT/TTS warmup likely still running). `webrtc`
  facade reports ready, which is what matters for the call path. Will re-check
  during reproduction.

next_action: orchestrator presents Android reproduction steps to user; on user
"go", read fresh background output for first-failing boundary.

## ROOT CAUSE FOUND (2026-04-26)

### Captured Boundary Trace (commit 70a175d, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| `offer.received` → `offer.answered` (5030 ms) | OK |
| `iceconnectionstatechange: checking → completed` | OK |
| `connectionstatechange: connecting → connected` | OK |
| `peer.on_datachannel rayme-events readyState=open` | OK |
| `track.recv.first_frame sample_rate=48000 samples=960` | OK |
| `turn.started frame_count=1 sample_rate=16000 pcm_bytes=1280` | OK |
| `vad.speech_start turn_frames=1` | **fires on frame 1** |
| `track.recv.progress` 50,100,150,200,250,300,350 | OK (audio flows ~7 s) |
| `vad.silence` | **NEVER** |
| `vad.end_of_turn` | **NEVER** |
| `stt.begin` / `stt.result` / LLM / TTS | NEVER reached |
| User hangs up → `MediaStreamError` → cleanup | OK |

### Root Cause

`CallSession._accept_vad_frame` (`ai-backend/app/call/session.py:463`) has a
real Silero VAD adapter loaded but only used the boolean "any speech ever?"
result. `_silence_ms` was driven entirely by an RMS-energy comparator with
threshold = `vad_threshold * 1000` = **500 RMS** for int16 audio. With browser
audio (AGC always pumping the signal), every frame's RMS exceeds 500, so the
energy branch keeps resetting `_silence_ms = 0`. End-of-turn condition
(`_silence_ms >= vad_end_silence_ms`) was therefore unreachable.

Effect: speech_start triggered on frame 1, the turn was held open forever, no
STT/LLM/TTS path ever executed, UI stayed in "Listening".

### Fix

When a Silero-style adapter exposing `speech_timestamps` is present, derive
`_silence_ms` from `len(buffered_samples) - last_timestamp.end` (in ms via
adapter sampling rate) and skip the energy heuristic. Energy fallback retained
only for the no-adapter case (mostly tests).

Regression test: `test_silero_silence_gap_finalizes_turn_even_with_loud_ambient_noise`
in `ai-backend/tests/test_call_session.py` feeds loud constant-amplitude PCM
through a Silero-mimic adapter; turn must finalize once the silence gap exceeds
`vad_end_silence_ms`.

`uv run --project ai-backend pytest ai-backend/tests -q` → **65 passed**.

next_action: deploy and ask user to reproduce; expect `vad.silence` then
`vad.end_of_turn` then `stt.begin/result` in the next trace.

## FOLLOW-UP ROOT CAUSE FOUND (2026-04-26)

### Captured Boundary Trace (commit 0bc6f9d, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `0bc6f9d` |
| Android client | `192.168.1.253` |
| `/api/calls/start` | 201 Created |
| `/api/calls/{id}/offer` | 200 OK |
| `offer.received` -> `offer.answered` | OK |
| `iceconnectionstatechange: checking -> completed` | OK |
| `connectionstatechange: connecting -> connected` | OK |
| `peer.on_datachannel rayme-events readyState=open` | OK |
| `track.recv.first_frame sample_rate=48000 samples=960` | OK |
| `turn.started frame_count=1 sample_rate=16000 pcm_bytes=1280` | OK |
| `track.recv.progress` 50,100,150,200,250,300,350 | OK |
| `vad.speech_start` / `vad.silence` / `vad.end_of_turn` | NEVER |
| `stt.begin` / `stt.result` / LLM / TTS | NEVER |

### Root Cause

The previous VAD silence fix was correct for the post-speech silence branch,
but the live Android trace now failed before speech was detected at all.

`normalize_inbound_audio_frame` averaged multi-dimensional PyAV integer audio
arrays before scaling int16 PCM into float audio. `numpy.mean()` changes the
dtype to float, so `_coerce_to_float32` no longer divided by the int16 max
value. The later clip-to-`[-1, 1]` step collapsed almost every non-zero sample
to full scale. Silero received a distorted clipped waveform rather than real
speech-shaped audio, so it produced no speech timestamps and the turn never
reached STT.

### Fix

Scale integer PCM to float before channel mixing in
`ai-backend/app/call/tracks.py`.

Regression test:
`ai-backend/tests/test_call_session.py::test_inbound_audio_normalizer_scales_integer_channels_before_mixing`
uses a PyAV-style int16 channel array and verifies the normalized PCM preserves
the original amplitudes instead of clipping to full scale.

Verification:
`uv run --project ai-backend pytest ai-backend/tests -q` -> **66 passed**.

### Deploy Confirmation

- OMEN deployed code HEAD: `6f96c4e`
- `scripts/deploy-omen.sh` completed with `OMEN deploy complete:
  6f96c4e37fe06d132548ba65d1edc50d003fbc9b`
- AI WebRTC status: `ready`, `live_call_ready: true`,
  `media_transport_ready: true`, `active_sessions: 0`
- Verification rerun before deploy:
  `uv run --project ai-backend pytest ai-backend/tests -q` -> **66 passed**

next_action: ask user to reproduce on Android Chrome; expected trace is
`vad.speech_start -> vad.silence -> vad.end_of_turn -> stt.begin -> stt.result`.

## FOLLOW-UP ROOT CAUSE FOUND (2026-04-26, later Android Chrome repro)

### Captured Boundary Trace (commit 445c19f)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `445c19f` |
| `/webrtc/offer` | 200 OK |
| `offer.received` -> `offer.answered` | OK |
| `iceconnectionstatechange: checking -> completed` | OK |
| `connectionstatechange: connecting -> connected` | OK |
| `track.recv.first_frame sample_rate=48000 samples=960` | OK |
| `turn.started frame_count=1 sample_rate=16000 pcm_bytes=640` | OK |
| `track.recv.progress` 50..400 | OK |
| `vad.speech_start` / `vad.silence` / `vad.end_of_turn` | NEVER |
| `stt.begin` / `stt.result` / LLM / TTS | NEVER |
| browser `datachannel.open` | OK |
| browser `datachannel.error` + `datachannel.close` | FAILED |

### Root Cause

The browser and backend were both creating `rayme-events` data channels. On
Android Chrome this produced two same-label channels in the session:

- browser-created `rayme-events`
- backend-created `rayme-events`

The browser then attached both, and both channels errored closed with
`OperationError`. That made call event delivery unreliable and introduced a
real signaling boundary failure separate from VAD.

This does not yet explain the lack of `vad.speech_start` in that repro, but it
is a concrete live-call bug and had to be removed before trusting any further
speech-path diagnosis.

### Fix

Stop creating `rayme-events` on the backend. The browser now owns channel
creation, and the backend only accepts the browser-opened channel via
`peer.on_datachannel`.

Files:

- `ai-backend/app/api/webrtc.py`
- `ai-backend/tests/test_webrtc_signaling.py`

Verification:

- `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q`
  -> **9 passed**
- `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q`
  -> **17 passed**

Deploy confirmation:

- OMEN deployed code HEAD: `8b6b9e6`
- `scripts/deploy-omen.sh` completed with:
  `OMEN deploy complete: 8b6b9e6e419b20124487122a20a507f084d016b0`

next_action: ask user to reproduce again on Android Chrome and confirm whether
the single-channel session reaches `vad.speech_start`; if not, add targeted
mic-energy instrumentation on the browser side and inspect normalized PCM on
the backend for the new session.
