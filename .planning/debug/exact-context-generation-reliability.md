---
status: verifying
trigger: "At deployed functional commit 9c09140, ten production swipes against a controlled clone whose effective request is byte-identical to the user's original thread yielded six in-character alternates and four safe llm_refusal_exhausted outcomes. No refusal was persisted or selected, but RayMe must reliably generate an in-character response instead of merely hiding refusals."
created: 2026-09-01
updated: 2026-09-01T08:24:00Z
---

# Exact-Context Generation Reliability

## Current Focus

- **user-goal preservation:** RayMe must generate a real in-character model reply for the selected character from the existing exact conversation context; refusal filtering remains intact, and no canned/non-model fallback may be introduced.
- **bug_class:** Mandelbug — the same effective production request reaches both accepted in-character output and all-attempt guarded exhaustion across fresh swipes.
- **known_pattern_candidate:** `same-thread-refusal-recurrence` — the prior guard omission is excluded for persisted output, but its attempt telemetry can identify whether the remaining failures are provider generation, request composition, or retry-path equivalence.
- **hypothesis:** Confirmed: applying the same Qwen sampling temperature (0.80) to every recovery attempt leaves the exact refusal-prone context in a low-variance policy-refusal mode. A bounded Qwen-only retry temperature of 1.20 improves the model's chance to select an in-character continuation while preserving the configured first attempt, prompt order, correction, guard, retry bound, and all non-temperature sampler fields.
- **test:** Add a deterministic adapter regression that verifies only Qwen attempts 2–3 receive the 1.20 recovery temperature, while attempt 1 and Generic requests retain configured temperature. Then rerun the unchanged full recovery test and real controlled-clone swipes after canonical deployment.
- **expecting:** Local contracts must prove the wire condition change is exactly scoped; production must materially improve on the deployed 24/30 completion baseline while persisting no refusal prose or canned fallback.
- **next_action:** Commit the accepted deployed-e2e debug record. The service remains healthy after the clone-only sample; no further code change is justified because the released real-route evidence matches the controlled recovery result.
- **reasoning_checkpoint:**
  hypothesis: "The Qwen retry path's reuse of configured temperature 0.80 causes residual all-attempt exhaustion because this exact context has a high-probability generic-refusal mode; setting temperature 1.20 only on Qwen attempts two and three broadens recovery sampling enough to select in-character continuations."
  confirming_evidence:
    - "Thirty real clone swipes with the deployed path completed 24 times and exhausted six times; only two completed on attempt one while 22 completed after recovery."
    - "A content-free 20-versus-20 isolated attempt-two experiment held every request field except temperature constant: 1.20 accepted 14 and guard-refused six, versus deployed 0.80 accepting seven and refusing 13."
    - "Thirty full non-persisting exact recovery flows with first attempt unchanged and retry attempts at 1.20 completed 28 times and exhausted twice; 17 completed on attempt two and seven on attempt three."
  falsification_test: "If the adapter regression finds any first-attempt or Generic temperature override, or a production exact-clone sample at the scoped change does not materially exceed 24/30 completion without refusal persistence, the hypothesis is wrong or insufficient."
  fix_rationale: "A Qwen-only retry sampler override changes the one empirically causal recovery condition while retaining the user's configured baseline generation behavior and every safety/persistence contract."
  blind_spots: "The full-flow evidence uses direct non-persisting Qwen calls through the same adapter rather than the deployed action route; final acceptance requires a stronger real-swipe sample. The optimal temperature may be context-dependent, so the override is deliberately bounded to recovery attempts."
  candidate_causes:
    - "config: the configured 0.80 sampler temperature is reused unchanged for all Qwen attempts, including guarded recovery."
    - "data: the byte-identical selected-history context makes Qwen's default sampling mode produce generic policy refusals at unusually high frequency."
    - "environment: a stale template or deployed source was considered, but clean `5603b22` identity, stable original/clone fingerprint, and real retry acceptance contradict it."
  and_gate: "yes — residual exhaustion requires both the exact context's refusal-prone distribution and reuse of the low-variance retry sampler; either an ordinary context or broader retry sampling reduces the observed terminal rate."

