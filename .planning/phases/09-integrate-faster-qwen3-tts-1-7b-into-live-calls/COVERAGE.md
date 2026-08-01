# API Coverage — Faster Qwen3-TTS v0.3.2

> Full coverage by default. Opt-outs are explicit, reasoned decisions. The source of record is the product-owner-supplied repository at tag `v0.3.2`, commit `a70afc0f81f7f5f8801c3227968f1102f43f211c`.

| capability | decision | reason |
|---|---|---|
| `FasterQwen3TTS.from_pretrained(local_snapshot, backend="torch")` | INTEGRATE | |
| CUDA-only `device="cuda"`, `bfloat16`, SDPA, static-cache loading | INTEGRATE | |
| Immutable local Hugging Face snapshot loading | INTEGRATE | |
| `warmup(prefill_len=100)` CUDA-graph warmup | INTEGRATE | |
| Full-ICL `create_voice_clone_prompt()` from reference WAV plus exact transcript | INTEGRATE | |
| Reuse of one precomputed selected-voice prompt | INTEGRATE | |
| `generate_voice_clone_streaming()` | INTEGRATE | |
| Public `generate()` default-voice method | OPT-OUT | At pinned commit it raises `NotImplementedError` and directs callers to voice cloning; Phase 09 has no default-voice path. |
| Native chunk timing metadata | INTEGRATE | |
| `chunk_size=4` | INTEGRATE | Preserves sustained long-call RTF headroom while RayMe retains a separate 600 ms startup buffer and 1.25 s caller-playback ceiling. |
| `non_streaming_mode=True` for the current bounded text segment | INTEGRATE | |
| `append_silence=True` | INTEGRATE | |
| Generator close/exhaustion terminal semantics | INTEGRATE | |
| Non-streaming `generate_voice_clone()` whole synthesis | OPT-OUT | Live RayMe calls must play early native chunks and may never fall back to a whole-turn WAV.
| Torch arguments `ref_spk`, `ref_rvq`, `ref_spk_emb`, and `ref_codes` | OPT-OUT | GGML-only cached inputs rejected by Torch. RayMe uses full-ICL `voice_clone_prompt` from approved audio and exact transcript. |
| X-vector-only cloning | OPT-OUT | The selected product path is full ICL with matching reference audio and transcript.
| Promptless voice cloning | OPT-OUT | Phase 09 requires the approved saved reference WAV and exact transcript.
| `generate_custom_voice()` | OPT-OUT | Requires a CustomVoice model and is explicitly outside the Phase 09 Base-model ICL boundary. |
| `generate_custom_voice_streaming()` | OPT-OUT | Streaming does not change the model/product boundary; CustomVoice remains explicitly deferred. |
| `generate_voice_design()` | OPT-OUT | Requires a VoiceDesign model and is explicitly outside the Phase 09 Base-model ICL boundary. |
| `generate_voice_design_streaming()` | OPT-OUT | Streaming does not change the model/product boundary; VoiceDesign remains explicitly deferred. |
| Base-model `instruct` controls | OPT-OUT | Phase 09 is English full-ICL cloning, not instruction-driven voice design.
| Qwen3-TTS 0.6B model | OPT-OUT | The product owner selected 1.7B after the accepted comparison and longitudinal reel.
| Multilingual language modes | OPT-OUT | RayMe v1 remains English-only, including accented English.
| Upstream CLI | OPT-OUT | RayMe keeps one public API and owns worker lifecycle, backpressure, cancellation, and state.
| Upstream HTTP/OpenAI-compatible server | OPT-OUT | A second service/public API would violate the locked topology and hide live-stream controls.
| Upstream Gradio/demo UI | OPT-OUT | RayMe Voice Lab is the only product UI.
| vLLM serving backend | OPT-OUT | The accepted RTX 3060 evidence uses the native Torch CUDA-graph backend.
| Triton kernels/backend | OPT-OUT | The accepted Windows runtime is the Torch/SDPA path and does not depend on Triton.
| FlashAttention 2 | OPT-OUT | The accepted Windows runtime uses SDPA; changing attention backends requires new hardware evidence.
| GGML/quantized runtime | OPT-OUT | Explicitly deferred by Phase 09 context.
| Mutable Hub branch/model-id loading at call time | OPT-OUT | Deployment materializes and attests the exact model snapshot before service start.
| Upstream path-keyed prompt cache | OPT-OUT | It is unbounded and path-sensitive; RayMe owns a capacity-one content/transcript/model cache.
| Batch/parallel generation on one model instance | OPT-OUT | CUDA graphs are mutable single-stream state; exactly one active generation owns the worker.
| Parity/benchmark mode | OPT-OUT | Production uses the accepted sampling path and records evidence through RayMe-owned runners.

## Package legitimacy decision

`faster-qwen3-tts` is marked `[SUS]` only because the package was 14 days old and registry download telemetry was unavailable at research time. The product owner supplied the official repository, listened to outputs produced from its immutable `v0.3.2` commit, selected the 1.7B path, and explicitly authorized implementation and deployment. That prior human provenance decision satisfies the human part of the young-package gate; execution must still record PyPI owner/source/tag/commit metadata, run the repository slop/package check, and install only the immutable Git commit.

<assumption_delta_decision>
primary_noun: generalized saved-voice `engine_id`
decision: no-change
rationale: The phrase “no whole-synthesis fallback” is a transport prohibition, not a second identity model. The truthful canonical value `qwen3_1_7b` replaces or compatibly translates the historical specific `qwen3_0_6b` value without changing the saved-voice identity abstraction.
</assumption_delta_decision>
