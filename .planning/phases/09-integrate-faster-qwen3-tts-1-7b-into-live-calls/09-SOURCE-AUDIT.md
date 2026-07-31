# Phase 09 Multi-Source Coverage Audit

All required source items are planned. Deferred CONTEXT items and explicitly opted-out SDK capabilities are exclusions, not gaps.

## Goal and requirements

| SOURCE | ID | Feature / requirement | Plan | Status | Notes |
|---|---|---|---|---|---|
| GOAL | — | First-class pinned 1.7B saved voice on real OMEN calls with visible prewarm, alignment, early bounded streaming, cancellation, and no whole fallback | 09-01–09-06 | COVERED | Tracer through canonical deployment and call-ready handoff. |
| REQ | REQ-22 | Truthful saved Qwen engine, exact transcript/reference, compatibility identity | 09-01–09-04, 09-06 | COVERED | Runtime, migration, server, UI, deployed evidence. |
| REQ | REQ-45 | Natural incremental text plus native early streamed chunks, bounded playout, metrics, interruption | 09-01, 09-05, 09-06 | COVERED | Slow LLM/native/playout and deployed normal/cancel flows. |
| REQ | REQ-46 | Latency target and warmed/native/realtime evidence without buffering cheats | 09-01, 09-05, 09-06 | COVERED | Native <=500 ms, normal playback <=1.25 s, RTF gates; <800 ms retained as target/evidence. |

## Context decisions

| SOURCE | ID | Feature / requirement | Plan | Status | Notes |
|---|---|---|---|---|---|
| CONTEXT | D-01 | Pin official v0.3.2 and exact 1.7B Base | 09-01, 09-06 | COVERED | Immutable Git commit and model snapshot attestation. |
| CONTEXT | D-02 | Truthful qwen3_1_7b and explicit legacy compatibility | 09-01, 09-03, 09-04 | COVERED | Exact migration/read normalization; no selectable alias. |
| CONTEXT | D-03 | CUDA one-hot manager; no CPU/second resident model | 09-01, 09-06 | COVERED | Local one-hot tests and OMEN identity/VRAM evidence. |
| CONTEXT | D-04 | One RayMe public API | 09-03–09-05 | COVERED | Existing voice/call/WebRTC boundaries only. |
| CONTEXT | D-05 | Base full-ICL saved WAV plus exact transcript | 09-01–09-03 | COVERED | Worker/prompt/server path. |
| CONTEXT | D-06 | Blank transcript blocks every boundary | 09-02–09-04 | COVERED | Backend, server, and browser gates. |
| CONTEXT | D-07 | Tolerant practical STT alignment | 09-02, 09-03, 09-06 | COVERED | Dual threshold plus deployed invalid/tolerant cases. |
| CONTEXT | D-08 | Text-relative generation ceilings | 09-02, 09-06 | COVERED | Token/audio/non-EOS gates and hardware mutation case. |
| CONTEXT | D-09 | Separate visible model and prompt states | 09-01, 09-03, 09-04, 09-06 | COVERED | Backend/server/client/deployed status. |
| CONTEXT | D-10 | Prewarm selected saved voice, bounded cache | 09-01–09-04 | COVERED | Capacity one, key invalidation, call prep. |
| CONTEXT | D-11 | Preview/test-play shared readiness and errors | 09-03, 09-04, 09-06 | COVERED | Saved browser and deployed evidence. |
| CONTEXT | D-12 | Qwen calls use streaming only | 09-01, 09-05, 09-06 | COVERED | Adapter spy, live call, verifier fallback blocker. |
| CONTEXT | D-13 | Bounded early playback | 09-01, 09-05, 09-06 | COVERED | Slow producer before completion locally/deployed. |
| CONTEXT | D-14 | Bounded producer queue/backpressure | 09-01, 09-05, 09-06 | COVERED | Capacity two plus paced playout credit. |
| CONTEXT | D-15 | Immediate/final timing separation | 09-01, 09-05, 09-06 | COVERED | Schema/event tests and raw evidence. |
| CONTEXT | D-16 | non_streaming_mode only current safe segment | 09-05, 09-06 | COVERED | Slow LLM first segment and no full response. |
| CONTEXT | D-17 | All interrupt/control causes cancel/drain/recover | 09-01, 09-02, 09-05, 09-06 | COVERED | Before/after audio, hangup, switch, close. |
| CONTEXT | D-18 | No normal done/persistence/late audio after cancel | 09-01, 09-05, 09-06 | COVERED | Cross-tier DB/event/audio evidence. |
| CONTEXT | D-19 | Engine-scoped sanitized containment | 09-02–09-06 | COVERED | Typed errors, UI, recovery, leak scan. |
| CONTEXT | D-20 | Full regression suite including VoxCPM2 invariants | 09-01, 09-02, 09-05, 09-06 | COVERED | Explicit commands run existing regressions. |
| CONTEXT | D-21 | Integrated 50-turn non-degradation gate | 09-06 | COVERED | Production-path soak, STT, acoustics, memory, anchors. |
| CONTEXT | D-22 | Canonical deploy only | 09-06 | COVERED | `scripts/deploy-omen.sh` is sole install/launcher/task/deploy/evidence path. |

