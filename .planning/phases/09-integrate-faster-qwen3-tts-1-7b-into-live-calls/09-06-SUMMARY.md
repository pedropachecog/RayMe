---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 06
subsystem: voice-lifecycle
tags: [qwen3-tts, prompt-eviction, voice-deletion, privacy, cancellation]

requires:
  - phase: 09-05
    provides: Worker-isolated Qwen prompt preparation and bounded streaming protocol
  - phase: 09-07
    provides: Durable authorization metadata for saved Qwen clone references
provides:
  - Saved-voice-derived opaque prompt ownership keys
  - Cancel-first exact-owner prompt eviction across API, manager, adapter, and worker
  - Transactional Qwen saved-voice deletion gated on confirmed backend invalidation
affects: [qwen-call-runtime, saved-voice-management, gpu-prompt-lifecycle]

actuals:
  tokens: 9943
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns: [saved-id-derived-opaque-owner, cancel-before-evict, transactional-delete-gate, typed-internal-invalidation]

key-files:
  created: []
  modified:
    - ai-backend/app/api/tts.py
    - ai-backend/app/models/model_manager.py
    - ai-backend/app/models/tts_qwen3.py
    - ai-backend/app/models/tts_qwen3_protocol.py
    - ai-backend/app/models/tts_qwen3_worker.py
    - web-ui/server/app/domain/voice_service.py
    - web-ui/server/app/domain/ai_backend_client.py
    - web-ui/server/app/api/voices.py

key-decisions:
  - "Prompt ownership uses sha256('rayme:qwen3_1_7b:' + saved_voice_id), keeping the durable owner identity separate from private prompt-content cache identity."
  - "A matching active request is cancelled before the adapter acquires the generation lock and evicts worker prompt state."
  - "Qwen soft deletion commits only after a strict backend invalidation result; failure remains sanitized, retryable, and leaves the saved voice active."

patterns-established:
  - "Exact-owner eviction: unrelated opaque keys return not_present without disturbing the prepared prompt."
  - "Truthful lifecycle boundary: durable deletion follows confirmed ephemeral-state invalidation, never precedes it."

requirements-completed: [REQ-22]

coverage:
  - id: D1
    description: Matching Qwen prompt tensors, adapter ownership, and manager readiness caches are evicted by opaque owner key while unrelated voices remain usable.
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py ai-backend/tests/test_model_manager.py -q"
        status: pass
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q"
        status: pass
    human_judgment: false
  - id: D2
    description: Saved Qwen soft deletion invalidates its backend prompt first, is idempotent, isolates non-Qwen voices, and returns a sanitized retryable failure without deleting on backend error.
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q"
        status: pass
      - kind: integration
        ref: "uv run --project web-ui/server pytest web-ui/server/tests -q"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 06: Saved Voice Prompt Eviction Summary

**Saved Qwen voice deletion now cancels matching work and removes worker tensors, adapter ownership, and manager readiness through one opaque, retryable lifecycle.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-31T18:44:58Z
- **Completed:** 2026-07-31T19:04:55Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Added an engine-scoped internal invalidation contract that accepts only a 64-character lowercase hexadecimal owner key and exposes no reference content, transcript, path, tensor, or cache hash.
- Implemented cancel-first exact-owner eviction through the model manager, adapter, worker protocol, and worker process, including idempotent `invalidated`/`not_present` results.
- Bound Qwen saved-voice soft deletion to successful backend invalidation while keeping backend failures sanitized, retryable, and non-destructive.
- Proved matching tensor objects do not survive eviction and unrelated prepared voices continue to synthesize.

## Task Commits

Each task was committed through TDD gates:

1. **Task 1 RED: Define Qwen prompt eviction lifecycle** - `c4e59df` (test)
2. **Task 1 GREEN: Evict Qwen prompt state by owner key** - `9fd02e5` (feat)
3. **Task 2 RED: Define saved Qwen deletion invalidation** - `aa286fc` (test)
4. **Task 2 GREEN: Invalidate Qwen prompt on saved voice delete** - `2576547` (feat)

