# Phase 09 Multi-Source Coverage Audit

All required source items are executable. Deferred CONTEXT items and COVERAGE opt-outs are exclusions, not gaps.

## Goal and requirements

| SOURCE | ID | Feature / requirement | Plan | Status | Notes |
|---|---|---|---|---|---|
| GOAL | — | First-class pinned 1.7B saved voice on real OMEN calls with visible prewarm, alignment, early bounded streaming, cancellation, and no whole fallback | 09-01–09-15 | COVERED | Wave 4 is a mandatory real production tracer; Waves 10–11 are final deployment and handoff. |
| REQ | REQ-22 | Truthful saved Qwen engine, exact transcript/reference, compatibility identity | 09-01–09-09, 09-12–09-15 | COVERED | Includes explicit delete→prompt eviction and permitted-fixture preflight. |
| REQ | REQ-45 | Incremental natural text, native early chunks, bounded playout, interruption | 09-03–09-05, 09-10–09-15 | COVERED | Slow LLM/native/playout and deployed live E2E. |
| REQ | REQ-46 | Latency targets/evidence without buffering cheats | 09-03–09-04, 09-08–09-15 | COVERED | <800 ms remains measured target; native/playout/RTF are release gates. |

## Context decisions

| SOURCE | ID | Feature / requirement | Plan | Status | Notes |
|---|---|---|---|---|---|
| CONTEXT | D-01 | Pin official v0.3.2 and exact 1.7B Base | 09-01, 09-02, 09-04, 09-14 | COVERED | Source/model/lock/deployed identity. |
| CONTEXT | D-02 | Truthful qwen3_1_7b and exact compatibility | 09-01, 09-07–09-09 | COVERED | No selectable old alias. |
| CONTEXT | D-03 | CUDA one-hot manager; no CPU/second TTS | 09-01, 09-03–09-05, 09-14 | COVERED | Local and twice-deployed hardware gates. |
| CONTEXT | D-04 | One RayMe public API | 09-02–09-11 | COVERED | Worker stays internal; browser uses RayMe routes. |
| CONTEXT | D-05 | Base full-ICL saved WAV plus exact transcript | 09-02, 09-04–09-07 | COVERED | Explicit upstream API opt-outs in COVERAGE. |
| CONTEXT | D-06 | Blank transcript blocks every boundary | 09-05, 09-07–09-09, 09-14–09-15 | COVERED | Backend/server/client/live fixture. |
| CONTEXT | D-07 | Tolerant practical STT alignment | 09-05, 09-07, 09-13–09-14 | COVERED | Known mismatch plus tolerant variants. |
| CONTEXT | D-08 | Text-relative generation ceilings | 09-05, 09-12–09-14 | COVERED | Mutation and real evidence. |
| CONTEXT | D-09 | Separate visible model/prompt states | 09-03–09-04, 09-07–09-09, 09-14–09-15 | COVERED | Fast component, mocked browser, real browser/hardware. |
| CONTEXT | D-10 | Prewarm selected voice; bounded/evicted cache | 09-02–09-07, 09-14 | COVERED | Includes delete→invalidate and unrelated-voice survival. |
| CONTEXT | D-11 | Preview/test-play shared readiness/errors | 09-05, 09-07–09-09, 09-14 | COVERED | Honest retryable UI and deployed evidence. |
| CONTEXT | D-12 | Qwen calls use streaming only | 09-02–09-05, 09-10–09-14 | COVERED | No fallback at fake, real tracer, final live gates. |
| CONTEXT | D-13 | Bounded early playback | 09-03–09-04, 09-11, 09-13–09-14 | COVERED | Real early hardware gate precedes broad work. |
| CONTEXT | D-14 | Bounded producer/backpressure | 09-03–09-04, 09-11–09-14 | COVERED | Bridge and paced track bounds. |
| CONTEXT | D-15 | Immediate/final timing separation | 09-03–09-04, 09-11–09-14 | COVERED | Local and raw deployed evidence. |
| CONTEXT | D-16 | Current safe segment prefill only | 09-02, 09-10, 09-13–09-14 | COVERED | Slow LLM proves no full response wait. |
| CONTEXT | D-17 | All interrupt/control causes cancel/drain/recover | 09-02–09-06, 09-10–09-14 | COVERED | Includes delete, switch, close, live cancel. |
| CONTEXT | D-18 | No done/persistence/late audio after cancel | 09-03–09-04, 09-10–09-14 | COVERED | Cross-tier rows/events/audio. |
| CONTEXT | D-19 | Engine-scoped sanitized containment | 09-02–09-11, 09-14–09-15 | COVERED | Other voices/services remain usable. |
| CONTEXT | D-20 | Full regression suite including VoxCPM2 | 09-03, 09-05, 09-11–09-15 | COVERED | Existing invariant tests remain unchanged. |
| CONTEXT | D-21 | Integrated 50-turn non-degradation gate | 09-12–09-15 | COVERED | Adds pinned speaker drift and human-pending separation. |
| CONTEXT | D-22 | Canonical deploy only | 09-04, 09-14 | COVERED | Early blocking tracer and final release both use deploy-omen.sh. |

