---
phase: 02-ai-backend-skeleton-voice-lab
plan: "17"
subsystem: ai-backend
tags: [fastapi, aiortc, webrtc, signaling, pytest, tdd]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: AI backend FastAPI app factory, health router, and model residency foundation from plans 02-06 and 02-08
provides:
  - Non-call `/webrtc/status` signaling skeleton contract for Phase 3
  - `/webrtc/offer` Phase 2 guard returning fixed HTTP 501 `call_not_ready` detail
  - Tests preventing Phase 2 from claiming call, captions, barge-in, or live media readiness
affects: [03-first-working-call, 04-call-feel]

tech-stack:
  added: [aiortc==1.14.0]
  patterns: [non-call signaling boundary, fixed public phase-boundary error detail, route-level readiness disclaimers]

key-files:
  created:
    - ai-backend/app/api/webrtc.py
    - ai-backend/tests/test_webrtc_signaling.py
  modified:
    - ai-backend/app/main.py
    - ai-backend/pyproject.toml
    - ai-backend/uv.lock

key-decisions:
  - "Phase 2 exposes only a non-call WebRTC signaling skeleton; live media, captions, and barge-in remain Phase 3+ scope."
  - "The offer endpoint rejects requests without parsing SDP or creating peer connections so it cannot allocate media resources."

patterns-established:
  - "AI backend phase-boundary endpoints return explicit readiness flags and fixed public error details."
  - "Future WebRTC implementation must replace the skeleton behind the existing `/webrtc` router without adding `/call`, `/captions`, or `/barge-in` routes in Phase 2."

requirements-completed: [REQ-02]

duration: 3 min
completed: 2026-04-25
---

# Phase 02 Plan 17: Non-Call aiortc Signaling Skeleton Summary

**aiortc dependency and FastAPI `/webrtc` skeleton that explicitly rejects live-call media until Phase 3.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-25T02:12:19Z
- **Completed:** 2026-04-25T02:15:32Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added contract tests for `/webrtc/status`, `/webrtc/offer`, and OpenAPI route boundaries.
- Added `aiortc==1.14.0` to the AI backend dependency set.
- Added `app/api/webrtc.py` with skeleton status and fixed HTTP 501 offer rejection.
- Registered the WebRTC router in `create_app()` without adding call, captions, barge-in, media tracks, or playback behavior.

## Task Commits

TDD tasks produced RED and GREEN commits:

1. **Task 1 RED: Add non-call signaling contract tests** - `b043288` (test)
2. **Task 2 GREEN: Implement non-call signaling skeleton** - `707609f` (feat)

## Files Created/Modified

- `ai-backend/tests/test_webrtc_signaling.py` - New non-call signaling contract tests.
- `ai-backend/app/api/webrtc.py` - New `/webrtc/status` and `/webrtc/offer` skeleton router.
- `ai-backend/app/main.py` - Includes the WebRTC router.
- `ai-backend/pyproject.toml` - Adds `aiortc==1.14.0`.
- `ai-backend/uv.lock` - Locks aiortc and resolver-selected transitive packages.

## Verification

- `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py ai-backend/tests/test_health.py -q` - PASS, 9 tests with the existing `pynvml` deprecation warning.
- `rg "/webrtc/status|/webrtc/offer|live_call_ready.*false|media_transport_ready.*false|call_not_ready|Phase 3 owns live call media|/call|/captions|/barge-in" ai-backend/tests/test_webrtc_signaling.py` - PASS.
- `rg "aiortc==1.14.0|/webrtc/status|/webrtc/offer|live_call_ready.*false|media_transport_ready.*false|call_not_ready|Phase 3 owns live call media|include_router\\(webrtc" ai-backend/pyproject.toml ai-backend/app ai-backend/tests/test_webrtc_signaling.py` - PASS.
- `! rg "Voice Visualizer|RTCPeerConnection" ai-backend/app/api/webrtc.py` - PASS.

## Decisions Made

- Kept the route in the AI backend because Phase 3 media transport belongs beside future aiortc handling.
- Did not import or instantiate aiortc primitives in Phase 2; the dependency is present, but the router only defines the safe contract boundary.
- Used a fixed 501 detail for `/webrtc/offer` so no SDP content is parsed or echoed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `uv add aiortc==1.14.0` resolved aiortc transitive dependencies and selected `av==16.1.0`, replacing the previously installed `av==17.0.1` in the local environment/lock to satisfy the dependency graph.
- The existing `pynvml` deprecation warning still appears in health tests and is unchanged by this plan.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. The skeleton is intentional Phase 2 scaffolding with explicit non-readiness flags and 501 rejection.

## Threat Flags

None. The new `/webrtc` endpoints are the planned trust-boundary surfaces in this plan's threat model and include the required no-resource-allocation and fixed-error mitigations.

## TDD Gate Compliance

- RED gate commit present: `b043288`
- GREEN gate commit present after RED: `707609f`

## Next Phase Readiness

Phase 3 can build real `RTCPeerConnection` signaling behind the existing `/webrtc` API boundary. Phase 2 remains clear that live call media, captions, and barge-in are not ready.

## Self-Check: PASSED

- Verified key files exist: `webrtc.py`, `test_webrtc_signaling.py`, `main.py`, `pyproject.toml`, `uv.lock`, and this summary.
- Verified task commits exist: `b043288` and `707609f`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
