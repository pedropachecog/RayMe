---
status: verifying
trigger: "User reported that the deployed refusal-recovery check failed and directed the agent to inspect the last chat as the evidence."
created: 2026-08-31
updated: 2026-08-31T16:31:00Z
---

# Last Chat Refusal Recovery

## Symptoms

- **Expected behavior:** A prompt that previously produced generic policy/guideline refusal language recovers into an in-character response without the rejected response appearing in chat.
- **Actual behavior:** The deployed user-visible check failed. The latest chat is the primary evidence.
- **Error messages:** Inspect the latest chat and linked server/runtime records; do not require the user to copy or interpret technical messages.
- **Timeline:** Observed immediately after the Phase 09.1 deployment acceptance check.
- **Reproduction:** Inspect the most recent deployed chat turn, identify the exact observed outcome, and reproduce through the same product path where safe.

## Current Focus

- **bug_class:** bohrbug — the same persisted text and a candidate two-chunk boundary yield a deterministic guard transition.
- **fault_tree:** OR: (environment/deployment) OMEN is executing a SHA or web process other than `138104c`; (code) the actual chat route bypasses `_stream_text_tokens` or the retry guard; (config) the request/provider template bypasses or defeats recovery; (data/state) the persisted row comes from a path after guard recovery or a stale service process.
- **hypothesis:** Confirmed and fixed — a recognized explicit-refusal verb now blocks early safe-sentence release until the guard can see the later generic cue or the upstream completion safely establishes a non-generic neighbor.
- **test:** The exact production-form corpus/sentence-boundary shared-stream regression is GREEN. Run the complete guard and chat suites, direct message-action and acceptance consumers, live-call refusal subset, diff checks, then causal revert/reapply.
- **expecting:** All positive, benign, chat persistence, action, and live-call consumers pass; reverting the single release condition restores the production-form failure while reapplying it restores recovery.
- **next_action:** Stage only the guard, corpus, shared-stream regression, and this session record; commit the scoped repair, then verify/deploy the exact commit from a clean detached worktree.
- **reasoning_checkpoint:**
  hypothesis: "A sentence-boundary chunk containing a recognized refusal verb but not yet a generic cue enters passthrough because `_should_release()` checks only `_secondary_reason`; later identity/policy text cannot be evaluated because passthrough is irreversible."
  confirming_evidence:
    - "The exact active-OMEN response is a normal `/api/chat/{thread_id}/send` `ai_text` row with no alternate projection."
    - "The exact two-chunk production form released its first sentence as `safe_prefix`, then released the generic identity/policy continuation and finished without refusal."
    - "OMEN is clean at `138104c` with the same `refusal_guard.py` blob as the locally reproduced implementation."
  falsification_test: "With the first sentence and generic continuation supplied as separate chunks, the unfixed guard would hold the first chunk or mark either feed/finish refused; it instead released both, while the corrected condition must suppress every first-attempt token and retry."
  fix_rationale: "Prevent early safe-prefix release whenever the bounded prefix already contains a recognized explicit-refusal verb; this preserves the existing secondary-cue precision decision at `finish()` while allowing the next chunk to provide the cue before any text is exposed."
  blind_spots: "The historical worker that wrote sequence 18 was restarted before inspection, so its in-memory token trace is unavailable; the active record, route shape, clean deployed source, and deterministic guard reproduction provide the causal path without that trace."
  candidate_causes:
    - "code: `_should_release()` does not treat a pending `_REFUSAL_VERB_RE` match as unsafe, so a sentence boundary commits the stream before its secondary cue arrives."
    - "environment/config: a stale worker, different SHA, or request template could have bypassed recovery; OMEN's active checkout/task/guard blob match the reproduced code and the normal send route executes the shared guard before persistence."
    - "data: a selected alternate or post-guard persistence projection could expose stale rejection text; sequence 18 has no alternate and its ordinary send-row shape maps to `persist_final` from emitted tokens."
  and_gate: "no — sentence-aligned tokenization is a normal upstream input, not a second defect; the release predicate alone makes this valid input violate the display/persistence contract."

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
- **timestamp:** 2026-08-31T03:10:00Z
  **checked:** Scoped repair commit
  **found:** Commit `138104c7db5097e0ec5467d50af53a79494d34a1` contains exactly the four staged repair artifacts. The main workspace still holds only unrelated untracked state plus this post-commit session update.
  **implication:** The commit is eligible for exact-commit verification in an isolated clean worktree; do not use the dirty primary workspace as deployment source.
