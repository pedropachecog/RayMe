# Phase 7: Add VoxCPM2 to the TTS roster with empirical quality, latency, VRAM, and call-flow evaluations - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-10
**Phase:** 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
**Areas discussed:** Roster Outcome And Promotion Gate, Cloning Mode And User-Facing Behavior, Benchmark And Quality Evidence, Runtime And Call-Flow Integration Path

---

## Roster Outcome And Promotion Gate

### What should Phase 7 be allowed to change if VoxCPM2 performs well?

| Option | Description | Selected |
|--------|-------------|----------|
| Gated experimental roster engine | Add VoxCPM2 to registry/metadata and make it selectable only after evidence passes; keep `f5` as default for now. | |
| Evaluation only | Benchmark VoxCPM2 and write evidence, but do not make it selectable in Voice Lab, Settings, or calls in this phase. | |
| Full promotion candidate | If it clears the evidence bar, Phase 7 may make it a normal selectable engine everywhere and potentially revisit labels/defaults. | Yes |
| Other | User-defined policy. | |

**User's choice:** Full promotion candidate.
**Notes:** The user asked for clarification. The locked interpretation is that VoxCPM2 may become a first-class engine and may challenge current labels/defaults if evidence supports it.

### What should be enough to promote VoxCPM2 over the current default/recommended path?

| Option | Description | Selected |
|--------|-------------|----------|
| Clear call-feel win | Better warm call latency than F5, acceptable voice quality, stable VRAM, and no call-flow regressions. | Yes |
| Quality-first win | Promote if it sounds clearly better, even if latency is only comparable and not faster. | |
| Balanced score win | Promote if combined quality, latency, VRAM, licensing, and reliability beats F5 overall. | |
| Other | User-defined promotion rule. | |

**User's choice:** Clear call-feel win.

### If VoxCPM2 sounds good but does not beat the current call-feel path on latency, what should happen?

| Option | Description | Selected |
|--------|-------------|----------|
| Selectable but caveated | Keep it available with labels like `Quality candidate` / `Latency caveat`, but do not promote it over F5. | Yes |
| Evaluation-only until faster | Keep evidence and adapter code, but do not expose it in normal Voice Lab or calls. | |
| Quality can override latency | Allow promotion anyway if voice quality is clearly better. | |
| Other | User-defined fallback rule. | |

**User's choice:** Selectable but caveated.

### If VoxCPM2 fails a hard gate on the RTX 3060, how should RayMe handle it?

| Option | Description | Selected |
|--------|-------------|----------|
| Evidence-only, not selectable | Keep benchmark notes and code/probe artifacts, but do not expose VoxCPM2 in normal Voice Lab, Settings, or calls. | |
| Visible but unavailable | Show VoxCPM2 in the engine picker with an unavailable reason. | Yes |
| Developer flag only | Keep it hidden from normal UI, but allow explicit local/dev testing through a flag. | |
| Other | User-defined failure policy. | |

**User's choice:** Visible but unavailable.

---

## Cloning Mode And User-Facing Behavior

### Which VoxCPM2 cloning mode should Phase 7 support first?

| Option | Description | Selected |
|--------|-------------|----------|
| Transcript-guided cloning first | Use stored RayMe sample plus editable transcript where available. | |
| Reference-only cloning first | Use uploaded sample without transcript, closer to XTTS-style UX. | |
| Support both modes | Support transcript-guided and reference-only cloning. | Yes |
| Other | User-defined cloning mode. | |

**User's choice:** Support both modes.

### How should RayMe choose between those two modes in normal use?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-select by data quality | Use transcript-guided when a non-empty saved transcript exists; otherwise fall back to reference-only. | |
| Always ask in UI | Expose a mode selector in preview/test-play/call settings. | |
| Voice-level preference | Save a VoxCPM2 mode on the voice record and reuse it. | Yes |
| Other | User-defined selection rule. | |

**User's choice:** Voice-level preference.

### If an existing saved voice is assigned to VoxCPM2 but has no transcript, what should happen?

| Option | Description | Selected |
|--------|-------------|----------|
| Allow reference-only automatically | Synthesize with reference-only mode and no blocking error. | |
| Prompt to add/edit transcript | Block VoxCPM2 until the user adds a transcript. | |
| Warn but continue | Synthesize reference-only and show a caution that transcript-guided mode may improve results. | Yes |
| Other | User-defined missing-transcript behavior. | |

