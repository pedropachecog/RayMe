# Spike Conventions

Patterns and stack choices established across spike sessions. New spikes follow these unless the question requires otherwise.

## Stack

- Remote Linux probes run from the repo via Bash, `scripts/bootstrap-rayme-ssh.sh`, Windows OpenSSH, and direct `wsl -d Ubuntu -e ...` commands.
- Linux-side work roots live in Ubuntu under `/home/pmpg/...`.
- The reusable CUDA env for `OMEN-PC` WSL work lives at `/home/pmpg/rayme/.venv-cu121`.
- The current validated WSL userspace for accelerator work on `OMEN-PC` is Ubuntu `22.04.5 LTS` with glibc `2.35`.

## Structure

- Use fixed absolute Linux paths in remote WSL commands.
- Keep probe artifacts under `.planning/spikes/<NNN>-<name>/`.
- Prefer one rerunnable shell script per fact-gathering spike.
- When a WSL env needs CUDA builds, pin `CUDA_HOME` explicitly instead of trusting the default `/usr/local/cuda` symlink.

## Patterns

- For `OMEN-PC` WSL access, connect as `pmpg`, not `rayme-ssh`.
- Avoid UNC WSL paths from the non-interactive SSH session.
- Treat `Failed to translate ...` PATH warnings from WSL as noise unless command behavior actually fails.
- For the current WSL accelerator env, use `CUDA_HOME=/usr/local/cuda-12.1`.
- Add the PyTorch shared library directory to `LD_LIBRARY_PATH` when testing compiled CUDA extensions from the WSL venv.
- Never run `rm -rf`.
- Never delete files or directories through variable-expanded paths.

## Tools & Libraries

- Use `/usr/lib/wsl/lib/nvidia-smi` as a fallback if `nvidia-smi` is not on `PATH` inside WSL.
- `torch 2.5.1+cu121`, `triton 3.1.0`, `deepspeed 0.18.9`, and `flash-attn 2.8.3` work in `/home/pmpg/rayme/.venv-cu121`.
- `flash-attn 2.8.3` imports successfully in `/home/pmpg/rayme/.venv-cu121` after the WSL distro upgrade to Ubuntu `22.04.5 LTS`.
