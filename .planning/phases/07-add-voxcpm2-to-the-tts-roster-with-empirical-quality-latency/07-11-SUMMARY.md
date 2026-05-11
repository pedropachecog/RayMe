---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 11
subsystem: evidence
tags: [voxcpm2, tts, scenario-matrix, call-flow, omen, live-evidence]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-07 Voice Lab VoxCPM2 controls and metadata payloads.
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-08 real call playback wiring for VoxCPM2 options.
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-09 scenario matrix and evidence schema support.
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-10 canonical OMEN VoxCPM2 CUDA runtime evidence.
provides:
  - Live VoxCPM2 and F5 scenario matrix JSON/CSV.
  - Generated WAV samples for VoxCPM2 and F5 comparison rows.
  - Live preview, Voice Library test-play, and call speak evidence through existing RayMe APIs.
  - Updated runtime smoke and VRAM soak evidence for the deployed call-flow runner commit.
affects: [phase-07, voxcpm2, tts, call-flow, omen-evidence, manual-quality]

tech-stack:
  added: []
  patterns: [live evidence artifact capture, sanitized call-flow probe, canonical OMEN redeploy before runtime evidence]

key-files:
  created:
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-call-flow.json
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/voxcpm2__call_flow_test_play.wav
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-11-SUMMARY.md
  modified:
    - .planning/phases/00-measurement-gate/probes/tts_scenario_matrix.py
    - ai-backend/app/models/tts_voxcpm2.py
    - ai-backend/tests/test_tts_voxcpm2.py
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.json
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.csv
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-runtime-smoke.json
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json

key-decisions:
  - "Live call-flow evidence uses existing Web UI `/api/voices/preview`, `/api/voices/{voice_id}/test-play`, AI backend `/webrtc/offer`, and `/webrtc/sessions/{session_id}/speak` APIs; no VoxCPM2-specific public route was added."
  - "OMEN evidence was refreshed only through `scripts/deploy-omen.sh` after the call-flow runner and `librosa.load` shim were pushed to GitHub main."
  - "VoxCPM2 preview, test-play, and call speak all passed with sanitized failure category `none`; manual quality scoring remains the next required gate."

patterns-established:
  - "Call-flow evidence records configured endpoint labels instead of raw LAN URLs."
  - "Generated call-flow audio is stored under the same `results/audio/` evidence package as scenario matrix samples."

requirements-completed: [REQ-02, REQ-20, REQ-21, REQ-23, REQ-41, REQ-42, REQ-45, REQ-62, REQ-A3]

duration: 2h
completed: 2026-05-11
---

# Phase 07 Plan 11: VoxCPM2 Live Matrix and Call-Flow Evidence Summary

**VoxCPM2 now has live scenario matrix, generated WAV, preview, test-play, and real call speak evidence saved under the Phase 07 evidence package.**

## Performance

- **Duration:** 2h including stalled executor recovery, OMEN redeploy, and live call-flow generation.
- **Completed:** 2026-05-11
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Generated live VoxCPM2 scenario matrix JSON/CSV with short, medium, and long rows plus F5 comparator rows.
- Saved VoxCPM2 and F5 generated WAV evidence under `results/audio/`, including the required `standard_python` VoxCPM2 and `optimized` F5 samples.
- Added `07-run-call-flow-evidence.py`, which exercises existing RayMe APIs for preview, test-play, WebRTC offer, call speak, interrupt, cleanup, and sanitized failure validation.
- Captured `results/voxcpm2-call-flow.json` with `preview_passed: true`, `test_play_passed: true`, `call_speak_passed: true`, `call_audio_enqueued: true`, `sanitized_failure_category: none`, and warm call TTFA metrics.
- Refreshed OMEN runtime smoke and VRAM evidence at deployed commit `dbc8ff119a619c265af5adc3c2106062af2466fb` through `scripts/deploy-omen.sh`.

## Task Commits

1. **Align live matrix runner with runtime behavior** - `4e8e451`, `6f8e12a`, `9175ae4`, `366cefb`
2. **Capture scenario matrix and WAV evidence** - `e883730`
3. **Shim missing runtime `librosa.load` dependency behavior** - `765c3aa`
4. **Add call-flow evidence runner** - `dbc8ff1`
5. **Capture live call-flow evidence** - `8b7bbf2`

