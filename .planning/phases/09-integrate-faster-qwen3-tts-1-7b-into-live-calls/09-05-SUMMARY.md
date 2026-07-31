---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 05
subsystem: ai-runtime
tags: [qwen3-tts, voice-cloning, transcript-alignment, worker-supervision, webrtc, privacy]

requires:
  - phase: 09-04
    provides: Pinned Qwen3-TTS 1.7B hardware tracer with real saved-voice early playback, interruption, and recovery evidence
provides:
  - Content-bound capacity-one Qwen prompt identity with exact-transcript ICL and clean unload/reload behavior
  - Text-relative generation ceilings and strict streamed-WAV/protocol validation
  - STT dual-threshold transcript alignment before Qwen load or prompt extraction
  - Stable sanitized backend error contracts with voice-correctable and Qwen-runtime failure scoping
affects: [09-06, 09-07, qwen3-evaluation, qwen3-deployment, live-calls]

actuals:
  tokens: 19265
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns: [content-addressed-prompt-identity, capacity-one-scalar-alignment-cache, typed-qwen-failure-containment, native-stream-preview-collection]

key-files:
  created: []
  modified:
    - ai-backend/app/models/tts_qwen3.py
    - ai-backend/app/models/tts_qwen3_worker.py
    - ai-backend/app/models/model_manager.py
    - ai-backend/app/api/tts.py
    - ai-backend/app/api/webrtc.py
    - ai-backend/tests/test_tts_qwen3.py
    - ai-backend/tests/test_model_manager.py
    - ai-backend/tests/test_webrtc_signaling.py

key-decisions:
  - "Prompt readiness is bound to reference-byte SHA-256, normalized comparison transcript, model revision, full-ICL mode, and append-silence policy while the exact steward-approved transcript enters ICL unchanged."
  - "Clone alignment accepts when either multiset token coverage is at least 0.45 or normalized edit similarity is at least 0.50; only opaque prompt identity and scalar scores are cached."
  - "Correctable validation, prompt, and ceiling failures leave Qwen usable; only runtime/protocol identity failures unload and mark Qwen unavailable while STT and other TTS engines remain intact."
  - "Qwen preview uses the adapter's native stream and discards partial output on failure; no whole-synthesis fallback was added to the live-call path."

patterns-established:
  - "Validate clone bytes and transcript alignment before loading Qwen or extracting a prompt."
  - "Translate typed Qwen failures into fixed public codes/messages and log only engine, opaque voice id, code, and exception class."
  - "Treat every worker chunk as untrusted until request identity, ordering, timing, WAV structure, signal, cumulative duration, and terminal semantics pass validation."

requirements-completed: [REQ-22, REQ-45]

