# Backend SSH Access: `192.168.1.199`

Use this file for direct executor access to the real Phase 0 backend.

## Target

- Hostname: `OMEN-PC`
- LAN IP: `192.168.1.199`
- SSH user: `rayme-ssh`
- Account type: standard local user, non-admin

## Durable Local Key

This key was generated specifically for Phase 0 executor access and stored outside the repo:

- Private key path: `/home/agent/.ssh/rayme_omen_phase0_ed25519`
- Public key path: `/home/agent/.ssh/rayme_omen_phase0_ed25519.pub`

Public key contents:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDNB/K4ffeW0Zqi/3qiYeejfyRu7qUUvw2vvvGFTCD+m rayme-phase0-executor-2026-04-22
```

## Persistence Rule

- Do not put persistent SSH material in `/tmp` or any other disposable path.
- The private key must live at `/home/agent/.ssh/rayme_omen_phase0_ed25519`.
- The public key must live at `/home/agent/.ssh/rayme_omen_phase0_ed25519.pub`.
- Persist instructions, public keys, fingerprints, and recovery steps in repo docs such as this file.
- `/tmp` may be used only for throwaway diagnostics that are safe to lose.

## SSH Command

Preferred command:

```bash
ssh -i /home/agent/.ssh/rayme_omen_phase0_ed25519 -o StrictHostKeyChecking=no rayme-ssh@192.168.1.199
```

Preferred alias after local setup:

```bash
ssh rayme-ssh
```

Quick connectivity test:

```bash
ssh -i /home/agent/.ssh/rayme_omen_phase0_ed25519 -o StrictHostKeyChecking=no rayme-ssh@192.168.1.199 whoami
```

Expected output:

```text
omen-pc\rayme-ssh
```

## Important Note

The earlier throwaway key was created under `/tmp` and is no longer available locally. This durable key is the replacement.

As of 2026-04-22 in the current Codex session:

- `~/.ssh/known_hosts` contains the backend host key for `192.168.1.199`
- `/home/agent/.ssh/rayme_omen_phase0_ed25519` exists locally
- `/home/agent/.ssh/config` should contain a `Host rayme-ssh` alias pointing at this key and backend
- SSH has been validated from Codex using real remote commands, not just a connection banner

If SSH later fails with `Permission denied`, do not generate another key by default. First verify that the existing documented key path still exists locally and that the public key above is still present in `C:\Users\rayme-ssh\.ssh\authorized_keys` on `OMEN-PC`.

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

icacls $sshDir  /inheritance:r /grant:r "${acct}:(OI)(CI)F" /grant:r "Administrators:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F"
icacls $keyFile /inheritance:r /grant:r "${acct}:F"         /grant:r "Administrators:F"         /grant:r "SYSTEM:F"

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

## Host Key Fingerprint

Server ED25519 host key fingerprint:

```text
SHA256:3hOdeVRPnjigg7pk9qyJnAg42N7zqkOva+3TvzixKKw
```

Local executor key fingerprint:

```text
SHA256:JVuVSKsC2aYOf3ApjfoORGuFaRdqSZsLzUPODixcIXg
```

## Verified Command

This command was executed successfully from Codex on 2026-04-22:

```bash
ssh -i /home/agent/.ssh/rayme_omen_phase0_ed25519 -o StrictHostKeyChecking=no rayme-ssh@192.168.1.199 "cmd /c \"hostname & whoami & python --version & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader\""
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
- Do not assume admin access.
- If an admin-only command is needed later, ask the user to run that specific command locally on `OMEN-PC`.
