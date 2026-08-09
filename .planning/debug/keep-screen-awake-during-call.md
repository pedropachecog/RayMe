---
status: fixing
trigger: "while the call works for the most part, it stops working correctly when the phone screen turns off for being idle. the call is still connected and it works once i wake up the screen but is there a way to keep the screen on while having a call? so I don't have to set my screen to never go to sleep or something."
created: "2026-08-09T00:00:00Z"
updated: "2026-08-09T13:41:27Z"
---

# Debug Session: Keep Screen Awake During Call

## User Goal Preservation

While a RayMe live call is active, prevent the phone from turning its screen off because of idle timeout without requiring a global phone setting change; release that behavior when the call ends and preserve early streaming playback, listening recovery, explicit interruption, mute, reconnect, and hangup behavior.

## Symptoms

- Expected behavior: while a live call is active and RayMe remains visible, the phone screen stays awake for the duration of the call and returns to normal idle-sleep behavior after hangup.
- Actual behavior: the phone screen turns off after the device idle timeout; the call remains connected but stops behaving correctly until the user wakes the screen.
- Error message: no error message was reported.
- Timeline: newly reported on 2026-08-09; whether an earlier RayMe version prevented idle sleep is unknown.
- Reproduction: start a RayMe call on a phone, leave the screen untouched until the device idle timeout turns it off, observe degraded call behavior, then wake the screen and observe the call resume working.
- Surface: mobile live-call UI lifecycle.

## Current Focus

- bug_class: "bohrbug — deterministic when the browser applies its normal idle timeout to a call route with no wake-lock integration."
- hypothesis: "Locally verified: wake-lock attempts are event-driven; a persistent rejection reports a visible fallback once and does not self-retry. A later explicit activation or visible recovery remains eligible to request again."
- test: "Local verification is complete; remaining validation is the parent-owned canonical deployment and physical phone acceptance of both granted and denied fallback behavior."
- expecting: "On deployed Android Chrome, an allowed request keeps the active call screen awake; a denied or unsupported request leaves the call controllable and visibly explains that the screen may sleep; End Call restores ordinary idle behavior."
- next_action: "Parent deploys only through scripts/deploy-omen.sh, verifies deployed health/commit, and asks the product owner to run the phone acceptance steps."

reasoning_checkpoint:
  hypothesis: "The helper's `finally` retry invokes `navigator.wakeLock.request('screen')` again after a rejected request, so an environment that continues to deny the lock creates a tight asynchronous retry loop; the call UI also has no visible fallback explanation."
  confirming_evidence:
    - "`wakeLock.ts` calls `requestIfNeeded()` unconditionally from `finally` when the call remains active, visible, and has no sentinel."
    - "Its rejection handler intentionally swallows request failure, leaving the `finally` predicate true after every persistent denial."
    - "The call route has a sticky non-blocking recovery/notice area but does not display wake-lock availability."
  falsification_test: "After one agent-authored persistent rejected request and no state or visibility event, observing a second request would confirm the loop; observing exactly one request and a visible rejected-fallback notice after the fix would refute it."
  fix_rationale: "Remove completion-driven retry. Keep requests event-driven from explicit active-state synchronization and visible recovery, report unsupported/rejected status through a narrow callback, and render that status as a non-blocking toolbar notice. This leaves call media and streaming untouched."
  blind_spots: "A supported phone can still deny a wake lock due to battery saver or browser policy; the notice is truthful fallback, and deployed Android Chrome must verify both granted and denied behavior where practical. Local Playwright remains unavailable."
  candidate_causes:
    - "code: confirmed — `finally` re-enters the request path after a rejection without a triggering lifecycle event."
    - "environment: contributing condition — browser, power, permission, or platform policy persistently denies the request."
    - "config: eliminated — existing HTTPS and policy evidence remains unchanged; no checked RayMe configuration causes the retry."
    - "data: eliminated — call content and persisted values do not affect Screen Wake Lock rejection."
  and_gate: "yes — a tight retry loop manifests only when the unconditional code retry and a persistent external rejection co-occur; both are recorded in the revised root cause."

