---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 03
subsystem: testing
tags: [web-ui, ai-backend, calls, webrtc, voxcpm2, pytest, red-contracts]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: "Plan 07-01 backend VoxCPM2 RED contracts and Plan 07-02 Voice Lab metadata contracts"
provides:
  - "Web UI call RED contracts for saved VoxCPM2 metadata forwarding into real call playback"
  - "AI backend WebRTC speak RED contracts for bounded VoxCPM2 call options and sanitized validation"
  - "Call-session RED contracts for generic adapter VoxCPM2 option forwarding and unchanged interrupt semantics"
affects: [phase-07-voxcpm2-call-integration, web-ui-calls, ai-backend-webrtc, call-session-tts]

tech-stack:
  added: []
  patterns:
    - "RED call-flow contracts before VoxCPM2 call integration"
    - "Public call TTS failures use fixed call_tts_failed details without raw runtime disclosure"

key-files:
  created:
    - ".planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-03-SUMMARY.md"
  modified:
    - "web-ui/server/tests/test_calls.py"
    - "ai-backend/tests/test_call_session.py"
    - "ai-backend/tests/test_webrtc_signaling.py"

key-decisions:
  - "VoxCPM2 preview success is insufficient; saved mode/style metadata must reach real call playback before promotion."
  - "VoxCPM2 call failures must surface sanitized call_tts_failed behavior while preserving truthful transcript rows."
  - "VoxCPM2 call option validation must be bounded and must not echo traceback, local path, or model-cache details."

patterns-established:
  - "Call voice reference tests seed metadata.engine_settings.voxcpm2 and assert flattened voxcpm2_* fields at the speak_call boundary."
  - "AI backend call tests require the same interrupt event behavior for engine_id=voxcpm2 as existing engines."

requirements-completed: [REQ-41, REQ-42, REQ-62]

duration: 8min
completed: 2026-05-11
---

# Phase 07 Plan 03: VoxCPM2 Call-Flow RED Contracts Summary

**Executable call-flow contracts now prove saved VoxCPM2 voice metadata must reach real WebRTC playback, with bounded speak options and sanitized call TTS failures.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-11T02:19:20Z
- **Completed:** 2026-05-11T02:27:01Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added Web UI call tests seeding a saved `voxcpm2` voice with `metadata.engine_settings.voxcpm2`, then requiring `voice_reference_for_call()` and `/api/calls/{call_id}/turns` `speak_call` payloads to carry the flattened VoxCPM2 mode/style/control fields.
- Added a Web UI failure contract requiring backend `call_tts_failed` during VoxCPM2 call playback to produce sanitized public SSE error details while preserving exact user speech and AI text rows.
- Added AI backend WebRTC speak tests requiring bounded VoxCPM2 request fields, sanitized 422 validation for unsafe/overlong values, and fixed `call_tts_failed` disclosure behavior.
- Added call-session tests requiring generic adapters to receive VoxCPM2 fields in `TtsSynthesisInput` and confirming interrupt/cancel event behavior remains unchanged for `engine_id="voxcpm2"`.

## Task Commits

1. **Task 1: Add Web UI call payload forwarding RED tests** - `c5e5f99` (test)
2. **Task 2: Add AI backend speak/session RED tests** - `91e2ee0` (test)

## Files Created/Modified

- `web-ui/server/tests/test_calls.py` - Added VoxCPM2 call metadata forwarding and sanitized call failure contracts.
- `ai-backend/tests/test_call_session.py` - Added VoxCPM2 generic adapter option-forwarding and interrupt behavior contracts.
- `ai-backend/tests/test_webrtc_signaling.py` - Added VoxCPM2 speak request bounds, sanitized 422, and sanitized failure assertions.
- `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-03-SUMMARY.md` - This execution summary.

## Verification

Plan-level commands:

```bash
uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q
```

Result: RED as intended, `2 failed, 28 passed`.

Expected Web UI RED failures:

- `voice_reference_for_call()` does not yet expose `voxcpm2_cloning_mode`, `voxcpm2_style_prompt`, `voxcpm2_cfg_value`, `voxcpm2_inference_timesteps`, `voxcpm2_normalize`, or `voxcpm2_denoise`.
- `/api/calls/{call_id}/turns` currently logs backend `call_tts_failed` and yields `ai_done` recovery instead of a public sanitized `call_tts_failed` SSE error for VoxCPM2 call playback.

```bash
uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q
```

Result: RED as intended, `3 failed, 57 passed, 3 warnings`.

Expected AI backend RED failures:

- `CallSession.speak_text()` does not yet accept VoxCPM2 option keyword arguments for generic adapter synthesis.
- `SpeakRequest` currently rejects valid bounded VoxCPM2 option fields with 422.
- FastAPI validation currently echoes unsafe overlong VoxCPM2 input in 422 details, including traceback/path/model-cache text.

## Decisions Made

- Kept this plan test-only. No production code, runtime dependencies, scripts, OMEN deployment changes, or scheduled-task changes were made.
- Used fixture-level fake adapters/backends only; no VoxCPM2 model import or download path was introduced.
- Required call option fields to be flattened as `voxcpm2_*` at the call playback boundary, matching the Phase 7 key-link pattern.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Expected RED failures documented above.
- `gsd-sdk` roadmap and session handlers updated planning state successfully, but the metric and decision handlers did not match this project's `STATE.md` section layout. The missing Phase 07-03 status and decision bullets were added directly to `STATE.md`.

## Known Stubs

None. Stub scan only found normal test fixture initializers, optional arguments, and empty-list assertions in touched test files.

## User Setup Required

None - no external service configuration required.

## Threat Flags

None - this plan added tests for the declared call TTS error-handling and speak-payload trust boundaries, and introduced no new runtime endpoint, auth path, file access implementation, or schema surface.

## Next Phase Readiness

Ready for the implementation follow-up. The next call-integration plan should satisfy these contracts without weakening existing F5/XTTS/Qwen/LuxTTS/Chatterbox/TADA call behavior, and should keep VoxCPM2 failures engine-scoped and sanitized.

## Self-Check: PASSED

- Found created/modified files: `web-ui/server/tests/test_calls.py`, `ai-backend/tests/test_call_session.py`, `ai-backend/tests/test_webrtc_signaling.py`, and this summary.
- Found task commits: `c5e5f99` and `91e2ee0`.
- `git diff --check` passed for this summary.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
