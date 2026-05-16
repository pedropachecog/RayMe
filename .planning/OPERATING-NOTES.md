# Operating Notes

These are project-specific operating rules for Codex/agent sessions. Treat them
as durable context, not one-off preferences.

## Session Startup

- At the start of every context-reset session, read `.planning/SESSION-START.md`
  and run `scripts/operational-check.sh start` before making implementation,
  deployment, or handoff decisions.
- Do not depend on previous conversational context for project constraints.
  Rehydrate from `.planning/PROJECT.md`, `.planning/STATE.md`,
  `.planning/OPERATING-NOTES.md`, `.planning/LEARNINGS.md`, and the active
  phase files.
- If the current request touches UI, OMEN, Android, LAN HTTPS, STT, TTS, VAD,
  LLM, WebRTC, or GPU runtime, decide the verification layers before editing
  and record them in the final handoff.

## Collaboration Expectations

- The agent owns execution. Do not hand the user a full command sequence for
  work the agent can do through available tools.
- Interactive GSD workflows must never auto-select defaults when the prompt UI
  is unavailable. If `request_user_input` cannot be used, or if
  `workflow.text_mode` is true, present the plain-text numbered choices and stop
  for the user's answer. This applies especially to `$gsd-discuss-phase`,
  `$gsd-spec-phase`, `$gsd-plan-phase` approval gates, `$gsd-next` when it
  routes into an interactive workflow, and any workflow that writes decisions,
  context, requirements, plans, or approvals.
- For discussion workflows, ask one decision at a time. Do not batch multiple
  discussion questions into one prompt when the user has asked for sequential
  discussion.
- For each discussion question, state the recommended option first and include a
  short "why" before waiting for the user's answer. Recommendations guide the
  discussion; they do not lock decisions.
- Do not ask "Skip", "Use existing context as-is", "View it", or similar
  bypass prompts during a fresh discussion unless the user explicitly asks for a
  bypass or invokes an auto mode. If prior draft context exists, invalidate it
  and continue with the fresh discussion flow instead of asking whether to skip.
- A discussion artifact is valid only if it contains actual user answers or an
  explicitly requested `--auto`/`--chain` mode. Do not create or commit
  canonical `*-CONTEXT.md`, `*-SPEC.md`, approval, or decision artifacts from
  inferred defaults merely because structured prompts are unavailable.
- Ask the user only for the narrow interactive action that cannot be completed
  through tools, such as approving a browser/device credential prompt, then
  immediately continue the remaining steps.
- Before inventing a workaround, check the obvious existing mechanism first:
  Git before copied staging trees, persisted certs before new certs, documented
  backend paths before filesystem searching, and real backend host before local
  substitutes.
- When the user points out a sequencing or architecture mistake, correct the
  underlying approach and update durable docs; do not just patch the symptom.
- RayMe's live-call invariant is non-negotiable: calls are live phone calls,
  not generated-audio playback. For call, TTS, STT, VAD, WebRTC, reconnect, and
  call UI work, read `.planning/LIVE-CALL-INVARIANTS.md` before editing. Do not
  fix smoothness, failure, or state issues by waiting for full assistant
  response generation or full TTS stream completion before first playback.
- For non-trivial regressions, incident repair, and deployment, GSD is the default execution structure.
  Create or update the relevant phase/plan/debug/
  learning/evidence artifact before implementation, then verify before handoff.
- Subagents must never run `codex`, `claude`, or another agent CLI from the
  shell to work around missing nested-subagent capability. If a workflow needs a
  specialist agent, the main agent must spawn that specialist directly and
  manage the checkpoint loop itself.
- For Codex `$gsd-debug` sessions, do not delegate to a debug session manager
  that may try nested subagents. The main agent should create or update the
  `.planning/debug/*.md` file, spawn `gsd-debugger` directly, wait for the
  result, then handle fixes, deployment, and follow-up checkpoints in the main
  agent.
- Keep updates concrete and short. Say what is blocked, what exact help is
  needed, and what the agent will do after that help is provided.
- When asking the user for a checkpoint, manual test, approval, or other human
  action, include the relevant phase/plan context in plain language. Do not say
  only "test on Android" or "approve the checkpoint"; explain what has already
  been verified by the agent, what remains for the user to verify, why that
  specific human signal is needed, and what the agent will do next after the
  response. The user does not share the agent's full planning context.
- Before asking the user to test a UI in browser, the agent must open it with a
  browser-capable check such as Playwright and verify rendered content plus
  console errors. HTTP 200, health endpoints, and curl output are not enough for
  browser UI readiness.
