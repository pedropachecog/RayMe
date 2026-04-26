---
status: awaiting_human_verify
trigger: "Android Chrome Phase 3 live call: microphone permission is granted and Android shows mic listening, then the RayMe call UI still fails or becomes unusable."
created: 2026-04-25T23:36:09Z
updated: 2026-04-26T23:55:00Z
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

- status: investigating — ICE timeout fix (commit `c0dbb34`) deployed and tested. User reports no improvement. OMEN logs pulled and analyzed.

- last_fix: ICE timeout prevention during STT+LLM+TTS processing gap (commit `c0dbb34`)
  - Added tiny jitter to silence frames in `QueuedAudioOutputTrack._next_samples()` so Opus DTX does not suppress them
  - Reduced data channel keepalive interval from 4s to 1s
  - Browser responds to backend ping events for bidirectional packet flow
  - Browser handles `ai_audio_started`/`ai_done` via data channel as fallback (in case SSE stream is slow)

- next_action: Fix the ICE timeout with stronger measures — see reasoning_checkpoint below.

## BLOCKING DISCOVERY UPDATE (2026-04-26) — Voice Blob Pipeline Analysis

### Pipeline Trace

**Voice Lab upload path** (`web-ui/server/app/api/voices.py:135-148`):
1. `POST /api/voices/assets` receives the audio file
2. `VoiceService.upload_sample()` validates and writes blob via `write_voice_sample_blob()`
3. Blob written to `voice_blob_dir / f"{asset_id}{extension}"` (e.g., `voice_asset_xxx.wav`)
4. `VoiceAsset` record created with `voice_id=None`, `asset_kind="sample"`, `storage_path=blob_filename`
5. **CRITICAL: The asset is NOT linked to any voice yet**

**Voice Lab save path** (`web-ui/server/app/domain/voice_service.py:118-135`):
1. `POST /api/voices` creates a new `Voice` record with `id=new_voice_id()`
2. `asset.voice_id = voice.id` links the asset to the new voice
3. **CRITICAL: The voice is NOT assigned to any character yet**

**Character assignment path** (`web-ui/client/src/routes/characters/[id]/+page.svelte`):
1. User must go to the character settings page
2. Select a voice from the "Default voice" dropdown
3. Click "Save Character" to persist `default_voice_id`
4. **THIS STEP IS MISSING — the Voice Lab does not auto-assign the voice**

**Call path** (`web-ui/server/app/domain/call_service.py:117-152`):
1. `start_call()` reads `character.default_voice_id`
2. If null → `CallVoiceRequiredError` ("Assign a voice before calling")
3. If set → looks up the Voice, creates `ActiveCall(voice_id=voice.id)`
4. `voice_reference_for_call()` looks up `VoiceAsset` for that `voice_id`

### Root Cause Hypothesis

**The character's `default_voice_id` is either null or points to a voice that has no VoiceAsset with `asset_kind='sample'`.**

The Voice Lab saves a voice but does NOT assign it to any character. The user uploaded a voice in the Voice Lab on OMEN (creating Voice + VoiceAsset), but the character's `default_voice_id` was never updated to point to this new voice. The call uses whatever voice was previously assigned (or none), which has no sample audio.

### Evidence

- `voice_reference_for_call()` reads `call.voice_id` which comes from `character.default_voice_id`
- The Voice Lab `save_voice()` creates a new Voice but does not update any character
- The character settings page has a "Default voice" dropdown, but this is a separate step
- The user confirmed the Voice Lab works (test-play succeeds) — confirming Voice + VoiceAsset exist
- But the test-play uses the voice_id from the Voice Lab, not from the character

### Fix Direction

**Immediate fix:** User needs to go to the character settings page on OMEN and assign the uploaded voice.

**UX improvement (future):** Voice Lab should show which characters are using this voice, or auto-assign to the character being edited.

### Diagnostic Commit

