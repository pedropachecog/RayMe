---
status: investigating
trigger: "At deployed functional commit 9c09140, ten production swipes against a controlled clone whose effective request is byte-identical to the user's original thread yielded six in-character alternates and four safe llm_refusal_exhausted outcomes. No refusal was persisted or selected, but RayMe must reliably generate an in-character response instead of merely hiding refusals."
created: 2026-09-01
updated: 2026-09-01T07:00:00Z
---

# Exact-Context Generation Reliability

## Current Focus

- **user-goal preservation:** RayMe must generate a real in-character model reply for the selected character from the existing exact conversation context; refusal filtering remains intact, and no canned/non-model fallback may be introduced.
- **bug_class:** Mandelbug — the same effective production request reaches both accepted in-character output and all-attempt guarded exhaustion across fresh swipes.
- **known_pattern_candidate:** `same-thread-refusal-recurrence` — the prior guard omission is excluded for persisted output, but its attempt telemetry can identify whether the remaining failures are provider generation, request composition, or retry-path equivalence.
- **hypothesis:** Confirmed instrumentation gap: message actions have no path to deliver their `swipe` recovery activity to the existing process-local ring. The controlled terminal reaches `create_swipe_alternate()` but fails before generation because its interface rejects the activity store.
- **test:** Add an optional existing-store dependency from the message-action API through regenerate/swipe/continue into `collect_chat_completion`, preserving the established normal-send record schema and testing the unchanged controlled terminal.
- **expecting:** The terminal produces exactly `[swipe/1/retry, swipe/2/retry, swipe/3/exhausted]`, while the allowlisted record serialization excludes the rejection prose and seed.
- **next_action:** Run only `scripts/deploy-omen.sh` from the primary checkout at published `712afb5`. After independent readiness confirmation, identify the existing controlled clone through content-free request fingerprints and collect a materially larger swipe sample.

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

## Resolution

- **root_cause:**
- **oracle_type:** specified — the selected character must receive a real model-generated in-character response; a safe terminal exhaustion is not sufficient reliability.
- **fix:**
- **verification:**
- **files_changed:** []
