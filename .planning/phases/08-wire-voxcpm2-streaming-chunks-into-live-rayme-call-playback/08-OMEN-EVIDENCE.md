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
