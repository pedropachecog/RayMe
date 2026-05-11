---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 10
subsystem: infra
tags: [omen, deployment, voxcpm2, cuda, runtime-evidence]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-05 CUDA-only VoxCPM2 adapter and optional `voxcpm==2.0.2` runtime dependency
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: Plan 07-09 runtime evidence verifier and JSON contracts
provides:
  - Canonical OMEN deploy support for opt-in VoxCPM2 runtime verification
  - Live RTX 3060 VoxCPM2 package/model/CUDA/sample-rate evidence
  - Live VRAM soak artifact showing VoxCPM2 stayed under the 11 GB budget
  - Runtime adapter compatibility fix for actual `voxcpm==2.0.2` loader behavior
affects: [phase-07, omen-deploy, ai-backend-tts-runtime, voxcpm2-evidence]

tech-stack:
  added: []
  patterns: [canonical deploy evidence gate, repo-local uv bootstrap, CUDA torch repair after optional TTS sync]

key-files:
  created:
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-runtime-smoke.json
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-10-SUMMARY.md
  modified:
    - scripts/deploy-omen.sh
    - ai-backend/app/models/tts_voxcpm2.py
    - ai-backend/tests/test_tts_voxcpm2.py
    - .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-OMEN-EVIDENCE.md

key-decisions:
  - "VoxCPM2 OMEN verification remains inside `scripts/deploy-omen.sh`; no alternate OMEN deployment script or scheduled-task workaround was created."
  - "`voxcpm==2.0.2` does not accept the documented `device=\"cuda\"` kwarg; RayMe loads with the package's actual API and verifies CUDA residency after load."
  - "OMEN optional TTS sync must force Python 3.11 and repair CUDA PyTorch wheels after `uv sync`, because the default sync path installs CPU torch."

patterns-established:
  - "Verified OMEN deploys can emit machine-readable local evidence through stdout JSON markers without writing helper scripts on OMEN."
  - "VoxCPM2 runtime acceptance checks CUDA by loaded model parameter device, not by trusting package defaults."

requirements-completed: [REQ-02, REQ-45, REQ-A3]

duration: 31min
completed: 2026-05-11
---

# Phase 07 Plan 10: VoxCPM2 OMEN Runtime Evidence Summary

**Canonical OMEN deploy now captures live VoxCPM2 CUDA runtime, 48 kHz sample-rate, and RTX 3060 VRAM evidence.**

## Performance

- **Duration:** 31 min
- **Started:** 2026-05-11T03:43:05Z
- **Completed:** 2026-05-11T04:14:11Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Extended `scripts/deploy-omen.sh` with `RAYME_OMEN_VERIFY_VOXCPM2=1`, local JSON evidence extraction, repo-local `uv` bootstrap, Python 3.11 sync selection, CUDA torch repair, and CPU fallback rejection.
- Ran the canonical deploy against `ssh rayme-pmpg`; deployed commit `39f1afaec30b160ac2160d5ffdf8723e21f594f5` on OMEN through the scheduled task launchers.
- Saved `results/voxcpm2-runtime-smoke.json` with `voxcpm==2.0.2`, `openbmb/VoxCPM2`, `device: cuda`, `sample_rate: 48000`, CUDA torch `2.10.0+cu126`, and model cache path.
- Saved `results/voxcpm2-vram-soak.json` showing peak observed VRAM `6334 MB`, budget `11264 MB`, `passed_11gb_budget: true`, and `cpu_fallback_detected: false`.
- Fixed the backend VoxCPM2 adapter to match the actual package API and verify CUDA residency after load.

## Task Commits

Each task was committed atomically, with additional Rule 1-3 fix commits required during live OMEN verification:

1. **Task 1: Add optional VoxCPM2 runtime verification to `deploy-omen.sh`** - `a090cd0` (feat)
2. **Rule 3 fix: avoid hanging verified deploy capture** - `d15723c` (fix)
3. **Rule 3 fix: pass verification env over SSH** - `0f329cc` (fix)
4. **Rule 3 fix: bootstrap repo-local uv on OMEN** - `86b462e` (fix)
5. **Rule 3 fix: return only uv path from bootstrap** - `46eb223` (fix)
6. **Rule 3 fix: stop services before `uv sync`** - `418bcb7` (fix)
7. **Rule 3 fix: converge OMEN sync onto Python 3.11** - `3fd6539`, `1f997a0` (fix)
8. **Rule 2 fix: restore CUDA torch after optional TTS sync** - `6723d27`, `1b5b5df` (fix)
9. **Rule 1 fix: load VoxCPM2 with actual package API** - `39f1afa` (fix)
10. **Task 2: Run OMEN deploy/runtime smoke and save evidence** - `7a3dd83` (feat)