historical_reasoning_checkpoint:
  hypothesis: "The call screen turns off because the live-call route does not request a browser Screen Wake Lock at all; without a request, the operating system applies normal idle timeout even while WebRTC remains connected."
  confirming_evidence:
    - "A complete source search found no Screen Wake Lock, WakeLockSentinel, or document-visibility handling anywhere in the client."
    - "The call route owns call start, active state, terminal teardown, and route destruction, but each path lacks wake-lock handling."
    - "The Screen Wake Lock API is expressly designed to prevent the observed dim/lock behavior for visible interactive applications, and requires re-request after automatic release or visibility recovery."
    - "Canonical OMEN phone calls already run over HTTPS and no checked Permissions-Policy denies screen-wake-lock."
  falsification_test: "On the pre-fix call route with a supported wake-lock mock, a request observed after the call reaches an active state would prove the claimed missing integration false; after the narrow fix, a real supported phone that receives a successful request yet still sleeps at idle would show an additional environment/policy cause."
  fix_rationale: "A route-owned, feature-detected helper can request a screen lock only for an active visible call, listen for automatic release and visible recovery, and release on terminal/destroy. It directly restores the missing platform request while leaving WebRTC, microphone, audio streaming, and TTS timing untouched."
  blind_spots: "A handset may deny or not implement the API because of browser version, battery saver, or system policy; the implementation must remain no-op-safe and the physical Android acceptance test must confirm the platform grants the request."
  candidate_causes:
    - "code: confirmed — no active-call Screen Wake Lock request, sentinel lifecycle, or teardown release exists."
    - "config: eliminated — canonical phone calls use HTTPS and no source emits a restrictive screen-wake-lock Permissions-Policy."
    - "environment: unconfirmed capability limit — an unsupported or power-restricted handset may reject a correct request, but cannot explain the universal missing request in current code."
    - "data: eliminated — no call payload, thread, or persisted value determines idle-screen policy."
  and_gate: "no — the absent code request alone fully explains the current normal idle timeout. Environment support affects post-fix availability but is not a simultaneous cause of the pre-fix behavior."

## Evidence

- timestamp: "2026-08-09T00:00:02Z"
  checked: ".planning/debug/knowledge-base.md"
  found: "The three resolved entries concern database migrations, Qwen prompt ownership, and TTS/cancellation behavior; none identifies mobile idle timeout, the Screen Wake Lock API, or equivalent browser lifecycle handling."
  implication: "There is no keyword-similar known-pattern candidate; call streaming defects remain distinct from the reported screen-idle behavior."

- timestamp: "2026-08-09T00:00:03Z"
  checked: "MemPalace semantic recall configuration and CLI availability"
  found: "`config.mempalace.enabled` is false, its wing is empty, and `mempalace` is not on PATH. Keyword fallback found no candidate in the durable knowledge base."
  implication: "Semantic recall is unavailable and does not bias the diagnosis; investigation continues from local evidence."

- timestamp: "2026-08-09T00:00:04Z"
  checked: "web-ui/client source search for Screen Wake Lock and document visibility integration"
  found: "No client source contains `wake lock`, `wakeLock`, `visibilitychange`, or `document.visibilityState`. The worktree has only this untracked debug session and an unrelated untracked Qwen debug file."
  implication: "The symptom is consistent with a missing browser lifecycle integration, while unrelated user work is preserved."

- timestamp: "2026-08-09T00:00:05Z"
  checked: "Complete call-route lifecycle entry, state transition, and terminal transaction code plus call audio/state tests"
  found: "`+page.svelte` starts the browser media call in `beginCall`, makes it active after the offer through `applyCallState`, terminalizes it through `terminalizeCall`/`stopBrowserMedia`, and stops media on component destruction. Neither the route nor the call helpers observe page visibility or request/release a wake lock. Existing tests cover call/audio state but no idle-screen lifecycle."
  implication: "The call route is the appropriate integration owner; the suspected cause is isolated outside WebRTC streaming, audio playback, and server call control."

