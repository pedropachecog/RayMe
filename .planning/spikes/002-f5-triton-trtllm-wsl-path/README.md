---
spike: 002
name: f5-triton-trtllm-wsl-path
type: standard
validates: "Given OMEN-PC Ubuntu WSL2 with Docker Desktop available, when the F5 Triton/TensorRT-LLM runtime path is staged from WSL, then the exact viable launch path and blockers are known."
verdict: PASS
related: [001]
tags: [f5, triton, tensorrt-llm, docker, wsl]
---

# Spike 002: F5 Triton/TensorRT-LLM WSL Path

## What This Validates

Given `OMEN-PC` Ubuntu WSL2 with Docker Desktop available, when the F5 Triton/TensorRT-LLM runtime path is staged from WSL, then the exact viable launch path and blockers are known.

## Research

Docs checked on 2026-04-23:

- F5-TTS official runtime docs describe the high-performance path as `Triton Inference Serving Best Practice`, with a quick start via `MODEL=F5TTS_v1_Base docker compose up` and a build-from-scratch path based on `nvcr.io/nvidia/tritonserver:24.12-py3`.
- The official runtime image installs `tensorrt-llm==0.16.0` and related inference dependencies on top of the NVIDIA Triton Server base image.
- The runtime `run.sh` script builds TensorRT-LLM engines, exports the vocoder, builds a Triton model repo, and launches `tritonserver`.

Approach comparison:

| Approach | Tool/Path | Pros | Cons | Status |
|----------|-----------|------|------|--------|
| Docker Desktop via WSL integration | `docker` inside Ubuntu WSL | Lowest friction and visible in Docker Desktop UI | Initially stalled on image pulls until Desktop was updated and restarted | Validated after update |
| Native Docker engine in WSL | `dockerd` on `unix:///home/pmpg/rayme/docker-native/docker.sock` | Fully Linux-local, reproducible from shell, GPU path confirmed | Separate daemon to manage | Validated |
| Native Windows Docker path | `docker.exe` on Windows | Avoids WSL integration questions | F5 runtime docs and scripts are Linux-first | Rejected |

Chosen approach: use Docker Desktop's Linux engine through Ubuntu WSL now that the Desktop update fixed pull behavior, but keep the native WSL daemon as a fallback and verification path. Avoid the stock F5 compose command because it includes a baked-in `rm -rf`.

Sources:

- https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/runtime/triton_trtllm/README.md
- https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/runtime/triton_trtllm/Dockerfile.server
- https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/runtime/triton_trtllm/run.sh

## How to Run

```bash
.planning/spikes/002-f5-triton-trtllm-wsl-path/docker-gpu-smoke.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/pull-runtime-image.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/build-runtime-artifacts.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/assemble-model-repo.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/launch-runtime-server.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/client-http-smoke.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/sync-phase0-fixtures.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/native-docker-bootstrap.sh
.planning/spikes/002-f5-triton-trtllm-wsl-path/native-docker-gpu-smoke.sh
```

## What to Expect

- Verifies that Ubuntu WSL can reach Docker Desktop's Linux engine.
- Uses a fixed public Docker config under `/home/pmpg/rayme/docker-config-public` to avoid non-interactive credential-helper failures.
- Confirms whether a GPU-enabled container can run from WSL on both Docker Desktop and the native WSL daemon.
- Pulls the official prebuilt F5 Triton runtime image.
- Builds or reuses the F5 checkpoint, TensorRT-LLM engine, and vocoder plan under `/home/pmpg/rayme/f5-triton-runtime/F5-TTS/ckpts`.
- Assembles a safe Triton model repository at `/home/pmpg/rayme/f5-triton-runtime/model_repo_cpuipc_18000`.
- Launches Triton on host ports `18000/18001/18002` and runs an end-to-end HTTP synthesis smoke test.

## Investigation Trail

