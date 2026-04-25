---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
stopped_at: Completed 02-06-PLAN.md
last_updated: "2026-04-25T00:03:31.826Z"
progress:
  total_phases: 8
  completed_phases: 3
  total_plans: 57
  completed_plans: 45
  percent: 79
---

## Phase Status

- Phase 0 complete on 2026-04-23.
- Phase 01.1 Wave 1 complete on 2026-04-24: plans 01.1-01 through 01.1-03 passed backend pytest, client unit tests, and full Playwright E2E.
- Phase 01.1 Wave 2 complete on 2026-04-24: plan 01.1-04 added the guarded full Phase 1 browser path and passed backend pytest, client unit tests, and full Playwright E2E.
- Phase 01.1 Wave 3 complete on 2026-04-24: live `OMEN-PC` browser verification passed, Android Chrome product-owner acceptance passed after message-action fixes, and deployed runtime reached commit `6f687e9`.
- Phase 1 plan 01-24 completed after Phase 01.1 hardened acceptance and Android checkpoint on 2026-04-24.
- Phase 01.1 complete on 2026-04-24; next phase gate is Phase 2 planning.
- Phase 02 plan 02-01 completed on 2026-04-24: RED Web UI server voice/schema/settings contracts committed; expected implementation failures remain for later Phase 2 plans.
- Phase 02 plan 02-02 completed on 2026-04-24: RED AI backend health/model residency, STT/VAD, and six-engine TTS registry contracts committed; expected implementation failures remain for later Phase 2 plans.
- Phase 02 plan 02-03 completed on 2026-04-24: RED client Voice Lab, Settings, navigation, local Playwright, and opt-in live OMEN-PC contracts committed; expected implementation failures remain for later Phase 2 plans.
- Phase 02 plan 02-04 completed on 2026-04-24: migration-backed voice storage, safe original sample blob validation, and minimal Voice API/service wiring passed server voice contracts.
- Phase 02 plan 02-05 completed on 2026-04-24: typed Web UI AI backend client, sanitized processing/status errors, RayMe-owned `/api/ai-backend/status`, and Settings AI backend probe integration passed health/settings contracts.
- Phase 02 plan 02-06 completed on 2026-04-25: AI backend settings, lifespan-owned model manager, six-engine residency metadata, and expanded `/health` VRAM/headroom payload passed AI backend health/model-manager contracts.

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
- Phase 02-02 contract policy: AI backend health exposes STT/VAD/TTS residency, VRAM/headroom, one resident TTS engine, typed unavailable reasons without raw exception text, English-only STT defaults, VAD/manual-transcript fallback, and the full six-engine TTS registry with F5 as only default.
- Phase 02-03 contract policy: client Voice Lab tests require the full six-engine roster, optional preview before save, `Use default engine`, `Voice unavailable`, Settings audio/VAD/resident-engine controls, and live OMEN-PC acceptance only through explicit LAN env gates.
- Phase 02-04 storage policy: voice samples are stored under server-generated asset-id blob names, `voice_assets.voice_id` is nullable for pre-save uploads, and soft-deleted voices retain stable IDs for unavailable character default state.
- Phase 02-05 status bridge policy: browser-visible AI backend errors use fixed public code/message fields only; degraded but reachable backend health maps to Settings `Connected`, while `/api/ai-backend/status` exposes the detailed `status: degraded` signal through a RayMe-owned server route.
- Phase 02-06 AI backend residency policy: model health starts from a metadata-driven six-engine roster with F5 as the default resident engine; lightweight adapters keep unit tests model-download-free until real STT/TTS adapter plans wire runtime loading.
- Phase 02-06 health disclosure policy: public AI backend health uses fixed sanitized degradation reasons rather than raw adapter exceptions, tracebacks, or local model paths.

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

Last session: 2026-04-25T00:03:31.804Z
Stopped at: Completed 02-06-PLAN.md
Resume file: None

**Planned Phase:** 02 (AI Backend Skeleton & Voice Lab) — 18 plans — 2026-04-24T22:37:51.511Z
