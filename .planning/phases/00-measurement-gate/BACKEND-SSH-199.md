# Backend SSH Access: `192.168.1.199`

Use this file for direct executor access to the real Phase 0 backend.

## Target

- Hostname: `OMEN-PC`
- LAN IP: `192.168.1.199`
- SSH user: `rayme-ssh`
- Account type: standard local user, non-admin
- WSL Ubuntu owner: `pmpg`
- Verified on `2026-04-22`: `rayme-ssh` cannot enter WSL on this host because `wsl ls /` reports no installed distributions for that Windows account, while `pmpg` sees `Ubuntu` on WSL2 and `wsl ls /` works.
- Verified on `2026-04-22`: SSH as `pmpg` works after installing the executor key into `C:\ProgramData\ssh\administrators_authorized_keys` because `pmpg` is in the local `Administrators` group.

## Hard Safety Guardrails

- Never run `rm -rf` in this project or on any connected backend/WSL host.
- Never delete files or directories through a variable-expanded path such as `rm -rf "$TARGET"` or `rm -rf "$DIR"/*`.
- If cleanup is ever required, use an explicit fixed path, print the exact absolute path first, and ask the user before any destructive command.
- Prefer non-destructive alternatives such as moving aside, renaming, or listing for inspection.
- Treat these rules as hard guardrails motivated by a prior destructive WSL loss event.

## Canonical Key Storage

`containme` persists the repo bind mount and `/home/agent/.codex`, but it does **not** persist `/home/agent/.ssh`. Treat `~/.ssh` as a disposable runtime cache, not as the durable source of truth.

Canonical persisted location on the repo bind mount:

- Private key path: `.local/phase0-ssh/rayme_omen_phase0_ed25519`
- Public key path: `.local/phase0-ssh/rayme_omen_phase0_ed25519.pub`
- Bootstrap script: `./scripts/bootstrap-rayme-ssh.sh`

Runtime location recreated each session:

- Private key path: `/home/agent/.ssh/rayme_omen_phase0_ed25519`
- Public key path: `/home/agent/.ssh/rayme_omen_phase0_ed25519.pub`

Public key contents:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvaejBEFEdS8W4Dlfsbv3cOleizp7sKfcdKssWyI9ZV rayme-phase0-executor-2026-04-22
```

## Persistence Rule

- Do not put persistent SSH material in `/tmp` or any other disposable path.
- Do not treat `/home/agent/.ssh` as durable under `containme`; it is session-local.
- The canonical private key must live at `.local/phase0-ssh/rayme_omen_phase0_ed25519` on the repo bind mount.
- The canonical public key must live at `.local/phase0-ssh/rayme_omen_phase0_ed25519.pub` on the repo bind mount.
- `./scripts/bootstrap-rayme-ssh.sh restore` must recreate the runtime `~/.ssh` files at the start of a fresh container session.
- `.local/` is gitignored, so the key persists on disk without being committed.
- `/tmp` may be used only for throwaway diagnostics that are safe to lose.

## Bootstrap + SSH Command

Restore the runtime SSH state first:

```bash
./scripts/bootstrap-rayme-ssh.sh restore
```

To target the WSL-owning `pmpg` account with the same persisted key:

```bash
RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg ./scripts/bootstrap-rayme-ssh.sh restore
ssh rayme-pmpg whoami
```

Preferred command:

```bash
ssh rayme-ssh
```

Preferred alias after local setup:

```bash
ssh rayme-ssh
```

Quick connectivity test:

```bash
./scripts/bootstrap-rayme-ssh.sh connect-test
```

WSL connectivity test once `pmpg` key auth is added:

```bash
RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg ./scripts/bootstrap-rayme-ssh.sh restore
ssh rayme-pmpg "wsl -d Ubuntu -e sh -c 'whoami && pwd && ls /'"
```

Verified WSL probe directory creation:

```bash
RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg ./scripts/bootstrap-rayme-ssh.sh restore
ssh rayme-pmpg "wsl -d Ubuntu --cd /home/pmpg -e sh -c 'mkdir -p /home/pmpg/rayme-wsl-probe && readlink -f /home/pmpg/rayme-wsl-probe && ls -ld /home/pmpg/rayme-wsl-probe'"
```

Expected output:

```text
omen-pc\rayme-ssh
```

## Important Note

The earlier throwaway key was created under `/tmp` and is no longer available locally. The next mistake was assuming `/home/agent/.ssh` was durable. Under `containme`, that path is disposable across sessions.

From now on:

- `.local/phase0-ssh/` is the persistent source of truth
- `/home/agent/.ssh/` is a runtime copy rebuilt by `./scripts/bootstrap-rayme-ssh.sh restore`
- `known_hosts` and the `rayme-ssh` alias are runtime artifacts, not durable state
- SSH is considered ready only after the restore step and a real remote verification command

If SSH later fails with `Permission denied`, do not generate another key by default. First verify that `.local/phase0-ssh/rayme_omen_phase0_ed25519` exists on the repo bind mount, run `./scripts/bootstrap-rayme-ssh.sh restore`, and then verify that the public key above is still present in `C:\Users\rayme-ssh\.ssh\authorized_keys` on `OMEN-PC`.

If WSL work is required, connect as `pmpg`. Because `pmpg` is in the local `Administrators` group on `OMEN-PC`, Windows OpenSSH reads the key from `C:\ProgramData\ssh\administrators_authorized_keys`, not from `C:\Users\pmpg\.ssh\authorized_keys`.

## One-Time Windows Fix If Key Auth Fails

Run this on `192.168.1.199` in PowerShell as Administrator:

```powershell
$user = 'rayme-ssh'
$acct = "${env:COMPUTERNAME}\${user}"
$key  = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDNB/K4ffeW0Zqi/3qiYeejfyRu7qUUvw2vvvGFTCD+m rayme-phase0-executor-2026-04-22'

