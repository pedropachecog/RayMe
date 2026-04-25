---
phase: 02-ai-backend-skeleton-voice-lab
plan: "16"
subsystem: docs
tags: [licenses, tts, runbook, runtime-evidence, voice-lab, omen-pc, https-lan]

requires:
  - phase: 00-measurement-gate
    provides: Phase 0 STT/TTS defaults, runtime matrix, and RTX 3060 VRAM evidence
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: TTS registry metadata from 02-08 and Voice Lab workflow from 02-12/02-14
provides:
  - TTS engine license and commercial-use caveat notices for the full six-engine roster
  - Runtime evidence gate for one-runtime preference, health, synthesis, and VRAM proof
  - Voice Lab operations runbook with upload, transcript, preview, save, delete, test-play, and cleanup guidance
  - OMEN-PC live evidence fill-in artifact
affects: [02-18, 03-first-working-call, runtime-operations, license-review]

tech-stack:
  added: []
  patterns: [license metadata separated from default selection, one-runtime evidence gate, exact cleanup path documentation]

key-files:
  created:
    - LICENSES.md
    - ai-backend/docs/RUNTIME-EVIDENCE.md
    - web-ui/server/docs/VOICE-LAB-RUNBOOK.md
    - .planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md
  modified:
    - web-ui/server/docs/HTTPS-LAN.md

key-decisions:
  - "License notices distinguish package/code licenses from model/weights licenses and do not treat default engine selection as commercial-use clearance."
  - "Runtime promotion requires one-runtime evidence first; split runtime, WSL, Docker, or subprocess paths require logged one-runtime failure evidence while preserving one public AI backend API."
  - "Voice Lab cleanup guidance uses exact durable blob paths and explicitly protects the canonical OMEN-PC checkout and reusable TLS material."

patterns-established:
  - "Operational docs name `C:\\Users\\pmpg\\rayme\\RayMe\\` and `C:\\Users\\pmpg\\rayme\\phase1-tls\\` as canonical OMEN-PC paths."
  - "Live runtime acceptance is recorded in a fill-in artifact with commit SHA, health JSON, engine roster, VRAM/headroom, generated audio, and Android product-owner result."

requirements-completed: [REQ-02, REQ-20, REQ-21, REQ-22, REQ-23, REQ-80, REQ-A3]

duration: 4 min
completed: 2026-04-25
---

# Phase 02 Plan 16: Runtime Evidence and License Runbooks Summary

**TTS license/caveat notices plus Voice Lab and OMEN-PC runtime evidence runbooks for Phase 2 live handoff.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-25T02:04:37Z
- **Completed:** 2026-04-25T02:08:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `LICENSES.md` with TTS Engine Notices for F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base, LuxTTS, Chatterbox Turbo, and TADA 1B.
- Added `ai-backend/docs/RUNTIME-EVIDENCE.md` with install/self-test, `/health`, short synthesis, `nvidia-smi`, 11 GB VRAM, and fallback evidence gates.
- Added `web-ui/server/docs/VOICE-LAB-RUNBOOK.md` covering sample upload storage, transcript retry/manual entry, optional preview, save, rename, force delete, test-play, and exact cleanup paths.
- Updated `web-ui/server/docs/HTTPS-LAN.md` with Phase 2 Voice Lab and AI health live URLs using the existing mkcert LAN setup.
- Added `.planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md` as the live verification fill-in artifact.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add license and caveat notices** - `3ce5bef` (docs)
2. **Task 2: Add runtime evidence and Voice Lab runbooks** - `c80b8df` (docs)

## Files Created/Modified

- `LICENSES.md` - Root TTS license, commercial-use caveat, and runtime caveat notices.
- `ai-backend/docs/RUNTIME-EVIDENCE.md` - One-runtime evidence gate and live runtime command checklist.
- `web-ui/server/docs/VOICE-LAB-RUNBOOK.md` - Voice Lab operational flow and safe cleanup paths.
- `web-ui/server/docs/HTTPS-LAN.md` - Phase 2 live Voice Lab and AI health URLs.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md` - OMEN-PC fill-in evidence template.

## Verification

- `rg "F5-TTS|XTTS v2|Qwen3-TTS 0.6B-Base|LuxTTS|Chatterbox Turbo|TADA 1B|CC-BY-NC|CPML|Apache-2.0|commercial-use caveat|model/weights license" LICENSES.md` - PASS.
- `rg "one public AI backend API|nvidia-smi|11000|RAYME_ENABLE_LIVE_E2E|https://192.168.1.199:8443/voice-lab|https://192.168.1.199:9443/health|optional preview|manual transcript|force delete|OMEN-PC|commit SHA" ai-backend/docs/RUNTIME-EVIDENCE.md web-ui/server/docs/VOICE-LAB-RUNBOOK.md web-ui/server/docs/HTTPS-LAN.md .planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md` - PASS.
- `git diff -- LICENSES.md ai-backend/docs/RUNTIME-EVIDENCE.md web-ui/server/docs/VOICE-LAB-RUNBOOK.md web-ui/server/docs/HTTPS-LAN.md .planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md` - PASS, no uncommitted diff after task commits.

## Decisions Made

- Followed the plan's license/commercial caveat split and added explicit language that F5's default status is not a commercial-use clearance.
- Kept Phase 2 runtime docs aligned with the user preference for one runtime first, requiring evidence before any split runtime recommendation.
- Treated Voice Lab preview blobs as future-reserved cleanup scope only; Phase 2 save does not require preview persistence.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

- `.planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md:21` contains an intentional empty `{}` JSON block for the future live `/health` response. This is a fill-in evidence artifact, not runtime code or UI data.

## Threat Flags

None. This plan added operational documentation only; it introduced no new network endpoint, auth path, runtime file access, or schema boundary.

## Next Phase Readiness

Plan 02-18 can use the live evidence artifact and runbooks to capture OMEN-PC `/health`, VRAM/headroom, generated audio, and Android product-owner acceptance without re-opening license/default-engine decisions.

## Self-Check: PASSED

- Verified created/modified files exist: `LICENSES.md`, `RUNTIME-EVIDENCE.md`, `VOICE-LAB-RUNBOOK.md`, `HTTPS-LAN.md`, `OMEN-PC-LIVE-EVIDENCE.md`, and this summary.
- Verified task commits exist: `3ce5bef` and `c80b8df`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