**User's choice:** Warn but continue.

### VoxCPM2 also has style/voice-design controls beyond plain cloning. Should Phase 7 expose those?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep style controls out of scope | Evaluate roster viability with RayMe's existing saved-voice flow. | |
| Minimal advanced field | Optional style/prompt field only for VoxCPM2 previews, not calls. | |
| Voice-level style settings | Save style controls on the voice and use them for preview, test-play, and calls. | Yes |
| Other | User-defined style scope. | |

**User's choice:** Voice-level style settings.

### How should these style controls be presented?

| Option | Description | Selected |
|--------|-------------|----------|
| Only show for VoxCPM2 voices | Reveal style controls only when VoxCPM2 is selected; keep existing engines unchanged. | Yes |
| Advanced collapsible section | Shared advanced panel, with VoxCPM2 fields enabled when relevant. | |
| Separate VoxCPM2 tuning screen | Put VoxCPM2 style/mode tuning on a separate detail screen. | |
| Other | User-defined UI shape. | |

**User's choice:** Only show for VoxCPM2 voices.

### What should happen if a saved voice has VoxCPM2-specific metadata, then switches to another engine?

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve but ignore it | Keep VoxCPM2 metadata for future switch-back, but do not send it to non-VoxCPM2 adapters. | Yes |
| Clear it on switch | Remove VoxCPM2 metadata when changing engines. | |
| Ask during switch | Prompt whether to keep or clear metadata. | |
| Other | User-defined metadata behavior. | |

**User's choice:** Preserve but ignore it.

---

## Benchmark And Quality Evidence

### What should be the minimum benchmark set before VoxCPM2 can be considered for promotion?

| Option | Description | Selected |
|--------|-------------|----------|
| Full RayMe-shaped matrix | Short/medium/long replies, shared chunk planner, timing/gaps, VRAM, WAVs, preview/test-play/call-flow evidence. | Yes |
| Fast viability pass first | Install, one short preview, one long sample, VRAM snapshot, then full matrix if those pass. | |
| Call-flow only | Focus on real Voice Lab and call behavior, with fewer standalone matrix benchmarks. | |
| Other | User-defined benchmark scope. | |

**User's choice:** Full RayMe-shaped matrix.

### What quality bar should VoxCPM2 have for manual listening?

| Option | Description | Selected |
|--------|-------------|----------|
| Must pass real user-sample listening | Intelligibility, voice match, accent preservation, prosody, and no sample leakage/mumbling artifacts must be acceptable. | Yes |
| Must beat F5 on voice match | It should clearly sound more like the user than F5. | |
| Good enough if call-feel wins | Quality acceptable but not necessarily better than F5 if latency clearly wins. | |
| Other | User-defined quality bar. | |

**User's choice:** Must pass real user-sample listening.

### Should VoxCPM2 be compared only against F5, or against the full current roster?

| Option | Description | Selected |
|--------|-------------|----------|
| Compare against full roster, promote against F5 | Run full-roster comparisons for context; promotion/default decision requires beating F5. | Yes |
| Compare only against F5 | Focus narrowly on the current default/recommended path. | |
| Compare against top candidates only | Compare F5, XTTS, Chatterbox optimized, TADA Windows optimized, and VoxCPM2. | |
| Other | User-defined comparison group. | |

**User's choice:** Compare against full roster, promote against F5.

### How strict should the VRAM gate be?

| Option | Description | Selected |
|--------|-------------|----------|
| Same 11 GB production budget | Must stay under existing 11 GB used-VRAM budget with Whisper + Silero + one resident TTS engine. | Yes |
| Allow near-limit with warning | Allow under 12 GB with a high-VRAM caveat. | |
| Evaluation can exceed, promotion cannot | Allow over-budget evidence runs, but do not expose unless it later fits. | |
| Other | User-defined VRAM rule. | |

**User's choice:** Same 11 GB production budget.

### What if VoxCPM2 passes preview/test-play but fails real call-flow behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| No promotion, visible unavailable/caveated | Standalone wins are not enough; call-flow failure blocks promotion and surfaces availability/caveats by severity. | |
| Selectable outside calls only | Allow Voice Lab preview/test-play but block call usage. | |
| Promote with call warning | Allow it everywhere with a call latency/reliability warning. | |
| Other | User-defined rule. | Yes |

