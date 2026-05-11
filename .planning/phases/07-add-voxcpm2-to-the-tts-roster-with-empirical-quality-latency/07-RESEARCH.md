# Phase 7: Add VoxCPM2 to the TTS roster with empirical quality, latency, VRAM, and call-flow evaluations - Research

**Researched:** 2026-05-11
**Domain:** RayMe TTS engine integration, VoxCPM2 runtime evaluation, RTX 3060 call-flow validation
**Confidence:** HIGH for codebase integration surfaces and official VoxCPM2 API shape; MEDIUM for runtime feasibility until OMEN install/load benchmarks run

<user_constraints>
## User Constraints (from CONTEXT.md)

Source: `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-CONTEXT.md` [VERIFIED: 07-CONTEXT.md]

### Locked Decisions

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

### Claude's Discretion
- Exact VoxCPM2 engine id, label wording, caveat chip wording, and unavailable reason taxonomy.
- Exact benchmark filenames and summary artifact names, as long as generated WAVs and manual CSV evidence remain linked.
- Exact scoring rubric weights, as long as the required quality dimensions and promotion gates above are preserved.
- Exact runtime choice after investigation, provided one public AI backend API is preserved and evidence supports the choice.
- Exact UI placement and field names for VoxCPM2 mode/style metadata, as long as non-VoxCPM2 engines are not made noisier.

### Deferred Ideas (OUT OF SCOPE)

None - discussion stayed within Phase 7 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-02 | AI backend targets one RTX 3060 with STT, VAD, and one resident TTS engine coexisting. [VERIFIED: .planning/REQUIREMENTS.md] | VoxCPM2 must use one-hot residency, `device="cuda"`, and an 11 GB soak with Whisper + Silero + one TTS engine before promotion. [VERIFIED: ai-backend/app/models/model_manager.py, ai-backend/app/models/gpu_runtime.py, VoxCPM docs] |
| REQ-20 | Voice Lab accepts short WAV/MP3/FLAC samples and warns outside the 6-15 s envelope. [VERIFIED: .planning/REQUIREMENTS.md] | Existing sample validation and asset-id storage can be reused for VoxCPM2 prompt/reference audio. [VERIFIED: web-ui/server/app/domain/voice_assets.py, web-ui/server/tests/test_voices.py] |
| REQ-21 | Uploaded samples are transcribed into editable reference transcripts. [VERIFIED: .planning/REQUIREMENTS.md] | VoxCPM2 transcript-guided cloning maps directly to stored `reference_transcript`; missing transcript falls back to reference-only with a warning. [VERIFIED: 07-CONTEXT.md, VoxCPM API docs] |
| REQ-22 | Voice save captures name, engine, sample path, transcript, timestamps, and selected TTS engine. [VERIFIED: .planning/REQUIREMENTS.md] | `Voice.metadata_json` already exists and should hold VoxCPM2 mode/style/settings without schema churn. [VERIFIED: web-ui/server/app/storage/models.py] |
| REQ-23 | Voice Library supports list, rename, delete, and test-play. [VERIFIED: .planning/REQUIREMENTS.md] | Test-play already passes saved sample bytes and transcript to AI backend; extend payload metadata for VoxCPM2 options. [VERIFIED: web-ui/server/app/domain/voice_service.py] |
| REQ-24 | Deleting referenced voices must not leave dangling references. [VERIFIED: .planning/REQUIREMENTS.md] | VoxCPM2 should not change stable voice IDs or soft-delete behavior. [VERIFIED: web-ui/server/app/domain/voice_service.py, web-ui/server/tests/test_voices.py] |
| REQ-41 | Calls are full-duplex. [VERIFIED: .planning/REQUIREMENTS.md] | VoxCPM2 evaluation must use real call playback, not only offline WAV generation, because call state and audio enqueue affect call feel. [VERIFIED: web-ui/server/app/api/calls.py, ai-backend/app/call/session.py] |
| REQ-42 | VAD-driven barge-in cancels TTS playback and LLM generation. [VERIFIED: .planning/REQUIREMENTS.md] | VoxCPM2 call tests must prove engine-scoped TTS failure/cancel behavior does not regress interrupt handling. [VERIFIED: ai-backend/app/call/session.py, ai-backend/tests/test_call_session.py] |
| REQ-45 | Every engine uses shared chunked TTS playback and logs TTFA, total stitched playback, and inter-chunk gaps. [VERIFIED: .planning/REQUIREMENTS.md] | Extend the existing scenario matrix planner with `voxcpm2` limits and rows before promotion. [VERIFIED: .planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py] |
| REQ-62 | AI call audio is saved per turn by default. [VERIFIED: .planning/REQUIREMENTS.md] | VoxCPM2 call-flow evaluation must confirm generated call audio reaches the normal saved AI speech path. [VERIFIED: web-ui/server/app/api/calls.py] |
| REQ-80 | Settings exposes default TTS engine and AI backend status. [VERIFIED: .planning/REQUIREMENTS.md] | Settings fallback/status types must include VoxCPM2 even when backend metadata is degraded. [VERIFIED: web-ui/client/src/lib/api/types.ts, web-ui/client/src/routes/voice-lab/+page.svelte] |
| REQ-A3 | v1 is English-only, with Spanish-accented English as a quality bar. [VERIFIED: .planning/REQUIREMENTS.md] | VoxCPM2's 30-language support does not expand Phase 7 scope; quality scoring should focus English and the builder's accented-English sample. [VERIFIED: 07-CONTEXT.md, Hugging Face model card] |
</phase_requirements>

## Summary

Phase 7 should plan VoxCPM2 as a real roster integration with an evidence gate, not as a detached spike. [VERIFIED: 07-CONTEXT.md] The existing RayMe architecture already has the right high-level extension points: metadata-driven TTS registry, optional import-gated adapters, one-hot resident TTS switching, health/unavailable metadata, Web UI voice metadata, and preview/test-play/call routes that forward reference audio plus transcript. [VERIFIED: ai-backend/app/models/tts_registry.py, ai-backend/app/models/model_manager.py, web-ui/server/app/domain/voice_service.py, web-ui/server/app/api/calls.py]

The first implementation path to plan is an in-process `voxcpm==2.0.2` adapter behind the AI backend optional `tts` extra, using `VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, device="cuda")`, RayMe temp-file handling for uploaded reference bytes, and explicit CUDA guards so VoxCPM's documented `cuda -> mps -> cpu` automatic fallback cannot mask a production regression. [VERIFIED: PyPI JSON 2026-05-11, VoxCPM installation/API docs, ai-backend/app/models/gpu_runtime.py] Streaming (`generate_streaming`) must be benchmarked in the same phase, but planner should not assume it improves RayMe call feel until call-path TTFA and chunk enqueue behavior are measured. [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html]

