---
status: verifying
trigger: "User reported that the deployed refusal-recovery check failed and directed the agent to inspect the last chat as the evidence."
created: 2026-08-31
updated: 2026-08-31T03:05:00Z
---

# Last Chat Refusal Recovery

## Symptoms

- **Expected behavior:** A prompt that previously produced generic policy/guideline refusal language recovers into an in-character response without the rejected response appearing in chat.
- **Actual behavior:** The deployed user-visible check failed. The latest chat is the primary evidence.
- **Error messages:** Inspect the latest chat and linked server/runtime records; do not require the user to copy or interpret technical messages.
- **Timeline:** Observed immediately after the Phase 09.1 deployment acceptance check.
- **Reproduction:** Inspect the most recent deployed chat turn, identify the exact observed outcome, and reproduce through the same product path where safe.

## Current Focus

- **bug_class:** bohrbug (provisional)
- **fault_tree:** OR: (code) a generic policy/meta response reaches `finish()` without the narrowly matched refusal verb; (code) the `fa861cd` retry correction is serialized but ineffective for the provider; (config/environment) deployed adapter/template differs from the recorded preflight; (data) alternate/stale state presents a rejected response after recovery.
- **hypothesis:** Confirmed — a generic guideline/policy response without one of `_REFUSAL_VERB_RE`'s exact refusal forms remains held but is classified safe by `finish()`, so its full text becomes emitted and persisted instead of triggering recovery.
- **test:** Create an exact, scoped release commit; rerun guard/chat/direct-consumer refusal tests from a clean release worktree; push it; then run only the canonical OMEN deployment script and collect its commit-matched health outcome.
- **expecting:** The exact commit is clean, all guard/chat/adjacent refusal tests pass, OMEN reports the same commit and healthy canonical services, and only then the formerly generic/guideline response can be checked through the real product workflow.
- **next_action:** Commit the four staged repair artifacts, then create a clean detached release worktree at the resulting commit before rerunning the required guard/chat/adjacent refusal suites.
- **reasoning_checkpoint:**
  hypothesis: "A generic declarative policy/guideline refusal escapes because finish() requires _REFUSAL_VERB_RE even after the prefix has been held for a policy cue, so the shared token stream releases and persists it."
  confirming_evidence:
    - "The direct guard experiment rejected the frozen explicit refusal with zero characters but released all 41 characters of the declarative policy/guideline response at finish."
    - "stream_chat_completion persists exactly the emitted shared-token stream, and the send endpoint writes one assistant message only after that stream completes."
    - "The Phase 09.1 contract forbids generic guideline/policy text from being displayed or persisted, while the frozen corpus excludes this declarative form."
  falsification_test: "A focused shared-stream test would emit no first-attempt text, close the first attempt, issue a retry, and persist only the accepted retry without a detector change."
  fix_rationale: "Recognize narrowly scoped declarative meta-policy refusals before finish so the existing shared retry path owns closure, retry, sink exclusion, and final persistence."
  blind_spots: "The deployed chat database and restart-lost activity ring are not available locally, so the exact reported wording and live provider reaction cannot be compared byte-for-byte."
  candidate_causes:
    - "code: finish() only classifies policy/identity text as a refusal when an exact refusal verb is also present."
    - "config/environment: a provider/template mismatch could make the retry correction ineffective, but the deployment receipt records matching SHA, Qwen adapter evidence, and preflight."
    - "data: a stale/selected alternate could expose an old refusal, but the streaming send path appends a new message and has no alternate selection."
  and_gate: "no — an unrecognized generic policy response is normal model-output input; the guard's missed classification alone violates the product contract without an additional config or persistence fault."
- **tdd_checkpoint:**

## Evidence

- **timestamp:** 2026-08-31T00:00:00Z
  **checked:** Session instructions and mandatory live-call invariants
  **found:** This is a Phase 09.1 deployed user-visible refusal-recovery regression; the repository requires GSD verification and a persisted debug session. No live-call, TTS, STT, VAD, WebRTC, reconnect, or deployment behavior is in scope unless later evidence directly requires it.
  **implication:** Investigate the saved chat and chat-generation path first, keep any fix scoped, and do not create or use an ad-hoc deployment path.