- The user's manual testing is product-owner acceptance, not first-line QA. Do
  not ask the user to try a feature until the agent has already run the relevant
  backend/API checks, automated browser tests or Playwright smoke checks, and
  live deployed verification when the feature depends on `OMEN-PC` LAN runtime.
- When a user-reported UI bug exposes an untested workflow, add durable coverage
  for that workflow before calling the phase complete. Manual reproduction by
  the user is evidence of missing test coverage, not a substitute for agent-run
  verification.
- Any Playwright/browser check used as acceptance evidence must be persisted as
  a repository test file or a saved phase artifact before handoff. Save the
  corresponding run result under the relevant phase directory with the command,
  timestamp, commit, and pass/fail outcome. Do not rely on unsaved one-off
  browser scripts or transient terminal output as final evidence.
- Before every user handoff that says a feature is ready, complete and report a
  pre-handoff verification checklist:
  1. relevant unit/API tests run,
  2. browser/Playwright workflow run for UI changes,
  3. live OMEN-PC deployed verification run when LAN/GPU behavior matters,
  4. result artifacts saved under the phase directory,
  5. commit SHA and deployed target stated.
  If any item is skipped, explicitly say why and mark the handoff as not fully
  verified.
- Use `scripts/operational-check.sh handoff` before final readiness handoffs.
  It does not replace judgment, but it prevents evidence-free "ready" claims
  after context resets.
- If the user reports "you gave me an untested path," treat that as an incident,
  not feedback to smooth over. Add or update durable tests/evidence, then add a
  brief note to `.planning/LEARNINGS.md` identifying the false assumption, the
  missing verification layer, and the guard that now prevents recurrence.
- If a user-visible bug is that a workflow fails before completing the expected
  success path, do not accept a fix that only cancels, rejects, hides, drops, or
  suppresses work after the failure. First write the user-goal preservation
  sentence: "The user must still be able to ..." Then make the first RED test
  assert the earliest wrong state transition or control-flow edge. Negative
  cleanup tests such as "do not generate after end" are allowed only as
  secondary guardrails, never as acceptance proof for "the call should not end."
- If a live-call audio bug is that playback is choppy, late, missing, or stuck
  in `Rehearsing`, do not accept a fix that buffers the full response or full
  TTS stream before first playback. The first regression must prove first
  playback starts before stream completion on a slow stream, and any buffering
  must be bounded.
- Before deploying any live-call debug fix, compare the diff against the user's
  expected behavior. If the patch removes a behavior the user expected to happen
  successfully, or only prevents a misleading artifact after failure, stop and
  re-target the upstream failure boundary.
- If the user reports that a GSD workflow skipped discussion, confirmation, or
  approval, treat that as an incident. Invalidate any affected canonical
  artifacts, record the false assumption in `.planning/LEARNINGS.md`, and add a
  structural guard before continuing the workflow.
- Do not rely on tone management as the fix for repeated technical failures.
  The acceptable response pattern is: acknowledge the exact miss, identify the
  verification gap, add an executable or procedural guard, run it, save evidence,
  and then hand off with the evidence path.
- Do not launch backend runtime tasks through visible `.cmd` windows. On
  `OMEN-PC`, scheduled tasks must use hidden PowerShell launchers or another
  no-console mechanism so the user's desktop is not littered with completed
  command prompt windows.
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
- SSH to `OMEN-PC` must use the configured host alias, not a hand-written
  `user@host` target. Use exactly `ssh rayme-pmpg` for backend-side work. That
  alias binds the correct user, host, identity file, known-hosts file, and
  strict host-key behavior in `~/.ssh/config`.
- Deploying to `OMEN-PC` must go through `scripts/deploy-omen.sh` from the repo
  root. Do not manually retype pull/build/kill/restart/health sequences unless
  repairing the script itself. The script is responsible for using the SSH alias,
  fast-forwarding the canonical checkout, rebuilding the client, killing stale
  8443/9443 listeners, starting scheduled tasks, verifying the AI GPU runtime,
  and verifying live health.
- RayMe is a real-time phone-call simulator. GPU acceleration is mandatory for
  AI model runtime. Do not switch STT, TTS, VAD, LLM, or embedding model paths
  to CPU to make an error disappear. Fix CUDA, drivers, wheels, PATH, model
  placement, or deployment instead, and add a failing guard/test for the broken
  path before handoff.
- `faster-whisper` STT must use CUDA with `int8_float16`; CPU `int8` fallback is
  a regression. F5-TTS must use CUDA PyTorch/torchaudio wheels; `torch+cpu` in
  the AI venv is a deployment blocker.
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
- Do not type `ssh rayme-pmpg@192.168.1.199`; that bypasses the alias contract
  and can fail. The correct command is `ssh rayme-pmpg`.
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
