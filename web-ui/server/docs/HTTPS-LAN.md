# Phase 1 HTTPS LAN Runbook

Phase 1 uses a reusable LAN development certificate set. Direct LAN IP HTTPS is
sufficient for Web UI and AI-backend checks. `rayme.local` is optional unless
DNS/mDNS is configured on the Android device and LAN.

## Certificate

The canonical reusable Phase 1 certificate material is intentionally kept out of
git but persisted under the repo-local `.local/` tree:

```text
.local/phase1-tls/rayme-phase1-rootCA.pem
.local/phase1-tls/rayme-phase1-rootCA-key.pem
.local/phase1-tls/rayme.local+1.pem
.local/phase1-tls/rayme.local+1-key.pem
```

The active Phase 1 root CA profile must include critical `CA:TRUE` basic
constraints and critical `keyCertSign, cRLSign` key usage for Android Chrome
trust compatibility. The active serving cert is valid from
`2026-04-24` through `2027-04-24` and covers `rayme.local`, `localhost`,
`192.168.1.199`, and `127.0.0.1`.

Current active fingerprints:

```text
Root CA SHA-256 fingerprint:
AE:57:76:5A:25:AF:38:D7:9E:17:73:E1:B4:28:C5:C2:17:F7:C8:D7:E5:45:9B:FB:AB:44:54:FE:38:41:06:D6

Root CA transfer-file SHA-256 hash:
9819c9661dfa5bb0b4d6251659029591f4e5b3e7250ef2d638b724c4f2ee00a1

Serving cert SHA-256 fingerprint:
46:85:09:B2:8E:75:D2:4F:0D:E2:6D:E3:EA:58:7A:DA:1A:A5:6D:C2:ED:85:C8:83:EC:7E:E9:06:9D:A5:E7:93
```

The same serving cert/key are mirrored on the backend host at:

```text
C:\Users\pmpg\rayme\phase1-tls\rayme-phase1-rootCA.pem
C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem
C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem
```

All agent-created Windows-side RayMe artifacts on `OMEN-PC` must live under
`C:\Users\pmpg\rayme\`. Do not create additional top-level directories in
`C:\Users\pmpg\`.

The canonical Windows-side runtime code location is a Git checkout:

```text
C:\Users\pmpg\rayme\RayMe\
```

Run `git status`, `git branch`, and `git rev-parse HEAD` there before starting
services so the backend runtime commit is explicit. Do not use copied partial
runtime trees as the normal sync mechanism. `C:\Users\pmpg\rayme\phase1-app\`
was a temporary copied staging tree from Plan 01-24 troubleshooting and is not
canonical.

Git sync must use the GitHub HTTPS remote. If fetch/pull prompts or fails on
`OMEN-PC`, fix Git Credential Manager instead of using copied trees or bundles:

```cmd
git config --global credential.helper manager
git config --global credential.credentialStore dpapi
```

Then clone or update the checkout:

```cmd
cd /d C:\Users\pmpg\rayme
git clone https://github.com/pedropachecog/RayMe.git RayMe
cd /d C:\Users\pmpg\rayme\RayMe
git fetch origin main
git pull --ff-only origin main
git status --short
git branch --show-current
git rev-parse --short HEAD
```

The certificate covers `rayme.local`, `localhost`, `192.168.1.199`, and
`127.0.0.1`. If Android Chrome does not already trust this Phase 1 root, install
`.local/phase1-tls/rayme-phase1-rootCA.pem` on the phone once and keep reusing
this cert set. Do not create per-session certificates.

For phone transfer during manual testing, `OMEN-PC` may run the temporary
`RayMePhase1CertTransfer` scheduled task, serving only the public root CA from
`C:\Users\pmpg\rayme\phase1-tls\` on port `8081`. Use the cache-busting filename
below when replacing an earlier bad Phase 1 root:

```text
http://192.168.1.199:8081/rayme-phase1-rootCA-20260424.crt
```

Use these paths from the backend Git checkout or the local repository root:

```env
RAYME_WEB_BIND_HOST=192.168.1.199
RAYME_WEB_PORT=8443
RAYME_WEB_PUBLIC_URL=https://192.168.1.199:8443
RAYME_TLS_CERT=C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem
RAYME_TLS_KEY=C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem
RAYME_ALLOWED_ORIGINS=https://192.168.1.199:8443
RAYME_AI_BACKEND_BASE_URL=https://192.168.1.199:9443
```

## Web UI

Run from the backend Git checkout after building the client:

```bash
npm --prefix web-ui/client run build
RAYME_WEB_BIND_HOST=192.168.1.199 \
RAYME_WEB_PORT=8443 \
RAYME_WEB_PUBLIC_URL=https://192.168.1.199:8443 \
RAYME_TLS_CERT=C:/Users/pmpg/rayme/phase1-tls/rayme.local+1.pem \
RAYME_TLS_KEY=C:/Users/pmpg/rayme/phase1-tls/rayme.local+1-key.pem \
RAYME_ALLOWED_ORIGINS=https://192.168.1.199:8443 \
RAYME_AI_BACKEND_BASE_URL=https://192.168.1.199:9443 \
uv run --project web-ui/server python web-ui/server/scripts/run_dev_https.py
```

Browser URL: `https://192.168.1.199:8443`.