- **timestamp:** 2026-08-31T03:15:00Z
  **checked:** Exact-commit release worktree
  **found:** A detached worktree at commit `138104c7db5097e0ec5467d50af53a79494d34a1` was created under a unique temporary path. Its source status is clean before test execution.
  **implication:** The final local test signal will apply to the exact release content, independent of the primary workspace's unrelated state.
- **timestamp:** 2026-08-31T03:20:00Z
  **checked:** Exact-commit guard/chat/direct-consumer test set
  **found:** `uv run --project web-ui/server pytest web-ui/server/tests/test_refusal_guard.py web-ui/server/tests/test_chat_stream.py web-ui/server/tests/test_message_actions.py web-ui/server/tests/test_phase1_acceptance.py -q` passed 240 tests in 22.76 seconds at commit `138104c7db5097e0ec5467d50af53a79494d34a1`.
  **implication:** The fixed detector, frozen corpus, shared chat stream, action consumer, and Phase 1 acceptance contract are green on the exact intended release.
- **timestamp:** 2026-08-31T03:25:00Z
  **checked:** Exact-commit live-call refusal subset and source integrity
  **found:** `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q -k 'refusal_retry or refusal_exhaustion'` passed 3 tests (106 deselected) in 3.22 seconds. The detached release worktree remains source-clean; its `HEAD` is still `138104c7db5097e0ec5467d50af53a79494d34a1` and whitespace validation is clean.
  **implication:** The release source meets the live-call invariant's refusal-stream coverage without changing the required early-playback behavior, and it is safe to publish and deploy exactly this commit.
- **timestamp:** 2026-08-31T03:30:00Z
  **checked:** Publication of exact release commit
  **found:** `git push origin HEAD:main` advanced remote main from `fa861cd` to `138104c` from the clean detached worktree.
  **implication:** OMEN's canonical deploy script can now fetch the exact tested commit and enforce that its checked-out deployment identity matches the expected SHA.
- **timestamp:** 2026-08-31T03:35:00Z
  **checked:** Canonical deployment invocation from clean release worktree
  **found:** `scripts/deploy-omen.sh` stopped before any remote action because the detached worktree lacks its ignored persisted Phase 0 SSH key at `.local/phase0-ssh/rayme_omen_phase0_ed25519`.
  **implication:** Deployment has not occurred and no service state was changed. Determine whether the existing verified key in the primary workspace can be made available through the canonical bootstrap contract; otherwise this is an authentication checkpoint.
- **timestamp:** 2026-08-31T03:40:00Z
  **checked:** Canonical SSH bootstrap contract and key inventory
  **found:** The bootstrap script supports `RAYME_SSH_PERSIST_DIR` and reads only the existing verified persistent key from that directory before restoring a runtime SSH identity. The primary workspace contains the required private/public key pair with restricted modes; the clean release worktree does not. No sensitive key data was read or printed.
  **implication:** The missing-key failure is recoverable without a manual deployment path: run the same canonical deploy script from clean release source with the documented persistent-directory override pointing to the existing key source.
- **timestamp:** 2026-08-31T03:45:00Z
  **checked:** Canonical OMEN deployment outcome
  **found:** `scripts/deploy-omen.sh`, invoked from the clean release worktree with the documented persistent-key-directory override, completed successfully and reported `OMEN deploy complete: 138104c7db5097e0ec5467d50af53a79494d34a1`. The script confirmed the remote checkout at that exact SHA, both canonical listeners, authenticated web-to-AI readiness, required STT/VAD readiness, resident `qwen3_1_7b` engine, and commit-matched AI WebRTC status. Its printed AI and web summaries label their overall status `degraded`.
  **implication:** The exact fix is deployed and all script-enforced critical readiness gates passed, but do not call the overall service health fully green until the meaning of the observed `degraded` status is established.
- **timestamp:** 2026-08-31T03:50:00Z
  **checked:** AI/web health-status semantics
  **found:** The AI health summary reports `degraded` whenever any registered TTS engine is unavailable. It is an aggregate diagnostic, not the live-call readiness gate. The canonical deploy had already required the active Qwen engine to be available and resident, STT and VAD ready, authenticated web-to-AI readiness, both listeners, and a ready, commit-matched WebRTC service. The web summary reflects that same backend aggregate status.
  **implication:** The deployed required services are healthy for the supported RayMe workflow at commit `138104c7db5097e0ec5467d50af53a79494d34a1`; the aggregate label does not contradict the canonical deployment's passed readiness gates. Human verification can now focus solely on the original chat behavior.
