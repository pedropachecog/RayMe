---
spike: 001
name: omen-pc-wsl-gpu-path
type: standard
validates: "Given OMEN-PC Ubuntu WSL2, when it is probed over SSH as pmpg with a fixed Linux work root, then GPU visibility and baseline build readiness are known."
verdict: PARTIAL
related: []
tags: [wsl, gpu, omen-pc, ssh]
---

# Spike 001: OMEN-PC WSL GPU Path

## What This Validates

Given `OMEN-PC` Ubuntu WSL2, when it is probed over SSH as `pmpg` with the fixed Linux work root `/home/pmpg/rayme`, then GPU visibility and baseline build readiness are known before attempting Linux-only optimization work.

## Research

Docs checked on 2026-04-22:

- NVIDIA CUDA on WSL User Guide: WSL2 GPU acceleration is supported through the Windows NVIDIA driver; do not install a Linux NVIDIA driver inside WSL; `nvidia-smi` has a limited feature set in WSL; use the WSL-Ubuntu CUDA toolkit path if a toolkit is later needed.
- Microsoft Learn, Working across Windows and Linux file systems: for fastest performance when working in Linux, keep project files in the Linux filesystem under `/home/<user>/...`, not `/mnt/c/...`.

Approach comparison:

| Approach | Tool/Path | Pros | Cons | Status |
|----------|-----------|------|------|--------|
| Native Windows backend | `rayme-ssh` on `OMEN-PC` | Already validated for current Phase 0 probes | Linux-first optimization stacks remain awkward or unsupported | Baseline only |
| WSL from `rayme-ssh` | `ssh rayme-ssh`, then `wsl ...` | Reuses existing SSH account | Invalid path: this Windows user sees no installed distro | Rejected |
| WSL from `pmpg` | `ssh rayme-pmpg`, then `wsl -d Ubuntu -e ...` | Reaches the real Ubuntu distro, keeps work in Linux FS, fits NVIDIA/Microsoft guidance | Requires separate admin-backed SSH auth and WSL bootstrap | Chosen |

Chosen approach: direct `pmpg` SSH into Windows OpenSSH, followed by direct `wsl -d Ubuntu --cd /home/pmpg -e bash -s` with fixed Linux paths.

Sources:

- https://docs.nvidia.com/cuda/wsl-user-guide/
- https://learn.microsoft.com/en-us/windows/wsl/filesystems

## How to Run

```bash
.planning/spikes/001-omen-pc-wsl-gpu-path/probe.sh
```

Bootstrap the reusable CUDA 12.1 WSL env:

```bash
.planning/spikes/001-omen-pc-wsl-gpu-path/bootstrap-cu121-env.sh
```

## What to Expect

- Restores the persisted `rayme-pmpg` SSH alias.
- Enters the `Ubuntu` WSL distro as `pmpg`.
- Creates and verifies `/home/pmpg/rayme`.
- Prints distro, GPU, Python, and baseline toolchain status.
- Prints whether PyTorch is already installed and whether CUDA is visible from it.

## Investigation Trail

- Verified that `rayme-ssh` cannot enter WSL on `192.168.1.199`; `wsl -l -v` from that Windows account reports no installed distributions.
- Verified locally with the user that `omen-pc\\pmpg` does see `Ubuntu` on WSL2 and that `wsl ls /` succeeds there.
- Fixed SSH auth for `pmpg` by placing the executor key in `C:\\ProgramData\\ssh\\administrators_authorized_keys`, because `pmpg` is in the local `Administrators` group.
- Confirmed direct WSL access over SSH as `pmpg`, then created `/home/pmpg/rayme-wsl-probe` as the first fixed-path validation.
- Created the real work root `/home/pmpg/rayme` and ran a second probe for GPU, Python, and build-tool prerequisites relevant to later DeepSpeed / FlashAttention-style work.
- Built a reusable WSL env at `/home/pmpg/rayme/.venv-cu121` using `/home/pmpg/miniconda3/bin/python`, installed `torch 2.5.1+cu121`, and verified CUDA visibility on the RTX 3060.
- Installed `deepspeed 0.18.9` in that env and verified that it imports successfully alongside CUDA-enabled PyTorch.
- Attempted `flash-attn 2.8.3` in the same env with `CUDA_HOME=/usr/local/cuda-12.1` and `MAX_JOBS=4`; wheel build succeeded but import initially failed on Ubuntu 20.04 because the distro runtime floor was too old.
- Upgraded the WSL distro in place from Ubuntu `20.04.6 LTS` to `22.04.5 LTS`, verified glibc `2.35`, and re-ran the same env import checks.

