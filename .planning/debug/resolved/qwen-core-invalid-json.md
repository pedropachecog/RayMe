---
status: resolved
trigger: "Canonical OMEN deployment at c200f0133984f839fd993c5aecf2326617701f8a passed Qwen provisioning, CUDA, runtime identity, and production streaming/cancellation tracing, then failed exact-commit Phase 09 core evidence with 'FAIL: RayMe runtime returned invalid JSON'."
created: 2026-08-01T10:27:00Z
updated: 2026-08-01T11:55:00Z
---

# Qwen Core Evidence Invalid JSON

## Symptoms

**Expected behavior:** `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh` deploys the exact pushed commit and completes the Phase 09 core evidence and independent verification gates.

**Actual behavior:** OMEN updated to `c200f0133984f839fd993c5aecf2326617701f8a`, provisioned the pinned Faster Qwen3-TTS runtime/model, attested CUDA, built and started both services, and passed the production Qwen saved-voice/WebRTC tracer. The next gate stopped with `FAIL: RayMe runtime returned invalid JSON`.

**Error messages:**

```text
== Running exact-commit Phase 09 Qwen core evidence
FAIL: RayMe runtime returned invalid JSON
Production Qwen core evidence failed: FAIL: RayMe runtime returned invalid JSON
At line:813 char:5
```

**Timeline:** First observed immediately after deploying the post-review Phase 09 fixes at `c200f01` on 2026-08-01. The same gate passed before the review/fix series at deployed commit `3501a1a`.

**Reproduction:** From the repository root, run `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh`. The failure occurs after the production Qwen tracer and before the independent verifier.

## Current Focus

hypothesis: Confirmed fixed in production — canonical deployment now advances OMEN's persistent database to Alembic head before new ORM services launch.
test: Completed exact-commit production verification with `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh` at commit 2ed38e33d2d475b7465cdaa788f00858e0b6d6d6.
expecting: Satisfied — migrations reached 0007, the hardware tracer and core evidence passed, the independent verifier passed, and the canonical deploy completed.
next_action: Archive this resolved session and retain its root-cause/prevention record for future deployments.
user_goal_preservation: The fix must make the canonical OMEN deployment advance the persisted database safely before new services start, while preserving exact-commit Qwen live-call streaming, early playback, cancellation, and all existing deployment gates.
bug_class: bohrbug
reasoning_checkpoint:
  hypothesis: "scripts/deploy-omen.sh launches c200f01 without running Alembic, so SQLAlchemy selects Message.call_id from an OMEN database stamped 0002 where that column does not exist."
  confirming_evidence:
    - "OMEN access logs show POST /api/characters 201 followed by POST /api/threads 500 with sqlite3.OperationalError: table messages has no column named call_id."
    - "Read-only `alembic current` on OMEN reports 0002_voice_storage while repository `alembic heads` reports 0007_call_turn_ownership; repository search found no upgrade invocation in canonical deploy/startup paths."
    - "Migration 0004_call_turn_idempotency explicitly adds messages.call_id and messages.call_turn_id."
  falsification_test: "The hypothesis would be false if canonical deploy already advanced the same RAYME_DATABASE_URL to 0007 before service launch, or if a revision-0007 database still produced the same missing-column error."
  fix_rationale: "Run the repository's Alembic upgrade through the installed web server environment before writing/starting launchers, failing the deployment if schema advancement fails; this removes the code/schema skew instead of masking the JSON symptom."
  blind_spots: "The local regression cannot prove the upgrade succeeds against OMEN's real retained data; the parent must rerun scripts/deploy-omen.sh and verify remote revision, core evidence, health, and real workflow."
  candidate_causes:
    - "code: canonical deploy has no Alembic upgrade step before launching the new ORM code (confirmed)."
    - "environment: OMEN retains a persistent database stamped 0002 while the deployed repository head is 0007 (confirmed contributing condition)."
    - "data: an existing row shape might independently block migrations (not observed; must be tested by the actual deployment)."
  and_gate: "yes — the failure requires both the deploy omission and a retained pre-0004 database; a fresh database created from current metadata would not show this missing column."

## Evidence

