# Phase 1 HTTPS LAN Runbook

Phase 1 uses the Phase 0 mkcert LAN path. Direct LAN IP HTTPS is sufficient for
Web UI and AI-backend checks. `rayme.local` is optional unless DNS/mDNS is
configured on the Android device and LAN.

## Certificate

Generate a certificate that covers the direct LAN IP:

```powershell
mkcert -install
mkcert rayme.local 192.168.1.199
```

Use the generated paths below as examples:

```env
RAYME_WEB_BIND_HOST=192.168.1.199
RAYME_WEB_PORT=8443
RAYME_WEB_PUBLIC_URL=https://192.168.1.199:8443
RAYME_TLS_CERT=.certs/rayme.local+1.pem
RAYME_TLS_KEY=.certs/rayme.local+1-key.pem
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
RAYME_TLS_CERT=.certs/rayme.local+1.pem \
RAYME_TLS_KEY=.certs/rayme.local+1-key.pem \
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
  --cert <mkcert-cert.pem> \
  --key <mkcert-key.pem>
```

Verification URL: `https://192.168.1.199:9443/health`.

## Binding Rules

Use an explicit LAN IP or hostname. The wildcard bind value `0.0.0.0` is
rejected by both HTTPS runners for Phase 1. Keep certificate files, private
keys, and mkcert root material out of git.

## Android Chrome Check

1. Install the mkcert root CA on the Android device.
2. Open `https://192.168.1.199:9443/health`; confirm JSON loads with no
   certificate warning.
3. Open `https://192.168.1.199:8443`; confirm no certificate warning.
4. In RayMe, confirm secure-context and media-device readiness are visible.
5. In Settings, run endpoint tests and confirm `Connected` for the Web UI, AI
   backend, and LLM when the LLM endpoint is configured.
