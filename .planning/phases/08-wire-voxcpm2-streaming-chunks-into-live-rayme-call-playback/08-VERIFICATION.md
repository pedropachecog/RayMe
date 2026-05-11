---
phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
verified: 2026-05-11T19:34:11Z
status: passed
score: 19/19 must-haves verified
overrides_applied: 0
---

# Phase 8: Wire VoxCPM2 Streaming Chunks Into Live RayMe Call Playback Verification Report

**Phase Goal:** Live RayMe calls using VoxCPM2 start audible playback from VoxCPM2 streaming audio chunks and beat F5 warm first-audio time in the same live evidence run; if that passes, RayMe updates its durable call-engine decision toward VoxCPM2.
**Verified:** 2026-05-11T19:34:11Z
**Status:** passed
**Re-verification:** No - initial verification

## Goal Achievement

The Phase 8 goal is achieved. The implementation adds an internal VoxCPM2 streaming path, wires it into `CallSession` live playback for `voxcpm2`, preserves existing `/webrtc` and Web UI call surfaces, and records live RTX 3060 evidence where VoxCPM2 warm first-audio beats F5 (`762.7 ms` vs `948.0 ms`) with `streaming_used=true` and `whole_wav_fallback_used=false`.

The roadmap entry has no `success_criteria` array in `gsd-sdk roadmap.get-phase "8"`, so verification uses the six PLAN frontmatter `must_haves` plus the locked `08-SPEC.md` requirements. `gsd-sdk roadmap.get-phase "08"` did not resolve the zero-padded phase number; `gsd-sdk roadmap.get-phase "8"` did.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | VoxCPM2 exposes an internal streaming audio path in the AI backend. | VERIFIED | `TtsAudioChunk` and `TtsStreamingAdapter` exist in `tts_registry.py`; `VoxCpm2TtsAdapter.stream()` exists in `tts_voxcpm2.py`. |
| 2 | The first valid VoxCPM2 stream chunk is serialized as playable WAV bytes without collecting all chunks first. | VERIFIED | `stream()` yields per-chunk WAV bytes from `generate_streaming`; tests assert WAV chunks and no `runtime.generate()` fallback. |
| 3 | Empty or invalid VoxCPM2 chunks cannot become queued playback evidence. | VERIFIED | Empty chunks are skipped and all-empty streams raise `VoxCPM2 streaming synthesis failed`; tests assert no fallback. |
| 4 | VoxCPM2 call playback queues the first streamed chunk before stream completion. | VERIFIED | `CallSession._speak_streaming_speech()` queues chunks as they arrive; test waits for first `ai_audio_started` before releasing chunk 2. |
| 5 | Interrupt after first streamed chunk prevents later chunks from enqueueing. | VERIFIED | Streaming interrupt test leaves one queued chunk, calls track stop once, emits `interrupted`, and emits no `ai_done`. |
| 6 | The AI backend emits one `ai_done` for one streamed final AI turn. | VERIFIED | Test asserts event sequence `ai_audio_started`, `ai_done` and exactly one done event. |
| 7 | Existing `/webrtc/sessions/{session_id}/speak` exposes streaming timing without a new VoxCPM2 public route. | VERIFIED | Route calls `session.speak_text(...)` and returns nested `event`; grep found no VoxCPM2-specific Web UI route. |
| 8 | Web UI call SSE forwards the first-audio event and keeps one durable `ai_speech` row. | VERIFIED | `_extract_ai_audio_started_event()` forwards nested event; server test asserts one SSE `ai_audio_started` and one `ai_speech` row. |
| 9 | Sanitized `call_tts_failed` behavior is unchanged for streaming failures. | VERIFIED | WebRTC test asserts fixed `call_tts_failed` 502 and no traceback/path/model leaks. |
| 10 | Phase 8 evidence cannot pass without live streaming proof fields. | VERIFIED | `08-verify-evidence.py` requires immediate/final streaming fields and rejects missing fields/fallback. |
| 11 | Warm VoxCPM2 and F5 samples are compared by median first-audio timing. | VERIFIED | Runner records three warm samples per engine; verifier recomputes medians and checks reported summary values. |
| 12 | The verifier rejects whole-WAV fallback as Phase 8 success evidence. | VERIFIED | Verifier requires `whole_wav_fallback_used=false` in immediate and final VoxCPM2 metrics. |
| 13 | Dirty OMEN checkout changes are never committed, discarded, reset, or otherwise mutated without explicit user direction. | VERIFIED | `08-OMEN-EVIDENCE.md` records dirty status, user `preserve` direction, preservation branch, and clean post-preservation status before deploy. |
| 14 | Live OMEN evidence was produced after canonical deployment through `scripts/deploy-omen.sh`. | VERIFIED | Evidence log records canonical deploy commands only; `scripts/deploy-omen.sh` writes runtime/VRAM JSON markers when `RAYME_OMEN_VERIFY_VOXCPM2=1`. |
| 15 | Same-run warm VoxCPM2 median first-audio is lower than same-run warm F5 median first-audio. | VERIFIED | `voxcpm2-live-streaming-call-flow.json` summary: VoxCPM2 `762.7 ms`, F5 `948.0 ms`, `voxcpm2_beats_f5=true`. |
| 16 | Evidence records CUDA runtime context, fallback flags, chunk counts, and single-turn call-flow behavior. | VERIFIED | Runtime smoke and VRAM artifacts record CUDA RTX 3060 context; call-flow JSON records flags and chunk counts. Single-turn behavior is locked by backend/Web UI tests. |
| 17 | Durable RayMe decisions cite Phase 8 live VoxCPM2-vs-F5 evidence. | VERIFIED | `PROJECT.md`, `STATE.md`, `ROADMAP.md`, `08-PROMOTION-DECISION.md`, and `voxcpm2-decision.json` cite the evidence path and median values. |
| 18 | VoxCPM2 becomes the preferred/default live-call TTS choice only after the verifier passes. | VERIFIED | `08-PROMOTION-DECISION.md` and `voxcpm2-decision.json` were created after `08-verify-evidence.py --decision-ready`; local rerun passed. |
| 19 | F5 remains available but no longer wins the call-feel default on speed. | VERIFIED | Durable decision text keeps F5 as fallback/comparator while promoting VoxCPM2 for live-call default. |

