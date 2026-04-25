# Phase 03 OMEN-PC Live Evidence

Phase 3 deployment/runtime evidence for `OMEN-PC`. Physical Android Chrome
product-owner acceptance remains pending.

## Runtime Identity

- Date/time: `2026-04-25T22:21:18Z`
- Operator: Codex
- Deployed commit SHA: `e77b0e4a8d504269a2e352a64a1c5ee34698cb83`
- Branch: `main`
- Canonical checkout: `C:\Users\pmpg\rayme\RayMe\`
- TLS directory: `C:\Users\pmpg\rayme\phase1-tls\`
- Web URL: `https://192.168.1.199:8443`
- AI health URL: `https://192.168.1.199:9443/health`
- Listening ports after restart: `9443 -> pid 19184`, `8443 -> pid 28868`

## Deployment Result

Command:

```text
scripts/deploy-omen.sh
```

Result:

- `OMEN-PC` pulled `e77b0e4a8d504269a2e352a64a1c5ee34698cb83`.
- Web client production build passed on `OMEN-PC`.
- Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` restarted.
- AI backend and Web UI listeners were verified on `192.168.1.199`.

## Deployment Fix Applied

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
  `/health`, and local automated Phase 3 suites passed before deployment.