NanoVLLM-VoxCPM and vLLM-Omni are relevant but should not be the first RayMe implementation path. [VERIFIED: VoxCPM deployment docs + codebase constraints] Both are Linux/GPU serving paths with extra operational complexity, while RayMe's current target runtime is OMEN Windows with one public AI backend API and an existing import-gated adapter pattern. [VERIFIED: .planning/OPERATING-NOTES.md, ssh rayme-pmpg probes, VoxCPM NanoVLLM/vLLM-Omni docs] Plan them as second-wave benchmark or fallback paths only after the standard API install/load/call-flow evidence shows a concrete reason. [VERIFIED: ai-backend/docs/RUNTIME-EVIDENCE.md]

**Primary recommendation:** Add `voxcpm2` as a metadata-visible, optional-runtime engine first, then promote or caveat it only after RayMe-shaped evidence proves quality, warm call latency, VRAM, generated samples, and real call-flow behavior against F5. [VERIFIED: 07-CONTEXT.md + codebase inspection]

## Project Constraints (from AGENTS.md and Operating Notes)

- OMEN deployment must use `scripts/deploy-omen.sh`; do not create ad-hoc deployment scripts, scheduled tasks, or launcher files outside that script. [VERIFIED: AGENTS.md, .planning/OPERATING-NOTES.md]
- Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` must point only to canonical `.cmd` files generated by `deploy-omen.sh`. [VERIFIED: AGENTS.md]
- The real GPU host is `OMEN-PC` via `ssh rayme-pmpg`, with canonical checkout `C:\Users\pmpg\rayme\RayMe`. [VERIFIED: .planning/OPERATING-NOTES.md, ssh rayme-pmpg git probe]
- CPU fallback for production STT/TTS/VAD/model runtime is a regression; fix CUDA, drivers, wheels, PATH, or model placement instead. [VERIFIED: .planning/OPERATING-NOTES.md, ai-backend/app/models/gpu_runtime.py]
- Runtime evidence must preserve one public AI backend API; split runtime, WSL, Docker, subprocess, or per-engine service designs require logged one-runtime failure evidence first. [VERIFIED: ai-backend/docs/RUNTIME-EVIDENCE.md]
- Browser/Web UI callers must not learn per-engine runtime internals. [VERIFIED: ai-backend/docs/RUNTIME-EVIDENCE.md, 07-CONTEXT.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| VoxCPM2 model load, CUDA guard, and synthesis | AI / Backend | Database / Storage | AI backend owns transient model runtime and one-hot TTS residency; Web UI storage provides the saved sample/transcript bytes. [VERIFIED: ai-backend/app/models/model_manager.py, web-ui/server/app/domain/voice_service.py] |
| TTS roster metadata and unavailable status | AI / Backend | Browser / Client fallback | Backend metadata is canonical, but client fallback lists/types must include VoxCPM2 for degraded/disconnected states. [VERIFIED: 07-CONTEXT.md, web-ui/client/src/routes/voice-lab/+page.svelte] |
| Voice-level VoxCPM2 mode/style preferences | Frontend Server | Browser / Client | Durable voice metadata lives in the Web UI server; browser controls edit bounded metadata without knowing runtime internals. [VERIFIED: web-ui/server/app/storage/models.py, web-ui/client/src/routes/voice-lab/+page.svelte] |
| Preview and test-play | Frontend Server | AI / Backend | Web UI routes own voice asset lookup and pass a single synthesis payload to AI backend. [VERIFIED: web-ui/server/app/api/voices.py, web-ui/server/app/domain/voice_service.py] |
| Real call playback | Frontend Server + AI / Backend | Browser / Client | Web UI call SSE owns LLM turn orchestration and AI backend `/webrtc/.../speak` owns TTS enqueue to the outbound audio track. [VERIFIED: web-ui/server/app/api/calls.py, ai-backend/app/api/webrtc.py, ai-backend/app/call/session.py] |
| Benchmark and promotion evidence | Planning artifacts + AI / Backend probes | Browser / Client live checks | Scenario matrix, WAV outputs, manual CSV, and live call evidence must be saved under the phase directory before promotion. [VERIFIED: 07-CONTEXT.md, .planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py] |
| OMEN deployment verification | Scripts / Operations | AI / Backend | `scripts/deploy-omen.sh` is the only deployment path; live GPU evidence must run on OMEN. [VERIFIED: AGENTS.md, .planning/OPERATING-NOTES.md] |

## Standard Stack

### Core

| Library / Asset | Version | Purpose | Why Standard |
|-----------------|---------|---------|--------------|
| `voxcpm` | `2.0.2`, uploaded 2026-04-08, `requires_python >=3.10` | Standard VoxCPM2 Python API and CLI. [VERIFIED: PyPI JSON 2026-05-11] | Official package exposes `VoxCPM.from_pretrained`, `generate`, and `generate_streaming`, and matches RayMe's import-gated adapter pattern. [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html] |
| `openbmb/VoxCPM2` | HF SHA `bffb3df5a29440629464e5e839f4d214c8714c3d`, last modified 2026-04-16 | Model weights for VoxCPM2. [VERIFIED: Hugging Face API 2026-05-11] | Official model card lists Apache-2.0 license, 2B parameters, 48 kHz output, ~8 GB VRAM, TTS pipeline, and VoxCPM usage. [CITED: https://huggingface.co/openbmb/VoxCPM2] |
| CUDA PyTorch / torchaudio | VoxCPM requires PyTorch >=2.5.0; OMEN venv currently reports `torch 2.10.0+cu126`, CUDA `12.6`, `torch.cuda.is_available() == True`. | Required GPU runtime for standard VoxCPM2 adapter. [VERIFIED: VoxCPM installation docs, ssh rayme-pmpg torch probe] | RayMe production policy rejects CPU fallback and existing GPU guards already enforce CUDA PyTorch for F5. [VERIFIED: ai-backend/app/models/gpu_runtime.py] |
| `soundfile` | RayMe pins `0.13.1` in `ai-backend/pyproject.toml`. | Write VoxCPM waveform arrays to WAV bytes with the model-reported sample rate. [VERIFIED: ai-backend/pyproject.toml, ai-backend/app/models/tts_f5.py] | Existing F5 adapter already uses `soundfile` for WAV output, avoiding a custom encoder. [VERIFIED: ai-backend/app/models/tts_f5.py] |
| `numpy` | RayMe pins `2.2.6` in `ai-backend/pyproject.toml`. | Concatenate/normalize waveform arrays from `generate_streaming`. [VERIFIED: ai-backend/pyproject.toml, VoxCPM API docs] | Official streaming examples return NumPy chunks, and RayMe scenario harness already uses NumPy for audio metrics. [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html; VERIFIED: tts_scenario_matrix.py] |

### Supporting

| Library / Asset | Version | Purpose | When to Use |
|-----------------|---------|---------|-------------|
| `nano-vllm-voxcpm` | `2.0.1`, uploaded 2026-04-22, `requires_python >=3.10,<3.13` | Accelerated VoxCPM serving with streaming and scheduler support. [VERIFIED: PyPI JSON 2026-05-11] | Benchmark only after standard Python API evidence shows latency or throughput is inadequate; it is Linux + CUDA + Triton + FlashAttention and no CPU-only execution. [CITED: https://voxcpm.readthedocs.io/en/latest/deployment/nanovllm_voxcpm.html] |
| vLLM-Omni | Docs pin example `vllm==0.19.0` plus source install from `vllm-project/vllm-omni`. | OpenAI-compatible `/v1/audio/speech` serving for VoxCPM2. [CITED: https://voxcpm.readthedocs.io/en/latest/deployment/vllm_omni.html] | Treat as a later serving benchmark path for concurrent/multi-tenant needs, not first integration for single-user RayMe. [VERIFIED: VoxCPM docs + RayMe topology constraints] |
| Existing scenario matrix harness | Local project code, no package version | Shared chunk planner, TTFA/RTF/stitch-gap metrics, WAV output rows. [VERIFIED: .planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py] | Extend with VoxCPM2 rows before any roster promotion. [VERIFIED: 07-CONTEXT.md] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Standard in-process `voxcpm` adapter | NanoVLLM-VoxCPM | NanoVLLM has streaming/concurrency and lower advertised RTX 4090 RTF, but it is Linux GPU-centric and requires local checkpoint layout, Triton, and FlashAttention. [CITED: https://voxcpm.readthedocs.io/en/latest/deployment/nanovllm_voxcpm.html] |
| Standard in-process `voxcpm` adapter | vLLM-Omni server | vLLM-Omni offers OpenAI-compatible serving and continuous batching, but adds a separate rapidly evolving serving stack. [CITED: https://voxcpm.readthedocs.io/en/latest/deployment/vllm_omni.html] |
| `generate()` whole WAV | `generate_streaming()` chunks | Streaming may improve TTFA, but RayMe's current code path enqueues WAV after synthesis; the planner must add/test a chunk-consumption contract before claiming call-feel gains. [VERIFIED: ai-backend/app/call/session.py; CITED: VoxCPM API docs] |
| Windows in-process runtime | WSL/subprocess/server-backed runtime | Allowed only after one-runtime evidence fails and while preserving the same RayMe AI backend API. [VERIFIED: 07-CONTEXT.md, ai-backend/docs/RUNTIME-EVIDENCE.md] |

**Installation:**

```bash
# Plan should add VoxCPM behind the existing AI backend optional TTS extra.
uv add --project ai-backend --optional tts "voxcpm==2.0.2"
uv sync --project ai-backend --extra tts
```

Version verification: `voxcpm==2.0.2` and `nano-vllm-voxcpm==2.0.1` were verified from PyPI JSON on 2026-05-11. [VERIFIED: PyPI JSON 2026-05-11] No new browser package is required for the initial plan. [VERIFIED: codebase inspection]

## Architecture Patterns

### System Architecture Diagram

```text
Voice sample upload
  -> Web UI server validates/stores asset-id blob
  -> STT transcribes editable reference transcript
  -> Voice save persists default_engine + metadata_json.engine_settings.voxcpm2
  -> Preview/test-play/call reads same voice sample + transcript + VoxCPM2 settings
  -> Web UI server calls existing RayMe AI backend API
  -> AI backend ModelManager switches one resident TTS engine
  -> VoxCPM2 adapter writes reference bytes to temp file
  -> VoxCPM2 generate/generate_streaming runs on CUDA
  -> WAV bytes + sample_rate return through normal RayMe synthesis response
  -> Preview audio, library test-play, or WebRTC outbound audio track

