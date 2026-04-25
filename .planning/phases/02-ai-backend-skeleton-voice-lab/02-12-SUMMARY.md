---
phase: 02-ai-backend-skeleton-voice-lab
plan: "12"
subsystem: ui
tags: [svelte, sveltekit, vitest, playwright, voice-lab, tts]

requires:
  - phase: 02-ai-backend-skeleton-voice-lab
    provides: Voice server APIs from 02-09, Settings status from 02-10/02-14, and client Voice Lab contracts from 02-03
provides:
  - Client Voice Lab upload, transcript, metadata-driven engine picker, optional preview, and save workflow
  - Typed client wrappers for Voice Lab and Voice Library voice APIs
  - Browser coverage proving Save Voice works after preview HTTP 502 and the route has no 320px horizontal scroll
affects: [02-13, 02-15, 02-16, 02-18, 03-first-working-call]

tech-stack:
  added: []
  patterns: [typed RayMe API wrappers, Settings-status-driven engine metadata, preview-optional save state]

key-files:
  created:
    - web-ui/client/src/lib/api/voices.ts
    - web-ui/client/src/lib/components/voice/AudioSampleDropzone.svelte
    - web-ui/client/src/lib/components/voice/TranscriptEditor.svelte
    - web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte
    - web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte
    - web-ui/client/src/routes/voice-lab/+page.svelte
  modified:
    - web-ui/client/src/lib/api/types.ts
    - web-ui/client/src/lib/components/AppShell.svelte
    - web-ui/client/tests/unit/voice-lab.test.ts
    - web-ui/client/tests/e2e/voice-lab.spec.ts

key-decisions:
  - "Voice Lab save is gated only by sample asset, non-empty name, non-empty transcript, and selected engine; preview success is never required."
  - "The engine picker renders the full six-engine roster from Settings AI backend metadata, with a local full-roster fallback."
  - "Voice Library and character default-voice UI behavior remains scoped to pending plans 02-13 and 02-15."

patterns-established:
  - "Voice client APIs live in `src/lib/api/voices.ts` and use RayMe-owned `/api/voices` routes through `apiFetch`."
  - "Voice Lab components live under `src/lib/components/voice/` and receive explicit route-owned state."

requirements-completed: [REQ-20, REQ-21, REQ-22, REQ-90]

duration: 25 min
completed: 2026-04-25
---

# Phase 02 Plan 12: Client Voice Lab Creation Workflow Summary

**Voice Lab now uploads samples, edits transcripts, renders all six TTS engines, previews optionally, and saves voices through typed RayMe API wrappers.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-04-25T01:34:54Z
- **Completed:** 2026-04-25T01:59:46Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Added typed voice client models and wrappers for upload, transcribe, preview, save, list/detail, rename, delete, and test-play APIs.
- Built the `/voice-lab` creation route with exact steps `1 Upload`, `2 Transcript`, `3 Engine`, `4 Preview`, and `5 Save`.
- Added focused local components for the dropzone, transcript editor, six-engine picker, and synth preview panel.
- Proved browser save succeeds after preview returns HTTP 502 and that the Voice Lab route does not horizontally scroll at 320px.

## Task Commits

TDD tasks produced RED and GREEN commits:

1. **Task 1 RED: Add voice API wrapper contracts** - `a42e57d` (test)
2. **Task 1 GREEN: Add voice API client wrappers** - `fbdbe41` (feat)
3. **Task 2 RED: Add Voice Lab creation UI contracts** - `d9ff911` (test)
4. **Task 2 GREEN: Build Voice Lab creation workflow** - `4b8cb2d` (feat)

## Files Created/Modified

- `web-ui/client/src/lib/api/types.ts` - Adds TTS engine metadata and voice asset/save/preview/test/delete result types.
- `web-ui/client/src/lib/api/voices.ts` - Adds typed wrappers for the Web UI voice API.
- `web-ui/client/src/lib/components/voice/AudioSampleDropzone.svelte` - Adds WAV/MP3/FLAC upload, 6-15 second guidance, and stable sample status layout.
- `web-ui/client/src/lib/components/voice/TranscriptEditor.svelte` - Adds pending/error/retry/manual transcript editing without re-upload.
- `web-ui/client/src/lib/components/voice/TtsEnginePicker.svelte` - Adds full-roster metadata-driven engine radio cards with caveat chips.
- `web-ui/client/src/lib/components/voice/SynthPreviewPanel.svelte` - Adds optional preview text, default-engine toggle, play/pause shell, retry, and error state.
- `web-ui/client/src/routes/voice-lab/+page.svelte` - Coordinates upload, transcription, engine choice, preview, and preview-independent save.
- `web-ui/client/src/lib/components/AppShell.svelte` - Fixes mobile topbar wrapping so Voice Lab has no 320px horizontal overflow.
- `web-ui/client/tests/unit/voice-lab.test.ts` - Adds wrapper and source contracts for this plan.
- `web-ui/client/tests/e2e/voice-lab.spec.ts` - Adds browser creation-flow coverage.

