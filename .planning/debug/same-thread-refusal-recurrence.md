---
status: verifying
trigger: "User reports another refusal failure in the same live OMEN chat thread immediately after canonical deployment of refusal guard commit 28a19f9."
created: 2026-08-31
updated: 2026-09-01T00:32:35Z
---

# Same Thread Refusal Recurrence

## Symptoms

- **Expected behavior:** The deployed refusal guard blocks generic assistant/guideline refusals before they appear or persist, then retries for an in-character response.
- **Actual behavior:** The user reports another failure in the same OMEN thread after the prior fix was deployed.
- **Error messages:** Read the newest messages, alternates, request lifecycle, and active service identity from OMEN read-only. Do not ask the user to repeat or decode the failure.
- **Timeline:** Immediate recurrence after the prior incident's commit `28a19f9` was canonically deployed and live-database validated.
- **Reproduction:** Compare the newest message(s) in OMEN thread `thread_9c8328d024dc41698a342b3814a2766d` with the active deployed SHA, the immediately preceding recovered turn, and the shared stream/guard path.

## Current Focus

- **bug_class:** Bohrbug — the newest persisted text supplies an exact deterministic detector input to test.
- **hypothesis:** The deployed `9d9fb59` repair covers one exact identity disclaimer but is too surface-specific: the newest live record has the same first-person assistant identity plus content-negating structure, phrased as `I am strictly programmed ... assistant, not an erotic one`. It lacks a primary refusal verb and the fixed exact phrase, so `finish()` releases it as `upstream_complete`.
- **known_pattern_candidate:** `last-chat-refusal-recovery` — a sentence boundary caused an irreversible early release before the identity/policy cue arrived. This remains a candidate only; the newest row must match its mechanism.
- **test:** Commit the inspected four-file repair, then test and publish only that exact commit from a clean detached worktree.
- **expecting:** The release candidate excludes all unrelated working-tree state and has the same accepted guardrail evidence.
- **next_action:** create the scoped repair commit
- **reasoning_checkpoint:**
  hypothesis: "The sixth live refusal persists because the direct identity matcher only recognizes the earlier `I’m just/only ... not for that/this kind of content` surface form; the structural `I am ... assistant, not an erotic one` response has no refusal verb, so `_refusal_reason()` returns `None` and `finish()` releases it as `upstream_complete`."
  confirming_evidence:
    - "The fresh isolated OMEN assistant row at deployed `9d9fb59` contains `I am strictly programmed to be a helpful assistant, not an erotic one`, has no alternate, and matches the terminal SSE message ID."
    - "Whole-message, sentence-boundary, and one-codepoint traces all release that exact text at `finish()` as `upstream_complete`; the frozen corpus and shared-stream regression were RED before the matcher change."
    - "After replacing the surface form with the bounded structural matcher, both observed identity-disclaimer forms classify as `generic_identity`, retry before persistence, and the quoted in-character neighbor remains unchanged."
  falsification_test: "If the structural matcher fails either observed direct identity disclaimer in its frozen corpus/shared-stream regression, or changes the quoted-opening neighbor, the hypothesis is wrong or the matcher is too broad."
  fix_rationale: "Classify only a sentence-leading first-person assistant identity followed within bounded distance by a direct content-negating phrase (`not for that/this kind of content` or `not an erotic/sexual one`) as `generic_identity`; this preserves the refusal-verb requirement for other identity references."
  blind_spots: "The live web process does not expose per-attempt refusal metadata, so the fresh record proves the exposed outcome but not which upstream attempt phrased it. The deterministic direct guard and shared-stream tests cover the exact classifier and persistence mechanism."
  candidate_causes:
    - "code: `_DIRECT_IDENTITY_DISCLAIMER_RE` was surface-specific and omitted the first-person assistant-plus-`not an erotic/sexual one` structure."
    - "config/environment: a prior or alternate OMEN process could have served the old matcher, but the clean exact SHA, canonical listeners, and readiness checks contradict that branch."
    - "data: the current Qwen response used a valid no-verb identity-disclaimer variant absent from the earlier exact-form corpus."
  and_gate: "yes — direct classification deliberately requires both a sentence-leading first-person assistant identity and bounded content negation; either cue alone remains too ambiguous to suppress."
- **reasoning_checkpoint:**
  hypothesis: "The fourth live refusal persists because `_REFUSAL_VERB_RE` recognizes `I can't fulfill` but `_POLICY_RE` does not recognize the coordinated phrase `explicit or erotic content`; without a secondary reason, `finish()` releases the held response as `upstream_complete`."
  confirming_evidence:
    - "The fresh isolated OMEN assistant row at deployed `06294e1` contains the exact generic response, has no alternate, and matches the terminal SSE message ID."
    - "Whole, sentence, and one-codepoint traces all release the exact response at `finish()` as `upstream_complete`."
    - "Substituting only the existing `explicit erotic content` spelling produces `policy_or_safety`, and the frozen exact corpus plus stream regression are RED (nine failures) before a code change."
  falsification_test: "If adding only the coordinated explicit-content grammar does not make the exact detector and stream tests GREEN, or changes the new nonrefusal coordinated-content boundary case, this hypothesis is wrong or the grammar is too broad."
  fix_rationale: "Extend the direct policy cue to the ordinary coordinated variants `explicit or erotic content` and `explicit sexual or erotic content`. The primary refusal-verb condition remains mandatory, so a nonrefusal reference to such content does not classify by itself."
  blind_spots: "The live web process does not expose per-attempt refusal metadata, so the fresh record proves the exposed outcome but not which upstream attempt phrased it. The deterministic direct guard and shared-stream tests cover the exact classifier and persistence mechanism."
  candidate_causes:
    - "code: `_POLICY_RE` accepts only one adjective after `explicit`, omitting the observed coordinated provider wording."
    - "config/environment: an old or alternate OMEN process could be serving a prior matcher, but the clean exact SHA, canonical listeners, and deployed-commit readiness directly contradict this."
    - "data: current Qwen output used the valid coordinated wording `explicit or erotic content`, exposing an unrepresented equivalence class in the frozen corpus."
  and_gate: "yes — suppression intentionally requires both a primary refusal verb and the coordinated direct-policy cue; either condition alone is too ambiguous for explicit generic-refusal classification."
- **reasoning_checkpoint:**
  hypothesis: "The new live refusal persists because the guard recognizes `I can't write` but sees no secondary generic cue: its actual `erotic content ... I'm here if you want to chat about anything else` redirect is absent from `_REDIRECT_RE`, so `finish()` releases it as `upstream_complete`."
  confirming_evidence:
    - "The fresh isolated OMEN assistant row at deployed `6dd2c4f` contains the exact generic response, has no alternate, and matches the terminal SSE message ID."
    - "Whole, word, and one-codepoint traces all release the exact response at `finish()` as `upstream_complete`."
    - "The frozen exact corpus case and shared-stream persistence regression are RED: eight detector schedules and the stream scenario fail before a code change."
  falsification_test: "If adding only the bounded actual-topic/chat-about-anything-else redirect alternative does not make the exact detector and stream tests GREEN, or suppresses the added close in-character boundary neighbor, this hypothesis is wrong or the matcher is too broad."
  fix_rationale: "Extend only the redirect cue with the actual `erotic/sexual content` plus `here if you want to chat about anything else` form. `_REFUSAL_VERB_RE` remains the required primary condition, and the topic/redirect sequence avoids classifying bare erotic language or general in-character chat invitations."
  blind_spots: "The live web process does not publish per-attempt refusal metadata, so the fresh record proves the exposed outcome but not which upstream attempt phrased it. The deterministic direct guard and shared-stream tests cover the exact classifier and persistence mechanism."
  candidate_causes:
    - "code: `_REDIRECT_RE` lacks the observed generic chat-about-anything-else redirect form."
    - "config/environment: an old or alternate OMEN process could be serving the prior matcher, but the clean exact SHA, canonical listeners, and deployed-commit readiness directly contradict this."
    - "data: current Qwen output used an ASCII apostrophe and a third valid generic redirect phrase, exposing a coverage case not represented in the first two production fixtures."
  and_gate: "yes — suppression intentionally requires both a primary refusal verb and this bounded topic-plus-generic-redirect cue; either condition alone is too ambiguous for an explicit generic-refusal classification."