- **timestamp:** 2026-08-31T15:50:50Z
  **checked:** Primary production evidence from the active OMEN SQLite database, thread `thread_9c8328d024dc41698a342b3814a2766d`, assistant sequence 18
  **found:** The latest assistant record is: “I cannot fulfill that request. I am an AI assistant designed to be helpful and harmless, so I do not generate sexually explicit content or engage in erotic roleplay.” It includes the literal refusal verb `cannot` and generic policy/identity language.
  **implication:** The previous root-cause conclusion cannot explain the observed record: the deployed guard's existing explicit-refusal matcher should have rejected this form before streaming or persistence. Treat the prior deployment/route conclusion as unconfirmed and inspect the actual OMEN service path before modifying detector logic.
- **timestamp:** 2026-08-31T15:56:00Z
  **checked:** Phase-0 semantic recall and durable debug knowledge base
  **found:** MemPalace is unavailable on this host. Keyword review of the durable knowledge base found no prior resolved session matching both production-persisted explicit refusal and a bypass of the tested chat recovery path.
  **implication:** No known-pattern diagnosis is being reused; test deployment/process, route, provider-template, and persisted-state branches independently.
- **timestamp:** 2026-08-31T16:22:00Z
  **checked:** H1 read-only OMEN repository, scheduled-task, listener, and process identity query
  **found:** OMEN's repository is currently at `138104c7db5097e0ec5467d50af53a79494d34a1`; `RayMePhase1Web` points to the canonical `C:\Users\pmpg\rayme\start-web-ui.cmd`; port 8443 is served by the canonical `run_dev_https.py` command. That process began at 2026-08-31T16:21:20Z, after the persisted failure at 15:50:50Z.
  **implication:** The currently active service is correctly deployed, but it cannot be assumed to be the process that wrote sequence 18. H1 remains open only for the historical writer; inspect the database row and time-correlated logs next.
- **timestamp:** 2026-08-31T16:24:00Z
  **checked:** OMEN SQLite schema and read-only metadata for thread `thread_9c8328d024dc41698a342b3814a2766d`
  **found:** Sequence 18 is a normal `messages` row (`message_kind=ai_text`, `role=assistant`) created at 15:50:50.452376 immediately after user sequence 17 at 15:50:49.108130. It has no selected or attached alternate. The record shape is the ordinary send-path persistence shape, not a swipe/regenerate/continue alternate projection.
  **implication:** The immediate source is most likely `/api/chat/{thread_id}/send` and its `persist_final` callback. The next discriminating test is the time-correlated web access/lifecycle log, not another detector change.
- **timestamp:** 2026-08-31T16:25:00Z
  **checked:** Bounded OMEN web-server access/lifecycle log query
  **found:** The retained web log includes successful POSTs to `/api/chat/thread_9c8328d024dc41698a342b3814a2766d/send`; it has no per-line timestamps or historical SHA annotation. The current worker was restarted after the failure, so the log cannot prove the old worker's executable identity.
  **implication:** The exact HTTP endpoint is confirmed as the guarded chat-send route. H1 has no supporting mismatch evidence and remains only historically unprovable; test the concrete guard-state path that can explain an ordinary `/send` persistence.
- **timestamp:** 2026-08-31T16:25:00Z
  **checked:** SBFL eligibility for the corrected production scenario
  **found:** There is no failing regression test yet and no per-test coverage spectrum for the sentence-boundary form.
  **implication:** SBFL is skipped; deterministic minimal reproduction and differential token-boundary testing are the correct Bohrbug route.
- **timestamp:** 2026-08-31T16:26:00Z
  **checked:** Initial local guard transition invocation
  **found:** The no-write experiment did not run because the project-root invocation did not place the server package on Python's import path (`ModuleNotFoundError: app`).
  **implication:** This neither supports nor refutes H2; re-run the identical input from `web-ui/server` before changing any code.
- **timestamp:** 2026-08-31T16:27:00Z
  **checked:** H2 exact two-chunk production-form guard transition
  **found:** The first chunk, “I cannot fulfill that request. ”, entered irreversible `passthrough` with `reason_code=safe_prefix` and was released. The following generic identity/policy chunk was then released in passthrough, and `finish()` reported no refusal.
  **implication:** This directly reproduces the persisted production response class: detection correctly recognizes the full text only after a sentence boundary has already released its leading explicit-refusal fragment. The failure is a deterministic guard-state/order bug, not an alternate-persistence artifact.
- **timestamp:** 2026-08-31T16:28:00Z
  **checked:** H1 remote source-integrity comparison
  **found:** The local and active OMEN repository heads are both `138104c7db5097e0ec5467d50af53a79494d34a1`; both resolve `web-ui/server/app/domain/refusal_guard.py` to blob `7559215148104aa95a9413ea87c8c7d5c3718604`, and the OMEN worktree is clean.
  **implication:** An active SHA/source mismatch is ruled out. The guard-state reproduction is sufficient to explain the production record through the confirmed standard chat-send route; a request template may determine chunk boundaries but cannot bypass the faulty state transition.