- **timestamp:** 2026-08-31T00:05:00Z
  **checked:** Project-specific skills and configured `gsd-debugger` skills
  **found:** No project-local skill files and no debugger-specific configured skills are present.
  **implication:** Apply the repository instructions and standard GSD debugger rules directly; there are no additional project skill rules to load.
- **timestamp:** 2026-08-31T00:10:00Z
  **checked:** Required debugging methodology and verification references
  **found:** The investigation must use a falsifiable, category-branched hypothesis; the issue is expected to be a deterministic Bohrbug unless the saved chat shows otherwise. Any code change must have an agent-authored, specified-oracle regression and pass the multi-signal acceptance guardrail.
  **implication:** Gather persisted evidence before forming or changing a hypothesis, and record any unavailable guardrail signal rather than treating it as passed.
- **timestamp:** 2026-08-31T00:15:00Z
  **checked:** MemPalace semantic recall and the durable debug knowledge base
  **found:** MemPalace is not available on this host. The durable knowledge base has no entry with two or more matching symptom tokens for generic/guideline refusal text becoming visible after recovery.
  **implication:** No known-pattern diagnosis applies; use the latest persisted chat and its request lifecycle as the primary evidence.
- **timestamp:** 2026-08-31T00:20:00Z
  **checked:** Repository history, working-tree state, persistence configuration, and candidate runtime evidence locations
  **found:** The reported release maps to commit `fa861cd` (Phase 09.1 bounded roleplay recovery). OMEN is configured to use `C:/Users/pmpg/rayme/RayMe/web-ui/server/data/rayme.sqlite3`. The current worktree has unrelated untracked GSD/debug state that must be preserved; local rollout chat logs are from May and are not the reported latest deployed chat.
  **implication:** Do not modify or rely on stale local rollout logs. Inspect only the mounted OMEN database/runtime records and later scope any patch to the refusal-recovery path.
- **timestamp:** 2026-08-31T00:25:00Z
  **checked:** Configured persistence path and available runtime evidence
  **found:** The active workspace database exists at `web-ui/server/data/rayme.sqlite3` and was modified on the reported date. The configured Windows OMEN path is not mounted separately, so this database is the only current persisted chat source available here. Historical debug logs contain the generic refusal phenotype but predate the release and are not used as acceptance evidence.
  **implication:** The latest saved chat can be inspected directly via the workspace database; no live-service mutation is necessary to establish the failure.
- **timestamp:** 2026-08-31T00:30:00Z
  **checked:** Persisted message schema and the initial recovery-path source trace
  **found:** Assistant responses are persisted both as `messages.content_text` and as selected `message_alternates` rows. The API returns the selected alternate's content, so any rejected first attempt visible in the current chat must either have been released by the guard or saved by a post-guard persistence path. Historical debug logs show prior generic policy/guideline refusals but do not identify this post-release regression.
  **implication:** Classify both the assistant message and every alternate in the latest turn, then trace the guard's release and recovery decisions rather than assuming that persistence alone is at fault.
- **timestamp:** 2026-08-31T00:35:00Z
  **checked:** Refusal guard, process-local refusal activity schema, and the stream's initial retry path
  **found:** The stream holds tokens until the prefix guard either finds an explicit refusal or releases a safe sentence. A refusal triggers a new bounded attempt rather than persistence. Detection currently requires a refusal verb plus a secondary generic cue (identity, policy/safety, apology, redirect, or warning); recovery activity is process-local metadata and is lost on a web-process restart.
  **implication:** The current database can prove the visible/persisted outcome but cannot prove prior attempt history after restart. The decisive test is whether the latest response contains a generic refusal wording that the current two-part detector does not recognize before its safe-prefix release.
