# Phase 07 VoxCPM2 OMEN Runtime Evidence

This artifact records live OMEN evidence for VoxCPM2 promotion. Deployment must use `scripts/deploy-omen.sh`; do not create alternate deployment scripts or manually manage RayMe scheduled tasks.

## Runtime Identity

| Field | Value |
|-------|-------|
| Commit SHA |  |
| Deploy command | `scripts/deploy-omen.sh` |
| Python package pin | `voxcpm==2.0.2` |
| Model id | `openbmb/VoxCPM2` |
| Device argument | `device="cuda"` |
| CUDA torch version |  |
| Torch CUDA available |  |
| Model cache path |  |
| Output sample rate |  |

## Install And Load Smoke

| Check | Command or Evidence | Result |
|-------|---------------------|--------|
| Dependency sync | `uv sync --project ai-backend --extra tts` |  |
| Import smoke | `python -c "import voxcpm"` |  |
| CUDA model load | `VoxCPM.from_pretrained("openbmb/VoxCPM2", device="cuda")` |  |
| Public API preserved | RayMe AI backend `/health` and `/tts/synthesize` remain the public surface |  |

## VRAM Evidence

| Moment | GPU | VRAM used MB | VRAM free MB | Notes |
|--------|-----|--------------|--------------|-------|
| Before VoxCPM2 load |  |  |  |  |
| After VoxCPM2 load |  |  |  |  |
| After short synthesis |  |  |  |  |
| After unload or engine switch |  |  |  |  |

## Smoke Artifacts

| Artifact | Required path | Status |
|----------|---------------|--------|
| Runtime smoke JSON | `results/voxcpm2-runtime-smoke.json` |  |
| Scenario matrix JSON | `results/voxcpm2-scenario-matrix.json` |  |
| Scenario matrix CSV | `results/voxcpm2-scenario-matrix.csv` |  |
| Generated WAV directory | `results/audio/` |  |
| VRAM soak JSON | `results/voxcpm2-vram-soak.json` |  |
| Call-flow JSON | `results/voxcpm2-call-flow.json` |  |

## Failure Handling

| Field | Value |
|-------|-------|
| Sanitized failure category |  |
| Public error code |  |
| Raw traceback exposed publicly | no |
| Local path or cache path exposed publicly | no |
| Other TTS engines stayed available |  |

## Acceptance Notes

Record only local evidence paths and sanitized failure categories in this file. Do not paste secrets, private TLS key material, or raw tracebacks.
