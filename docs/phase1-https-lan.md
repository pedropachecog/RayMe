# Phase 1 LAN HTTPS Setup

Phase 1 uses the reusable certificate set documented in
`web-ui/server/docs/HTTPS-LAN.md`. Direct LAN IP HTTPS is sufficient for the Web
UI and AI-backend health checks. `rayme.local` is optional unless DNS/mDNS is
configured.

## Endpoints

- Web UI: `https://192.168.1.199:8443`
- AI backend health: `https://192.168.1.199:9443/health`
- LLM: external OpenAI-compatible endpoint configured by
  `RAYME_LLM_BASE_URL`, `RAYME_LLM_API_KEY`, and `RAYME_LLM_MODEL`

## Certificate Setup

Use the persisted Phase 1 certificate files. Do not generate per-session
certificates.

```env
RAYME_TLS_CERT=C:\Users\pmpg\rayme\phase1-tls\rayme.local+1.pem
RAYME_TLS_KEY=C:\Users\pmpg\rayme\phase1-tls\rayme.local+1-key.pem
```

Install the active Phase 1 root CA as an Android CA certificate before testing
Chrome. During manual testing, `OMEN-PC` can temporarily serve the public root
CA at `http://192.168.1.199:8081/rayme-phase1-rootCA-20260424.crt`.

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