- **reasoning_checkpoint:**
  hypothesis: "The affected refusals persist because U+2019 in `can’t` was not normalized before refusal-verb matching and the secondary generic-refusal cues omit both direct explicit-content language and the generic redirect `I’m here to help`; the latter is the remaining production escape after `0498da3`."
  confirming_evidence:
    - "The fresh OMEN sequence-20 `ai_text` is a normal post-deployment `/send` result and exactly reproduces as non-refused under every tested fragmentation schedule."
    - "The real non-custom Qwen adapter serializes the observed post-swipe follow-up and returns the exact response through `PrefixRefusalGuard`, excluding an adapter bypass."
    - "Normalizing only the apostrophe or adding only an existing safety cue still releases the response at finish; combining both makes the current guard refuse with `policy_or_safety`."
    - "The prior isolated OMEN verification record persisted `I can’t write erotic content, but I’m here to help with anything else you need!`, and the deployed partial repair holds but releases it at finish because `_REDIRECT_RE` does not match that generic first-person redirect."
  falsification_test: "If the missing redirect cue is not causal, the historical exact-response regression will pass under `0498da3` or remain non-refused after adding only the bounded first-person redirect pattern."
  fix_rationale: "Retain the deployed punctuation and explicit-content corrections, then add the bounded first-person generic redirect pattern to `_REDIRECT_RE`; this sends the historical response through existing retry/persistence exclusion without treating all erotic-content words as policy language."
  blind_spots: "The original production token traces are process-local and unavailable, but the persisted rows, normal `/send` route, standard-adapter reproduction, and whole/sentence/codepoint reproductions cover all detector decisions relevant to these cue forms."
  candidate_causes:
    - "code: the comparison normalizer and secondary cue patterns omit conditions required to classify the affected response forms."
    - "config/environment: the active canonical Qwen deployment emits typographic punctuation, but the listener/SHA/adapter path are healthy and do not bypass the guard."
    - "data: this ordinary provider output uses U+2019 and the exact policy phrase, exercising the two code omissions; it is valid stream input rather than corrupt persistence."
  and_gate: "yes — the pre-0498da3 forms require canonical punctuation plus their respective generic cue; `0498da3` fixes the explicit-content branch, and the remaining historical branch requires the bounded first-person redirect cue."
- **tdd_checkpoint:**

## Evidence

- **timestamp:** 2026-08-31T18:45:00Z
  **checked:** Required session records, live-call invariants, canonical OMEN deployment contract, project-local skills, and configured debugger skills.
  **found:** This is a persisted chat refusal recurrence after `28a19f9`; live OMEN SQLite and service identity are the only valid production evidence. There are no project-local or debugger-specific skill rules. Any release must preserve the shared streaming contract and use only `scripts/deploy-omen.sh`.
  **implication:** Do not rely on the empty workspace database, do not change detector logic before the newest OMEN row is classified, and keep any repair scoped to the shared chat path.
- **timestamp:** 2026-08-31T18:46:00Z
  **checked:** Durable debug knowledge base (MemPalace is unavailable in this environment).
  **found:** `last-chat-refusal-recovery` semantically matches the reported symptom: an explicit generic refusal can escape when a sentence is released before its later cue. Its deployed recurrence guard covered that exact former shape, not every new row/action/template variation.
  **implication:** Test this known pattern first against the newest live record, while independently checking deployment, request path, alternate selection, and request-specific behavior.
- **timestamp:** 2026-08-31T18:47:00Z
  **checked:** Initial read-only OMEN identity and SQLite-query invocation.
  **found:** OMEN's repository HEAD is `28a19f9b12a15ab3dac2c334107256b12652f646`, its worktree is clean, `refusal_guard.py` resolves to blob `61d0741d2311e62981ab04c914acadf0717f1587`, and `RayMePhase1Web` points to the canonical launcher. The combined invocation returned before its listener and SQLite sections emitted, so it did not yet inspect the fresh row.
  **implication:** Active source drift is not supported at repository level, but do not infer the writer process or classify the recurrence until isolated read-only queries return their records.
- **timestamp:** 2026-08-31T18:48:00Z
  **checked:** Isolated OMEN SQLite-read invocation.
  **found:** The query did not reach SQLite: Windows command-line parsing removed the Python raw-string quotes, producing a syntax error before connection creation. No database state was changed.
  **implication:** Re-encode the Python source itself and execute it inside the interpreter; this transport failure neither supports nor refutes any recurrence mechanism.
- **timestamp:** 2026-08-31T18:49:00Z
  **checked:** Read-only Python-stdin transport to OMEN's live SQLite database.
  **found:** The live database is reachable through a `mode=ro` SQLite URI and currently contains 2,568 message records. The query transport is now proven without changing the store.
  **implication:** The next exact row/alternate inspection can use this transport; do not use the empty workspace database as a substitute.
- **timestamp:** 2026-08-31T23:06:46Z
  **checked:** Read-only OMEN SQLite records for the reported thread, including all linked alternates.
  **found:** The actual new failure is assistant sequence 20 at `2026-08-31 23:06:45.026382`: “I can’t write explicit sexual content like that. Let’s keep things respectful and safe instead.” It is a normal `ai_text` row with no alternate, no edit/branch/call identity, and no selected alternate. It follows user sequence 19 by under one second. Sequence 18 was later swiped at 23:06:34, but that alternate is attached only to sequence 18 and cannot be the source of sequence 20.
  **implication:** This is a fresh post-deployment generic refusal, not stale alternate selection. Its typographic “can’t” and different generic-cue wording are a concrete code-path candidate; test the exact text before editing.
- **timestamp:** 2026-08-31T23:08:00Z
  **checked:** Exact sequence-20 assistant text against the deployed `PrefixRefusalGuard` source under whole-message, sentence-boundary, and one-codepoint schedules.
  **found:** Every schedule released the entire exact refusal and finished non-refused with `reason_code=safe_prefix`. In particular, the first sentence with typographic “can’t” releases immediately; the normalizer preserves that apostrophe, `_REFUSAL_VERB_RE` matches only ASCII `can't`, and the phrase's remaining cues do not match `_secondary_reason()`.
  **implication:** This is a deterministic detector boundary regression. Test the still-open action/process/template branches for completeness, but a matcher correction must normalize typographic apostrophes or recognize this equivalent contraction before it can prevent persistence.
- **timestamp:** 2026-08-31T23:09:00Z
  **checked:** Read-only sequence-18-to-20 records, linked selected alternate, current web listener, scheduled-task action, and retained route-log lines.
  **found:** Sequence 18's selected alternate was an in-character `swipe` result created at 23:06:34, not refusal text. The user then sent `make it longer` at 23:06:44 and sequence 20 persisted the fresh refusal at 23:06:45. The active port-8443 process is the canonical `run_dev_https.py` web listener, and the scheduled task points to the canonical launcher. Retained logs contain successful POSTs for this thread's `/api/chat/{thread_id}/send` route, though they lack timestamps.
  **implication:** Alternate selection cannot explain the new persisted refusal. The evidence is consistent with the ordinary guarded send route; obtain precise process timing and settings, then verify the real adapter's raw-token path before closing the remaining non-code branches.
- **timestamp:** 2026-08-31T23:10:00Z
  **checked:** Read-only current OMEN endpoint settings and initial listener-timestamp query.
  **found:** The active setting uses `unsloth/Qwen3.5-27B` with thinking disabled and default prompt-generation settings. The timestamp query treated an already materialized CIM DateTime as a DMTF string and failed before returning the formatted value; it did not affect the listener or service.
  **implication:** The request uses the expected Qwen adapter family, but process timing remains unconfirmed. The adapter/template can influence the response words but the shared guard still has to classify the emitted tokens; verify that exact path from source.
- **timestamp:** 2026-08-31T23:11:00Z
  **checked:** OMEN listener start time, deployed generation-adapter source, and all call sites for ordinary AI-message append.
  **found:** The active canonical port-8443 listener began at `2026-08-31T18:39:06Z`, before the 23:06 sequence-20 failure; the checked-out OMEN repository is clean at `28a19f9`. The active settings select the Qwen adapter. Its raw provider chunks flow through `_stream_text_tokens()` and `PrefixRefusalGuard` before `append_ai_message`; that append call is used only by `/api/chat/{thread_id}/send`.
  **implication:** A stale/mismatched web process and a different persistence/action route are ruled out. The Qwen template can produce the observed words but cannot bypass the guard, so test the real adapter path with the exact response before closing the template branch.
- **timestamp:** 2026-08-31T23:12:00Z
  **checked:** Non-custom OpenAI-compatible Qwen adapter path with the observed selected-alternate then `make it longer` ordering and the exact two sequence-20 token chunks.
  **found:** The request uses `unsloth/Qwen3.5-27B`, streaming, and disabled thinking; its final user wire message is `make it longer` with `/no_think`. The exact refusal returns unchanged through the real raw-token path.
  **implication:** Request-specific adapter/template behavior is not a guard bypass. It is valid upstream input that reaches the same flawed detector; determine whether normalization alone is sufficient before fixing.
