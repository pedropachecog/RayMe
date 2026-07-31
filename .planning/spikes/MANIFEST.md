# Spike Manifest

## Idea
Validate GPU-backed runtime and TTS-engine experiments on `OMEN-PC` before they enter RayMe. Current work evaluates `faster-qwen3-tts` as a replacement candidate for the voice engine that progressively became muffled, whisper-like, noisy, and unintelligible during longer conversations.

## Requirements

- Remote WSL work must enter `OMEN-PC` as `omen-pc\\pmpg`, then use direct `wsl -d Ubuntu -e ...` commands.
- Keep Linux-side work roots under `/home/pmpg/...`, not `/mnt/c/...`.
- Use fixed absolute Linux paths in remote WSL commands.
- Never run `rm -rf`.
- Never delete files or directories through variable-expanded paths.
- Test `faster-qwen3-tts` from the immutable `v0.3.2` release on native Windows first because that is RayMe's production AI-backend runtime.
- Compare both Base voice-cloning models (`0.6B` and `1.7B`) on the RTX 3060 rather than choosing from upstream benchmark claims.
- GPU execution is mandatory. CPU fallback is a failed test.
- Peak model/runtime VRAM must stay within RayMe's 11 GiB working budget.
- A candidate cannot pass on TTFA alone. It must survive at least 50 sequential turns without progressive muffling, whispering, noise, silence, clipping, intelligibility loss, or speaker/prosody collapse.
- Longitudinal evidence must preserve early, middle, and late WAVs plus turn-indexed acoustic, latency, and intelligibility measurements for human review.
- Live playback must start before stream completion, use bounded startup buffering only, remain interruptible, and never use whole-synthesis fallback.
- Do not integrate or deploy the engine until runtime fit, longitudinal quality, live-stream invariants, and human listening acceptance all pass.

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | omen-pc-wsl-gpu-path | standard | Given `OMEN-PC` Ubuntu WSL2, when it is probed over SSH as `pmpg` with a fixed Linux work root, then GPU visibility and baseline build readiness are known. | PARTIAL | wsl, gpu, omen-pc, ssh |
| 002 | f5-triton-trtllm-wsl-path | standard | Given `OMEN-PC` Ubuntu WSL2 with Docker Desktop available, when the F5 Triton/TensorRT-LLM runtime path is staged from WSL, then the exact viable launch path and blockers are known. | PASS | f5, triton, tensorrt-llm, docker, wsl |
| 003 | tts-engine-extension-luxtts-chatterbox-tada | standard | Given the Phase 0 TTS probe host on `OMEN-PC`, when LuxTTS, Chatterbox Turbo, and TADA 1B are integrated using Voicebox-compatible installs, then their warm-model latency, quality risks, and acceleration levers are known. | PARTIAL | tts, luxtts, chatterbox, tada, benchmark, quality |
| 004a | faster-qwen3-tts-06b-cuda | comparison | Given the immutable `v0.3.2` package and the OMEN RTX 3060, when the 0.6B Base model is loaded and streamed on native Windows, then CUDA enforcement, VRAM fit, TTFA, throughput, chunk cadence, and basic voice-clone correctness are measured. | PASS | tts, qwen3, cuda-graphs, windows, benchmark, voice-clone |
| 004b | faster-qwen3-tts-17b-cuda | comparison | Given the same runtime and fixtures, when the 1.7B Base model is measured head-to-head with 0.6B, then RayMe knows whether its quality headroom fits the 12 GB card without losing realtime behavior. | PASS | tts, qwen3, cuda-graphs, windows, benchmark, voice-clone |
| 005 | faster-qwen3-tts-longitudinal-quality | standard | Given one hot model and a fixed RayMe voice reference, when at least 50 sequential turns are synthesized, then early/middle/late evidence proves or rejects progressive quality degradation and state leakage. | PENDING | tts, qwen3, soak, quality, intelligibility, regression |
| 006 | faster-qwen3-tts-live-stream-contract | standard | Given the strongest runtime candidate, when its pull-based audio stream is driven through a RayMe-shaped bounded consumer, then first playback precedes completion, production stays faster than playback, joins remain stable, interruption stops late audio, and no whole-WAV fallback occurs. | PASS | tts, qwen3, streaming, live-call, barge-in, regression |
