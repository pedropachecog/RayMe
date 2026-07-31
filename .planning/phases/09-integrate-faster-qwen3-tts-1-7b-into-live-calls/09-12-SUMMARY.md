---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 12
subsystem: release-evidence
tags: [qwen3-tts, wavlm, cuda, evidence-verifier, privacy, longitudinal-quality]

requires:
  - phase: 09-10
    provides: Incremental Qwen LLM-to-TTS submission and terminal-authorized speech persistence
  - phase: 09-11
    provides: Sample-bounded live playout, truthful terminal metrics, and exact-request cancellation
provides:
  - Twenty immutable Phase 09 release scenarios with exact runtime, model, fixture, threshold, seed, and event contracts
  - Pinned privacy-local CUDA WavLM speaker trend scoring across integrated baseline and early/middle/late soak buckets
  - Independent contracts/core/decision evidence verification with thirty-three named false-readiness mutations
affects: [09-13, 09-14, 09-15, qwen3-release-evidence, omen-deployment, physical-call-handoff]

actuals:
  tokens: 28528
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns: [raw-threshold-recomputation, exact-commit-evidence, local-only-speaker-scoring, adversarial-verifier-self-test]

key-files:
  created:
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-evidence-manifest.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-speaker-score.py
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py
  modified: []

key-decisions:
  - "Freeze the selected release fixture to the passed hardware tracer's generated non-person SAPI reference; prior product-owner listening is explicitly not treated as speaker permission."
  - "Run microsoft/wavlm-base-plus-sv only from revision feb593a6c23c1cc3d9510425c29b0a14d2b07b1e on the pinned CUDA/Torch/transformers stack, retaining only hashes and cosine scalars."
  - "Ignore stored overall/pass booleans and independently recompute every core and decision threshold from raw scenario, turn, STT, speaker, queue, track, cancellation, and identity fields."
  - "Keep autonomous release readiness separate from pending integrated human listening and pending physical-call acceptance."

patterns-established:
  - "Evidence artifacts share schema version, exact deployed commit, bounded recency, critical-gate ids, and scalar-only privacy rules before any threshold is evaluated."
  - "The verifier owns a passing synthetic bundle solely for hostile mutation tests; deployed evidence can pass only through separately acquired production-path raw files."
  - "Speaker stability is a trend gate against both early turns and a same-commit short/medium/long integrated baseline, never a standalone likeness verdict."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "Twenty AI-SPEC scenarios, their event order, thresholds, seeds/anchors, pinned identities, and hash-bound non-person fixture are frozen in a privacy-local manifest."
    requirement: REQ-22
    verification:
      - kind: unit
        ref: "test_phase09_evidence.py -k 'manifest or speaker' (9 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A pinned local CUDA WavLM scorer records same-commit integrated baseline plus early/middle/late cosine trends without committing audio, embeddings, transcripts, or paths."
    requirement: REQ-22
    verification:
      - kind: unit
        ref: "test_phase09_evidence.py speaker helper and payload tests"
        status: pass
      - kind: integration
        ref: "09-verify-evidence.py --contracts-only"
        status: pass
    human_judgment: false
  - id: D3
    description: "The independent verifier recomputes core/decision release gates and fails closed for thirty-three named commit, fallback, bound, drift, cancellation, identity, and privacy mutations."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "09-verify-evidence.py --self-test (33/33 rejected)"
        status: pass
      - kind: unit
        ref: "test_phase09_evidence.py (21 passed)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Automated readiness remains structurally separate from pending integrated listening and physical call acceptance."
    requirement: REQ-46
    verification:
      - kind: unit
        ref: "test_manifest_keeps_automated_and_human_acceptance_separate plus missing-human-pending-separation self-test"
        status: pass
    human_judgment: false

duration: 17min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 12: Independent Evidence Contracts Summary

**RayMe now has a frozen twenty-scenario release manifest, a pinned privacy-local CUDA WavLM trend scorer, and a hostile self-tested verifier that recomputes readiness from raw evidence.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-31T21:03:45Z
- **Completed:** 2026-07-31T21:20:07Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Froze exactly twenty Phase 09 scenarios with public stimuli, expected event order, criticality, seeds, anchors, artifact ownership, and the complete AI-SPEC threshold set.
- Bound evidence to the accepted Faster Qwen3-TTS source/model/Torch/CUDA identities and the honest generated non-person hardware-tracer fixture; no product-owner action was recast as voice permission.
- Added local-only `WavLMForXVector` scoring at the exact model revision with 16 kHz resampling, L2-normalized embeddings, cosine trends, same-commit baseline binding, and `0.05` early/baseline late-drop gates.
- Added contracts-only, core-ready, decision-ready, self-test, and print-deployed-commit modes that validate freshness/commit identity and independently recompute raw runtime, readiness, streaming, queue, track, cancellation, soak, STT, speaker, browser, and leak gates.
- Proved the verifier rejects all thirty-three named false-readiness mutations, including false stored status, stale/foreign commits, fallback, missing gates/scenarios, invalid authorization, unbounded queues/output/cache, progressive speaker drift, cancellation leakage, substitutions, and private data.

