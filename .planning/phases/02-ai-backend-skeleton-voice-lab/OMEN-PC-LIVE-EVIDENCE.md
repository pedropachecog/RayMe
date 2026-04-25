# OMEN-PC Live Evidence

Phase 2 live verification on `OMEN-PC`.

## Runtime Identity

- Date/time: 2026-04-25T04:50:36Z
- Operator: Codex
- Commit SHA: `dfc036db8e16be40c547fc7cb904ca1636d53775`
- Branch: `main`
- Canonical checkout: `C:\Users\pmpg\rayme\RayMe\`
- TLS directory: `C:\Users\pmpg\rayme\phase1-tls\`
- Web URL: `https://192.168.1.199:8443/voice-lab`
- AI health URL: `https://192.168.1.199:9443/health`
- Listening ports after restart: `9443 -> pid 25796`, `8443 -> pid 32524`

## Local Automated Acceptance

Commands and results:

```text
uv run --project ai-backend pytest ai-backend/tests -q
36 passed, 1 warning

uv run --project web-ui/server pytest web-ui/server/tests -q
118 passed

npm --prefix web-ui/client run test:unit -- --run
78 passed

npm --prefix web-ui/client run test:e2e
37 passed, 1 unrelated mobile-text failure; targeted rerun passed

npm --prefix web-ui/client run test:e2e -- mobile-text.spec.ts --project=mobile-chromium
1 passed
```

## AI Backend `/health` JSON

Captured after the passing live generated-audio run:

```json
{
  "service": "rayme-ai-backend",
  "status": "ok",
  "stt_model": "distil-large-v3",
  "stt_compute_type": "int8_float16",
  "stt_language": "en",
  "vad_ready": true,
  "vad_threshold": 0.5,
  "vad_end_silence_ms": 700,
  "resident_tts_engine": "f5",
  "available_engines": [
    {"id": "f5", "label": "F5-TTS", "available": true, "resident": true, "state": "resident", "unavailable_reason": null},
    {"id": "xtts_v2", "label": "XTTS v2", "available": true, "resident": false, "state": "idle", "unavailable_reason": null},
    {"id": "qwen3_0_6b", "label": "Qwen3-TTS 0.6B-Base", "available": true, "resident": false, "state": "idle", "unavailable_reason": null},
    {"id": "luxtts", "label": "LuxTTS", "available": true, "resident": false, "state": "idle", "unavailable_reason": null},
    {"id": "chatterbox_turbo", "label": "Chatterbox Turbo", "available": true, "resident": false, "state": "idle", "unavailable_reason": null},
    {"id": "tada_1b", "label": "TADA 1B", "available": true, "resident": false, "state": "idle", "unavailable_reason": null}
  ],
  "loading_engine": null,
  "vram_used_mb": 1202.1,
  "vram_headroom_mb": 9797.9,
  "phase": "02",
  "capabilities": ["health", "stt", "vad", "tts"]
}
```

## VRAM and Headroom

`nvidia-smi` evidence captured after the passing live generated-audio run:

```text
memory.used [MiB], memory.total [MiB]
1025, 12288
```

- VRAM used MB: `1202.1` from `/health`, `1025 MiB` from `nvidia-smi`
- VRAM headroom MB: `9797.9`
- Under 11000 MB budget: yes

## Generated Audio Evidence

- Engine used: `f5`
- Upload result: passed (`POST /api/voices/assets`)
- Transcript result: STT returned sanitized failure for the synthetic tone sample; supported manual transcript fallback was used.
- Save result: passed (`POST /api/voices`)
- Direct AI generated-audio probe: passed (`POST /tts/synthesize` returned `200 OK` with `audio/wav` base64 payload)
- Direct OMEN F5 runtime probe: passed (`136748` WAV bytes, `24000 Hz`, `2848.0 ms`)
- Browser spec result: passed:

```text
RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npm --prefix web-ui/client run test:e2e -- live-voice-lab.spec.ts --project=desktop-chromium

1 passed (2.6m)
```

## Resolved Live Blockers

- Installed pinned `f5-tts==1.1.17` into `C:\Users\pmpg\rayme\RayMe\ai-backend\.venv`.
- Added F5 generated-audio synthesis via `F5TTS().infer(...)`.
- Added startup hardening so default TTS load failure degrades `/health` instead of killing the AI service.
- Routed F5 reference audio loading through `soundfile` to avoid Windows `torchcodec`/FFmpeg DLL failures.
- Increased Web UI synthesis timeout to allow live F5 generation to complete.

## Android Product-Owner Result

- Android Chrome URL opened: pending handoff
- Certificate warning absent: pending handoff
- Voice Lab loaded: pending handoff
- Sample upload result: pending handoff
- Transcript retry/manual transcript result: pending handoff
- Save result: pending handoff
- Test-play result: pending handoff
- Product-owner acceptance: pending handoff after passing desktop/live gate