## Symptoms

- **expected:** A fresh exact-context swipe produces one persisted, selected in-character model alternate; guarded retries must provide materially improved recovery rather than repeatedly exhausting.
- **actual:** On deployed `9c09140`, a controlled clone with a byte-identical effective request produced six in-character alternates and four `llm_refusal_exhausted` outcomes from ten real swipes. No generic refusal text was persisted or selected.
- **errors:** `llm_refusal_exhausted` on four of ten production swipes.
- **reproduction:** Use only a controlled clone of the original thread. Keep the original user message, historical alternates, and selection read-only; compare attempt-level, content-free stream activity and request structure across fresh exact-context swipes.
- **started:** Verified after canonical deployment of `9c09140` on 2026-09-01.

## Eliminated

- **hypothesis:** Generic refusal prose still reaches alternate persistence or selection in the exact-context swipe path.
  **evidence:** The ten-swipe production verification at clean `9c09140` produced six in-character stored alternates and four no-row safe exhaustions; zero refusal rows were persisted or selected.
  **timestamp:** 2026-09-01T07:00:00Z

- **hypothesis:** The deployed retry correction fails because it does not explicitly ban a new refusal/policy/meta reply.
  **evidence:** In a fresh-seed 20-versus-20 exact Qwen attempt-two experiment, the explicit late-user anti-refusal correction accepted 8 while the deployed correction accepted 9. Every other wire message, sampler field, no-thinking option, and request setting was equal.
  **timestamp:** 2026-09-01T07:40:00Z

- **hypothesis:** The deployed `min_p=0.05` floor suppresses viable in-character continuations in the exact retry context.
  **evidence:** A fresh-seed 20-versus-20 exact attempt-two test with every field equal except `min_p` accepted 10 under the deployed floor and 8 with `min_p=0.00`.
  **timestamp:** 2026-09-01T07:42:00Z

## Evidence

- **timestamp:** 2026-09-01T07:00:00Z
  **checked:** Resolved same-thread refusal incident and its final exact-context deployment verification.
  **found:** The prior incident froze structural refusal classes and proved byte-identical clone requests, but its final ten-swipe verification still exhausted on four requests after all guarded attempts were rejected.
  **implication:** The persistence classifier is not the remaining repair target; inspect generation composition and retry differentiation before changing retry count or guard rules.

- **timestamp:** 2026-09-01T07:00:00Z
  **checked:** Knowledge-base candidate and admitted SillyTavern prompt-composition diagnosis.
  **found:** RayMe's historical prompt design is thinner than SillyTavern's ordered Main/character/examples/history/late post-history contract; prior research explicitly requires a shared ordered inspectable composer, late post-history instruction, example injection, model-aware roles, and sampler controls.
  **implication:** Prompt order/template and retry-request equivalence are concrete code/config hypotheses, not a basis to weaken refusal handling.

- **timestamp:** 2026-09-01T07:07:00Z
  **checked:** Current normal-send and message-action generation paths.
  **found:** Normal send passes its process-local `RefusalActivityStore` into `stream_chat_completion`, but regenerate/swipe/continue call `collect_chat_completion` without an activity sink. The exact-context swipe evidence therefore has no per-attempt reason/outcome projection even though the ring already accepts the `swipe` action.
  **implication:** Add the existing allowlisted activity seam to actions before inferring why their live retries exhaust.

- **timestamp:** 2026-09-01T07:07:00Z
  **checked:** Current Qwen request serializer and structured prompt order.
  **found:** RayMe coalesces leading Main/character/Auxiliary sections into one Qwen system message, maps the late post-history instruction to a user message after history, and places retry correction as a final user message before any assistant prefill. For retries, all section/history/sampler settings are unchanged; only a fresh seed and the correction (including `/no_think` when enabled) differ.
  **implication:** The adapter preserves intended SillyTavern-style late instruction ordering, but only live attempt data can show whether this bounded correction materially improves the refusal-prone exact context.