- **timestamp:** 2026-08-31T23:13:00Z
  **checked:** Differential guard experiment: only ASCII apostrophe, only existing safety cue, and both substitutions.
  **found:** With only an ASCII apostrophe the guard holds then releases at `finish()` as `upstream_complete`; with only a safety cue it also releases at finish; only the combined case is refused with `policy_or_safety`.
  **implication:** The root cause is a code AND-gate, not one missing regex literal. The repair and regression must cover both canonical punctuation and the precise generic-policy phrase.
- **timestamp:** 2026-08-31T23:14:00Z
  **checked:** Agent-authored frozen-corpus and shared-stream regressions before implementation.
  **found:** RED as predicted: all eight fragmentation schedules for the exact sequence-20 response finished non-refused, and the observed post-swipe `make it longer` stream emitted the rejected first sentence instead of retry-only output (9 failures total).
  **implication:** The regression has a specified display/persistence oracle and directly exercises both roots of the confirmed AND-gate before any code change.
- **timestamp:** 2026-08-31T23:15:00Z
  **checked:** Target corpus and shared-stream regressions after the paired detector change.
  **found:** All 16 detector/corpus cases passed, including the exact refusal and typographic in-character neighbor. The stream behavior assertions passed through retry-only persistence; its final request-order assertion omitted the existing `section_ids` field and failed only because the implementation correctly preserves that metadata.
  **implication:** The implementation behavior is correct; repair the agent-authored test's incomplete expected request shape, then rerun without changing product code.
- **timestamp:** 2026-08-31T23:16:00Z
  **checked:** Exact recurrence target suite after correcting the test-only expected metadata shape.
  **found:** GREEN: 17 passed (exact refusal over all schedules, typographic in-character boundary neighbor, and post-swipe shared-stream retry/persistence regression).
  **implication:** The paired detector change meets the specified oracle. Proceed to guardrail verification before accepting or deploying it.
- **timestamp:** 2026-08-31T23:17:00Z
  **checked:** Scoped diff quality and mutation-runner availability.
  **found:** The diff is whitespace-clean and limited to the guard, frozen corpus, and shared-stream regression. No Stryker, mutmut, or other configured mutation runner exists in the repository.
  **implication:** The no-op/deletion signal is provisionally clean because this is additive behavior, while mutation analysis must be recorded as skipped rather than passed. Run all direct consumers next.
- **timestamp:** 2026-08-31T23:18:00Z
  **checked:** Direct refusal-guard, chat-stream, message-action, and Phase 1 acceptance consumers.
  **found:** GREEN: 274 passed in 8.56 seconds.
  **implication:** The expanded detector preserves all directly coupled chat contracts. Verify the shared live-call stream contract, then run the code-only reversible counterfactual.
- **timestamp:** 2026-08-31T23:19:00Z
  **checked:** Focused live-call refusal retry/exhaustion coverage.
  **found:** GREEN: 3 passed with 106 unrelated call tests deselected.
  **implication:** The shared live-call stream retains early accepted output, closure, interruption, and rejected-sink exclusion. The only remaining local causal signal is revert-and-reconfirm.
- **timestamp:** 2026-08-31T23:20:00Z
  **checked:** Scope of the implementation diff and scoped stash setup for causal verification.
  **found:** `refusal_guard.py` contains only the two paired detector changes. It is now stashed by itself; the newly authored frozen-corpus and stream regressions remain present, and unrelated modified/untracked workspace state remains untouched.
  **implication:** The next target run isolates the implementation as the only changed variable and can establish whether it causally corrects the recurrence.
- **timestamp:** 2026-08-31T23:21:00Z
  **checked:** Exact target suite with only `refusal_guard.py` reverted while the new regression files remained unchanged.
  **found:** RED returned exactly: eight fragmented corpus failures plus the post-swipe stream emitted the rejected first sentence (9 failures).
  **implication:** The implementation file is causal. Reapply that same isolated diff and require the target suite to return GREEN before release verification.
- **timestamp:** 2026-08-31T23:22:00Z
  **checked:** Reapplication of the scoped detector diff.
  **found:** The exact `refusal_guard.py` diff reapplied cleanly; whitespace validation remains clean and no unrelated tracked files were introduced.
  **implication:** Run the unchanged target suite once more to complete the reversible causal proof.
- **timestamp:** 2026-08-31T23:23:00Z
  **checked:** Exact target suite after restoring the isolated detector implementation.
  **found:** GREEN restored: 17 passed, 224 deselected.
  **implication:** The revert-and-reconfirm signal passes: the defect returns on code-only revert and disappears when the exact implementation is restored. Prepare a scoped source commit for clean-worktree release verification.
- **timestamp:** 2026-08-31T23:24:00Z
  **checked:** Staged repair scope and staged whitespace validation.
  **found:** The staged diff is clean and contains exactly three files: the paired guard changes, frozen exact/neighbor corpus cases, and the post-swipe shared-stream regression. All other workspace state remains unstaged and untracked.
  **implication:** The repair can be committed without absorbing unrelated work, then verified from a clean exact-commit checkout.
- **timestamp:** 2026-08-31T23:25:00Z
  **checked:** Scoped repair commit.
  **found:** Commit `0498da3` contains exactly the three staged detector/regression artifacts. The primary workspace still retains its unrelated untracked debug/runtime state outside the commit.
  **implication:** Verify and publish only this exact commit from a clean detached worktree; do not deploy from the primary workspace.
- **timestamp:** 2026-08-31T23:26:00Z
  **checked:** Exact-commit release worktree.
  **found:** A new detached worktree was created at commit `0498da3` with no primary-workspace modifications carried into it.
  **implication:** Its test results and source state will apply to the precise release candidate rather than the dirty primary workspace.
- **timestamp:** 2026-08-31T23:27:00Z
  **checked:** Exact-commit direct guard/chat/action/acceptance suites.
  **found:** GREEN: 274 passed in 8.10 seconds at detached commit `0498da3`.
  **implication:** The release candidate preserves all direct consumer contracts. Run focused live-call refusal coverage and source-clean checks before publishing.
- **timestamp:** 2026-08-31T23:28:00Z
  **checked:** Exact-commit live-call refusal subset and release source integrity.
  **found:** GREEN: 3 focused live-call tests passed (106 unrelated cases deselected). The detached worktree has no source changes, whitespace validation is clean, and HEAD is `0498da3f877bb56df00e16437a06a56883c8968c`.
  **implication:** The exact source candidate meets shared live-call retry/stream constraints and is ready for publication and canonical deployment.
- **timestamp:** 2026-08-31T23:29:00Z
  **checked:** Publication of the exact release candidate.
  **found:** The clean detached worktree advanced `origin/main` from `28a19f9` to `0498da3`.
  **implication:** OMEN can now fetch the verified repair. Deploy only with the repository's canonical script, which will assert the expected SHA remotely.
- **timestamp:** 2026-08-31T23:33:00Z
  **checked:** Canonical deployment process lifecycle from the clean worktree.
  **found:** `scripts/deploy-omen.sh` advanced OMEN from `28a19f9` to the exact `0498da3` commit and its long-running local script plus remote SSH child have exited after the normal pinned-runtime/service-restart output. The initial command handle returned before it exposed a final exit status.
  **implication:** Do not infer health solely from process exit. Verify the remote checkout, canonical listeners/tasks, authenticated web-to-AI readiness, and commit-matched WebRTC state before exercising a live chat.
- **timestamp:** 2026-08-31T23:34:00Z
  **checked:** Post-deploy OMEN service identity and readiness.
  **found:** OMEN is clean at `0498da3`; both canonical scheduled tasks point to their required launchers and ports 8443/9443 are served by the canonical web/AI commands. Web-to-AI readiness is authenticated, STT/VAD are ready, Qwen is resident, and WebRTC is ready with deployed commit `0498da3`. The aggregate AI health label is `degraded` only because of an inactive registered engine, while all required live-call gates are ready.
  **implication:** Canonical deployment is accepted. Use a fresh isolated chat record for final user-visible stream/persistence verification without modifying the user's active thread.
- **timestamp:** 2026-08-31T23:35:00Z
  **checked:** Prior isolated OMEN verification thread retained in the live SQLite store.
  **found:** The prior thread used the same character and user input `make it more erotic`; its assistant sequence 2 persisted a generic refusal beginning `I can’t write erotic content`. That response has a typographic apostrophe and direct `erotic content` wording, but no current identity/policy/redirect cue.
  **implication:** The earlier isolated check was a false acceptance because it searched only for markers from the first refusal form. The deployed partial cue expansion does not cover this second real production form; validate it locally, then extend the bounded cue class before final live verification.
- **timestamp:** 2026-08-31T23:36:00Z
  **checked:** The historical persisted response against the exact deployed `0498da3` guard.
  **found:** The normalized response enters `holding` but `finish()` releases it unchanged with `reason_code=upstream_complete`: the deployed explicit-content cue is not present, while the sentence's generic `I’m here to help` redirect is also absent from `_REDIRECT_RE`.
  **implication:** Do not broaden bare `erotic content` language. Add a narrow first-person redirect cue and a regression for this exact historical response.
