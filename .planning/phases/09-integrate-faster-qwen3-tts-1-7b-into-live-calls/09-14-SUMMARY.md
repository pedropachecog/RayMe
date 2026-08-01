---
phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls
plan: 14
subsystem: deployment
tags: [qwen3-tts, voice-cloning, omen, webrtc, cuda, streaming, stt, release-evidence]

requires:
  - phase: 09-13
    provides: Production 20-scenario and 50-turn acquisition runner with deterministic anchors and independent verification
provides:
  - Canonical exact-commit OMEN deployment and evidence orchestration for Faster Qwen3-TTS 1.7B
  - Production CUDA/WebRTC proof of early streaming, bounded backpressure, cancellation, recovery, and no whole-synthesis fallback
  - Independently verified 20-scenario and 50-turn runtime, call-flow, memory, and STT evidence bundle
  - OMEN runtime left with Qwen selected, resident, and its saved voice prompt ready
affects: [09-15, omen-deployment, live-call-handoff, qwen3-release-evidence]

actuals:
  tokens: 62341
  tasks: 2
  commits: 28

tech-stack:
  added:
    - faster-qwen3-tts 0.3.2 on pinned OMEN CUDA runtime
    - Qwen/Qwen3-TTS-12Hz-1.7B-Base revision fd4b254389122332181a7c3db7f27e918eec64e3
  patterns:
    - One canonical deploy flag owns provisioning, launchers, evidence acquisition, copy-back, independent verification, and ready-state restoration
    - Bounded four-step native Qwen streaming with a 1536-position static cache and 600 ms native median hard gate
    - Evidence capture preserves PCM representation before channel collapse and rejects private-data, fallback, and measurement corruption

key-files:
  created:
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-runtime.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-webrtc-status.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-call-flow.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-soak.json
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/results/qwen3-stt.json
  modified:
    - scripts/deploy-omen.sh
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-hardware-tracer.py
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py
    - .planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-verify-evidence.py
    - ai-backend/app/models/tts_qwen3_worker.py
    - web-ui/client/src/routes/call/[threadId]/+page.svelte

key-decisions:
  - "The final Qwen verification flag extends scripts/deploy-omen.sh; no alternate OMEN deployment, launcher, scheduled task, or evidence path is permitted."
  - "Live caller playback and sustained supply remain authoritative: keep the 1.25 second playback, per-sample RTFx, zero-underflow, and no-fallback gates while treating 500 ms native yield as a warning and 600 ms as the hard median bound."
  - "Four-step native streaming with a 1536-position static cache provides the demonstrated balance of first playback, sustained throughput, and RTX 3060 VRAM headroom."
  - "Physical-call and integrated human listening acceptance remain explicit Plan 09-15 work; automated core evidence cannot self-approve human audio judgment."

patterns-established:
  - "Exact deployment identity: every artifact records the deployed code SHA, model/runtime revisions, CUDA/Torch identity, and one-hot resident engine."
  - "Fail-closed production evidence: missing metrics, corrupted capture, private-data leaks, fallback use, late cancellation output, underflow, or degraded STT stop the deploy claim."

requirements-completed: [REQ-22, REQ-45, REQ-46]

coverage:
  - id: D1
    description: "The sole canonical deployment path provisions and verifies the exact Faster Qwen3-TTS 1.7B runtime, canonical launchers/tasks, deployed SHA, and restored prompt-ready state."
    requirement: REQ-22
    verification:
      - kind: integration
        ref: "RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh at 5e8a49c5179e4d38c55994625cd9ab18718e2962"
        status: pass
      - kind: unit
        ref: "test_phase09_evidence.py canonical deploy and evidence contracts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Production WebRTC calls begin playback before synthesis completion, remain bounded and interruptible, recover after cancellation/failure, and never use whole-synthesis fallback."
    requirement: REQ-45
    verification:
      - kind: integration
        ref: "results/qwen3-call-flow.json; 18 call-flow scenarios plus runtime and soak scenarios"
        status: pass
      - kind: e2e
        ref: "qwen3-readiness.spec.ts, voice-lab.spec.ts, call-start.spec.ts (66 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A 50-turn hot-worker soak proves stable playback, sustained real-time supply, flat Torch reserve, zero underflows, and intelligible late-call speech."
    requirement: REQ-46
    verification:
      - kind: integration
        ref: "09-verify-evidence.py --core-ready --expected-commit 5e8a49c5179e4d38c55994625cd9ab18718e2962"
        status: pass
      - kind: other
        ref: "results/qwen3-soak.json and results/qwen3-stt.json (50/50 turns accepted)"
        status: pass
    human_judgment: false

