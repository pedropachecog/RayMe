---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
stopped_at: Completed 02-01-PLAN.md
last_updated: "2026-04-24T23:02:34.595Z"
progress:
  total_phases: 8
  completed_phases: 3
  total_plans: 57
  completed_plans: 40
  percent: 70
---

## Phase Status

- Phase 0 complete on 2026-04-23.
- Phase 01.1 Wave 1 complete on 2026-04-24: plans 01.1-01 through 01.1-03 passed backend pytest, client unit tests, and full Playwright E2E.
- Phase 01.1 Wave 2 complete on 2026-04-24: plan 01.1-04 added the guarded full Phase 1 browser path and passed backend pytest, client unit tests, and full Playwright E2E.
- Phase 01.1 Wave 3 complete on 2026-04-24: live `OMEN-PC` browser verification passed, Android Chrome product-owner acceptance passed after message-action fixes, and deployed runtime reached commit `6f687e9`.
- Phase 1 plan 01-24 completed after Phase 01.1 hardened acceptance and Android checkpoint on 2026-04-24.
- Phase 01.1 complete on 2026-04-24; next phase gate is Phase 2 planning.
- Phase 02 plan 02-01 completed on 2026-04-24: RED Web UI server voice/schema/settings contracts committed; expected implementation failures remain for later Phase 2 plans.

## Current Decisions

- HTTPS strategy: `mkcert` on LAN, validated on Android Chrome via `https://192.168.1.199:8443`.
- Operating rules: see `.planning/OPERATING-NOTES.md` before backend LAN/Android HTTPS work. Key points: use real backend `OMEN-PC`/`192.168.1.199`, keep Windows artifacts under `C:\Users\pmpg\rayme\`, reuse `.local/phase1-tls/` certs, and do not create throwaway certs.
- STT default: `distil-large-v3` (`int8_float16`), WER `0.0627`.
- TTS v1 default: `f5`.
- TTS v1 roster: `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`.
- TTS future implementation policy: keep all measured engine paths available, including `LuxTTS`, `Chatterbox Turbo`, and `TADA 1B`; use quality evaluations to choose defaults, labels, warnings, and retesting priorities.
- TTS long-form implementation: shared engine-agnostic chunk planner is now implemented in the scenario harness; raw whole-generation fallback rows are no longer the only comparison.
- TTS quality notes: Spike 003 is closed as `PASS_WITH_CAVEATS`. LuxTTS optimized is very fast but has current user-sample quality failures; Chatterbox Turbo baseline long-form is gibberish, while optimized long-form normal and seed 1337 are fine on the listened long samples; TADA Windows optimized long is acceptable while WSL is caution; XTTS/F5 long samples need sample/tuning caveats.
- Qwen3-TTS: included as an opt-in/non-default engine despite failing the acceptance gate; latency and accent-quality caveats still apply.
- FlashAttention 2: not installed on Windows, so Qwen 1.7B is ineligible for v1.
- VRAM soak: F5 `1990.2 MB`, XTTS `2104.0 MB`, Qwen3 `3010.0 MB`; all stable and within budget.
- Phase 02-01 contract policy: voice APIs use stable internal voice IDs, voice save has no preview gate, voice deletes surface `Voice unavailable`, and Settings owns save-audio/VAD/status fields.

## Evidence

- Human-readable synthesis: `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`
- Machine-readable roll-up: `.planning/phases/00-measurement-gate/results/phase0_summary.json`
- Runtime matrix: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix.json`
- Warm-model scenario matrix and listening samples: `.planning/phases/00-measurement-gate/results/tts_runtime_matrix_v2.json`, `.planning/phases/00-measurement-gate/results/tts_scenario_audio/`

## Accumulated Context

### Roadmap Evolution

- Plan 00-07.1 inserted into `00-measurement-gate`: benchmark TTS attention/optimization backends per engine before final writeback.
- Plan 00-07.2 completed: benchmarked native Windows vs WSL runtime permutations before Phase 0 writeback.
- 2026-04-23 TTS follow-up: shared chunking has been implemented and the Windows plus WSL matrix reran. Manual listening is partially scored but sufficient to close the spike with caveats: keep all engines, avoid raw latency-only defaults, tune F5 long-form stretch/duration, retest LuxTTS with better references, and keep Chatterbox optimized long-form while avoiding baseline/raw long-form.
- Phase 01.1 inserted after Phase 1: UI acceptance and regression test hardening. Reason: Phase 1 live LAN/Android acceptance exposed UI workflows that existed but were not adequately agent-tested before product-owner testing. Future manual user testing must be treated as acceptance after agent-run API/browser/deployed verification, not first-line QA.

### Phase 0 Completion Notes

- Android HTTPS passed with mkcert after installing the root CA on the phone.
- The checked-in measurement artifacts were captured directly on the RTX 3060 target hardware.
- Phase 1 should start from the frozen decisions in PROJECT.md rather than re-opening model-selection debates.

## Session Continuity

Last session: 2026-04-24T23:00:14Z
Stopped at: Completed 02-01-PLAN.md
Resume file: None

**Planned Phase:** 02 (AI Backend Skeleton & Voice Lab) — 18 plans — 2026-04-24T22:37:51.511Z
