---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
plan: 08
subsystem: calls
tags: [web-ui, ai-backend, calls, webrtc, voxcpm2, tts, pytest]

requires:
  - phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
    provides: "Plans 07-03, 07-05, and 07-06 VoxCPM2 call contracts, backend synthesis fields, and Web UI voice metadata"
provides:
  - "Saved VoxCPM2 voice settings forwarded through real call playback using existing call routes"
  - "Bounded VoxCPM2 WebRTC speak fields threaded into call-session synthesis"
  - "Sanitized call TTS and validation failures without raw traceback/path disclosure"
affects: [phase-07-voxcpm2-call-evidence, web-ui-calls, ai-backend-webrtc, ai-backend-call-session]

tech-stack:
  added: []
  patterns:
    - "Call voice references flatten saved metadata.engine_settings.voxcpm2 only for active voxcpm2 calls"
    - "Call-specific TTS adapters receive VoxCPM2 options only when their synthesize_call_text signature accepts them"
    - "AI backend validation errors use fixed public details instead of echoing unsafe request input"

key-files:
  created:
    - ".planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-08-SUMMARY.md"
  modified:
    - "web-ui/server/app/domain/call_service.py"
    - "web-ui/server/app/api/calls.py"
    - "web-ui/server/tests/test_calls.py"
    - "ai-backend/app/api/webrtc.py"
    - "ai-backend/app/call/session.py"
    - "ai-backend/app/main.py"

key-decisions:
  - "Real call playback reuses saved VoxCPM2 settings through the existing RayMe call API; no VoxCPM2-specific browser route was added."
  - "AI backend call speak validation uses the same VoxCPM2 bounds as transient synthesis and does not echo rejected input."
  - "Legacy call-specific TTS adapters are kept compatible unless they explicitly accept VoxCPM2 option kwargs."

patterns-established:
  - "Web UI call voice references append voxcpm2_* fields from durable voice metadata only when call.engine_id == voxcpm2."
  - "CallSession builds TtsSynthesisInput with VoxCPM2 options for generic adapters while preserving existing interrupt and audio enqueue semantics."

requirements-completed: [REQ-41, REQ-42, REQ-62]

duration: 9min
completed: 2026-05-11
---

# Phase 07 Plan 08: VoxCPM2 Real Call Playback Summary

**Saved VoxCPM2 cloning and style settings now reach real call TTS playback through the existing Web UI and AI backend call APIs.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-05-11T03:17:09Z
- **Completed:** 2026-05-11T03:26:24Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Extended Web UI call voice references to include bounded flat `voxcpm2_*` fields from `metadata.engine_settings.voxcpm2` only for active `voxcpm2` calls.
- Forwarded those fields through the existing `/api/calls/{call_id}/turns` speak payload without adding any browser-facing VoxCPM2 route.
- Surfaced call TTS failures as fixed sanitized SSE errors while preserving saved user speech and AI text rows.
- Added bounded VoxCPM2 fields to `/webrtc/sessions/{session_id}/speak` and threaded them through `CallSession.speak_text()` into generic `TtsSynthesisInput`.
- Added a fixed AI backend validation error response so rejected overlong/unsafe fields do not echo tracebacks, local paths, model cache strings, or model IDs.

## Task Commits

1. **Task 1: Forward VoxCPM2 settings from saved voice to call speak payload** - `d706063` (feat)
2. **Task 2: Pass VoxCPM2 options through AI backend speak/session synthesis** - `86f8b6e` (feat)

## Files Created/Modified

- `web-ui/server/app/domain/call_service.py` - Extracts saved VoxCPM2 metadata into call voice references for active VoxCPM2 calls.
- `web-ui/server/app/api/calls.py` - Propagates call voice reference fields into the existing speak payload and yields sanitized call TTS errors.
- `web-ui/server/tests/test_calls.py` - Locks VoxCPM2 call forwarding and non-VoxCPM2 payload omission.
- `ai-backend/app/api/webrtc.py` - Accepts bounded VoxCPM2 speak options and forwards them into call sessions.
- `ai-backend/app/call/session.py` - Threads VoxCPM2 options into generic adapter synthesis while preserving legacy adapter compatibility.
- `ai-backend/app/main.py` - Adds fixed public validation error details for rejected request bodies.

## Verification

- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` - passed, `30 passed`.
- `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` - passed, `60 passed, 3 warnings`.
- `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py -q` - passed, `17 passed, 1 warning`.
- `git diff --check` - passed.

The warnings are existing dependency/runtime warnings from `torch.cuda`, `silero_vad`, and `torch.jit` imports in the AI backend test environment.

## Decisions Made

- Kept the browser/public API unchanged: calls still use the existing Web UI call routes and AI backend WebRTC speak route.
- Used the existing flat `voxcpm2_*` boundary fields from Plans 07-05 and 07-06 rather than introducing nested call-only payloads.
- Added sanitized validation handling at the AI backend app boundary because FastAPI's default 422 body echoed unsafe rejected input.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added fixed validation-error responses**
- **Found during:** Task 2 (AI backend WebRTC speak validation)
- **Issue:** FastAPI's default validation response echoed rejected `voxcpm2_style_prompt` input, including simulated traceback/path/model-cache text.
- **Fix:** Added an app-level `RequestValidationError` handler returning fixed public `{code, message}` details.
- **Files modified:** `ai-backend/app/main.py`
- **Verification:** `test_webrtc_speak_rejects_unbounded_voxcpm2_options_with_sanitized_422` passed; `test_tts_registry.py` spot-check passed.
- **Committed in:** `86f8b6e`

**2. [Rule 1 - Bug] Preserved legacy call-specific adapter compatibility**
- **Found during:** Task 2 verification
- **Issue:** Forwarding VoxCPM2 kwargs to every `synthesize_call_text()` implementation broke existing adapters that do not accept arbitrary option kwargs, causing the interrupt test to emit `failed` before `interrupted`.
- **Fix:** Added signature-aware option forwarding: call-specific adapters receive VoxCPM2 kwargs only when they accept `**kwargs` or named fields; generic adapters still receive the full `TtsSynthesisInput`.
- **Files modified:** `ai-backend/app/call/session.py`
- **Verification:** `test_interrupt_cancels_voxcpm2_active_speech_before_ai_done` and the full AI backend call/WebRTC suite passed.
- **Committed in:** `86f8b6e`

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug).
**Impact on plan:** Both fixes were required for the declared D-20/T-07-03/T-07-04 correctness and security behavior. No public route, schema, runtime dependency, or deployment surface was added.

## Issues Encountered

- Expected RED contracts failed initially for missing VoxCPM2 call fields, missing WebRTC speak fields, missing session option plumbing, and unsafe validation echo. The implementation resolved those failures.

## Known Stubs

None. Stub-pattern scan only found normal optional fields, empty collection initializers, and test fixture state.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Phase 07 call-flow and runtime evidence plans. Real call playback now carries saved VoxCPM2 settings through the normal call path, but live OMEN/GPU VoxCPM2 quality, latency, VRAM, and promotion evidence are still handled by later Phase 07 plans.

## Self-Check: PASSED

- Found created/modified files listed in this summary, including `07-08-SUMMARY.md`.
- Found task commits: `d706063` and `86f8b6e`.
- `git diff --check` passed for this summary.

---
*Phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency*
*Completed: 2026-05-11*
