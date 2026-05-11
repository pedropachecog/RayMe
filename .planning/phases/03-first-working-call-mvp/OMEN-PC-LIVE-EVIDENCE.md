# Phase 03 OMEN-PC Live Evidence

Phase 3 deployment/runtime evidence for `OMEN-PC`. Desktop live LAN/GPU
acceptance passed on `OMEN-PC`; physical Android Chrome product-owner
acceptance remains pending.

## Runtime Identity

- Date/time: `2026-05-11T22:58:10Z`
- Operator: Codex
- Deployed commit SHA: `e48e2ce57cc31a30e7df97c1f0ea9215c136dc45`
- Branch: `main`
- Canonical checkout: `C:\Users\pmpg\rayme\RayMe\`
- TLS directory: `C:\Users\pmpg\rayme\phase1-tls\`
- Web URL: `https://192.168.1.199:8443`
- AI health URL: `https://192.168.1.199:9443/health`
- Listening endpoints after deploy: `https://192.168.1.199:8443` and
  `https://192.168.1.199:9443/health` responded from the live services.

## Deployment Result

Command:

```text
scripts/deploy-omen.sh
```

Result:

- `OMEN-PC` checkout verified at `e48e2ce57cc31a30e7df97c1f0ea9215c136dc45`.
- Deployment used the canonical `scripts/deploy-omen.sh` path.
- Web client production build had already passed on `OMEN-PC`.
- AI backend and Web UI listeners were verified on `192.168.1.199`.

## Current Acceptance Snapshot

- Live desktop browser acceptance: passed.
- Browser secure context: `window.isSecureContext === true`.
- Non-mocked live call spec target: `desktop-chromium` against
  `https://192.168.1.199:8443` and `https://192.168.1.199:9443/health`.
- Live call session: `rtc_4bc2136a389c428195ae6ddc9c353846`.
- Web UI call ID: `call_a221cc68290840c085b0db70b6fd3520`.
- Result line: `1 passed (6.1m)`.
- Five-minute stability line:
  `duration_ms=300000 before_user=2 before_ai=2 after_user=13 after_ai=12`.
- Browser console/page-error guard: passed.
- Call writeback: thread returned with `call_start`, at least two
  `user_speech`, at least two `ai_speech`, and `call_end` rows.

## Deployment Fixes Applied

Earlier 03-11 deploy/debug history retained for traceability:

The first deploy of `62bb40786ffefb9b83f3ae7f882d645e60342583`
failed to keep the AI backend online because `OMEN-PC` runs the AI backend
venv with Python 3.10 and `ai-backend/app/call/events.py` imported
`NotRequired` from `typing`.

Fix commit:

```text
e77b0e4 fix(03-11): support OMEN Python typing
```

Local verification before redeploy:

```text
uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py ai-backend/tests/test_health.py -q
25 passed
```

Android Chrome smoke testing then exposed a call startup defect: the call route
started the RayMe call record without requesting microphone capture or posting
the browser WebRTC offer to the web server. That meant Chrome had no reason to
show a microphone permission prompt, and later mute/end requests targeted an AI
session that had never been created.

Fix commit:

```text
3226fd5 fix(03-11): request mic and negotiate call session
```

Local verification before redeploy:

```text
npm --prefix web-ui/client run test:unit -- --run tests/unit/call-audio.test.ts
1 passed, 4 tests

npm --prefix web-ui/client run check
passed

npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts tests/e2e/call-toolbar.spec.ts tests/e2e/call-permissions.spec.ts tests/e2e/call-summary.spec.ts --project=desktop-chromium
6 passed

npm --prefix web-ui/client run test:e2e -- tests/e2e/call-visualizer.spec.ts --project=desktop-chromium
1 passed

npm --prefix web-ui/client run test:e2e -- tests/e2e/call-mobile.spec.ts --project=mobile-chromium
1 passed

uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q
16 passed

uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py ai-backend/tests/test_call_session.py -q
19 passed
```

Follow-up Android Chrome testing then reached the microphone permission prompt
but fell back to the generic failed panel shortly after permission was granted.
The client was still treating browser-side WebRTC answer application as a hard
startup requirement, and the UI did not start local microphone metering until
after signaling succeeded.

Fix commit:

```text
a325c35 fix(03-11): keep Android call UI alive after mic grant
```

Local verification before redeploy:

```text
npm --prefix web-ui/client run check
passed

npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts tests/e2e/call-mobile.spec.ts --project=desktop-chromium
4 passed

uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q
16 passed

npm --prefix web-ui/client run test:unit -- --run tests/unit/call-audio.test.ts
1 passed, 4 tests

npm --prefix web-ui/client run build
passed
```

