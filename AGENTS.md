# Agent Instructions

## OMEN Deployment

**The only correct way to deploy to OMEN is `scripts/deploy-omen.sh`.**

- NEVER create ad-hoc deployment scripts (`*.ps1`, `*.cmd`, `*.sh`) on OMEN outside the repo
- NEVER manually run `schtasks /Create` or `schtasks /Delete` for `RayMePhase1AI` / `RayMePhase1Web`
- NEVER use `Start-Process -WindowStyle Hidden` as a deployment mechanism
- NEVER write launcher files to `C:\Users\pmpg\rayme\` except via `deploy-omen.sh`
- The canonical launchers are `start-ai-backend.cmd` and `start-web-ui.cmd`, both written by `deploy-omen.sh`
- Scheduled tasks `RayMePhase1AI` and `RayMePhase1Web` must point to those `.cmd` files only
- If `deploy-omen.sh` is missing functionality, fix the script — do not work around it

## Subagent Sequencing

When a task is delegated to a subagent, the parent agent must stop working on
that same task until the subagent returns.

- After spawning a subagent, immediately wait for its final result.
- Do not continue local investigation, implementation, verification, or file
  edits for the delegated task while the subagent is running.
- Do not repeatedly poll the subagent. Use one wait for completion unless the
  user explicitly asks for status.
- If local takeover is necessary, first cancel or close the subagent, state why
  the takeover is happening, and only then continue locally.
- Parallel work is allowed only when it is clearly disjoint from the delegated
  task and cannot touch the same files, boundary, or decision.
- Subagents must never launch `codex`, `claude`, or another agent CLI from the
  shell as a workaround for missing nested-subagent capability.
- Codex debug workflows must not delegate to a debug-session-manager that then
  tries to spawn its own agents. Instead, the main agent must run the session
  manager workflow inline:
  - First follow the normal `gsd-debug` skill setup: parse subcommands/flags,
    initialize GSD context, check/list/resume active sessions, gather symptoms
    for new sessions, and create/update the `.planning/debug/{slug}.md` file.
  - At the point where `gsd-debug` would spawn `gsd-debug-session-manager`, read
    the entire `/home/agent/.codex/agents/gsd-debug-session-manager.md`
    instruction file. If available, also read its TOML config for role metadata.
  - Execute that session-manager process inline. The debug file is the primary
    context: read it first, extract status/current focus/evidence count, resolve
    the `gsd-debugger` model, spawn `gsd-debugger` directly with the debug file
    path as required reading, and immediately wait for it.
  - While the debugger is running, do not investigate, edit, verify, or deploy
    the same task locally.
  - Parse the debugger's structured return header and continue the same loop
    inline:
    - `ROOT CAUSE FOUND`: record/review the root cause, run any applicable
      specialist review directly if available, then explicitly choose or ask
      whether to fix now, plan, or stop.
    - `TDD CHECKPOINT`: surface the failing test and continue only after the red
      state is accepted or otherwise handled.
    - `CHECKPOINT REACHED`: collect the missing user/runtime evidence, wrap it
      as data, and spawn the next `gsd-debugger` continuation.
    - `INVESTIGATION INCONCLUSIVE`: choose or ask whether to continue, add
      context, or stop; do not silently end the debug loop.
    - `DEBUG COMPLETE`: read the final debug file and return a compact summary.
  - Handle checkpoints, fixes, verification, commits, deployments, and follow-up
    debugger continuations in the parent context, preserving the session-manager
    state-machine semantics even though no `gsd-debug-session-manager` agent is
    spawned.

This applies to all subagent usage, including GSD workflows, code review,
debugging, planning, and implementation.