**Score:** 19/19 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `ai-backend/app/models/tts_registry.py` | Internal streaming chunk contract | VERIFIED | `TtsAudioChunk`, `TtsStreamingAdapter`, and `supports_streaming=True` for VoxCPM2 exist; `gsd-sdk verify.artifacts` passed. |
| `ai-backend/app/models/tts_voxcpm2.py` | VoxCPM2 `generate_streaming` adapter | VERIFIED | `stream()` calls `generate_streaming`, serializes chunks as WAV, skips invalid chunks, and raises on empty stream. |
| `ai-backend/tests/test_tts_voxcpm2.py` | Adapter coverage | VERIFIED | Covers exported stream contract, timed WAV chunks, empty-stream rejection, and no whole-generation fallback. |
| `ai-backend/app/call/session.py` | Streaming playback lifecycle | VERIFIED | `speak_text()` selects `_speak_streaming_speech()` for VoxCPM2 and queues each chunk through `_queue_outbound_audio`. |
| `ai-backend/tests/test_call_session.py` | First enqueue, cancellation, single completion | VERIFIED | Covers first chunk before stream completion, interrupt after first chunk, and one final `ai_done`. |
| `ai-backend/app/api/webrtc.py` | Stable speak response wrapping metrics | VERIFIED | Route forwards `session.speak_text(...)` payload and sanitizes `call_tts_failed`. |
| `web-ui/server/app/api/calls.py` | SSE keepalive and nested audio-start forwarding | VERIFIED | Keeps long TTS request alive, forwards nested `ai_audio_started_event`, and persists final visible text once. |
| `ai-backend/tests/test_webrtc_signaling.py` | Route tests | VERIFIED | Covers streaming metrics and sanitized streaming failures. |
| `web-ui/server/tests/test_calls.py` | Web UI server tests | VERIFIED | Covers nested first-audio SSE and one durable `ai_speech` row. |
| `08-run-call-flow-evidence.py` | Repeated warm live evidence runner | VERIFIED | Calls `/webrtc/offer` and `/webrtc/sessions/{session_id}/speak`, captures immediate first-audio and final metrics. |
| `08-verify-evidence.py` | Machine-readable evidence gate | VERIFIED | Recomputes medians, rejects fallback, rejects final-only fields in immediate carrier, checks raw leak patterns. |
| `results/README.md` | Result artifact inventory | VERIFIED | Artifact exists and passed SDK artifact check. |
| `08-OMEN-EVIDENCE.md` | Human-readable live evidence log | VERIFIED | Records dirty preflight, preservation, canonical deploy, runtime/VRAM, live runner, and verifier output. |
| `results/voxcpm2-live-streaming-call-flow.json` | Machine-readable repeated warm comparison | VERIFIED | Contains three measured F5 and three measured VoxCPM2 samples plus summary. |
| `results/voxcpm2-runtime-smoke.json` | CUDA runtime/package evidence | VERIFIED | Records `voxcpm==2.0.2`, `openbmb/VoxCPM2`, RTX 3060, CUDA torch, 48 kHz, no CPU fallback. |
| `results/voxcpm2-vram-soak.json` | VRAM budget evidence | VERIFIED | Peak 6544 MB, budget 11264 MB, no CPU fallback, `within_11gb_budget=true`. |
| `08-PROMOTION-DECISION.md` | Human-readable Phase 8 decision | VERIFIED | Outcome `promoted_for_live_call_default`, preferred `voxcpm2`, fallback `f5`, evidence values cited. |
| `results/voxcpm2-decision.json` | Machine-readable Phase 8 decision | VERIFIED | Preferred engine `voxcpm2`, fallback `f5`, evidence values and flags match call-flow JSON. |
| `.planning/PROJECT.md` | Durable project-level decision | VERIFIED | Adds Phase 8 live-call default `voxcpm2` and evidence path. |
| `.planning/STATE.md` | Current decision and phase status | VERIFIED | Records Phase 8 completion, live-call default, evidence result, and preservation policy. |
| `.planning/ROADMAP.md` | Roadmap final outcome wording | VERIFIED | Phase 8 marked complete with final outcome and first-audio evidence. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tts_voxcpm2.py` | `tts_registry.py` | `TtsAudioChunk` import and yielded model | WIRED | SDK verified; import appears at `tts_voxcpm2.py:14-19`, yield at `tts_voxcpm2.py:121`. |
| `session.py` | `tts_registry.py` | `TtsStreamingAdapter`/`TtsAudioChunk` | WIRED | SDK verified; imports at `session.py:40-41`, use at `session.py:957` and `session.py:1028`. |
| `session.py` | outbound track | `_queue_outbound_audio` per streamed WAV chunk | WIRED | Streaming branch calls `_queue_outbound_audio()` for each chunk at `session.py:1047`. |
| `webrtc.py` | `session.py` | `session.speak_text(...)` return payload | WIRED | Route calls `speak_text` at `webrtc.py:293` and returns the event wrapper. |
| `calls.py` | AI backend speak result | `_extract_ai_audio_started_event` | WIRED | `speak_call` result is inspected at `calls.py:462`; extractor checks nested `event.ai_audio_started_event`. |
| `08-run-call-flow-evidence.py` | `/webrtc/sessions/{session_id}/speak` | immediate and final metrics | WIRED | Manual verification; SDK regex missed multiline code. Runner posts to speak route and extracts `event["ai_audio_started_event"]["tts_playback"]` and `event["tts_playback_final"]`. |
| `08-verify-evidence.py` | `voxcpm2-live-streaming-call-flow.json` | median comparison and fallback rejection | WIRED | Manual verification; SDK regex missed separate-field layout. Verifier requires summary fields, recomputes medians, and rejects fallback. |
| `scripts/deploy-omen.sh` | runtime/VRAM JSON artifacts | `RAYME_OMEN_VERIFY_VOXCPM2=1` markers | WIRED | Manual verification; env handling and JSON marker extraction exist in `scripts/deploy-omen.sh:7-9` and `:366-407`; evidence log records canonical commands. |
| `voxcpm2-live-streaming-call-flow.json` | durable project docs | median values in decision wording | WIRED | Manual verification; plan key-link source was relative and SDK could not resolve it. Values appear in `PROJECT.md`, `STATE.md`, `ROADMAP.md`, decision markdown, and decision JSON. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `VoxCpm2TtsAdapter.stream()` | `TtsAudioChunk.wav_bytes`, timing fields | `runtime.generate_streaming(**generate_kwargs)` | Yes | FLOWING - chunks are produced from runtime stream, serialized as WAV, and yielded one at a time. |
| `CallSession._speak_streaming_speech()` | `audio_started_event.tts_playback` | First `TtsAudioChunk` consumed from adapter stream | Yes | FLOWING - first chunk is queued before stream completion and event emits immediate timing. |
| `CallSession._speak_streaming_speech()` | `tts_playback_final` | Accumulated chunk count, gaps, generation/playback timing | Mostly | FLOWING with residual metric risk - final `total_generation_ms` is inflated by playback wait; not used for promotion decision. |
| `/webrtc/sessions/{session_id}/speak` | returned `event` | `session.speak_text(...)` | Yes | FLOWING - route returns nested immediate/final metrics unless sanitized failure is raised. |
| Web UI call SSE | `ai_audio_started` SSE event | `AiBackendClient.speak_call` result | Yes | FLOWING - extractor forwards nested event; test proves one durable speech row remains. |
| `voxcpm2-live-streaming-call-flow.json` | `summary.voxcpm2_warm_call_ttfa_ms`, `summary.f5_warm_call_ttfa_ms` | Live `/webrtc/speak` first-audio event metrics | Yes | FLOWING - runner captures `ai_audio_started_ms`; verifier recomputes medians from samples. |
| `voxcpm2-decision.json` and project docs | preferred/default decision | Verified call-flow evidence | Yes | FLOWING - decision artifact and docs cite same evidence values. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 8 decision evidence passes strict verifier | `python3 .../08-verify-evidence.py --decision-ready` | `PASS` | PASS |
| Evidence-script unit contracts pass | `python3 .../tests/test_08_verify_evidence.py && python3 .../tests/test_08_call_flow_runner.py` | 4 unittest cases passed | PASS |
| AI backend streaming/call/WebRTC contracts pass | `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` | 77 passed, 3 warnings | PASS |
| Web UI call facade contracts pass | `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` | 31 passed | PASS |
| Schema drift check passes | `gsd-sdk query verify.schema-drift "08" --raw` | `drift_detected=false`, `blocking=false` | PASS |
| Live call-flow invariant spot check | Python JSON assertions over live call-flow artifact | `call-flow invariants ok` | PASS |

### Requirements Coverage

`P8-R1` through `P8-R5` are absent from `.planning/REQUIREMENTS.md`; that file contains global `REQ-*` IDs only. They are phase-local IDs from `08-SPEC.md` and PLAN frontmatter, and are judged against the phase spec/plan artifacts.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| P8-R1 | 08-SPEC, 08-01, 08-02, 08-03 | VoxCPM2 live chunk playback | SATISFIED | `stream()` yields chunks; `CallSession` queues first chunk before completion; `/webrtc` exposes metrics. |
| P8-R2 | 08-SPEC, 08-04, 08-05 | Faster than F5 in live evidence | SATISFIED | Same-run warm medians: VoxCPM2 `762.7 ms`, F5 `948.0 ms`; verifier passed. |
| P8-R3 | 08-SPEC, 08-01, 08-02, 08-03, 08-05 | Interrupt/barge-in preservation and sanitized failures | SATISFIED | `interrupt()` cancels active task/stops track; streaming interrupt test prevents late enqueue and no duplicate done; route failure test sanitizes. |
| P8-R4 | 08-SPEC, 08-02, 08-03, 08-05 | Single call turn semantics | SATISFIED | Backend emits one `ai_done`; Web UI test persists one `ai_speech` row for streamed metrics. |
| P8-R5 | 08-SPEC, 08-04, 08-06 | Evidence-gated decision writeback | SATISFIED | `--decision-ready` passes; decision JSON and PROJECT/STATE/ROADMAP agree on VoxCPM2 preferred/default live-call TTS. |

No orphaned Phase 8 requirement IDs were found in `.planning/REQUIREMENTS.md`.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `ai-backend/app/call/session.py` | 977 | Streamed `total_generation_ms` computed after playback wait | Warning | Non-blocking residual risk. The Phase 8 promotion gate uses immediate `ai_audio_started_ms` from `ai_audio_started_event.tts_playback`, not `tts_playback_final.total_generation_ms`; follow-up should fix this before using total generation time for model/runtime comparisons. |
| `ai-backend/app/models/tts_registry.py`, `ai-backend/app/config.py`, `web-ui/server/app/domain/settings_service.py` | 156/249, 10, 137 | Runtime/global defaults still identify F5 as the resident or settings default | Info | Not a Phase 8 gap because `08-SPEC.md` acceptance scoped decision/default writeback to PROJECT/STATE/ROADMAP and Phase 8 decision artifacts. Future work should decide whether runtime default settings should also switch to VoxCPM2. |

Stub scan found only normal list/dict initializers, test fixtures, and pre-existing policy text. No placeholder implementations or orphaned Phase 8 artifacts were found.

### Human Verification Required

None. The phase is playback/evidence/backend-call behavior, not a visual UI acceptance phase. Live OMEN evidence is already machine-readable and passed the strict verifier.

### Gaps Summary

No blocking gaps found.

The code-review warning about `total_generation_ms` is real but does not invalidate the Phase 8 goal because the goal and promotion decision depend on first-audio timing, and that comes from the immediate first-audio carrier before playback wait. The report records it as residual risk for future metrics use, not as a failed must-have.

No deferred items were identified. `gsd-sdk roadmap.analyze --raw` lists no later phase with number greater than 8 in the current roadmap data.

---

_Verified: 2026-05-11T19:34:11Z_
_Verifier: Codex (gsd-verifier)_