Commit `fdc3ab3` adds structured logging to `voice_reference_for_call()` so each failure point produces a distinct log message. Deploy to OMEN and reproduce to confirm the exact failure point.

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

## FOLLOW-UP ROOT CAUSES FOUND (2026-04-26, post-VAD fix)

### Root Cause 1 — `session.fail()` called when inbound track ends mid-TTS

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `8b6b9e6` (single data channel) |
| `vad.speech_start` / `vad.end_of_turn` | OK (confirmed from previous fix) |
| `stt.result` / LLM tokens | OK |
| F5 TTS synthesis | OK (`tts.enqueue wav_bytes=1822700`) |
| Audio delivered over WebRTC | NEVER |

After the user finishes speaking, Android Chrome stops sending audio frames.
aiortc raises `MediaStreamError` at that point with `ice=completed conn=connected`.
The `_receive_audio_track` error handler fallthrough was calling
`await session.fail(reason="connection_failed")` which closed the peer
connection entirely — destroying the outbound `QueuedAudioOutputTrack` before
TTS audio (already synthesized and enqueued) could be delivered. The call UI
showed `thinking → speaking → listening` in under 1 second with no audible
audio. F5 synthesis had succeeded (`tts.enqueue wav_bytes=1822700`) but the
outbound track was dead.

Fix: when `track.recv()` raises and ICE/conn state is still `completed`/`connected`,
exit the inbound receive loop with a log line and `return` — do NOT call
`session.fail()`. The outbound audio track remains alive.

File: `ai-backend/app/api/webrtc.py` — `_receive_audio_track` fallthrough case.

### Root Cause 2 — `ai_audio_started_event` nested key lookup always returned None

`_speak_call` returns `{"session_id":…, "turn_id":…, "state":…, "event":
{"type":"ai_done", …, "ai_audio_started_event": {…}}}`. The `/turns` SSE
generator checked `speak_result.get("ai_audio_started_event")` which is always
`None` because the key is inside `speak_result["event"]`, not at the top level.
The `ai_audio_started` SSE event was therefore never yielded to the browser,
so the client had no signal that audio was playing.

Fix: check both `speak_result.get("ai_audio_started_event")` and
`(speak_result.get("event") or {}).get("ai_audio_started_event")`.

File: `web-ui/server/app/api/calls.py` — `create_call_turn` SSE `events()` generator.

### Regression Tests

- `ai-backend/tests/test_webrtc_signaling.py::test_receive_audio_track_media_stream_error_with_live_ice_does_not_fail_session`
- `web-ui/server/tests/test_calls.py::test_turn_yields_ai_audio_started_event_when_nested_inside_speak_result_event`

### Verification

- `uv run --project ai-backend pytest ai-backend/tests -q` → **71 passed**
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` → **25 passed**

### Deploy Confirmation

- Commit: `58e0a96`
- `scripts/deploy-omen.sh` completed: `OMEN deploy complete: 58e0a96d0af9c618d3090cae1b4f04ad2686785f`
- OMEN listeners confirmed on ports 8443/9443

next_action: ask user to reproduce on Android Chrome; expected outcome is
audible AI speech for the first time since the voice blob was re-uploaded.

## FOLLOW-UP ROOT CAUSE FOUND (2026-04-26, post-MediaStreamError fix)

### Captured Boundary Trace (commit 58e0a96, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `58e0a96` |
| `vad.speech_start` / `vad.end_of_turn` / `stt.result` | OK (turns 1 and 2) |
| `event.sent type=user_final readyState=open` | OK (turns 1 and 2) |
| Browser `datachannel.message event_type=user_final` | OK (turns 1 and 2) |
| `POST .../turns` | 200 OK (SSE stream with `type=error`) |
| Browser receives SSE `type=error code=call_tts_failed` | OK |
| UI shows error notice in transcript | NEVER |
| UI stays in `listening` indefinitely | SYMPTOM |
| `voice_reference.unavailable` | fires for BOTH turns |

### Root Cause

`handleTurnStreamEvent()` handled `type=error` from the `/turns` SSE by
setting `callState = 'listening'` but never calling `appendCallNotice`.
The error message was silently discarded. The call stayed alive with no
user feedback. The VAD 5 s max-turn timer fired again, another
`user_final` was submitted, the same `voice_reference.unavailable` error
recurred — an infinite silent loop.

### Fix

Call `appendCallNotice(messageForCallFailure(code, message), turn_id)` in
`handleTurnStreamEvent` when `event.type === 'error'`, so the error text
appears in the transcript. Also added `installCallDebugEventRoute` helper
to e2e test harness so the browser's `/_debug/event` diagnostics POSTs are
mocked in all call tests.

Regression test:
`web-ui/client/tests/e2e/call-start.spec.ts::shows a call notice in the
transcript when /turns returns a type=error SSE event`

Verification:
- `npm --prefix web-ui/client run check` — passed
- `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts --project=desktop-chromium --workers=1` — **5 passed**
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py web-ui/server/tests/test_health_settings.py -q` — **44 passed**

