# AI Backend Runtime Evidence

Phase 2 runtime work must preserve one public AI backend API while proving the
chosen model runtime can start, synthesize, report health, and stay inside the
RTX 3060 VRAM budget. The default preference is one runtime environment for all
engines. Split runtime, Docker, WSL, subprocess, or per-engine service designs
require logged failure evidence for the one-runtime path first.

## Evidence Sources

- Phase 0 summary: `.planning/phases/00-measurement-gate/results/phase0_summary.json`
- Warm-model scenario matrix: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json`
- Human-readable decisions: `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`
- Live fill-in artifact: `.planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md`

## One-Runtime Evidence Gate

Run from the canonical OMEN-PC checkout:

```text
C:\Users\pmpg\rayme\RayMe\
```

Use the reusable TLS material:

```text
C:\Users\pmpg\rayme\phase1-tls\
```

Do not use copied staging trees, throwaway certificates, or alternate
top-level directories under `C:\Users\pmpg\`.

### 1. Install and Startup Self-Test

Use the AI backend optional TTS dependencies only when runtime evidence is being
captured:

```cmd
cd /d C:\Users\pmpg\rayme\RayMe
uv sync --project ai-backend --extra tts
uv run --project ai-backend python -m pytest ai-backend\tests\test_health.py ai-backend\tests\test_tts_registry.py -q
```

Record the commit SHA, package sync result, and any self-test failures in the
live evidence artifact. If an engine cannot load, record the exact engine,
runtime, command, sanitized failure category, and whether other engines stayed
available.

### 2. Start the Public AI Backend API

The public service remains a single HTTPS AI backend API:

```cmd
cd /d C:\Users\pmpg\rayme\RayMe
uv run --project ai-backend python ai-backend\scripts\run_https.py --host 192.168.1.199 --port 9443 --cert C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem --key C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem
```

If later implementation uses WSL, Docker, subprocesses, or a split runtime, the
RayMe-visible surface must still be this one public AI backend API. Browser and
Web UI server calls must not learn per-engine runtime internals.

### 3. Health Check

Capture the full JSON response:

```cmd
curl.exe -k https://192.168.1.199:9443/health
```

Required evidence fields:

- STT model and compute type
- VAD readiness
- resident TTS engine
- available engines
- loading engine, if any
- per-engine unavailable reasons, if any
- VRAM used and headroom

### 4. Short Synthesis Check

Use the Web UI server route when testing the full Voice Lab path. For an AI
backend-only smoke test, call `/tts/synthesize` with a stored sample and
reference transcript from a known local fixture or a freshly uploaded Voice Lab
sample. Record the generated audio path returned through the RayMe flow, not a
private AI backend temp path.

The live browser spec is opt-in and must remain gated:

```cmd
set RAYME_ENABLE_LIVE_E2E=1
set RAYME_LIVE_WEB_URL=https://192.168.1.199:8443
set RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health
npm --prefix web-ui/client run test:e2e -- live-voice-lab.spec.ts --project=desktop-chromium
```

### 5. VRAM Headroom Check

Capture `nvidia-smi` while the resident engine is loaded and immediately after
the short synthesis check:

```cmd
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv
```

The live evidence gate requires used VRAM to stay under `11000` MB with enough
headroom for the later call path. Any row above `11000` MB blocks runtime
promotion until the implementation reduces residency or documents a different
approved deployment target.

## Fallback Rule

The default path is one runtime environment. A split runtime, Docker, WSL,
subprocess, or per-engine helper process is allowed only after the evidence log
shows:

1. The one-runtime install or self-test command that failed.
2. The engine and runtime that failed.
3. The failure category without raw secrets or private key material.
4. Why the failure cannot be solved inside the one-runtime path in reasonable
   scope.
5. Confirmation that RayMe still exposes one public AI backend API.

## Cleanup Safety

Runtime evidence may create virtual environments, model caches, logs, and
generated audio samples. Do not delete private TLS material, the canonical Git
checkout, or durable Web UI blobs while cleaning evidence output. Safe cleanup
paths must be listed in the phase summary with exact paths and no globs.
