---
spike: 005
name: faster-qwen3-tts-longitudinal-quality
type: standard
validates: "Given one hot Faster Qwen3-TTS model and a fixed RayMe voice, when at least 50 sequential turns are generated, then early/middle/late evidence proves or rejects progressive degradation and state leakage."
verdict: PASS
related: [003, 004a, 004b, 006]
tags: [tts, qwen3, soak, quality, intelligibility, regression]
---

# Spike 005: Longitudinal Conversation Quality

## What This Validates

Given the runtime winner from 004, when a single hot process synthesizes at least 50 sequential short, medium, and long RayMe-shaped turns, then it must not progressively become muffled, whisper-like, noisy, silent, clipped, less intelligible, or less speaker-consistent.

## Research

This is the kill gate. Upstream parity samples are capped around 14 seconds and do not prove session-long stability. Open issues report inconsistent pitch/style across independently synthesized streaming text chunks and occasional swallowed endings in roughly 2 of 50 generated sentences:

- https://github.com/andimarafioti/faster-qwen3-tts/issues/96
- https://github.com/andimarafioti/faster-qwen3-tts/issues/105

The probe therefore measures turn order, not just isolated sample quality.

## Pass Gates

- At least 50 consecutive successful generations in one hot process.
- Zero NaN/Inf, empty, near-silent, hard-clipped, or pure-noise outputs.
- Early/middle/late bucket intelligibility does not degrade materially; round-trip STT WER must not rise monotonically or by more than 0.15 absolute from early to late median.
- Late-bucket RMS, voiced-energy proxy, and high-frequency ratio stay within bounded ranges of the early bucket; no progressive collapse consistent with whispering/muffling/noise.
- Deterministic repeated-text controls with reset seeds do not drift across turn position.
- Selected early/middle/late WAVs and a concatenated listening reel are preserved for product-owner listening.

## How to Run

`soak_probe.py` runs in the isolated OMEN environment, repeats a deterministic anchor at turns 1/10/20/30/40/50, preserves every WAV, and creates a turn 1/25/46/50 listening reel. `evaluate_stt.py` then scores every turn with RayMe's resident GPU STT and compares early versus late WER.

## Observability

Every turn records UTC time, model, seed policy, text class, wall time, TTFA, generation rate, chunk count/gaps, duration, peak/RMS, clipping and silence fractions, spectral ratios, zero-crossing rate, STT transcript/WER when available, CUDA allocation, and failure category.

## Investigation Trail

- 2026-07-31: user-reported longitudinal collapse was promoted to the primary acceptance gate rather than treated as an anecdotal quality note.
- 2026-07-31: advanced 1.7B to the soak because it passed the RTX 3060 runtime gates and preserves more model capacity than 0.6B. The 50-turn acoustic/runtime/STT gate passed.
- 2026-07-31: product owner listened to the 0.6B and 1.7B comparisons plus the longitudinal reel, accepted the quality, and selected 1.7B for RayMe integration.

## Results

PASS — automated and human-listening gates are complete.

- 50/50 sequential turns completed in one hot process with natural EOS, first playback before completion, faster-than-realtime synthesis, and valid audio.
- Deterministic anchor turns 1/10/20/30/40/50 were bit-identical (`anchor_unique_hashes=1`).
- GPU use stayed at 8,348 MiB during the run; reserved-memory growth from early to late was 0.0 MiB.
- Early-to-late mean RMS changed by -0.248 dB, spectral-centroid ratio was 0.805, spectral-flatness change was -0.0002, RTFx ratio was 0.999, and TTFA changed by +3.17 ms.
- RayMe Whisper accepted 50/50 WAVs. Early WER was 0.000, late WER was 0.000, and overall WER was 0.00736.
- Product-owner listening accepted the longitudinal stability and selected the 1.7B model for implementation.