## Task Commits

Each TDD task was committed with separate RED and GREEN gates:

1. **Task 1 RED: Define manifest and speaker scoring contracts** - `3c30e56` (test)
2. **Task 1 GREEN: Freeze local speaker evidence contract** - `a10fb8c` (feat)
3. **Task 2 RED: Define adversarial evidence verification** - `837248e` (test)
4. **Task 2 GREEN: Verify raw release evidence independently** - `6eae94c` (feat)

## Files Created/Modified

- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-evidence-manifest.json` - Twenty scenarios, immutable identities, selected fixture hashes, global/scenario thresholds, evidence inventory, and separate acceptance states.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-speaker-score.py` - CUDA-only pinned WavLM loader, local WAV resampling/embedding, cosine trend calculation, same-commit baseline binding, and scalar-only JSON output.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py` - Contracts/core/decision verifier, leak scanner, exact-commit printer, synthetic test bundle, and thirty-three hostile mutations.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py` - Deterministic CPU-safe manifest/scorer/verifier contracts with no model download.

## Decisions Made

- Used the generated non-person SAPI reference that already passed the Phase 09 hardware tracer as the frozen release fixture. A future real-person fixture can be selected only through the exact hash-bound steward/basis/LAN-scope contract; listening approval alone is never permission.
- Required the scorer to resolve the exact local WavLM snapshot, assert `WavLMForXVector`, `transformers==4.57.3`, Torch `2.10.0+cu126`, CUDA 12.6, and CUDA-only parameters before any private audio is embedded.
- Kept speaker audio, embeddings, private transcripts, and paths out of committed artifacts. The scorer emits only opaque bucket/turn ids, SHA-256 values, cosines, medians, deltas, and pinned runtime metadata.
- Treated artifact booleans as non-authoritative. Readiness comes only from recomputed raw thresholds, exact event order, exact commit/freshness, complete scenario/gate inventories, and zero privacy findings.
- Kept integrated human listening and physical-call acceptance pending even when automated gates pass; candidate Spike 005 listening remains explicitly separate.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The host `/usr/bin/python3` does not include pytest. The planned `python3 -m pytest` commands were executed with the existing `ai-backend/.venv/bin` placed first on `PATH`; no package was installed and no model/network access occurred.
- The legacy STATE format has no parseable `Current Plan / Total Plans in Phase` fields, so `state.advance-plan` could not run and `state.add-decision` emitted `Phase ?` labels. The normal progress/session handlers still updated counts and timestamps; the four labels and activity description were corrected in place before the metadata commit.

## Known Stubs

None.

## Threat Flags

None. The new local file-reading/scoring and evidence-verification surfaces are fully covered by T-09-06, T-09-07, and T-09-08; no network endpoint, authentication path, database schema, or hosted judge was added.

## Verification

- Manifest/speaker gate: 9 passed, 12 deselected.
- Full Phase 09 evidence tests: 21 passed.
- `09-verify-evidence.py --contracts-only`: PASS.
- `09-verify-evidence.py --self-test`: 33/33 named mutations rejected; PASS.
- Python compilation and `git diff --check`: PASS.
- No CUDA model or WavLM snapshot was downloaded or loaded during local contract verification.

## User Setup Required

None - no dependency, credential, service, hosted tool, or deployment configuration was added.

## Next Phase Readiness

- Plan 09-13 can implement its production OMEN runner directly against the frozen scenario/artifact schema and use `write_synthetic_bundle` only for deterministic hostile tests, never as release evidence.
- Plan 09-14 can require the five exact-commit core artifacts and run `--core-ready`; Plan 09-15 can add the pinned speaker, leak, and real browser artifacts and run `--decision-ready`.
- No deployment or production evidence was collected in this plan. Integrated listening and the physical call remain honest later gates.

## Self-Check: PASSED

- All four plan output/test files and this summary exist.
- Commits `3c30e56`, `a10fb8c`, `837248e`, and `6eae94c` exist in git history in RED/GREEN order.
- Both task gates, the full 21-test evidence suite, all thirty-three hostile mutations, Python compilation, and `git diff --check` passed.
- No stub, skipped test, unrun verification, unexpected deletion, unmodeled threat surface, model download, deployment, or production evidence collection remains in this plan.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
