---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
plan: 05
subsystem: omen-live-evidence
tags: [voxcpm2, omen, cuda, webrtc, evidence]

# Dependency graph
requires:
  - phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
    provides: Phase 8 streaming playback and public metric carriers from plans 08-01 through 08-04
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Phase 7 VoxCPM2 runtime and reference evidence context
provides:
  - Canonical OMEN deploy evidence for final Phase 8 live call-flow commit
  - CUDA-only VoxCPM2 runtime smoke and VRAM soak artifacts
  - Same-run repeated warm F5 versus VoxCPM2 live call-flow artifact
  - User-directed preservation record for pre-existing dirty OMEN checkout changes
affects: [phase-08-decision-writeback, voxcpm2-default-decision, omen-runtime-evidence]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - OMEN dirty checkout preservation branch before deployment
    - Live evidence runner records sanitized reference source labels only
    - Live evidence runner bounds WebRTC client cleanup so sample loops cannot hang

key-files:
  created:
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-OMEN-EVIDENCE.md
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-runtime-smoke.json
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-vram-soak.json
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-live-streaming-call-flow.json
  modified:
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py
    - .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_call_flow_runner.py

key-decisions:
  - "OMEN dirty Phase 07 evidence changes were preserved on branch preserve/phase08-omen-dirty-20260511T183300Z before deployment."
  - "Final Phase 8 live evidence runs against deployed commit 6b69aeb98434678f4aa1853953a710f8b9b0f905."
  - "VoxCPM2 beat F5 in same-run warm live call-flow evidence: 762.7 ms median versus F5 948.0 ms."
  - "Evidence JSON must not include absolute reference-audio paths; only stable source labels are allowed."

patterns-established:
  - "Preserve remote dirty work on a named branch with a recorded commit before canonical deployment."
  - "Call-flow evidence must be verifier-clean locally before decision writeback can proceed."

requirements-completed: [P8-R2, P8-R3, P8-R4]

# Metrics
duration: 33 min
completed: 2026-05-11
---

# Phase 08 Plan 05: OMEN Live Evidence Summary

**Canonical OMEN RTX 3060 evidence proves VoxCPM2 warm streaming call first-audio beats F5 in the same live run**

## Performance

- **Duration:** 33 min
- **Started:** 2026-05-11T18:32:15Z
- **Completed:** 2026-05-11T19:05:40Z
- **Tasks:** 3 completed
- **Files modified:** 6

## Accomplishments

- Preserved the pre-existing dirty OMEN checkout exactly as directed, on branch `preserve/phase08-omen-dirty-20260511T183300Z` commit `2077f8ddb7d50a6cca5f1d14ff26456a781f990a`, then reran the dirty preflight clean.
- Deployed only through `scripts/deploy-omen.sh`, with final runtime evidence at commit `6b69aeb98434678f4aa1853953a710f8b9b0f905`.
- Captured live repeated warm call-flow evidence where VoxCPM2 median first-audio was `762.7 ms` versus F5 `948.0 ms`, with `voxcpm2_beats_f5: true`.

## Task Commits

Each task was committed atomically or with focused auto-fix commits:

1. **Task 1: Preflight OMEN checkout cleanliness decision** - `10c3783` (docs)
2. **Task 2: Deploy to OMEN only through canonical script** - `522db24` (docs)
3. **Task 3 auto-fix: Bound call-flow peer cleanup** - `0cdfd82` (fix)
4. **Task 3 auto-fix: Sanitize call-flow reference source** - `6b69aeb` (fix)
5. **Task 3: Run live repeated warm VoxCPM2 versus F5 evidence** - `d58b19d` (docs)

## Files Created/Modified

- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-OMEN-EVIDENCE.md` - Human-readable record of dirty preflight, preservation branch, canonical deploys, live runner command, verifier output, and timing summary.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-runtime-smoke.json` - CUDA runtime smoke for `voxcpm==2.0.2`, `openbmb/VoxCPM2`, 48 kHz, `cpu_fallback_detected=false`.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-vram-soak.json` - RTX 3060 VRAM evidence with `6544 MB` peak, within the `11264 MB` budget.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/results/voxcpm2-live-streaming-call-flow.json` - Live same-run repeated warm F5/VoxCPM2 call-flow artifact.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py` - Bounded peer cleanup and sanitized reference source labels.
- `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_call_flow_runner.py` - Locks sanitized reference source behavior.

## Decisions Made

- Followed the user's `preserve` decision by committing the dirty OMEN changes on a durable preservation branch before switching back to `main`.
- Kept deployment and redeployment strictly inside `scripts/deploy-omen.sh`; no ad-hoc OMEN launchers, deployment scripts, or manual scheduled-task edits were used.
- Treated absolute reference-audio paths as evidence leaks and sanitized them in the runner before accepting live JSON.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Copied missing gitignored Phase 0 reference WAV to OMEN**
- **Found during:** Task 3 (Run live repeated warm VoxCPM2 versus F5 evidence)
- **Issue:** The runner's default Phase 0 reference WAV existed locally but was missing on OMEN, so the exact planned command failed before live calls.
- **Fix:** Copied `.planning/phases/00-measurement-gate/probes/fixtures/short_ref_audio.wav` to the same OMEN path and verified `git status --short` stayed clean because the WAV is gitignored.
- **Files modified:** OMEN-local ignored fixture only.
- **Verification:** The planned runner command advanced into live calls after the copy.
- **Committed in:** Documented in `d58b19d`.

**2. [Rule 1 - Bug] Bounded WebRTC client cleanup in the call-flow runner**
- **Found during:** Task 3 (Run live repeated warm VoxCPM2 versus F5 evidence)
- **Issue:** The runner completed the first F5 speak call but hung awaiting `RTCPeerConnection.close()`, preventing later samples.
- **Fix:** Added a 5-second timeout around peer close cleanup.
- **Files modified:** `08-run-call-flow-evidence.py`
- **Verification:** `python3 -m py_compile ...`, `python3 .../tests/test_08_call_flow_runner.py`, and the subsequent live runner progressed through VoxCPM2 samples.
- **Committed in:** `0cdfd82`

**3. [Rule 1 - Bug] Sanitized reference source labels in live evidence JSON**
- **Found during:** Task 3 (Run live repeated warm VoxCPM2 versus F5 evidence)
- **Issue:** The runner completed live calls but rejected its own payload because `reference_audio_source` exposed an absolute local path.
- **Fix:** Recorded `phase00-short-ref-fixture` or a filename-only label instead of absolute paths, and added a contract assertion.
- **Files modified:** `08-run-call-flow-evidence.py`, `tests/test_08_call_flow_runner.py`
- **Verification:** `python3 .../tests/test_08_call_flow_runner.py` and `python3 08-verify-evidence.py --call-flow-only` passed.
- **Committed in:** `6b69aeb`

---

**Total deviations:** 3 auto-fixed (1 blocking, 2 bugs).
**Impact on plan:** All fixes were required to produce truthful, verifier-clean live evidence. No deployment workaround was introduced.

## Issues Encountered

- Final OMEN AI/Web status remained `degraded` while required live-call readiness fields passed: `stt_ready=true`, `vad_ready=true`, resident TTS engine `f5`, CUDA VoxCPM2 runtime smoke passed, and call-flow evidence verified.
- The preservation branch is intentionally left on OMEN and was not pushed to origin; it remains a durable local OMEN branch/commit preserving the user's remote-only dirty work.

## Authentication Gates

None.

## Known Stubs

None. Stub-pattern scan only matched the deliberate `iceServers=[]` no-STUN aiortc configuration in the evidence runner.

## Verification

- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --call-flow-only` - PASS
- `rg -n "OMEN Dirty Checkout Preflight|scripts/deploy-omen.sh|voxcpm2_beats_f5|whole_wav_fallback_used" .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-OMEN-EVIDENCE.md` - PASS
- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_call_flow_runner.py` - PASS
- `python3 -m py_compile .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py` - PASS
- `git diff --check` - PASS

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 08-06 can perform decision writeback using `results/voxcpm2-live-streaming-call-flow.json`, `results/voxcpm2-runtime-smoke.json`, and `results/voxcpm2-vram-soak.json`. The live evidence gate now passes and proves VoxCPM2 warm streaming first-audio beats F5 in the same run without fallback.

## Self-Check: PASSED

- Summary, evidence log, runtime smoke, VRAM soak, live call-flow JSON, runner, and runner test files exist.
- Task commits `10c3783`, `522db24`, `0cdfd82`, `6b69aeb`, and `d58b19d` exist in git history.
- `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --call-flow-only` still passes.

---
*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Completed: 2026-05-11*
