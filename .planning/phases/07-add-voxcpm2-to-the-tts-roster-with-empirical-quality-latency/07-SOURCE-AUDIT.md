# Phase 07 Source Coverage Audit

All required source items are covered by the Phase 07 plan set. Deferred ideas: none.

| SOURCE | ID | Feature / Requirement | Plan | Status | Notes |
|---|---:|---|---|---|---|
| GOAL | - | Add VoxCPM2 as a RayMe TTS roster candidate with empirical quality, latency, VRAM, and call-flow evaluation before promotion | 01-12 | COVERED | Goal is decomposed into RED contracts, implementation, runtime-path decision, live evidence, manual quality, and final decision. |
| REQ | REQ-02 | AI backend targets one RTX 3060 with STT, VAD, and one resident TTS engine coexisting | 01, 05, 09, 10, 11, 12 | COVERED | CUDA-only adapter, one-hot state, VRAM soak, OMEN runtime evidence, and decision gate. |
| REQ | REQ-20 | Voice Lab accepts short audio samples and preserves sample workflow | 02, 06, 07, 11 | COVERED | Existing sample path retained; VoxCPM2 metadata layers onto Voice Lab. |
| REQ | REQ-21 | Editable transcript is captured and used by engines that benefit from it | 02, 06, 07, 11 | COVERED | Transcript-guided and reference-only modes, missing transcript warning. |
| REQ | REQ-22 | Voice save captures selected engine and engine metadata | 01, 02, 05, 06, 07, 12 | COVERED | `voxcpm2` roster, metadata, payloads, and decision writeback. |
| REQ | REQ-23 | Voice Library test-play works for saved voices | 02, 06, 11 | COVERED | Test-play forwards saved VoxCPM2 settings and evidence gate verifies. |
| REQ | REQ-24 | Voice delete/unavailable behavior remains stable | 02, 06 | COVERED | Plans explicitly preserve rename/delete/unavailable behavior. |
| REQ | REQ-41 | Full-duplex call audio path remains intact | 03, 08, 11 | COVERED | Existing call speak path extended, no public API fork. |
| REQ | REQ-42 | Barge-in/interrupt behavior remains safe | 03, 08, 11 | COVERED | Interrupt/cancel tests remain in scope for VoxCPM2 call playback. |
| REQ | REQ-45 | Shared chunk planner and TTS metrics are required | 04, 09, 11, 12 | COVERED | Scenario matrix rows, TTFA/RTF/stitch gaps, WAVs, F5 comparison, and decision gate. |
| REQ | REQ-62 | AI call audio saved by default and evidenced | 03, 08, 11 | COVERED | Call-flow JSON includes saved AI audio path. |
| REQ | REQ-80 | Settings/metadata fallback engine status remains coherent | 01, 02, 05, 07 | COVERED | Backend metadata and client fallback roster include VoxCPM2. |
| REQ | REQ-A3 | English/accent quality bar is manually evaluated | 04, 09, 10, 11, 12 | COVERED | Generated WAVs, manual quality CSV, and builder-owned listening gate. |
| RESEARCH | R-01 | Use `voxcpm==2.0.2` and model `openbmb/VoxCPM2` | 01, 05, 10 | COVERED | Optional dependency, adapter, OMEN smoke. |
| RESEARCH | R-02 | Force CUDA with `device="cuda"` and reject CPU fallback | 01, 05, 10 | COVERED | Adapter tests, CUDA guard, deploy smoke. |
| RESEARCH | R-03 | Preserve one public AI backend API | 03, 05, 06, 08, 11, 12 | COVERED | Runtime-path decision, `/tts/synthesize`, and `/webrtc/.../speak` only. |
| RESEARCH | R-04 | Use existing `metadata_json.engine_settings.voxcpm2` for durable voice settings | 02, 06, 07, 08 | COVERED | No new table; settings persist and forward. |
| RESEARCH | R-05 | Compare standard API, streaming API, NanoVLLM, and vLLM-Omni before runtime choice | 05, 09, 10, 11 | COVERED | Plan 05 creates `07-RUNTIME-PATH-DECISION.md` explicitly evaluating `standard_python_generate`, `standard_python_generate_streaming`, `nanovllm_voxcpm`, and `vllm_omni_serving` before adapter implementation while preserving one public AI backend API. |
| RESEARCH | R-06 | Preserve 48 kHz output and avoid hard-coded sample rate | 01, 05, 09, 10 | COVERED | Adapter and smoke evidence require runtime sample rate. |
| RESEARCH | R-07 | Use scenario matrix, manual CSV, VRAM soak, call-flow proof, and generated WAVs | 04, 09, 10, 11, 12 | COVERED | Evidence verifier enforces matrix/runtime/call-flow artifacts, and manual quality/decision gates are separate. |
| RESEARCH | R-08 | OMEN deployment must go through `scripts/deploy-omen.sh` | 10, 11 | COVERED | Deploy support is added to canonical script only. |
| CONTEXT | D-01 | VoxCPM2 is a full promotion candidate | 01, 05, 12 | COVERED | Metadata-visible candidate and promotion decision. |
| CONTEXT | D-02 | Promotion requires better warm call latency than F5, quality, VRAM, no regressions | 04, 09, 10, 11, 12 | COVERED | Live evidence and final decision apply all gates. |
| CONTEXT | D-03 | If quality passes but F5 latency is not beaten, keep selectable with caveats | 05, 12 | COVERED | Decision outcomes include `selectable_with_caveats`. |
| CONTEXT | D-04 | Hard gate failure means visible unavailable with clear reason | 01, 05, 10, 12 | COVERED | Engine-scoped unavailable state and final outcome. |
| CONTEXT | D-05 | Support reference-only and transcript-guided modes | 01, 05, 06, 07 | COVERED | Adapter, server, and UI controls. |
| CONTEXT | D-06 | Store voice-level cloning-mode preference | 02, 06, 07, 08 | COVERED | `metadata_json.engine_settings.voxcpm2.cloning_mode`. |
| CONTEXT | D-07 | Missing transcript uses reference-only with warning | 01, 02, 05, 06, 07 | COVERED | Warning code and client copy. |
| CONTEXT | D-08 | Save style controls and use for preview/test-play/calls | 02, 06, 07, 08 | COVERED | Style prompt and numeric controls forward. |
| CONTEXT | D-09 | Show controls only for VoxCPM2 | 02, 07 | COVERED | Conditional component and tests. |
| CONTEXT | D-10 | Preserve VoxCPM2 metadata when switching away, ignore for other engines | 02, 06, 07 | COVERED | Server and client tests. |
| CONTEXT | D-11 | Full RayMe-shaped matrix and evidence required | 04, 09, 11, 12 | COVERED | Short/medium/long, TTFA/RTF/gaps/WAVs and final decision evidence. |
| CONTEXT | D-12 | Manual listening on builder sample must pass | 04, 12 | COVERED | Blocking human verification. |
| CONTEXT | D-13 | Compare full roster; promotion specifically beats F5 | 04, 09, 11, 12 | COVERED | F5 comparator required in matrix and final decision. |
| CONTEXT | D-14 | Same 11 GB VRAM budget with Whisper + Silero + one TTS | 01, 10, 12 | COVERED | VRAM soak JSON and decision gate. |
| CONTEXT | D-15 | Standalone pass plus call-flow fail blocks promotion but remains visible/available | 03, 08, 11, 12 | COVERED | Call-flow JSON and outcome logic. |
| CONTEXT | D-16 | Manual quality CSV plus WAV samples | 04, 11, 12 | COVERED | Generated audio paths plus manual quality CSV. |
| CONTEXT | D-17 | Investigate standard, streaming, NanoVLLM, vLLM-Omni runtime paths | 05, 09, 10 | COVERED | Plan 05 creates the runtime-path decision artifact before implementation, explicitly evaluating standard Python API, `generate_streaming`, NanoVLLM-VoxCPM, and vLLM-Omni-style serving; Plans 09-10 add targeted verifier/evidence gates. |
| CONTEXT | D-18 | Preserve one public AI backend API | 03, 05, 08, 11, 12 | COVERED | Runtime decision and evidence use existing synthesis and speak APIs only. |
| CONTEXT | D-19 | Include real call-flow integration/evaluation | 03, 08, 11, 12 | COVERED | Call tests, live call-flow JSON, and final decision gate. |
| CONTEXT | D-20 | VoxCPM2 failures are engine-scoped | 01, 05, 08 | COVERED | Backend tests and sanitized failure handling. |
| CONTEXT | D-21 | Optional runtime gate, documented model/cache/artifact paths, no large downloads in git | 01, 05, 10 | COVERED | Optional extra, OMEN evidence, deploy script. |
| CONTEXT | D-22 | Backend metadata canonical, UI fallbacks/types/labels include VoxCPM2 | 01, 02, 05, 07 | COVERED | Metadata and client fallback roster. |
