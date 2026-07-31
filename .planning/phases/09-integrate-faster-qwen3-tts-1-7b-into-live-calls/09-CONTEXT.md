# Phase 09: Integrate Faster Qwen3-TTS 1.7B Into Live Calls - Context

**Gathered:** 2026-07-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 9 turns the accepted Faster Qwen3-TTS 1.7B spike runtime into a first-class RayMe engine for Voice Lab preview, saved voices, test-play, and real OMEN calls. It includes honest engine identity and compatibility handling, ICL reference-transcript validation, visible one-hot loading and reference prewarm, bounded native streaming with early playback, cancellation/barge-in, regression and soak evidence, and canonical deployment.

This phase does not add the 0.6B model as a second production choice, custom-voice generation, multilingual support, a standalone TTS service, GGML deployment, or a non-live whole-response playback mode.

</domain>

<decisions>
## Implementation Decisions

### Runtime And Model Identity
- **D-01:** Pin the official `faster-qwen3-tts` v0.3.2 runtime and `Qwen/Qwen3-TTS-12Hz-1.7B-Base`. Production may not float to an untested commit, package version, or model.
- **D-02:** Use a truthful canonical engine id for 1.7B (recommended: `qwen3_1_7b`). Treat the old `qwen3_0_6b` value as compatibility data only: migrate or translate existing saved records explicitly, and never let it silently select 0.6B or masquerade as 1.7B.
- **D-03:** Keep the runtime behind RayMe's one-hot TTS manager on CUDA. CPU fallback and a second resident TTS model are failures.
- **D-04:** Keep one RayMe public API. The browser and Web UI server must not call an upstream TTS server or learn upstream runtime internals.

### Voice Cloning And Transcript Protection
- **D-05:** Use the Base model's zero-shot ICL voice-cloning path with the saved reference WAV and its matching transcript. Promptless/custom-voice modes are out of scope.
- **D-06:** A missing or blank reference transcript is a blocking validation error for this engine in save, preview/test-play, call start, and backend synthesis boundaries.
- **D-07:** Add a practical alignment preflight using existing RayMe STT/transcript assets and bounded sanity checks. Grossly mismatched audio/transcript pairs must fail before long generation begins, with an actionable sanitized message. Validation must tolerate ordinary STT punctuation/casing errors and accented English.
- **D-08:** Enforce generation ceilings (tokens/chunks/audio duration relative to requested text) so a bad prompt cannot repeat or run to a token-cap-length output. A ceiling breach is an engine-scoped sanitized failure, never partial unbounded playback.

### Loading, Prewarm, And Visible State
- **D-09:** Model load and reference-prompt preparation are separate visible states. RayMe must expose `loading`, `resident`, and reference `prewarming`/`ready`/failure state instead of hiding them behind a frozen first call turn.
- **D-10:** Prewarm the selected saved voice's reference prompt before the first spoken turn when the call is prepared. Do not retain unbounded reference caches; cache ownership and eviction follow the one-hot model lifecycle.
- **D-11:** Preview and test-play may trigger the same load/prewarm path, and must surface progress and sanitized errors through existing product controls.

### Live Streaming Contract
- **D-12:** Real calls use `generate_voice_clone_streaming` only for Faster Qwen3-TTS. No whole-synthesis fallback is allowed before or after first playback.
- **D-13:** Preserve early playback. A bounded startup/jitter buffer may smooth joins, but the first playable audio must be enqueued before a deliberately slow synthesis stream completes.
- **D-14:** Bound producer-to-consumer queue capacity and apply backpressure. Do not accumulate an entire turn in memory when network or playout is slower than generation.
- **D-15:** Keep immediate timing (`first chunk`, `first enqueue`, `ai_audio_started`) separate from final timing (`generation complete`, `playout complete`, final event). Do not overwrite early metrics with completion values.
- **D-16:** The upstream `non_streaming_mode` optimization may prefill only the current safe synthesis segment; it must never cause RayMe to wait for the full assistant response or full turn audio before first playback.