## Research, AI-SPEC, edge, and prohibitions

| SOURCE | ID | Feature / requirement | Plan | Status | Notes |
|---|---|---|---|---|---|
| RESEARCH | R-01 | Supervised Windows CUDA worker/IPC | 09-02, 09-05 | COVERED | Reader-thread cancel, validated IPC. |
| RESEARCH | R-02 | Incremental LLM segmentation | 09-10 | COVERED | Slow LLM early submission. |
| RESEARCH | R-03 | End-to-end paced backpressure | 09-03, 09-11 | COVERED | Bridge plus track credit. |
| RESEARCH | R-04 | Persist only normal terminal speech | 09-10 | COVERED | Database/event assertions. |
| RESEARCH | R-05 | Saved identity migration/read normalization | 09-07 | COVERED | Alembic/idempotency. |
| RESEARCH | R-06 | Young-package legitimacy | 09-RESEARCH, COVERAGE, 09-01 | COVERED | Prior human approval resolved; exact automated metadata/tag/commit/lock checks. |
| RESEARCH | R-07 | Visible readiness/hard-coded roster sweep | 09-08–09-09 | COVERED | Fast component plus Playwright. |
| RESEARCH | R-08 | Canonical deployment/independent evidence | 09-04, 09-12–09-15 | COVERED | Early hard gate, self-test, final real E2E. |
| AI-SPEC | C-01–C-05 | Identity, reference integrity, streaming, timing, interruption | 09-01–09-15 | COVERED | Critical paths have local plus hardware evidence. |
| AI-SPEC | C-06–C-07 | Message integrity/endings and longitudinal stability | 09-12–09-15 | COVERED | STT/EOS/50-turn/acoustics/speaker. |
| AI-SPEC | H-01 | Clone likeness/naturalness/joins | 09-04, 09-11–09-15 | COVERED | Automated speaker/join readiness; integrated human listening remains explicitly pending. |
| AI-SPEC | H-02/C-08 | Visible containment and voice-data safety | 09-04, 09-06–09-09, 09-12–09-15 | COVERED | Hash-bound steward/basis/LAN-scope authorization sidecar with automatic non-person fallback, delete eviction, and leak self-test. |
| UI-SPEC | — | Canonical engine identity, independent readiness, three-field authorized-reference form, row-scoped prepare/synthesis/retry, truthful call gate, fixed live-region/focus/reduced-motion/44px contracts | 09-08–09-09, 09-15 | COVERED | Production tasks name EndpointSettingsPanel, VoiceLibraryRow/List, Voice Lab, and call route; Playwright is the wave acceptance and deployed browser gate. |
| EDGE | E-01–E-06 | Empty input, byte hash/exact transcript, idempotency, concurrency, REQ-45/46 concrete gates | 09-01–09-15 | COVERED | Named behaviors/assumptions in task contracts. |
| PROHIBITION | P-01 | No arbitrary/unapproved reference | 09-04, 09-06–09-07, 09-09, 09-13–09-15 | COVERED | Phase 005 requires a matching hash-bound speaker/data-steward authorization sidecar; missing/malformed/wrong-hash/wrong-scope metadata automatically selects the deterministic mechanical fallback. |
| PROHIBITION | P-02 | No hosted/private voice leakage | 09-02, 09-04–09-15 | COVERED | Local-only audio/scorer plus leak mutation. |
| PROHIBITION | P-03 | No model/CPU/x-vector/whole-WAV substitution | 09-01–09-05, 09-11–09-15 | COVERED | Identity/fallback checks and COVERAGE opt-outs. |
| PROHIBITION | P-04 | No hidden loading/full buffering | 09-03–09-04, 09-08–09-15 | COVERED | Fast, mocked, real hardware/browser proof. |

## Explicit exclusions

0.6B selectable engine; generic `generate()` default voice; Torch use of GGML-only `ref_spk`/`ref_rvq`/`ref_spk_emb`/`ref_codes`; whole `generate_voice_clone()`; CustomVoice and its streaming method; VoiceDesign and its streaming method; x-vector/promptless, multilingual, GGML/quantized/Triton/vLLM/server/demo paths; broad UI redesign.

**Audit result:** PASS — no source item is missing from the 15-plan executable set.
