# Spike Manifest

## Idea
Validate whether `OMEN-PC`'s Ubuntu WSL2 environment, accessed remotely through the `pmpg` Windows account, is a viable Linux-first execution path for backend optimization work that is awkward or unsupported on native Windows.

## Requirements

- Remote WSL work must enter `OMEN-PC` as `omen-pc\\pmpg`, then use direct `wsl -d Ubuntu -e ...` commands.
- Keep Linux-side work roots under `/home/pmpg/...`, not `/mnt/c/...`.
- Use fixed absolute Linux paths in remote WSL commands.
- Never run `rm -rf`.
- Never delete files or directories through variable-expanded paths.

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | omen-pc-wsl-gpu-path | standard | Given `OMEN-PC` Ubuntu WSL2, when it is probed over SSH as `pmpg` with a fixed Linux work root, then GPU visibility and baseline build readiness are known. | PARTIAL | wsl, gpu, omen-pc, ssh |
| 002 | f5-triton-trtllm-wsl-path | standard | Given `OMEN-PC` Ubuntu WSL2 with Docker Desktop available, when the F5 Triton/TensorRT-LLM runtime path is staged from WSL, then the exact viable launch path and blockers are known. | PASS | f5, triton, tensorrt-llm, docker, wsl |
| 003 | tts-engine-extension-luxtts-chatterbox-tada | standard | Given the Phase 0 TTS probe host on `OMEN-PC`, when LuxTTS, Chatterbox Turbo, and TADA 1B are integrated using Voicebox-compatible installs, then their warm-model latency, quality risks, and acceleration levers are known. | PARTIAL | tts, luxtts, chatterbox, tada, benchmark, quality |