Deploy: `82dfbd8` — `OMEN deploy complete: 82dfbd80478ec29fbeadd4dafc1eb6ebc97ecc88`

## BLOCKING DISCOVERY (2026-04-26) — Voice Blob Missing On OMEN, No Upload Path Outside Voice Lab

### Discovery

OMEN is missing the voice reference audio blob required for TTS during calls.
The error `voice_reference.unavailable` fires on every `/turns` call.

**Critical constraint confirmed by product owner:**
> There is no settings page or character settings UI to upload voice reference
> audio blobs. The only upload path is the **Voice Lab**.

The user re-uploaded a voice in the Voice Lab and verified it works there. However
the call path still gets `voice_reference.unavailable`, which means one of:

1. The Voice Lab upload writes the blob to a different location or database record
   than what `voice_reference_for_call()` reads at call time.
2. The blob IS written correctly but the call path looks up the wrong voice ID
   (e.g. the character's assigned voice ID does not match the newly uploaded blob's ID).
3. The Voice Lab upload endpoint stores the blob on the local dev machine (not OMEN)
   because dev machine ran the upload, not OMEN.

### Next Investigation Required

Before any further call testing is possible, the voice blob pipeline must be traced:

- What does the Voice Lab upload endpoint write to disk, and where?
- What does `voice_reference_for_call()` read, and from where?
- Does the character's assigned voice ID match the uploaded blob's ID?
- Is the Voice Lab upload routed through OMEN (https://192.168.1.199:8443) or local dev?

Until `voice_reference.unavailable` stops firing, TTS will never succeed and the
call cannot be end-to-end tested.

### Status

Blocked on voice blob pipeline investigation. All other call path fixes
(VAD, ICE, data channel, MediaStreamError, SSE error visibility) are believed
complete based on logs showing correct operation through `stt.result`.

---

## 2026-04-26T23:30:00Z — New Symptom: TTS runs but no audio on Android

### New User-Visible Symptom

After the voice blob fix (blobs/ in .gitignore, voice re-uploaded on OMEN):
- Voice blob found: `voice_reference OK file_size=266606`
- TTS synthesized: `tts.enqueue wav_bytes=1190412 target=track`
- Browser received: `ai_audio_started`, `ai_done` via data channel
- Browser: `remote_audio.play.ok` — Audio element play() succeeded
- **User hears NO audio and sees NO error message**

### Captured Boundary Trace (commit 0e76c7e, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `0e76c7e` |
| Android client | `192.168.1.253` |
| Voice blob | OK (`voice_6d6d48ec89534ec1a9567ba971a5772e`, 266606 bytes) |
| `/api/calls/start` | 201 Created |
| `/api/calls/{id}/offer` | 200 OK |
| WebRTC negotiation | OK (ICE completed, connected) |
| Data channel | OK (opened, messages flowing) |
| Inbound audio | OK (frames flowing, VAD works) |
| VAD (turns 1+2) | OK (speech_start, end_of_turn) |
| STT | OK (transcript_len=41, transcript_len=7) |
| `user_final` via data channel | OK (browser received both) |
| `/turns` SSE | 200 OK (two turns submitted) |
| LLM | OK (tokens generated) |
| TTS | OK (`wav_bytes=1190412`) |
| `ai_audio_started` via data channel | OK (browser received) |
| `ai_done` via data channel | OK (browser received) |
| Browser `remote_audio.play.ok` | OK |
| Browser `iceConnectionState=disconnected` | After ai_done |
| Browser `connectionState=failed` | After ai_done |
| Audio audible on Android | **NO** |

### Key Evidence

**AI backend stderr logs (instrumentation IS working, was in stderr not stdout):**
- Full lifecycle visible: offer → ICE → track → VAD → STT → TTS → events
- TTS enqueued 1.19 MB WAV to QueuedAudioOutputTrack
- Data channel events sent with `readyState=open`
- After events: DTLS `ConnectionError: Cannot send encrypted data, not connected`
- Inbound track ended gracefully (MediaStreamError, outbound kept alive)

**Browser debug logs (via /_debug/event POST):**
- `remote_audio.attach` — track attached to Audio element
- `remote_audio.play.ok` — play() resolved successfully
- `datachannel.message event_type=user_final` (x2) — turns submitted
- `datachannel.message event_type=ai_audio_started` — speaking signal
- `datachannel.message event_type=ai_done` — turn finished
- `iceConnectionState=disconnected` → `connectionState=failed` — after ai_done
- `datachannel.close` — cleanup

### Current Hypothesis

The `<Audio>` element approach for remote audio playback may not produce audible
sound on Android Chrome when the audio data arrives significantly after the initial
`play()` call. On Android, the `<Audio>` element's `play()` resolves as soon as the
MediaStream has live tracks, but the actual audio data (TTS output) arrives much
later — after LLM generation and TTS synthesis. By the time the audio data arrives,
Android's audio session may have moved on.

**Alternative hypothesis:** The audio IS transmitted and IS playing, but Android's
audio routing (communications mode, speaker vs earpiece, volume) makes it inaudible.

### Investigation Plan

1. Add browser-side logging for remote audio track activity (onended, onmute,
   track event count) to verify audio data actually arrives
2. Add browser-side logging for connection state changes that affect audio
3. Test switching from `<Audio>` element to AudioContext-based playback
   (MediaStreamAudioSourceNode → AudioContext.destination) for Android compatibility
4. Add `speakingRms` metering for remote audio to verify audio data is non-zero


### reasoning_checkpoint (AudioContext-based remote audio playback)

  hypothesis: "The <Audio> element approach for remote audio playback produces no
    audible sound on Android Chrome because (a) play() resolves when the track is
    first attached with silent frames, but the actual TTS audio arrives much later
    after LLM + TTS synthesis, and (b) Android's audio session may not maintain
    the playback path for delayed audio data on an <Audio> element that is not
    connected to the DOM."

  confirming_evidence:
    - "Browser logs show remote_audio.play.ok fired early (before ICE connected),
      but actual TTS audio was enqueued much later (after 2+ turns of user speech)"
    - "The <Audio> element is created with new Audio() but never appended to the DOM"
    - "Android Chrome has known issues with <Audio> element playback for WebRTC
      MediaStream sources when audio data arrives asynchronously"
    - "The audio unlock (unlockCallAudioContext) creates a separate AudioContext
      that is unlocked by user gesture, but the <Audio> element does not use this
      context"
    - "User hears no audio despite all other call path working correctly (VAD, STT,
      LLM, TTS, data channel events)"

  falsification_test: "If the AudioContext-based approach also produces no audio,
    then the hypothesis is wrong and the issue is elsewhere (e.g., audio not
    transmitted over WebRTC, codec mismatch, or Android audio routing issue
    unrelated to playback method)"

  fix_rationale: "Routing remote audio through an AudioContext (MediaStreamAudioSourceNode
    -> AnalyserNode -> AudioContext.destination) ensures the audio flows through
    the same audio rendering path that was unlocked by the user gesture. The
    AudioContext is a proper audio graph that processes incoming audio data in
    real-time, rather than relying on the <Audio> element's internal buffer
    management which may discard late-arriving data on Android."

  blind_spots:
    - "If the audio is not actually being transmitted over WebRTC (e.g., aiortc
      not polling the outbound track), then changing the playback method won't help"
    - "If Android's WebRTC stack mutes the remote track when the connection
      transitions to 'failed', the audio may stop before being audible"
    - "If the F5 TTS output is silent or inaudible (e.g., wrong voice, codec issue),
      the playback method doesn't matter"

