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

The matrix JSON must also include F5 comparator rows for `short_reply`, `medium_reply`, and `long_reply`, plus a `summary.promotion_comparison` object with:

- `baseline_engine`: `f5`
- `candidate_engine`: `voxcpm2`
- `metric`: `request_ttfa_ms`
- `by_scenario`: per-scenario F5 and VoxCPM2 warm request metrics

The matrix CSV must include the same required row fields listed above.

## Runtime Smoke Contract

`results/voxcpm2-runtime-smoke.json` must include:

- `package`: exact value `voxcpm==2.0.2`
- `model_id`: exact value `openbmb/VoxCPM2`
- `device`: exact value `cuda`
- `runtime_sample_rate`: runtime-reported output sample rate
- `cpu_fallback_detected`: exact value `false`

`results/voxcpm2-vram-soak.json` must include:

- `peak_vram_mb`: maximum observed VoxCPM2 soak VRAM
- `vram_budget_mb`: production budget, no greater than 11264
- `within_11gb_budget`: exact value `true`

## Call-Flow Contract

`results/voxcpm2-call-flow.json` must include:

- `engine`: exact value `voxcpm2`
- `preview_result`: one of `passed`, `failed`, or `skipped`
- `test_play_result`: one of `passed`, `failed`, or `skipped`
- `call_speak_result`: one of `passed`, `failed`, or `skipped`
- `call_audio_enqueued`: exact value `true`
- `saved_ai_audio_path`: generated audio path under `results/audio/`
- `sanitized_failure_category`: one of `none`, `tts_failed`, `call_tts_failed`, `voxcpm2_unavailable`, `runtime_unavailable`, or `validation_failed`
- `warm_call_ttfa_ms`: warm VoxCPM2 call TTFA
- `f5_warm_call_ttfa_ms`: warm F5 comparator call TTFA

## Decision Outcomes

If `results/voxcpm2-decision.json` is present, `final_outcome` must be one of:

- `promoted`
- `selectable_with_caveats`
- `visible_unavailable`
- `rejected_from_runtime_loading`

## Promotion Gate

VoxCPM2 can only be promoted over F5 if these files prove better warm call-feel latency than F5, acceptable manual quality, stable VRAM below the production budget, and no call-flow regression.