## Files Created/Modified

- `scripts/deploy-omen.sh` - Adds opt-in VoxCPM2 verification, JSON marker extraction, uv bootstrap, Python 3.11 sync, CUDA torch repair, and dirty-checkout refusal.
- `ai-backend/app/models/tts_voxcpm2.py` - Loads `voxcpm==2.0.2` through the actual API and rejects non-CUDA runtime residency.
- `ai-backend/tests/test_tts_voxcpm2.py` - Updates adapter contract coverage for CUDA guard plus actual loader signature.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-OMEN-EVIDENCE.md` - Records exact command, commit, package/model/cache/sample-rate/CUDA/VRAM evidence.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-runtime-smoke.json` - Machine-readable OMEN runtime smoke evidence.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json` - Machine-readable RTX 3060 VRAM budget evidence.

## Verification

- `bash -n scripts/deploy-omen.sh` - PASS.
- Required script grep for `RAYME_OMEN_VERIFY_VOXCPM2`, `voxcpm==2.0.2`, `openbmb/VoxCPM2`, `device="cuda"`, and `rayme-pmpg` - PASS.
- `ssh rayme-pmpg whoami` - PASS (`omen-pc\pmpg`).
- `RAYME_OMEN_VERIFY_VOXCPM2=1 ... scripts/deploy-omen.sh` - PASS, deployed `39f1afaec30b160ac2160d5ffdf8723e21f594f5`.
- `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --runtime-only` - PASS.
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py -q` - PASS (`29 passed`, one pre-existing torch/pynvml warning).
- `git diff --check` on touched files - PASS.

## Decisions Made

- Kept all OMEN deployment behavior in `scripts/deploy-omen.sh` and used only scheduled task launchers created by that script.
- Refused dirty OMEN checkouts instead of running blanket `git checkout -- .` or `git clean -fd`.
- Treated `device="cuda"` as the runtime contract, but not as a literal loader kwarg, because live `voxcpm==2.0.2` rejects that kwarg. CUDA is verified by PyTorch CUDA availability plus loaded parameter device.
- Installed the repo-local `uv` bootstrap under `.local/uv-bootstrap` on OMEN when `uv` is absent from PATH; `.local/` is gitignored.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed verified deploy output capture hang**
- **Found during:** Task 2 live deploy.
- **Issue:** Piping the SSH heredoc invocation through `tee` left the remote PowerShell invocation stuck before useful output.
- **Fix:** Captured deploy output to a temp file, printed it after completion, and parsed JSON markers from that file.
- **Files modified:** `scripts/deploy-omen.sh`
- **Verification:** `bash -n scripts/deploy-omen.sh`
- **Committed in:** `d15723c`

**2. [Rule 3 - Blocking] Passed deploy verification settings over SSH explicitly**
- **Found during:** Task 2 live deploy.
- **Issue:** Local environment variables were not inherited by remote OpenSSH PowerShell, so `RAYME_OMEN_VERIFY_VOXCPM2=1` was not seen on OMEN.
- **Fix:** Injected expected commit, repo path, branch, and verification flag into the remote PowerShell bootstrap command.
- **Files modified:** `scripts/deploy-omen.sh`
- **Verification:** Subsequent deploy entered the VoxCPM2 verification block.
- **Committed in:** `0f329cc`

**3. [Rule 3 - Blocking] Bootstrapped `uv` for OMEN PowerShell**
- **Found during:** Task 2 live deploy.
- **Issue:** OMEN PowerShell did not have `uv` on PATH, blocking the required `uv sync --project ai-backend --extra tts`.
- **Fix:** Added a repo-local `.local/uv-bootstrap` venv and resolved `uv.exe` from there when PATH lookup fails.
- **Files modified:** `scripts/deploy-omen.sh`
- **Verification:** OMEN installed and used `uv==0.11.6`.
- **Committed in:** `86b462e`, `46eb223`

**4. [Rule 3 - Blocking] Freed the AI backend venv before dependency sync**
- **Found during:** Task 2 live deploy.
- **Issue:** Running services locked `ai-backend\.venv`, causing `uv sync` to fail with access denied.
- **Fix:** Reused canonical port-owner stop logic before the optional VoxCPM2 sync.
- **Files modified:** `scripts/deploy-omen.sh`
- **Verification:** Later `uv sync` proceeded past venv removal/recreation.
- **Committed in:** `418bcb7`