$sshDir  = "C:\Users\$user\.ssh"
$keyFile = "$sshDir\authorized_keys"
$config  = 'C:\ProgramData\ssh\sshd_config'

New-Item -ItemType Directory -Force $sshDir | Out-Null
Set-Content -Path $keyFile -Value $key -Encoding ascii

cmd /c icacls "$sshDir"  /inheritance:r /grant:r "${acct}:(OI)(CI)F" /grant:r "Administrators:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F"
cmd /c icacls "$keyFile" /inheritance:r /grant:r "${acct}:F"         /grant:r "Administrators:F"         /grant:r "SYSTEM:F"

$lines = Get-Content $config
$filtered = foreach ($line in $lines) {
  if ($line -ne 'Match User rayme-ssh' -and $line -ne '    AuthorizedKeysFile C:/Users/rayme-ssh/.ssh/authorized_keys') {
    $line
  }
}
$filtered += ''
$filtered += 'Match User rayme-ssh'
$filtered += '    AuthorizedKeysFile C:/Users/rayme-ssh/.ssh/authorized_keys'

Set-Content -Path $config -Value $filtered -Encoding ascii
& "$env:WINDIR\System32\OpenSSH\sshd.exe" -t -f $config
Restart-Service sshd
```

For `pmpg`, use the same key but write it to the administrators key file instead:

```powershell
$key  = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvaejBEFEdS8W4Dlfsbv3cOleizp7sKfcdKssWyI9ZV rayme-phase0-executor-2026-04-22'
$file = 'C:\ProgramData\ssh\administrators_authorized_keys'