- **timestamp:** 2026-09-01T07:10:00Z
  **checked:** New controlled swipe-terminal activity regression launch.
  **found:** The direct `pytest` launcher is absent from the shell (`pytest: command not found`); no test body ran and no product conclusion follows.
  **implication:** Run the exact target through the repository's managed Python environment before deciding whether the missing activity seam is reproduced.

- **timestamp:** 2026-09-01T07:11:00Z
  **checked:** Controlled real swipe-action terminal regression in the pinned server environment.
  **found:** RED as predicted: `create_swipe_alternate()` rejects the process-local activity-store argument before generation (`TypeError: unexpected keyword argument`).
  **implication:** The exact swipe path has no route to the existing activity ring. Add only that existing allowlisted seam before collecting new production reliability evidence.

- **timestamp:** 2026-09-01T07:14:00Z
  **checked:** Controlled terminal regression after wiring the existing activity store through message actions and collector.
  **found:** GREEN: the swipe terminal records exactly three allowlisted outcomes in retry order (`retry`, `retry`, `exhausted`), and serialized records contain neither the rejection canary nor a seed field.
  **implication:** The new seam is content-free and process-local. It changes neither classifier behavior nor recovery conditions and can now instrument the real exact-context swipe path.

- **timestamp:** 2026-09-01T07:16:00Z
  **checked:** Expanded message-action, stream, adapter, and preview suite after the observability seam.
  **found:** Three existing action tests fail only because their uninstrumented collector spies reject the newly forwarded activity keywords. The controlled terminal, remaining 114 checks, scoped Ruff, and whitespace pass.
  **implication:** The instrumentation must be a true no-op when no store is supplied. Narrow its forwarding condition rather than changing pre-existing action contracts.

- **timestamp:** 2026-09-01T07:18:00Z
  **checked:** Corrected observability seam across action, stream, Qwen adapter, and prompt-preview direct suites.
  **found:** GREEN: 117 checks pass. The action seam forwards activity only when a store is explicitly supplied; uninstrumented collectors retain their former call shape. Scoped Ruff and whitespace checks pass.
  **implication:** The action instrumentation is behavior-preserving and ready for an additional route-level terminal test.

- **timestamp:** 2026-09-01T07:19:00Z
  **checked:** Controlled real `/swipes` route terminal with an injected process-local activity store.
  **found:** GREEN: the real route returns the established `llm_refusal_exhausted` result and records exactly `swipe` attempts 1–3 with outcomes retry, retry, exhausted; serialized activity contains neither the rejection canary nor seed data.
  **implication:** Exact-context production swipes can now be diagnosed without persisting generated prose or changing recovery semantics.

- **timestamp:** 2026-09-01T07:24:00Z
  **checked:** Complete server test suite after the action activity seam.
  **found:** GREEN: 966 server tests pass. Three pre-existing FastAPI deprecation warnings remain.
  **implication:** The observability-only increment preserves server behavior beyond the focused recovery suites.

- **timestamp:** 2026-09-01T07:24:00Z
  **checked:** Static and diff validation.
  **found:** Scoped Ruff and `git diff --check` pass. Repository-wide Ruff has one unrelated pre-existing unused local in `tests/test_calls.py`, outside this diff.
  **implication:** Do not modify unrelated live-call coverage. The scoped instrumentation change is ready for a commit and canonical diagnosis deployment.

- **timestamp:** 2026-09-01T07:26:00Z
  **checked:** Scoped commit preparation.
  **found:** Published commit `712afb5` contains only action activity wiring, two controlled terminal tests, and this active debug record; unrelated working-tree artifacts remain unstaged.
  **implication:** Publish this exact diagnosis increment, deploy it canonically, and use its process-local activity only to collect causal attempt evidence.