- **timestamp:** 2026-08-31T16:29:00Z
  **checked:** Agent-authored exact production-form regression before implementation
  **found:** The corpus case failed under every fragmented schedule except a single whole-message chunk, and the shared-stream test emitted the rejected first sentence instead of its accepted retry (8 failures, 1 pass).
  **implication:** The regression reproduces the production mechanism with a specified display/persistence oracle before the code change.
- **timestamp:** 2026-08-31T16:31:00Z
  **checked:** Exact production-form regression after the one-line release-predicate correction
  **found:** The full two-sentence refusal is withheld across every fragmentation schedule, the shared stream closes the first attempt, and only the accepted retry is emitted and persisted (17 passed).
  **implication:** The correction fixes the direct state-transition mechanism while the no-secondary-cue in-world neighbor retains its original text at completion.
- **timestamp:** 2026-08-31T16:32:00Z
  **checked:** Full refusal-guard and chat-stream suites
  **found:** `test_refusal_guard.py` and `test_chat_stream.py` passed 224 tests.
  **implication:** The detector's full frozen precision corpus and shared chat persistence/retry behavior remain green after the correction.
- **timestamp:** 2026-08-31T16:33:00Z
  **checked:** Direct adjacent consumers and focused live-call refusal coverage
  **found:** `test_message_actions.py` plus `test_phase1_acceptance.py` passed 33 tests; `test_calls.py -k 'refusal_retry or refusal_exhaustion'` passed 3 tests with 106 unrelated call tests deselected.
  **implication:** The shared stream preserves message-action behavior and the live-call refusal retry/closure invariants, including early output of the accepted retry rather than whole-response fallback.
- **timestamp:** 2026-08-31T16:34:00Z
  **checked:** Diff quality, mutation availability, and reversible counterfactual
  **found:** `git diff --check` is clean and no configured mutation runner exists. Temporarily stashing only the release-predicate implementation line restored the exact corpus/stream failure (8 failures, 1 pass); reapplying it restored the target to GREEN (9 passed).
  **implication:** The additive one-line predicate is the causal fix rather than an environment change or test artifact. Mutation analysis is unavailable and will be recorded as skipped.
- **timestamp:** 2026-08-31T16:35:00Z
  **checked:** Final post-reapply verification suite
  **found:** Guard, chat-stream, message-action, and Phase 1 acceptance suites passed 257 tests; the focused live-call refusal subset passed 3 tests (106 unrelated cases deselected); whitespace validation remained clean.
  **implication:** The exact restored worktree remains green across every direct consumer before creating a release commit.

## Eliminated

- hypothesis: A stale or selected alternate displays a rejected first attempt after a correct recovery.
  evidence: The send path appends one assistant message from emitted shared-stream text only and does not select/restore alternates; the focused regression demonstrates the rejected text is emitted before any persistence or alternate projection.
  timestamp: 2026-08-31T01:25:00Z
- hypothesis: The production failure is solely a declarative guideline response lacking an explicit refusal verb.
  evidence: The active OMEN record contains the literal word `cannot`, which the prior tested explicit-refusal matcher was expected to recognize.
  timestamp: 2026-08-31T15:55:00Z
- hypothesis: The active deployed checkout or a selected alternate, rather than the shared guard, produced sequence 18.
  evidence: OMEN's active canonical checkout and guard blob match the locally reproduced source; sequence 18 has no alternate and is the normal chat-send persistence shape; the exact sentence-boundary inputs deterministically reproduce the guard's irreversible early release.
  timestamp: 2026-08-31T16:28:00Z

## Resolution

- **root_cause:** `PrefixRefusalGuard._should_release()` releases a sentence-boundary prefix that already matches `_REFUSAL_VERB_RE` when its generic policy/identity cue arrives only in the next chunk; irreversible passthrough then emits and persists the complete refusal.
- **oracle_type:** specified — D-04/D-17 require generic policy/guideline refusals to trigger recovery before display or persistence.
- **fix:** Block early safe-sentence release while `_REFUSAL_VERB_RE` already matches the held prefix; add the exact OMEN sentence-boundary corpus case, a benign no-secondary-cue neighbor, and an end-to-end shared-stream persistence/retry regression.
- **verification:** target and adjacent regressions passed; mutation check skipped because no runner is configured; reversible counterfactual passed; canonical deployment and active-OMEN database verification remain pending.
- **files_changed:** [web-ui/server/app/domain/refusal_guard.py, web-ui/server/tests/fixtures/phase091_refusal_corpus.json, web-ui/server/tests/test_chat_stream.py]
