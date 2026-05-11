# Phase 07 VoxCPM2 Results

This directory is the deterministic evidence location for VoxCPM2 promotion artifacts. Files in this directory are generated during later OMEN runtime, scenario matrix, call-flow, VRAM soak, and manual quality passes.

## Required Paths

| Path | Producer | Purpose |
|------|----------|---------|
| `results/voxcpm2-scenario-matrix.json` | Scenario matrix run | Machine-readable VoxCPM2 rows for short, medium, and long replies. |
| `results/voxcpm2-scenario-matrix.csv` | Scenario matrix run | Spreadsheet-readable matrix rows for comparison against the current roster and F5. |
| `results/audio/` | Scenario matrix and call-flow runs | Generated WAV samples linked from matrix and manual quality rows. |
| `results/voxcpm2-vram-soak.json` | OMEN soak run | RTX 3060 VRAM before, during, and after VoxCPM2 cycling with STT/VAD residency context. |
| `results/voxcpm2-call-flow.json` | Live call-flow run | Preview/test-play/call speak evidence proving saved VoxCPM2 metadata reaches real playback. |
| `results/voxcpm2-runtime-smoke.json` | OMEN runtime smoke | Package, model, CUDA torch, cache, sample-rate, and sanitized failure evidence. |

## Matrix Row Contract

Each VoxCPM2 row in `results/voxcpm2-scenario-matrix.json` must include:

- `engine`
- `scenario`
- `request_ttfa_ms`
- `request_total_ms`
- `request_rtf`
- `generation_rtf`
- `stitched_playback_ms`
- `max_inter_chunk_gap_ms`
- `peak_vram_mb`
- `sample_path`
- `backend`
- `mode`
- `optimizations_applied`

The required scenarios are `short_reply`, `medium_reply`, and `long_reply`. Every `sample_path` must point under `results/audio/`.

## Promotion Gate

VoxCPM2 can only be promoted over F5 if these files prove better warm call-feel latency than F5, acceptable manual quality, stable VRAM below the production budget, and no call-flow regression.
