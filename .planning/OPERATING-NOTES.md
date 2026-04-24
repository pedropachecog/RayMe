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
- Keep generated private keys, root CA keys, virtual environments, and staged
  runtime apps out of git.