- **timestamp:** 2026-09-01T07:31:00Z
  **checked:** Canonical deployment of the published observability increment.
  **found:** `scripts/deploy-omen.sh` completed at `5603b22`; it rebuilt the web client, applied migrations, reasserted canonical launchers/tasks, restarted both listeners, and reported STT/VAD plus resident Qwen ready. Aggregate health remains degraded only for inactive registered engines.
  **implication:** Deployment is complete but not yet independent production evidence. Confirm active service identity/readiness before any controlled-clone swipe.

- **timestamp:** 2026-09-01T07:32:00Z
  **checked:** Independent OMEN checkout, process, task, and health projection after deployment.
  **found:** OMEN is clean at `5603b22`; both canonical listeners and scheduled tasks are running. Web health is OK; AI health has its known degraded aggregate while STT/VAD and resident Qwen are ready.
  **implication:** The observability increment is active in the real swipe path. Controlled clone sampling can begin without touching the original conversation.

- **timestamp:** 2026-09-01T07:33:00Z
  **checked:** Read-only content-free original-to-clone prefix fingerprints for every original assistant target.
  **found:** One controlled clone reproduces all twelve original assistant-target prefixes, including the sequence-24 swipe target, with distinct cloned identities but equal snapshot/selected-history fingerprints.
  **implication:** Use only the clone's sequence-24 target for the stronger sample; the original thread remains read-only and its effective request can be rechecked by digest before and after every production mutation.

- **timestamp:** 2026-09-01T07:35:00Z
  **checked:** Thirty real production swipes on the matching clone, with original/clone request fingerprints checked before and after every clone-only mutation.
  **found:** The original and clone request fingerprints remain equal and constant at `6d705143…09a21`. Twenty-four swipes persisted in-character output and six safely exhausted. Only two accepted on attempt one; 22 recovered after retry (15 on attempt two and seven on attempt three). The retry activity reports 41 withheld attempts and six terminal exhaustions; its reason codes are allowlisted and contain no prompt, completion, seed, credential, URL, audio, or raw exception data. Qwen receives the intended one leading merged system message, ordered history, late post-history user instruction, and unchanged sampler; attempts two and three add only the terminal user correction plus fresh seed.
  **implication:** Retries materially improve exact-context response generation (from 2/30 first-attempt acceptance to 24/30 final acceptance), disproving a no-op retry/template hypothesis. The remaining 6/30 terminal rate is still not acceptable. Test whether the late correction’s missing explicit anti-refusal instruction is the causal residual difference before changing it.

- **timestamp:** 2026-09-01T07:37:00Z
  **checked:** Initial isolated A/B runner launch.
  **found:** The runner used the wrong process working directory and stopped before loading RayMe code or opening a provider request.
  **implication:** Correct the runner location and rerun unchanged; this setup error neither supports nor refutes the retry-correction hypothesis.

- **timestamp:** 2026-09-01T07:38:00Z
  **checked:** Corrected runner working-directory launch.
  **found:** The remote interpreter retains its original script import path after `chdir`, so it again stopped before importing RayMe or contacting the provider.
  **implication:** Add the deployed server directory explicitly to the interpreter import path and rerun the same non-persisting A/B experiment.

- **timestamp:** 2026-09-01T07:40:00Z
  **checked:** Isolated exact attempt-two Qwen A/B with deployed correction versus one explicit anti-refusal correction; all non-correction messages, model/template settings, sampler fields, and no-thinking mode were equal.
  **found:** Across 20 fresh seeds per condition, the deployed correction accepted 9 and guard-refused 11; the explicit correction accepted 8 and guard-refused 12. Both correction variants were final user messages and their request fingerprints differed only in correction content.
  **implication:** The stronger wording does not improve this exact model behavior and is rejected as a repair. Do not change production correction prose; test one sampler field at a time.