Decision points:
  - Missing transcript?
      -> reference-only mode + warning, not a hard failure
  - Mode is transcript-guided?
      -> prompt_wav_path + prompt_text + reference_wav_path
  - VoxCPM2 load/synthesis fails?
      -> mark VoxCPM2 unavailable/caveated with sanitized reason; keep other engines available
  - Evidence beats F5 and passes quality/VRAM/call flow?
      -> promote candidate; otherwise keep visible with caveats or unavailable reason
```

Diagram source: existing RayMe call/voice/API flow plus VoxCPM2 API semantics. [VERIFIED: web-ui/server/app/domain/voice_service.py, ai-backend/app/models/model_manager.py, ai-backend/app/call/session.py; CITED: VoxCPM API docs]

### Recommended Project Structure

```text
ai-backend/
├── app/models/tts_voxcpm2.py          # VoxCPM2 ImportGatedTtsAdapter implementation
├── app/models/tts_registry.py         # add voxcpm2 metadata, expected id, default adapter builder
├── app/models/engine_metadata.py      # health/model-manager metadata mirror
├── app/api/tts.py                     # accept bounded VoxCPM2 engine options
├── app/api/webrtc.py                  # pass bounded VoxCPM2 engine options through speak route
└── tests/test_tts_voxcpm2.py          # adapter option mapping, CUDA guard, sanitized failure contracts

web-ui/server/
├── app/api/voices.py                  # preview/save/test-play payload schema for engine settings
├── app/domain/voice_service.py        # preserve per-engine metadata and pass it to AI backend
├── app/api/calls.py                   # call voice_reference includes VoxCPM2 settings
└── tests/test_voices.py, test_calls.py

web-ui/client/
├── src/routes/voice-lab/+page.svelte
├── src/lib/components/voice/TtsEnginePicker.svelte
├── src/lib/components/voice/VoxCpm2Controls.svelte
├── src/lib/components/voice/VoiceAssignmentSelect.svelte
├── src/lib/api/types.ts
└── tests/unit + tests/e2e voice-lab coverage

