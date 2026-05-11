# Phase 08: Wire VoxCPM2 Streaming Chunks Into Live RayMe Call Playback - Context

**Gathered:** 2026-05-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 8 converts VoxCPM2's benchmark-only streaming advantage into live RayMe call playback. Live calls using VoxCPM2 must enqueue the first viable streaming audio chunk before full generation completes, preserve existing call turn and interrupt semantics, produce same-run evidence where VoxCPM2 warm first-audio time beats F5, and update durable project decisions if that evidence passes.

This phase is not a Voice Call UI redesign, Voice Lab rework, new provider integration, or broader mobile/PWA/thread-management phase. It may touch AI backend TTS adapter/session/track contracts, Web UI call facade behavior, evidence tooling, and project decision writeback only where needed for VoxCPM2 live streaming playback.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**5 requirements are locked.** See `08-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `08-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- VoxCPM2 live call playback changes needed to consume streaming audio chunks.
- AI backend adapter/session/track contracts needed for first-chunk enqueue and later chunk stitching/playout.
- Web UI call facade changes only if required to preserve SSE keepalive, captions, interrupt, or call-state behavior while VoxCPM2 streams.
- Same-run live evidence comparing warm VoxCPM2 first-audio time against warm F5 first-audio time.
- Phase 8 evidence artifacts and durable decision writeback if VoxCPM2 beats F5.

**Out of scope (from SPEC.md):**
- Redesigning the Voice Call UI.
- Reworking Voice Lab controls or character editing.
- Replacing every engine's TTS implementation except where shared abstractions are required for VoxCPM2 streaming playback.
- Adding managed/cloud TTS providers.
- Treating benchmark-only streaming evidence as sufficient.
- Implementing unrelated mobile, PWA, auth, or thread-management features.

</spec_lock>

<decisions>
## Implementation Decisions

### Streaming Boundary
- **D-01:** Build a reusable internal TTS streaming contract inside the AI backend, with VoxCPM2 as the first real implementation. Do not add a VoxCPM2-specific browser API or expose runtime internals outside the AI backend.
- **D-02:** Preserve the existing public RayMe call surfaces where possible: Web UI/browser callers still use the normal call facade and AI backend `/webrtc` call routes.
- **D-03:** Non-streaming engines may continue using the existing whole-WAV path unless a small shared interface adapter is needed to keep call-session code coherent.

### Playback Timing
- **D-04:** Optimize for first-audio latency. Enqueue the first viable VoxCPM2 streaming chunk as soon as it can produce valid playable audio.
- **D-05:** Use only a minimal viability floor for chunk playback: reject empty/invalid chunks and apply necessary format/sample-rate normalization, but do not intentionally wait for full-response smoothing.
- **D-06:** Measure first chunk time, first enqueue time, `ai_audio_started` time, chunk count, total generation/playback time, inter-chunk gaps, and whether any fallback occurred.

### Call Completion Contract
- **D-07:** Keep the AI backend speak request open until streamed playback reaches the same completion point as current call playback. This preserves the existing Web UI SSE keepalive and Android Chrome connection behavior.
- **D-08:** Emit `ai_audio_started` when the first streamed chunk is queued, not after full VoxCPM2 generation finishes.
- **D-09:** Emit exactly one final completion for the AI turn. Streaming chunks are a playback detail and must not create multiple `ai_done` events or multiple durable `ai_speech` rows.

### Failure And Fallback Policy
- **D-10:** Evidence runs must not silently fall back to whole-WAV synthesis. If streaming is unavailable or not used, the evidence artifact must show that clearly and cannot satisfy the Phase 8 pass gate.
- **D-11:** In production behavior, fallback is allowed only before first audio starts and only if it is explicit in events/evidence. After first audio starts, streaming failure should stop future chunks, emit sanitized `call_tts_failed` behavior as appropriate, and avoid duplicate completion events.
- **D-12:** Interrupt and VAD barge-in must cancel pending VoxCPM2 generation, prevent later chunk enqueue, stop/drain queued speech through the existing interrupt path, and return to listening.

