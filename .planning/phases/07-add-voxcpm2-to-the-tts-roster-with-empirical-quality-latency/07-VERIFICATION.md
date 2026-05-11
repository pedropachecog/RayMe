---
phase: 07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
verified: 2026-05-11T12:14:34Z
status: passed
score: 38/38 must-haves verified
overrides_applied: 0
---

# Phase 7: Add VoxCPM2 to the TTS roster with empirical quality, latency, VRAM, and call-flow evaluations Verification Report

**Phase Goal:** Add VoxCPM2 as a first-class visible TTS roster candidate and decide, from RayMe-specific evidence, whether it is promoted, selectable with caveats, visible unavailable, or rejected from runtime loading.
**Verified:** 2026-05-11T12:14:34Z
**Status:** passed
**Re-verification:** No - initial verification

## Goal Achievement

VoxCPM2 is present as a first-class visible TTS roster candidate and the final outcome is evidence-backed `selectable_with_caveats`, not default promotion. Runtime, matrix, call-flow, VRAM, and manual quality artifacts all exist and agree with that outcome.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | VoxCPM2 is visible in backend metadata before runtime promotion. | VERIFIED | `ai-backend/app/models/tts_registry.py` includes `voxcpm2` in `EXPECTED_ENGINE_IDS`, `TTS_ENGINE_METADATA`, and `build_default_tts_adapters`; `f5` remains the single default. |
| 2 | VoxCPM2 runtime loading is CUDA-only, optional-package gated, and engine-scoped. | VERIFIED | `ai-backend/app/models/tts_voxcpm2.py` requires `voxcpm`, calls `require_torch_cuda_runtime("VoxCPM2")`, loads `openbmb/VoxCPM2`, and rejects runtimes without CUDA parameters. |
| 3 | Bounded VoxCPM2 synthesis options flow through transient `/tts/synthesize`. | VERIFIED | `ai-backend/app/api/tts.py` validates `voxcpm2_*` fields, bounds text/style/reference audio, creates `TtsSynthesisInput`, and returns sanitized `tts_failed` errors. |
| 4 | Voice Lab and Web UI server persist VoxCPM2 mode/style metadata and reuse it for preview/test-play. | VERIFIED | `web-ui/server/app/domain/voice_service.py` normalizes `metadata.engine_settings.voxcpm2`; `web-ui/server/app/api/voices.py` flattens it into AI backend `voxcpm2_*` payload fields only when engine is `voxcpm2`. |
| 5 | Client Voice Lab renders VoxCPM2 from fallback/backend rosters and shows controls only for VoxCPM2. | VERIFIED | `web-ui/client/src/routes/voice-lab/+page.svelte` contains fallback `VoxCPM2` metadata and renders `<VoxCpm2Controls>` only under `selectedEngine === 'voxcpm2'`; controls are implemented in `VoxCpm2Controls.svelte`. |
| 6 | Saved VoxCPM2 voice metadata reaches real call playback through existing APIs. | VERIFIED | `web-ui/server/app/domain/call_service.py` adds `voxcpm2_*` fields to voice references; `ai-backend/app/api/webrtc.py` accepts bounded `voxcpm2_*` speak fields; `ai-backend/app/call/session.py` forwards them into adapter synthesis. |
| 7 | Call failures are sanitized and existing interrupt/cancel behavior is preserved. | VERIFIED | WebRTC speak route uses fixed `call_tts_failed` handling, bounded validation, and `results/voxcpm2-call-flow.json` records `sanitized_failures_checked: true` and `interrupt_cancel_unchanged: true`. |
| 8 | Scenario matrix evidence covers short, medium, and long VoxCPM2 rows using shared planner fields and F5 comparison. | VERIFIED | `results/voxcpm2-scenario-matrix.json` has 15 measured rows, including VoxCPM2 baseline/standard/streaming-collected rows for `short_reply`, `medium_reply`, and `long_reply`, plus F5 comparator rows and promotion comparison fields. |
| 9 | OMEN runtime evidence was captured through the canonical deploy script only. | VERIFIED | `scripts/deploy-omen.sh` contains the `RAYME_OMEN_VERIFY_VOXCPM2` verification path and writes canonical launchers; runtime evidence JSON records OMEN CUDA/VRAM data. No alternate OMEN deploy script was introduced. |
| 10 | Runtime smoke proves `voxcpm==2.0.2`, CUDA, model id, 48 kHz output, and no CPU fallback. | VERIFIED | `results/voxcpm2-runtime-smoke.json` records `package: voxcpm==2.0.2`, `model_id: openbmb/VoxCPM2`, `device: cuda`, `runtime_sample_rate: 48000`, and `cpu_fallback_detected: false`. |
| 11 | VRAM evidence remains within RTX 3060 budget while STT/VAD and resident F5 coexist. | VERIFIED | `results/voxcpm2-vram-soak.json` records peak `6941 MB` against `11264 MB` budget, `vad_ready: true`, `stt_model: distil-large-v3`, and resident `live_ai_backend:f5`. |
| 12 | Real preview, test-play, and WebRTC call speak evidence uses existing RayMe APIs. | VERIFIED | `results/voxcpm2-call-flow.json` has `preview_passed`, `test_play_passed`, `call_speak_passed`, `call_audio_enqueued`, and endpoint labels rather than VoxCPM2-specific routes. |
| 13 | Manual listening covers quality dimensions and supports the final decision. | VERIFIED | `MANUAL-QUALITY.csv` scores VoxCPM2 short/medium/long at 5/5 across intelligibility, voice match, accent preservation, prosody, leakage, and mumbling, all `pass=true`; F5 comparator rows fail. |
| 14 | Final decision is evidence-backed `selectable_with_caveats` rather than default promotion. | VERIFIED | `07-PROMOTION-DECISION.md`, `results/voxcpm2-decision.json`, `.planning/ROADMAP.md`, and `.planning/STATE.md` all record `selectable_with_caveats`; rationale cites slower current live call TTFA because RayMe calls do not yet consume VoxCPM2 streaming chunks. |

