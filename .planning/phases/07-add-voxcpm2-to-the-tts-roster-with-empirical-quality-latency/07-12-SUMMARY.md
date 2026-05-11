---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 07-12-manual-quality-and-final-decision
status: completed
completed_at: 2026-05-11
commits:
  - b66730e test(07-12): regenerate VoxCPM2 evidence with BeauBrown sample
---

# 07-12 Summary: Manual Quality And Final Decision

## Outcome

Completed the manual quality gate and final VoxCPM2 roster decision.

Final outcome: `selectable_with_caveats`.

VoxCPM2 is visible and selectable in the TTS roster. It is not the default engine yet because the current RayMe live call path waits for full synthesis before enqueuing audio, so it does not receive VoxCPM2 streaming TTFA benefit in calls.

## Evidence Used

- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.json`
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.csv`
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/`
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-runtime-smoke.json`
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json`
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-call-flow.json`
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/MANUAL-QUALITY.csv`
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-PROMOTION-DECISION.md`

## Manual Quality Result

The builder judged VoxCPM2 perceptively superior to F5 across the regenerated BeauBrown-s2 samples. VoxCPM2 short, medium, and long samples pass manual quality. F5 comparator rows are marked failing because they sound metallic, sometimes too fast, and repeat parts of the reference voice.

The builder reported no perceptible quality difference between VoxCPM2 baseline, standard, and streaming-collected samples.

## Latency Result

The matrix shows VoxCPM2 streaming-collected first audio is faster than F5 first audio:

- `short_reply`: VoxCPM2 `387.9 ms` vs F5 `912.6 ms`
- `medium_reply`: VoxCPM2 `381.2 ms` vs F5 `1051.5 ms`
- `long_reply`: VoxCPM2 `399.1 ms` vs F5 `1114.6 ms`

The live call-flow evidence does not yet show that benefit:

- VoxCPM2 warm call TTFA: `14425.6 ms`
- F5 warm call TTFA: `1117.1 ms`

The difference is explained by the call path: RayMe calls use full-WAV playback today, while `generate_streaming` is still only measured by the benchmark runner.

## Runtime Result

VoxCPM2 runtime evidence passed on OMEN through the canonical deployment path. Evidence shows CUDA residency, `voxcpm==2.0.2`, model id `openbmb/VoxCPM2`, no CPU fallback, and peak VRAM under the RTX 3060 budget.

## Durable Writeback

- Added final decision artifact `07-PROMOTION-DECISION.md`.
- Added machine-readable decision artifact `results/voxcpm2-decision.json`.
- Updated `.planning/STATE.md` with the Phase 07 outcome and streaming caveat.
- Updated `.planning/PROJECT.md` to list VoxCPM2 as selectable with caveats while F5 remains default.
- Updated `.planning/ROADMAP.md` to mark Phase 07 and Plan 07-12 complete.

## Verification

- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --decision-ready` - PASS
- `git diff --check` - PASS

## Follow-Up

Future work should wire VoxCPM2 `generate_streaming` chunks into RayMe live call playback if the goal is to convert the benchmark TTFA advantage into call-feel latency.
