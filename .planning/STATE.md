---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: phase_0_complete
last_updated: "2026-04-23T06:03:24Z"
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 9
  completed_plans: 9
  percent: 14.3
---

## Phase Status

- Phase 0 complete on 2026-04-23.
- Next phase: Phase 1 - Foundations & Text Chat.

## Current Decisions

- HTTPS strategy: `mkcert` on LAN, validated on Android Chrome via `https://192.168.1.199:8443`.
- STT default: `distil-large-v3` (`int8_float16`), WER `0.0627`.
- TTS v1 default: `f5`.
- TTS v1 roster: `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`.
- TTS long-form implementation: requires a shared engine-agnostic chunk planner before final engine comparisons; raw whole-generation fallback rows are not sufficient.
- Qwen3-TTS: included as an opt-in/non-default engine despite failing the acceptance gate; latency and accent-quality caveats still apply.
- FlashAttention 2: not installed on Windows, so Qwen 1.7B is ineligible for v1.
- VRAM soak: F5 `1990.2 MB`, XTTS `2104.0 MB`, Qwen3 `3010.0 MB`; all stable and within budget.

## Evidence

- Human-readable synthesis: `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`
- Machine-readable roll-up: `.planning/phases/00-measurement-gate/results/phase0_summary.json`
- Runtime matrix: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix.json`
- Warm-model scenario matrix and listening samples: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json`, `.planning/phases/00-measurement-gate/results/tts_scenario_audio/`

## Accumulated Context

### Roadmap Evolution

- Plan 00-07.1 inserted into `00-measurement-gate`: benchmark TTS attention/optimization backends per engine before final writeback.
- Plan 00-07.2 completed: benchmarked native Windows vs WSL runtime permutations before Phase 0 writeback.
- 2026-04-23 TTS follow-up: XTTS long-form streaming was under-tested because `inference_stream` hit its 400-token cap and fell back to full-render timing. Phase 4 must implement shared chunking for all engines and remeasure long-form paths through that planner.

### Phase 0 Completion Notes

- Android HTTPS passed with mkcert after installing the root CA on the phone.
- The checked-in measurement artifacts were captured directly on the RTX 3060 target hardware.
- Phase 1 should start from the frozen decisions in PROJECT.md rather than re-opening model-selection debates.