- timestamp: 2026-08-01T10:26:49Z
  checked: "Canonical deploy output before the failing gate."
  found: "Exact commit c200f0133984f839fd993c5aecf2326617701f8a was fetched and launched; Torch 2.10.0+cu126, CUDA 12.6, RTX 3060, runtime source commit a70afc0, model revision fd4b254, prompt readiness, early playback, no whole-WAV fallback, cancellation, and recovery all passed the production tracer."
  implication: "The failure is downstream of successful runtime/model/call tracing and is currently localized to the core-evidence runner or its serialization boundary."

- timestamp: 2026-08-01T10:27:00Z
  checked: "Deployment authority and stopping point."
  found: "The only deployment command used was scripts/deploy-omen.sh; it aborted at its own core-evidence gate and did not report deployment completion."
  implication: "Do not declare OMEN ready or run ad-hoc deployment workarounds; repair and rerun the canonical script."

- timestamp: 2026-08-01T10:38:00Z
  checked: "Phase 0 durable recall and project/agent skill configuration."
  found: "No .planning/debug/knowledge-base.md exists, no project-defined .codex/skills or .agents/skills directory exists, configured gsd-debugger agent skills were empty, and no MemPalace recall tool is available."
  implication: "There is no known-pattern candidate to privilege; proceed with direct code tracing and the common Data Shape / API Contract and Environment / Config hypotheses."

- timestamp: 2026-08-01T10:43:00Z
  checked: "Deployment gate and good-to-bad change boundary."
  found: "scripts/deploy-omen.sh captures the exact-commit Python evidence runner's merged stdout/stderr, surfaces its final FAIL line, and aborts at lines 854-865. Between known-good 3501a1a and failing c200f01, 49 files changed; the deployment script changed by 68 lines and the code-review series also changed AI/backend and database behavior."
  implication: "The visible PowerShell error is a faithful wrapper around a Python runner failure. The investigation must trace the runner's own JSON producer rather than changing PowerShell error handling."

- timestamp: 2026-08-01T10:43:00Z
  checked: "Phase 1.25 spectrum-based fault localization eligibility."
  found: "No locally identified failing test yet provides per-test coverage with both failing and passing spectra for this OMEN-only evidence failure."
  implication: "SBFL is skipped for now; deterministic narrow reproduction and differential tracing are the correct first route."

- timestamp: 2026-08-01T10:48:00Z
  checked: "Exact origin of `FAIL: RayMe runtime returned invalid JSON`."
  found: "The deployment's Python runner is .planning/.../09-run-omen-evidence.py. The exact exception text is defined at 09-run-hardware-tracer.py:238 around decoding an HTTP response body as UTF-8 JSON; the core runner imports and reuses that tracer module. The runner's own request helper uses the distinct text `RayMe production request returned invalid JSON`."
  implication: "This is HTTP response-body data, not subprocess/stdout serialization. The distinguishing request must be one made through the imported tracer client during the core-only evidence path."

- timestamp: 2026-08-01T10:58:00Z
  checked: "Complete core runner and shared HTTP/tracer execution path."
  found: "The preceding tracer and core runner share voice upload/create, WebRTC offer/prepare/status/health, speak, interrupt, and end requests. Core then runs the frozen 20-scenario manifest, including three message-integrity STT calls, 50 soak turns with status/health reads, and finally `collect_canonical_call`, which uniquely POSTs `/api/characters`, `/api/threads`, `/api/calls/start`, and `/api/calls/{id}/end` through the strict tracer JSON client."
  implication: "A failure at a shared endpoint is still possible due to data/state, but the unique public-call requests are the strongest code-path differential. File inventory can locate whether the runner reached that final scenario without another mutating reproduction."

- timestamp: 2026-08-01T11:02:00Z
  checked: "Read-only OMEN runner-work inventory after the failed deployment."
  found: "The private output contains all three clone-valid WAVs, all three message-integrity WAVs, slow-stream-backpressure.wav, and every soak-turn-01.wav through soak-turn-50.wav. The last soak file was completed at 10:33:58Z; no five core JSON artifacts or runner state were written because collection failed before payload assembly."
  implication: "Voice creation, WebRTC, TTS streaming/cancellation, STT, and the entire 50-turn soak succeeded. The invalid JSON occurs after soak, localizing it to the final manifest scenario `canonical-deployed-call` and its public web API chain."

