---
phase: 03-first-working-call-mvp
plan: "11"
subsystem: testing
tags: [omen, playwright, webrtc, live-call, gpu]
requires:
  - phase: 03-first-working-call-mvp
    provides: "Plan 03-10 produced full local Phase 3 automated acceptance and the gated live-call Playwright spec."
provides:
  - "Live OMEN-PC desktop call acceptance against the deployed LAN HTTPS Web UI and RTX 3060 AI backend."
  - "Saved evidence for deployed commit SHA, AI health, secure browser context, server-side mute frame drops, 5-minute stability, and Android handoff status."
affects: [03-first-working-call-mvp, live-call-handoff, android-acceptance]
tech-stack:
  added: []
  patterns:
    - "Live evidence records deployed SHA, canonical URLs, GPU health, browser secure-context proof, non-mocked Playwright result, and exact caveats before physical-device handoff."
key-files:
  created:
    - .planning/phases/03-first-working-call-mvp/03-11-SUMMARY.md
  modified:
    - web-ui/client/tests/e2e/live-call.spec.ts
    - .planning/phases/03-first-working-call-mvp/OMEN-PC-LIVE-EVIDENCE.md
key-decisions:
  - "The passing desktop live evidence is the OMEN-local Chromium run; the WSL-origin run is recorded only as a WSL/LAN ICE-path caveat."
  - "Android Chrome product-owner acceptance remains a separate blocking checkpoint in Plan 03-12."
patterns-established:
  - "OMEN live acceptance must use `scripts/deploy-omen.sh` for deployment and record exact runtime evidence instead of relying on mocked local specs."
requirements-completed: [REQ-40, REQ-47, REQ-48, REQ-49, REQ-50, REQ-63, REQ-A0, REQ-A1]
duration: 1h 27m
completed: 2026-05-11
---

# Phase 03 Plan 11: OMEN-PC Live LAN Call Acceptance Summary

**Live OMEN-PC Chromium completed a non-mocked LAN call with two user turns, two AI speech turns, server-side mute drops, durable call writeback, and a 5-minute stability hold.**

## Performance

- **Duration:** 1h 27m
- **Started:** 2026-05-11T21:31:21Z
- **Completed:** 2026-05-11T22:58:10Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Verified `OMEN-PC` checkout at `e48e2ce57cc31a30e7df97c1f0ea9215c136dc45` with live Web UI and AI backend responding on the canonical LAN HTTPS URLs.
- Ran the non-mocked `live-call.spec.ts` on `OMEN-PC` using a fake audio capture WAV and `RAYME_LIVE_STABILITY_MS=300000`; result was `1 passed (6.1m)`.
- Recorded current AI `/health` evidence: CUDA faster-whisper STT, `resident_tts_engine=f5`, VoxCPM2 available idle, `vram_used_mb=3481.6`, and `vram_headroom_mb=7518.4`.
- Recorded server-side mute evidence where the AI backend emitted `type=muted` and dropped all sampled inbound frames while `state=muted`.

## Task Commits

Implementation/test hardening commits from this plan:

1. **Task 1: Repair live call acceptance spec** - `1acef63` (fix)
2. **Task 1: Avoid optional interrupt wait in live spec** - `5ba4a6e` (fix)
3. **Task 2: Add live call stability hold** - `b8e84ad` (fix)
4. **Task 2: Wait for live end persistence** - `d4473fe` (fix)
5. **Task 2: Disambiguate live return button** - `e48e2ce` (fix)

Plan metadata and evidence are committed separately with this summary.

## Files Created/Modified

- `web-ui/client/tests/e2e/live-call.spec.ts` - Hardened live-only acceptance for deterministic OMEN execution, mute/unmute, end persistence, and 5-minute stability evidence.
- `.planning/phases/03-first-working-call-mvp/OMEN-PC-LIVE-EVIDENCE.md` - Updated with current deployed SHA, health evidence, passing command, mute logs, stability result, WSL caveat, and Android pending status.
- `.planning/phases/03-first-working-call-mvp/03-11-SUMMARY.md` - This execution summary.

## Decisions Made

