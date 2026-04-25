# Phase 03 OMEN-PC Live Evidence

Phase 3 deployment/runtime evidence for `OMEN-PC`. Physical Android Chrome
product-owner acceptance remains pending.

## Runtime Identity

- Date/time: `2026-04-25T22:34:25Z`
- Operator: Codex
- Deployed commit SHA: `3226fd54a1d4407b51261779834d6569782a1fa0`
- Branch: `main`
- Canonical checkout: `C:\Users\pmpg\rayme\RayMe\`
- TLS directory: `C:\Users\pmpg\rayme\phase1-tls\`
- Web URL: `https://192.168.1.199:8443`
- AI health URL: `https://192.168.1.199:9443/health`
- Listening ports after restart: `9443 -> pid 18588`, `8443 -> pid 21848`

## Deployment Result

Command:

```text
scripts/deploy-omen.sh
```

Result:

- `OMEN-PC` pulled `3226fd54a1d4407b51261779834d6569782a1fa0`.
- Web client production build passed on `OMEN-PC`.
- Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` restarted.
- AI backend and Web UI listeners were verified on `192.168.1.199`.

## Deployment Fixes Applied

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

Command started:

```text
RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npm --prefix web-ui/client run test:e2e -- tests/e2e/live-call.spec.ts --project=desktop-chromium
```

Result: stopped by operator before completion per handoff decision. Services
remained online after the stop. This is not counted as passing live desktop call
acceptance.

## Android Product-Owner Acceptance

- Android Chrome product-owner acceptance: pending
- Manual target URL: `https://192.168.1.199:8443`
- Preconditions currently met: Web UI and AI backend are deployed on
  `OMEN-PC`, HTTPS listeners are up, CUDA STT/F5 residency is visible through
  `/health`, the call route now requests microphone capture before starting
  browser negotiation, and local automated Phase 3 suites passed before
  deployment.