duration: 4h19m
completed: 2026-08-01
status: complete
---

# Phase 09 Plan 14: Canonical Qwen OMEN Evidence Summary

**Faster Qwen3-TTS 1.7B voice cloning deployed on OMEN with exact-commit CUDA/WebRTC proof, bounded live streaming, safe interruption, and a stable intelligible 50-turn soak**

## Performance

- **Duration:** 4h 19m
- **Started:** 2026-07-31T22:08:44Z
- **Completed:** 2026-08-01T02:27:55Z
- **Tasks:** 2
- **Files modified:** 36
- **Deployed implementation:** `5e8a49c5179e4d38c55994625cd9ab18718e2962`

## Accomplishments

- Extended `scripts/deploy-omen.sh` into the only final Qwen path: exact source/model/Torch/CUDA provisioning, canonical task/launcher assertions, WavLM cache materialization, hardware tracer, production core runner, named artifact copy-back, independent verification, and Qwen prompt-ready restoration.
- Passed all 20 frozen production scenarios. Short/medium/long clone paths stream early with caller playback at 798.3/918.6/1051.8 ms, no underflow, no fallback, and no whole-WAV synthesis; cancellation acknowledges within 75.8-125.6 ms with zero late audio, completion, or persistence.
- Passed the 50-turn hot-worker soak with 808.25 ms median first playback, RTFx minimum/median 1.129/1.348, zero underflows, flat 5702 MiB Torch reserve, and 8245.2 MiB measured system GPU use at runtime identity.
- Passed STT integrity with overall WER 0.004615, late WER 0, all 50 turns accepted with final words intact, and all names/numbers, negation/abbreviation, and punctuation/final-word hard phrases at WER 0.
- Left OMEN on the exact deployed implementation with `qwen3_1_7b` as the only resident TTS engine, model state resident, saved prompt ready, STT ready, and VAD ready.

## Task Commits

Task 1 TDD and canonical deploy ownership:

1. `9f56c79` - define canonical Qwen evidence deploy contract
2. `ac8ab42` - own final Qwen evidence deployment
3. `e70c4f3` - permit named live microphone evidence fixtures

Task 2 production repairs, exact deployment, and evidence:

1. `7c83f78` - send canonical Qwen voice authorization
2. `d8b206d` - keep call startup ahead of audio unlock
3. `03125f1` - measure Qwen worker allocator memory
4. `f5b99d5` - define slow-stream evidence target
5. `c9957f8`, `492f197` - control and source-bind deterministic soak anchors
6. `bd71e48` - meet Qwen live playout timing
7. `006109a`, `f374dc0`, `83a2bcf` - preserve real WebRTC capture PCM and channel semantics
8. `1fcd42e`, `6dfc83f` - sweep Qwen fidelity profiles and cover failing seeds
9. `1ae5d34` - normalize numeric ordinal evidence words
10. `126db7e`, `ae2741e`, `7e676cc`, `5e8a49c` - converge native chunking, cache capacity, latency, VRAM, and sustained throughput
11. `99dd24d` - record exact-commit sanitized OMEN core evidence

Resolved incident documentation was committed separately in `90c7c83`, `a1b2032`, `303ffad`, `8eb231c`, `02bb02a`, `14f6a37`, and `2797c37`.

## Files Created/Modified