- The live acceptance result must come from the OMEN-local Chromium run because the WSL-origin attempt failed with a LAN/ICE connection drop before user speech finalized.
- The Android product-owner gate remains pending and must not be inferred from desktop Chromium evidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Hardened the live browser spec until the deployed flow was assertable**
- **Found during:** Task 1 and Task 2
- **Issue:** The live spec needed deterministic setup, optional interrupt handling, stability timing, end persistence, and an unambiguous return-to-thread selector before it could serve as trustworthy OMEN evidence.
- **Fix:** Updated `live-call.spec.ts` across the five 03-11 fix commits listed above.
- **Files modified:** `web-ui/client/tests/e2e/live-call.spec.ts`
- **Verification:** OMEN-local live command passed with `1 passed (6.1m)` and stability line `duration_ms=300000 before_user=2 before_ai=2 after_user=13 after_ai=12`.
- **Committed in:** `1acef63`, `5ba4a6e`, `b8e84ad`, `d4473fe`, `e48e2ce`

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** The fixes strengthened the live acceptance gate without changing the product surface.

## Issues Encountered

- The first WSL-origin live command used a relative fake-audio path and was rerun with an absolute path.
- The WSL-origin absolute-path run reached the deployed services but failed after the page reported `The call ended because the connection dropped`; it is documented as a WSL/LAN ICE-path caveat and is not counted as passing evidence.
- The delegated executor did not return a final result or create this summary within the wait budget. The parent closed the subagent, verified the deployed run, and completed the evidence/summary inline.
- OMEN logs contained Windows asyncio `_ProactorBasePipeTransport._call_connection_lost(None)` callback messages during the live run; Playwright still passed and the browser console/page-error guard reported no page failures.

## User Setup Required

Android Chrome product-owner acceptance is still required by Plan 03-12:
open `https://192.168.1.199:8443` on the already trusted Android Chrome device
and verify the physical-device call flow.

## Known Stubs

None.

## Threat Flags

None. Evidence records runtime facts and sanitized log excerpts only; no TLS private keys, API keys, or raw microphone audio were captured.

## Auth Gates

None.

## Verification

- `curl -k -s https://192.168.1.199:9443/health` - passed; returned `stt_model=distil-large-v3`, `stt_compute_type=int8_float16`, `vad_ready=true`, `resident_tts_engine=f5`, `voxcpm2` available idle, `vram_used_mb=3481.6`, and `vram_headroom_mb=7518.4`.
- OMEN-local `npm --prefix web-ui/client run test:e2e -- tests/e2e/live-call.spec.ts --project=desktop-chromium --reporter=line` with live env vars and `RAYME_LIVE_STABILITY_MS=300000` - `1 passed (6.1m)`.
- AI backend log inspection - passed; `rtc_4bc2136a389c428195ae6ddc9c353846` emitted `type=muted` and `inbound.dropped ... total=100 dropped=100 muted=True state=muted`.
- Evidence grep - passed; required fields were found for deployed commit SHA,
  `/health`, `resident_tts_engine`, `vram_used_mb`,
  `window.isSecureContext`, two user turns, two `ai_speech`,
  server-side mute, `dropped_audio_frames`, 5-minute stability, and Android.

## Next Phase Readiness

Plan 03-12 can proceed to the blocking Android Chrome product-owner checkpoint. Desktop/live OMEN evidence is complete; physical Android approval or exact failure details are still required before Phase 3 can close.

## Self-Check: PASSED

- Created/modified files exist: `.planning/phases/03-first-working-call-mvp/OMEN-PC-LIVE-EVIDENCE.md` and this summary.
- Task commits exist in git history: `1acef63`, `5ba4a6e`, `b8e84ad`, `d4473fe`, `e48e2ce`.
- The live evidence file records deployed commit SHA, `/health`, `resident_tts_engine`, `vram_used_mb`, `window.isSecureContext`, two user turns, two `ai_speech`, server-side mute, dropped frame evidence, 5-minute stability, and Android pending status.

---
*Phase: 03-first-working-call-mvp*
*Completed: 2026-05-11*
