---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 04
subsystem: ai-runtime
tags: [qwen3-tts, omen, cuda, webrtc, voice-cloning, hardware-tracer]

requires:
  - phase: 09-03
    provides: Responsive Qwen readiness, strict saved-voice WebRTC contracts, bounded live streaming, and request-scoped cancellation
provides:
  - Canonical OMEN provisioning for the exact Faster Qwen3-TTS source, immutable 1.7B snapshot, and CUDA runtime
  - Hash-bound real-person reference authorization with deterministic non-person SAPI fallback
  - Commit-matched real saved-voice/WebRTC evidence for early playback, bounded backpressure, cancellation, and recovery
affects: [09-05, 09-06, 09-07, qwen3-deployment, live-calls, release-evidence]

actuals:
  tokens: 22697
  tasks: 2
  commits: 9

tech-stack:
  added: [faster-qwen3-tts-0.3.2, Qwen3-TTS-12Hz-1.7B-Base]
  patterns: [canonical-commit-pinned-deploy, hash-bound-reference-authorization, deterministic-non-person-fallback, commit-matched-hardware-tracer, cuda-before-control-reader]

key-files:
  created:
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-hardware-tracer.json
  modified:
    - scripts/deploy-omen.sh
    - ai-backend/app/models/tts_qwen3.py
    - ai-backend/app/models/tts_qwen3_worker.py
    - ai-backend/tests/test_tts_qwen3.py

key-decisions:
  - "Canonical deploy alone installs source commit a70afc0f81f7f5f8801c3227968f1102f43f211c, materializes model revision fd4b254389122332181a7c3db7f27e918eec64e3, reasserts Torch 2.10.0+cu126, and passes only the verified local model path to RayMe."
  - "A real-person reference is eligible only with matching steward, authorization basis, LAN-test scope, reference hash, and transcript hash; every invalid case automatically selects deterministic Microsoft David SAPI audio."
  - "On Windows, Qwen IPC uses console Python and performs the mandatory CUDA load/graph capture on the worker main thread before starting the cancellation reader."

patterns-established:
  - "Deployment evidence is accepted only when origin, OMEN checkout, runtime identity, status identity, and tracer payload all name the same intended implementation commit."
  - "The hardware tracer uses production voice upload/save, ModelManager preparation, CallSession, and WebRTC capture; model-only generation cannot satisfy the gate."
  - "Synthetic reference and fake-microphone bytes remain local and temporary copies are deleted after upload; committed evidence contains only opaque ids, hashes, and scalar control/runtime data."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "The canonical OMEN path provisions and attests the exact Faster Qwen3-TTS source, immutable 1.7B snapshot, CUDA/Torch build, RTX 3060, one-hot residency, and authorized saved-voice reference."
    requirement: REQ-22
    verification:
      - kind: e2e
        ref: "RAYME_OMEN_VERIFY_QWEN3_TRACER=1 scripts/deploy-omen.sh at deployed commit e9923925e55d7d2f71929372d9186df46aacaa6d"
        status: pass
      - kind: unit
        ref: "09-run-hardware-tracer.py --self-test-reference-authorization"
        status: pass
    human_judgment: false
  - id: D2
    description: "Real saved-voice Qwen audio reaches WebRTC before synthesis completion for short, medium, and long turns through a capacity-two bridge without whole-synthesis fallback."
    requirement: REQ-45
    verification:
      - kind: e2e
        ref: "results/qwen3-hardware-tracer.json normal_streams: all first_before_completion=true, bridge_queue_high_water=1, whole_wav_fallback_used=false"
        status: pass
      - kind: integration
        ref: "Qwen/model-manager/call/WebRTC/Vox regression command (148 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A real Qwen turn cancels after first audio in under two seconds with no late nonzero audio or normal completion, then a recovery turn produces fresh audio."
    requirement: REQ-46
    verification:
      - kind: e2e
        ref: "results/qwen3-hardware-tracer.json cancellation: 144.4 ms acknowledgement, zero post-cancel frames, zero ai_done, recovery passed"
        status: pass
      - kind: integration
        ref: "Qwen/model-manager/call/WebRTC/Vox regression command (148 passed)"
        status: pass
    human_judgment: false

duration: 1h 14m
completed: 2026-07-31
status: complete
---

# Phase 09 Plan 04: Qwen Hardware Tracer Summary

