---
phase: 00-measurement-gate
plan: "01"
subsystem: infra
tags: [python, torch, whisper, probes, cuda]
requires: []
provides:
  - "Phase 0 Python 3.11 backend venv on OMEN-PC"
  - "Pinned requirements-phase0.txt and shared probe utilities"
  - "Cached Whisper model weights and passing smoke test"
affects: [phase-00-measurements, phase-02-ai-backend, phase-04-call-feel]
tech-stack:
  added: [torch-cu118, faster-whisper, f5-tts, coqui-tts, qwen-tts]
  patterns: [repo-local probe scaffolding, OMEN-PC backend validation over SSH]
key-files:
  created:
    - .planning/phases/00-measurement-gate/requirements-phase0.txt
    - .planning/phases/00-measurement-gate/probes/bench_utils.py
    - .planning/phases/00-measurement-gate/probes/test_smoke.py
    - .planning/phases/00-measurement-gate/results/setup_install.json
  modified:
    - .planning/phases/00-measurement-gate/.gitignore
    - .planning/phases/00-measurement-gate/probes/conftest.py
    - .planning/phases/00-measurement-gate/probes/pytest.ini
key-decisions:
  - "Phase 0 backend runs in a dedicated Python 3.11 venv on OMEN-PC with torch 2.5.1+cu118."
  - "Shared measurement helpers live in bench_utils.py and stamp GPU/runtime metadata into every result."
patterns-established:
  - "Validate backend-only behavior over SSH on OMEN-PC rather than the local WSL shell."
  - "Persist setup outcomes in JSON before downstream probes rely on them."
requirements-completed: []
duration: 81 min
completed: 2026-04-22
---

# Phase 00 Plan 01: Wave 0 Setup Summary

**Python 3.11 Phase 0 measurement environment on OMEN-PC with pinned AI packages, cached Whisper weights, and passing smoke probes**

## Performance

- **Duration:** 81 min
- **Started:** 2026-04-22T15:00:30Z
- **Completed:** 2026-04-22T16:21:12Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments
- Created the Phase 0 probe package, pytest config, results directory, and pinned requirements file.
- Provisioned the OMEN-PC backend venv with CUDA-enabled torch and all Phase 0 AI packages.
- Cached all three Whisper checkpoints and validated the environment with a passing smoke test.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create probes package + requirements + gitignore scaffolding** - `e42c349` (feat)
2. **Task 2: Persist backend setup outcome and smoke probes** - `5a4a7bb` (feat)

**Plan metadata:** captured in the two task commits above.

## Files Created/Modified
- `.planning/phases/00-measurement-gate/requirements-phase0.txt` - Exact Phase 0 dependency set for the backend venv.
- `.planning/phases/00-measurement-gate/probes/bench_utils.py` - Shared GPU/timing/result helpers for every probe.
- `.planning/phases/00-measurement-gate/probes/test_smoke.py` - Smoke validation for torch CUDA + probe wiring.
- `.planning/phases/00-measurement-gate/results/setup_install.json` - Backend setup facts, installed versions, warnings, and smoke-test result.

## Decisions Made
- Used the CUDA 11.8 torch wheel family on OMEN-PC because the host exposes CUDA 11 tooling.
- Kept flash-attn out of plan 01 so FA2 remains an isolated measurement in plan 07.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `pip install -r requirements-phase0.txt` hit a transient `WinError 32` on `proto\__init__.py`; stopping leftover Python processes and rerunning resolved it cleanly.
- `qwen_tts` imported with warnings about missing SoX CLI and missing flash-attn; both were recorded instead of treated as blockers for setup.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plans `00-02` through `00-07.1` can use the shared probe environment and cached models directly.
- The backend host and SSH path are validated; future Phase 0 work must continue on OMEN-PC only.

---
*Phase: 00-measurement-gate*
*Completed: 2026-04-22*