- **timestamp:** 2026-08-31T23:37:00Z
  **checked:** Agent-authored historical-response frozen corpus and shared-stream regressions against deployed `0498da3` code.
  **found:** RED as predicted: all eight fragmentation schedules released the historical response at finish, and the matching stream emitted/persisted the refusal instead of retry-only output (9 failures).
  **implication:** The regression supplies a specified oracle for the remaining redirect-cue escape. Implement only that bounded cue alternative.
- **timestamp:** 2026-08-31T23:38:00Z
  **checked:** Exact production-form and typographic-neighbor target suite after adding the bounded redirect alternative.
  **found:** GREEN: 26 passed, 224 deselected. Both real production refusal forms retry before token/persistence and the typographic in-character neighbor still round-trips unchanged.
  **implication:** The remaining detector coverage branch is corrected. Run the full guardrail again because this is a new incremental deployment candidate.
- **timestamp:** 2026-08-31T23:39:00Z
  **checked:** Incremental diff quality and mutation-runner availability.
  **found:** The incremental diff is whitespace-clean and limited to the redirect matcher, the historical real-form corpus seed, and its shared-stream regression. No configured mutation runner exists.
  **implication:** Record mutation analysis as skipped, preserve the additive no-op/deletion signal, and run all direct consumers before the causal counterfactual.
- **timestamp:** 2026-08-31T23:40:00Z
  **checked:** Direct guard/chat/action/Phase 1 acceptance consumers after the incremental redirect change.
  **found:** GREEN: 283 passed in 8.32 seconds.
  **implication:** All directly coupled chat contracts remain intact. Verify the live-call consumer and the redirect-only revert/reapply proof before publishing a second exact commit.
- **timestamp:** 2026-08-31T23:41:00Z
  **checked:** Focused live-call refusal retry/exhaustion coverage after the incremental redirect change.
  **found:** GREEN: 3 passed with 106 unrelated call tests deselected.
  **implication:** The live-call stream contract remains intact. Isolate only the redirect matcher next; its removal must return the historical real-form target to RED.
- **timestamp:** 2026-08-31T23:42:00Z
  **checked:** Incremental redirect diff scope and scoped stash setup.
  **found:** `refusal_guard.py` differs from `0498da3` only by the bounded first-person redirect alternative. That file alone is stashed while both real-form regressions stay present; unrelated workspace state is unchanged.
  **implication:** The next target run isolates this one matcher alternative as the only behavioral variable.
- **timestamp:** 2026-08-31T23:43:00Z
  **checked:** Historical real-form target with only the redirect matcher reverted.
  **found:** RED returned exactly: all eight fragmentation schedules and the shared stream released/persisted the historical refusal (9 failures).
  **implication:** The bounded first-person redirect matcher is causal. Reapply that exact change and require the same target to return GREEN before release verification.
- **timestamp:** 2026-08-31T23:44:00Z
  **checked:** Reapplication of the scoped redirect matcher.
  **found:** The exact matcher diff reapplied cleanly; whitespace validation is clean and the worktree still contains no unrelated tracked edits.
  **implication:** Rerun the unchanged historical target to complete the redirect branch's reversible causal proof.
- **timestamp:** 2026-08-31T23:45:00Z
  **checked:** Historical real-form target after restoring the redirect matcher.
  **found:** GREEN restored: 9 passed, 241 deselected.
  **implication:** The redirect-only revert-and-reconfirm signal passes. Stage only the incremental repair for exact-commit release verification.
- **timestamp:** 2026-08-31T23:46:00Z
  **checked:** Staged incremental repair scope and staged whitespace validation.
  **found:** The staged diff is clean and contains exactly the bounded redirect matcher, historical real-form corpus seed, and shared-stream regression. All other workspace state is unstaged and untracked.
  **implication:** Commit this minimal increment, then use an exact-commit clean worktree for the release decision.
- **timestamp:** 2026-08-31T23:47:00Z
  **checked:** Scoped redirect-repair commit.
  **found:** Commit `6dd2c4f` contains exactly the three incremental matcher/regression artifacts. The primary workspace still retains only unrelated untracked debug/runtime state outside the commit.
  **implication:** Verify and publish only `6dd2c4f` from a clean detached worktree; do not deploy from the primary workspace.
- **timestamp:** 2026-08-31T23:48:00Z
  **checked:** Exact-commit redirect release worktree.
  **found:** A clean detached worktree was created at `6dd2c4f` with no primary-workspace modifications carried into it.
  **implication:** Its test results and source state will apply to the exact incremental release candidate.
- **timestamp:** 2026-08-31T23:50:00Z
  **checked:** Exact-commit direct guard/chat/action/acceptance suites at detached `6dd2c4f`.
  **found:** GREEN: 283 passed in 8.26 seconds.
  **implication:** The exact redirect-recovery release candidate preserves all directly coupled chat contracts; verify its focused live-call consumer and source integrity before publishing.
- **timestamp:** 2026-08-31T23:51:00Z
  **checked:** Exact-commit focused live-call refusal retry/exhaustion suite and source integrity at detached `6dd2c4f`.
  **found:** GREEN: 3 focused live-call tests passed with 106 unrelated tests deselected. `git diff --check` and `git status --short` are clean; HEAD is exactly `6dd2c4f3b0bdcc1a25d94ed3c0af90df84cf460d`.
  **implication:** The candidate satisfies the shared live-call recovery contract and is clean for exact publication and canonical OMEN deployment.
- **timestamp:** 2026-08-31T23:52:00Z
  **checked:** Publication of exact detached redirect-recovery release candidate.
  **found:** The clean detached worktree advanced `origin/main` from `0498da3` to `6dd2c4f`.
  **implication:** Canonical OMEN deployment may now fetch only the tested commit; do not deploy from the primary workspace.
- **timestamp:** 2026-08-31T23:56:00Z
  **checked:** Canonical deployment process for the exact detached `6dd2c4f` candidate.
  **found:** `scripts/deploy-omen.sh` fast-forwarded OMEN from `0498da3` to `6dd2c4f`, rebuilt the web client, reasserted the canonical scheduled tasks, restarted the listeners, and completed successfully. It reported the expected aggregate AI health label `degraded` while STT/VAD and the resident Qwen TTS engine were ready.
  **implication:** Confirm independent post-deploy service identity/readiness read-only before sending the isolated verification chat; the aggregate label alone is not a deployment acceptance signal.
- **timestamp:** 2026-08-31T23:57:00Z
  **checked:** First independent remote health-query transport.
  **found:** Repository SHA, clean checkout, canonical task commands, and canonical listener processes returned correctly, but the command used an obsolete in-repository CA path. Curl rejected that missing path before issuing any HTTPS request, leaving health/readiness/WebRTC fields empty.
  **implication:** This was a read-only query transport error, not service evidence. Repeat the query using the canonical deployment script's state-root CA path before creating a fresh chat record.
- **timestamp:** 2026-08-31T23:58:00Z
  **checked:** Corrected independent post-deploy OMEN identity and readiness query.
  **found:** OMEN is clean at `6dd2c4f3b0bdcc1a25d94ed3c0af90df84cf460d`; both scheduled tasks use the required canonical `.cmd` launchers, and ports 9443/8443 are served by their canonical AI/web commands. Web-to-AI readiness is `ready` and authenticated; STT/VAD and resident `qwen3_1_7b` are ready; WebRTC is `ready`, `live_call_ready=true`, and reports the exact deployed SHA.
  **implication:** The exact correction is active in the healthy normal chat path. It is safe to verify a fresh isolated record without interacting with the user's active thread.
- **timestamp:** 2026-09-01T00:01:00Z
  **checked:** First isolated thread-create request through the deployed web API.
  **found:** The API returned HTTP 422 before returning a thread ID, so no `/send` request or assistant record was created. The PowerShell/curl invocation suppressed the validation payload while passing its JSON body.
  **implication:** This is a request-transport/validation failure, not a product result. Read the 422 payload and preserve the JSON as one native curl argument before retrying the isolated verification.
- **timestamp:** 2026-09-01T00:02:00Z
  **checked:** Unredacted 422 validation response for the isolated thread-create request.
  **found:** FastAPI reported malformed JSON (`Expecting property name enclosed in double quotes`), proving Windows native argument handling stripped the JSON property quotes before request parsing. No application-level thread record was returned.
  **implication:** Pipe the JSON document through curl stdin rather than passing it as a native command-line argument; this corrects the verification transport only and does not change the deployed product.