**RayMe now deploys the pinned Qwen3-TTS 1.7B runtime canonically and proves real saved-voice early WebRTC playback, bounded streaming, clean interruption, and recovery on OMEN.**

## Performance

- **Duration:** 1h 14m
- **Started:** 2026-07-31T16:26:08Z
- **Completed:** 2026-07-31T17:40:25Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Extended only `scripts/deploy-omen.sh` to install the approved source commit, materialize the immutable 1.7B snapshot, reassert CUDA Torch, write the canonical launcher environment, and invoke/copy back hardware evidence.
- Added a privacy-preserving tracer that validates hash-bound real-person authorization before opening reference bytes, automatically uses deterministic Microsoft David SAPI for every invalid case, and exercises production voice upload/save and WebRTC.
- Proved one resident Qwen engine and separately observed `loading -> resident` plus `prewarming -> ready` on exact deployed commit `e9923925e55d7d2f71929372d9186df46aacaa6d`.
- Proved first remote audio before synthesis response completion for short, medium, and long turns; every bridge high-water was 1 of capacity 2 and every whole-WAV fallback flag was false.
- Proved interruption acknowledgement in 144.4 ms with zero late nonzero frames, zero normal `ai_done`, no forced backend termination, and a successful fresh recovery turn.

## Task Commits

Each task and directly discovered correction was committed atomically:

1. **Task 1 RED: Define tracer authorization contracts** - `55919b7` (test)
2. **Task 1 GREEN: Provision and trace pinned Qwen hardware** - `c822403` (feat)
3. **Task 2 observability: Preserve sanitized tracer diagnostics** - `98e3e59` (fix)
4. **Task 2 fixture: Select deterministic SAPI voice by token name** - `274d1d7` (fix)
5. **Task 2 fixture: Use the SAPI voice native PCM format** - `732858b` (fix)
6. **Task 2 runtime: Attest pinned nested CUDA parameters** - `19ba138` (fix)
7. **Task 2 runtime: Launch Qwen IPC with console Python** - `fadf217` (fix)
8. **Task 2 runtime: Initialize Qwen CUDA before cancel reader** - `e992392` (fix)
9. **Task 2 evidence: Record real Qwen hardware tracer** - `50f44ed` (test)

## Files Created/Modified

- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py` - Authorization preflight, deterministic SAPI fixtures, production saved-voice/WebRTC runner, evidence validation, and sanitized CLI failures.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/.gitignore` - Keeps local fixtures/audio private while allowing the single committed JSON result.
- `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-hardware-tracer.json` - Commit-matched opaque/scalar hard-gate evidence.
- `scripts/deploy-omen.sh` - Exact Qwen source/model/CUDA provisioning, canonical launcher variables, tracer invocation, and result copy-back.
- `ai-backend/app/models/tts_qwen3.py` - Windows console-interpreter selection for reliable worker IPC.
- `ai-backend/app/models/tts_qwen3_worker.py` - Exact nested CUDA attestation and main-thread CUDA initialization before cancellation-reader startup.
- `ai-backend/tests/test_tts_qwen3.py` - Pinned wrapper depth, non-CUDA rejection, Windows interpreter, and startup-order regressions.

## Decisions Made

- The canonical deployment script owns source/model installation and identity checks; no alternate OMEN script, launcher, task, endpoint, or manual service path was created.
- The deterministic non-person reference is the default unless all five authorization/provenance fields and both exact file hashes validate before upload.
- CUDA parameters are checked at the pinned runtime's actual `runtime.model.model` depth and every discovered parameter must be CUDA-resident.
- The first load command runs before the background cancellation reader. The reader still starts before prewarm/generation, preserving request-scoped interruption while avoiding the Windows CUDA initialization deadlock.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved the tracer's sanitized failure reason through PowerShell**
- **Found during:** Task 2 canonical deploy
- **Issue:** PowerShell treated Python stderr as a terminating native-command error and hid the useful tracer failure.
- **Fix:** Converted tracer failures to one-line sanitized output and captured the process result without allowing native stderr policy to mask it.
- **Files modified:** `scripts/deploy-omen.sh`, `09-run-hardware-tracer.py`
- **Verification:** Later canonical failures reported their exact sanitized gate reason.
- **Committed in:** `98e3e59`