- `scripts/deploy-omen.sh` - Canonical exact-commit Qwen provisioning, deployment, evidence, copy-back, verification, and restoration path.
- `09-run-hardware-tracer.py` - Authorized saved-voice request, real WebRTC PCM capture, early-stream/cancellation/recovery tracing, and allocator identity.
- `09-run-omen-evidence.py` - Production 20-scenario/50-turn runner, deterministic source-bound anchors, STT/acoustic evidence, and GPU memory collection.
- `09-verify-evidence.py` - Independent timing, throughput, integrity, privacy, memory, fallback, and ready-state gates.
- `ai-backend/app/models/tts_qwen3_worker.py` - Four-step native yields and bounded 1536-position static cache.
- `web-ui/client/src/routes/call/[threadId]/+page.svelte` - Best-effort audio unlock no longer blocks signaling or visible Qwen preparation failures.
- `results/qwen3-runtime.json` - Exact deployed runtime/model/CUDA/one-hot identity.
- `results/qwen3-webrtc-status.json` - Resident model, prompt readiness, output limits, and authorization state.
- `results/qwen3-call-flow.json` - Sanitized production call, backpressure, cancellation, hangup, recovery, and failure evidence.
- `results/qwen3-soak.json` and `results/qwen3-stt.json` - Fifty-turn stability, memory, timing, acoustic, and intelligibility evidence.

## Decisions Made

- Canonical deployment remains `scripts/deploy-omen.sh`; the evidence workflow was added to that script instead of creating a second deployment mechanism.
- The runtime keeps bounded startup buffering while preserving early playback before stream completion. A four-step native yield and 1536-position cache met caller latency, sustained RTFx, underflow, and VRAM gates together.
- Evidence capture identifies integer versus normalized PCM before channel collapse and collapses packed stereo into mono without duplicating time or destroying scale.
- The native first-chunk design target remains 500 ms, but the hard release median is 600 ms because caller playback under 1.25 seconds and sustained supply above RTFx 1.05 are the user-visible safety requirements.
- Generated non-person fixtures and opaque/hash-only evidence remain the release default; permitted reference audio and transcripts stay gitignored under `results/.local`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Completed the authorized saved-voice boundary**
- **Found during:** Task 2 first canonical deployment
- **Issue:** The hardware tracer nested authorization metadata but omitted the save API's required top-level steward, basis, and scope, producing HTTP 422.
- **Fix:** Sent all three canonical top-level fields without weakening hash-bound server validation; kept private inputs under `.local` and explicitly allowlisted only named synthetic fixtures.
- **Verification:** Payload regression, server authorization suite, hardware tracer, and final core verifier passed.
- **Committed in:** `e70c4f3`, `7c83f78`

**2. [Rule 1 - Bug] Prevented browser audio unlock from blocking call signaling**
- **Found during:** Task 2 predeployment browser gate
- **Issue:** `AudioContext.resume()` could remain pending without a user gesture, leaving direct call startup in Connecting before the Qwen preparation failure could render.
- **Fix:** Made audio unlock best-effort and non-blocking while keeping offer completion authoritative.
- **Verification:** Six focused Qwen failure repeats, twelve paired Qwen/ICE repeats, and the final 66-case desktop/mobile suite passed.
- **Committed in:** `d8b206d`

**3. [Rule 1 - Bug] Repaired production evidence identity and anchor measurements**
- **Found during:** Task 2 OMEN core acquisition
- **Issue:** Process-level GPU memory lookup could not identify the Qwen worker; the slow-stream target was absent; soak anchors were not yet bound to their actual deterministic source audio.
- **Fix:** Measured allocator memory inside the worker, defined the production slow-stream target, and bound every reset anchor to the Qwen source hash and seed lifecycle.
- **Verification:** Exact runtime identity, flat allocator memory, all 20 scenarios, and 50 deterministic source-bound turns passed.
- **Committed in:** `03125f1`, `f5b99d5`, `c9957f8`, `492f197`

