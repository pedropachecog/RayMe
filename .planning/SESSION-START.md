# Session Start Protocol

Use this protocol at the start of every context-reset session before planning,
executing, deploying, or asking the user to test anything.

## Required Reads

Read these files first, in this order:

1. `.planning/PROJECT.md` - product goal and non-negotiable constraints.
2. `.planning/STATE.md` - current phase, decisions, and active policies.
3. `.planning/OPERATING-NOTES.md` - operational rules for handoff, OMEN, GPU,
   Android, Playwright, and cleanup.
4. `.planning/LEARNINGS.md` - repeated mistakes, false assumptions, and
   recurrence guards.
5. The active phase `PLAN.md`/`SUMMARY.md` files relevant to the request.

Do not rely on conversational memory for any of those points after context has
been cleared.

## Startup Checks

Run:

```bash
scripts/operational-check.sh start
```

Then inspect:

```bash
git status --short
git log --oneline -5
```

If the work touches OMEN, Android, live LAN, STT, TTS, LLM, VAD, WebRTC, or
browser UI, identify the required verification layers before editing:

- unit/API tests,
- browser/Playwright tests,
- live OMEN deployment through `scripts/deploy-omen.sh`,
- GPU runtime checks for AI models,
- Android product-owner acceptance only after agent verification.

## Interactive Workflow Rule

If a GSD workflow needs user decisions, approvals, context, requirements, or
planning confirmation, and structured prompt UI is unavailable, use plain-text
numbered choices and stop for the user's answer. Never infer defaults for
interactive GSD decisions unless the user explicitly invoked `--auto` or
`--chain`.

Before planning from any `*-CONTEXT.md` or `*-SPEC.md`, confirm the artifact was
created from actual user answers or explicit auto mode. Draft files marked
`NOT-USER-DISCUSSED` are invalid for planning.

## Handoff Gate

Before saying a workflow is ready, run:

```bash
scripts/operational-check.sh handoff \
  --phase-dir .planning/phases/<phase-dir> \
  --commit "$(git rev-parse --short HEAD)" \
  --tests "<commands and pass/fail result>" \
  [--ui-evidence <saved-playwright-json-or-md>] \
  [--live-evidence <saved-live-result-json-or-md>] \
  [--gpu-evidence <saved-gpu-result-json-or-md>]
```

If the script cannot be satisfied, do not ask the user to find the failure.
Keep testing or explicitly mark the handoff as not fully verified.

## Communication Rule

When reporting readiness, include:

- what was verified by the agent,
- exact saved evidence paths,
- commit SHA,
- deployed target when live behavior matters,
- what remains for product-owner acceptance.

Do not bury known failures, slow paths, CPU fallbacks, stale deployments, or
untested routes. Report them as blockers or residual risk.
