---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
outcome: promoted_for_live_call_default
decided: 2026-05-11
preferred_call_tts_engine: voxcpm2
fallback_call_tts_engine: f5
---

# VoxCPM2 Phase 8 Promotion Decision

Outcome: promoted_for_live_call_default

Preferred live-call TTS engine: voxcpm2

Fallback/comparator engine: f5

## Decision

VoxCPM2 is promoted as the preferred/default live-call TTS engine after Phase 8 live RayMe call evidence proved same-run warm first-audio latency lower than F5 while using streamed chunks.

F5 remains available as the fallback and comparator engine, but it no longer wins the default call-feel decision on speed after VoxCPM2 live call playback began consuming streaming chunks.

## Evidence

| Evidence | Path |
|----------|------|
| Live repeated warm call-flow evidence | `results/voxcpm2-live-streaming-call-flow.json` |

## Latency Result

The Phase 8 live call-flow evidence reports:

- VoxCPM2 warm live call TTFA median: `762.7 ms`
- F5 warm live call TTFA median: `948.0 ms`
- VoxCPM2 beats F5: `true`
- VoxCPM2 streaming used: `true`
- Whole-WAV fallback used: `false`

## Rationale

The Phase 7 caveat blocked VoxCPM2 from becoming the default because live RayMe calls did not consume VoxCPM2 streaming chunks. Phase 8 removed that blocker: live call playback now starts from streamed VoxCPM2 chunks, the evidence artifact passed the call-flow verifier, and the median same-run warm first-audio time beat F5 without whole-WAV fallback.