- **timestamp:** 2026-08-31T00:40:00Z
  **checked:** Complete stream and chat API persistence path
  **found:** `stream_chat_completion` persists only text yielded by `_stream_text_tokens`; rejected attempts yield nothing and must retry. The send endpoint appends one assistant message only after the stream completes. Therefore a persisted refusal means the guard classified it as safe, not a client-side alternate-selection artifact.
  **implication:** A metadata-only inspection of the latest persisted assistant response is a direct discrimination test for the guard-detection hypothesis.
- **timestamp:** 2026-08-31T00:40:00Z
  **checked:** Initial metadata-only database classifier invocation
  **found:** The first read-only script did not execute because its inline Python function syntax was invalid; it made no database changes and emitted no chat contents.
  **implication:** Re-run the same read-only classification with valid syntax; this attempt neither supports nor refutes any code hypothesis.
- **timestamp:** 2026-08-31T00:45:00Z
  **checked:** Corrected read-only classifier execution
  **found:** The workspace's global Python does not include FastAPI, so importing the package-level application failed before any database query or content output. No database changes occurred.
  **implication:** Load only the dependency-free refusal-guard source module for the next read-only classification; the data query remains valid.
- **timestamp:** 2026-08-31T00:50:00Z
  **checked:** Read-only classifier over the configured workspace database's most-recent active thread
  **found:** The guard module loaded correctly without application dependencies, but the database contains no non-deleted thread, so there is no active latest chat to classify in that file.
  **implication:** The configured repository database cannot yet be treated as the reported deployed chat evidence. Check for soft-deleted records and runtime path divergence before changing any detector logic.
- **timestamp:** 2026-08-31T00:55:00Z
  **checked:** Database inventory, local runtime, and configured persistence locations
  **found:** `rayme.sqlite3` has zero threads, messages, alternates, and call turns; there are no active local RayMe web/backend processes and no alternate database in the workspace. The checked-out database is therefore an empty local runtime store, not the deployed acceptance store.
  **implication:** Direct persisted-chat classification is unavailable in this workspace. Continue with differential debugging against the exact Phase 09.1 release and its intended fixed corpus; do not invent a result from historical logs.
- **timestamp:** 2026-08-31T00:55:00Z
  **checked:** SBFL eligibility
  **found:** No runnable failing regression test or per-test failure coverage exists yet for this externally observed deployment regression.
  **implication:** SBFL is skipped; use deterministic differential debugging, a minimal reproduction, and the release diff instead.
- **timestamp:** 2026-08-31T01:00:00Z
  **checked:** Phase 09.1 deployment receipt, fixed refusal corpus, and deployed-commit scope
  **found:** OMEN deployed `fa861cd` and automated gates passed, but blocking human verification remained pending. The deployed commit changed only retry-correction generation/profile tests and one live-call test; it did not modify the guard, stream, or persistence code. The frozen corpus covers ten known explicit forms but not all generic/guideline phrasings.
  **implication:** The first code hypothesis is that the changed retry correction produces an ineffective request for the reported first-attempt refusal. Independently, the guard's finite corpus/regex coverage remains a candidate if that hypothesis is eliminated.
- **timestamp:** 2026-08-31T01:05:00Z
  **checked:** Retry-correction implementation and deployed change against the Phase 09.1 intent
  **found:** The deployed commit replaced the frozen correction with a longer fictional-scene variant and updated only serialization/string tests. The Qwen adapter delivers it as a late user instruction. More importantly, `_should_release()` suppresses early release when it sees policy/identity language, but `finish()` refuses only when that same text also matches the fixed refusal-verb regex; otherwise it releases the held text unchanged.
  **implication:** A generic declarative guideline response without a recognized refusal verb has a concrete path to user-visible persistence. Test this exact guard transition before considering a fix; the changed retry correction remains a separate candidate until its provider behavior is tested or excluded.
- **timestamp:** 2026-08-31T01:15:00Z
  **checked:** Complete shared-stream regression suite
  **found:** Existing tests prove explicit-verb refusals retry without reaching SSE or persistence, but none exercise a declarative policy/guideline response without a matched refusal verb. The test seam already captures emitted SSE, request closure, retry inputs, and persisted text.
  **implication:** One focused stream-level regression can reproduce the exact visible failure class and give a specified oracle for both sink exclusion and recovery behavior.