For Phase 2 Voice Lab live checks, use the same reusable mkcert material and
canonical checkout, then open:

```text
https://192.168.1.199:8443/voice-lab
```

The matching Phase 2 AI backend health URL is:

```text
https://192.168.1.199:9443/health
```

On `OMEN-PC`, the current repeatable Phase 1 runtime uses Windows scheduled
tasks so the HTTPS services survive the SSH command that starts them:

```text
Task: RayMePhase1Web
Script: C:\Users\pmpg\rayme\start-web-ui.cmd
Logs: C:\Users\pmpg\rayme\logs\web-ui.run.log
URL: https://192.168.1.199:8443
```

The launcher must run from `C:\Users\pmpg\rayme\RayMe\`, set
`RAYME_DATABASE_URL` with the async SQLite driver
`sqlite+aiosqlite:///C:/Users/pmpg/rayme/RayMe/web-ui/server/data/rayme.sqlite3`,
and call `web-ui\server\scripts\run_dev_https.py` with only the supported
`--host`, `--port`, `--cert`, and `--key` arguments. Do not pass a static-dir
argument; the server mounts `web-ui/client/build` by convention. The launcher
file is written by `scripts/deploy-omen.sh`; do not hand-edit it on OMEN.

`scripts/deploy-omen.sh` also creates or updates a Windows Desktop shortcut
named `Run RayMe.lnk`. The shortcut targets the repo-owned
`C:\Users\pmpg\rayme\RayMe\scripts\start-rayme-omen.ps1` script, which starts
the existing `RayMePhase1AI` and `RayMePhase1Web` scheduled tasks when their
ports are not already listening, then opens `https://192.168.1.199:8443`. This
is a convenience launcher only; deployment, scheduled-task definitions, and the
canonical `.cmd` launchers remain owned by `scripts/deploy-omen.sh`.

## AI Backend

Run from the backend Git checkout:

```bash
uv run --project ai-backend python ai-backend/scripts/run_https.py \
  --host 192.168.1.199 \
  --port 9443 \
  --cert C:/Users/pmpg/rayme/phase1-tls/rayme.local+1.pem \
  --key C:/Users/pmpg/rayme/phase1-tls/rayme.local+1-key.pem
```

Verification URL: `https://192.168.1.199:9443/health`.

On `OMEN-PC`, the matching scheduled-task runtime is:

```text
Task: RayMePhase1AI
Script: C:\Users\pmpg\rayme\start-ai-backend.cmd
Logs: C:\Users\pmpg\rayme\logs\ai-backend.run.log
URL: https://192.168.1.199:9443/health
```

The Windows firewall must allow inbound TCP on `8443` and `9443`. The durable
rule names used for Phase 1 are `RayMe Phase 1 HTTPS Web UI 8443` and
`RayMe Phase 1 HTTPS AI Backend 9443`.

## Binding Rules

Use an explicit LAN IP or hostname. The wildcard bind value `0.0.0.0` is
rejected by both HTTPS runners for Phase 1. Keep certificate files, private
keys, and root CA private key material out of git.

## Android Chrome Check

1. Install `.local/phase1-tls/rayme-phase1-rootCA.pem` on the Android device if
   this Phase 1 root is not already trusted.
2. Open `https://192.168.1.199:9443/health`; confirm JSON loads with no
   certificate warning.
3. Open `https://192.168.1.199:8443`; confirm no certificate warning.
4. In RayMe, confirm secure-context and media-device readiness are visible.
5. In Settings, run endpoint tests and confirm `Connected` for the Web UI, AI
   backend, and LLM when the LLM endpoint is configured.
