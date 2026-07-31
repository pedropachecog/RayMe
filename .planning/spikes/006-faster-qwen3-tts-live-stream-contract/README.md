---
spike: 006
name: faster-qwen3-tts-live-stream-contract
type: standard
validates: "Given the strongest Faster Qwen3-TTS candidate, when its pull-based stream is consumed by a RayMe-shaped bounded live-playback harness, then early playback, realtime continuity, interruption, and no-fallback invariants hold."
verdict: PASS
related: [004a, 004b, 005]
tags: [tts, qwen3, streaming, live-call, barge-in, regression]
---

# Spike 006: RayMe Live-Stream Contract

## What This Validates

Given the candidate that survives runtime and longitudinal gates, when `generate_voice_clone_streaming()` feeds a bounded RayMe-shaped consumer, then first playback starts before generation completes, chunk production stays ahead of playout, joins do not accumulate silence, interruption prevents late chunks, and no code path collects the entire stream before playback.

## Research

The upstream API is a pull-based generator. Its documentation explicitly warns that blocking after each yielded chunk prevents generation/playback overlap; a queue-backed consumer is required. Audio chunks are decoded with a sliding left-context window. RayMe must preserve those semantics rather than wrapping the generator in `list()` or a whole-WAV fallback.

Primary source: https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2

## Pass Gates

- A deliberately slow-stream test observes first consumer enqueue before producer completion.
- The first playback event contains immediate fields only; final totals arrive separately.
- No `generate_voice_clone()` or whole-WAV fallback is called from the streaming path.
- Bounded startup buffering has an explicit upper limit and cannot wait for stream completion.
- Interruption after first audio stops producer consumption and prevents a normal completed turn.
- For sustained samples, generated audio duration divided by wall time remains above 1.0 and late chunk debt does not grow without bound.
- Chunk boundary metrics and the listening reel do not reveal progressively widening gaps or discontinuity.

## How to Run

`live_contract_probe.py` first runs completion/interruption cases against a deterministic fake stream, then repeats both against the real OMEN 1.7B stream. Every producer crosses a queue with capacity two; the real completion case deliberately consumes slower than synthesis to force backpressure. Product integration is forbidden until all cases pass.

## Investigation Trail

- 2026-07-31: upstream pull-based semantics identified as an integration hazard; bounded producer/consumer overlap is mandatory.
- 2026-07-31: deterministic fake completion/interruption and real 1.7B completion/interruption cases all passed through a capacity-two queue.

## Results

PASS.

- Real slow-consumer case: first consumption at 387.3 ms while production continued to 24,027.5 ms; 62 chunks crossed a capacity-two queue without whole-stream collection.
- Real interruption case: stopped 278.3 ms after cancellation with one in-flight post-cancel chunk and no normal completion.
- Both fake cases and both real cases stopped their producer threads cleanly with no errors or timeouts.
- Bounded queue, early consumption, normal completion, prompt interruption, and no-whole-stream gates all passed.