- timestamp: 2026-08-01T11:07:00Z
  checked: "Read-only OMEN web access/error log at the final scenario boundary."
  found: "POST /api/characters returned 201, then POST /api/threads returned 500. The ASGI traceback ends in `sqlite3.OperationalError: table messages has no column named call_id` / SQLAlchemy OperationalError. Because Starlette's unhandled 500 body is plain text, the shared strict client raises the observed `RayMe runtime returned invalid JSON`."
  implication: "The JSON error is a secondary symptom. The actual failure is database schema skew: deployed code maps messages.call_id while OMEN's existing SQLite table does not contain that column."

- timestamp: 2026-08-01T11:14:00Z
  checked: "Canonical migration path and live OMEN Alembic revision."
  found: "No `alembic upgrade` invocation exists in scripts/deploy-omen.sh or server startup. Read-only remote Alembic reports current `0002_voice_storage`; the deployed repository head is `0007_call_turn_ownership`. Migration 0004 is the revision that adds messages.call_id/call_turn_id and the unique index required by the current Message model."
  implication: "Root cause is confirmed as an AND-gated deployment/schema skew: omitted canonical migration execution plus an existing persistent OMEN database older than the new code's schema contract."

- timestamp: 2026-08-01T11:20:00Z
  checked: "Initial focused regression invocation."
  found: "System /usr/bin/python3 has no pytest module, so the agent-authored regression did not execute and no assertion result was obtained."
  implication: "Use the repository's uv-declared test environment; do not count this environment failure as a red/green signal."

- timestamp: 2026-08-01T11:23:00Z
  checked: "Agent-authored deployment regression before the fix."
  found: "`test_omen_deploy_upgrades_persistent_web_schema_before_launch` failed at the first root-cause assertion because deploy-omen.sh contains no migration database binding/command."
  implication: "The regression is RED against the exact omission and is suitable to drive the minimal fix."

- timestamp: 2026-08-01T11:29:00Z
  checked: "Focused deployment regression after the fix."
  found: "`test_omen_deploy_upgrades_persistent_web_schema_before_launch` passed (1 passed)."
  implication: "The canonical script now contains the exact database binding, fail-closed Alembic upgrade, and required pre-launch ordering asserted by the specified contract oracle."

- timestamp: 2026-08-01T11:33:00Z
  checked: "Adjacent deployment/migration tests and script syntax."
  found: "All 5 deploy-contract tests passed; all 10 Alembic migration tests passed, including retained revision-0002-to-head and lifecycle preservation cases; `bash -n scripts/deploy-omen.sh` passed."
  implication: "The migration command is compatible with existing deployment contracts, and repository migrations advance persisted pre-change databases to the schema required by current ORM code."

- timestamp: 2026-08-01T11:37:00Z
  checked: "Exact failing route suite and scoped diff."
  found: "All 7 thread API tests passed. `git diff --check` passed. The scoped diff adds only five fail-closed deployment lines and one specified-oracle contract test; it deletes or short-circuits no behavior."
  implication: "The adjacent route remains healthy on a current schema, and the fix directly adds the missing migration behavior without masking failures."

- timestamp: 2026-08-01T11:41:00Z
  checked: "Guardrail revert-and-reconfirm."
  found: "Stashing only scripts/deploy-omen.sh made the focused regression fail; popping that stash restored the script and the identical test passed. The temporary stash was dropped."
  implication: "The migration block itself is causally necessary and sufficient for the agent-authored deployment-contract regression."

- timestamp: 2026-08-01T11:45:00Z
  checked: "Mutation tooling and final scoped worktree state."
  found: "No Stryker/mutmut configuration or executable exists for this Bash/Python contract change. The intended modified files are scripts/deploy-omen.sh and ai-backend/tests/test_omen_deploy_contract.py; the debug session is the only untracked file; no temporary stash remains."
  implication: "Mutation signal is explicitly skipped per guardrail degradation. All other applicable self-verification signals pass, so the fix is accepted for parent-owned production verification."

