---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 13
subsystem: testing
tags: [qwen3-tts, omen, webrtc, deterministic-evidence, wavlm, cuda, privacy]

requires:
  - phase: 09-12
    provides: Frozen 20-scenario manifest, pinned WavLM scorer, and independent evidence verifier
  - phase: 09-11
    provides: Sample-bounded live playout, truthful terminal metrics, and request-scoped cancellation
provides:
  - Production RayMe acquisition runner for all 20 scenarios and the 50-turn hot-worker soak
  - Explicit release-only deterministic seed path with full RNG-state restoration
  - Split core acquisition and CUDA speaker/leak finishing lifecycle with fail-closed Qwen restoration
  - Sanitized, independently verifiable core and decision-artifact bundle
affects: [09-14, 09-15, omen-deployment, qwen3-release-evidence, physical-call-handoff]

actuals:
  tokens: 27740
  tasks: 2
  commits: 6

tech-stack:
  added: []
  patterns:
    - Paired release-evidence mode and uint32 seed across API, call session, adapter, and worker protocol
    - Request-scoped Python, NumPy, Torch, and CUDA RNG save/reset/restore
    - Core-first evidence acquisition followed by GPU-exclusive scoring and verified service restoration

key-files:
  created:
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py
  modified:
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py
    - ai-backend/app/api/webrtc.py
    - ai-backend/app/call/session.py
    - ai-backend/app/models/tts_qwen3.py
    - ai-backend/app/models/tts_qwen3_protocol.py
    - ai-backend/app/models/tts_qwen3_worker.py
    - ai-backend/app/models/tts_registry.py
    - ai-backend/tests/test_tts_qwen3.py
    - ai-backend/tests/test_webrtc_signaling.py

key-decisions:
  - "Deterministic generation is available only when an explicit Phase 09 release-evidence mode and bounded seed are paired on a phase09-evidence session and evidence turn."
  - "Evidence seeding saves and restores every Python, NumPy, Torch, and CUDA RNG state so ordinary calls never inherit or reuse the fixed evidence seed."
  - "Every anchor records the SHA-256 of its own captured WAV; any real mismatch stops evidence acquisition instead of copying a passing hash."
  - "Core acquisition and CUDA scoring are separate modes so Qwen can be unloaded for WavLM, then reloaded and prewarmed before readiness is reported."

patterns-established:
  - "Release-only controls: diagnostic determinism requires an explicit mode, a paired bounded value, and a dedicated session namespace."
  - "Fail-closed evidence: scorer or restore failure leaves runner state qwen_ready=false and emits no decision-ready claim."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "All twenty frozen scenarios dispatch through named RayMe production seams, with hash-bound fixture selection and no direct model-generation path."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "test_phase09_evidence.py -k 'runner or scenario or production_path' (16 passed)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Release evidence seeds propagate through WebRTC, CallSession, the Qwen adapter, protocol, and worker while ordinary calls remain unseeded."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "test_tts_qwen3.py and test_webrtc_signaling.py release-evidence tests (5 focused; 93 affected-suite tests passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Core and finish modes produce independently verifiable artifacts and restore the selected Qwen voice after pinned local CUDA scoring."
    requirement: REQ-46
    verification:
      - kind: integration
        ref: "test_phase09_evidence.py full suite (36 passed), verifier contracts PASS, verifier self-test 33/33 rejected"
        status: pass
    human_judgment: false
  - id: D4
    description: "Real browser and physical-call evidence remains pending for the final deployment/handoff plan."
    requirement: REQ-46
    verification: []
    human_judgment: true
    rationale: "Plan 13 deliberately builds the runner without deploying or conducting the user-facing OMEN call; Plan 15 must replace the explicit browser placeholder with real live evidence."

duration: 30min
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 13: Production OMEN Evidence Runner Summary

**Production-path 20-scenario and 50-turn evidence acquisition with release-only deterministic seeding, pinned CUDA scoring, privacy-safe artifacts, and fail-closed Qwen restoration**

## Performance

- **Duration:** 30 min
- **Started:** 2026-07-31T21:32:40Z
- **Completed:** 2026-07-31T22:02:19Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Built the production RayMe runner that selects only a hash-authorized Phase 005 fixture or the generated non-person fallback, dispatches the frozen scenarios, captures local WAV/STT/acoustic/stream scalars, and never imports the model runtime directly.
- Added an auditable deterministic-anchor path across WebRTC, CallSession, the Qwen adapter/protocol, and worker, with paired validation, uint32 bounds, dedicated evidence-session scoping, and full RNG-state restoration.
- Replaced fabricated anchor reuse with independent SHA-256 binding for every captured anchor; unequal reset-seed outputs now stop the run.
- Added core-only and finish modes that unload Qwen for pinned CUDA WavLM scoring, scan same-commit evidence/logs, reload Qwen, prewarm the selected saved voice, and leave a truthful readiness state.