- timestamp: "2026-08-09T00:00:05Z"
  checked: "SBFL applicability"
  found: "No pre-existing failing test or per-test coverage input represents this screen-idle defect."
  implication: "Spectrum-based fault localization is skipped; it cannot rank a defect with no failing spectrum."

- timestamp: "2026-08-09T00:00:06Z"
  checked: "W3C Screen Wake Lock specification and MDN API guidance"
  found: "A visible document can request `navigator.wakeLock.request('screen')`; its sentinel may be released automatically when visibility changes or by platform power policy, so an app that still needs it must hold the sentinel, observe its `release` event, and request a fresh sentinel after visible recovery. Manual release is the documented teardown path. The API requires HTTPS and has a safe unsupported/rejected-request fallback."
  implication: "The proposed lifecycle is a direct, bounded remedy for idle screen-off and does not alter live TTS/WebRTC scheduling."

- timestamp: "2026-08-09T00:00:06Z"
  checked: "Terminal browser-media teardown and client unit-test command"
  found: "`stopBrowserMedia` is the route's idempotent resource teardown: it invalidates lifecycle owners, closes media/data channels, stops tracks, and closes audio contexts. `web-ui/client` runs focused Vitest unit tests with `npm run test:unit -- <file>`; no current wake-lock regression exists."
  implication: "Wake-lock release belongs alongside this route-level lifecycle and can be independently unit-tested without touching live audio streaming."

- timestamp: "2026-08-09T00:00:07Z"
  checked: "Production HTTPS and policy configuration"
  found: "The canonical OMEN deployment serves the web UI at `https://192.168.1.199:8443` with the established TLS certificate. No source configuration emits a restrictive `Permissions-Policy` or `screen-wake-lock` directive."
  implication: "The secure-context prerequisite is already met for the phone call workflow, and no checked configuration cause blocks a same-origin screen wake-lock request."

- timestamp: "2026-08-09T00:00:10Z"
  checked: "Agent-authored mobile Playwright regression"
  found: "The new `call-mobile.spec.ts` assertion is ready to observe `request('screen')` after call start, but Playwright cannot launch because its Chromium executable is not installed in this workspace."
  implication: "The physical browser regression cannot be executed locally without a large external browser install; use an injected unit lifecycle test for deterministic RED/GREEN verification and retain the mobile browser assertion for CI/deployed acceptance."

- timestamp: "2026-08-09T00:00:13Z"
  checked: "Focused agent-authored regression: web-ui/client/tests/unit/call-wake-lock.test.ts"
  found: "RED: before implementation the test failed to resolve the missing wake-lock helper. GREEN: after the targeted implementation, all 4 specified lifecycle assertions pass in 7.05 seconds."
  implication: "The introduced code now enforces the root-cause behavior rather than merely suppressing a visible symptom."

- timestamp: "2026-08-09T00:00:15Z"
  checked: "Expanded wake-lock lifecycle regression"
  found: "All 5 tests pass in 8.42 seconds, including the late asynchronous request case: a stale sentinel is released and a fresh request is made after reactivation."
  implication: "The lifecycle remains correct across the visible/hidden and in-flight-request boundary neighbors of the reported active-call state."

- timestamp: "2026-08-09T00:00:16Z"
  checked: "Client production build and adjacent call unit suites"
  found: "`npm run build` completed successfully, and `call-audio.test.ts` plus `call-state.test.ts` passed 18/18 assertions in 14.80 seconds."
  implication: "The new browser lifecycle code compiles into the production call route while existing microphone, audio, and call-state behavior remains intact."