- **timestamp:** 2026-09-01T07:42:00Z
  **checked:** Isolated exact attempt-two Qwen A/B with deployed sampler versus `min_p=0.00`; prompts, retry correction, no-thinking mode, seed policy, and every other sampler field were equal.
  **found:** Across 20 fresh seeds per condition, deployed settings accepted 10 and guard-refused 10; the zero-min-p variant accepted 8 and guard-refused 12. Fingerprints differed only in the min-p field.
  **implication:** Removing the min-p floor weakens rather than improves recovery. Keep the deployed min-p setting and test temperature independently.

- **timestamp:** 2026-09-01T07:44:00Z
  **checked:** Isolated exact attempt-two Qwen A/B with deployed sampler versus `temperature=1.00`; prompts, retry correction, no-thinking mode, seed policy, and every other sampler field were equal.
  **found:** Across 20 fresh seeds per condition, deployed settings accepted 10 and guard-refused 10; the 1.00-temperature variant accepted 12 and guard-refused 8. Fingerprints differed only in temperature.
  **implication:** The direction is favorable but the two-generation difference is not enough to claim a reliable repair. Test the next bounded temperature setting with the same one-field control.

- **timestamp:** 2026-09-01T07:46:00Z
  **checked:** Isolated exact attempt-two Qwen A/B with deployed sampler versus `temperature=1.20`; prompts, retry correction, no-thinking mode, seed policy, and every other sampler field were equal.
  **found:** Across 20 fresh seeds per condition, deployed settings accepted 7 and guard-refused 13; the 1.20-temperature variant accepted 14 and guard-refused 6. Fingerprints differed only in temperature.
  **implication:** The effect is large enough to test as a recovery-only strategy: preserve the configured first attempt, but use 1.20 only for attempts two and three. Validate complete bounded flows before implementing.

- **timestamp:** 2026-09-01T07:48:00Z
  **checked:** Thirty complete non-persisting guarded recovery flows through the deployed Qwen adapter, with attempt one at configured temperature and attempts two/three at 1.20 only.
  **found:** Twenty-eight flows completed and two exhausted. Four accepted on attempt one, 17 on attempt two, and seven on attempt three. The request invariant confirms first-attempt temperature stayed configured and retry requests differed from deployed requests only in temperature; no generated text or seed was retained.
  **implication:** The recovery-only sampler change materially improves full exact-context completion from the deployed 24/30 to 28/30 in a controlled same-adapter test. Proceed with the narrowly scoped implementation and real action-route verification.

- **timestamp:** 2026-09-01T07:50:00Z
  **checked:** Adapter golden regression before the scoped implementation.
  **found:** RED as predicted: attempt one retained the configured Qwen temperature, while attempts two and three still sent 0.65 instead of the required 1.20. All prompt roles, late instruction placement, no-thinking field, and non-temperature sampler assertions remained unchanged.
  **implication:** The regression isolates the missing recovery-sampler behavior rather than changing prompt or guard semantics.

- **timestamp:** 2026-09-01T07:51:00Z
  **checked:** Qwen adapter, stream, action, prompt-preview, and refusal-guard suites after scoped implementation.
  **found:** GREEN: 643 checks pass. The Qwen golden now proves attempt one retains configured temperature while attempts two and three use 1.20; Generic requests and a user-configured temperature above 1.20 retain their original values. Three pre-existing FastAPI deprecation warnings remain; scoped Ruff and whitespace pass.
  **implication:** The repair is constrained to Qwen recovery sampling and preserves prompt, guard, normal first-attempt, generic-adapter, and persistence behavior. Run the full suite before release.

- **timestamp:** 2026-09-01T07:54:00Z
  **checked:** Complete server suite after the scoped recovery-sampler implementation.
  **found:** GREEN: 967 server tests pass. Three pre-existing FastAPI deprecation warnings remain.
  **implication:** The one-field Qwen retry override preserves the complete server test surface. Complete static and counterfactual acceptance signals before publishing.