- **timestamp:** 2026-08-31T01:25:00Z
  **checked:** Focused shared-stream user-visible regression before the fix
  **found:** RED as predicted: the first token event contains the declarative guideline response rather than the safe retry response. The guard therefore did not trigger retry, and the existing stream would persist that first response at completion.
  **implication:** The guard escape mechanism is confirmed end-to-end through the same shared streaming and persistence path used by chat. A narrow detector extension is warranted.
- **timestamp:** 2026-08-31T01:35:00Z
  **checked:** Focused shared-stream regression after the detector change
  **found:** GREEN: 1 passed. The stream now closes the rejected declarative guideline attempt, sends the existing retry correction, emits only the accepted retry, and persists only that response.
  **implication:** The code change directly corrects the reproduced user-visible failure. Run the complete positive/benign corpus and adjacent consumers to check precision and regressions.
- **timestamp:** 2026-08-31T01:40:00Z
  **checked:** Adjacent-test and mutation-check discovery
  **found:** Five test modules directly import the changed guard/shared-stream path: refusal guard, chat stream, calls, message actions, and Phase 1 acceptance. No Stryker or other mutation-test configuration exists in the server project.
  **implication:** Run all five direct consumers as the adjacent-test signal. The mutation guardrail is unavailable and will be recorded as skipped rather than passed.
- **timestamp:** 2026-08-31T01:45:00Z
  **checked:** Initial combined adjacent-test command
  **found:** The combined process completed after the tool's streaming window, but its final exit status was not returned through that window. Partial output showed continuous passing progress through 61%, which is not sufficient to accept the suite.
  **implication:** Collect each module's explicit final status before accepting the adjacent-test guardrail signal.
- **timestamp:** 2026-08-31T01:50:00Z
  **checked:** Individually bounded adjacent test modules
  **found:** `test_refusal_guard.py` passed 188 tests, `test_chat_stream.py` passed 19, `test_message_actions.py` passed 32, and `test_phase1_acceptance.py` passed 1. The full 112-test call module reached 66% with no failure but exceeded its 60-second bound.
  **implication:** The completed consumers are green. Do not treat the timed-out full call module as green; run only its refusal-specific tests, which exercise the changed shared stream without unrelated long-running call coverage.
- **timestamp:** 2026-08-31T01:55:00Z
  **checked:** Refusal-specific call test discovery
  **found:** The direct call consumers are `test_refusal_retry_releases_caption_and_speech_before_llm_and_tts_complete`, `test_interrupt_during_refusal_retry_closes_attempt_and_rejects_late_output`, and `test_refusal_exhaustion_closes_each_attempt_without_caption_speech_or_persistence`.
  **implication:** These three tests are the precise held-out live-call coverage for the shared stream change and can complete within the required bounded runtime.
- **timestamp:** 2026-08-31T02:00:00Z
  **checked:** Refusal-specific live-call regression subset
  **found:** All three direct shared-stream call tests passed (3 passed, 106 deselected), preserving early caption/speech, interruption, closure, and rejected-sink exclusion.
  **implication:** Adjacent chat and live-call consumers remain correct under the fixed stream behavior. Proceed to the no-op and counterfactual acceptance signals.
- **timestamp:** 2026-08-31T02:05:00Z
  **checked:** Scoped diff and whitespace validation
  **found:** The fix is additive and narrowly scoped: it adds one explicit declarative meta-policy matcher, one corpus case, and one stream-level regression. `git diff --check` is clean; no behavior is deleted or short-circuited.
  **implication:** The no-op/deletion acceptance signal passes. Run the reversible counterfactual with only the implementation files removed, keeping the regression active as the oracle.
- **timestamp:** 2026-08-31T02:10:00Z
  **checked:** Revert-and-reconfirm counterfactual
  **found:** Stashing only the detector/corpus files restored the focused regression to RED with the generic first-attempt token. Restoring that exact stash returned the same test to GREEN. The test file and unrelated untracked work remained intact.
  **implication:** The implementation change, not an unrelated environment change, is the cause of the corrected behavior. Re-run the compact core suites once on the final re-applied worktree before accepting the fix.
