# Phase 1 LAN HTTPS Setup

Phase 1 uses the Phase 0 mkcert-on-LAN workflow for trusted browser access. For
Phase 1, direct LAN IP HTTPS is sufficient for the Web UI and AI-backend health
checks. rayme.local is optional unless DNS/mDNS is configured.

## Endpoints

- Web UI: `https://192.168.1.199:8443`
- AI backend health: `https://192.168.1.199:9443/health`
- LLM: external OpenAI-compatible endpoint configured by
  `RAYME_LLM_BASE_URL`, `RAYME_LLM_API_KEY`, and `RAYME_LLM_MODEL`

## Certificate Setup

On the LAN host, generate a certificate that covers both the friendly name and
the direct IP:

```powershell
mkcert -install
mkcert rayme.local 192.168.1.199
```

The output files can be referenced from `web-ui/server/config.example.env`:

```env
RAYME_TLS_CERT=.certs/rayme.local+1.pem
RAYME_TLS_KEY=.certs/rayme.local+1-key.pem
```

Install the mkcert root CA on the Android device before testing Chrome. The
accepted Phase 0 path loaded `https://192.168.1.199:8443` directly because
`rayme.local` name resolution was not configured on the phone.

## Bind And Origin Rules

- Bind the Web UI to an explicit LAN host such as `192.168.1.199`.
- The wildcard `0.0.0.0` is rejected for Phase 1 run scripts and examples.
- wildcard CORS is not allowed; configure explicit origins such as
  `https://192.168.1.199:8443`.
- Keep certificate files and private keys out of git.

## Verification

1. Start the Web UI host with `RAYME_WEB_PUBLIC_URL=https://192.168.1.199:8443`.
2. Start the AI backend on port `9443` with its mkcert certificate and key.
3. Load `https://192.168.1.199:8443` from Android Chrome.
4. Confirm the browser reports a secure context.
5. Verify AI-backend health at `https://192.168.1.199:9443/health`.
6. Use Settings to run `POST /api/settings/test/llm` against the configured
   external OpenAI-compatible endpoint.
