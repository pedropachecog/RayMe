# Phase 1 Acceptance Runbook

Run the automated suites from the repository root:

```bash
uv run --project web-ui/server pytest web-ui/server/tests -q
npm --prefix web-ui/client run test:unit -- --run
npm --prefix web-ui/client run test:e2e
```

Expected automated result: backend tests pass, frontend unit tests pass, and
Playwright covers desktop plus Android-like mobile Phase 1 text surfaces.

## Manual Android HTTPS Acceptance

Use `web-ui/server/docs/HTTPS-LAN.md` to start both HTTPS services. Direct LAN
IP HTTPS is sufficient; `rayme.local` is optional unless DNS/mDNS is configured.

1. On Android Chrome, open `https://192.168.1.199:9443/health`.
2. Confirm the AI-backend health JSON loads with no certificate warning.
3. On Android Chrome, open `https://192.168.1.199:8443`.
4. Confirm the Web UI loads with no certificate warning.
5. Confirm Home or Settings shows `Secure`.
6. Confirm Home or Settings shows `Media ready`.
7. In Settings, run `Test Connection` for Web UI, AI backend, and LLM.
8. Confirm each configured endpoint reports `Connected`.
9. Import a fixture character, save review mode, start a chat with a non-default
   alternate greeting, stream a reply, regenerate, generate/select a swipe,
   continue with composer text, reload, and continue the same thread.

Record the exact Web UI URL, AI-backend health URL, Android browser, and any
certificate warning or endpoint status mismatch in
`.planning/phases/01-foundations-text-chat-end-to-end/01-VALIDATION.md`.
