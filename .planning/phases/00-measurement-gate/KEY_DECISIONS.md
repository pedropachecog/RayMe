# Phase 0 Key Decisions

**Phase:** 00-measurement-gate
**Completed:** 2026-04-23
**Hardware:** NVIDIA GeForce RTX 3060 (8.6, 12287 MB)
**Runtime:** Python 3.11.15 + torch 2.5.1+cu118

## Summary Table

| Decision | Value | Source |
|---|---|---|
| HTTPS strategy | mkcert | results/https_android.json |
| Whisper default rung | distil-large-v3 @ int8_float16 | results/whisper.json |
| v1 TTS default engine | f5 | results/tts_ttfa.json |
| Qwen3-TTS v1 disposition | included by override, non-default (gate failed) | results/tts_ttfa.json + results/vram_soak_qwen3.json |
| Qwen3-TTS variant (if accepted) | 0.6B-Base | measured in results/tts_ttfa.json |
| FlashAttention 2 installed | no (build: 56.1s) | results/fa2_install.json |

## Missing Inputs

None.

## 1. HTTPS on Android

Android Chrome passed with `mkcert` after the mkcert root CA was installed on the phone. The passing probe URL was `https://192.168.1.199:8443` with `window.isSecureContext === True` and `navigator.mediaDevices` defined. The validation used the direct LAN IP because `rayme.local` name resolution was not configured on the phone.

## 2. Whisper WER

| Model | Compute Type | WER | p50 Latency (ms) | Peak VRAM (MB) | Default |
|---|---|---:|---:|---:|---|
| distil-large-v3 | int8_float16 | 0.0627 | 18241.2 | 1731.4 | yes |
| large-v3-turbo | int8_float16 | 0.0524 | 23080.7 | 1074.0 | no |
| large-v3 | float16 | 0.0452 | 66396.7 | 3538.0 | no |

The default rung stays `distil-large-v3` because it kept the best latency/VRAM balance while remaining acceptable on the builder's Spanish-accented English sample. Resolved Tension #2 did not fire because the selected rung is not `large-v3` FP16.

## 3. TTS TTFA

| Engine | TTFA (ms) | RTF | Peak VRAM (MB) | Mode | Backend Label |
|---|---:|---:|---:|---|---|
| f5 | 517.3 | 0.388 | 1990.2 | simulated_streaming | not_applicable |
| xtts | 534.3 | 0.59 | 1897.6 | streaming | not_applicable |
| qwen3 | 5626.8 | 2.705 | 2509.1 | simulated_streaming_text | eager |

`f5` remains the v1 default because no engine clears the budget and F5 still has the best TTFA. Qwen3-TTS did fail its acceptance gate for `ttfa_too_high, rtf_too_high, accent_drift_or_untested`, but the builder explicitly chose to keep the measured `0.6B-Base` variant in the v1 engine roster as an opt-in, non-default path.

## 4. TTS Runtime / Acceleration Matrix

| Engine | Runtime | Host | Scenario | Backend | Status | TTFA (ms) | RTF | Peak VRAM (MB) | Source |
|---|---|---|---|---|---|---:|---:|---:|---|
| f5 | windows_native | rayme-ssh | short_ack | not_applicable | measured | 521.8 | 0.391 | 1990.2 | .planning/spikes/002-f5-triton-trtllm-wsl-path/results/f5_short_ttfa_comparison.json |
| f5 | windows_native | rayme-ssh | longform | not_applicable | measured | 528.4 | 0.096 | 1990.2 | .planning/phases/00-measurement-gate/results/f5_production_chunked_speed15.json |
| f5 | wsl_python | rayme-pmpg | short_ack | not_applicable | measured | 570.2 | 0.428 | 1988.7 | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/f5_wsl_python_short.json |
| f5 | wsl_python | rayme-pmpg | longform | not_applicable | measured | 557.2 | 0.092 | 1988.7 | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/f5_wsl_python_longform.json |
| f5 | wsl_triton | rayme-pmpg | short_ack | triton_tensorrt_llm | measured | 4870.4 | 6.088 | 4298.0 | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/f5_wsl_triton_short_ack.json |
| f5 | wsl_triton | rayme-pmpg | longform | triton_tensorrt_llm | not_available | None | None | None | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/f5_wsl_triton_longform.json |
| xtts | wsl_python | rayme-pmpg | short_ack | baseline | measured | 489.9 | 0.533 | 1936.1 | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/xtts_wsl_baseline.json |
| xtts | wsl_python | rayme-pmpg | short_ack | deepspeed | not_available | None | None | None | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/xtts_wsl_deepspeed.json |
| qwen3 | wsl_python | rayme-pmpg | short_ack | eager | measured | 4514.0 | 2.821 | 2491.3 | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/qwen_wsl_eager.json |
| qwen3 | wsl_python | rayme-pmpg | short_ack | flash_attention_2 | measured | 4697.2 | 2.936 | 2491.3 | /home/pmpg/rayme/phase0-probes/results/runtime-matrix/qwen_wsl_fa2.json |