- Confirmed that F5's documented fast path is containerized Triton + TensorRT-LLM, not a plain Python package install.
- Confirmed that `docker.exe` on Windows initially failed because Docker Desktop's Linux engine was not running.
- Confirmed that once Docker Desktop was started, `docker` became available inside Ubuntu WSL and could talk to the `docker-desktop` Linux engine.
- Hit a non-interactive SSH credential-helper failure when pulling a public image from WSL; mitigated by using a fixed empty Docker config at `/home/pmpg/rayme/docker-config-public/config.json`.
- Confirmed that the original Docker Desktop engine path still stalled on pulls before the Desktop update, even though normal WSL internet access was fine.
- Installed `docker.io` and `nvidia-container-toolkit` inside Ubuntu and started a separate native daemon on `unix:///home/pmpg/rayme/docker-native/docker.sock`.
- Confirmed that the native WSL daemon can pull public images and run `nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` successfully on the RTX 3060.
- After Docker Desktop was updated to `4.70.0`, confirmed that the Desktop engine now also pulls public images and runs the same GPU smoke container successfully from Ubuntu WSL.
- Cloned `https://github.com/SWivid/F5-TTS.git` to `/home/pmpg/rayme/f5-triton-runtime/F5-TTS` so the runtime can be launched from a fixed workspace without using the stock compose command.
- Confirmed that the official prebuilt image `soar97/triton-f5-tts:24.12` reaches `TensorRT-LLM 0.16.0`, `torch 2.5.1+cu124`, and `tritonserver 2.53.0` in-container on the RTX 3060.
- Ran F5 runtime stage `0` and persisted `model_1250000.safetensors` plus `vocab.txt` under `/home/pmpg/rayme/f5-triton-runtime/F5-TTS/ckpts/F5TTS_v1_Base`.
- Ran F5 runtime stage `1` and persisted `trtllm_ckpt/` plus `trtllm_engine/rank0.engine`; the TensorRT-LLM engine build completed in about `00:01:21`.
- Found that the prebuilt image is missing `vocos`, so stage `2` only succeeds after `pip install vocos`; persisted `vocos_vocoder.onnx` and `vocos_vocoder.plan`.
- Avoided the stock stage `3` path because `run.sh` uses `rm -r $MODEL_REPO`; instead assembled a fixed safe repo at `/home/pmpg/rayme/f5-triton-runtime/model_repo_cpuipc_18000`.
- Found that the prebuilt image is also missing `rjieba`, so the server launch needs `pip install rjieba` before `tritonserver`.
- Found that the unpatched Python backend fails on the BLS call into `vocoder` with `Failed to open the cudaIpcHandle. error: invalid resource handle`, even with `--ipc=host`.
- Patched the generated `f5_tts` model repo copy to request the `vocoder` output with `preferred_memory=pb_utils.PreferredMemory(pb_utils.TRITONSERVER_MEMORY_CPU, 0)`, which avoids the failing CUDA IPC output path under this WSL deployment.
- Relaunched Triton with `--ipc=host --pid=host --shm-size=2g --ulimit memlock=-1 --ulimit stack=67108864` and verified a full HTTP inference request returns `200` and writes `/home/pmpg/rayme/f5-triton-runtime/client_http_out.wav`.

## Results

Verdict: `PASS`

Current status:

- The control path is validated two ways:
  - Docker Desktop `4.70.0` from Ubuntu WSL
  - Native WSL daemon on `unix:///home/pmpg/rayme/docker-native/docker.sock`
- GPU containers are confirmed on both paths via `nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`.
- The fixed runtime workspace exists at `/home/pmpg/rayme/f5-triton-runtime/F5-TTS`.
- The official F5 runtime image is present in Docker Desktop as `soar97/triton-f5-tts:24.12` and works from Ubuntu WSL.
- The checkpoint, TensorRT-LLM engine, and vocoder TensorRT plan are all built and persisted under `/home/pmpg/rayme/f5-triton-runtime/F5-TTS/ckpts`.
- The exact safe server path is now known and scripted:
  - build artifacts with `build-runtime-artifacts.sh`
  - assemble `model_repo_cpuipc_18000` with `assemble-model-repo.sh`
  - launch Triton with `launch-runtime-server.sh`
  - verify synthesis with `client-http-smoke.sh`
- The builder's short Phase 0 fixture is mirrored into `/home/pmpg/rayme/f5-triton-runtime/phase0-fixtures` with `sync-phase0-fixtures.sh` for apples-to-apples comparison work.
- The official prebuilt image has two defects relative to the documented path:
  - stage `2` needs `pip install vocos`
  - runtime launch needs `pip install rjieba`
- The stock F5 `run.sh` stage `3` is not acceptable for this workspace because it contains `rm -r $MODEL_REPO`; the safe assembled repo replaces that path without destructive cleanup.
- The WSL-specific runtime blocker was the Python backend's BLS handoff to `vocoder` via CUDA IPC. For this host, the working fix is to patch the generated model repo copy so the `vocoder` BLS response uses CPU preferred memory.
- End-to-end HTTP inference now succeeds on `192.168.1.199`:
  - server health: `READY` on `http://127.0.0.1:18000/v2/health/ready`
  - synthesis response: HTTP `200`
  - output audio: `/home/pmpg/rayme/f5-triton-runtime/client_http_out.wav`
  - output format: `24000 Hz`, `97280` frames, about `191 KB`
- Short-response comparison against the existing native F5 Phase 0 probe is now captured in `results/f5_short_ttfa_comparison.json`.
- Result for target text `Hey, got it.`:
  - native Windows F5 trials: `524.5 ms`, `520.1 ms`, `521.8 ms`; median `521.8 ms`
  - WSL Triton gRPC trials: `2801.2 ms`, `1806.2 ms`, `1813.4 ms`; median `1813.4 ms`
  - median delta: `+1291.6 ms`
  - median ratio: `3.475x` slower than native
- Practical conclusion: keep native Windows F5 for short-response TTFA. The current WSL Triton path is a validated deployment/runtime path, but it is not the latency winner for v1 short acknowledgments.