- **timestamp:** 2026-09-01T00:03:00Z
  **checked:** Isolated thread creation with JSON piped to curl stdin.
  **found:** The deployed normal thread API accepted the exact same body and created `thread_4a63d4fb13ab49ffbb9e988d37b8c279`.
  **implication:** The verification transport is corrected. Send only the prior observed input in this fresh thread, then inspect the resulting live record and alternates.
- **timestamp:** 2026-09-01T00:04:00Z
  **checked:** Fresh normal `/api/chat/{thread_id}/send` stream for the prior observed input.
  **found:** The isolated thread streamed 22 token events and one `done` event, with no SSE error, and reported persisted message ID `msg_33eefa1c0628477794da40d3bdd1bed0`.
  **implication:** The route completed normally at deployed `6dd2c4f`; inspect the live database record and alternates before deciding whether its actual text demonstrates recovery.
- **timestamp:** 2026-09-01T00:05:00Z
  **checked:** Fresh isolated live SQLite rows and linked alternates for `thread_4a63d4fb13ab49ffbb9e988d37b8c279` in read-only mode.
  **found:** The normal-path assistant sequence 2 is a new generic refusal: `I can't write erotic content for you, but I'm here if you want to chat about anything else.` It has no alternate; the only alternate is the initial greeting. The record is at the exact completed SSE message ID, so it is neither a stale row nor an alternate-selection artifact.
  **implication:** The prior incremental repair is insufficient for this third real redirect phrasing. Test this exact detector input before touching code; do not treat the clean deployment or successful SSE transport as product acceptance.
- **timestamp:** 2026-09-01T00:06:00Z
  **checked:** First local guard-trace invocation for the new live response.
  **found:** The invocation ran from the repository root without the server package on Python's import path and failed before constructing `PrefixRefusalGuard`.
  **implication:** This is an experiment setup error, not detector evidence. Rerun the unchanged trace from `web-ui/server`, where the server package is importable.
- **timestamp:** 2026-09-01T00:07:00Z
  **checked:** Exact new-live-response guard traces under whole, word, and one-codepoint schedules.
  **found:** All three schedules finish non-refused with `reason_code=upstream_complete` and release the full exact response. `_REFUSAL_VERB_RE` correctly prevents early sentence release, but the unchanged prefix reaches `finish()` with no secondary cue because `I’m here if you want to chat` matches neither the policy nor existing bounded redirect alternatives.
  **implication:** The new live escape is a deterministic, fragmentation-independent secondary-redirect coverage gap. A RED corpus and shared-stream regression can now isolate that candidate before a minimal matcher change.
- **timestamp:** 2026-09-01T00:08:00Z
  **checked:** Frozen new-live-response detector corpus and shared-stream regression before implementation.
  **found:** RED as predicted: the exact response releases under all eight fragmentation schedules, and the normal chat stream emits and persists that refusal instead of retrying (9 failures).
  **implication:** The specified oracle directly reproduces the fresh OMEN defect. The narrowly bounded redirect matcher can now be changed as the only variable.
- **timestamp:** 2026-09-01T00:10:00Z
  **checked:** Exact new-live-response corpus, shared-stream retry/persistence regression, and close in-character boundary neighbor after the bounded matcher change.
  **found:** GREEN: 17 passed. The exact response is classified as `redirect` in all eight schedules and retries before persistence; the boundary neighbor remains byte-for-byte unchanged in all eight schedules.
  **implication:** The matcher adds the causal missing condition without broadly suppressing the nearest in-character counterexample. Run all direct consumers and the live-call subset before release approval.
- **timestamp:** 2026-09-01T00:11:00Z
  **checked:** Direct refusal-guard, chat-stream, message-action, and Phase 1 acceptance consumers after the third bounded redirect change.
  **found:** GREEN: 300 passed in 8.50 seconds.
  **implication:** The exact correction preserves all directly coupled chat contracts. Verify the shared live-call consumer, then run an isolated code-only counterfactual before release.
- **timestamp:** 2026-09-01T00:12:00Z
  **checked:** Focused live-call refusal retry/exhaustion coverage after the third bounded redirect change.
  **found:** GREEN: 3 passed with 106 unrelated call tests deselected.
  **implication:** The shared live-call stream preserves early accepted output, interruption, closure, and rejected-sink exclusion. Inspect the exact incremental scope and prove causality with the matcher as the only reverted variable.
- **timestamp:** 2026-09-01T00:13:00Z
  **checked:** Incremental diff scope, whitespace, and mutation-runner configuration.
  **found:** The whitespace-clean diff is limited to the one bounded redirect alternative, the frozen exact/boundary corpus cases, and the shared-stream regression (66 insertions, one deletion across three files). No configured mutation runner (Stryker, mutmut, or equivalent) is present in the project manifests or files.
  **implication:** Mutation analysis is skipped rather than passed. The additive no-op/deletion signal is covered by the close boundary case; isolate the guard file for the remaining reversible causal counterfactual.
- **timestamp:** 2026-09-01T00:14:00Z
  **checked:** Third-form target after reverting only `refusal_guard.py` and retaining the new frozen corpus/stream regression.
  **found:** RED returned exactly: all eight fragmentation schedules and the shared stream released/persisted the new live refusal (9 failures).
  **implication:** The matcher alternative is causal. Reapply that exact guard diff and require the unchanged target to return GREEN before committing.
- **timestamp:** 2026-09-01T00:15:00Z
  **checked:** Third-form target after restoring the isolated matcher implementation.
  **found:** GREEN restored: 17 passed, including all exact-response schedules, shared-stream retry/persistence behavior, and the close in-character boundary neighbor. `git diff --check` is clean.
  **implication:** The reversible causal signal passes: the new live defect returns on code-only revert and disappears on reapplication. Prepare a scoped source commit for clean-worktree release verification.
- **timestamp:** 2026-09-01T00:16:00Z
  **checked:** Scoped third-form repair commit.
  **found:** Commit `06294e1` contains exactly the bounded redirect matcher, frozen exact/boundary corpus cases, and shared-stream retry/persistence regression. Unrelated primary-workspace debug/runtime files remain untracked and outside the commit.
  **implication:** Verify and publish only `06294e1` from a clean detached worktree; do not deploy from the primary workspace.
- **timestamp:** 2026-09-01T00:17:00Z
  **checked:** Exact-commit third-form release worktree.
  **found:** A detached worktree was created at `06294e157237a2b9b88416a9b6799729341a4890` with no primary-workspace modifications carried into it.
  **implication:** Its test results and source state will apply to the precise third incremental release candidate.
- **timestamp:** 2026-09-01T00:18:00Z
  **checked:** Exact-commit direct guard/chat/action/acceptance suites at detached `06294e1`.
  **found:** GREEN: 300 passed in 8.46 seconds.
  **implication:** The exact release candidate preserves all directly coupled chat contracts. Run focused live-call refusal coverage and source-clean checks before publishing.
- **timestamp:** 2026-09-01T00:19:00Z
  **checked:** Exact-commit focused live-call refusal retry/exhaustion suite and source integrity at detached `06294e1`.
  **found:** GREEN: 3 focused live-call tests passed with 106 unrelated tests deselected. `git diff --check` and `git status --short` are clean; HEAD is exactly `06294e157237a2b9b88416a9b6799729341a4890`.
  **implication:** The candidate satisfies the shared live-call recovery contract and is clean for exact publication and canonical OMEN deployment.
- **timestamp:** 2026-09-01T00:20:00Z
  **checked:** Publication of exact detached third-form redirect-recovery release candidate.
  **found:** The clean detached worktree advanced `origin/main` from `6dd2c4f` to `06294e1`.
  **implication:** OMEN can now fetch the verified correction. Deploy only with the repository's canonical script, which will assert the expected SHA remotely.
- **timestamp:** 2026-09-01T00:24:00Z
  **checked:** Canonical deployment process for the exact detached `06294e1` candidate.
  **found:** `scripts/deploy-omen.sh` fast-forwarded OMEN from `6dd2c4f` to `06294e1`, rebuilt the web client, reasserted canonical scheduled tasks, restarted the listeners, and completed successfully. It reported the expected aggregate AI-health label `degraded` while STT/VAD and resident Qwen TTS were ready.
  **implication:** Confirm independent post-deploy service identity/readiness read-only before the final isolated verification; aggregate health alone is not deployment acceptance.
- **timestamp:** 2026-09-01T00:25:00Z
  **checked:** Corrected independent post-deploy OMEN identity and readiness query.
  **found:** OMEN is clean at `06294e157237a2b9b88416a9b6799729341a4890`; both scheduled tasks use the required canonical `.cmd` launchers, and ports 9443/8443 are served by their canonical AI/web commands. Web-to-AI readiness is `ready` and authenticated; STT/VAD and resident `qwen3_1_7b` are ready; WebRTC is `ready`, `live_call_ready=true`, and reports the exact deployed SHA.
  **implication:** The exact correction is active in the healthy normal chat path. It is safe to verify a new isolated record without touching the user's active thread.
