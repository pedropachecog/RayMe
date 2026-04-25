---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
stopped_at: Completed 02-15-PLAN.md
last_updated: "2026-04-25T02:56:07.542Z"
progress:
  total_phases: 8
  completed_phases: 3
  total_plans: 57
  completed_plans: 56
  percent: 98
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
- Phase 02 plan 02-07 completed on 2026-04-25: faster-whisper STT, Silero VAD gating, hallucination/manual transcript fallback, and transient `/stt/transcribe` passed AI backend STT/health contracts.
- Phase 02 plan 02-08 completed on 2026-04-25: six-engine TTS registry metadata, optional TTS runtime pins, import-gated adapter modules, and transient `/tts/synthesize` route passed AI backend TTS/health contracts.
- Phase 02 plan 02-09 completed on 2026-04-25: durable Web UI voice service/API now uploads, transcribes, previews, saves without preview gate, lists, reads, renames, soft-deletes with referents, and test-plays voices.
- Phase 02 plan 02-10 completed on 2026-04-25: Settings now persists audio/VAD/STT/TTS defaults, enforces VAD bounds, and returns compact AI backend residency status.
- Phase 02 plan 02-11 completed on 2026-04-25: character writes now persist validated default voice IDs and character reads hydrate `none`, `assigned`, and `unavailable` voice states.
- Phase 02 plan 02-12 completed on 2026-04-25: client Voice Lab now uploads samples, transcribes editable references, renders the full six-engine picker, previews optionally, and saves voices without a preview gate.
- Phase 02 plan 02-13 completed on 2026-04-25: Voice Library now lists saved voices, supports row-scoped test-play and rename, and requires explicit force confirmation with readable referents before deleting referenced voices.
- Phase 02 plan 02-14 completed on 2026-04-25: Settings UI now exposes audio defaults, VAD values, compact AI backend residency status, and top-level Voice Lab navigation.
- Phase 02 plan 02-15 completed on 2026-04-25: Character Editor now assigns saved default voices through Save Character, and Gallery cards show assigned, no-voice, and unavailable voice states.
- Phase 02 plan 02-16 completed on 2026-04-25: license notices, runtime evidence gates, Voice Lab operations, safe cleanup paths, and OMEN-PC live evidence templates now document Phase 2 handoff rules.
- Phase 02 plan 02-17 completed on 2026-04-25: AI backend now exposes only a non-call `/webrtc` skeleton with explicit non-readiness flags and fixed Phase 3 offer rejection.

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
- Phase 02-07 STT policy: uploaded samples are decoded to generated temporary WAV paths, faster-whisper runs English transcribe with `condition_on_previous_text=False`, and no-speech/hallucination/failure paths preserve retry plus manual transcript fallback.
- Phase 02 GPU runtime policy: the AI backend must fail fast instead of falling
  back to CPU for production AI models. faster-whisper STT is CUDA
  `int8_float16`; F5-TTS requires CUDA PyTorch/torchaudio. OMEN deploy verifies
  the CUDA Toolkit runtime and rejects CPU-only Torch before restart.
- Execution learning policy: repeated user reports of untested handoffs must be
  converted into durable tests, saved evidence, and `.planning/LEARNINGS.md`
  entries that name the false assumption and recurrence guard.
- Phase 02-08 TTS registry policy: TTS runtime packages are locked behind the AI backend optional `tts` extra, the canonical synthesis route is `/tts/synthesize`, and per-engine adapter modules are import-gated until live runtime evidence enables real model synthesis paths.
- Phase 02-08 TTS error policy: synthesis failures return fixed public `tts_failed` details and never expose local paths, tracebacks, or adapter exception text.
- Phase 02-09 voice API policy: voice save persists metadata plus sample linkage without a preview-success gate; rename updates display name only; Web UI transcription uses the AI backend `/stt/transcribe` route with stored sample bytes.
- Phase 02-10 Settings policy: server-side Settings persists `stt_model` and `tts_default_engine` with audio/VAD defaults, uses compact AI backend status fields matching the RayMe-owned bridge, and unit tests override backend status dependencies instead of probing live LAN services.
- Phase 02-11 character default voice policy: assignments use stable voice IDs, reject missing or soft-deleted voices on write, and keep deleted references visible as `Voice unavailable` with tombstoned voice names.
- Phase 02-12 Voice Lab policy: client save is gated by sample asset, name, transcript, and selected engine only; preview success is optional and never required.
- Phase 02-12 engine-picker policy: Voice Lab renders the full six-engine roster from Settings AI backend metadata with a full-roster fallback.
- Phase 02-13 Voice Library action policy: test-play loading is row-scoped and must not disable rename/delete actions on unrelated saved voices.
- Phase 02-13 delete policy: blocked delete referents are preserved by the client delete wrapper so the UI can show readable character/chat names before `Force Delete Voice`.
- Phase 02-13 unavailable-state policy: force-deleting a referenced voice removes it from active library rows while leaving character references intact for later UI to render as `Voice unavailable`.
- Phase 02-14 Settings UI policy: browser saves include audio, VAD, STT, and TTS defaults before every endpoint test, and backend residency stays a compact endpoint-panel summary rather than a dashboard.
- Phase 02-14 navigation policy: Voice Lab is a real top-level destination; Call navigation remains out of scope for Phase 2.
- Phase 02-15 character voice UI policy: Character Editor default voice selection is route-owned state and persists only through `Save Character`.
- Phase 02-15 Gallery voice-state policy: voice names render as text-only badges, and deleted references remain visible as `Voice unavailable` rather than crashing or disappearing.
- Phase 02-16 license policy: TTS notices distinguish package/code licenses from model/weights licenses and keep default engine selection separate from commercial-use clearance.
- Phase 02-16 runtime evidence policy: runtime promotion requires one-runtime evidence first; split runtime, WSL, Docker, or subprocess paths require logged one-runtime failure evidence while preserving one public AI backend API.
- Phase 02-16 cleanup policy: Voice Lab cleanup guidance uses exact durable blob paths and protects the canonical OMEN-PC checkout plus reusable TLS material.
- Phase 02-17 signaling policy: Phase 2 exposes only `/webrtc/status` and `/webrtc/offer`; live media, captions, barge-in, and peer connection allocation remain Phase 3+ scope.

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

Last session: 2026-04-25T02:54:55Z
Stopped at: Completed 02-15-PLAN.md
Resume file: None

**Planned Phase:** 02 (AI Backend Skeleton & Voice Lab) — 18 plans — 2026-04-24T22:37:51.511Z