- **timestamp:** 2026-09-01T07:54:00Z
  **checked:** First scoped static-check launcher.
  **found:** The command was issued from repository root, which has no server virtual-environment executable; no static check ran.
  **implication:** Run the unchanged scoped static check from `web-ui/server`; this launcher error is not product or lint evidence.

- **timestamp:** 2026-09-01T07:55:00Z
  **checked:** Scoped static analysis and diff integrity from the managed server environment.
  **found:** GREEN: scoped Ruff and `git diff --check` pass. The diff is limited to the Qwen recovery sampler, adapter-boundary tests, and active debug record; unrelated workspace artifacts remain untracked.
  **implication:** The implementation is within the confirmed mechanism. Prove its causal necessity by temporary removal/reapplication before publication.

- **timestamp:** 2026-09-01T07:57:00Z
  **checked:** Counterfactual removal and reapplication of only the Qwen recovery-temperature branch.
  **found:** Removing the branch returns attempts two and three to the configured 0.65 and makes exactly those two adapter golden cases RED; attempt one remains GREEN. Reapplying the branch returns all 14 adapter cases GREEN, including Generic and high-user-temperature boundary cases.
  **implication:** The regression kills the fix-site omission, and the branch—not an unrelated test condition—causes the requested retry-only wire behavior.

- **timestamp:** 2026-09-01T07:58:00Z
  **checked:** Scoped publication.
  **found:** Published repair commit `0fb99b1` and its active-debug update `c8d81e4` contain only the Qwen retry-temperature minimum, its adapter-boundary regression, and session state; unrelated workspace artifacts remain unstaged.
  **implication:** Deploy this exact repair only through the canonical script, then use the controlled clone for final production verification.

- **timestamp:** 2026-09-01T08:05:00Z
  **checked:** Canonical deployment of the scoped Qwen recovery-sampler repair.
  **found:** `scripts/deploy-omen.sh` completed at `8ab04d2`; it updated OMEN to that published revision, rebuilt the web client, reapplied migrations and canonical launchers/tasks, restarted both listeners, and reported STT/VAD plus resident Qwen ready. The aggregate AI health remains degraded only for inactive registered engines.
  **implication:** The intended retry-sampler code has been released through the only permitted path. Independently confirm running-service identity before clone-only action-route sampling.

- **timestamp:** 2026-09-01T08:06:00Z
  **checked:** First independent-health command launch.
  **found:** The local shell rejected the nested command quoting before SSH connected, so no deployed process, endpoint, or generation request was contacted.
  **implication:** Correct the command transport and rerun the same read-only readiness projection; this setup error is not deployment or production evidence.

- **timestamp:** 2026-09-01T08:08:00Z
  **checked:** Independent OMEN source identity, cleanliness, canonical listeners/tasks, and health projection after deployment.
  **found:** OMEN is clean at `8ab04d2`; both expected listeners and scheduled tasks are running. Web health is OK; AI aggregate health is degraded only for inactive engines while STT/VAD and resident Qwen are ready.
  **implication:** The intended recovery-sampler source is active and the clone-only action-route validation can begin.

- **timestamp:** 2026-09-01T08:10:00Z
  **checked:** First content-free remote sample-runner launch.
  **found:** The local tool runtime lacks the attempted text-encoding API, so it stopped before opening SSH or making any HTTP request.
  **implication:** Use an ASCII-safe transport encoding for the unchanged runner. This local launch failure neither mutates the clone nor supplies generation evidence.

- **timestamp:** 2026-09-01T08:12:00Z
  **checked:** Second remote sample-runner transport launch.
  **found:** Windows rejected the fully embedded encoded runner because it exceeded its command-line length limit; the interpreter did not start and no clone request ran.
  **implication:** Stream the already content-free runner payload over standard input to a short encoded PowerShell launcher. This transport correction does not alter the test or product state.

