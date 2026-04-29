---
status: resolved
trigger: "Recurring GSD workflow failure: discussion/approval prompts are skipped and defaults are inferred when structured prompt UI is unavailable."
created: 2026-04-25T17:24:00Z
updated: 2026-04-25T17:24:00Z
---

# Debug Session: Interactive GSD Auto-Default

## Symptoms

- Expected behavior: interactive GSD workflows ask the user in plain text when
  structured prompt UI is unavailable, then wait for the user's answer.
- Actual behavior: `$gsd-next` routed into `$gsd-discuss-phase 3`, inferred
  defaults, wrote canonical context, and committed it without discussion.
- Timeline: recurring; latest instance happened during Phase 3 context capture
  on 2026-04-25.
- Reproduction: run an interactive GSD workflow from Codex Default mode where
  `request_user_input` is unavailable and the skill adapter says to pick a
  reasonable default.

## Root Cause

The Codex skill adapter fallback conflicted with GSD text-mode semantics. The
adapter said to present a numbered list and pick a reasonable default when
`request_user_input` is rejected. For decision-gathering workflows, that converts
the workflow from interactive discussion into silent auto-mode.

## Fix

- Invalidate the incorrectly generated Phase 3 context by moving it out of the
  canonical `03-CONTEXT.md` path.
- Add both root-level and Phase 3-level `.continue-here.md` checkpoints so
  `$gsd-next` and direct `$gsd-discuss-phase 3` cannot silently advance.
- Add project operating rules forbidding inferred defaults for interactive GSD
  decisions unless the user explicitly requested `--auto` or `--chain`.
- Record the failure and guard in `.planning/LEARNINGS.md`.
- Attempt to update local GSD skill adapter files. This was blocked for the
  installed `/home/agent/.codex/skills/gsd-*` files because they are root-owned
  in this environment, so project-level guardrails and a blocking checkpoint
  were added instead.

## Verification

- `gsd-sdk query find-phase 3` must report `has_context: false` until a real
  user-discussed `03-CONTEXT.md` exists.
- `scripts/operational-check.sh start` must fail while the unresolved
  `.planning/.continue-here.md` checkpoint exists.
- `.planning/phases/03-first-working-call-mvp/.continue-here.md` must exist so
  direct `$gsd-discuss-phase 3` hits the blocking anti-pattern gate.