**Score:** 38/38 plan truth must-haves verified, represented by the grouped truths above.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `ai-backend/tests/test_tts_voxcpm2.py` | Adapter contracts | VERIFIED | Artifact verifier passed; backend suite later passed. |
| `ai-backend/tests/test_tts_registry.py` | Roster/API contracts | VERIFIED | Artifact verifier passed; review fixes added reference-audio limit coverage. |
| `ai-backend/tests/test_model_manager.py` | One-hot residency coverage | VERIFIED | Artifact verifier passed. |
| `ai-backend/app/models/tts_voxcpm2.py` | Import-gated CUDA adapter | VERIFIED | 204 substantive lines; wired through registry default adapters. |
| `ai-backend/app/models/tts_registry.py` | Metadata and synthesis input contract | VERIFIED | Includes VoxCPM2 metadata, bounded `TtsSynthesisInput`, and adapter builder. |
| `ai-backend/app/api/tts.py` | `/tts/synthesize` option bridge | VERIFIED | Bounded Pydantic fields, decoded-audio byte limit, sanitized 502. |
| `ai-backend/app/api/webrtc.py` | Speak request option bridge | VERIFIED | Bounded `SpeakRequest` fields and oversized-reference guard. |
| `ai-backend/app/call/session.py` | Call synthesis forwarding | VERIFIED | `voxcpm2_options` forwarded for generic adapters and `synthesize_call_text` adapters. |
| `web-ui/server/app/domain/voice_service.py` | Durable voice metadata normalization | VERIFIED | Normalizes, merges, and engine-scopes VoxCPM2 settings. |
| `web-ui/server/app/api/voices.py` | Preview/test-play payload bridge | VERIFIED | Emits flat `voxcpm2_*` fields only for VoxCPM2. |
| `web-ui/server/app/domain/call_service.py` | Call voice reference metadata | VERIFIED | Saved metadata becomes `voxcpm2_*` fields for call speak. |
| `web-ui/server/app/api/calls.py` | Existing call route forwarding | VERIFIED | Uses existing call/SSE route; no VoxCPM2-specific public route found. |
| `web-ui/client/src/routes/voice-lab/+page.svelte` | Voice Lab state and payload wiring | VERIFIED | Fallback roster, conditional control rendering, preview/save metadata payloads. |
| `web-ui/client/src/lib/components/voice/VoxCpm2Controls.svelte` | Conditional mode/style UI | VERIFIED | Mode radios, style prompt, bounded numeric inputs, normalize/denoise toggles, missing-transcript warning. |
| `web-ui/client/src/lib/api/types.ts` | Typed VoxCPM2 payloads | VERIFIED | Includes `voxcpm2` engine id and `VoxCpm2EngineSettings`. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/MANUAL-QUALITY.csv` | Manual quality scores | VERIFIED | Required columns and scored VoxCPM2/F5 rows present. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-PROMOTION-DECISION.md` | Final outcome | VERIFIED | Outcome `selectable_with_caveats`; evidence and caveat documented. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-decision.json` | Machine-readable decision | VERIFIED | Valid JSON with quality/runtime/call-flow/VRAM booleans all true and final outcome. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-scenario-matrix.json` | Live matrix | VERIFIED | Verifier passed; rows and sample paths present. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/audio/` | Generated WAV samples | VERIFIED | Directory exists with 17 files, including VoxCPM2 standard/streaming/baseline and F5 comparator WAVs. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-runtime-smoke.json` | Runtime package/model/CUDA evidence | VERIFIED | Valid JSON, CUDA and 48 kHz evidence present. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-vram-soak.json` | VRAM soak evidence | VERIFIED | Valid JSON, within budget. |
| `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/voxcpm2-call-flow.json` | Preview/test-play/call evidence | VERIFIED | Valid JSON, all key call-flow booleans true. |
| `scripts/deploy-omen.sh` | Canonical deployment/runtime verification path | VERIFIED | `bash -n` passed; VoxCPM2 verification path exists inside canonical deploy script. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| Backend tests | Backend registry/adapter/API | Contract assertions | VERIFIED | `verify.key-links` passed for plans 07-01 and 07-05. |
| Voice Lab client | Web UI voices API | `previewVoice`/`saveVoice` metadata payloads | VERIFIED | Multiline manual grep found `engine_settings: { voxcpm2: ... }` in `+page.svelte`; API bridge flattens settings. |
| Web UI voice service | Voices API | `metadata.engine_settings.voxcpm2` | VERIFIED | `verify.key-links` passed for plan 07-06. |
| Web UI call service/API | AI backend WebRTC speak | `speak_call` payload | VERIFIED | `call_service.py` extracts saved settings; `webrtc.py` accepts fields; `verify.key-links` passed for plan 07-08. |
| Scenario matrix runner | VoxCPM2 runtime adapter | Runtime generation path | VERIFIED | `verify.key-links` passed for plan 07-09. |
| Deploy script | OMEN SSH runtime verification | `RAYME_OMEN_VERIFY_VOXCPM2` | VERIFIED | `verify.key-links` passed for plan 07-10. |
| Call-flow evidence runner | Existing RayMe APIs | `/tts/synthesize`, `/api/voices/*`, `/webrtc/sessions/{session_id}/speak` | VERIFIED | `verify.key-links` passed for plan 07-11; call-flow JSON confirms live preview/test-play/call speak. |
| Promotion decision | Durable state | Decision writeback | VERIFIED | `verify.key-links` passed for plan 07-12; `.planning/STATE.md` and `ROADMAP.md` record final outcome. |
| Scenario matrix test/schema | Scenario matrix artifact | Required short/medium/long rows | VERIFIED | Raw grep checker missed JSON ordering; manual `jq` check confirms VoxCPM2 `short_reply`, `medium_reply`, and `long_reply` rows. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `tts_registry.py` | `TTS_ENGINE_METADATA` / adapters | Static roster plus `build_default_tts_adapters()` | Yes - consumed by backend model manager/status and tests | VERIFIED |
| `tts_voxcpm2.py` | `TtsSynthesisInput` VoxCPM2 fields | `/tts/synthesize`, WebRTC speak, call session | Yes - passed to runtime `generate()` kwargs | VERIFIED |
| `voice_service.py` | `metadata.engine_settings.voxcpm2` | Saved Voice Lab metadata | Yes - normalized/persisted and reused for preview/test-play | VERIFIED |
| `+page.svelte` | `engineSettings.voxcpm2` | Route-owned state and `VoxCpm2Controls` binding | Yes - included in preview/save payloads when VoxCPM2 selected | VERIFIED |
| `call_service.py` | Saved voice metadata | Database voice record and sample asset | Yes - encoded sample and `voxcpm2_*` fields returned to call API | VERIFIED |
| `webrtc.py` / `session.py` | `SpeakRequest` VoxCPM2 fields | Existing WebRTC speak route | Yes - forwarded into `session.speak_text()` and adapter synthesis | VERIFIED |
| Evidence artifacts | Decision booleans/metrics | Runtime smoke, VRAM soak, matrix, call-flow, manual CSV | Yes - `07-verify-evidence.py --decision-ready` passed | VERIFIED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Decision evidence is complete | `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --decision-ready` | PASS | PASS |
| Schema drift absent | `gsd-sdk query verify.schema-drift "07"` | `drift_detected: false` | PASS |
| Deploy script syntax valid | `bash -n scripts/deploy-omen.sh` | syntax OK | PASS |
| Decision JSON parses | `python3 -m json.tool .../results/voxcpm2-decision.json` | valid JSON | PASS |
| Scenario matrix has VoxCPM2 short/medium/long rows | `jq -e '([.rows[] | select(.engine=="voxcpm2") | .scenario] | unique) == ["long_reply","medium_reply","short_reply"]' .../voxcpm2-scenario-matrix.json` | true | PASS |
| Backend tests after review fixes | `uv run --project ai-backend pytest ai-backend/tests -q` | 120 passed, 3 warnings (orchestrator evidence) | PASS |
| Web UI server tests after review fixes | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_calls.py -q` | 52 passed (orchestrator evidence) | PASS |
| Voice Lab unit tests after review fixes | `npm --prefix web-ui/client run test:unit -- --run tests/unit/voice-lab.test.ts` | 13 passed (orchestrator evidence) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REQ-02 | 07-01, 07-04, 07-05, 07-09, 07-10, 07-11, 07-12 | AI backend targets RTX 3060 with STT, VAD, and one resident TTS engine coexisting. | SATISFIED | Runtime/VRAM evidence shows RTX 3060, CUDA, STT/VAD ready, F5 resident, VoxCPM2 standalone probe within budget. |
| REQ-20 | 07-02, 07-06, 07-07, 07-11, 07-12 | Voice Lab sample upload. | SATISFIED | Voice Lab preview/save paths reuse existing sample asset flow; call-flow evidence used a saved voice asset. |
| REQ-21 | 07-02, 07-06, 07-07, 07-11, 07-12 | Editable reference transcript captured for engines. | SATISFIED | VoxCPM2 metadata supports transcript-guided mode and falls back with warning when transcript is blank. |
| REQ-22 | 07-01, 07-02, 07-05, 07-06, 07-07, 07-12 | Voice save captures engine and voice metadata. | SATISFIED | Voice Lab and server persist `metadata.engine_settings.voxcpm2`; backend roster includes VoxCPM2. |
| REQ-23 | 07-02, 07-06, 07-07, 07-11, 07-12 | Voice Library test-play works. | SATISFIED | Test-play reuses saved VoxCPM2 settings; call-flow JSON records `test_play_passed: true`. |
| REQ-24 | 07-02, 07-06, 07-12 | Deleting referenced voices must be safe. | SATISFIED | Existing voice service behavior preserved; Phase 07 metadata additions do not bypass delete reference checks, and tests passed. |
| REQ-41 | 07-03, 07-08, 07-11, 07-12 | Full-duplex call audio. | SATISFIED | Existing WebRTC call speak path is reused; call-flow JSON records session creation, speak pass, and audio enqueued. |
| REQ-42 | 07-03, 07-08, 07-11, 07-12 | VAD-driven barge-in/cancel behavior. | SATISFIED | `interrupt_cancel_unchanged: true` in call-flow evidence and AI backend call tests passed. |
| REQ-45 | 07-01, 07-04, 07-05, 07-09, 07-10, 07-11, 07-12 | Shared chunked TTS playback and metrics for every engine. | SATISFIED | Matrix rows include VoxCPM2 shared chunked and streaming-collected profiles with TTFA/RTF/sample paths; decision caveat correctly notes call playback does not yet consume VoxCPM2 streaming chunks. |
| REQ-62 | 07-03, 07-08, 07-11, 07-12 | AI call audio saved per turn by default. | SATISFIED | Call-flow evidence records `saved_ai_audio_path: results/audio/voxcpm2__call_flow_test_play.wav`. |
| REQ-80 | 07-01, 07-02, 07-05, 07-06, 07-07, 07-12 | Settings/roster surfaces TTS engine default/options. | SATISFIED | Backend status metadata and client fallback roster expose VoxCPM2; F5 remains default. |
| REQ-A3 | 07-01, 07-04, 07-05, 07-09, 07-10, 07-11, 07-12 | English-only v1 quality bar. | SATISFIED | Manual quality used English sample rows and judged VoxCPM2 quality/accent preservation pass. |

No orphaned Phase 7 requirement IDs found: the plan frontmatter union exactly matches the user-provided set and ROADMAP Phase 7 requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | - | - | - | Stub scan found only legitimate guard/default returns such as non-VoxCPM2 empty option maps and missing-audio `null` UI fallback. No TODO/FIXME/placeholders, console-only handlers, or hardcoded empty dynamic data blocking the goal were found. |

### Human Verification Required

None outstanding. The phase's required human listening gate is already completed in `MANUAL-QUALITY.csv` by Pedro, and the final decision cites that evidence. Live OMEN/runtime behavior was not re-run during this verifier pass, but existing machine-readable evidence was schema-checked and passed.

### Gaps Summary

No blocking gaps found. VoxCPM2 is visible and selectable with caveats, runtime loading is CUDA-gated, Voice Lab and call-flow settings are wired, RayMe-specific evidence exists, and durable state records the evidence-backed `selectable_with_caveats` outcome. The caveat that live calls still wait for full VoxCPM2 synthesis is correctly reflected in the decision and is not a Phase 7 gap because the requested outcome allows selectable-with-caveats.

---

_Verified: 2026-05-11T12:14:34Z_
_Verifier: Claude (gsd-verifier)_