coverage:
  - id: D1
    description: "Qwen clone prompts use content-bound capacity-one identity, preserve the exact approved transcript, and reject malformed or runaway worker output within bounded ceilings."
    requirement: REQ-22
    verification:
      - kind: unit
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py -q (49 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The backend blocks missing or grossly mismatched clone context before Qwen load/prompt work and returns sanitized typed failures without poisoning a later valid voice, STT, or another TTS engine."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py ai-backend/tests/test_model_manager.py ai-backend/tests/test_webrtc_signaling.py -q (99 passed)"
        status: pass
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py -q (20 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Qwen hardening preserves early live playback, bounded buffering, interruption recovery, and the prohibition on whole-synthesis fallback for VoxCPM2."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q (102 passed)"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 05: Qwen Runtime Hardening Summary

**Qwen3-TTS clone prompts are now content-bound and STT-aligned, while malformed output, runaway streams, and runtime failures terminate within strict Qwen-scoped boundaries.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-31T17:47:58Z
- **Completed:** 2026-07-31T18:07:38Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Bound the one-slot worker prompt cache to the reference bytes, comparison transcript, pinned model/mode, and silence policy without altering the exact transcript used for full ICL.
- Enforced the 60-word input maximum, the specified 6–32 second text-relative audio ceiling, four-step token rounding, 384-token cap, two-second cancellation acknowledgement, strict streamed-WAV validation, and one-terminal protocol behavior.
- Added RayMe STT alignment before Qwen load/prompt extraction with punctuation, case, and accented-English tolerance plus a hard stop when both coverage scores miss their threshold.
- Exposed stable actionable error codes at preview, preparation, status, and WebRTC boundaries while proving a rejected voice does not poison a later valid voice, STT, WebRTC health, or F5.
- Preserved the live-call invariant: native chunks still reach playback before stream completion and no VoxCPM2 whole-synthesis fallback was introduced.

## Task Commits

Each TDD task was committed with separate RED and GREEN gates:

1. **Task 1 RED: Define prompt and output hardening contracts** - `0e194b9` (test)
2. **Task 1 GREEN: Harden prompt identity and stream ceilings** - `2f108e2` (feat)
3. **Task 2 RED: Define alignment and failure-boundary contracts** - `3c689cd` (test)
4. **Task 2 GREEN: Enforce alignment and failure boundaries** - `69ce6c4` (feat)

## Files Created/Modified

- `ai-backend/app/models/tts_qwen3.py` - Typed failure hierarchy, content-bound identity, generation limits, output validation, cancellation, and reload containment.
- `ai-backend/app/models/tts_qwen3_worker.py` - Capacity-one prompt replacement, exact-transcript ICL, native-chunk signal rejection, and token-ceiling enforcement.
- `ai-backend/app/models/model_manager.py` - STT dual-threshold alignment, scalar result caching, content-aware readiness, and Qwen-only runtime containment.
- `ai-backend/app/api/tts.py` - Asynchronous Qwen preparation, native-stream preview collection, partial-output discard, and sanitized error mapping.
- `ai-backend/app/api/webrtc.py` - Exact reference identity checks and shared stable Qwen error contracts at live-call boundaries.
- `ai-backend/tests/test_tts_qwen3.py` - Worker mutation matrix, cache identity, exact transcript, ceilings, cancellation, crash, and reload regressions.
- `ai-backend/tests/test_model_manager.py` - Alignment thresholds/cache, pre-load rejection, exact transcript, later-valid-voice recovery, and engine isolation tests.
- `ai-backend/tests/test_webrtc_signaling.py` - Stable public failure mapping, leak rejection, and correctable-versus-fatal scope tests.

## Decisions Made

- The steward-approved transcript remains authoritative. STT output is comparison evidence only and is never substituted into Qwen full ICL.
- A normal variant passes if either threshold passes; a clone is rejected only when token coverage is below 0.45 and normalized edit similarity is below 0.50.
- Alignment cache state is capacity one and contains only the opaque content key plus acceptance/scalar scores, never transcript or audio.
- Validation, prompt, and ceiling errors are correctable request/voice failures. Worker runtime and protocol failures alone trigger Qwen unload/unavailable containment.
- The non-live preview endpoint may collect validated native chunks into one response WAV, but it cannot call Qwen whole-synthesis; the live path continues forwarding chunks early.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None beyond the expected failing RED tests. The planned implementation made both TDD gates green without changing the live-call architecture.

## User Setup Required

None - no new dependency, service, secret, or deployment configuration was introduced.

## Next Phase Readiness

- Qwen prompt preparation and generation now fail closed under the known mismatch/runaway, malformed-output, worker-crash, hang, and cache-drift cases.
- Plan 09-06 can build product-facing validation and call controls on stable backend codes without duplicating the AI trust boundary.
- Physical RayMe call listening remains a later acceptance/deployment gate; this plan intentionally did not redeploy OMEN.

## Self-Check: PASSED

- All eight modified implementation/test files and this summary exist.
- Commits `0e194b9`, `2f108e2`, `3c689cd`, and `69ce6c4` are present in git history.
- Both plan commands, the 20-test TTS registry suite, the 102-test VoxCPM2/live-call regression suite, and `git diff --check` passed.
- No runtime stubs, skipped tests, unrun verification commands, new trust-boundary surfaces outside the plan threat model, or unexpected deletions remain.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
