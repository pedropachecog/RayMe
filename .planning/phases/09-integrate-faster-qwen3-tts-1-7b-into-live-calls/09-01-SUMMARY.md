---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 01
subsystem: ai-runtime
tags: [faster-qwen3-tts, qwen3-tts, voice-cloning, uv, cuda]

requires:
  - phase: 09-spikes
    provides: Accepted Faster Qwen3-TTS v0.3.2 runtime, 1.7B listening choice, RTX 3060 stability, and bounded streaming evidence
provides:
  - Immutable Faster Qwen3-TTS v0.3.2 Git source lock at the approved commit
  - Truthful selectable qwen3_1_7b backend roster identity
  - Transcript-required and native-streaming capability metadata for the 1.7B Base model
affects: [09-02, 09-03, qwen3-worker, model-manager, voice-lab, omen-deployment]

actuals:
  tokens: 4096
  tasks: 2
  commits: 3

tech-stack:
  added: [faster-qwen3-tts-v0.3.2]
  patterns: [immutable-git-dependency, truthful-engine-identity, tdd-roster-contract]

key-files:
  created: []
  modified:
    - ai-backend/pyproject.toml
    - ai-backend/uv.lock
    - ai-backend/app/models/tts_registry.py
    - ai-backend/app/models/engine_metadata.py
    - ai-backend/tests/test_tts_registry.py
    - ai-backend/tests/test_health.py

key-decisions:
  - "Lock Faster Qwen3-TTS to approved commit a70afc0f81f7f5f8801c3227968f1102f43f211c instead of a mutable package or tag reference."
  - "Expose only qwen3_1_7b as the production roster identity, with matching transcript and streaming capabilities, while leaving F5 as the sole global default."

patterns-established:
  - "Approved young-package sources require registry, repository, annotated-tag-object, peeled-commit, and lock agreement."
  - "Engine metadata states model identity and production capabilities truthfully; legacy identity handling stays outside the selectable roster."

requirements-completed: [REQ-22]

coverage:
  - id: D1
    description: "The optional TTS dependency resolves the approved Faster Qwen3-TTS v0.3.2 source at its immutable peeled commit."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "git ls-remote annotated/peeled v0.3.2 assertion plus uv lock --project ai-backend --check"
        status: pass
    human_judgment: false
  - id: D2
    description: "Backend registry and health metadata expose Qwen3-TTS 1.7B-Base with transcript-required native streaming while preserving one-hot F5 default residency."
    requirement: REQ-22
    verification:
      - kind: unit
        ref: "ai-backend/tests/test_tts_registry.py and ai-backend/tests/test_health.py (27 passed)"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 01: Runtime Lock and Roster Identity Summary

**The approved Faster Qwen3-TTS v0.3.2 source is immutably locked, and RayMe now advertises one truthful transcript-guided, streaming 1.7B engine identity without changing its global default.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-31T15:28:25Z
- **Completed:** 2026-07-31T15:33:24Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Pinned `faster-qwen3-tts` to source commit `a70afc0f81f7f5f8801c3227968f1102f43f211c` and regenerated the reproducible uv lock.
- Replaced the selectable 0.6B roster identity with `qwen3_1_7b` / `Qwen3-TTS 1.7B-Base` in both backend metadata sources.
- Locked transcript-required ICL cloning, native streaming, RTX 3060 evidence, F5 default residency, and sanitized health behavior in focused tests.

## Task Commits

Each task was committed atomically:

1. **Task 1: Lock the product-owner-approved runtime source** - `b905bdc` (chore)
2. **Task 2 RED: Require truthful Qwen3 1.7B roster identity** - `1f2a9b5` (test)
3. **Task 2 GREEN: Publish Qwen3 1.7B engine metadata** - `00bdccd` (feat)

## Files Created/Modified

- `ai-backend/pyproject.toml` - Adds the exact approved Git source to the optional TTS group.
- `ai-backend/uv.lock` - Resolves Faster Qwen3-TTS 0.3.2 at the immutable source commit.
- `ai-backend/app/models/tts_registry.py` - Publishes the canonical 1.7B identity and truthful clone/stream capabilities.
- `ai-backend/app/models/engine_metadata.py` - Keeps health/model-manager roster identity aligned with the registry.
- `ai-backend/tests/test_tts_registry.py` - Enforces exact identity, transcript requirement, streaming capability, and evidence copy.
- `ai-backend/tests/test_health.py` - Enforces the canonical id/label and idle Qwen state beside sole-resident F5.

## Decisions Made

- Used the approved peeled source commit directly in the dependency URL; the annotated tag object is required to exist but is not trusted as the source revision.
- Kept Qwen selectable but did not change the current global F5 default or one-hot residency semantics.
- Kept runtime arguments and private paths out of public engine/health metadata.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The installed `uv tree` CLI did not accept the attempted `--extra` inspection option. This did not affect implementation; exact lock entries, pinned compatible versions, and the prescribed `uv lock --check` gate verified the result directly.

## User Setup Required

None - runtime installation and OMEN model setup are owned by later canonical deployment plans.

## Next Phase Readiness

- The worker/protocol plans can now build against one immutable Faster Qwen3-TTS runtime and one canonical 1.7B engine id.
- No blocker remains for Plan 09-02.

## Self-Check: PASSED

- All six modified implementation/test files and this summary exist.
- Task commits `b905bdc`, `1f2a9b5`, and `00bdccd` are present in git history.
- The exact source-lock assertion, focused 27-test gate, and `git diff --check` passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
