# Phase 7: Add VoxCPM2 to the TTS roster with empirical quality, latency, VRAM, and call-flow evaluations - Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 evaluates and, if evidence supports it, integrates VoxCPM2 as an additional RayMe TTS roster candidate after the v1 ship path. The phase covers registry metadata, optional runtime dependency handling, VoxCPM2 voice metadata, preview/test-play/call playback integration, RTX 3060 VRAM validation, RayMe-shaped latency/quality benchmarks, generated sample artifacts, and manual listening evidence.

This phase does not add managed cloud TTS/STT, multilingual v1 scope, non-TTS character features, auth, marketplace behavior, or CPU fallback. It also does not promote VoxCPM2 by enthusiasm alone: promotion requires measured call-feel evidence on the target RayMe runtime.

</domain>

<decisions>
## Implementation Decisions

### Roster Outcome And Promotion Gate
- **D-01:** VoxCPM2 is a full promotion candidate, not merely a spike. If evidence supports it, Phase 7 may make VoxCPM2 a normal first-class engine and may challenge current labels/defaults.
- **D-02:** Promotion over the current default/recommended path requires a clear call-feel win: better warm call latency than F5, acceptable voice quality, stable VRAM, and no call-flow regressions.
- **D-03:** If VoxCPM2 sounds good but does not beat the current call-feel latency path, keep it selectable but caveated. It must not be promoted over F5.
- **D-04:** If VoxCPM2 fails a hard gate such as install failure, VRAM over budget, unstable runtime, or broken call playback, keep it visible but unavailable with a clear unavailable reason, matching current engine metadata behavior.

### Cloning Mode And User-Facing Behavior
- **D-05:** Support both VoxCPM2 cloning modes: reference-only cloning and transcript-guided cloning.
- **D-06:** Store a voice-level VoxCPM2 cloning-mode preference and reuse it for preview, test-play, and calls.
- **D-07:** If a VoxCPM2 voice has no transcript, synthesize with reference-only mode but warn that transcript-guided mode may improve results.
- **D-08:** Save VoxCPM2 style controls on the voice and use them for preview, test-play, and calls.
- **D-09:** Show VoxCPM2 style controls only when VoxCPM2 is selected, keeping existing engine UX unchanged.
- **D-10:** If a voice switches away from VoxCPM2, preserve VoxCPM2-specific mode/style metadata for future switch-back, but ignore it for non-VoxCPM2 engines.

### Benchmark And Quality Evidence
- **D-11:** VoxCPM2 promotion requires a full RayMe-shaped matrix: short, medium, and long replies through the shared chunk planner; TTFA/RTF/stitch gaps; VRAM peak; generated WAVs; preview/test-play evidence; and real call-flow evidence.
- **D-12:** Manual listening must pass on the builder's own sample, covering intelligibility, voice match, accent preservation, prosody, and absence of sample leakage or mumbling artifacts.
- **D-13:** Compare VoxCPM2 against the full current roster for context, but the promotion decision specifically requires beating F5 on the current call-feel path.
- **D-14:** VoxCPM2 must satisfy the same 11 GB production VRAM budget with Whisper + Silero + one resident TTS engine under realistic cycling.
- **D-15:** If VoxCPM2 passes standalone preview/test-play benchmarks but fails real call-flow behavior, do not promote it. Keep it fully visible and available rather than hiding or disabling it.
- **D-16:** Store human quality evidence as a manual quality CSV plus generated WAV samples, following the existing `MANUAL-QUALITY.csv` evidence pattern.

### Runtime And Call-Flow Integration Path
- **D-17:** Planning must investigate all relevant VoxCPM2 runtime paths before choosing: standard Python API, streaming API, NanoVLLM-VoxCPM, and vLLM-Omni-style serving.
- **D-18:** Preserve one public AI backend API. VoxCPM2 may use in-process, subprocess, WSL, or server-backed runtime internally, but Web UI and browser callers must continue using the normal RayMe AI backend API and engine registry.
- **D-19:** Phase 7 includes real call-flow integration and evaluation through preview, test-play, and real call playback.
- **D-20:** VoxCPM2 failures must be engine-scoped. VoxCPM2 load/synthesis/call failures may mark VoxCPM2 unavailable or caveated, but other engines and the AI backend must stay available.
- **D-21:** Keep VoxCPM2 dependencies behind an optional AI backend extra/runtime gate. Document exact model, cache, and artifact paths; keep large downloads out of git.
- **D-22:** Backend metadata remains canonical, but UI fallbacks, types, and engine-label code paths must include VoxCPM2 so disconnected/degraded states still render correctly.