### Evidence Strictness
- **D-13:** Same-run warm comparison is required, but use repeated warm samples and promote based on median VoxCPM2 warm first-audio time beating median F5 warm first-audio time.
- **D-14:** The evidence artifact must include enough timing fields to prove first audio came from live streaming playback rather than whole-WAV completion.
- **D-15:** Durable default/preferred-engine writeback occurs only if live evidence passes the comparative latency gate and preserves call-flow, interrupt, sanitized-error, VRAM/runtime, and single-turn semantics.

### the agent's Discretion
- Exact internal class/interface names for streaming chunks and adapters.
- Exact chunk viability thresholds, as long as they are minimal and latency-first.
- Exact evidence filenames and schema shape, as long as required metrics are machine-readable and verifier-enforced.
- Exact test layering and fixture design, as long as tests prove first-chunk enqueue before final generation completion and interrupt behavior after the first streamed chunk.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked Scope
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-SPEC.md` - Locked Phase 8 goal, requirements, boundaries, constraints, and acceptance criteria.
- `.planning/ROADMAP.md` - Phase 8 position after Phase 7 and durable roadmap outcome wording.
- `.planning/PROJECT.md` - Core call-feel priority, RTX 3060 hardware constraint, self-hosted engine boundary, shared TTS chunking rule, and current VoxCPM2 caveat/default wording.
- `.planning/REQUIREMENTS.md` - TTS/call requirements, especially `REQ-02`, `REQ-41`, `REQ-42`, `REQ-45`, `REQ-60`, `REQ-62`, `REQ-80`, and `REQ-A3`.
- `.planning/STATE.md` - Current Phase 7 outcome, call-session policies, runtime/deployment rules, and VoxCPM2 streaming caveat.

### Prior Phase Decisions And Evidence
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-CONTEXT.md` - VoxCPM2 roster, quality, runtime, call-flow, and promotion-gate decisions.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-RUNTIME-PATH-DECISION.md` - Standard Python runtime path and streaming API revisit gate.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-12-SUMMARY.md` - Final Phase 7 quality and latency outcome.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-PROMOTION-DECISION.md` - Evidence-backed final outcome and caveat rationale.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-call-flow.json` - Existing whole-WAV live call TTFA and F5 comparator values.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-decision.json` - Machine-readable Phase 7 final outcome.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.json` - Benchmark-only VoxCPM2 `generate_streaming` first-audio evidence.
- `.planning/phases/03-first-working-call-mvp/03-CONTEXT.md` - Existing call turn, interrupt, transcript, and verification decisions.

### Runtime And Deployment Rules
- `ai-backend/docs/RUNTIME-EVIDENCE.md` - Runtime evidence expectations and one-public-API constraints.
- `ai-backend/docs/STT-GPU-RUNTIME.md` - CUDA runtime, no CPU fallback, and OMEN RTX 3060 verification rules.
- `.planning/OPERATING-NOTES.md` - OMEN-PC, LAN/Android HTTPS, and verification rules.
- `scripts/deploy-omen.sh` - The only valid OMEN deployment path; fix this script if deployment support is missing.

### Existing Code Entry Points
- `ai-backend/app/models/tts_voxcpm2.py` - Current VoxCPM2 adapter using `runtime.generate(...)` and returning one WAV.
- `ai-backend/app/models/tts_registry.py` - Existing TTS metadata, synthesis input/output models, optional-runtime adapter pattern, and `supports_streaming` metadata.
- `ai-backend/app/models/model_manager.py` - One-hot TTS residency and engine-scoped unavailable behavior.
- `ai-backend/app/call/session.py` - Current call speech synthesis, interrupt, outbound enqueue, `ai_audio_started`, and `ai_done` behavior.
- `ai-backend/app/call/tracks.py` - `QueuedAudioOutputTrack` and outbound audio queue/playout behavior.
- `ai-backend/app/api/webrtc.py` - AI backend `/webrtc` offer/control/speak route and VoxCPM2 option validation.
- `web-ui/server/app/api/calls.py` - Web UI call turn SSE, keepalive behavior, durable `ai_speech` writeback, and AI backend speak call.
- `web-ui/server/app/domain/ai_backend_client.py` - Sanitized AI backend call client boundary.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py` - Existing call-flow evidence runner to extend or mirror for Phase 8.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py` - Existing evidence verifier pattern to extend or mirror for Phase 8.

