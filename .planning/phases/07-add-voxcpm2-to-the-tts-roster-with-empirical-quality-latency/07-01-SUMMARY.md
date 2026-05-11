---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 01
subsystem: testing
tags: [ai-backend, tts, voxcpm2, pytest, red-contracts]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: Metadata-driven TTS registry, one-hot model manager residency, and transient /tts/synthesize route
provides:
  - VoxCPM2 backend roster metadata RED contracts
  - VoxCPM2 one-hot residency and sanitized unavailable-state RED contracts
  - VoxCPM2 adapter CUDA, cloning-mode, 48 kHz, and option-mapping RED contracts
affects: [phase-07-voxcpm2-runtime, ai-backend-tts-registry, ai-backend-model-manager]

tech-stack:
  added: []
  patterns: [pytest contract tests, import-gated runtime adapter tests, sanitized public error assertions]

key-files:
  created:
    - ai-backend/tests/test_tts_voxcpm2.py
  modified:
    - ai-backend/tests/test_tts_registry.py
    - ai-backend/tests/test_model_manager.py

key-decisions:
  - "VoxCPM2 RED contracts require metadata visibility before runtime promotion."
  - "VoxCPM2 runtime contracts require CUDA-only loading with voxcpm==2.0.2 and model id openbmb/VoxCPM2."
  - "VoxCPM2 failures must be engine-scoped and sanitized without traceback, local path, or model-id disclosure."

patterns-established:
  - "VoxCPM2 adapter tests use fake runtimes and package shims only; they do not download models."
  - "Backend synthesis option tests require bounded VoxCPM2 fields to flow through TtsSynthesisInput."

requirements-completed: [REQ-02, REQ-22, REQ-45, REQ-80, REQ-A3]

duration: 6min
completed: 2026-05-11
---

# Phase 07 Plan 01: VoxCPM2 Backend RED Contracts Summary

**Executable VoxCPM2 backend contracts now lock metadata visibility, CUDA-only optional runtime loading, one-hot degradation, 48 kHz output, cloning-mode behavior, bounded options, and sanitized public failures before implementation.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-11T01:58:12Z
- **Completed:** 2026-05-11T02:04:21Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added roster metadata tests requiring `voxcpm2`, `VoxCPM2`, Apache-2.0 code/model license fields, `supports_streaming=True`, `requires_transcript=False`, health/runtime evidence, and the `RTX 3060 gate pending` caveat.
- Added model manager tests requiring failed VoxCPM2 loads to mark only `voxcpm2` unavailable with fixed reason `engine load failed`, while `f5`, `xtts_v2`, `qwen3_0_6b`, `luxtts`, `chatterbox_turbo`, and `tada_1b` remain present.
- Created VoxCPM2 adapter tests for `voxcpm==2.0.2`, `VoxCPM.from_pretrained("openbmb/VoxCPM2", device="cuda")`, no `device="auto"`, reference-only fallback warnings, transcript-guided prompt text, bounded style/control options, sanitized empty-audio failure, and 48 kHz sample-rate propagation.
- Extended `/tts/synthesize` tests so VoxCPM2-specific bounded fields must flow into `TtsSynthesisInput`, and public error payloads reject `Traceback`, `C:\`, `/home/`, and `openbmb/VoxCPM2`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add VoxCPM2 roster and residency RED tests** - `c2bb05c` (test)
2. **Task 2: Add VoxCPM2 adapter and synthesis API RED tests** - `0ebc956` (test)

## Files Created/Modified

- `ai-backend/tests/test_tts_voxcpm2.py` - New VoxCPM2 adapter contract tests using fake runtimes and package shims.
- `ai-backend/tests/test_tts_registry.py` - Extended engine metadata and `/tts/synthesize` contracts for VoxCPM2.
- `ai-backend/tests/test_model_manager.py` - Extended one-hot residency and engine-scoped unavailable-state contracts for VoxCPM2.

## Verification

Plan-level command:

```bash
uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py -q
```

Result: RED as intended, `13 failed, 15 passed, 1 warning`.

Expected RED failure categories:

- `app.models.tts_voxcpm2` is missing, so adapter contract tests fail with `ModuleNotFoundError`.
- `TtsSynthesisInput` does not yet expose `voxcpm2_cloning_mode`, `voxcpm2_style_prompt`, `voxcpm2_cfg_value`, `voxcpm2_inference_timesteps`, `voxcpm2_normalize`, or `voxcpm2_denoise`.
- `TTS_ENGINE_METADATA` and `EXPECTED_ENGINE_IDS` do not yet include `voxcpm2`.
- `ModelManager` health/status metadata does not yet include `voxcpm2`, so one-hot residency and load-failure degradation tests fail.

These failures match the plan goal: production code has not implemented VoxCPM2 metadata, adapter, or bounded synthesis behavior yet.

## Decisions Made

- Kept this plan test-only. No production code, dependencies, runtime scripts, or OMEN deployment changes were made.
- Used fake runtimes and import shims in adapter tests to keep RED contracts deterministic and model-download-free.
- Required sanitization assertions for traceback text, Windows paths, Unix home paths, and model id leakage at the public HTTP boundary.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. RED failures are expected and document missing production behavior for later Phase 7 plans.

## Known Stubs

None. The empty transcript in `test_voxcpm2_reference_only_mode_when_transcript_missing` is intentional test input for the reference-only fallback contract.

## User Setup Required

None - no external service configuration required.

## Threat Flags

None - this plan added tests only and introduced no new runtime network endpoint, auth path, file access implementation, or schema trust boundary.

## Next Phase Readiness

Ready for the next Phase 7 implementation plan. The missing production work is now explicitly described by executable backend tests.

## Self-Check: PASSED

- Found created/modified files: `ai-backend/tests/test_tts_voxcpm2.py`, `ai-backend/tests/test_tts_registry.py`, `ai-backend/tests/test_model_manager.py`, and this summary.
- Found task commits: `c2bb05c` and `0ebc956`.
- `git diff --check` passed for this summary.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