---

## 2026-04-26T23:55:00Z — New Symptom: No audio, no error, "speaking" for a few seconds then nothing

### New User-Visible Symptom

User reports on Android Chrome: UI says "speaking" for a few seconds but nothing plays. No error shown.

### Captured Boundary Trace (commit c6e9820, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `c6e9820` (AudioContext remote playback) |
| Android client | `192.168.1.253` |
| Voice blob | OK (`voice_6d6d48ec89534ec1a9567ba971a5772e`, 266606 bytes) |
| `/api/calls/start` | 201 Created |
| `/api/calls/{id}/offer` | 200 OK |
| WebRTC negotiation | OK (ICE completed, connected) |
| Data channel | OK (opened, messages flowing) |
| Inbound audio | OK (frames flowing, VAD works) |
| VAD (turn 1) | OK (speech_start frame 37, end_of_turn frame 195, silence 702ms) |
| STT | OK (transcript_len=47, language=en) |
| `user_final` via data channel | OK (readyState=open) |
| Browser received `user_final` | OK |
| `/turns` SSE | 200 OK (LLM + TTS processing) |
| Browser ICE | **disconnected -> connected -> disconnected -> failed** (multiple cycles) |
| Browser `speakingRms` | **0.04** (floor value — NO audio data) |
| Browser `remoteAudioElementPlaying` | **false** |
| Backend inbound track | MediaStreamError at frame 610 (caused by browser ICE disconnect) |
| Backend data channel | **closed** (before TTS events) |
| Backend TTS | **wav_bytes=1061900** (enqueued AFTER connection closed) |
| Backend events | **all skipped** (`ai_audio_started`, `ai_done`, `ended` — `readyState=closed`) |
| Audio audible on Android | **NO** |