**User's choice:** No promotion, but fully visible and available.
**Notes:** The locked nuance is that call-flow failure blocks promotion but does not hide or disable VoxCPM2.

### How should Phase 7 store/list the human quality evidence?

| Option | Description | Selected |
|--------|-------------|----------|
| Manual quality CSV plus generated samples | Extend the existing manual quality CSV style with ratings and notes linked to WAV samples. | Yes |
| Markdown evidence report only | Narrative notes and summary tables, but no structured CSV. | |
| JSON/CSV machine-readable scorecard | Structured rows for automated comparison and a short Markdown summary. | |
| Other | User-defined evidence format. | |

**User's choice:** Manual quality CSV plus generated samples.

---

## Runtime And Call-Flow Integration Path

### Which VoxCPM2 runtime path should planning investigate first?

| Option | Description | Selected |
|--------|-------------|----------|
| Standard Python API first | Start with the official `VoxCPM.from_pretrained(...).generate(...)` path in the existing adapter pattern. | |
| Streaming API first | Prioritize `generate_streaming` because call feel depends on first audio. | |
| Server runtime first | Investigate NanoVLLM/vLLM-Omni serving before in-process integration. | |
| Other | User-defined runtime priority. | Yes |

**User's choice:** Investigate everything.
**Notes:** Planning should investigate standard Python API, streaming API, NanoVLLM-VoxCPM, and vLLM-Omni-style serving before choosing.

### After investigation, what implementation shape should Phase 7 prefer if multiple paths work?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep one public AI backend API | Runtime may be internal/in-process/subprocess/WSL/server-backed, but RayMe callers see one backend API and normal registry. | Yes |
| Prefer in-process adapter | Use subprocess/server runtimes only if in-process API fails hard. | |
| Prefer streaming/server runtime | Use the runtime with best first-audio behavior even if it needs a helper service. | |
| Other | User-defined implementation shape. | |

**User's choice:** Keep one public AI backend API.

### Should Phase 7 include real call-flow integration?

| Option | Description | Selected |
|--------|-------------|----------|
| Include real call-flow integration | Wire VoxCPM2 through preview, test-play, and call playback enough to measure handoff, gaps, interrupt behavior, and stability. | Yes |
| Benchmark and Voice Lab only | Do not touch the call loop until a later phase. | |
| Call-flow smoke only | Run one minimal call playback smoke and leave deeper tests for later. | |
| Other | User-defined call integration depth. | |

**User's choice:** Include real call-flow integration.

### How should VoxCPM2 failures be isolated from the rest of the TTS system?

| Option | Description | Selected |
|--------|-------------|----------|
| Engine-scoped degradation | VoxCPM2 failures mark only VoxCPM2 unavailable/caveated; other engines and backend stay available. | Yes |
| Backend startup can fail | If VoxCPM2 fails startup, the AI backend fails fast. | |
| Hidden dev-only failure | Failed VoxCPM2 is hidden from normal UI and only logged for developers. | |
| Other | User-defined failure isolation. | |

**User's choice:** Engine-scoped degradation.

### How should Phase 7 handle package/model downloads and large runtime artifacts?

| Option | Description | Selected |
|--------|-------------|----------|
| Optional extra plus documented cache paths | Optional AI backend extra/runtime gate, exact paths documented, large downloads out of git. | Yes |
| Install by default | Add VoxCPM2 runtime dependencies to normal AI backend install. | |
| Separate local script only | Keep all install/model handling outside normal dependency management. | |
| Other | User-defined dependency/artifact handling. | |

**User's choice:** Optional extra plus documented cache paths.

### Should Phase 7 update UI fallback lists and engine-label code paths?

| Option | Description | Selected |
|--------|-------------|----------|
| Update fallback lists too | Backend metadata remains canonical, but UI fallbacks/types/labels include VoxCPM2. | Yes |
| Backend metadata only | Engine appears only when backend metadata includes it. | |
| No UI exposure until evidence complete | Benchmark first, then update UI only if it passes. | |
| Other | User-defined UI metadata policy. | |

**User's choice:** Update fallback lists too.

---

## the agent's Discretion

- Exact VoxCPM2 engine id, caveat wording, scoring weights, artifact names, and implementation runtime after evidence.

## Deferred Ideas

None.