**5. [Rule 3 - Blocking] Forced a compatible Python for OMEN sync**
- **Found during:** Task 2 live deploy.
- **Issue:** `uv sync` first chose Python 3.14, causing a `kaldifst` source build failure; forcing system Python 3.10 then violated `requires-python >=3.11`.
- **Fix:** Set `UV_PYTHON=3.11` and invoked `uv sync --python 3.11`.
- **Files modified:** `scripts/deploy-omen.sh`
- **Verification:** OMEN provisioned CPython 3.11.15 and installed the optional TTS dependency set.
- **Committed in:** `3fd6539`, `1f997a0`

**6. [Rule 2 - Missing Critical] Restored CUDA torch after optional TTS sync**
- **Found during:** Task 2 live deploy.
- **Issue:** Windows `uv sync --extra tts` installed CPU-only `torch==2.11.0`, which would create a false CPU fallback acceptance.
- **Fix:** Reinstalled `torch==2.10.0+cu126` and `torchaudio==2.10.0+cu126` from the CUDA 12.6 PyTorch wheel index after sync, then ran the probe through venv Python to avoid `uv run` re-syncing CPU wheels.
- **Files modified:** `scripts/deploy-omen.sh`
- **Verification:** deploy log reported CUDA torch `2.10.0+cu126`, CUDA `12.6`, RTX 3060; runtime JSON has `cpu_fallback_detected: false`.
- **Committed in:** `6723d27`, `1b5b5df`

**7. [Rule 1 - Bug] Fixed VoxCPM2 loader API mismatch**
- **Found during:** Task 2 live deploy.
- **Issue:** Live `voxcpm==2.0.2` rejects `VoxCPM.from_pretrained(..., device="cuda")` even though planning docs referenced that form; the backend adapter would fail on OMEN.
- **Fix:** Loaded with `VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)` and added CUDA residency verification after load in both the adapter and deploy probe.
- **Files modified:** `ai-backend/app/models/tts_voxcpm2.py`, `ai-backend/tests/test_tts_voxcpm2.py`, `scripts/deploy-omen.sh`
- **Verification:** backend TTS/model-manager tests passed; live OMEN runtime probe loaded VoxCPM2 on CUDA.
- **Committed in:** `39f1afa`

---

**Total deviations:** 7 auto-fixed (1 bug, 1 missing critical runtime guard, 5 blocking issues).
**Impact on plan:** All fixes were required to make the canonical deploy path truthful and executable on OMEN. No alternate deployment script, manual scheduled-task workaround, CPU fallback, or committed model/cache file was introduced.

## Issues Encountered

- Live `voxcpm==2.0.2` does not accept the documented `device="cuda"` kwarg; this is now recorded in evidence and guarded by actual CUDA parameter inspection.
- `uv sync --extra tts` on OMEN mutates the AI backend environment and defaults to CPU torch unless repaired; the deploy script now applies the CUDA wheel repair automatically.
- The AI backend health after deploy is still `degraded` while STT/VAD are ready and F5 is resident, matching the current Phase 07 candidate state rather than a VoxCPM2 promotion claim.

## Known Stubs

None. Stub scan found only local empty lists in implementation/tests and an empty transcript test case; no UI or runtime path is stubbed for this plan.

## Threat Flags

None. The new deployment/runtime trust boundary was already in the plan threat model, and the implementation records package/model/cache/CUDA/VRAM evidence while rejecting CPU fallback.

## User Setup Required

None - no manual OMEN action was required. The deploy script created `.local/uv-bootstrap` inside the canonical OMEN checkout as ignored runtime tooling, and VoxCPM2 model cache files remain outside git under `C:\Users\pmpg\.cache\huggingface\...`.

## Next Phase Readiness

Plan 07-11 can use the saved runtime smoke and VRAM JSON as the runtime prerequisite for live matrix and call-flow evidence. VoxCPM2 is not promoted by this plan; it is proven loadable on CUDA within VRAM budget, with synthesis/call-flow quality still pending.

## Self-Check: PASSED

- Verified created files exist: `results/voxcpm2-runtime-smoke.json`, `results/voxcpm2-vram-soak.json`, and this summary.
- Verified task/fix commits exist in git history: `a090cd0`, `d15723c`, `0f329cc`, `86b462e`, `46eb223`, `418bcb7`, `3fd6539`, `1f997a0`, `6723d27`, `1b5b5df`, `39f1afa`, and `7a3dd83`.
- Verified runtime evidence contract with `07-verify-evidence.py --runtime-only`.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
