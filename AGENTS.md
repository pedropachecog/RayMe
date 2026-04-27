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

This applies to all subagent usage, including GSD workflows, code review,
debugging, planning, and implementation.