## Files Created/Modified

- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py` - Live API evidence runner for preview, test-play, and call speak.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.json` - Live scenario metrics.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.csv` - CSV copy of live scenario metrics.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/` - Generated VoxCPM2 and F5 WAV samples, including call-flow test-play audio.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-call-flow.json` - Live preview/test-play/call speak evidence.
- `ai-backend/app/models/tts_voxcpm2.py` - Adds a soundfile-backed `librosa.load` shim for runtime environments where `librosa` imports without the expected loader.
- `ai-backend/tests/test_tts_voxcpm2.py` - Covers the runtime shim.

## Verification

- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --matrix-only` - PASS.
- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --runtime-only` - PASS.
- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --call-flow-only` - PASS.
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py -q` - PASS (`7 passed` after the shim addition).
- `git diff --check` - PASS.
- `RAYME_OMEN_VERIFY_VOXCPM2=1 ... scripts/deploy-omen.sh` - PASS, deployed `dbc8ff119a619c265af5adc3c2106062af2466fb`.
- `uv run --project ai-backend python .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-run-call-flow-evidence.py` - PASS, wrote `results/voxcpm2-call-flow.json`.

## Deviations from Plan

### Auto-fixed Issues

**1. Runtime `librosa.load` shim needed for live VoxCPM2 synthesis**
- **Found during:** Task 2 live call-flow evidence.
- **Issue:** The deployed VoxCPM2 runtime imported `librosa` without a callable `load`, causing preview synthesis to return sanitized `tts_failed`.
- **Fix:** Added a small soundfile-backed `librosa.load` shim before invoking the package runtime, with linear resampling for evidence/runtime compatibility.
- **Verification:** `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py -q` passed.
- **Committed in:** `765c3aa`

**2. Canonical redeploy required before call-flow evidence**
- **Found during:** Task 2 live preview.
- **Issue:** OMEN initially ran commit `366cefb`, which did not include the shim or call-flow runner.
- **Fix:** Pushed the two required commits to `origin/main` and redeployed through `scripts/deploy-omen.sh` with VoxCPM2 runtime verification enabled.
- **Verification:** Deploy completed at `dbc8ff119a619c265af5adc3c2106062af2466fb`; runtime and call-flow verifiers passed.

**3. Executor stalled after partial Task 1 completion**
- **Found during:** Orchestrator spot-check.
- **Issue:** The delegated executor made matrix commits and left uncommitted call-flow work, but did not produce `07-11-SUMMARY.md`.
- **Fix:** Orchestrator closed the stalled executor, completed the missing call-flow evidence, committed the evidence, and wrote this summary.

## Issues Encountered

- Live VoxCPM2 preview is slow relative to F5. The captured call-flow evidence recorded `preview_elapsed_ms: 24823.5`, `test_play_elapsed_ms: 3967.9`, and `warm_call_ttfa_ms: 13086.6`, compared with F5 short-row TTFA `946.9`.
- Runtime evidence remains within VRAM budget after the redeploy: peak VRAM `6941 MB` against budget `11264 MB`.

## Known Stubs

None. The call-flow runner uses live HTTPS APIs and writes evidence only after successful preview, test-play, and call speak.

## User Setup Required

Manual listening and scoring are still required in Plan 07-12 using the generated WAV files and `MANUAL-QUALITY.csv`.

## Threat Flags

None. Raw LAN URLs are not stored in call-flow evidence, runtime failures are sanitized, and the temporary evidence voice was force-deleted after capture.

## Next Phase Readiness

Plan 07-12 can now perform manual quality scoring and final promotion writeback using the saved matrix, runtime, call-flow, and WAV evidence.

## Self-Check: PASSED

- Verified required matrix JSON/CSV and WAV samples exist.
- Verified `results/voxcpm2-call-flow.json` passes the call-flow verifier.
- Verified task commits exist in git history.
- Verified no `## Self-Check: FAILED` marker applies to this plan.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
