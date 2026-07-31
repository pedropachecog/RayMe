---
status: resolved
created: 2026-07-31T22:40:29Z
updated: 2026-07-31T22:59:34Z
trigger: "Phase 09 Plan 14 predeployment E2E gate persistently fails on desktop and mobile because call-start.spec.ts cannot find the fixed Qwen preparation failure alert heading."
---

# Debug Session: Qwen Preparation Alert Missing

## Current Focus

user_goal_preservation: "RayMe must visibly explain a failed Qwen saved-voice preparation attempt, focus the actionable alert, preserve retry/state, and never enter Listening before authoritative model and prompt readiness."
hypothesis: "Confirmed: direct call startup awaits AudioContext.resume() before POST /api/calls/start; Chromium can leave resume pending without a user gesture, so the offer is never sent and the page remains Connecting before Qwen preparation can fail visibly."
test: "Keep the E2E offer counter assertion as a RED boundary, make audio unlock best-effort/non-blocking, then repeat the failure case across desktop/mobile and run call/start/live invariant regressions."
expecting: "All repeats reach one offer, render and focus the fixed safe Voice preparation failed alert, and retain no early Listening state or browser error."
next_action: "Resume Phase 09 Plan 14 from the committed browser startup repair and rerun every predeployment gate before canonical deployment."

## Symptoms

expected: "When Qwen saved-voice preparation fails, the call page renders an alert headed Voice preparation failed, focuses it, shows only fixed safe copy, and offers recovery without entering Listening."
actual: "The expected Voice preparation failed alert heading is never rendered in the persistent desktop and mobile Playwright case."
errors:
  - "call-start.spec.ts:145 — focuses a fixed Qwen preparation failure without exposing backend detail"
  - "63/66 passed in the focused run; serial rerun 2/4 passed; this case fails on both desktop and mobile"
timeline: "First observed on 2026-07-31 in the Phase 09 Plan 14 predeployment browser gate at exact commit 90c7c83aab276ebd5528a51b2dfc9429bae3b3a1."
reproduction: "Run the named call-start.spec.ts test under the configured desktop and mobile Playwright projects; the alert heading lookup times out."

## Evidence

- timestamp: 2026-07-31T22:40:29Z
  checked: "Plan 14 executor focused and serial E2E reruns."
  found: "The Qwen preparation failure case fails persistently on desktop and mobile; 63/66 other focused cases passed; an ICE reconnect failure passed when isolated; OMEN was not redeployed; worktree was clean."
  implication: "This is a local call UI acceptance regression and must be repaired before canonical deployment."
- timestamp: 2026-07-31T22:48:00Z
  checked: "Single traced run, six serial desktop/mobile repeats, page snapshots, startup route counters, requestCallMicrophone, unlockAudioForCall, and unlockCallAudioContext."
  found: "A traced run occasionally passed, but all six untraced repeats remained Connecting with offerCount=0. The thread had loaded and microphone capture was mocked; beginCall then awaited AudioContext.resume before startCall. Chromium may keep resume pending without transient user activation on direct route startup."
  implication: "Audio unlock is best-effort browser work and must not gate signaling, Qwen readiness, or visible startup failure. Fire it without awaiting; keep offer completion authoritative."
- timestamp: 2026-07-31T22:59:34Z
  checked: "RED/GREEN offer-boundary assertion, six desktop/mobile repeats of the Qwen failure, repeated Qwen plus ICE timing pair, complete 66-case focused browser suite, 101 client unit tests, production build, and git diff check."
  found: "Before the fix, six repeats had offerCount=0 and remained Connecting. After non-blocking unlock, all six rendered/focused the safe failure in about 0.3 seconds. A separate ICE clock assertion flaked at a 100 ms boundary under the full parallel suite; using the existing 500 ms split preserved the 2.5 second product grace and passed 12 repeated paired cases. The final focused suite passed 66/66, units 101/101, and production build/diff checks passed."
  implication: "Direct startup can no longer be held hostage by a pending audio resume, and browser acceptance now synchronizes on real offer scheduling with stable grace-period evidence."

## Eliminated

- hypothesis: "The Qwen error mapping or fixed safe copy was missing."
  evidence: "The route already mapped qwen3_prompt_failed to the correct focused blocking panel; execution never reached that branch because no offer was sent."
- hypothesis: "Waiting longer for the alert locator alone would repair the contract."
  evidence: "The offer counter remained zero in every untraced repeat; the product was blocked on a pending audio resume, not merely slow rendering."

## Resolution

root_cause: "Call startup synchronously awaited a browser AudioContext resume promise before contacting the server; on direct navigation without a live user gesture, Chromium left that promise pending and RayMe stayed Connecting forever, so the Qwen failure alert could never render."
fix: "Call startup now starts best-effort audio unlock without awaiting a potentially gesture-blocked resume promise, and the E2E contract waits for the actual offer boundary before asserting the focused safe failure. The ICE clock check retains the exact 2.5 second grace with a stable 2.0/0.5 second split."
verification: "Six Qwen failure repeats passed on desktop/mobile; 12 paired Qwen/ICE repeats passed; focused browser gate passed 66/66; client unit tests passed 101/101; production build and git diff check passed."
files_changed: "web-ui/client/src/routes/call/[threadId]/+page.svelte, web-ui/client/tests/e2e/call-start.spec.ts"
