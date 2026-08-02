# Voice Sample Authorization Policy

## Authoritative rule

Uploading a voice sample to RayMe is assumed authorized. This is the active policy
for product work, requirements, acceptance, evidence, and future planning. No extra
authorization record is needed to save, preview, test-play, prepare, call, accept,
or gather evidence for a voice.

## Prohibited resurrection paths

Do not introduce reference-source, data-steward, consent, authorization-basis,
use-scope, or authorization-status forms, fields, status/readiness states, or
sidecars. Their absence must not reject, delay, block, or otherwise change a sample's
selection, and must never use an automatic synthetic or non-person fallback. Product
and evidence checks must not recreate these concepts under a new
name.

## Retained technical correctness checks

This policy removes authorization metadata, not technical safety. RayMe still requires
a RayMe-owned contained sample asset with valid audio bytes, stored byte/hash integrity,
and a nonblank matching transcript plus acoustic alignment where the engine needs one.
Prompt identity remains opaque; audio and transcript handling remains private and leak
resistant; deletion must invalidate related cache/prompt material. A generated
non-person fixture is allowed only when explicitly selected as a transport-test fixture,
never as missing-metadata fallback.

## Immutable historical records

The following retained artifacts are factual records of completed work. They are
non-normative, are superseded by this policy, and must not be copied into new
requirements, tests, evidence, or acceptance criteria.

- Completed contradictory Phase 9 plans: `09-04-PLAN.md`, `09-07-PLAN.md`,
  `09-08-PLAN.md`, `09-09-PLAN.md`, `09-12-PLAN.md`, `09-13-PLAN.md`,
  `09-14-PLAN.md`, and `09-15-PLAN.md` in
  `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/`.
- Phase 9 summaries containing the retired scheme: `09-04-SUMMARY.md`,
  `09-07-SUMMARY.md`, `09-08-SUMMARY.md`, `09-09-SUMMARY.md`,
  `09-12-SUMMARY.md`, `09-13-SUMMARY.md`, `09-14-SUMMARY.md`, and
  `09-15-SUMMARY.md` in that same phase directory.
- Resolved debug records: `.planning/debug/resolved/qwen-saved-voice-422.md` and
  `.planning/debug/resolved/qwen-voice-transcript-reject.md`; Phase 9 review:
  `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-REVIEW.md`.
- Frozen exact-commit evidence artifacts in the Phase 9 directory:
  `09-evidence-manifest.json`, `09-run-hardware-tracer.py`,
  `09-run-omen-evidence.py`, `09-qwen-fidelity-sweep.py`, `09-speaker-score.py`,
  `09-verify-evidence.py`, and `test_phase09_evidence.py`.
- The Phase 8 summaries and `08-OMEN-EVIDENCE.md` may use a sanitized
  sample-source label as historical evidence terminology. It is never a RayMe product
  authorization field.