## Results

Verdict: `PARTIAL`

Key findings:

- The remote control path is validated: `ssh rayme-pmpg` can run commands inside `Ubuntu` WSL2.
- The fixed Linux work root `/home/pmpg/rayme` exists and is the correct location for future Linux-side work.
- GPU visibility is present inside WSL: `NVIDIA GeForce RTX 3060, 12288 MiB, 560.94`.
- The distro is `Ubuntu 20.04.6 LTS` with kernel `6.6.87.2-microsoft-standard-WSL2`.
- The system Python is `3.8.10`, but the reusable accelerator env now exists at `/home/pmpg/rayme/.venv-cu121` and uses Python `3.10.9`.
- That env now contains `torch 2.5.1+cu121`, `torchvision 0.20.1+cu121`, `torchaudio 2.5.1+cu121`, `deepspeed 0.18.9`, `ninja`, and `cmake`.
- CUDA is visible from that env: `torch.cuda.is_available() == true` and the detected device is `NVIDIA GeForce RTX 3060`.
- XTTS's documented DeepSpeed path is now practical on this host via the WSL env.
- After the distro upgrade to Ubuntu `22.04.5 LTS`, glibc is now `2.35` and `flash-attn 2.8.3` imports successfully in `/home/pmpg/rayme/.venv-cu121`.
- That removes the old WSL userspace blocker for the Qwen/FlashAttention path on this host.
- The recurring `Failed to translate 'D:\\Pedro\\Programs\\python\\...'` lines are environment propagation warnings from WSL startup; they did not block the probe.

Observed output:

```text
wsl: Failed to translate 'D:\Pedro\Programs\python\'
wsl: Failed to translate 'D:\Pedro\Programs\python\Scripts'
linux_user:pmpg
linux_pwd:/home/pmpg
linux_work_root:/home/pmpg/rayme
drwxr-xr-x 2 pmpg pmpg 4096 Apr 22 19:34 /home/pmpg/rayme
PRETTY_NAME="Ubuntu 20.04.6 LTS"
NVIDIA GeForce RTX 3060, 12288 MiB, 560.94
Python 3.8.10
{"python_executable": "/usr/bin/python3", "torch_error": "No module named 'torch'", "torch_installed": false}
6.6.87.2-microsoft-standard-WSL2
git version 2.25.1
pip 20.0.2 from /usr/lib/python3/dist-packages/pip (python 3.8)
gcc (Ubuntu 9.4.0-1ubuntu1~20.04.2) 9.4.0
g++ (Ubuntu 9.4.0-1ubuntu1~20.04.2) 9.4.0
cmake:missing
ninja:missing
libcuda:present
```

Impact:

- WSL on `OMEN-PC` is now a viable execution base for both XTTS + DeepSpeed and Qwen + FlashAttention experiments through `/home/pmpg/rayme/.venv-cu121`.
- The distro upgrade removed the glibc blocker that previously made the built FlashAttention module unusable on this host.
- The next real step is no longer distro surgery. It is to run the actual Linux-side TTS/Qwen optimization probes against this env.

Accelerator env verification:

```text
{"cuda_available": true, "device_count": 1, "device_name": "NVIDIA GeForce RTX 3060", "torch_cuda_version": "12.1", "torch_version": "2.5.1+cu121"}
{"deepspeed_version": "0.18.9", "torch_version": "2.5.1+cu121", "cuda_available": true}
```

FlashAttention failure details:

```text
ImportError: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.32' not found
/lib/x86_64-linux-gnu/libstdc++.so.6: version `GLIBCXX_3.4.29' not found
/lib/x86_64-linux-gnu/libstdc++.so.6: version `CXXABI_1.3.13' not found
```

Post-upgrade verification:

```text
PRETTY_NAME="Ubuntu 22.04.5 LTS"
ldd (Ubuntu GLIBC 2.35-0ubuntu3.13) 2.35
{"cuda_available": true, "device_name": "NVIDIA GeForce RTX 3060", "flash_attn_version": "2.8.3", "torch_version": "2.5.1+cu121"}
{"cuda_available": true, "deepspeed_version": "0.18.9", "torch_version": "2.5.1+cu121"}
```