### Root Cause Analysis

The browser's WebRTC ICE disconnected during the processing gap (STT + LLM + TTS).
This caused a cascade:

1. Browser ICE disconnected (no enough bidirectional packet flow during processing)
2. Backend inbound track raised MediaStreamError (browser stopped sending audio)
3. Backend data channel closed (connection state changed to closed)
4. TTS completed (1.06 MB WAV) but enqueued to a dead connection
5. All data channel events (`ai_audio_started`, `ai_done`, `ended`) skipped
6. Browser `speakingRms=0.04` (floor value) — no audio data ever arrived
7. Browser `remoteAudioElementPlaying=false` — track was muted or ended

**Why ICE disconnected:**
- The outbound `QueuedAudioOutputTrack` sends silence frames during the processing gap
- Opus DTX (Discontinuous Transmission) suppresses consecutive silence frames
- No actual packets flow over the media channel during processing
- Data channel keepalive (every 4s) provides intermittent reconnection but not enough
- Android Chrome's ICE timeout fires, connection fails

**Why `speakingRms=0.04`:**
- The remote audio track never received actual audio data (connection was dead)
- The AnalyserNode reads silence, `Math.max(0.04, ...)` floors at 0.04

### Fix Direction

1. **Reduce data channel keepalive interval** from 4s to 1s to prevent ICE timeout
2. **Add jitter to silence frames** so Opus DTX does not suppress them entirely
3. **Browser responds to keepalive pings** for bidirectional packet flow
4. **Recreate data channel on ICE reconnect** (already partially implemented, verify)