**4. [Rule 1 - Bug] Repaired WebRTC evidence capture and semantic comparison**
- **Found during:** Task 2 independent STT verification
- **Issue:** Planar int16 audio was rescaled as normalized float, then packed stereo was flattened as mono, creating clipped or half-speed evidence even though Qwen/WebRTC output was valid. Numeric ordinals also caused a false final-token mismatch.
- **Fix:** Preserved integer scale, restored the capture consumer import, collapsed packed/planar channels correctly, and normalized numeric ordinal suffixes without weakening WER, named-term, number, negation, or final-word gates.
- **Verification:** Direct/captured waveform checks, fidelity sweeps, all three hard phrases at WER 0, 50/50 STT acceptance, and core verifier PASS.
- **Committed in:** `006109a`, `f374dc0`, `1fcd42e`, `6dfc83f`, `83a2bcf`, `1ae5d34`

**5. [Rule 1 - Performance Correctness] Balanced live latency, VRAM, and long-call supply**
- **Found during:** Task 2 exact-hardware timing and soak gates
- **Issue:** Successive configurations separately missed caller first-playback, native yield, Torch reserve, or sustained RTFx headroom.
- **Fix:** Converged on four-step native yields with a 1536-position cache, retained the 600 ms bounded startup target, and preserved early playback/no-whole-synthesis behavior.
- **Verification:** Native clone median 514.857 ms, maximum caller playback 1051.8 ms, 50-turn RTFx minimum/median 1.129/1.348, zero underflows, and flat 5702 MiB Torch reserve.
- **Committed in:** `bd71e48`, `126db7e`, `ae2741e`, `7e676cc`, `5e8a49c`

---

**Total deviations:** 5 auto-fixed groups (4 correctness bugs, 1 missing critical contract)
**Impact on plan:** Every repair was required to make live playback or release evidence truthful on the actual OMEN hardware. No alternate deployment path, CPU/model substitution, threshold waiver, whole-synthesis fallback, or private artifact was introduced.

## Issues Encountered

- Four canonical deploy attempts correctly stopped before a release claim when saved-voice authorization, GPU process memory, slow-stream targeting, or anchor source binding was invalid.
- Once source streaming was proven, the apparent STT degradation was traced to the evidence recorder's PCM scale and stereo layout rather than the Qwen engine. The capture path was repaired and revalidated before trusting quality results.
- Hardware tuning exposed real tradeoffs: two-step chunks met native latency but exceeded VRAM; three-step chunks met latency but lost sustained RTFx; four-step chunks plus the smaller cache passed all user-visible latency, throughput, memory, and intelligibility gates.

## Known Stubs

| File | Line | Stub | Reason |
|---|---:|---|---|
| `.planning/phases/09-integrate-faster-qwen3-tts-1-7b-into-live-calls/09-run-omen-evidence.py` | 1025 | `_browser_placeholder` emits `awaiting_real_live_e2e` | Intentional Plan 14 boundary: Plan 09-15 replaces it with real browser microphone and physical-call acceptance evidence. |

## User Setup Required

None - the canonical deployment completed autonomously. The next action is product-owner call testing, not infrastructure setup.

## Next Phase Readiness

- OMEN is running deployed implementation `5e8a49c5179e4d38c55994625cd9ab18718e2962` with Faster Qwen3-TTS 1.7B resident and the selected saved prompt ready.
- Plan 09-15 can use the existing `.local` permitted reference/fake microphone fixtures for real browser acquisition and then guide the user's physical RayMe call acceptance.
- Automated core release evidence is complete. Integrated human listening and physical-call judgment remain explicitly pending and must not be inferred from these automated results.

## Self-Check: PASSED

All named evidence and summary files exist, all 28 task/deviation/debug commits are present, the coverage contract classifies all three Plan 14 deliverables as automatically proven, the core verifier passes against deployed SHA `5e8a49c5179e4d38c55994625cd9ab18718e2962`, and `git diff --check` is clean.

---
*Phase: 09-integrate-faster-qwen3-tts-1-7b-into-live-calls*
*Completed: 2026-08-01*