### the agent's Discretion
- Exact VoxCPM2 engine id, label wording, caveat chip wording, and unavailable reason taxonomy.
- Exact benchmark filenames and summary artifact names, as long as generated WAVs and manual CSV evidence remain linked.
- Exact scoring rubric weights, as long as the required quality dimensions and promotion gates above are preserved.
- Exact runtime choice after investigation, provided one public AI backend API is preserved and evidence supports the choice.
- Exact UI placement and field names for VoxCPM2 mode/style metadata, as long as non-VoxCPM2 engines are not made noisier.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope And Project Constraints
- `.planning/ROADMAP.md` - Phase 7 scope and dependency on the post-v1 ship path.
- `.planning/PROJECT.md` - Core call-feel priority, RTX 3060 hardware constraint, English-only v1, shared TTS chunking rule, self-hosted engine boundary, and current Phase 0 TTS decisions.
- `.planning/REQUIREMENTS.md` - TTS, Voice Lab, call-flow, Settings, and RTX 3060 requirements, especially `REQ-02`, `REQ-20` through `REQ-24`, `REQ-41`, `REQ-42`, `REQ-45`, `REQ-62`, `REQ-80`, and `REQ-A3`.
- `.planning/STATE.md` - Current TTS roster/defaults, future TTS policy, VRAM notes, runtime evidence rules, and Phase 7 addition.
- `.planning/OPERATING-NOTES.md` - OMEN-PC, GPU runtime, verification, and deployment rules. Deployment to OMEN must use `scripts/deploy-omen.sh`.

### Prior Phase Decisions
- `.planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md` - Full measured TTS roster policy, metadata-driven engine registry, Voice Lab semantics, runtime evidence gate, and voice ownership boundaries.
- `.planning/phases/03-first-working-call-mvp/03-CONTEXT.md` - Saved voice sample + transcript forwarding for call playback, call-start validation, and call evidence expectations.
- `ai-backend/docs/RUNTIME-EVIDENCE.md` - One-runtime evidence gate, public AI backend API constraint, synthesis smoke, and VRAM headroom checks.
- `ai-backend/docs/STT-GPU-RUNTIME.md` - CUDA runtime, no CPU fallback, OMEN RTX 3060 baseline, and deployment verification.

### Existing TTS Evidence And Harnesses
- `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/README.md` - Prior TTS engine extension lessons: latency is not enough, shared chunked playback is required, and manual listening drives caveats/defaults.
- `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/MANUAL-QUALITY.csv` - Existing manual quality evidence format to extend for VoxCPM2.
- `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/RESULT-MATRIX.csv` - Prior matrix shape for engine comparison.
- `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py` - Shared chunk planner and RayMe-shaped scenario harness for short, medium, and long TTS evaluation.
- `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py` - Existing tests for scenario matrix behavior.

### VoxCPM2 Official References
- `https://github.com/OpenBMB/VoxCPM` - Official VoxCPM/VoxCPM2 repository, feature claims, model/version table, runtime/deployment references, license, and benchmark tables.
- `https://huggingface.co/openbmb/VoxCPM2` - Official Hugging Face model card and basic `VoxCPM.from_pretrained("openbmb/VoxCPM2")` usage.
- `https://voxcpm.readthedocs.io/en/latest/quickstart.html` - Official quick start, install, Python API, CLI clone/design paths, and first-run model download behavior.
- `https://voxcpm.readthedocs.io/en/latest/reference/api.html` - Official API reference for `generate`, `generate_streaming`, `prompt_wav_path`, `prompt_text`, `reference_wav_path`, style/control input, denoise, `cfg_value`, `inference_timesteps`, device behavior, and sample rate handling.
- `https://voxcpm.readthedocs.io/en/latest/deployment/nanovllm_voxcpm.html` - NanoVLLM-VoxCPM CUDA-centric runtime, streaming inference, FastAPI server option, and VoxCPM2 support.
- `https://voxcpm.readthedocs.io/en/latest/reference/changelog.html` - VoxCPM 2 migration notes, 2B model default, 48 kHz output, architecture auto-detection, and dependency changes.

