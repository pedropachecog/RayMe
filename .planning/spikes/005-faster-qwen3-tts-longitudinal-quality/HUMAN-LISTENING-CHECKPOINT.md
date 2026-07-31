# Faster Qwen3-TTS Human Listening Checkpoint

**Status:** ACCEPTED on 2026-07-31.

Automated runtime, 50-turn stability, STT intelligibility, and live-stream contract gates passed. The product owner listened to both model comparisons and the longitudinal reel, reported that both sounded great, and selected 1.7B for RayMe integration.

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

## Recorded decision

**Accept 1.7B.** The listening gate is closed and no longer blocks product integration.
