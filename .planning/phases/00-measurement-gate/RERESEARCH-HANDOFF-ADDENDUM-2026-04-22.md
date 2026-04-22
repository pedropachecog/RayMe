# Phase 0 Re-Research Handoff Addendum

Read this alongside `RERESEARCH-HANDOFF.md`.

This addendum exists so the executor can use the correct backend access details without editing the original handoff file mid-run.

## Access Override

- Real backend machine: `OMEN-PC`
- Real backend LAN IP: `192.168.1.199`
- Real SSH user: `rayme-ssh`
- SSH/access details file: `.planning/phases/00-measurement-gate/BACKEND-SSH-199.md`
- Canonical persisted private key path: `.local/phase0-ssh/rayme_omen_phase0_ed25519`
- Canonical persisted public key path: `.local/phase0-ssh/rayme_omen_phase0_ed25519.pub`
- Runtime bootstrap script: `./scripts/bootstrap-rayme-ssh.sh`
- Preferred local alias: `rayme-ssh`

Do not probe the local Codex workstation or the old `pedro-2023` machine.
Do not store persistent keys or SSH state in `/tmp`.
Do not assume `/home/agent/.ssh` survives a fresh `containme` session.

## Executor Instruction

Before doing any more backend probing or Phase 0 execution work:

1. Read `.planning/phases/00-measurement-gate/BACKEND-SSH-199.md`
2. Verify the canonical repo-local key exists at `.local/phase0-ssh/rayme_omen_phase0_ed25519`
3. Run `./scripts/bootstrap-rayme-ssh.sh restore`
4. Use the exact verified command from that file, or the `rayme-ssh` alias once the restore step succeeds
5. Verify remote output includes `OMEN-PC`, `omen-pc\rayme-ssh`, `Python 3.10.8`, and `NVIDIA GeForce RTX 3060, 12288 MiB, 560.94`
6. Continue Phase 0 work against `192.168.1.199`

If step 2 fails because the repo-local key is missing, stop and restore that exact key path on the bind-mounted repo. Do not generate a new key unless the user explicitly decides to rotate credentials.

## Phase 0 Reality Check

Confirmed backend facts already established from the corrected research:

- GPU: RTX 3060 12 GB
- Host: `OMEN-PC` / `192.168.1.199`
- Only Python 3.10.8 is installed today
- `py -3.11` is missing
- `tailscale` is missing
- `ollama` and `llama-server` are missing
- `nvcc` 11.7 is present
- `cl.exe` is not on PATH

Those facts are already reflected in the rewritten `00-RESEARCH.md` and the patched Phase 0 plan files. This addendum is only to prevent executor confusion about which machine and SSH path to use.