- **timestamp:** 2026-09-01T00:26:00Z
  **checked:** Fresh isolated verification thread creation through deployed normal API.
  **found:** The API created `thread_0c54d2e3150a4db599b1134f11695332` using the corrected stdin JSON transport.
  **implication:** Send only the prior observed input in this new thread, then inspect the resulting live stream and persistence records.
- **timestamp:** 2026-09-01T00:27:00Z
  **checked:** Fresh normal `/api/chat/{thread_id}/send` stream for the prior observed input after third-form deployment.
  **found:** The isolated thread streamed 27 token events and one `done` event, with no SSE error, and reported persisted message ID `msg_40ad47ccac7744b09a33d66d015d8b34`.
  **implication:** The route completed normally at deployed `06294e1`; inspect the actual persisted record and alternates before declaring recovery.
- **timestamp:** 2026-09-01T00:28:00Z
  **checked:** Fresh isolated live SQLite rows and linked alternates for `thread_0c54d2e3150a4db599b1134f11695332` in read-only mode.
  **found:** The normal-path assistant sequence 2 is another new generic refusal: `I don't write explicit or erotic content, so I can't fulfill that request. Is there something else I can help you with?` It has no alternate; the only alternate is the initial greeting. The record matches the terminal SSE message ID, so it is not a stale row or alternate-selection artifact.
  **implication:** The third release covered its frozen phrase but not this fourth real provider form. Do not accept the release as a product fix; reproduce this exact detector input before changing code.
- **timestamp:** 2026-09-01T00:29:00Z
  **checked:** Exact newest-live-response guard traces under whole, sentence, and one-codepoint schedules.
  **found:** All three schedules finish non-refused with `reason_code=upstream_complete` and release the full exact response. `I can't fulfill` correctly prevents early release, but neither `explicit or erotic content` nor `something else I can help you with` is recognized as its required secondary cue.
  **implication:** The fourth live escape is deterministic and fragmentation-independent. Compare the two missing cues independently before selecting the minimal repair.
- **timestamp:** 2026-09-01T00:30:00Z
  **checked:** Differential unchanged-guard variants for the fourth live response.
  **found:** The actual text releases. Replacing only `explicit or erotic content` with the already-recognized `explicit erotic content` produces `policy_or_safety`; independently replacing only its redirect with the already-recognized `Instead, I can help with something else` produces `redirect`.
  **implication:** Both missing secondary spellings could correct the response. Expand only the direct coordinated policy spelling because it applies within the first refusal sentence and avoids a broader generic redirect rule.
- **timestamp:** 2026-09-01T00:31:00Z
  **checked:** Frozen fourth-live-response detector corpus and shared-stream regression before implementation.
  **found:** RED as predicted: the exact response releases under all eight fragmentation schedules, and the normal chat stream emits and persists its first sentence instead of retrying (9 failures).
  **implication:** The specified oracle directly reproduces the new live escape and its sentence-boundary risk. The direct coordinated-policy matcher can now be changed as the only variable.
- **timestamp:** 2026-09-01T00:33:00Z
  **checked:** Exact fourth-live-response corpus, shared-stream retry/persistence regression, and nonrefusal coordinated-content boundary neighbor after the policy-grammar change.
  **found:** GREEN: 17 passed. The exact response is classified as `policy_or_safety` in all eight schedules and retries before persistence; the nonrefusal reference remains byte-for-byte unchanged in all eight schedules.
  **implication:** The policy grammar adds the causal missing condition without classifying content references that lack a primary refusal verb. Run all direct consumers and the live-call subset before release approval.
- **timestamp:** 2026-09-01T00:34:00Z
  **checked:** Direct refusal-guard, chat-stream, message-action, and Phase 1 acceptance consumers after the fourth policy-grammar change.
  **found:** GREEN: 317 passed in 8.49 seconds.
  **implication:** The exact correction preserves all directly coupled chat contracts. Verify the shared live-call consumer, then run an isolated code-only counterfactual before release.
- **timestamp:** 2026-09-01T00:35:00Z
  **checked:** Focused live-call refusal retry/exhaustion coverage after the fourth policy-grammar change.
  **found:** GREEN: 3 passed with 106 unrelated call tests deselected.
  **implication:** The shared live-call stream preserves early accepted output, interruption, closure, and rejected-sink exclusion. Inspect the exact incremental scope and prove causality with the policy grammar as the only reverted variable.
- **timestamp:** 2026-09-01T00:36:00Z
  **checked:** Incremental diff scope, whitespace, and mutation-runner configuration.
  **found:** The whitespace-clean diff is limited to the one coordinated policy-grammar alternative, frozen exact/boundary corpus cases, and the shared-stream regression (67 insertions, one deletion across three files). No configured mutation runner (Stryker, mutmut, or equivalent) appears in the project manifests.
  **implication:** Mutation analysis is skipped rather than passed. The additive no-op/deletion signal is covered by the nonrefusal boundary case; isolate the guard file for the remaining reversible causal counterfactual.
- **timestamp:** 2026-09-01T00:37:00Z
  **checked:** Fourth-form target after reverting only `refusal_guard.py` and retaining the new frozen corpus/stream regression.
  **found:** RED returned exactly: all eight fragmentation schedules and the shared stream released/persisted the fourth live refusal (9 failures).
  **implication:** The coordinated policy grammar is causal. Reapply that exact guard diff and require the unchanged target to return GREEN before committing.
- **timestamp:** 2026-09-01T00:38:00Z
  **checked:** Fourth-form target after restoring the isolated policy-grammar implementation.
  **found:** GREEN restored: 17 passed, including all exact-response schedules, shared-stream retry/persistence behavior, and the nonrefusal coordinated-content boundary neighbor. `git diff --check` is clean.
  **implication:** The reversible causal signal passes: the new live defect returns on code-only revert and disappears on reapplication. Prepare a scoped source commit for clean-worktree release verification.
- **timestamp:** 2026-09-01T00:39:00Z
  **checked:** Scoped fourth-form repair commit.
  **found:** Commit `af270cc` contains exactly the coordinated policy grammar, frozen exact/boundary corpus cases, and shared-stream retry/persistence regression. Unrelated primary-workspace debug/runtime files remain untracked and outside the commit.
  **implication:** Verify and publish only `af270cc` from a clean detached worktree; do not deploy from the primary workspace.
- **timestamp:** 2026-09-01T00:40:00Z
  **checked:** Exact-commit fourth-form release worktree.
  **found:** A detached worktree was created at `af270cc2e5dbe76edb92afbc6f336f456f128ac1` with no primary-workspace modifications carried into it.
  **implication:** Its test results and source state will apply to the precise fourth incremental release candidate.
- **timestamp:** 2026-09-01T00:41:00Z
  **checked:** Exact-commit direct guard/chat/action/acceptance suites at detached `af270cc`.
  **found:** GREEN: 317 passed in 8.13 seconds.
  **implication:** The exact release candidate preserves all directly coupled chat contracts. Run focused live-call refusal coverage and source-clean checks before publishing.
- **timestamp:** 2026-09-01T00:42:00Z
  **checked:** Exact-commit focused live-call refusal retry/exhaustion suite and source integrity at detached `af270cc`.
  **found:** GREEN: 3 focused live-call tests passed with 106 unrelated tests deselected. `git diff --check` and `git status --short` are clean; HEAD is exactly `af270cc2e5dbe76edb92afbc6f336f456f128ac1`.
  **implication:** The candidate satisfies the shared live-call recovery contract and is clean for exact publication and canonical OMEN deployment.
- **timestamp:** 2026-09-01T00:43:00Z
  **checked:** Publication of exact detached fourth-form policy-recovery release candidate.
  **found:** The clean detached worktree advanced `origin/main` from `06294e1` to `af270cc`.
  **implication:** OMEN can now fetch the verified correction. Deploy only with the repository's canonical script, which will assert the expected SHA remotely.
- **timestamp:** 2026-09-01T00:47:00Z
  **checked:** Canonical deployment process for the exact detached `af270cc` candidate.
  **found:** `scripts/deploy-omen.sh` fast-forwarded OMEN from `06294e1` to `af270cc`, rebuilt the web client, reasserted canonical scheduled tasks, restarted the listeners, and completed successfully. It reported the expected aggregate AI-health label `degraded` while STT/VAD and resident Qwen TTS were ready.
  **implication:** Confirm independent post-deploy service identity/readiness read-only before the final isolated verification; aggregate health alone is not deployment acceptance.