- **timestamp:** 2026-09-01T08:18:00Z
  **checked:** First streamed action-route sample collection.
  **found:** The clone-only runner reached the real route, but the terminal stream handle was not retained by the local tool after its initial yield, so its full aggregate result cannot be recovered. A read-only activity projection confirms only recent allowlisted swipe metadata is present; it does not prove the required full sample invariants. No original-thread data was written.
  **implication:** Treat that run as invalid evidence and repeat the unchanged clone-only protocol while retaining the terminal session handle through completion.

- **timestamp:** 2026-09-01T08:22:00Z
  **checked:** Thirty sequential real `/swipes` through the released action route, using only the controlled clone and content-free aggregate projections.
  **found:** Twenty-eight requests persisted an accepted alternate and two safely exhausted; there were no unexpected outcomes. Eight accepted on attempt one, 17 on attempt two, and three on attempt three, with 27 withheld retry records and two terminal-exhausted records. All 28 new alternates and the final selected alternate pass the same refusal guard; the original thread snapshot stayed unchanged. Original/clone effective-request digests were equal before and after and remained stable; the active adapter stayed Qwen and the previewed configured first-attempt temperature stayed unchanged. No activity-contract violation occurred.
  **implication:** The released recovery-only sampler repair reproduces the controlled 28/30 result through the actual route, improving the prior deployed 24/30 completion result while preserving original-context isolation, prompt identity, first-attempt behavior, retry bounds, and the refusal-persistence barrier.

- **timestamp:** 2026-09-01T08:24:00Z
  **checked:** Independent service readiness projection after the completed route sample.
  **found:** Both expected listeners remain active; Web health is OK and STT/VAD plus resident Qwen remain ready.
  **implication:** The real-route recovery result was obtained from a healthy released service, not a transient shutdown or fallback state.

## Resolution

- **root_cause:** Qwen reuses the user-configured 0.80 temperature for all recovery attempts, including the refusal-prone exact context. That low-variance retry sampling keeps selecting policy refusals even after the retry instruction; bounded 1.20 sampling for attempts two and three materially improves recovery while leaving the configured initial attempt unchanged.
- **oracle_type:** specified — the selected character must receive a real model-generated in-character response; a safe terminal exhaustion is not sufficient reliability.
- **fix:** Applied a 1.20 minimum temperature only to `qwen_llama_server` attempts two and three, without changing first-attempt/configured sampling, prompt text/order, guard behavior, retry count, or persistence.
- **verification:**
  target_test: { result: pass, suites_run: ["Qwen retry adapter golden (3 cases; RED before fix, GREEN after)", "focused adapter/stream/action/preview/guard checks (643 passed)", "complete server suite (967 passed)"] }
  mutation_check: { result: skipped, reason_if_skipped: "no Stryker, mutmut, or equivalent mutation runner is configured" }
  no_op_deletion: { result: pass, deletion_justified_by_rca: false }
  adjacent_tests: { result: pass, suites_run: ["Generic adapter golden", "higher configured Qwen temperature boundary", "stream/action/persistence/preview/refusal-guard coverage", "scoped Ruff", "git diff --check"] }
  revert_and_reconfirm: { result: pass, bug_returned_on_revert: true, fixed_on_reapply: true, evidence: "removing only retry-temperature branch makes Qwen attempts 2/3 golden cases RED; reapplying restores GREEN" }
  deployed_e2e: { result: pass, sample: "30 real controlled-clone swipe actions", stored: 28, safe_exhausted: 2, accepted_attempts: { attempt_1: 8, attempt_2: 17, attempt_3: 3 }, prior_same_route_baseline: { stored: 24, safe_exhausted: 6, sample_size: 30 }, refusal_rows: 0, selected_refusals: 0, original_thread_unchanged: true, request_digest_equal_and_stable: true, activity_contract_violations: 0 }
  guardrail_verdict: accepted
- **files_changed:** [web-ui/server/app/domain/generation_profiles.py, web-ui/server/tests/test_generation_profiles.py]
