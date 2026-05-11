# Phase 07 VoxCPM2 OMEN Runtime Evidence

This artifact records live OMEN evidence for VoxCPM2 promotion. Deployment must use `scripts/deploy-omen.sh`; do not create alternate deployment scripts or manually manage RayMe scheduled tasks.

## Runtime Identity

| Field | Value |
|-------|-------|
| Commit SHA | `39f1afaec30b160ac2160d5ffdf8723e21f594f5` |
| Deploy command | `RAYME_OMEN_VERIFY_VOXCPM2=1 scripts/deploy-omen.sh` |
| Executed shell command | `RAYME_OMEN_VERIFY_VOXCPM2=1 RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON=.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-runtime-smoke.json RAYME_OMEN_VOXCPM2_VRAM_SOAK_JSON=.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json scripts/deploy-omen.sh` |
| Python package pin | `voxcpm==2.0.2` |
| Model id | `openbmb/VoxCPM2` |
| Device argument | `device="cuda"` |
| CUDA torch version | `torch==2.10.0+cu126`, CUDA `12.6` |
| Torch CUDA available | `true`, device `NVIDIA GeForce RTX 3060` |
| Model cache path | `C:\Users\pmpg\.cache\huggingface\hub\models--openbmb--VoxCPM2\snapshots\bffb3df5a29440629464e5e839f4d214c8714c3d` |
| Output sample rate | `48000` |

## Install And Load Smoke

| Check | Command or Evidence | Result |
|-------|---------------------|--------|
| Dependency sync | `uv sync --project ai-backend --extra tts --python 3.11` followed by CUDA PyTorch repair | passed |
| Import smoke | runtime probe imported `voxcpm` from the synced AI backend venv | passed |
| CUDA model load | `VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)` with post-load CUDA parameter verification; documented `device="cuda"` kw is not accepted by `voxcpm==2.0.2` | passed |
| Public API preserved | RayMe AI backend `/health` and `/tts/synthesize` remain the public surface | passed; live `/health` and Web UI settings checks passed through `scripts/deploy-omen.sh` |

## VRAM Evidence

| Moment | GPU | VRAM used MB | VRAM free MB | Notes |
|--------|-----|--------------|--------------|-------|
| Before VoxCPM2 load | NVIDIA GeForce RTX 3060 | 714 | 11397 | captured by `results/voxcpm2-runtime-smoke.json` |
| After VoxCPM2 load | NVIDIA GeForce RTX 3060 | 6334 | 5777 | peak stayed below 11264 MB budget |
| After short synthesis | NVIDIA GeForce RTX 3060 | n/a | n/a | Plan 07-10 performed load/warm-up smoke; scenario synthesis evidence is reserved for Plan 07-11 |
| After unload or engine switch | NVIDIA GeForce RTX 3060 | n/a | n/a | deploy restarted live AI backend with F5 resident after standalone probe |

## Smoke Artifacts

| Artifact | Required path | Status |
|----------|---------------|--------|
| Runtime smoke JSON | `results/voxcpm2-runtime-smoke.json` | passed |
| Scenario matrix JSON | `results/voxcpm2-scenario-matrix.json` |  |
| Scenario matrix CSV | `results/voxcpm2-scenario-matrix.csv` |  |
| Generated WAV directory | `results/audio/` |  |
| VRAM soak JSON | `results/voxcpm2-vram-soak.json` | passed |
| Call-flow JSON | `results/voxcpm2-call-flow.json` |  |

## Failure Handling

| Field | Value |
|-------|-------|
| Sanitized failure category | `none` |
| Public error code | n/a |
| Raw traceback exposed publicly | no |
| Local path or cache path exposed publicly | no |
| Other TTS engines stayed available | yes; deployed AI backend reported `resident_tts_engine=f5`, STT ready, and VAD ready after the standalone VoxCPM2 probe |

## Acceptance Notes

Record only local evidence paths and sanitized failure categories in this file. Do not paste secrets, private TLS key material, or raw tracebacks.
