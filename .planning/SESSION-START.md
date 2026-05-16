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
5. `.planning/LIVE-CALL-INVARIANTS.md` - non-negotiable live-call and GSD
   incident-repair rules.
6. The active phase `PLAN.md`/`SUMMARY.md` files relevant to the request.

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

If the work touches calls, TTS, STT, VAD, WebRTC, reconnect, or call UI, first
write the live-call preservation sentence. The change must preserve early
playback, listening recovery, and interrupt/barge-in behavior. Reject any
live-call fix that waits for full assistant response generation or full TTS
stream completion before first playback.

If the work is a non-trivial product regression, incident repair, or deployment,
use GSD structure before implementation: update or create the relevant phase,
plan, debug record, learning, or evidence artifact. Do not ship an unplanned
quick fix and then ask the user to discover whether it preserved the product.

## Interactive Workflow Rule

If a GSD workflow needs user decisions, approvals, context, requirements, or
planning confirmation, and structured prompt UI is unavailable, use plain-text
numbered choices and stop for the user's answer. Never infer defaults for
interactive GSD decisions unless the user explicitly invoked `--auto` or
`--chain`.

For discussion workflows, ask one decision at a time when the user wants a
sequential discussion format. Show the recommendation first, include a short
reason why it is recommended, then stop for the answer before asking the next
question.

Do not insert "Skip", "Use existing context as-is", "View it", or similar
bypass prompts into a fresh discussion unless the user explicitly asks for that
path. If a prior draft or invalid context exists, treat it as non-canonical and
continue the fresh discussion instead of asking whether to bypass it.

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