- **timestamp:** 2026-09-01T00:48:00Z
  **checked:** Corrected independent post-deploy OMEN identity and readiness query.
  **found:** OMEN is clean at `af270cc2e5dbe76edb92afbc6f336f456f128ac1`; both scheduled tasks use the required canonical `.cmd` launchers, and ports 9443/8443 are served by their canonical AI/web commands. Web-to-AI readiness is `ready` and authenticated; STT/VAD and resident `qwen3_1_7b` are ready; WebRTC is `ready`, `live_call_ready=true`, and reports the exact deployed SHA.
  **implication:** The exact correction is active in the healthy normal chat path. It is safe to verify a final new isolated record without touching the user's active thread.
- **timestamp:** 2026-09-01T00:49:00Z
  **checked:** Fresh final isolated verification thread creation through deployed normal API.
  **found:** The API created `thread_887e03991c314735ad73c7871ec8cf41` using the corrected stdin JSON transport.
  **implication:** Send only the prior observed input in this new thread, then inspect the resulting live stream and persistence records.
- **timestamp:** 2026-09-01T00:50:00Z
  **checked:** Fresh normal `/api/chat/{thread_id}/send` stream for the prior observed input after fourth-form deployment.
  **found:** The isolated thread streamed 25 token events and one `done` event, with no SSE error, and reported persisted message ID `msg_eb39c4e687c64c09bf6774573f61a70e`.
  **implication:** The route completed normally at deployed `af270cc`; inspect the actual persisted record and alternates before declaring recovery.
- **timestamp:** 2026-09-01T00:51:00Z
  **checked:** Fresh isolated live SQLite rows and linked alternates for `thread_887e03991c314735ad73c7871ec8cf41` in read-only mode.
  **found:** The normal-path assistant sequence 2 is another generic refusal: `I’m just a warm assistant here to help, not for that kind of content. Let’s keep things friendly and appropriate.` (SSH console rendering of its apostrophes is not yet byte-verified.) It has no alternate; the only alternate is the initial greeting. The record matches the terminal SSE message ID, so it is not a stale row or alternate-selection artifact.
  **implication:** This form does not depend on `I can't`/`cannot`; it tests the remaining identity-disclaimer branch. Verify raw bytes and deterministic guard behavior before choosing a broader architectural correction.
- **timestamp:** 2026-09-01T00:52:00Z
  **checked:** Raw SQLite bytes and exact guard traces for the newest identity-disclaimer response.
  **found:** SQLite stores valid U+2019 apostrophes (not replacement characters). Whole, sentence, and one-codepoint traces all hold the exact response then release it at `finish()` as `upstream_complete`: `_secondary_reason()` finds `assistant`, but `_refusal_reason()` does not classify secondary identity cues without a primary refusal verb.
  **implication:** The remaining mechanism is a direct identity-disclaimer class, not encoding, route, alternate, or token-fragmentation behavior. Add a specified regression before a narrow direct-classifier addition.
- **timestamp:** 2026-09-01T00:54:00Z
  **checked:** Frozen fifth-live-response detector corpus and shared-stream regression before implementation.
  **found:** RED as predicted: the exact response releases under all eight fragmentation schedules, and the normal chat stream emits and persists the first identity-disclaimer sentence instead of retrying (9 failures).
  **implication:** The specified oracle directly reproduces the fifth live escape and its sentence-boundary risk. The sentence-leading direct identity-disclaimer matcher can now be changed as the only variable.
- **timestamp:** 2026-09-01T00:56:00Z
  **checked:** Exact fifth-live-response corpus, shared-stream retry/persistence regression, and quoted-opening boundary neighbor after the direct identity-disclaimer matcher change.
  **found:** GREEN: 17 passed. The exact response is classified as `generic_identity` in all eight schedules and retries before persistence; the quoted opening remains byte-for-byte unchanged in all eight schedules.
  **implication:** The direct matcher adds the causal missing identity-disclaimer class without classifying the nearby quoted in-character reference. Run all direct consumers and the live-call subset before release approval.
- **timestamp:** 2026-09-01T00:57:00Z
  **checked:** Direct refusal-guard, chat-stream, message-action, and Phase 1 acceptance consumers after the fifth direct-identity matcher change.
  **found:** GREEN: 334 passed in 8.59 seconds.
  **implication:** The exact correction preserves all directly coupled chat contracts. Verify the shared live-call consumer, then run an isolated code-only counterfactual before release.
- **timestamp:** 2026-09-01T00:58:00Z
  **checked:** Focused live-call refusal retry/exhaustion coverage after the fifth direct-identity matcher change.
  **found:** GREEN: 3 passed with 106 unrelated call tests deselected.
  **implication:** The shared live-call stream preserves early accepted output, interruption, closure, and rejected-sink exclusion. Inspect the exact incremental scope and prove causality with the identity matcher as the only reverted variable.
- **timestamp:** 2026-09-01T00:59:00Z
  **checked:** Incremental diff scope, whitespace, and mutation-runner configuration.
  **found:** The whitespace-clean diff is limited to the sentence-leading identity matcher, frozen exact/boundary corpus cases, and the shared-stream regression (73 insertions across three files). No configured mutation runner (Stryker, mutmut, or equivalent) appears in the project manifests.
  **implication:** Mutation analysis is skipped rather than passed. The additive no-op/deletion signal is covered by the quoted-opening boundary case; isolate the guard file for the remaining reversible causal counterfactual.
- **timestamp:** 2026-09-01T01:00:00Z
  **checked:** Fifth-form target after reverting only `refusal_guard.py` and retaining the new frozen corpus/stream regression.
  **found:** RED returned exactly: all eight fragmentation schedules and the shared stream released/persisted the fifth live refusal (9 failures).
  **implication:** The direct identity matcher is causal. Reapply that exact guard diff and require the unchanged target to return GREEN before committing.
- **timestamp:** 2026-09-01T01:01:00Z
  **checked:** Fifth-form target after restoring the isolated direct-identity implementation.
  **found:** GREEN restored: 17 passed, including all exact-response schedules, shared-stream retry/persistence behavior, and the quoted-opening boundary neighbor. `git diff --check` is clean.
  **implication:** The reversible causal signal passes: the new live defect returns on code-only revert and disappears on reapplication. Prepare a scoped source commit for clean-worktree release verification.
- **timestamp:** 2026-09-01T01:02:00Z
  **checked:** Scoped fifth-form repair commit.
  **found:** Commit `9d9fb59` contains exactly the sentence-leading identity matcher, frozen exact/boundary corpus cases, and shared-stream retry/persistence regression. Unrelated primary-workspace debug/runtime files remain untracked and outside the commit.
  **implication:** Verify and publish only `9d9fb59` from a clean detached worktree; do not deploy from the primary workspace.
- **timestamp:** 2026-09-01T01:03:00Z
  **checked:** Exact-commit fifth-form release worktree.
  **found:** A detached worktree was created at `9d9fb59deb2041e4e6baf750eef4a77e56030f63` with no primary-workspace modifications carried into it.
  **implication:** Its test results and source state will apply to the precise fifth incremental release candidate.
- **timestamp:** 2026-09-01T01:04:00Z
  **checked:** Exact-commit direct guard/chat/action/acceptance suites at detached `9d9fb59`.
  **found:** GREEN: 334 passed in 8.15 seconds.
  **implication:** The exact release candidate preserves all directly coupled chat contracts. Run focused live-call refusal coverage and source-clean checks before publishing.
- **timestamp:** 2026-09-01T01:05:00Z
  **checked:** Exact-commit focused live-call refusal retry/exhaustion suite and source integrity at detached `9d9fb59`.
  **found:** GREEN: 3 focused live-call tests passed with 106 unrelated tests deselected. `git diff --check` and `git status --short` are clean; HEAD is exactly `9d9fb59deb2041e4e6baf750eef4a77e56030f63`.
  **implication:** The candidate satisfies the shared live-call recovery contract and is clean for exact publication and canonical OMEN deployment.
- **timestamp:** 2026-09-01T01:06:00Z
  **checked:** Publication of exact detached fifth-form identity-recovery release candidate.
  **found:** The clean detached worktree advanced `origin/main` from `af270cc` to `9d9fb59`.
  **implication:** OMEN can now fetch the verified correction. Deploy only with the repository's canonical script, which will assert the expected SHA remotely.
- **timestamp:** 2026-09-01T01:10:00Z
  **checked:** Canonical deployment process for the exact detached `9d9fb59` candidate.
  **found:** `scripts/deploy-omen.sh` fast-forwarded OMEN from `af270cc` to `9d9fb59`, rebuilt the web client, reasserted canonical scheduled tasks, restarted the listeners, and completed successfully. It reported the expected aggregate AI-health label `degraded` while STT/VAD and resident Qwen TTS were ready.
  **implication:** Confirm independent post-deploy service identity/readiness read-only before the final isolated verification; aggregate health alone is not deployment acceptance.