The runtime matrix is now the source of truth for cross-runtime claims. It shows native Windows winning both measured F5 scenarios, XTTS DeepSpeed unavailable in WSL, and Qwen FlashAttention 2 slower than the eager baseline on this stack. Recommendation block: F5 short winner `windows_native`, F5 long winner `windows_native`, XTTS runtime `wsl_python_baseline`, Qwen backend `eager`.

### 4.1 TTS Streaming / Chunking Caveat

The measured long-form TTS numbers must not be treated as final engine limits until the runtime has a shared chunk planner. Phase 0 follow-up showed that XTTS native streaming works for short/medium replies, but long-form XTTS hit the `inference_stream` 400-token limit and fell back to full-render timing. That fallback inflates long-form streaming comparisons and is not acceptable as the final benchmark method.

Phase 4 must implement best-practical chunking for every TTS engine:

- Prefer sentence boundaries while handling abbreviations and short-first-sentence flushes.
- Enforce engine-specific caps such as XTTS's 400-token streaming limit.
- Avoid tiny unnatural fragments.
- Use native streaming inside safe chunks when an engine supports it.
- Use chunked playback for non-streaming engines instead of waiting for the full response.
- Measure first-chunk TTFA, total stitched playback time, inter-chunk gaps, and generate a stitched WAV for listening.

## 5. VRAM Soak (30-min cycling)

| Engine | Peak VRAM (MB) | Growth Detected | Growth Slope (MB/min) | Cycles | Fits 3060 |
|---|---:|---|---:|---:|---|
| f5 | 1990.2 | False | -1.25 | 180 | True |
| xtts | 2104.0 | False | -2.04 | 180 | True |
| qwen3 | 3010.0 | False | -9.86 | 180 | True |

All three engines stayed well below the 11 GB budget on the actual RTX 3060, and all three ended with negative growth slopes. No engine showed unbounded fragmentation during the 30-minute cycling probe.

## 6. FlashAttention 2

Windows FlashAttention 2 install remains a fail: `installed=False`, `failure_reason=windows_build_compile_error`, `build_duration_s=56.1`. That keeps Qwen3-TTS 1.7B out of scope for v1 on the native Windows runtime; the only measured Qwen variant in Phase 0 was `0.6B-Base`.

## Cascades Triggered

- Qwen3-TTS failed its acceptance gate, so it must not become the default engine. It is included only as a builder override and should be presented as an opt-in/non-default path.
- FlashAttention 2 did not install on Windows, so Qwen3-TTS 1.7B is ineligible for v1 and all current native-Windows Qwen numbers remain eager-baseline results on `0.6B-Base`.
- TTS long-form implementation must use shared chunking across all engines before final engine comparisons; raw whole-generation fallback rows are not accepted as final long-form data.

## Hardware Note

The checked-in Phase 0 measurement artifacts were captured directly on the target RTX 3060 (12 GB, sm_86), not on a larger staging GPU. That means the soak-based `fits_3060_budget` flags answer the real hardware question directly and no 4090→3060 VRAM translation was needed. TTFA and RTF values are still machine-specific and should be re-measured if the runtime stack changes materially.

## Phase 1+ Implications

- STT default: `distil-large-v3` (`int8_float16`)
- TTS v1 default: `f5` (runtime matrix keeps native Windows as the fastest measured F5 path)
- Engines shipping in v1 Voice Lab: `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base` (opt-in, non-default)
- Phase 4 implementation requirement: build the shared TTS chunk planner and rerun long-form comparisons through it before making final call-feel tuning decisions.
- HTTPS: `mkcert` on LAN, with the Android validation performed against `https://192.168.1.199:8443`
- PROJECT.md and STATE.md should freeze these choices before Phase 1 begins.

## Source JSONs

- `results/https_android.json`
- `results/whisper.json`
- `results/tts_ttfa.json`
- `results/tts_attention_matrix.json`
- `results/tts_runtime_matrix.json`
- `results/tts_runtime_matrix_v2.json`
- `results/vram_soak_f5.json`
- `results/vram_soak_xtts.json`
- `results/vram_soak_qwen3.json`
- `results/fa2_install.json`