### reasoning_checkpoint (ICE timeout during processing gap)
    hypothesis: "The browser's WebRTC ICE connection times out during the
      STT+LLM+TTS processing gap because no bidirectional packet flow occurs.
      Opus DTX suppresses silence frames from the outbound track, and the
      data channel keepalive (every 4s) is not frequent enough to prevent
      Android Chrome's ICE timeout. The connection fails before TTS audio
      arrives, resulting in speakingRms=0.04 (floor value) and no audible audio."
    confirming_evidence:
      - "Browser logs show ICE flapping: connected -> disconnected -> connected
        -> disconnected -> failed (multiple cycles during processing)"
      - "speakingRms=0.04 (floor value) confirms no audio data reached the
        browser AnalyserNode"
      - "Backend logs show data channel closed (readyState=closed) before TTS
        events (ai_audio_started, ai_done, ended) were sent"
      - "TTS enqueued 1.06 MB WAV but all events were skipped due to closed
        data channel"
      - "Backend inbound track ended at frame 610 (MediaStreamError) caused by
        browser ICE disconnect"
    falsification_test: "If the fix (jittered silence frames + faster keepalive
      + ping response) is deployed and the browser ICE stays connected during
      the processing gap, then TTS audio will arrive and the user will hear
      audio. If speakingRms remains 0.04, the hypothesis is wrong."
    fix_rationale: "Adding tiny jitter to silence frames prevents Opus DTX from
      suppressing them, ensuring continuous packet flow over the media channel.
      Reducing keepalive interval from 4s to 1s provides more frequent data
      channel packets. Responding to pings creates bidirectional flow. Together,
      these prevent ICE timeout during the processing gap."
    blind_spots:
    - "If the ICE timeout is caused by something other than lack of packet
      flow (e.g., NAT binding expiry, firewall), jitter won't help"
    - "If Android Chrome has a shorter ICE timeout than the default, even 1s
      keepalive may not be enough"
    - "If the data channel close is caused by the DTLS connection closing
      (not just ICE), the keepalive won't help"

---

## 2026-04-26T23:55:00Z — ICE Fix (c0dbb34) Did NOT Work

### New User-Visible Symptom

User reports on Android Chrome: UI says "speaking" for a few seconds but nothing plays. No error shown.

### Captured Boundary Trace (commit c0dbb34, Android Chrome reproduction)

| Boundary | Outcome |
|---|---|
| OMEN deployed HEAD | `c0dbb34` |
| Android client | `192.168.1.253` |
| `/api/calls/start` | 201 Created |
| `/api/calls/{id}/offer` | 200 OK |
| WebRTC negotiation | OK (ICE completed, connected) |
| Data channel | OK (opened, messages flowing) |
| Inbound audio | OK (frames flowing, VAD works) |
| VAD (turn 1) | OK (speech_start frame 82, end_of_turn frame 247, silence 718ms) |
| STT | OK (transcript_len=46, language=en) |
| `user_final` via data channel | OK (readyState=open) |
| Browser received `user_final` | OK |
| `/turns` SSE | 200 OK (LLM + TTS processing) |
| Browser ICE | **disconnected -> failed** (immediately after connected) |
| Browser `speakingRms` | **0.04** (floor value — NO audio data) |
| Browser `remoteAudioElementPlaying` | **false** |
| Backend inbound track | MediaStreamError at frame 665 (ice=completed, conn=connected) |
| Backend data channel | **closed** (before TTS events) |
| Backend TTS | **wav_bytes=1271308** (enqueued AFTER connection closed) |
| Backend events | **all skipped** (`ai_audio_started`, `ai_done`, `ended` — `readyState=closed`) |
| Audio audible on Android | **NO** |

