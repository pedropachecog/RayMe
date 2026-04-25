# OMEN-PC Live Evidence

Fill this file during Phase 2 live verification on `OMEN-PC`.

## Runtime Identity

- Date/time:
- Operator:
- Commit SHA:
- Branch:
- Canonical checkout: `C:\Users\pmpg\rayme\RayMe\`
- TLS directory: `C:\Users\pmpg\rayme\phase1-tls\`
- Web URL: `https://192.168.1.199:8443/voice-lab`
- AI health URL: `https://192.168.1.199:9443/health`

## AI Backend `/health` JSON

Paste the `/health` JSON here:

```json
{}
```

## Resident Engine

- Resident engine:
- Loading engine:
- STT model:
- STT compute type:
- VAD ready:

## Available Engines

Check every engine reported by health/status:

- [ ] F5-TTS
- [ ] XTTS v2
- [ ] Qwen3-TTS 0.6B-Base
- [ ] LuxTTS
- [ ] Chatterbox Turbo
- [ ] TADA 1B

Unavailable engines and sanitized reasons:

| Engine | Available | Sanitized reason |
| --- | --- | --- |
| F5-TTS |  |  |
| XTTS v2 |  |  |
| Qwen3-TTS 0.6B-Base |  |  |
| LuxTTS |  |  |
| Chatterbox Turbo |  |  |
| TADA 1B |  |  |

## VRAM and Headroom

Paste `nvidia-smi` evidence:

```text
name, memory.total [MiB], memory.used [MiB], memory.free [MiB]
```

- VRAM used MB:
- VRAM headroom MB:
- Under 11000 MB budget: yes/no

## Generated Audio Evidence

- Voice Lab sample asset:
- Engine used:
- Generated audio path:
- Preview/test-play result:
- Browser spec result:

## Android Product-Owner Result

- Android Chrome URL opened:
- Certificate warning absent: yes/no
- Voice Lab loaded: yes/no
- Sample upload result:
- Transcript retry/manual transcript result:
- Save result:
- Test-play result:
- Product-owner acceptance:
- Caveats to carry forward:

## Fallback Evidence

If one runtime failed and a split runtime, WSL, Docker, or subprocess path was
used, record the required evidence here:

- One-runtime command attempted:
- Failure category:
- Engine affected:
- Why one runtime could not continue:
- Public AI backend API preserved: yes/no