### Existing Code Entry Points
- `ai-backend/app/models/tts_registry.py` - Existing TTS metadata model, full-roster validation, adapter protocol, and default adapter builder.
- `ai-backend/app/models/engine_metadata.py` - Health/model-manager engine metadata currently mirroring the six-engine roster.
- `ai-backend/app/models/model_manager.py` - One-hot resident TTS switching, engine-scoped unavailable state, health payload, and adapter loading.
- `ai-backend/app/api/tts.py` - Transient `/tts/synthesize` route that switches engines and passes reference audio/transcript to adapters.
- `ai-backend/app/api/webrtc.py` - Call `/webrtc/sessions/{session_id}/speak` route and `SpeakRequest` reference-audio/reference-transcript payload.
- `ai-backend/app/call/session.py` - Call speech synthesis path, generic adapter support, audio enqueue, and call failure events.
- `web-ui/server/app/api/voices.py` - Voice Lab preview/test-play payload shaping and AI backend synthesis bridge.
- `web-ui/server/app/domain/voice_service.py` - Durable voice metadata, sample asset, transcript, preview, save, and test-play behavior.
- `web-ui/client/src/routes/voice-lab/+page.svelte` - Current hard-coded fallback engine list and Voice Lab selected-engine flow.
- `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` - Engine picker caveat/availability rendering.
- `web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte` - Engine label fallbacks for character default voice assignment.
- `web-ui/client/src/lib/api/types.ts` - TTS engine type union and backend engine status types.
- `scripts/deploy-omen.sh` - Canonical OMEN deployment path; fix this script if deployment support is missing.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TtsEngineMetadata`, `TtsEngineAvailability`, `TtsSynthesisInput`, and `TtsSynthesisOutput` in `ai-backend/app/models/tts_registry.py` already provide the metadata and synthesis contract shape VoxCPM2 should extend.
- `ImportGatedTtsAdapter` provides an existing optional-runtime pattern for engines whose packages may not be installed in normal tests.
- `ModelManager.switch_tts_engine()` already enforces one resident engine and engine-scoped unavailable state.
- `/tts/synthesize` and `/webrtc/sessions/{session_id}/speak` already pass reference audio and reference transcript through the AI backend boundary.
- The Voice Lab server/client flow already stores voice metadata and saved transcripts and can be extended with VoxCPM2-specific mode/style metadata.
- The scenario matrix harness already implements shared chunk planning, first-chunk timing, stitched playback modeling, inter-chunk gaps, generated WAV output, and per-engine rows.

### Established Patterns
- Durable voice/sample/transcript state belongs in the Web UI server; transient STT/TTS/VAD/model runtime belongs in the AI backend.
- The browser and Web UI server must not learn per-engine runtime internals. They call RayMe-owned routes and consume backend metadata.
- Full engine availability should be metadata-driven, but the current code still has hard-coded six-engine validation and UI fallback lists that must be expanded for VoxCPM2.
- Runtime packages for TTS engines are optional/import-gated; real runtime promotion requires live evidence, not local unit-test mocks.
- CPU fallback for production STT/TTS/VAD/model runtime is a regression.

### Integration Points
- Add VoxCPM2 metadata and adapter registration in `ai-backend/app/models/tts_registry.py`, `engine_metadata.py`, and `build_default_tts_adapters()`.
- Add a VoxCPM2 adapter module that maps RayMe saved voice data to VoxCPM2 reference-only, transcript-guided, and style-control parameters.
- Extend Voice Lab save/preview/test-play payloads and voice metadata handling for VoxCPM2 mode/style settings.
- Extend call speech payload handling only as needed to pass VoxCPM2 mode/style metadata while preserving existing call semantics.
- Extend UI fallback engine lists, labels, and TypeScript types so VoxCPM2 renders correctly when backend metadata is unavailable or degraded.
- Extend the TTS scenario matrix and manual quality artifacts for VoxCPM2 rows and generated samples.

</code_context>

<specifics>
## Specific Ideas

- VoxCPM2 is allowed to compete seriously, including against current defaults, but only after RayMe-specific evidence proves a call-feel win.
- VoxCPM2's style controls are part of this phase, but only inside VoxCPM2-specific voice UI so current engines remain unchanged.
- Missing transcript should not block VoxCPM2, because reference-only mode is in scope; it should warn and continue.
- A call-flow failure is not the same as a hard runtime gate failure: call-flow failure blocks promotion but keeps VoxCPM2 visible and available, while hard gate failures make it visible but unavailable.
- Official docs indicate VoxCPM2 uses 48 kHz output; downstream implementation must not hard-code older VoxCPM sample rates.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 7 scope.

</deferred>

---

*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Context gathered: 2026-05-10*
