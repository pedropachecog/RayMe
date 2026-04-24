# Operating Notes

These are project-specific operating rules for Codex/agent sessions. Treat them
as durable context, not one-off preferences.

## Collaboration Expectations

- The agent owns execution. Do not hand the user a full command sequence for
  work the agent can do through available tools.
- Ask the user only for the narrow interactive action that cannot be completed
  through tools, such as approving a browser/device credential prompt, then
  immediately continue the remaining steps.
- Before inventing a workaround, check the obvious existing mechanism first:
  Git before copied staging trees, persisted certs before new certs, documented
  backend paths before filesystem searching, and real backend host before local
  substitutes.
- When the user points out a sequencing or architecture mistake, correct the
  underlying approach and update durable docs; do not just patch the symptom.
- Keep updates concrete and short. Say what is blocked, what exact help is
  needed, and what the agent will do after that help is provided.
- Before asking the user to test a UI in browser, the agent must open it with a
  browser-capable check such as Playwright and verify rendered content plus
  console errors. HTTP 200, health endpoints, and curl output are not enough for
  browser UI readiness.
- At the end of each phase, explicitly tell the user what temporary/runtime
  directories can be deleted. Include exact full paths, what each path contains,
  whether it is safe to delete for the rest of the project, and deletion commands
  only when requested. Never use expanded variables, globs, or mounted Windows
  paths in cleanup commands.

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
- Backend Git sync uses the GitHub HTTPS remote
  `https://github.com/pedropachecog/RayMe.git`. If credentials fail, fix Git
  Credential Manager on `OMEN-PC`; do not invent bundle or copied-tree sync
  paths.
- `OMEN-PC` Git credential baseline:
  - `git config --global credential.helper manager`
  - `git config --global credential.credentialStore dpapi`
  - GitHub auth may require one user-assisted browser/device approval, after
    which the agent should continue the rest of the sync itself.
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
- Phase 1 HTTPS runtime on `OMEN-PC` uses scheduled tasks
  `RayMePhase1Web` and `RayMePhase1AI`, backed by
  `C:\Users\pmpg\rayme\start-web-ui.cmd` and
  `C:\Users\pmpg\rayme\start-ai-backend.cmd`. Logs are under
  `C:\Users\pmpg\rayme\logs\`.
- Keep inbound Windows firewall rules for TCP `8443` and `9443` when doing
  Android LAN testing.
- Do not generate throwaway certificates for normal HTTPS testing. Reuse the
  Phase 1 cert set until it expires or the LAN IP/hostnames change.
- The active Phase 1 root CA must include critical CA basic constraints and
  critical `keyCertSign, cRLSign` key usage; an earlier root without key usage
  did not work for Android Chrome. Active root transfer-file SHA-256:
  `9819c9661dfa5bb0b4d6251659029591f4e5b3e7250ef2d638b724c4f2ee00a1`.
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
  checkout is missing, create it there with GitHub clone/pull after credentials
  are fixed rather than copying a partial runtime tree.
- Do not repurpose the `OMEN-PC` SSH login key for GitHub. That key is for
  logging into `192.168.1.199` only.
- Push local commits to `origin/main` before expecting `OMEN-PC` to pull them.
- Ask the user for help only when an interactive credential/browser approval is
  genuinely needed; do not hand them the whole operational command sequence.
- Keep generated private keys, root CA keys, virtual environments, and staged
  runtime apps out of git.