**2. [Rule 1 - Bug] Matched Microsoft David by stable SAPI token name**
- **Found during:** Task 2 deterministic fallback generation
- **Issue:** OMEN localizes the visible description with a language suffix, so exact description matching found no voice.
- **Fix:** Selected the exact `Microsoft David Desktop` token `Name` attribute.
- **Files modified:** `09-run-hardware-tracer.py`
- **Verification:** OMEN resolved the intended David token.
- **Committed in:** `274d1d7`

**3. [Rule 1 - Bug] Removed an unsupported forced SAPI format**
- **Found during:** Task 2 deterministic fallback generation
- **Issue:** David rejected the forced 24 kHz stream with `SPERR_UNSUPPORTED_FORMAT`.
- **Fix:** Generated deterministic native PCM WAV and let RayMe's saved-voice path perform normal resampling.
- **Files modified:** `09-run-hardware-tracer.py`
- **Verification:** The canonical tracer generated, uploaded, saved, and used the synthetic reference.
- **Committed in:** `732858b`

**4. [Rule 1 - Bug] Attested CUDA at the pinned runtime's actual model depth**
- **Found during:** Task 2 Qwen preparation
- **Issue:** The adapter checked only two wrapper levels and rejected a valid CUDA model stored at `runtime.model.model`.
- **Fix:** Inspected the exact nested module and rejected any discovered non-CUDA parameter.
- **Files modified:** `ai-backend/app/models/tts_qwen3_worker.py`, `ai-backend/tests/test_tts_qwen3.py`
- **Verification:** Focused real runtime load plus the 39-test Qwen suite passed.
- **Committed in:** `19ba138`

**5. [Rule 2 - Missing Critical] Used console Python for worker IPC under the scheduled pythonw backend**
- **Found during:** Task 2 Qwen preparation
- **Issue:** A child inheriting `pythonw.exe` cannot provide the standard streams required by the validated IPC protocol.
- **Fix:** Resolve the sibling `python.exe` and fail closed when it is unavailable.
- **Files modified:** `ai-backend/app/models/tts_qwen3.py`, `ai-backend/tests/test_tts_qwen3.py`
- **Verification:** Windows interpreter regression and the real OMEN worker handshake passed.
- **Committed in:** `fadf217`

**6. [Rule 1 - Bug] Loaded CUDA before starting the persistent cancellation reader**
- **Found during:** Task 2 Qwen preparation
- **Issue:** On OMEN, CUDA initialization stalled when the worker's daemon stdin reader was already active.
- **Fix:** Read and dispatch the mandatory first load command on the main thread, then start the reader before prewarm/generation so cancellation remains live.
- **Files modified:** `ai-backend/app/models/tts_qwen3_worker.py`, `ai-backend/tests/test_tts_qwen3.py`
- **Verification:** Exact canonical deploy passed full load, prewarm, three normal streams, cancellation, and recovery.
- **Committed in:** `e992392`

---

**Total deviations:** 6 auto-fixed (5 bugs, 1 missing critical IPC requirement).
**Impact on plan:** Every correction was required for the planned deterministic fixture or real Windows/CUDA worker path; no alternate deployment or non-live fallback was introduced.

## Issues Encountered

- Early canonical runs failed at deterministic fixture creation and then at the real runtime boundary. Each failure remained a hard stop; no evidence was fabricated and no gate was weakened.
- The successful deployment produced the result only after exact origin/OMEN commit equality, runtime/model/CUDA attestation, and the complete production call sequence passed.

## User Setup Required

None - OMEN is provisioned through the canonical script and the deployed RayMe services are running. Physical-call listening remains a later explicit acceptance gate, not setup for this plan.

## Next Phase Readiness

- Plan 09-05 and later integration/evaluation work may proceed from the passed hard-gate artifact.
- The deployed OMEN implementation is `e9923925e55d7d2f71929372d9186df46aacaa6d`; the local evidence commit `50f44ed` records that deployment without changing it.
- Automated proof covers runtime identity and call mechanics. Final perceived likeness/naturalness on a physical call remains intentionally pending for the later human listening plan.

## Self-Check: PASSED

- All seven created/modified implementation, test, deploy, tracer, and evidence files plus this summary exist.
- Commits `55919b7`, `c822403`, `98e3e59`, `274d1d7`, `732858b`, `19ba138`, `fadf217`, `e992392`, and `50f44ed` are present in git history.
- The commit-matched hardware evidence verifier, canonical deployment hard gate, dependency-lock checks, authorization self-test, and 148-test regression suite all passed.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-07-31*