## Research and AI-SPEC release gates

| SOURCE | ID | Feature / requirement | Plan | Status | Notes |
|---|---|---|---|---|---|
| RESEARCH | R-01 | Supervised spawned Windows CUDA worker and validated IPC | 09-01, 09-02 | COVERED | Reader-thread cancel differs from Vox worker analog. |
| RESEARCH | R-02 | Incremental LLM-to-TTS natural segmentation | 09-05 | COVERED | Slow-LLM regression first. |
| RESEARCH | R-03 | End-to-end backpressure through paced track | 09-05 | COVERED | Both bridge and track bounds. |
| RESEARCH | R-04 | Persist only normal terminal speech | 09-05 | COVERED | Cancel/error DB checks. |
| RESEARCH | R-05 | Saved identity migration/read normalization | 09-03 | COVERED | Real Alembic command/test. |
| RESEARCH | R-06 | Young-package legitimacy | COVERAGE, 09-01 | COVERED | Prior product-owner provenance approval recorded; immutable metadata/slop/lock checks remain executable. |
| RESEARCH | R-07 | Visible client readiness and hard-coded roster sweep | 09-04 | COVERED | Saved Playwright plus dynamic metadata preservation. |
| RESEARCH | R-08 | Canonical deployment and independent evidence | 09-06 | COVERED | No alternate deployment mechanism. |
| AI-SPEC | C-01 | Immutable runtime/CUDA/one-hot residency | 09-01, 09-06 | COVERED | Critical. |
| AI-SPEC | C-02 | Reference/transcript integrity and runaway prevention | 09-02, 09-03, 09-06 | COVERED | Critical. |
| AI-SPEC | C-03 | True live streaming, bounded backpressure, realtime supply | 09-01, 09-05, 09-06 | COVERED | Critical. |
| AI-SPEC | C-04 | Timing/event truthfulness | 09-01, 09-05, 09-06 | COVERED | Critical. |
| AI-SPEC | C-05 | Interruption, hangup, and recovery | 09-01, 09-05, 09-06 | COVERED | Critical. |
| AI-SPEC | C-06 | Spoken-message integrity and clean endings | 09-06 | COVERED | Critical STT/EOS/final-word/audio gate. |
| AI-SPEC | C-07 | Longitudinal non-degradation | 09-06 | COVERED | Critical 50-turn gate. |
| AI-SPEC | H-01 | Clone likeness, natural delivery, and joins | 09-05, 09-06 | COVERED | High; local join/speaker trend plus previously accepted candidate and final physical-call acceptance. |
| AI-SPEC | H-02 | Visible readiness and contained failures | 09-01–09-06 | COVERED | High; every tier plus deployed browser evidence. |
| AI-SPEC | C-08 | Voice-data safety and scope adherence | 09-03, 09-04, 09-06 | COVERED | Critical; provenance, path containment, local-only evidence, leak scan. |

## Edge-probe assumptions and surviving prohibitions

| SOURCE | ID | Feature / requirement | Plan | Status | Notes |
|---|---|---|---|---|---|
| EDGE | E-01 | Empty/null/single input rejection and no fake empty speech | 09-01–09-05 | COVERED | Backend/server/client/turn tests. |
| EDGE | E-02 | Byte SHA-256, normalized comparison only, exact ICL transcript | 09-02, 09-03 | COVERED | Explicit planner assumptions/actions. |
| EDGE | E-03 | Legacy/deploy/warmup/prewarm idempotency | 09-01–09-03, 09-06 | COVERED | Exact repeatability contracts. |
| EDGE | E-04 | One CUDA generation, scoped cancel/terminal, bounded queues | 09-01, 09-02, 09-05 | COVERED | Concurrency state machine. |
| EDGE | E-05 | REQ-45 defined by locked live-call/AI-SPEC tests | 09-01, 09-05 | COVERED | Must-haves and regression commands. |
| EDGE | E-06 | REQ-46 concrete gates and target semantics | 09-01, 09-05, 09-06 | COVERED | Measured fields; no buffering exception. |
| PROHIBITION | P-01 | No unapproved/arbitrary clone reference | 09-02–09-04, 09-06 | COVERED | Flagged-unverified must-have plus executable boundary tests. |
| PROHIBITION | P-02 | No hosted/log/evidence private voice leakage | 09-03, 09-04, 09-06 | COVERED | Flagged-unverified must-have plus leak scan. |
| PROHIBITION | P-03 | No model/CPU/x-vector/whole-WAV substitution | 09-01, 09-02, 09-06 | COVERED | Flagged-unverified must-have plus identity/fallback gates. |
| PROHIBITION | P-04 | No hidden loading/whole buffering as ready call | 09-01, 09-04–09-06 | COVERED | Flagged-unverified must-have plus UI/call tests. |

## Explicit exclusions

- 0.6B as a separate selectable engine; CustomVoice; VoiceDesign; promptless/x-vector-only cloning; multilingual controls; GGML/quantized/Triton/vLLM/server/demo APIs; general Voice Lab/call UI redesign.
- The API capability subtraction record is in `COVERAGE.md`; every OPT-OUT has a reason.

**Audit result:** PASS — no source item is missing from the executable plan set.
