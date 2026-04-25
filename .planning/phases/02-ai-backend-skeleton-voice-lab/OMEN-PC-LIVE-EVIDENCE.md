# OMEN-PC Live Evidence

Phase 2 live verification on `OMEN-PC`.

## Runtime Identity

- Date/time: 2026-04-25T04:06:42Z
- Operator: Codex
- Commit SHA: `6478f86`
- Branch: `main`
- Canonical checkout: `C:\Users\pmpg\rayme\RayMe\`
- TLS directory: `C:\Users\pmpg\rayme\phase1-tls\`
- Web URL: `https://192.168.1.199:8443/voice-lab`
- AI health URL: `https://192.168.1.199:9443/health`
- Listening ports after restart: `9443 -> pid 21216`, `8443 -> pid 6876`

## Local Automated Acceptance

Command:

```text
uv run --project web-ui/server pytest web-ui/server/tests -q && uv run --project ai-backend pytest ai-backend/tests -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e
```

Result:

```text
117 passed in web-ui/server
33 passed, 1 warning in ai-backend
78 passed in client unit tests
38 passed in local Playwright
```

## AI Backend `/health` JSON

Captured after the live generated-audio failure:

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
    {
      "id": "f5",
      "label": "F5-TTS",
      "available": false,
      "resident": false,
      "state": "unavailable",
      "unavailable_reason": "engine synthesis failed"
    },
    {
      "id": "xtts_v2",
      "label": "XTTS v2",
      "available": true,
      "resident": false,
      "state": "idle",
      "unavailable_reason": null
    },
    {
      "id": "qwen3_0_6b",
      "label": "Qwen3-TTS 0.6B-Base",
      "available": true,
      "resident": false,
      "state": "idle",
      "unavailable_reason": null
    },
    {
      "id": "luxtts",
      "label": "LuxTTS",
      "available": true,
      "resident": false,
      "state": "idle",
      "unavailable_reason": null
    },
    {
      "id": "chatterbox_turbo",
      "label": "Chatterbox Turbo",
      "available": true,
      "resident": false,
      "state": "idle",
      "unavailable_reason": null
    },
    {
      "id": "tada_1b",
      "label": "TADA 1B",
      "available": true,
      "resident": false,
      "state": "idle",
      "unavailable_reason": null
    }
  ],
  "loading_engine": null,
  "vram_used_mb": 1202.1,
  "vram_headroom_mb": 9797.9,
  "phase": "02",
  "capabilities": [
    "health",
    "stt",
    "vad",
    "tts"
  ]
}
```

## Resident Engine

- Resident engine: `f5` at startup; marked unavailable after live synthesis failed.
- Loading engine: `null`
- STT model: `distil-large-v3`
- STT compute type: `int8_float16`
- VAD ready: `true`

## Available Engines

- [x] F5-TTS
- [x] XTTS v2
- [x] Qwen3-TTS 0.6B-Base
- [x] LuxTTS
- [x] Chatterbox Turbo
- [x] TADA 1B

Unavailable engines and sanitized reasons:

| Engine | Available | Sanitized reason |
| --- | --- | --- |
| F5-TTS | no | engine synthesis failed |
| XTTS v2 | yes | n/a |
| Qwen3-TTS 0.6B-Base | yes | n/a |
| LuxTTS | yes | n/a |
| Chatterbox Turbo | yes | n/a |
| TADA 1B | yes | n/a |

## VRAM and Headroom

`nvidia-smi` evidence captured after the failed live generated-audio run:

```text
name, memory.total [MiB], memory.used [MiB], memory.free [MiB]
NVIDIA GeForce RTX 3060, 12288 MiB, 1025 MiB, 11086 MiB
```

- VRAM used MB: `1202.1` from `/health`, `1025 MiB` from `nvidia-smi`
- VRAM headroom MB: `9797.9`
- Under 11000 MB budget: yes

## Generated Audio Evidence

- Voice Lab sample asset: `voice_asset_8dfb004a1ad94591bcfe2f6e207fa4c2`
- Saved voice: `voice_05093ae10dee484b82637f64d63b228b` (`Live Voice Lab 1777089978615`)
- Engine used: `f5`
- Upload result: passed (`POST /api/voices/assets`)
- Transcript result: STT returned sanitized failure for the synthetic tone sample; supported manual transcript fallback was used.
- Save result: passed (`POST /api/voices`)
- Generated audio path: none
- Preview/test-play result: blocked. `POST /api/voices/voice_05093ae10dee484b82637f64d63b228b/test-play` returned `502 Bad Gateway` with `{"detail":{"message":"Voice test-play did not produce generated audio"}}`.
- Browser spec result: failed as expected after adding generated-audio assertion:

```text
RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npm --prefix web-ui/client run test:e2e -- live-voice-lab.spec.ts --project=desktop-chromium

1 failed: Voice test-play should return generated audio
```

## Android Product-Owner Result

- Android Chrome URL opened: not reached
- Certificate warning absent: not reached
- Voice Lab loaded: not reached
- Sample upload result: not reached
- Transcript retry/manual transcript result: not reached
- Save result: not reached
- Test-play result: not reached
- Product-owner acceptance: blocked before handoff
- Caveats to carry forward: Android acceptance should wait until live desktop generated audio returns an actual audio URL or base64 payload.

## Fallback Evidence

- One-runtime command attempted: canonical scheduled-task runtime at `C:\Users\pmpg\rayme\RayMe\` with public HTTPS AI backend on `https://192.168.1.199:9443`.
- Failure category: generated-audio synthesis unavailable in the current one-runtime AI backend adapter path.
- Engine affected: `f5`
- Why one runtime could not continue: current live runtime reports the engine at startup, but synthesis fails and no generated audio is returned through the public Web UI route.
- Public AI backend API preserved: yes
