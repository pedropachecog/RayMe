# Spike Conventions

Patterns and stack choices established across spike sessions. New spikes follow these unless the question requires otherwise.

## Stack

- Remote Linux probes run from the repo via Bash, `scripts/bootstrap-rayme-ssh.sh`, Windows OpenSSH, and direct `wsl -d Ubuntu -e ...` commands.
- Linux-side work roots live in Ubuntu under `/home/pmpg/...`.

## Structure

- Use fixed absolute Linux paths in remote WSL commands.
- Keep probe artifacts under `.planning/spikes/<NNN>-<name>/`.
- Prefer one rerunnable shell script per fact-gathering spike.

## Patterns

- For `OMEN-PC` WSL access, connect as `pmpg`, not `rayme-ssh`.
- Avoid UNC WSL paths from the non-interactive SSH session.
- Treat `Failed to translate ...` PATH warnings from WSL as noise unless command behavior actually fails.
- Never run `rm -rf`.
- Never delete files or directories through variable-expanded paths.

## Tools & Libraries

- Use `/usr/lib/wsl/lib/nvidia-smi` as a fallback if `nvidia-smi` is not on `PATH` inside WSL.