### Cancellation And Failure Semantics
- **D-17:** Barge-in, explicit interrupt, hangup, engine switch, and session close must signal generation cancellation, stop/drain future audio, discard late chunks, and return the call to the correct listening/closed state promptly.
- **D-18:** A cancelled turn cannot emit normal `ai_done`, cannot persist a complete `ai_speech` artifact, and cannot leak late audio into the next turn.
- **D-19:** Faster Qwen3 failures are engine-scoped and sanitized. They may mark that engine unavailable/caveated while keeping STT, WebRTC, the backend, and other TTS engines usable.

### Evidence And Deployment
- **D-20:** Regression tests must prove slow-stream first playback before completion, bounded queueing, no whole-synthesis fallback, separate immediate/final metrics, prompt interruption, late-chunk rejection, and preservation of the existing VoxCPM2 live-stream invariant tests.
- **D-21:** Preserve the Spike 005 failure-mode gate in the integrated path: a hot-process multi-turn run must check intelligibility, audio validity, latency drift, memory drift, and early/middle/late acoustic stability.
- **D-22:** `scripts/deploy-omen.sh` is the only OMEN deployment mechanism. It must install/verify the pinned runtime and model through the canonical launchers/tasks, then verify status and a RayMe-shaped call flow before handoff for the builder's physical call.

### the Agent's Discretion
- Exact compatibility migration mechanism for persisted `qwen3_0_6b` values, provided it is explicit, tested, and does not lie about model identity.
- Exact transcript similarity algorithm and tolerance, provided it catches the known gross mismatch without rejecting normal punctuation/casing/accented-English variance.
- Exact prompt-cache key, capacity, and observability fields, provided cache lifetime is bounded and tied to model residency.
- Exact native chunk size, startup-buffer duration, queue capacity, and cancellation primitive, provided measured live-call invariants and target latency hold.
- Exact UI wording and progress presentation within RayMe's existing design system.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked Product And Live-Call Contract
- `.planning/LIVE-CALL-INVARIANTS.md` - Non-negotiable early playback, bounded buffering, recovery, barge-in, testing, and deployment rules.
- `.planning/ROADMAP.md` - Phase 9 goal and observable success criteria.
- `.planning/REQUIREMENTS.md` - `REQ-02`, `REQ-20` through `REQ-24`, `REQ-41`, `REQ-42`, `REQ-45`, `REQ-46`, `REQ-62`, and `REQ-80`.
- `.planning/STATE.md` - Current runtime, deployment, call, and phase state.
- `.planning/OPERATING-NOTES.md` - OMEN host and verification rules.

### Accepted Faster Qwen3-TTS Evidence
- `.planning/spikes/004-a-faster-qwen3-tts-06b-cuda/README.md` - 0.6B comparison evidence.
- `.planning/spikes/004-b-faster-qwen3-tts-17b-cuda/README.md` - Selected 1.7B CUDA/latency/VRAM evidence.
- `.planning/spikes/005-faster-qwen3-tts-longitudinal-quality/README.md` - 50-turn stability and intelligibility gate.
- `.planning/spikes/005-faster-qwen3-tts-longitudinal-quality/HUMAN-LISTENING-CHECKPOINT.md` - Product-owner acceptance and 1.7B selection.
- `.planning/spikes/006-faster-qwen3-tts-live-stream-contract/README.md` - Bounded consumer, early playback, realtime, and interruption evidence.