### VoxCPM2 References
- `https://voxcpm.readthedocs.io/en/latest/reference/api.html` - Official API reference for `generate_streaming`, clone inputs, style/control fields, and sample-rate behavior.
- `https://github.com/OpenBMB/VoxCPM` - Official VoxCPM/VoxCPM2 repository.
- `https://huggingface.co/openbmb/VoxCPM2` - Official VoxCPM2 model card.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `VoxCpm2TtsAdapter` already maps RayMe voice metadata into VoxCPM2 clone/style/control kwargs and writes temporary reference-audio files.
- `TtsSynthesisInput` already carries bounded VoxCPM2 settings used by preview, test-play, and calls.
- `CallSession.speak_text()` already owns the right lifecycle points for `thinking`, outbound enqueue, `ai_audio_started`, playback wait, cancellation, and `ai_done`.
- `QueuedAudioOutputTrack.enqueue()` already accepts WAV bytes and returns playback duration; this can remain the playout boundary if streaming chunks are converted to valid per-chunk WAV bytes before enqueue.
- Web UI call SSE already waits on the AI backend speak request and sends keepalive comments during long TTS windows.
- Phase 7 evidence scripts already capture call-flow, runtime, scenario matrix, and decision artifacts in deterministic result paths.

### Established Patterns
- Durable thread/message state belongs in the Web UI server; transient STT/TTS/VAD/WebRTC runtime belongs in the AI backend.
- Browser and Web UI callers should not learn per-engine runtime internals.
- Production AI model paths must stay CUDA-only; CPU fallback is a regression.
- Public errors must remain sanitized and must not expose tracebacks, local paths, cache paths, or raw model internals.
- OMEN deployment and runtime evidence must go through `scripts/deploy-omen.sh`.

### Integration Points
- Add a streaming synthesis path to `ai-backend/app/models/tts_voxcpm2.py` around VoxCPM2 `generate_streaming`.
- Add an internal streaming adapter/session contract in `ai-backend/app/models/tts_registry.py` and/or `ai-backend/app/call/session.py`.
- Teach `CallSession.speak_text()` to consume streamed chunks for VoxCPM2 while keeping current whole-WAV behavior for other engines.
- Extend tests in `ai-backend/tests/test_tts_voxcpm2.py`, `ai-backend/tests/test_call_session.py`, and `ai-backend/tests/test_webrtc_signaling.py` for first-chunk enqueue, cancellation, sanitized failure, and single-final-event behavior.
- Extend or mirror Phase 7 call-flow evidence tooling under the Phase 8 directory with repeated warm F5/VoxCPM2 comparison and streaming proof fields.
- Update `PROJECT.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, and a Phase 8 decision artifact only after passing live evidence.

</code_context>

<specifics>
## Specific Ideas

- The accepted default direction is latency-first: play the first viable VoxCPM2 chunk immediately rather than waiting for smoother full-response assembly.
- The streaming implementation should be internal and reusable, not a new browser-facing VoxCPM2 route.
- Evidence must distinguish true streaming playback from benchmark-only `generate_streaming` collection or whole-WAV fallback.
- Promotion/default writeback needs repeated same-run warm evidence, not a single lucky measurement.
- The current Phase 7 caveat is precise: VoxCPM2 sounds better than F5, but F5 remains default until live RayMe calls receive the streaming first-audio advantage.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 8 scope.

</deferred>

---

*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Context gathered: 2026-05-11*
