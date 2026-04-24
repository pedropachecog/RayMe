# Operating Notes

These are project-specific operating rules for Codex/agent sessions. Treat them
as durable context, not one-off preferences.

## Backend Host And TLS

- The real LAN backend for Android HTTPS checks is `OMEN-PC` at
  `192.168.1.199`. Do not substitute the local Codex shell, container, or WSL
  network address for the physical-device acceptance path.
- All agent-created Windows-side RayMe artifacts on `OMEN-PC` must live under
  `C:\Users\pmpg\rayme\`. Do not create additional top-level directories in
  `C:\Users\pmpg\`.
- Current Windows-side runtime staging layout:
  - `C:\Users\pmpg\rayme\phase1-app\` - staged runtime copy used when the
    Windows host must bind `192.168.1.199`.
  - `C:\Users\pmpg\rayme\phase1-app\.venv\` - Windows Python runtime
    environment for that staged app.
  - `C:\Users\pmpg\rayme\phase1-app\web-ui\server\` - staged Web UI API/static
    host source.
  - `C:\Users\pmpg\rayme\phase1-app\web-ui\client\build\` - staged built
    Svelte client.
  - `C:\Users\pmpg\rayme\phase1-app\ai-backend\` - staged AI backend health
    service source.
  - `C:\Users\pmpg\rayme\phase1-tls\` - backend mirror of the reusable Phase 1
    TLS cert set.
- The staged Windows app is not a new source of truth. The source of truth stays
  in the repo; restage deliberately when code changes need to run on the
  physical LAN host.
- Reusable Phase 1 LAN TLS material lives locally under
  `.local/phase1-tls/`, which is gitignored but persisted with the repo bind
  mount.
- The backend mirror for that same TLS material lives under
  `C:\Users\pmpg\rayme\phase1-tls\`.
- Do not generate throwaway certificates for normal HTTPS testing. Reuse the
  Phase 1 cert set until it expires or the LAN IP/hostnames change.
- If a new certificate set is required, create it deliberately as a reusable
  project artifact, document its paths, copy it back to the repo-local ignored
  store, and update `web-ui/server/docs/HTTPS-LAN.md`.
- Android trust setup is not disposable. Do not ask for repeated phone CA
  installs unless the active reusable root CA has actually changed.

## Runbook Execution

- Before running LAN/Android checks, inspect the existing runbooks and Phase 0
  acceptance records. Phase 0 already validated Android Chrome HTTPS against
  `https://192.168.1.199:8443`.
- Prefer SSH to `OMEN-PC` via the documented `rayme-pmpg` path for backend-side
  work that needs the real LAN IP.
- If WSL cannot bind `192.168.1.199`, use the Windows side of `OMEN-PC`; the LAN
  IP belongs to Windows, not the local container.
- Do not waste time searching for ad hoc backend staging directories. Check
  `C:\Users\pmpg\rayme\` first; if the needed runtime copy is stale, refresh it
  from the repo into the documented subdirectories.
- Keep generated private keys, root CA keys, virtual environments, and staged
  runtime apps out of git.
