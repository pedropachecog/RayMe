# Phase 08 OMEN Evidence

## OMEN Dirty Checkout Preflight

Timestamp: 2026-05-11T15:28:44Z

Command:

```bash
ssh rayme-pmpg "powershell -NoProfile -Command \"cd C:\\Users\\pmpg\\rayme\\RayMe; git status --short\""
```

Output:

```text
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__baseline__long_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__baseline__medium_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__baseline__short_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__optimized__long_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__optimized__medium_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__optimized__short_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__baseline__long_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__baseline__medium_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__baseline__short_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__standard_python__long_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__standard_python__medium_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__standard_python__short_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__streaming_collected__long_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__streaming_collected__medium_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__streaming_collected__short_reply.wav
 M .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.json
?? .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5.rows.json
?? .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2.rows.json
?? runtime-temp/
```

Result: dirty

User direction: preserve

User direction recorded: 2026-05-11T18:32:44Z

The user explicitly chose `preserve`. The dirty OMEN checkout changes listed in
the preflight output must be durably preserved before deployment and must not be
discarded or reset before preservation is complete.

## OMEN Dirty Checkout Preservation

Timestamp: 2026-05-11T18:34:05Z

User decision: preserve

Preservation branch: `preserve/phase08-omen-dirty-20260511T183300Z`

Preservation commit: `2077f8ddb7d50a6cca5f1d14ff26456a781f990a`

Preserved files:

```text
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5.rows.json
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__baseline__long_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__baseline__medium_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__baseline__short_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__optimized__long_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__optimized__medium_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/f5__optimized__short_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2.rows.json
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__baseline__long_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__baseline__medium_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__baseline__short_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__standard_python__long_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__standard_python__medium_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__standard_python__short_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__streaming_collected__long_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__streaming_collected__medium_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__streaming_collected__short_reply.wav
.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.json
runtime-temp/voice_asset_531ca6a567db4f01a870cdfba8abae96.txt
```

Post-preservation branch: `main`

Post-preservation HEAD: `dbc8ff119a619c265af5adc3c2106062af2466fb`

## OMEN Dirty Checkout Preflight - After Preservation

Timestamp: 2026-05-11T18:34:05Z

Command:

```bash
ssh rayme-pmpg "powershell -NoProfile -Command \"cd C:\\Users\\pmpg\\rayme\\RayMe; git status --short\""
```

Output:

```text
```

Result: clean

## OMEN Canonical Deployment

Timestamp: 2026-05-11T18:38:11Z

Command:

```bash
OMEN_SSH_ALIAS=rayme-pmpg RAYME_OMEN_VERIFY_VOXCPM2=1 RAYME_OMEN_VOXCPM2_RUNTIME_SMOKE_JSON=.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-runtime-smoke.json RAYME_OMEN_VOXCPM2_VRAM_SOAK_JSON=.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-vram-soak.json scripts/deploy-omen.sh
```

Deployed commit SHA: `10c37838bc7e3f2a12e97ca62f6cd4b40c17aa78`

Runtime evidence path:
`.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-runtime-smoke.json`

VRAM evidence path:
`.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-vram-soak.json`

Runtime summary:

```text
package: voxcpm==2.0.2
model_id: openbmb/VoxCPM2
device: cuda
cuda_device_name: NVIDIA GeForce RTX 3060
torch_version: 2.10.0+cu126
torch_cuda_version: 12.6
runtime_sample_rate: 48000
sample_rate: 48000
model_load_ms: 23541.3
cpu_fallback_detected: false
```

VRAM summary:

```text
gpu_name: NVIDIA GeForce RTX 3060
memory_total_mb: 12288
memory_used_peak_mb: 6393
memory_free_min_mb: 5718
vram_budget_mb: 11264
within_11gb_budget: true
resident_engines:
  - voxcpm2_standalone_probe
  - live_ai_backend:f5
stt_model: distil-large-v3
vad_ready: true
cpu_fallback_detected: false
```

Deploy result: success. OMEN is running commit
`10c37838bc7e3f2a12e97ca62f6cd4b40c17aa78` through `scripts/deploy-omen.sh`.
