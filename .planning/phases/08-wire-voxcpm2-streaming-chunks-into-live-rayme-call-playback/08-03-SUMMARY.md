---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
plan: 03
subsystem: call-route-and-web-ui-facade
tags: [voxcpm2, streaming, webrtc, sse, pytest]

# Dependency graph
requires:
  - phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
    provides: CallSession immediate and final playback metric carriers from plan 08-02
provides:
  - Route-level coverage proving `/webrtc/sessions/{session_id}/speak` preserves streaming playback metrics
  - Web UI SSE coverage proving nested `ai_audio_started_event.tts_playback` reaches the browser
  - Server coverage proving streamed playback metrics do not create extra durable AI speech rows
affects: [phase-08-live-evidence, web-ui-call-sse, webrtc-speak]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Route/server tests lock metric-carrier separation without adding VoxCPM2 public routes
    - Web UI forwards nested first-audio events by copying the backend event mapping

key-files:
  created: []
  modified:
    - ai-backend/tests/test_webrtc_signaling.py
    - web-ui/server/tests/test_calls.py

key-decisions:
  - "The existing `/webrtc/sessions/{session_id}/speak` route response already preserves nested `ai_audio_started_event.tts_playback` and final `tts_playback_final` fields."
  - "The Web UI call facade keeps forwarding the nested first-audio event as one SSE event and does not persist per-chunk speech rows."
  - "No VoxCPM2-specific browser-visible route was added for Phase 8 metric forwarding."

patterns-established:
  - "Immediate playback metrics stay under `ai_audio_started_event.tts_playback`; final-only generation/playback totals stay under `tts_playback_final`."
  - "Streaming failure tests assert fixed public `call_tts_failed` responses while separately locking post-first-audio session event shape."

requirements-completed: [P8-R1, P8-R3, P8-R4]

# Metrics
duration: 7 min
completed: 2026-05-11
---

# Phase 08 Plan 03: WebRTC and Web UI Streaming Metrics Summary

**Existing call APIs now have route and server tests proving VoxCPM2 streaming timing fields reach callers without new public runtime routes**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-11T15:15:04Z
- **Completed:** 2026-05-11T15:22:07Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments

- Added `/webrtc/speak` tests for successful VoxCPM2 streaming responses with immediate `tts_playback` and final `tts_playback_final` metrics.
- Added sanitized streaming-failure coverage for raw VoxCPM2 traceback/cache-path errors, plus post-first-audio event-shape coverage.
- Added Web UI call SSE coverage proving nested streaming first-audio metrics are forwarded once while the visible LLM reply creates one durable `ai_speech` row.

## Task Commits

Each task was committed atomically:

1. **Task 1: Lock `/webrtc/speak` streaming metrics and sanitized failures** - `1455d1a` (test)
2. **Task 2: Preserve Web UI SSE keepalive and single durable AI speech row** - `5fc4b0c` (test)

_TDD note: both RED test runs passed immediately because the 08-02 implementation already preserved the route/server behavior under test. No GREEN implementation commit was needed._

## Files Created/Modified

- `ai-backend/tests/test_webrtc_signaling.py` - Adds scripted VoxCPM2 streaming adapters and route assertions for streaming metric carriers plus sanitized failure responses.
- `web-ui/server/tests/test_calls.py` - Adds Web UI server SSE/persistence assertions for nested `ai_audio_started_event.tts_playback` forwarding and one durable AI speech row.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q` - PASS, 22 passed.
- `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` - PASS, 31 passed.
- `git diff --check` - PASS.
- `rg -n "voxcpm2" ai-backend/app/api/webrtc.py` - PASS, only bounded payload option handling.
- `rg -n "voxcpm2" web-ui/server/app/api/calls.py || true` - PASS, no Web UI route path contains `voxcpm2`.

## Decisions Made

- No implementation edits were required: the existing backend route wrapper returns the session event without dropping nested first-audio or final playback metrics.
- No Web UI facade edits were required: `_extract_ai_audio_started_event(...)` already returns `dict(candidate)`, preserving nested `tts_playback`.
- The plan stayed within existing `/webrtc` and `/api/calls` surfaces; no browser-visible VoxCPM2 runtime API was added.

## Deviations from Plan

None - plan executed exactly as written. The plan allowed code updates only if wrappers dropped metrics or leaked raw errors; the new tests confirmed no code update was needed.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope change.

## Issues Encountered

- TDD RED runs passed immediately for both tasks. Investigation showed this is because plan 08-02 already added the behavior; this plan locked the public route/server contracts around it.
- Metadata note: `gsd-sdk query requirements.mark-complete P8-R1 P8-R3 P8-R4` returned `not_found` because these are Phase 8 SPEC requirement IDs, not global `.planning/REQUIREMENTS.md` IDs. The IDs remain copied verbatim in summary frontmatter for traceability.

## Authentication Gates

None.

## Known Stubs

None. Stub-pattern scan found only an existing test initializer with `prompt_messages=[]`, unrelated to this plan and not a UI/data stub.

## User Setup Required

None - no external service configuration required. This plan did not deploy to OMEN.

## TDD Gate Compliance

- RED commits present: `1455d1a`, `5fc4b0c`.
- GREEN commits: not needed; the added tests passed before implementation changes because the required behavior already existed.
- Warning: strict RED failure was not observed for either task. The tests were still committed as contract locks after confirming no code path needed changes.

## Next Phase Readiness

Plan 08-05 can consume the metric carriers through the existing public call route and Web UI SSE path; plan 08-04 evidence tooling is already complete.

## Self-Check: PASSED

- Summary file exists.
- Key modified files exist.
- Task commits `1455d1a` and `5fc4b0c` exist in git history.

---
*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Completed: 2026-05-11*
