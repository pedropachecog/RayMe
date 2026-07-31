# Faster Qwen3-TTS Human Listening Checkpoint

Automated runtime, 50-turn stability, STT intelligibility, and live-stream contract gates passed. Product integration remains blocked until the product owner listens for the failure mode that motivated this work.

## Listen in this order

1. `results/listening-reel-turns-001-025-046-050.wav`
   - Turn 1 anchor, turn 25 varied text, turn 46 varied text, turn 50 anchor.
   - One second of silence separates each sample.
   - Reject if the later samples become muffled, whispery, noisy, metallic, less intelligible, or materially less like the same speaker.
2. `../004-a-faster-qwen3-tts-06b-cuda/results/runtime/06b-chunk8-long.wav`
3. `../004-b-faster-qwen3-tts-17b-cuda/results/runtime/17b-chunk8-long.wav`
   - Compare 0.6B and 1.7B for voice resemblance, naturalness, expressiveness, and artifacts.

## Decision requested

- **Accept 1.7B:** the longitudinal reel stays stable and 1.7B is at least as good as 0.6B.
- **Prefer 0.6B:** the reel is stable, but 0.6B sounds better enough to justify its lower capacity and faster runtime.
- **Reject:** either model has audible defects that should block RayMe integration.