- **timestamp:** 2026-08-31T02:15:00Z
  **checked:** Final post-reapply core suites
  **found:** The full refusal corpus passed (188 tests) and the full chat-stream suite passed (19 tests) on the restored worktree.
  **implication:** The positive/benign detector contract and the user-visible shared-stream persistence path are both green after the causal counterfactual.
- **timestamp:** 2026-08-31T02:20:00Z
  **checked:** Final scoped diff and worktree validation
  **found:** Whitespace validation is clean and the final code diff contains only the refusal detector, its frozen corpus entry, and its shared-stream user-visible regression. Unrelated untracked GSD/debug state remains untouched.
  **implication:** The fix-acceptance guardrail is accepted. The remaining validation is a real deployed chat check that cannot be observed from this empty local runtime store.
- **timestamp:** 2026-08-31T03:00:00Z
  **checked:** Release and deployment readiness after orchestration correction
  **found:** The scoped fix is present only as local changes; it has not yet been committed, pushed, or deployed. The workspace also contains unrelated modified and untracked runtime/planning state. `scripts/deploy-omen.sh` derives its expected SHA from the checked-out local commit, asserts the matching remote checkout, recreates only its canonical launchers/tasks, and verifies both health endpoints plus the AI/WebRTC deployed commit identity.
  **implication:** The earlier human-verification checkpoint was premature. Commit only the four scoped artifacts, test from a clean detached worktree at that commit, then use `scripts/deploy-omen.sh` from that worktree as the sole deployment route.
- **timestamp:** 2026-08-31T03:05:00Z
  **checked:** Staged release scope
  **found:** The staged index contains exactly four artifacts: the guard implementation, frozen corpus, shared-stream regression, and this debug-session record. The staged diff is whitespace-clean; all other modified and untracked workspace state remains unstaged.
  **implication:** The incident repair can be committed without incorporating unrelated user or runtime changes.

## Eliminated

- hypothesis: A stale or selected alternate displays a rejected first attempt after a correct recovery.
  evidence: The send path appends one assistant message from emitted shared-stream text only and does not select/restore alternates; the focused regression demonstrates the rejected text is emitted before any persistence or alternate projection.
  timestamp: 2026-08-31T01:25:00Z

## Resolution

- **root_cause:** `PrefixRefusalGuard.finish()` releases a held generic declarative policy/guideline response whenever it lacks one narrowly enumerated refusal verb, allowing the shared stream to emit and persist the response instead of entering bounded recovery.
- **oracle_type:** specified — D-04/D-17 require generic policy/guideline refusals to trigger recovery before display or persistence.
- **fix:** Added a narrow matcher for sentence-leading declarative meta-policy statements (for example, a response that says a roleplay or request violates guidelines) so `finish()` classifies them as `policy_or_safety` and routes them through the existing bounded retry path. Added the exact regression case to the frozen guard corpus.
- **verification:**
  target_test: { result: pass, test: "test_declarative_guideline_refusal_retries_without_reaching_chat_or_persistence" }
  mutation_check: { result: skipped, reason_if_skipped: "No Stryker or other mutation-test configuration exists in the server project." }
  no_op_deletion: { result: pass, deletion_justified_by_rca: true, evidence: "Additive matcher, corpus case, and regression only; git diff --check clean." }
  adjacent_tests: { result: pass, suites_run: ["test_refusal_guard.py (188 passed)", "test_chat_stream.py (19 passed)", "test_message_actions.py (32 passed)", "test_phase1_acceptance.py (1 passed)", "test_calls.py -k refusal_retry or refusal_exhaustion (3 passed)"] }
  adjacent_suite_note: "The unrelated full call suite was bounded at 60 seconds and reached 66% without failure; its three direct refusal-stream tests passed separately."
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true }
  guardrail_verdict: accepted
- **files_changed:** [web-ui/server/app/domain/refusal_guard.py, web-ui/server/tests/fixtures/phase091_refusal_corpus.json, web-ui/server/tests/test_chat_stream.py]
