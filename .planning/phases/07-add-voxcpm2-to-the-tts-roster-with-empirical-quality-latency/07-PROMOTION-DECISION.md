---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
outcome: selectable_with_caveats
decided: 2026-05-11
reference_voice: BeauBrown-s2
reference_audio: web-ui/server/data/blobs/voices/voice_asset_531ca6a567db4f01a870cdfba8abae96.wav
---

# VoxCPM2 Promotion Decision

Outcome: selectable_with_caveats

## Decision

VoxCPM2 is accepted into the visible TTS roster as a selectable engine with caveats.

It is not promoted to the default engine yet because the live RayMe call path does not consume VoxCPM2 streaming chunks. The current call path waits for completed synthesis before enqueuing audio, so measured live call TTFA remains slower than F5.

## Evidence

| Evidence | Path |
|----------|------|
| Scenario matrix | `results/voxcpm2-scenario-matrix.json` |
| Scenario matrix CSV | `results/voxcpm2-scenario-matrix.csv` |
| Generated audio directory | `results/audio/` |
| Runtime smoke | `results/voxcpm2-runtime-smoke.json` |
| VRAM soak | `results/voxcpm2-vram-soak.json` |
| Call-flow evidence | `results/voxcpm2-call-flow.json` |
| Manual quality | `MANUAL-QUALITY.csv` |

## Quality Result

Manual listening judged VoxCPM2 far superior to F5. F5 sounded metallic, sometimes too fast, and repeated parts of the voice reference. VoxCPM2 baseline, standard, and streaming-collected samples had no perceptible quality difference to the listener.

Manual quality rows mark VoxCPM2 short, medium, and long samples as passing.

## Latency Result

The scenario matrix shows VoxCPM2 streaming-collected first audio beats F5 first audio:

- `short_reply`: VoxCPM2 `387.9 ms` vs F5 `912.6 ms`
- `medium_reply`: VoxCPM2 `381.2 ms` vs F5 `1051.5 ms`
- `long_reply`: VoxCPM2 `399.1 ms` vs F5 `1114.6 ms`

The live call-flow evidence does not yet show that benefit:

- VoxCPM2 warm call TTFA: `14425.6 ms`
- F5 warm call TTFA: `1117.1 ms`

Reason: RayMe calls currently use full-WAV TTS playback. VoxCPM2 `generate_streaming` is measured as benchmark-only until the call path consumes chunks live.

## Runtime Result

VoxCPM2 loaded on CUDA through the canonical OMEN deployment path. The runtime smoke evidence reports `voxcpm==2.0.2`, `openbmb/VoxCPM2`, CUDA device residency, and 48 kHz output. VRAM soak stayed within the RTX 3060 budget with peak VRAM `6941 MB` against budget `11264 MB`, with `cpu_fallback_detected: false`.

## Call-Flow Result

The live call-flow evidence passed:

- Preview passed.
- Voice Library test-play passed.
- Real WebRTC call speak passed.
- Call audio was enqueued.
- Failure validation stayed sanitized.

## Caveat

Use VoxCPM2 when voice quality matters more than current response speed. Keep F5 as the default for fastest current call feel until RayMe implements live streaming TTS playback for VoxCPM2 chunks.