## Task Commits

Each TDD task and the architectural repair were committed separately:

1. **Task 1 RED: Define production OMEN acquisition** - `2509a8d`
2. **Task 1 GREEN: Acquire production-path OMEN scenarios** - `987c546`
3. **Task 2 RED: Define split evidence lifecycle** - `ab2a454`
4. **Architectural RED: Define deterministic evidence seed contract** - `8d8b8fe`
5. **Architectural GREEN: Isolate deterministic release evidence seeds** - `f9b1962`
6. **Task 2 GREEN: Coordinate split OMEN evidence lifecycle** - `39f09d1`

## Files Created/Modified

- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py` - Production acquisition, artifact construction, CUDA scorer lifecycle, leak scan, and readiness restoration.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py` - Optional evidence-seed carrier that leaves ordinary tracer calls unchanged.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/test_phase09_evidence.py` - Fixture authorization, scenario dispatch, anchor integrity, and core/finish lifecycle contracts.
- `ai-backend/app/api/webrtc.py` - Explicit release-evidence request validation and scope enforcement.
- `ai-backend/app/call/session.py` - Seed propagation through the live streaming synthesis request.
- `ai-backend/app/models/tts_registry.py` - Paired evidence metadata on synthesis inputs.
- `ai-backend/app/models/tts_qwen3.py` - Adapter-to-worker propagation.
- `ai-backend/app/models/tts_qwen3_protocol.py` - Strict bounded worker command schema.
- `ai-backend/app/models/tts_qwen3_worker.py` - Scoped deterministic RNG reset and restoration.
- `ai-backend/tests/test_tts_qwen3.py` and `ai-backend/tests/test_webrtc_signaling.py` - Protocol, worker, API, propagation, and ordinary-call isolation regressions.

## Decisions Made

- Deterministic seeding is not a normal call option. It requires the exact `phase09_release_evidence` mode, a paired seed, a `phase09-evidence-*` session, and an `evidence-*` turn.
- Evidence generation restores the prior RNG states in `finally`, preserving the normal worker sampling stream even when evidence acquisition fails.
- The runner records real hashes and fails on non-identical anchors. It cannot self-certify a reset-seed gate by copying an earlier value.
- Local audio, transcripts, scorer embeddings, and paths stay under the uncommitted `.local` evidence directory; committed artifacts contain only opaque ids, hashes, and scalars.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 4 - Authorized Architectural Change] Added a production deterministic evidence-seed contract**
- **Found during:** Task 2 verification
- **Issue:** The independent verifier required bit-identical reset-seed anchors, but the production Qwen request/protocol/worker had no per-generation seed. The initial runner could only copy the first hash, which would fabricate evidence.
- **Fix:** After explicit parent authorization under the user's autonomous implementation instruction, added a narrowly scoped paired mode/seed contract, end-to-end propagation, RNG save/reset/restore, and actual per-WAV anchor comparison.
- **Files modified:** WebRTC API, CallSession, TTS registry, Qwen adapter/protocol/worker, hardware tracer, runner, and their tests.
- **Verification:** 5 focused seed/anchor tests, 93 Qwen/WebRTC tests, 63 CallSession tests, and 36 Plan 13 tests passed.
- **Committed in:** `8d8b8fe`, `f9b1962`

---

**Total deviations:** 1 authorized architectural repair
**Impact on plan:** The repair is required for truthful release evidence and is isolated from ordinary live-call sampling. No deployment or production evidence collection was added to this plan.

## Issues Encountered

- The host Python does not include pytest. Verification used the repository's existing `ai-backend/.venv`, without installing packages or changing dependencies.
- The production seed gap caused a blocking checkpoint. Work resumed only after explicit authorization to extend the minimum API/protocol/worker surface.

## Known Stubs

| File | Line | Stub | Reason |
|---|---:|---|---|
| `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py` | 967 | `_browser_placeholder` emits `awaiting_real_live_e2e` | Intentional Plan 13 boundary: Plan 15 must replace it with real browser and physical-call evidence after canonical deployment. |

## Threat Flags

| Flag | File | Description |
|---|---|---|
| threat_flag: release-evidence-seed-api | `ai-backend/app/api/webrtc.py` | The speak trust boundary accepts an evidence-only seed only when exact mode, bounded seed, dedicated session namespace, Qwen engine, and evidence turn namespace all match. |

## User Setup Required

None - no deployment, secrets, or external service configuration occurred in this plan.

## Next Phase Readiness

- Plan 14 can deploy the exact commit through `scripts/deploy-omen.sh` and invoke `--core-only`, then `--finish-acoustic-leak`.
- Plan 15 must run the real browser/live-call acceptance, replace the explicit placeholder artifact, and obtain the user's physical-call judgment.
- No OMEN deployment or production audio collection occurred during Plan 13.

## Self-Check: PASSED

All listed key files exist and all six task/deviation commits are present in git history.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