## Files Created/Modified

- `ai-backend/app/api/tts.py` - Strict engine-scoped prompt invalidation endpoint with fixed public failure payloads.
- `ai-backend/app/models/model_manager.py` - Matching prompt-cache/readiness reset under the shared preparation lock.
- `ai-backend/app/models/tts_qwen3.py` - Opaque ownership tracking, active cancellation, worker eviction, and idempotent result model.
- `ai-backend/app/models/tts_qwen3_protocol.py` - Worker invalidation result reports whether a prompt owner matched.
- `ai-backend/app/models/tts_qwen3_worker.py` - Exact-owner prompt tensor eviction inside the worker process.
- `ai-backend/tests/test_tts_qwen3.py` - Tensor-removal, owner isolation, cancellation, idempotency, sanitized API, and recovery coverage.
- `ai-backend/tests/test_model_manager.py` - Manager cache and selected-prompt eviction coverage.
- `web-ui/server/app/domain/voice_service.py` - Durable owner-key derivation and invalidate-before-delete transaction ordering.
- `web-ui/server/app/domain/ai_backend_client.py` - Typed strict invalidation request and response contract.
- `web-ui/server/app/api/voices.py` - Backend bridge and sanitized retryable deletion failure.
- `web-ui/server/tests/test_voices.py` - Two-voice isolation, repeated delete, non-Qwen isolation, failure, and client contract coverage.
- `web-ui/server/tests/test_calls.py` - Existing saved-Qwen call assertions updated to the durable owner-key contract.

## Decisions Made

- Derived ownership from the durable saved voice ID rather than private audio/transcript content so lifecycle operations have a stable key without exposing clone material.
- Separated owner identity from the adapter's content cache key; matching owner invalidation clears both only when ownership matches.
- Cancelled an active matching generation before waiting for the adapter operation lock, preventing future output before prompt memory is cleared.
- Treated backend confirmation as part of deletion correctness: the database tombstone is committed only after a valid strict invalidation result.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Extended the worker protocol and call contract for truthful ownership semantics**
- **Found during:** Tasks 1 and 2
- **Issue:** The plan's file list omitted the worker protocol/worker process and existing saved-Qwen call assertion, but exact tensor eviction and durable owner identity cannot be proven or carried end-to-end without those seams.
- **Fix:** Added the worker `matched` result, exact worker-state eviction, and updated the call regression to assert the saved-ID-derived opaque key.
- **Files modified:** `ai-backend/app/models/tts_qwen3_protocol.py`, `ai-backend/app/models/tts_qwen3_worker.py`, `web-ui/server/tests/test_calls.py`
- **Verification:** 71 Qwen/model-manager tests, 208 web-server tests, and 102 live-call invariant tests passed.
- **Committed in:** `9fd02e5`, `2576547`

---

**Total deviations:** 1 auto-fixed (1 Rule 2)
**Impact on plan:** The additional seams are required for the planned privacy and lifecycle guarantees; no unrelated feature scope was added.

## Issues Encountered

None.

## Known Stubs

None.

## Verification

- Focused backend invalidation/cache selection: 12 passed, 59 deselected.
- Focused web deletion/Qwen selection: 19 passed, 22 deselected.
- Full Qwen adapter/model-manager suite: 71 passed.
- Full saved-voice server suite: 41 passed.
- Full web-server suite: 208 passed.
- Live-call invariant regression suite: 102 passed; only three pre-existing dependency deprecation warnings were emitted.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Saved Qwen voice ownership now terminates at delete across durable and GPU state. The lifecycle is ready for phase-level verification and call testing with RayMe; no implementation blocker remains in this plan.

## Self-Check: PASSED

All 12 changed files, four task commits, and the canonical summary artifact were verified present.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
