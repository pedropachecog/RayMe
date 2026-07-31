---
spike: 004b
name: faster-qwen3-tts-17b-cuda
type: comparison
validates: "Given the same v0.3.2 runtime and RayMe fixtures as 004a, when the 1.7B Base model runs on OMEN, then its quality headroom can be compared without exceeding VRAM or losing realtime playback."
verdict: PASS
related: [003, 004a, 005, 006]
tags: [tts, qwen3, cuda-graphs, windows, benchmark, voice-clone]
---

# Spike 004b: Faster Qwen3-TTS 1.7B CUDA Runtime

## What This Validates

Given the exact 004a environment and voice fixture, when `Qwen/Qwen3-TTS-12Hz-1.7B-Base` is measured head-to-head with 0.6B, then RayMe can select quality headroom only if it fits the RTX 3060 and remains genuinely realtime.

## Research

The upstream project labels 1.7B as the higher-quality Base option and reports native streaming, but its public benchmarks do not cover RayMe's RTX 3060, RayMe's reference voice, or long sequential-call behavior. It therefore receives the same gates as 0.6B.

An open upstream issue reports pitch/style discontinuity when separate LLM text chunks are synthesized independently:
https://github.com/andimarafioti/faster-qwen3-tts/issues/96

## Pass Gates

Identical to 004a. A 1.7B win additionally requires a meaningful quality advantage over 0.6B; higher parameter count alone is not a win.

## How to Run

Use the shared runtime probe from Spike 004a with the 1.7B model ID and this directory as the result target.

## Investigation Trail

- 2026-07-31: 1.7B retained for direct comparison rather than assumed superior.
- 2026-07-31: the model fit alongside RayMe's resident services and cleared every runtime gate. Both 0.6B and 1.7B achieved zero normalized STT WER on the selected medium and long samples, so objective transcription did not establish a quality winner. The 1.7B model advanced to longitudinal and human-listening gates because it retained realtime behavior while offering the upstream higher-capacity quality path.

## Results

PASS on native Windows/RTX 3060 with the same runtime, fixture, ICL mode, and full-text-prefill settings as 004a.

| Metric | 4-step chunks | 8-step chunks |
|---|---:|---:|
| Median TTFA | 368.9 ms | 520.1 ms |
| Median RTFx | 1.46 | 1.71 |
| Maximum positive chunk debt | 0.0 ms | 0.0 ms |

- Long sample: 523.5 ms TTFA, 1.78 RTFx, 20.0 seconds, natural EOS.
- Peak Torch reservation: 5,604.0 MiB; total system GPU use with RayMe still resident: 8,128 MiB.
- All structural, natural-stop, plausible-duration, CUDA, VRAM, realtime, TTFA, and early-stream gates passed.
- RayMe GPU STT reproduced the medium and long target texts with normalized WER `0.0`.
- 1.7B uses 2,076 MiB more reserved VRAM than 0.6B and is about 14% slower at the selected four-step live chunk size. Human listening remains the quality-selection gate.