- timestamp: "2026-08-09T00:00:19Z"
  checked: "First scoped revert-and-reconfirm attempt"
  found: "The stash also removed the untracked driving test, so Vitest reported no matching test files and exited under `--passWithNoTests`. This is not accepted as a revert signal."
  implication: "The guardrail must retry with the test retained; no conclusion was drawn from the invalid first attempt."

- timestamp: "2026-08-09T00:00:25Z"
  checked: "Final diff/status and fix-acceptance guardrail"
  found: "`git diff --check` and targeted trailing-whitespace scan are clean. The worktree contains only the two tracked call files, the two new wake-lock source/test files, this debug session, and an unrelated Qwen debug session. The focused lifecycle test returned the original RED missing-helper failure when only this implementation was stashed, then returned 5/5 GREEN after restoration."
  implication: "The minimal, additive fix is locally accepted and is ready for canonical deployment plus physical phone verification."

- timestamp: "2026-08-09T00:00:26Z"
  checked: "Parent guardrail review"
  found: "`requestIfNeeded().catch(...).finally(...)` schedules `requestIfNeeded()` whenever the active document remains visible and has no sentinel. A persistent browser/platform rejection therefore schedules another request immediately and without a retry bound."
  implication: "The fix is not locally acceptable yet: retries must be event-driven, not completion-driven, and the user needs a non-blocking explanation when the browser cannot keep the screen awake."

- timestamp: "2026-08-09T00:00:27Z"
  checked: "wakeLock.ts finalization and call route notice/status patterns"
  found: "The helper's unconditional `finally` retry exactly matches the reviewed loop. The call route already renders non-blocking recovery content inside `.toolbar-wrap` while keeping End Call available; existing transcript notices are reserved for turn events."
  implication: "A toolbar-level `role=status` fallback notice is the narrow, visible UI fit; it avoids blocking panels, transcript pollution, and any change to live-call control or media behavior."

- timestamp: "2026-08-09T00:00:29Z"
  checked: "Review regression: web-ui/client/tests/unit/call-wake-lock.test.ts"
  found: "RED: 2/6 tests failed. A rejected request produced no `rejected` status, and an unsupported browser produced no `unsupported` status; the pre-fix implementation still owns the reviewed completion-driven retry."
  implication: "The regression exposes the user-visible fallback gap before the corrective change."

- timestamp: "2026-08-09T00:00:31Z"
  checked: "Revised wake-lock lifecycle regression"
  found: "All 6 tests pass in 7.51 seconds. The bounded persistent-rejection assertion proves one rejected request produces one fallback status and no unprompted retry; a later visible lifecycle event can make the next request."
  implication: "The retry loop is removed while supported calls still reacquire only from an explicit eligible lifecycle event."

- timestamp: "2026-08-09T00:00:32Z"
  checked: "Revised client build and adjacent live-call unit suites"
  found: "`npm run build` completed successfully, and `call-audio.test.ts` plus `call-state.test.ts` passed 18/18 assertions in 14.57 seconds."
  implication: "The non-blocking fallback notice compiles into the call route and leaves existing audio/state behavior intact."

- timestamp: "2026-08-09T00:00:37Z"
  checked: "Revised scoped revert-and-reconfirm"
  found: "With only wakeLock.ts, the call route, and the mobile browser assertion stashed, the retained six-case unit suite returned the expected missing-helper RED failure. Restoring that exact stash returned 6/6 GREEN in 8.24 seconds."
  implication: "The revised implementation directly causes the corrected bounded-rejection and fallback-status behavior."

- timestamp: "2026-08-09T00:00:37Z"
  checked: "Final revised diff/status"
  found: "`git diff --check` and targeted trailing-whitespace scan are clean. The worktree contains the two tracked call files, the two new wake-lock source/test files, this debug session, and the unrelated Qwen debug session."
  implication: "The corrected local change is scoped and ready for the parent-owned deployment/phone checkpoint."

