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

The same serving cert/key are mirrored on the backend host at:

```text
C:\Users\pmpg\rayme\phase1-tls\rayme-phase1-rootCA.pem
C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem
C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem
```

All agent-created Windows-side RayMe artifacts on `OMEN-PC` must live under
`C:\Users\pmpg\rayme\`. Do not create additional top-level directories in
`C:\Users\pmpg\`.

The certificate covers `rayme.local`, `localhost`, `192.168.1.199`, and
`127.0.0.1`. If Android Chrome does not already trust this Phase 1 root, install
`.local/phase1-tls/rayme-phase1-rootCA.pem` on the phone once and keep reusing
this cert set. Do not create per-session certificates.

Use these paths from the repository root:

```env
RAYME_WEB_BIND_HOST=192.168.1.199
RAYME_WEB_PORT=8443
RAYME_WEB_PUBLIC_URL=https://192.168.1.199:8443
RAYME_TLS_CERT=.local/phase1-tls/rayme.local+1.pem
RAYME_TLS_KEY=.local/phase1-tls/rayme.local+1-key.pem
RAYME_ALLOWED_ORIGINS=https://192.168.1.199:8443
RAYME_AI_BACKEND_BASE_URL=https://192.168.1.199:9443
```

## Web UI

Run from the repository root after building the client:

```bash
npm --prefix web-ui/client run build
RAYME_WEB_BIND_HOST=192.168.1.199 \
RAYME_WEB_PORT=8443 \
RAYME_WEB_PUBLIC_URL=https://192.168.1.199:8443 \
RAYME_TLS_CERT=.local/phase1-tls/rayme.local+1.pem \
RAYME_TLS_KEY=.local/phase1-tls/rayme.local+1-key.pem \
RAYME_ALLOWED_ORIGINS=https://192.168.1.199:8443 \
RAYME_AI_BACKEND_BASE_URL=https://192.168.1.199:9443 \
uv run --project web-ui/server python web-ui/server/scripts/run_dev_https.py
```

Browser URL: `https://192.168.1.199:8443`.

## AI Backend

Run from the repository root:

```bash
uv run --project ai-backend python ai-backend/scripts/run_https.py \
  --host 192.168.1.199 \
  --port 9443 \
  --cert .local/phase1-tls/rayme.local+1.pem \
  --key .local/phase1-tls/rayme.local+1-key.pem
```

Verification URL: `https://192.168.1.199:9443/health`.

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