- **timestamp:** 2026-09-01T01:11:00Z
  **checked:** Corrected independent post-deploy OMEN identity and readiness query.
  **found:** OMEN is clean at `9d9fb59deb2041e4e6baf750eef4a77e56030f63`; both scheduled tasks use required canonical `.cmd` launchers. Web-to-AI readiness is authenticated and ready; STT/VAD, resident `qwen3_1_7b`, and WebRTC live-call readiness are all ready and report the exact deployed SHA.
  **implication:** The exact correction is active in the healthy normal chat path. It is safe to run the final isolated record verification.
- **timestamp:** 2026-09-01T01:12:00Z
  **checked:** Final fresh normal `/api/chat/{thread_id}/send` stream for the prior observed input after fifth-form deployment.
  **found:** The isolated thread streamed 21 token events and one `done` event, with no SSE error, and reported persisted message ID `msg_baa0cf5aa0cf459e9f1cdba774e884fc`.
  **implication:** The route completed normally at deployed `9d9fb59`; inspect the actual persisted record before declaring recovery.
- **timestamp:** 2026-09-01T01:13:00Z
  **checked:** Final fresh isolated live SQLite rows and linked alternates for `thread_00047d591e5d4a159d099d2bc870b74e` in read-only mode.
  **found:** The normal-path assistant sequence 2 is another generic identity disclaimer: `I am strictly programmed to be a helpful assistant, not an erotic one. Please ask me something else.` It has no alternate; the only alternate is the initial greeting. The record matches the terminal SSE message ID, so it is not stale or alternate-selected.
  **implication:** The fifth repair correctly addressed its exact sentence but exposes a structural identity-disclaimer gap. Replace its surface-specific form with a bounded first-person-assistant-plus-content-negation classifier rather than add another exact literal.
- **timestamp:** 2026-09-01T01:14:00Z
  **checked:** Exact newest-identity-disclaimer guard traces under whole, sentence, and one-codepoint schedules.
  **found:** All three schedules finish non-refused with `reason_code=upstream_complete` and release the full exact response.
  **implication:** The sixth live escape is deterministic and fragmentation-independent. Add its frozen regression before changing the direct identity-disclaimer classifier.
- **timestamp:** 2026-09-01T01:15:00Z
  **checked:** Frozen sixth-live-response detector corpus and shared-stream regression before the structural matcher change.
  **found:** RED as predicted: all eight fragmentation schedules and the shared stream released/persisted the new identity disclaimer (9 failures).
  **implication:** The exact current production form is now a specified regression. Replace the surface-specific identity matcher with the bounded structural identity-and-content-negation form.
- **timestamp:** 2026-09-01T01:16:00Z
  **checked:** Both observed identity-disclaimer forms, their shared-stream regressions, and the quoted-opening boundary neighbor after the structural matcher change.
  **found:** GREEN: 26 passed. Both direct forms classify as `generic_identity`; the quoted reference remains byte-for-byte unchanged.
  **implication:** The structural matcher fixes the sixth real form without losing coverage for the fifth. Run full direct consumers, then perform the remaining commit/deploy/live-record guardrail steps.

- **timestamp:** 2026-09-01T00:30:30Z
  **checked:** Direct refusal-guard, chat-stream, message-action, and Phase 1 acceptance consumers after the structural identity matcher change.
  **found:** GREEN: `uv run --project web-ui/server pytest web-ui/server/tests/test_refusal_guard.py web-ui/server/tests/test_chat_stream.py web-ui/server/tests/test_message_actions.py web-ui/server/tests/test_phase1_acceptance.py -q` passed 343 tests in 9.00 seconds.
  **implication:** The structural matcher preserves all directly coupled chat contracts. Run the focused live-call refusal consumer before the scoped counterfactual and release commit.

- **timestamp:** 2026-09-01T00:31:10Z
  **checked:** Focused live-call refusal retry/exhaustion coverage after the structural identity matcher change.
  **found:** GREEN: `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q -k 'refusal_retry or refusal_exhaustion'` passed 3 tests with 106 deselected in 3.16 seconds.
  **implication:** The shared live-call stream retains early accepted caption/speech, explicit interruption, closure, and rejected-attempt sink exclusion. Re-run the exact structural target and boundary neighbor before recording guardrail acceptance.

- **timestamp:** 2026-09-01T00:31:40Z
  **checked:** Exact structural identity corpus cases, quoted-opening boundary neighbor, and both shared-stream retry/persistence regressions after the direct consumer suites.
  **found:** GREEN: 26 passed, 284 deselected in 0.17 seconds. Both observed identity-disclaimer forms retry as `generic_identity` before token emission/persistence; the quoted opening remains byte-for-byte unchanged.
  **implication:** The specified target oracle and its boundary neighbor pass on the candidate. Inspect the incremental diff and static quality before a scoped commit.

- **timestamp:** 2026-09-01T00:32:10Z
  **checked:** Incremental diff scope, whitespace, static quality, mutation-runner availability, and prior reversible causal counterfactual.
  **found:** `git diff --check` and scoped Ruff are GREEN. The diff replaces only the surface-specific identity pattern with a bounded structural one (3 changed lines), adds one exact corpus entry, and adds its stream regression (32 insertions, 3 deletions across three files); it contains no behavior-deleting early return, blanket suppression, or weakened assertion. No configured mutation runner exists. With only `refusal_guard.py` reverted, the unchanged sixth-form corpus and stream targets were RED (9 failures); reapplying the matcher restored GREEN (17 passed).
  **implication:** Fix-acceptance signals are accepted: target test PASS, mutation check SKIPPED (no runner), no-op/deletion PASS, adjacent consumers PASS, and revert-and-reconfirm PASS. Stage only the scoped repair plus this debug record.

## Eliminated

- **hypothesis:** Sequence 20 was a stale selected alternate or a different message action/path that persisted after correct guard recovery.
  **evidence:** The only alternate belongs to sequence 18, is a non-refusal swipe result, and sequence 20 is a new plain `ai_text` immediately after user sequence 19. `append_ai_message` is called only by the ordinary `/api/chat/{thread_id}/send` route, which is also present in the retained OMEN log.
  **timestamp:** 2026-08-31T23:11:00Z
- **hypothesis:** Sequence 20 was written by a stale or SHA-mismatched active OMEN web worker.
  **evidence:** The current listener predates the failure, launches through the canonical task/launcher, and OMEN's clean repository is exactly `28a19f9` with the deployed guard blob.
  **timestamp:** 2026-08-31T23:11:00Z
- **hypothesis:** The Qwen adapter/template bypassed the shared refusal guard for the post-swipe follow-up.
  **evidence:** A standard (non-custom) Qwen-compatible request with the observed ordering passed its generated chunks through `_stream_text_tokens()` and returned the exact refusal unchanged; the adapter generates input but cannot bypass `PrefixRefusalGuard`.
  **timestamp:** 2026-08-31T23:12:00Z

## Resolution

- **root_cause:** `_comparison_view()` originally left U+2019 apostrophes unmatched by the ASCII-only `can't` refusal-verb alternative; secondary generic-refusal patterns also omitted four provider-produced verb-led cues (direct explicit-content, `I’m here to help`, `erotic content ... I’m here if you want to chat about anything else`, and coordinated `explicit [sexual] or erotic content`). The direct no-verb identity-disclaimer branch then overfit its first live example: it recognized only `I’m just/only ... not for that/this kind of content`, so the later structural `I am ... assistant, not an erotic one` form escaped and persisted through the normal shared stream.
- **oracle_type:** specified — the chat contract requires generic policy/guideline refusals to retry before any token reaches chat persistence.
- **fix:** Preserve the deployed punctuation, policy, and redirect corrections; replace the surface-specific direct identity matcher with a bounded sentence-leading first-person assistant plus content-negation matcher covering both `not for that/this kind of content` and `not an erotic/sexual one`. The frozen corpus and shared-stream regression now cover six real OMEN forms and close nonrefusal/in-character neighbors.
- **verification:**
  target_test: { result: pass, suites_run: ["structural corpus + shared-stream targets (26 passed, 284 deselected)"] }
  mutation_check: { result: skipped, reason_if_skipped: "no Stryker, mutmut, or equivalent mutation runner is configured" }
  no_op_deletion: { result: pass, deletion_justified_by_rca: true }
  adjacent_tests: { result: pass, suites_run: ["guard/chat/action/Phase 1 acceptance (343 passed)", "focused live-call refusal subset (3 passed, 106 deselected)", "scoped Ruff"] }
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true }
  guardrail_verdict: accepted
- **files_changed:** [web-ui/server/app/domain/refusal_guard.py, web-ui/server/tests/fixtures/phase091_refusal_corpus.json, web-ui/server/tests/test_chat_stream.py]
