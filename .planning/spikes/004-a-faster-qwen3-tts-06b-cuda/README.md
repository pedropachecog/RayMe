---
spike: 004a
name: faster-qwen3-tts-06b-cuda
type: comparison
validates: "Given faster-qwen3-tts v0.3.2 and OMEN's RTX 3060, when the 0.6B Base voice-cloning model runs on native Windows, then its CUDA enforcement, VRAM fit, latency, streaming cadence, and basic output validity are known."
verdict: PASS
related: [003, 004b, 005, 006]
tags: [tts, qwen3, cuda-graphs, windows, benchmark, voice-clone]
---

# Spike 004a: Faster Qwen3-TTS 0.6B CUDA Runtime

## What This Validates

Given the immutable `faster-qwen3-tts` `v0.3.2` release and RayMe's native-Windows RTX 3060 host, when `Qwen/Qwen3-TTS-12Hz-0.6B-Base` performs warmed voice-clone streaming, then the engine stays on CUDA, fits the 11 GiB working budget, starts early enough for a live call, produces faster than realtime, and yields structurally valid finite audio.

## Research

Primary sources:

- https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2
- https://github.com/andimarafioti/faster-qwen3-tts/blob/v0.3.2/README.md
- https://github.com/andimarafioti/faster-qwen3-tts/blob/v0.3.2/pyproject.toml

The package requires Python 3.10+, PyTorch 2.5.1+, and an NVIDIA CUDA GPU. Its Torch backend uses static KV caches and `torch.cuda.CUDAGraph`; streaming yields decoded audio every configurable codec-step chunk. The upstream Windows RTX 4060 result is promising but is not accepted as RayMe evidence.

| Approach | Pros | Cons | Status |
|---|---|---|---|
| 0.6B Base, Torch CUDA graphs | Lowest expected TTFA/VRAM; native Python streaming API | May lose fidelity or stability versus 1.7B | Chosen for 004a |
| 1.7B Base, Torch CUDA graphs | Higher upstream quality target | More VRAM and lower throughput | Compared in 004b |
| GGML backend | Alternate optimized runtime | Extra native wheel/toolchain and not RayMe's current Python adapter shape | Deferred unless Torch fails |

## Pass Gates

- `torch.cuda.is_available()` is true and all model parameters are CUDA-backed.
- No CPU fallback or silent quantized substitute.
- Peak runtime VRAM is at most 11,264 MiB.
- Warm median TTFA is below 500 ms, or demonstrably improves RayMe's current same-host baseline while remaining suitable for bounded live startup.
- Sustained generation is faster than realtime (`RTFx > 1.0`).
- Every sample is finite, non-empty, non-silent, and unclipped.
- Streaming produces multiple chunks and first chunk arrives before completion.

## How to Run

The rerunnable native-Windows probe will be added beside this README and run in an isolated OMEN spike environment. Results and selected WAVs return to this directory.

## Investigation Trail

- 2026-07-31: selected immutable `v0.3.2`; confirmed OMEN uses Python 3.11.15, CUDA PyTorch 2.10.0+cu126, and RTX 3060 12 GB.
- 2026-07-31: current RayMe services use about 2.3 GiB VRAM, leaving about 9.8 GiB free for a non-disruptive first probe.
- 2026-07-31: the first RayMe-reference medium sample failed to emit EOS and reached the 1,024-token ceiling, producing 81.92 seconds of audio. The owned probe was stopped; RayMe remained online. Added `diagnose_modes.py` to compare RayMe and upstream references under a bounded 256-token ceiling before drawing a model verdict.
- 2026-07-31: the bounded run isolated the failure to RayMe ICL and STT exposed an invalid probe fixture pairing: the WAV says `Okay... I resent you... You blew it`, while the supplied transcript described the Vulcan Science Academy. That mismatch also made full-text-prefill ICL prepend corrupted reference-tail words. The canonical Phase 0 `short_ref_transcript.txt` confirms the STT reading, so the spike transcript was corrected and the bounded diagnostic scheduled again.

## Results

PASS on native Windows/RTX 3060 with `faster-qwen3-tts==0.3.2`, CUDA PyTorch `2.10.0+cu126`, ICL voice cloning, full-text prefill per synthesis request, and a cached reference prompt.

| Metric | 4-step chunks | 8-step chunks |
|---|---:|---:|
| Median TTFA | 341.6 ms | 469.4 ms |
| Median RTFx | 1.69 | 1.99 |
| Maximum positive chunk debt | 0.0 ms | 0.0 ms |

- Long sample: 501.6 ms TTFA, 2.07 RTFx, 20.56 seconds, natural EOS.
- Peak Torch reservation: 3,528.0 MiB; total system GPU use with RayMe still resident: 6,052 MiB.
- All structural, natural-stop, plausible-duration, CUDA, VRAM, realtime, TTFA, and early-stream gates passed.
- RayMe GPU STT reproduced the medium and long target texts with normalized WER `0.0`.
- One invalid-run artifact is deliberately preserved: the original probe paired the WAV with an unrelated transcript and generated 81.92 seconds to the token cap. Correcting the transcript removed the failure. Production must treat reference audio/transcript alignment as a hard input invariant.
- First-time reference extraction took about 8.9 seconds. It is excluded from warmed TTFA and must be completed visibly before the first call turn.