### Existing Live Streaming And Runtime Patterns
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-CONTEXT.md` - Shared internal streaming contract and live playback decisions.
- `.planning/phases/08.1-live-call-streaming-invariant-incident-repair-and-prevention/` - Incident repair and recurrence guards.
- `ai-backend/docs/RUNTIME-EVIDENCE.md` - CUDA and one-public-API evidence expectations.
- `ai-backend/docs/STT-GPU-RUNTIME.md` - GPU runtime and no-CPU-fallback rules.
- `scripts/deploy-omen.sh` - Sole authorized OMEN deployment path.

### Existing Code Entry Points
- `ai-backend/app/models/tts_registry.py` - Engine metadata and synthesis/streaming contracts.
- `ai-backend/app/models/tts_qwen3.py` - Current import-gated 0.6B placeholder to replace.
- `ai-backend/app/models/model_manager.py` - One-hot residency and health/status behavior.
- `ai-backend/app/call/session.py` - Live streamed speech lifecycle, queueing, metrics, and cancellation.
- `ai-backend/app/call/tracks.py` - Outbound playout queue and playback clock.
- `ai-backend/app/api/tts.py` and `ai-backend/app/api/webrtc.py` - Preview and call synthesis boundaries.
- `web-ui/server/app/api/voices.py` and `web-ui/server/app/domain/voice_service.py` - Durable voice metadata and backend bridge.
- `web-ui/client/src/routes/voice-lab/+page.svelte` and `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` - Voice Lab engine selection and visible status.

### Official Upstream
- `https://github.com/andimarafioti/faster-qwen3-tts/tree/v0.3.2` - Pinned official runtime source and API.
- `https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base` - Pinned model card and license/usage contract.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- RayMe already has a metadata-driven TTS roster, synthesis inputs carrying reference audio/transcript, a one-hot model manager, and engine-scoped unavailability.
- The mature VoxCPM2 adapter/worker path demonstrates native streaming, subprocess isolation, cancellation, and no-fallback policy.
- `CallSession` already owns the correct points for first enqueue, `ai_audio_started`, playback completion, interrupt, final events, and timing metrics.
- Voice Lab already uploads, transcribes, edits, saves, previews, and test-plays reference voices.
- Phase 8/08.1 tests and evidence scripts already encode the live-call invariant and must remain green.

### Known Risks
- The current Qwen3 adapter is only an import-gated `qwen_tts` placeholder labeled `qwen3_0_6b`; it does not implement the accepted runtime or streaming contract.
- Several backend and client tests hard-code the engine roster; the identity migration must be systematic.
- The call streaming producer currently uses an unbounded asyncio queue; Faster Qwen3 can outrun playback, so bounded backpressure and cancellation need explicit design.
- The accepted spike proved that a wrong reference transcript can generate an 81.92-second token-cap runaway. Correct transcript alignment restored natural EOS, so input validation and output ceilings are release gates.
- The 1.7B model fits the RTX 3060 only under the one-hot residency rule: observed Torch reserved memory was about 5.6 GiB and whole-system use with RayMe services was about 8.1–8.35 GiB.

### Measured Baseline
- Selected 1.7B, four-step streaming: median TTFA 368.9 ms and RTFx 1.46.
- Selected 1.7B, eight-step streaming: TTFA 520.1 ms and RTFx 1.71.
- Fifty-turn hot-process soak: 50/50 natural EOS, 50/50 accepted by RayMe STT, overall WER 0.00736, zero reserved-memory growth, stable early/late acoustics, and bit-identical reset-seed anchors.
- Real bounded consumer: first consume at 387 ms while generation continued for 24.027 s; capacity two; interrupt stopped generation in 278 ms with at most one in-flight chunk.

</code_context>

<specifics>
## Specific Ideas

- The user accepted both model samples and the longitudinal reel, then chose 1.7B for its expected cloning-quality headroom.
- The handoff target is concrete: RayMe on OMEN must be deployed and ready for the user to select a cloned 1.7B voice and place a physical call.
- Visible model/reference readiness matters as much as backend correctness; the user must not have to infer that a hidden warmup is happening.

</specifics>

<deferred>
## Deferred Ideas

- Shipping 0.6B as a separate selectable engine.
- Qwen3 custom-voice design, multilingual controls, standalone upstream server mode, GGML, or additional quantization paths.
- General redesign of Voice Lab or call UI beyond the status/error controls required for this integration.

</deferred>

---

*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Context gathered: 2026-07-31*