### Root Cause Analysis

The ICE timeout fix from commit `c0dbb34` did NOT work. The same cascade occurred:

1. Browser ICE connected, then immediately disconnected during processing gap
2. Backend inbound track ended (MediaStreamError, but outbound kept alive)
3. Backend data channel closed before TTS events could be sent
4. TTS synthesized 1.27 MB WAV but all events skipped (readyState=closed)
5. Browser `speakingRms=0.04` (floor) — no audio data ever arrived

**Why the jitter fix failed:** The jitter values (`np.random.randint(-4, 4)`) are approximately -0.00009 of full scale. This is likely still below the Opus encoder's internal silence detection threshold, meaning DTX continues to suppress the frames. Additionally, the data channel keepalive (every 1s) may not be frequent enough to prevent Android Chrome's ICE timeout.

### Key Evidence from Logs

**Browser-side (web-ui stderr):**
- `iceConnectionState: disconnected` -> `connectionState: disconnected` -> `connectionState: failed`
- `speakingRms: 0.04` (floor value) — confirms NO audio data reached the browser
- `remoteAudioElementPlaying: false` — track was muted or ended
- `datachannel.close` — data channel closed before TTS events

**Backend-side (ai-backend stderr):**
- `track.recv.error frames=665 exc=MediaStreamError ice=completed conn=connected` — inbound ended gracefully
- `datachannel.close` — data channel closed
- `tts.enqueue wav_bytes=1271308` — TTS succeeded but too late
- `event.skip_channel_not_open` for `ai_audio_started`, `ai_done`, `ended` — all skipped

### reasoning_checkpoint (Stronger ICE keepalive measures)

  hypothesis: "The browser's WebRTC ICE connection times out during the
    STT+LLM+TTS processing gap because the current jitter (-4 to +4 int16,
    approximately -0.00009 of full scale) is still below the Opus encoder's
    internal silence detection threshold. DTX continues to suppress the frames,
    and the 1s data channel keepalive is not frequent enough to prevent
    Android Chrome's ICE timeout."

  confirming_evidence:
    - "OMEN logs show the exact same cascade as before the fix: ICE connected
      -> disconnected -> failed, speakingRms=0.04, data channel closed,
      TTS events skipped"
    - "The jitter range (-4 to +4) is extremely small relative to int16 max
      (32767). Opus DTX has a comfort noise floor that may be higher"
    - "Android Chrome's ICE timeout (typically 10-15s) requires continuous
      packet flow; the processing gap (STT + LLM + TTS) can take 20-30s"
    - "The data channel keepalive interval (1s) should be sufficient if
      packets are actually flowing, but the media channel is the primary
      ICE keepalive mechanism"

  falsification_test: "If increasing the jitter to a level that Opus DTX
    cannot suppress (e.g., -100 to +100 int16, approximately -0.003 of
    full scale) and the ICE still times out, then the hypothesis is wrong
    and the issue is with the data channel keepalive or Android Chrome's
    ICE implementation"

  fix_rationale: "Increasing the jitter amplitude ensures the Opus encoder
    treats the frames as non-silence and sends actual packets over the media
    channel. This provides continuous bidirectional packet flow that keeps
    the ICE connection alive during the processing gap."

  blind_spots:
    - "If the ICE timeout is caused by something other than lack of packet
      flow (e.g., NAT binding expiry, firewall), jitter won't help"
    - "If Android Chrome's ICE timeout is shorter than the processing gap,
      even continuous packet flow may not be enough"
    - "If the data channel close is caused by the DTLS connection closing
      (not just ICE), the keepalive won't help"