.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/
├── results/voxcpm2-scenario-matrix.json
├── results/voxcpm2-scenario-matrix.csv
├── results/voxcpm2-vram-soak.json
├── results/voxcpm2-call-flow.json
├── results/audio/*.wav
└── MANUAL-QUALITY.csv
```

Structure source: current repository layout and Phase 7 evidence requirements. [VERIFIED: codebase inspection, 07-CONTEXT.md]

### Pattern 1: Metadata-Visible Optional Runtime

**What:** Add VoxCPM2 to the full roster metadata even when the runtime package is absent. [VERIFIED: ai-backend/app/models/tts_registry.py]

**When to use:** Use for every optional TTS engine so Voice Lab and Settings can render unavailable engines with caveats. [VERIFIED: web-ui/client/src/routes/voice-lab/+page.svelte]

**Example:**

```python
# Source pattern: ai-backend/app/models/tts_registry.py [VERIFIED]
TtsEngineMetadata(
    id="voxcpm2",
    label="VoxCPM2",
    code_license="Apache-2.0",
    model_license="Apache-2.0",
    caveat_chips=["Candidate", "48 kHz", "RTX 3060 gate pending"],
    runtime_evidence="Phase 7 pending: install, TTFA/RTF, VRAM, quality, and call-flow evidence required.",
    requires_transcript=False,
    supports_streaming=True,
    quality_notes="Supports reference-only and transcript-guided cloning; promotion requires RayMe evidence.",
)
```

### Pattern 2: CUDA-Forced VoxCPM2 Adapter

**What:** Use the official Python API but force CUDA and run the existing RayMe CUDA guard before loading. [VERIFIED: ai-backend/app/models/gpu_runtime.py; CITED: VoxCPM installation/API docs]

**When to use:** Use for the first implementation path because it preserves one process, one model manager, and one public AI backend API. [VERIFIED: ai-backend/docs/RUNTIME-EVIDENCE.md]

**Example:**

```python
# Source pattern: ai-backend/app/models/tts_f5.py + VoxCPM API docs [VERIFIED/CITED]
from voxcpm import VoxCPM

require_torch_cuda_runtime("VoxCPM2")
self._runtime = VoxCPM.from_pretrained(
    "openbmb/VoxCPM2",
    load_denoiser=False,
    device="cuda",
    cache_dir=self._cache_dir,
)
```

### Pattern 3: Mode Mapping from RayMe Voice Metadata

**What:** Store VoxCPM2-specific options under a per-engine metadata key and ignore that key for other engines. [VERIFIED: 07-CONTEXT.md, web-ui/server/app/storage/models.py]

**When to use:** Use for preview, test-play, and call synthesis so a saved voice behaves consistently. [VERIFIED: 07-CONTEXT.md]

**Example:**

```json
{
  "engine_settings": {
    "voxcpm2": {
      "cloning_mode": "transcript_guided",
      "style_control": "warm, natural, slightly slower",
      "cfg_value": 2.0,
      "inference_timesteps": 10,
      "normalize": false,
      "denoise": false
    }
  }
}
```

### Pattern 4: Adapter Mapping for Reference-Only vs Transcript-Guided

**What:** Convert RayMe's stored sample bytes to a temp audio file because the official VoxCPM API accepts file paths for prompt/reference audio. [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html; VERIFIED: ai-backend/app/models/tts_f5.py]

**When to use:** Use for every preview, test-play, and call synthesis request. [VERIFIED: web-ui/server/app/domain/voice_service.py, web-ui/server/app/api/calls.py]

**Example:**

```python
# Source: VoxCPM API docs + existing F5 temp-file pattern [CITED/VERIFIED]
if cloning_mode == "transcript_guided" and reference_transcript:
    wav = model.generate(
        text=styled_text,
        prompt_wav_path=str(reference_path),
        prompt_text=reference_transcript,
        reference_wav_path=str(reference_path),
        cfg_value=cfg_value,
        inference_timesteps=inference_timesteps,
        normalize=normalize,
        denoise=denoise,
    )
else:
    wav = model.generate(
        text=styled_text,
        reference_wav_path=str(reference_path),
        cfg_value=cfg_value,
        inference_timesteps=inference_timesteps,
        normalize=normalize,
        denoise=denoise,
    )
```

### Pattern 5: Evidence Before Promotion

**What:** Treat benchmark outputs as phase artifacts, not console-only notes. [VERIFIED: 07-CONTEXT.md, .planning/OPERATING-NOTES.md]

**When to use:** Use before changing default/recommended engine labels. [VERIFIED: 07-CONTEXT.md]

**Minimum evidence set:** scenario matrix JSON/CSV, generated WAVs, manual quality CSV, VRAM soak JSON, preview/test-play proof, real call-flow proof, deployment command/evidence path. [VERIFIED: 07-CONTEXT.md, .planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/MANUAL-QUALITY.csv]

### Anti-Patterns to Avoid

- **Using VoxCPM `device="auto"` in production:** Official docs say auto can fall back from CUDA to MPS/CPU, which violates RayMe production policy. [CITED: VoxCPM installation docs; VERIFIED: .planning/OPERATING-NOTES.md]
- **Adding `/voxcpm2/*` browser or Web UI routes:** Phase 7 requires one public AI backend API and canonical backend metadata. [VERIFIED: 07-CONTEXT.md, ai-backend/docs/RUNTIME-EVIDENCE.md]
- **Promoting from public RTX 4090 RTF claims:** Official RTF numbers are not RTX 3060 RayMe call-flow evidence. [CITED: Hugging Face model card; VERIFIED: 07-CONTEXT.md]
- **Hardcoding output sample rate:** Official docs and model card say VoxCPM2 outputs 48 kHz and examples use `model.tts_model.sample_rate`; adapter must return the actual model sample rate. [CITED: Hugging Face model card, VoxCPM quickstart]
- **Disabling VoxCPM2 entirely after call-flow failure:** Context says call-flow failure blocks promotion but keeps VoxCPM2 visible and available if standalone runtime works. [VERIFIED: 07-CONTEXT.md]
- **Letting VoxCPM2 errors poison other engines:** Existing model-manager policy is engine-scoped unavailable state. [VERIFIED: ai-backend/app/models/model_manager.py]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| VoxCPM2 model inference | Custom MiniCPM/AudioVAE/DiT inference | `voxcpm` official API | Official package owns architecture detection, generation, streaming, denoiser, and LoRA hooks. [CITED: VoxCPM API/changelog docs] |
| WAV writing and sample-rate handling | Manual RIFF byte construction | `soundfile` + `model.tts_model.sample_rate` | Existing F5 adapter and official examples use soundfile; manual WAV handling risks wrong sample rate. [VERIFIED: ai-backend/app/models/tts_f5.py; CITED: VoxCPM quickstart] |
| Runtime fallback logic | Silent CPU fallback or ad-hoc device switching | `require_torch_cuda_runtime` + explicit `device="cuda"` | RayMe rejects production CPU fallback. [VERIFIED: ai-backend/app/models/gpu_runtime.py, .planning/OPERATING-NOTES.md] |
| TTS chunk planning | New VoxCPM2-only splitter | Existing scenario matrix shared chunk planner | REQ-45 requires shared planner across engines. [VERIFIED: .planning/REQUIREMENTS.md, tts_scenario_matrix.py] |
| Engine status/error sanitization | Raw exception text in health/API responses | Existing fixed public codes and unavailable reasons | Existing tests forbid paths, tracebacks, and CUDA OOM text in public payloads. [VERIFIED: ai-backend/tests/test_model_manager.py, ai-backend/tests/test_tts_registry.py] |
| Voice metadata storage | New VoxCPM2 tables for first pass | Existing `Voice.metadata_json.engine_settings.voxcpm2` | Durable voice metadata already stores per-engine settings and avoids migration risk. [VERIFIED: web-ui/server/app/storage/models.py, web-ui/server/app/domain/voice_service.py] |
| Call transport | Separate VoxCPM2 websocket or audio server exposed to browser | Existing `/api/calls` and AI backend `/webrtc/.../speak` flow | One public API and call FSM are already established. [VERIFIED: web-ui/server/app/api/calls.py, ai-backend/app/api/webrtc.py] |
| VRAM metrics | Hand-parsed process guesses | `pynvml` health probe and `nvidia-smi` evidence | Existing health exposes VRAM used/headroom and operating notes require `nvidia-smi` capture. [VERIFIED: ai-backend/app/models/model_manager.py, ai-backend/docs/RUNTIME-EVIDENCE.md] |

**Key insight:** VoxCPM2 is deceptively easy to call once, but RayMe's hard part is proving the complete phone-call path: resident GPU fit, first audible chunk, stitched playback, voice quality, barge-in safety, and stable degraded behavior. [VERIFIED: 07-CONTEXT.md, codebase inspection]

## Common Pitfalls

### Pitfall 1: Silent CPU Fallback
**What goes wrong:** VoxCPM loads on CPU/MPS because `device="auto"` is used, and the phase records invalid latency/VRAM evidence. [CITED: VoxCPM installation docs]
**Why it happens:** Official `auto` device selection prefers CUDA but can fall back. [CITED: https://voxcpm.readthedocs.io/en/latest/installation.html]
**How to avoid:** Force `device="cuda"` and call `require_torch_cuda_runtime("VoxCPM2")` before loading. [VERIFIED: ai-backend/app/models/gpu_runtime.py]
**Warning signs:** Health shows low/no VRAM change, slow synthesis, or missing CUDA torch metadata. [VERIFIED: ai-backend/docs/STT-GPU-RUNTIME.md]

### Pitfall 2: Wrong Output Sample Rate
**What goes wrong:** Adapter returns 16 kHz or 24 kHz while VoxCPM2 outputs 48 kHz, causing playback/metrics errors. [CITED: Hugging Face model card]
**Why it happens:** One Hugging Face usage snippet writes `16000`, while official quickstart/API examples use `model.tts_model.sample_rate` and the model card states 48 kHz output. [CITED: https://huggingface.co/openbmb/VoxCPM2, https://voxcpm.readthedocs.io/en/latest/quickstart.html]
**How to avoid:** Always return `int(model.tts_model.sample_rate)` in `TtsSynthesisOutput`. [VERIFIED: ai-backend/app/models/tts_registry.py]
**Warning signs:** Generated audio duration is wrong, call playout timing drifts, or scenario RTF is impossible. [VERIFIED: tts_scenario_matrix.py]

### Pitfall 3: Treating Streaming API as Call-Flow Streaming
**What goes wrong:** Research claims TTFA wins from `generate_streaming`, but production still waits for a collected WAV before enqueue. [VERIFIED: ai-backend/app/call/session.py]
**Why it happens:** Existing adapter protocol returns `TtsSynthesisOutput`, not a chunk generator. [VERIFIED: ai-backend/app/models/tts_registry.py]
**How to avoid:** Add a tested optional streaming/chunk adapter contract or limit the claim to benchmark-only rows. [VERIFIED: codebase inspection]
**Warning signs:** Scenario matrix shows streaming chunks but `/webrtc/.../speak` emits `ai_audio_started` only after full synthesis. [VERIFIED: ai-backend/app/call/session.py]

### Pitfall 4: Ignoring Style-Control and Prompt-Text Ambiguity
**What goes wrong:** Style controls are saved but not applied consistently, or transcript-guided mode errors/degrades when style prefix and prompt text are combined. [CITED: VoxCPM API/CLI docs]
**Why it happens:** Official CLI docs say `--control` cannot be used together with `--prompt-text`, while Python style control is represented as a parenthesized text prefix. [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html]
**How to avoid:** Plan an empirical contract for style + transcript-guided synthesis; do not silently ignore style without a visible caveat if the combination fails. [VERIFIED: 07-CONTEXT.md]
**Warning signs:** Reference-only style works but transcript-guided mode returns validation errors or poor quality. [CITED: VoxCPM API docs]

### Pitfall 5: Hard-Coded Six-Engine Lists
**What goes wrong:** VoxCPM2 appears in backend health but disappears from Voice Lab, Settings, assignment labels, or disconnected fallbacks. [VERIFIED: web-ui/client/src/routes/voice-lab/+page.svelte, web-ui/client/src/lib/components/voice/VoiceAssignmentSelect.svelte]
**Why it happens:** The code still has explicit six-engine `EXPECTED_ENGINE_IDS`, fallback arrays, type unions, and label switches. [VERIFIED: ai-backend/app/models/tts_registry.py, web-ui/client/src/lib/api/types.ts]
**How to avoid:** Plan a full roster update across backend, Web UI server, client fallback metadata, and tests. [VERIFIED: codebase inspection]
**Warning signs:** Unit tests pass with backend metadata mocked but disconnected UI omits VoxCPM2. [VERIFIED: web-ui/client/tests/unit/voice-lab.test.ts, web-ui/client/tests/e2e/voice-lab.spec.ts]

### Pitfall 6: Evidence Artifacts Without Manual Quality
**What goes wrong:** Low latency promotes an engine with sample leakage, mumbling, poor accent preservation, or bad prosody. [VERIFIED: .planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/MANUAL-QUALITY.csv]
**Why it happens:** Prior TTS spike showed latency alone is insufficient. [VERIFIED: .planning/STATE.md, spike CSV]
**How to avoid:** Require manual quality CSV rows and generated WAV links for each VoxCPM2 scenario/mode before promotion. [VERIFIED: 07-CONTEXT.md]
**Warning signs:** Matrix has TTFA/RTF but no listened WAV scores. [VERIFIED: 07-CONTEXT.md]

## Code Examples

Verified patterns from official sources and RayMe code:

### Standard VoxCPM2 Load and Generate

```python
# Source: VoxCPM API docs [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html]
from voxcpm import VoxCPM

model = VoxCPM.from_pretrained(
    "openbmb/VoxCPM2",
    load_denoiser=False,
    device="cuda",
)
wav = model.generate(
    text="RayMe should measure this on the RTX 3060.",
    reference_wav_path="speaker.wav",
    cfg_value=2.0,
    inference_timesteps=10,
)
sample_rate = int(model.tts_model.sample_rate)
```

### Streaming Benchmark Shape

```python
# Source: VoxCPM API docs [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html]
chunks = []
first_chunk_ms = None
started = time.perf_counter()
for chunk in model.generate_streaming(text=text, reference_wav_path=reference_path):
    if first_chunk_ms is None:
        first_chunk_ms = (time.perf_counter() - started) * 1000
    chunks.append(chunk)
wav = np.concatenate(chunks)
```

### RayMe Adapter Temp-File Pattern

```python
# Source: existing F5 adapter temp-file pattern [VERIFIED: ai-backend/app/models/tts_f5.py]
with tempfile.TemporaryDirectory(prefix="rayme-voxcpm2-") as tmp_dir:
    reference_path = Path(tmp_dir) / "reference.wav"
    reference_path.write_bytes(request.reference_audio)
    wav = model.generate(
        text=styled_text,
        reference_wav_path=str(reference_path),
    )
```

### Sanitized Engine Failure

```python
# Source: existing model-manager and synthesis route pattern [VERIFIED]
try:
    manager.switch_tts_engine("voxcpm2")
    result = adapter.synthesize(request)
except Exception as exc:
    manager._mark_unavailable("voxcpm2", "engine synthesis failed")
    raise HTTPException(
        status_code=502,
        detail={"code": "tts_failed", "message": "Synthesis failed", "engine_id": "voxcpm2"},
    ) from exc
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| VoxCPM 0.5B/1.5 continuation-only cloning | VoxCPM2 2B with reference-only cloning, transcript-guided cloning, voice design, and 48 kHz output | VoxCPM2 release news 2026-04 [CITED: GitHub README/HF card] | RayMe can support missing-transcript voices without blocking, but must measure 2B VRAM on RTX 3060. [VERIFIED: 07-CONTEXT.md] |
| Flat legacy `voxcpm --text` CLI | `voxcpm design`, `voxcpm clone`, and `voxcpm batch` subcommands | Changelog documents VoxCPM2-first CLI rewrite [CITED: VoxCPM changelog] | Planner should use Python API for integration, but CLI probes should use subcommands if needed. [CITED: VoxCPM API docs] |
| Whole-request non-streaming TTS | `generate_streaming`, NanoVLLM streaming, vLLM-Omni streaming serving | VoxCPM2 docs list streaming and serving options [CITED: VoxCPM API/deployment docs] | Phase 7 must benchmark streaming, but call path changes require RayMe contracts before production TTFA claims. [VERIFIED: ai-backend/app/call/session.py] |
| Implicit device auto-selection | Explicit CUDA runtime for RayMe production | Existing RayMe runtime policy from Phase 2 [VERIFIED: .planning/OPERATING-NOTES.md] | VoxCPM2 adapter must reject CPU/MPS in production even though official package supports them. [CITED: VoxCPM installation docs] |

**Deprecated/outdated:**
- Legacy flat CLI usage still works but is deprecated in official docs; prefer subcommands for CLI probes. [CITED: https://voxcpm.readthedocs.io/en/latest/reference/api.html]
- Assuming VoxCPM sample rate is 16 kHz is outdated for VoxCPM2 output; official model details list 48 kHz output. [CITED: https://huggingface.co/openbmb/VoxCPM2]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No user confirmation is needed for the preliminary engine id `voxcpm2` because context leaves exact id wording to Claude's discretion. [ASSUMED] | Standard Stack / Architecture Patterns | If the user prefers a different id, tests and persisted metadata keys would need renaming before implementation. |

## Open Questions (RESOLVED)

The research unknowns below remain empirical runtime facts, but they are no longer planning blockers. Each is converted into an explicit Phase 7 evidence gate so executors measure the fact instead of assuming it.

1. **`voxcpm==2.0.2` install/load on OMEN Windows AI venv**
   - Known baseline: OMEN has Python 3.10.8, CUDA torch `2.10.0+cu126`, RTX 3060 12 GB, and `voxcpm` is not currently installed. [VERIFIED: ssh rayme-pmpg probes]
   - Evidence gate: Plan 07-10 runs `scripts/deploy-omen.sh` with `RAYME_OMEN_VERIFY_VOXCPM2=1`, records `uv sync --project ai-backend --extra tts`, imports `voxcpm`, loads `VoxCPM.from_pretrained("openbmb/VoxCPM2", device="cuda")`, and saves `results/voxcpm2-runtime-smoke.json`.
   - Decision effect: install/import/load failure maps to visible unavailable or rejected-from-runtime-loading per D-04, not silent promotion.

2. **RTX 3060 11 GB production VRAM fit with Whisper + Silero + one TTS**
   - Known baseline: official model card lists VoxCPM2 VRAM around 8 GB, RayMe's STT baseline previously used about 1.7 GB, and the budget is 11 GB. [CITED: Hugging Face model card; VERIFIED: .planning/STATE.md]
   - Evidence gate: Plan 07-10 writes `results/voxcpm2-vram-soak.json` with peak/free VRAM, resident engines, STT/VAD readiness, `passed_11gb_budget`, and `cpu_fallback_detected=false`.
   - Decision effect: exceeding 11000 MB blocks promotion and availability per D-04/D-14.

3. **Style control behavior with transcript-guided cloning**
   - Known baseline: context requires style controls; official docs show parenthesized style text, while CLI notes indicate control limitations with prompt text. [VERIFIED: 07-CONTEXT.md; CITED: VoxCPM API docs]
   - Evidence gate: Plans 07-05 through 07-07 add bounded style fields and tests; Plan 07-11 generates styled VoxCPM2 samples; Plan 07-12 requires manual quality rows covering style + transcript-guided output.
   - Decision effect: degraded style behavior becomes a caveat or promotion blocker, not a hidden runtime assumption.

4. **`generate_streaming` impact on real RayMe call TTFA**
   - Known baseline: official API yields waveform chunks, but the current RayMe call path synthesizes then enqueues WAV bytes. [CITED: VoxCPM API docs; VERIFIED: ai-backend/app/call/session.py]
   - Evidence gate: Plan 07-05 creates `07-RUNTIME-PATH-DECISION.md` evaluating standard Python `generate`, `generate_streaming`, NanoVLLM-VoxCPM, and vLLM-Omni-style serving before the adapter path. Plan 07-09 records streaming rows as benchmark-only unless production call code consumes chunks. Plan 07-11 compares VoxCPM2 warm call TTFA against F5 in `voxcpm2-call-flow.json`.
   - Decision effect: streaming can only support a promotion claim if the measured call-flow artifact shows a real call-feel win through the RayMe API.

5. **Durable VoxCPM2 model/cache path on OMEN**
   - Known baseline: official API supports `cache_dir`, and context requires documenting model/cache/artifact paths while keeping large downloads out of git. [CITED: VoxCPM API docs; VERIFIED: 07-CONTEXT.md]
   - Evidence gate: Plan 07-10 records the exact model/cache path in `07-OMEN-EVIDENCE.md` and `results/voxcpm2-runtime-smoke.json`; cache contents stay outside tracked repo paths.
   - Decision effect: undocumented or git-tracked weights fail the runtime evidence gate per D-21.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| `ssh rayme-pmpg` | OMEN live GPU install/evidence | yes | user `omen-pc\pmpg` | None; this is the canonical target. [VERIFIED: ssh rayme-pmpg whoami] |
| OMEN GPU | VRAM/call-flow evidence | yes | NVIDIA GeForce RTX 3060, 12288 MiB, driver 560.94 | None for promotion. [VERIFIED: ssh rayme-pmpg nvidia-smi] |
| OMEN Python | VoxCPM runtime | yes | Python 3.10.8 in system and AI venv | None; version is within official VoxCPM range. [VERIFIED: ssh rayme-pmpg Python probe; CITED: VoxCPM installation docs] |
| OMEN CUDA PyTorch | VoxCPM runtime | yes | `torch 2.10.0+cu126`, CUDA `12.6`, CUDA available true | None; CPU torch blocks production. [VERIFIED: ssh rayme-pmpg torch probe] |
| `voxcpm` package | Standard adapter | no | PyPI latest `2.0.2` | Install behind optional `tts` extra. [VERIFIED: ssh import probe, PyPI JSON] |
| `openbmb/VoxCPM2` weights | Runtime load | not downloaded/verified in this session | HF SHA verified via API | Use `cache_dir` and evidence log; no git storage. [VERIFIED: Hugging Face API, 07-CONTEXT.md] |
| `nano-vllm-voxcpm` | Optional accelerated benchmark | no | PyPI latest `2.0.1` | Use only if standard path fails a measured gate. [VERIFIED: PyPI JSON; CITED: NanoVLLM docs] |
| vLLM-Omni | Optional server-backed benchmark | not audited locally | docs show source install with `vllm==0.19.0` | Use only as later benchmark path. [CITED: vLLM-Omni docs] |
| Local Node/npm | Client tests | yes | Node `v22.22.2`, npm `10.9.7` | None needed. [VERIFIED: local command] |
| Local `uv` | Python project sync/tests | yes | `uv 0.11.6` | Use existing uv workflow. [VERIFIED: local command] |

**Missing dependencies with no fallback:**
- `voxcpm` is missing from the OMEN AI venv and must be installed before live adapter evidence. [VERIFIED: ssh import probe]
- `openbmb/VoxCPM2` weights have not been downloaded or loaded on OMEN in this session. [VERIFIED: Hugging Face API + environment probe]

**Missing dependencies with fallback:**
- `nano-vllm-voxcpm` and vLLM-Omni are missing, but they are not first-path blockers because the recommended first path is standard `voxcpm`. [VERIFIED: docs + recommendation synthesis]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| AI backend framework | `pytest==9.0.3`, configured in `ai-backend/pyproject.toml`. [VERIFIED: ai-backend/pyproject.toml] |
| Web UI server framework | `pytest==9.0.3`, `pytest-asyncio==1.3.0`, configured in `web-ui/server/pyproject.toml`. [VERIFIED: web-ui/server/pyproject.toml] |
| Client unit framework | `vitest==4.1.5`, configured by client package scripts. [VERIFIED: web-ui/client/package.json] |
| Client E2E framework | `@playwright/test==1.59.1`. [VERIFIED: web-ui/client/package.json] |
| Quick run command | `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py -q` plus targeted Web UI/client tests. [VERIFIED: test layout] |
| Full suite command | `uv run --project ai-backend pytest -q && uv run --project web-ui/server pytest -q && npm --prefix web-ui/client run test:unit && npm --prefix web-ui/client run test:e2e`. [VERIFIED: pyproject/package scripts] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| REQ-02 | VoxCPM2 is one-hot resident, CUDA-only, engine-scoped unavailable on failure, and reports VRAM. [VERIFIED: requirements + code] | unit + live evidence | `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py ai-backend/tests/test_gpu_runtime.py -q` | Partial; add `test_tts_voxcpm2.py`. [VERIFIED: tests listing] |
| REQ-20/21/22 | Voice Lab stores VoxCPM2 mode/style metadata and transcript fallback behavior. [VERIFIED: 07-CONTEXT.md] | server + client unit/e2e | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q`; `npm --prefix web-ui/client run test:unit -- voice-lab.test.ts`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts` | Partial; add VoxCPM2-specific assertions. [VERIFIED: tests listing] |
| REQ-23 | Test-play uses saved VoxCPM2 settings and no preview gate. [VERIFIED: voice_service.py] | server + client e2e | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q` | Partial. [VERIFIED: web-ui/server/tests/test_voices.py] |
| REQ-41/42/62 | Real call playback forwards VoxCPM2 settings, enqueues audio, handles failures without breaking call recovery. [VERIFIED: call code] | server + AI backend + E2E | `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q`; `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` | Partial; add VoxCPM2 payload/failure tests. [VERIFIED: tests listing] |
| REQ-45 | Scenario matrix includes VoxCPM2 short/medium/long rows, chunk metadata, TTFA/RTF, stitch gaps, generated WAVs. [VERIFIED: requirements] | probe unit + live artifact | `python -m pytest .planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py -q` plus Phase 7 live probe command | Partial; add `voxcpm2` limits/rows. [VERIFIED: tts_scenario_matrix.py] |
| REQ-80 | Settings and fallback metadata render VoxCPM2 in degraded/disconnected states. [VERIFIED: requirements + client code] | client unit/e2e | `npm --prefix web-ui/client run test:unit -- settings.test.ts voice-lab.test.ts`; `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts settings-connection.spec.ts` | Partial; add fallback labels/types. [VERIFIED: tests listing] |
| REQ-A3 | Quality evidence focuses English and builder accented-English sample; 30-language support does not expand v1 scope. [VERIFIED: requirements + context] | manual evidence | Update Phase 7 `MANUAL-QUALITY.csv` | Missing; Wave 0 evidence artifact. [VERIFIED: 07-CONTEXT.md] |

### Sampling Rate

- **Per task commit:** Run the narrow unit test for the touched tier plus `git diff --check`. [VERIFIED: project test structure]
- **Per wave merge:** Run AI backend pytest, Web UI server pytest, client unit tests, and affected Playwright specs. [VERIFIED: pyproject/package scripts]
- **Phase gate:** Full suite green, OMEN deployed through `scripts/deploy-omen.sh`, live RTX 3060 evidence artifacts saved, and manual quality CSV completed before `/gsd-verify-work`. [VERIFIED: AGENTS.md, .planning/OPERATING-NOTES.md, 07-CONTEXT.md]

### Wave 0 Gaps

- [ ] `ai-backend/tests/test_tts_voxcpm2.py` - covers adapter load guard, option mapping, mode fallback, output sample rate, sanitized failures. [VERIFIED: no file exists]
- [ ] `web-ui/server/tests/test_voices.py` additions - covers VoxCPM2 metadata persistence, patch/update behavior, preview/test-play payloads. [VERIFIED: existing file]
- [ ] `web-ui/server/tests/test_calls.py` additions - covers call voice reference includes VoxCPM2 options. [VERIFIED: existing file]
- [ ] `web-ui/client/tests/unit/voice-lab.test.ts` and `web-ui/client/tests/e2e/voice-lab.spec.ts` additions - covers conditional VoxCPM2 controls and fallback roster. [VERIFIED: existing files]
- [ ] Phase 7 probe/evidence files - scenario matrix JSON/CSV, VRAM soak JSON, generated WAVs, call-flow evidence JSON, manual quality CSV. [VERIFIED: 07-CONTEXT.md]
- [ ] OMEN install/load smoke artifact - records `uv sync --project ai-backend --extra tts`, `import voxcpm`, `VoxCPM.from_pretrained(... device="cuda")`, model cache path, and VRAM. [VERIFIED: environment probe + RUNTIME-EVIDENCE.md]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no for Phase 7 | Project is LAN/no-auth by scope; do not add auth in this phase. [VERIFIED: .planning/PROJECT.md, .planning/REQUIREMENTS.md] |
| V3 Session Management | no direct change | Existing call/session IDs continue through current server-owned call routes. [VERIFIED: web-ui/server/app/api/calls.py] |
| V4 Access Control | yes, route boundary | Keep browser on RayMe-owned same-origin `/api/*` routes and AI backend API; do not expose NanoVLLM/vLLM servers to browser or untrusted networks. [VERIFIED: web-ui/client/tests/unit/voice-lab.test.ts; CITED: NanoVLLM docs] |
| V5 Input Validation | yes | Use Pydantic max lengths/enums for VoxCPM2 options, style text, transcripts, and numeric controls; client controls are not a trust boundary. [VERIFIED: ai-backend/app/api/tts.py, web-ui/server/app/api/voices.py] |
| V6 Cryptography | yes for supply chain/cache integrity, not custom crypto | Do not hand-roll crypto; keep model downloads in documented cache paths, pin packages, and keep secrets/TLS keys out of git. [VERIFIED: .planning/OPERATING-NOTES.md, 07-CONTEXT.md] |

### Known Threat Patterns for RayMe + VoxCPM2

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Model/runtime supply-chain drift | Tampering | Pin `voxcpm==2.0.2`, document HF model SHA/cache path, and record install evidence. [VERIFIED: PyPI JSON, HF API, 07-CONTEXT.md] |
| Untrusted audio filename/path traversal | Tampering | Existing asset-id blob storage and filename validation; never pass original filename as storage path. [VERIFIED: web-ui/server/tests/test_voices.py] |
| Raw traceback/model path disclosure | Information Disclosure | Fixed public `tts_failed`/`call_tts_failed` payloads and sanitized unavailable reasons. [VERIFIED: ai-backend/tests/test_model_manager.py, ai-backend/tests/test_tts_registry.py] |
| User style text or transcript resource exhaustion | Denial of Service | Bound style length, transcript length, synthesis text length, `cfg_value`, `inference_timesteps`, retry counts, and sample duration. [VERIFIED: existing Pydantic patterns; CITED: VoxCPM API parameters] |
| CPU fallback producing false acceptance | Spoofing/Tampering | Explicit CUDA guard and `device="cuda"`; fail visible when CUDA unavailable. [VERIFIED: ai-backend/app/models/gpu_runtime.py; CITED: VoxCPM installation docs] |
| Generated audio misuse/impersonation | Repudiation/Misuse | Keep generated evidence local, label AI-generated samples, and avoid expanding scope beyond builder-owned local voice tests. [CITED: Hugging Face model card limitations; VERIFIED: .planning/PROJECT.md single-user LAN scope] |
| Exposing optional FastAPI demo server | Information Disclosure / DoS | Do not expose NanoVLLM demo to LAN/internet; if used internally, keep RayMe AI backend as the only public API. [CITED: NanoVLLM docs; VERIFIED: 07-CONTEXT.md] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-CONTEXT.md` - locked Phase 7 decisions D-01..D-22. [VERIFIED]
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/PROJECT.md`, `.planning/OPERATING-NOTES.md`, `AGENTS.md` - RayMe constraints, runtime policy, deployment rules. [VERIFIED]
- `ai-backend/app/models/tts_registry.py`, `engine_metadata.py`, `model_manager.py`, `api/tts.py`, `api/webrtc.py`, `call/session.py` - current AI backend TTS/call extension points. [VERIFIED]
- `web-ui/server/app/api/voices.py`, `web-ui/server/app/domain/voice_service.py`, `web-ui/server/app/api/calls.py`, `web-ui/server/app/storage/models.py` - voice/call metadata and synthesis bridge. [VERIFIED]
- `web-ui/client/src/routes/voice-lab/+page.svelte`, `TtsEnginePicker.svelte`, `VoiceAssignmentSelect.svelte`, `types.ts` - client fallback roster/types/labels. [VERIFIED]
- `https://voxcpm.readthedocs.io/en/latest/installation.html` - install and device behavior. [CITED]
- `https://voxcpm.readthedocs.io/en/latest/reference/api.html` - `VoxCPM.from_pretrained`, `generate`, `generate_streaming`, prompt/reference parameters. [CITED]
- `https://voxcpm.readthedocs.io/en/latest/deployment/nanovllm_voxcpm.html` - NanoVLLM runtime constraints and features. [CITED]
- `https://voxcpm.readthedocs.io/en/latest/deployment/vllm_omni.html` - vLLM-Omni serving path. [CITED]
- `https://voxcpm.readthedocs.io/en/latest/reference/changelog.html` - VoxCPM2 architecture/CLI/control changes. [CITED]
- `https://huggingface.co/openbmb/VoxCPM2` and Hugging Face API - model license, SHA, sample-rate/VRAM/model details. [CITED/VERIFIED]
- PyPI JSON for `voxcpm` and `nano-vllm-voxcpm` fetched 2026-05-11 - package versions and dependencies. [VERIFIED]
- Context7 `/openbmb/voxcpm` docs query - official-source snippets for Python API, streaming, NanoVLLM usage. [VERIFIED: ctx7 CLI]

### Secondary (MEDIUM confidence)

- `.planning/spikes/003-tts-engine-extension-luxtts-chatterbox-tada/MANUAL-QUALITY.csv` and `RESULT-MATRIX.csv` - prior RayMe evidence shape and pitfalls. [VERIFIED]
- `.planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py` and tests - reusable benchmark harness and chunk planner. [VERIFIED]
- SSH environment probes against `rayme-pmpg` on 2026-05-11 - Python, GPU, CUDA torch, missing `voxcpm`. [VERIFIED]

### Tertiary (LOW confidence)

- None. The only assumption is logged as A1 and is naming-related, not technical feasibility. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for official package/model/API versions; MEDIUM for OMEN install feasibility until `voxcpm` is installed and loaded on target hardware. [VERIFIED: PyPI/HF/docs + ssh probes]
- Architecture: HIGH because RayMe extension points are directly verified in current code. [VERIFIED: codebase inspection]
- Pitfalls: HIGH for CPU fallback, sample-rate, metadata fallback, and evidence gates; MEDIUM for style-control + transcript-guided ambiguity until live API behavior is tested. [CITED: official docs; VERIFIED: codebase/context]
- Runtime recommendation: MEDIUM because it is a conservative synthesis of official docs and current code, but actual promotion depends on Phase 7 benchmarks. [VERIFIED: docs + codebase + 07-CONTEXT.md]

**Research date:** 2026-05-11
**Valid until:** 2026-06-10 for RayMe code patterns; 2026-05-18 for VoxCPM2 package/runtime versions because this ecosystem is actively changing. [VERIFIED: current release dates from PyPI/HF]