## GPU Runtime Evidence

Deploy script GPU guard output:

```text
torch 2.10.0+cu126 cuda 12.6 device NVIDIA GeForce RTX 3060
torchaudio 2.10.0+cu126
```

`nvidia-smi` after restart:

```text
NVIDIA GeForce RTX 3060, driver 560.94, 1156 MiB used, 12288 MiB total
```

## AI Backend `/health` JSON

Current health spot check after deployed commit
`e48e2ce57cc31a30e7df97c1f0ea9215c136dc45`:

```json
{
  "service": "rayme-ai-backend",
  "status": "degraded",
  "stt_model": "distil-large-v3",
  "stt_compute_type": "int8_float16",
  "stt_language": "en",
  "stt_ready": true,
  "vad_ready": true,
  "vad_threshold": 0.5,
  "vad_end_silence_ms": 700,
  "resident_tts_engine": "f5",
  "available_engines": [
    {"id": "f5", "available": true, "resident": true, "state": "resident"},
    {"id": "voxcpm2", "available": true, "resident": false, "state": "idle"}
  ],
  "loading_engine": null,
  "vram_used_mb": 3481.6,
  "vram_headroom_mb": 7518.4,
  "phase": "02",
  "capabilities": ["health", "stt", "vad", "tts"]
}
```

Captured after redeploy:

```json
{
  "service": "rayme-ai-backend",
  "status": "degraded",
  "stt_model": "distil-large-v3",
  "stt_compute_type": "int8_float16",
  "stt_language": "en",
  "vad_ready": true,
  "vad_threshold": 0.5,
  "vad_end_silence_ms": 700,
  "resident_tts_engine": "f5",
  "available_engines": [
    {"id": "f5", "label": "F5-TTS", "available": true, "resident": true, "state": "resident", "unavailable_reason": null},
    {"id": "xtts_v2", "label": "XTTS v2", "available": false, "resident": false, "state": "unavailable", "unavailable_reason": "engine synthesis is not implemented in Phase 02"},
    {"id": "qwen3_0_6b", "label": "Qwen3-TTS 0.6B-Base", "available": false, "resident": false, "state": "unavailable", "unavailable_reason": "engine synthesis is not implemented in Phase 02"},
    {"id": "luxtts", "label": "LuxTTS", "available": false, "resident": false, "state": "unavailable", "unavailable_reason": "engine synthesis is not implemented in Phase 02"},
    {"id": "chatterbox_turbo", "label": "Chatterbox Turbo", "available": false, "resident": false, "state": "unavailable", "unavailable_reason": "engine synthesis is not implemented in Phase 02"},
    {"id": "tada_1b", "label": "TADA 1B", "available": false, "resident": false, "state": "unavailable", "unavailable_reason": "engine synthesis is not implemented in Phase 02"}
  ],
  "loading_engine": null,
  "vram_used_mb": 1333.5,
  "vram_headroom_mb": 9666.5,
  "phase": "02",
  "capabilities": ["health", "stt", "vad", "tts"]
}
```

Post-fix health spot check after deploying `3226fd5`:

```text
service             : rayme-ai-backend
status              : degraded
stt_model           : distil-large-v3
stt_compute_type    : int8_float16
vad_ready           : True
resident_tts_engine : f5
vram_used_mb        : 1333.5
vram_headroom_mb    : 9666.5
```

Post-fix health spot check after deploying `a325c35`:

```text
service             : rayme-ai-backend
status              : degraded
stt_model           : distil-large-v3
stt_compute_type    : int8_float16
vad_ready           : True
resident_tts_engine : f5
vram_used_mb        : 1333.5
vram_headroom_mb    : 9666.5
```

## Web UI Settings Bridge

Captured after redeploy from `https://192.168.1.199:8443/api/settings`:

```text
web_url: https://192.168.1.199:8443
ai_backend_url: https://192.168.1.199:9443
ai_backend_status.endpoint_status: degraded
ai_backend_status.stt_model: distil-large-v3
ai_backend_status.stt_compute_type: int8_float16
ai_backend_status.vad_ready: true
ai_backend_status.resident_tts_engine: f5
ai_backend_status.vram_used_mb: 1333.5
ai_backend_status.vram_headroom_mb: 9666.5
```

## Live Browser Call Spec

Passing command, run on `OMEN-PC` from
`C:\Users\pmpg\rayme\RayMe`:

```text
$env:RAYME_ENABLE_LIVE_E2E='1'
$env:RAYME_LIVE_WEB_URL='https://192.168.1.199:8443'
$env:RAYME_LIVE_AI_HEALTH_URL='https://192.168.1.199:9443/health'
$env:RAYME_LIVE_REFERENCE_AUDIO_FILE='C:\Users\pmpg\rayme\RayMe\.local\phase3-live-call\fake-mic-basic-ref-4turns.wav'
$env:RAYME_LIVE_FAKE_AUDIO_FILE='C:\Users\pmpg\rayme\RayMe\.local\phase3-live-call\fake-mic-basic-ref-4turns.wav'
$env:RAYME_LIVE_STABILITY_MS='300000'
npm --prefix web-ui/client run test:e2e -- tests/e2e/live-call.spec.ts --project=desktop-chromium --reporter=line
```

Result:

```text
[live-stability] duration_ms=300000 before_user=2 before_ai=2 after_user=13 after_ai=12
Slow test file: [desktop-chromium] > tests\e2e\live-call.spec.ts (5.7m)
1 passed (6.1m)
```

The spec asserted the live canonical URLs, loaded AI `/health`, configured live
settings, uploaded a real reference WAV, opened the live call route, verified
`window.isSecureContext === true`, toggled Mute/Unmute, observed at least two
`user_speech` turns and at least two `ai_speech` turns, held the call for five
minutes, ended the call, returned to thread scrollback, and verified the durable
call rows.

WSL-origin caveat: the same live command from the WSL host reached the deployed
services but failed with `user_speech` count `0` after the page reported
`The call ended because the connection dropped.` That run originated from
`192.168.1.190` and is treated as a WSL/LAN ICE-path caveat, not passing live
evidence. The passing evidence is the OMEN-local browser run above.

## Server-Side Mute Evidence

The passing live session emitted server-side mute controls and frame drops while
muted:

```text
INFO: [rayme-call] event.sent session=rtc_4bc2136a389c428195ae6ddc9c353846 type=muted readyState=open
INFO: 192.168.1.199:55530 - "POST /webrtc/sessions/rtc_4bc2136a389c428195ae6ddc9c353846/mute HTTP/1.1" 200 OK
INFO: [rayme-call] track.recv.progress session=rtc_4bc2136a389c428195ae6ddc9c353846 frames=50 state=muted
INFO: [rayme-call] inbound.dropped session=rtc_4bc2136a389c428195ae6ddc9c353846 total=100 dropped=100 muted=True state=muted
INFO: [rayme-call] track.recv.progress session=rtc_4bc2136a389c428195ae6ddc9c353846 frames=200 state=muted
INFO: [rayme-call] inbound.dropped session=rtc_4bc2136a389c428195ae6ddc9c353846 total=200 dropped=200 muted=True state=muted
INFO: [rayme-call] event.sent session=rtc_4bc2136a389c428195ae6ddc9c353846 type=muted readyState=open
INFO: 192.168.1.199:55531 - "POST /webrtc/sessions/rtc_4bc2136a389c428195ae6ddc9c353846/mute HTTP/1.1" 200 OK
```

Interpretation: while server-side state was `muted`, inbound receive progress
continued but `dropped_audio_frames` equaled all observed frames in the sampled
window (`100/100`, then `200/200`). After unmute, subsequent logs moved out of
`state=muted` and continued the live AI response cycle.

## Five-Minute Desktop Stability

- 5-minute stability check: passed in the same OMEN-local
  `live-call.spec.ts` run.
- two user turns: passed before the hold (`before_user=2`) and continued to
  `after_user=13`.
- two ai_speech: passed before the hold (`before_ai=2`) and continued to
  `after_ai=12`.
- Catastrophic ping-pong/runaway loopback: not observed by the live spec.
- Browser uncaught exceptions/page errors: none observed by the Playwright guard.
- Exact log caveat: OMEN logs contained repeated Windows asyncio
  `_ProactorBasePipeTransport._call_connection_lost(None)` callback messages
  during the run; they did not fail the browser guard or the live acceptance
  command.

Post-`a325c35` deployed browser smoke:

```json
{
  "state": "listening",
  "rms": "0.040",
  "events": [
    "POST /api/calls/start",
    "POST /api/calls/call_0010e16cd3914850ad6f7fe2e7b755fc/offer"
  ],
  "errors": []
}
```

## Android Product-Owner Acceptance

- Android Chrome product-owner acceptance: pending
- Manual target URL: `https://192.168.1.199:8443`
- Preconditions currently met: Web UI and AI backend are deployed on
  `OMEN-PC`, HTTPS listeners are up, CUDA STT/F5 residency is visible through
  `/health`, the call route now requests microphone capture before starting
  browser negotiation, local microphone metering starts immediately after
  permission is granted, and local automated Phase 3 suites passed before
  deployment.