## Verification

- `npm --prefix web-ui/client run test:unit -- --run tests/unit/voice-lab.test.ts tests/unit/api.test.ts` - PASS, 14 tests.
- `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts` - PASS, 4 browser-project tests.
- `rg "TtsEngineMetadata|uploadVoiceAsset|transcribeVoiceAsset|previewVoice|saveVoice|listVoices|renameVoice|deleteVoice|testPlayVoice|/voices/assets|/voices/preview|/test-play" web-ui/client/src/lib/api web-ui/client/tests/unit/voice-lab.test.ts` - PASS.
- `rg "1 Upload|2 Transcript|3 Engine|4 Preview|5 Save|Upload Sample|Transcribe Sample|Use default engine|Preview Voice|Save Voice|F5-TTS|XTTS v2|Qwen3-TTS 0.6B-Base|LuxTTS|Chatterbox Turbo|TADA 1B" web-ui/client/src/routes/voice-lab web-ui/client/src/lib/components/voice web-ui/client/tests` - PASS.

## Decisions Made

- Used `/api/settings` AI backend status as the engine metadata source because plan 02-14 already exposes compact status to the client; the route keeps a full-roster fallback for resilience.
- Kept Voice Library actions and character default-voice UI out of this plan because 02-13 and 02-15 remain pending.
- Preserved Svelte text bindings for user-controlled voice name/transcript/preview text and did not introduce raw HTML rendering in Voice Lab.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Tightened overbroad save-gate source contract**
- **Found during:** Task 2 (Build Voice Lab creation route and components)
- **Issue:** The unit source contract rejected any `disabled={...preview...}` string across all Voice Lab sources, which incorrectly caught the Preview button instead of the Save Voice gate.
- **Fix:** Changed the test to inspect the route-level `canSave` condition and verify it contains sample/name/transcript/engine without preview state.
- **Files modified:** `web-ui/client/tests/unit/voice-lab.test.ts`
- **Verification:** `npm --prefix web-ui/client run test:unit -- --run tests/unit/voice-lab.test.ts`
- **Committed in:** `4b8cb2d`

**2. [Rule 1 - Bug] Fixed mobile AppShell status overflow**
- **Found during:** Task 2 Playwright 320px viewport verification
- **Issue:** Existing AppShell status chips overflowed the topbar at 320px, causing document horizontal scroll on the new Voice Lab route.
- **Fix:** Added mobile topbar wrapping and `min-width: 0` status-row behavior.
- **Files modified:** `web-ui/client/src/lib/components/AppShell.svelte`
- **Verification:** `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts`
- **Committed in:** `4b8cb2d`

**3. [Rule 1 - Bug] Fixed Playwright locator and expected 502 console handling**
- **Found during:** Task 2 Playwright verification
- **Issue:** The E2E step-label and upload locators matched multiple accessible elements, and the expected preview HTTP 502 produced a browser console resource error that the generic error guard treated as unexpected.
- **Fix:** Made step-label assertions exact, gave the dropzone region a distinct accessible label, and allowed the deliberate preview 502 console message in this test only.
- **Files modified:** `web-ui/client/tests/e2e/voice-lab.spec.ts`, `web-ui/client/src/lib/components/voice/AudioSampleDropzone.svelte`
- **Verification:** `npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts`
- **Committed in:** `4b8cb2d`

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All fixes were required to make the planned source/browser contracts precise and to satisfy the no-horizontal-scroll acceptance criterion. Product scope did not expand beyond Voice Lab creation.

## Issues Encountered

- Playwright web server startup continues to print Vite plugin timing warnings, consistent with prior client plans. Tests passed after startup.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. Stub-pattern scan hits were nullable route state, typed test fixtures, empty test arrays, and existing AppShell pending-status labels rather than runtime stubs that block Voice Lab creation.

## Threat Flags

None. This plan introduced browser UI and client wrappers for already-planned RayMe `/api/voices` and `/api/settings` surfaces; upload extension validation and text rendering mitigations are present in the client, with server-side validation remaining authoritative.

## TDD Gate Compliance

- RED gate commits present: `a42e57d`, `d9ff911`
- GREEN gate commits present after RED commits: `fbdbe41`, `4b8cb2d`

## Next Phase Readiness

Voice Lab creation is ready for Voice Library plan 02-13 to add list/rename/delete/test-play UI and for character UI plan 02-15 to consume saved voices for default assignment and Gallery badges.

## Self-Check: PASSED

- Verified key created/modified files exist: `voices.ts`, all four `components/voice/*.svelte` files, `/voice-lab/+page.svelte`, and this summary.
- Verified task commits exist: `a42e57d`, `fbdbe41`, `d9ff911`, and `4b8cb2d`.

---
*Phase: 02-ai-backend-skeleton-voice-lab*
*Completed: 2026-04-25*