- timestamp: 2026-08-01T11:55:00Z
  checked: "Human-confirmed canonical OMEN deployment at fixed commit 2ed38e33d2d475b7465cdaa788f00858e0b6d6d6."
  found: "The only deployment path used was `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh`. Alembic advanced 0002_voice_storage through 0003, 0004, 0005, 0006, and 0007_call_turn_ownership. The exact deployed commit was 2ed38e3. Production Qwen hardware tracing passed early playback, no whole-synthesis fallback, cancellation, and recovery; exact-commit core evidence passed all 50 soak turns and the public-call scenario; the independent verifier passed; the matching core-ready marker was emitted; and the script reported deployment complete."
  implication: "The original invalid-JSON failure is resolved end-to-end on OMEN. The schema skew is removed, `/api/threads` completes inside core evidence, and all RayMe live-call invariants remain verified."

## Hypotheses

- hypothesis: A warning or informational line is written to stdout by the exact core runner and contaminates strict JSON parsing.
  status: active
- hypothesis: A post-review response contract changed and the core runner is serializing a non-JSON object or receiving a non-JSON HTTP body.
  status: active
- hypothesis: The Qwen runtime/model itself failed to load or generate.
  status: deprioritized
  reason: The same-commit production hardware tracer loaded Qwen, prepared the prompt, streamed short/medium/long audio, cancelled, and recovered successfully immediately before the failure.

## Eliminated

- hypothesis: A warning or informational line contaminates the evidence runner's stdout and causes a strict parser to reject its final output.
  evidence: The exact message `RayMe runtime returned invalid JSON` is raised only inside the shared hardware tracer HTTP client's `json.loads(data.decode('utf-8'))`; deploy-omen merely forwards the runner's FAIL line and does not parse runner stdout as JSON.
  timestamp: 2026-08-01T10:48:00Z

## Specialist Review

## Resolution

root_cause: "Canonical scripts/deploy-omen.sh does not run Alembic before launching services; OMEN's retained database stayed at 0002_voice_storage while c200f01 mapped schema through 0007_call_turn_ownership, causing `/api/threads` to select missing `messages.call_id` and return a plain-text 500 that surfaced as invalid JSON."
fix: "Added a fail-closed Alembic `upgrade head` in scripts/deploy-omen.sh, bound to OMEN's exact persistent web database after services are stopped/provisioned and before launchers/services are written or started."
verification:
  target_test: {result: pass}
  mutation_check: {result: skipped, reason_if_skipped: "No Stryker/mutmut configuration or executable exists for the Bash deployment fix", mutant_killed: false}
  no_op_deletion: {result: pass, deletion_justified_by_rca: false}
  adjacent_tests: {result: pass, suites_run: ["ai-backend/tests/test_omen_deploy_contract.py (5 passed)", "web-ui/server/tests/test_migrations.py (10 passed)", "web-ui/server/tests/test_threads.py (7 passed)", "bash -n scripts/deploy-omen.sh (pass)", "git diff --check (pass)"]}
  revert_and_reconfirm: {result: pass, bug_returned_on_revert: true, fixed_on_reapply: true}
  production_verify: {result: pass, deployed_commit: "2ed38e33d2d475b7465cdaa788f00858e0b6d6d6", alembic_revision: "0007_call_turn_ownership", hardware_tracer: pass, core_evidence: pass, independent_verifier: pass, core_ready_marker: pass, canonical_deploy_complete: true}
  guardrail_verdict: accepted
files_changed: ["scripts/deploy-omen.sh", "ai-backend/tests/test_omen_deploy_contract.py"]
oracle_type: specified — AGENTS.md defines scripts/deploy-omen.sh as the only deployment authority, and current ORM/Alembic head defines the schema that must exist before those services launch.

## Postmortem

why_not_caught: "The deployment contract covered provisioning/runtime identity but never asserted database migration execution; route tests created fresh current-schema databases, so they could not expose retained revision-0002 deployment skew."
prevention_guard: "Agent-authored regression ai-backend/tests/test_omen_deploy_contract.py::test_omen_deploy_upgrades_persistent_web_schema_before_launch plus existing revision-0002-to-head migration tests."