- timestamp: "2026-08-09T13:39:18Z"
  checked: "Parent focused wake-lock and adjacent live-call unit verification"
  found: "`npm run test:unit -- tests/unit/call-wake-lock.test.ts tests/unit/call-audio.test.ts tests/unit/call-state.test.ts` passed 24/24 assertions across 3 files."
  implication: "The parent context independently confirmed bounded wake-lock acquisition/rejection behavior and preserved call audio/state behavior."

- timestamp: "2026-08-09T13:40:49Z"
  checked: "Parent production client build"
  found: "`npm run build` completed successfully with the static adapter and emitted the production call route."
  implication: "The wake-lock lifecycle and visible fallback compile into the deployable web client."

- timestamp: "2026-08-09T13:41:27Z"
  checked: "Parent full client unit suite and diff hygiene"
  found: "`npm run test:unit` passed 119/119 assertions across 17 files; `git diff --check` passed."
  implication: "No client unit regression is visible beyond the focused live-call surface; the change is ready to commit and deploy through the canonical OMEN script."

## Eliminated

- hypothesis: "A missing HTTPS prerequisite or restrictive screen-wake-lock Permissions-Policy prevents an existing browser wake-lock implementation from working."
  evidence: "Canonical OMEN phone calls are served over HTTPS and no source defines a restrictive screen-wake-lock policy; more importantly, no wake-lock implementation existed anywhere in the client."
  timestamp: "2026-08-09T00:00:25Z"

- hypothesis: "Call payload, thread, voice, or persisted data selectively causes the phone idle timeout."
  evidence: "The complete client search found no data-dependent idle-screen or wake-lock path, and the normal device timeout occurs independently of call content."
  timestamp: "2026-08-09T00:00:25Z"

## Specialist Review

## Resolution

- root_cause: "The active browser call lifecycle originally never requested a Screen Wake Lock, so mobile devices used ordinary idle timeout; the first repair also re-requested from `finally` after every rejection, which creates a tight retry loop when a browser/platform persistently denies the lock."
- fix: "Revised the wake-lock helper so rejected requests report deduplicated fallback status without completion-driven retry; only explicit activation during an in-flight request can queue one retry. The call toolbar now shows a non-blocking unsupported/rejected screen-awake notice while preserving call controls."
- verification:
    target_test: { result: pass, command: "npm run test:unit -- tests/unit/call-wake-lock.test.ts", assertions: "6/6 pass" }
    mutation_check: { result: skipped, reason_if_skipped: "No Stryker dependency or configuration exists in web-ui/client; no mutation runner was installed." }
    no_op_deletion: { result: pass, deletion_justified_by_rca: true, evidence: "The revised diff remains additive except for removing the RCA-confirmed unsafe completion-driven retry; it adds fallback reporting and a non-blocking route notice without removing call, audio, or streaming branches." }
    adjacent_tests: { result: pass, suites_run: ["npm run build", "npm run test:unit -- tests/unit/call-audio.test.ts tests/unit/call-state.test.ts"], assertions: "production build passed; adjacent tests 18/18 pass" }
    revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true, evidence: "Scoped removal of revised helper/wiring retained the six-case driving test and reproduced the missing-helper RED failure; restoring the exact stash returned 6/6 GREEN." }
    browser_e2e: { result: skipped, reason_if_skipped: "Local Playwright Chromium executable is absent; retained mobile E2E assertions cover successful acquisition and the rejected-fallback notice for CI/deployed execution." }
    guardrail_verdict: accepted
    pending: "Canonical OMEN deployment and physical Android Chrome acceptance remain parent-owned."
- files_changed:
  - "web-ui/client/src/lib/call/wakeLock.ts"
  - "web-ui/client/src/routes/call/[threadId]/+page.svelte"
  - "web-ui/client/tests/unit/call-wake-lock.test.ts"
  - "web-ui/client/tests/e2e/call-mobile.spec.ts"
- oracle_type: "specified — the persisted user-goal contract explicitly requires an active visible live call to keep the screen awake and to return to normal sleep behavior after hangup."
