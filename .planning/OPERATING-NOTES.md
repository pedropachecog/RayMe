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
- Backend runtime code should be a Git checkout, not an ad hoc copied staging
  tree. Use `C:\Users\pmpg\rayme\RayMe\` as the canonical Windows-side checkout
  on `OMEN-PC`, and use Git to inspect/update the commit that is running.
- If `OMEN-PC` cannot clone/fetch from GitHub non-interactively, use a Git
  bundle as the transport, but keep the backend as a real branch checkout:
  - local: `git bundle create .local/backend-sync/RayMe-main.bundle main`
  - copy bundle to `C:\Users\pmpg\rayme\RayMe-main.bundle`
  - first backend setup: `git clone -b main C:\Users\pmpg\rayme\RayMe-main.bundle C:\Users\pmpg\rayme\RayMe`
  - backend update: from `C:\Users\pmpg\rayme\RayMe`, run `git fetch C:\Users\pmpg\rayme\RayMe-main.bundle main:refs/heads/main` and `git switch main`
  - verify with `git status`, `git branch --show-current`, and `git rev-parse HEAD`
- `C:\Users\pmpg\rayme\phase1-app\` was a temporary copied staging tree created
  during Plan 01-24 troubleshooting. Do not add to it or treat it as canonical;
  it can be removed after `C:\Users\pmpg\rayme\RayMe\` is available and verified.
- `C:\Users\pmpg\rayme\phase1-tls\` is the backend mirror of the reusable Phase
  1 TLS cert set. TLS material stays outside the Git checkout because it is
  private and gitignored locally.
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
  `C:\Users\pmpg\rayme\RayMe\` first, then run `git status`, `git branch`, and
  `git rev-parse HEAD` to determine what code is on the backend. If that
  checkout is missing, create it there rather than copying a partial runtime
  tree.
- Keep generated private keys, root CA keys, virtual environments, and staged
  runtime apps out of git.