New-Item -ItemType Directory -Force C:\ProgramData\ssh | Out-Null
Set-Content -Path $file -Value $key -Encoding ascii
cmd /c icacls "$file" /inheritance:r /grant:r "Administrators:F" /grant:r "SYSTEM:F"
Restart-Service sshd
```

## Host Key Fingerprint

Server ED25519 host key fingerprint:

```text
SHA256:3hOdeVRPnjigg7pk9qyJnAg42N7zqkOva+3TvzixKKw
```

Local executor key fingerprint:

```text
SHA256:NqvfpOxkdbd7hVWdTNC54xJjbg/G+ib+R/Lr1z5VAvU
```

## Verified Command

This command was executed successfully from Codex on 2026-04-22:

```bash
./scripts/bootstrap-rayme-ssh.sh restore
ssh rayme-ssh "cmd /c \"hostname & whoami & python --version & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader\""
```

Observed output:

```text
OMEN-PC
omen-pc\rayme-ssh
Python 3.10.8
NVIDIA GeForce RTX 3060, 12288 MiB, 560.94
```

This command was also executed successfully from Codex on 2026-04-22 for WSL-backed access:

```bash
RAYME_SSH_ALIAS=rayme-pmpg RAYME_SSH_USER=pmpg ./scripts/bootstrap-rayme-ssh.sh restore
ssh rayme-pmpg "wsl -d Ubuntu --cd /home/pmpg -e sh -c 'mkdir -p /home/pmpg/rayme-wsl-probe && echo linux_user:\$(whoami) && echo linux_probe:\$(readlink -f /home/pmpg/rayme-wsl-probe) && ls -ld /home/pmpg/rayme-wsl-probe'"
```

Observed output:

```text
wsl: Failed to translate 'D:\Pedro\Programs\python\'
wsl: Failed to translate 'D:\Pedro\Programs\python\Scripts'
linux_user:pmpg
linux_probe:/home/pmpg/rayme-wsl-probe
drwxr-xr-x 2 pmpg pmpg 4096 Apr 22 19:09 /home/pmpg/rayme-wsl-probe
```

Those `Failed to translate ...` lines are PATH translation warnings from Windows environment propagation. They did not block WSL execution.

Verified WSL accelerator env bootstrap on 2026-04-23:

```bash
.planning/spikes/001-omen-pc-wsl-gpu-path/bootstrap-cu121-env.sh
```

Observed result:

```text
{"cuda_available": true, "deepspeed_version": "0.18.9", "device_count": 1, "device_name": "NVIDIA GeForce RTX 3060", "flash_attn_version": "2.8.3", "torch_cuda_version": "12.1", "torch_version": "2.5.1+cu121", "triton_version": "3.1.0"}
```

WSL accelerator env facts:

- Reusable env path: `/home/pmpg/rayme/.venv-cu121`
- Current validated distro/userspace: Ubuntu `22.04.5 LTS`, glibc `2.35`
- CUDA toolkit path to pin explicitly: `/usr/local/cuda-12.1`
- Do not trust the default `nvcc` on `PATH`; `/usr/local/cuda` still resolves to an older CUDA 10.1 toolchain on this host.
- `triton 3.1.0` is provided through `torch 2.5.1+cu121` in this env.
- When testing compiled CUDA extensions from the WSL env, include the PyTorch library directory in `LD_LIBRARY_PATH`:

```bash
export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:/home/pmpg/rayme/.venv-cu121/lib/python3.10/site-packages/torch/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
```

Validated F5 Triton/TensorRT-LLM path on 2026-04-23:

- Runtime image: `soar97/triton-f5-tts:24.12`
- Fixed workspace: `/home/pmpg/rayme/f5-triton-runtime/F5-TTS`
- Safe model repo: `/home/pmpg/rayme/f5-triton-runtime/model_repo_cpuipc_18000`
- Live host ports: `18000` HTTP, `18001` gRPC, `18002` metrics
- End-to-end smoke output: `/home/pmpg/rayme/f5-triton-runtime/client_http_out.wav`
- Repro scripts:
  - `.planning/spikes/002-f5-triton-trtllm-wsl-path/build-runtime-artifacts.sh`
  - `.planning/spikes/002-f5-triton-trtllm-wsl-path/assemble-model-repo.sh`
  - `.planning/spikes/002-f5-triton-trtllm-wsl-path/launch-runtime-server.sh`
  - `.planning/spikes/002-f5-triton-trtllm-wsl-path/client-http-smoke.sh`

Known runtime quirks on this host:

- The prebuilt F5 image is missing `vocos` for stage `2`, so the artifact build path installs it ad hoc before exporting the vocoder plan.
- The prebuilt F5 image is missing `rjieba`, so the launch path installs it ad hoc before starting `tritonserver`.
- The unpatched Python backend fails on the BLS hop into `vocoder` with `Failed to open the cudaIpcHandle. error: invalid resource handle` under WSL.
- The safe model repo works around that by forcing the `vocoder` BLS response to `preferred_memory=pb_utils.PreferredMemory(pb_utils.TRITONSERVER_MEMORY_CPU, 0)`.
- Avoid the stock F5 `run.sh` stage `3` because it contains `rm -r $MODEL_REPO`; the safe assembled repo replaces that destructive path.

Measured short-response comparison versus native F5 on 2026-04-23:

- Comparison artifact: `.planning/spikes/002-f5-triton-trtllm-wsl-path/results/f5_short_ttfa_comparison.json`
- Target text: `Hey, got it.`
- Native Windows F5 trials: `524.5 ms`, `520.1 ms`, `521.8 ms`
- WSL Triton gRPC trials: `2801.2 ms`, `1806.2 ms`, `1813.4 ms`
- Native median TTFA: `521.8 ms`
- WSL Triton gRPC median TTFA: `1813.4 ms`
- Median gap: `+1291.6 ms`
- Median ratio: `3.475x` slower than native
- Recommendation: keep native Windows F5 for short-response TTFA; do not promote the current WSL Triton path as the v1 latency path for short acknowledgments.

FlashAttention status in WSL on this host:

- The WSL distro was upgraded in place to Ubuntu `22.04.5 LTS`.
- glibc is now `2.35` (`ldd (Ubuntu GLIBC 2.35-0ubuntu3.13) 2.35`).
- `flash-attn 2.8.3` now imports successfully in `/home/pmpg/rayme/.venv-cu121`.
- Practical implication: both XTTS + DeepSpeed and the Qwen/FlashAttention path are now viable in WSL on this host, and the bootstrap script recreates the validated accelerator stack directly.

## WSL Path Rule

- From non-interactive SSH sessions, prefer direct `wsl -d Ubuntu -e sh -c '...'` commands with fixed Linux paths such as `/home/pmpg/...`.
- Do not rely on `\\wsl.localhost\Ubuntu\...` or `\\wsl$\Ubuntu\...` from the remote SSH session; they were not reliably available during the 2026-04-22 verification.

## Scope Reminder

- Use `rayme-ssh` for probe and measurement work.
- Use `pmpg` specifically for WSL-backed work on `OMEN-PC`.
- If `ssh rayme-ssh` fails because the key is missing, restore the canonical repo-local key into `.local/phase0-ssh/` once, then rerun `./scripts/bootstrap-rayme-ssh.sh restore`.
- Do not assume admin access.
- If an admin-only command is needed later, ask the user to run that specific command locally on `OMEN-PC`.
