# Backend SSH Access: `192.168.1.199`

Use this file for direct executor access to the real Phase 0 backend.

## Target

- Hostname: `OMEN-PC`
- LAN IP: `192.168.1.199`
- SSH user: `rayme-ssh`
- Account type: standard local user, non-admin
- WSL Ubuntu owner: `pmpg`
- Verified on `2026-04-22`: `rayme-ssh` cannot enter WSL on this host because `wsl ls /` reports no installed distributions for that Windows account, while `pmpg` sees `Ubuntu` on WSL2 and `wsl ls /` works.

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
ssh rayme-pmpg "wsl --cd ~ -e bash -lc 'whoami && pwd && ls /'"
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

If WSL work is required, verify that the same public key is also present in `C:\Users\pmpg\.ssh\authorized_keys` and connect as `pmpg`.

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

For `pmpg`, use the same key but write it to that account's SSH directory instead:

```powershell
$user = 'pmpg'
$acct = "${env:COMPUTERNAME}\${user}"
$key  = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvaejBEFEdS8W4Dlfsbv3cOleizp7sKfcdKssWyI9ZV rayme-phase0-executor-2026-04-22'

$sshDir  = "C:\Users\$user\.ssh"
$keyFile = "$sshDir\authorized_keys"

New-Item -ItemType Directory -Force $sshDir | Out-Null
Set-Content -Path $keyFile -Value $key -Encoding ascii

cmd /c icacls "$sshDir"  /inheritance:r /grant:r "${acct}:(OI)(CI)F" /grant:r "Administrators:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F"
cmd /c icacls "$keyFile" /inheritance:r /grant:r "${acct}:F"         /grant:r "Administrators:F"         /grant:r "SYSTEM:F"
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

## Scope Reminder

- Use `rayme-ssh` for probe and measurement work.
- Use `pmpg` specifically for WSL-backed work on `OMEN-PC`.
- If `ssh rayme-ssh` fails because the key is missing, restore the canonical repo-local key into `.local/phase0-ssh/` once, then rerun `./scripts/bootstrap-rayme-ssh.sh restore`.
- Do not assume admin access.
- If an admin-only command is needed later, ask the user to run that specific command locally on `OMEN-PC`.
