---
phase: 08
slug: wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
status: verified
threats_open: 0
asvs_level: project-default
created: 2026-05-11
---

# Phase 08 Security Verification

## Scope

This audit verifies only the Phase 08 threat mitigations declared in the provided threat register. Implementation files were treated as read-only; this document is the only file created by the audit.

## Threat Summary

- Threats verified: 30
- Threats closed: 30
- Threats open: 0
- Accepted risks documented: 1
- Unregistered threat flags: none

## Trust Boundaries Reviewed

| Boundary | Notes |
|----------|-------|
| Web UI server to AI backend | `/api/calls` forwards bounded requests and sanitized playback failure events. |
| Browser/Web UI to AI backend `/webrtc` | Existing route surfaces are preserved; no browser-visible VoxCPM2 runtime endpoint was added. |
| AI backend route to call session | `SpeakRequest` bounds and fixed `call_tts_failed` handling are preserved before playback. |
| Call session to TTS adapter | Streaming requests are built through `TtsSynthesisInput` and bounded reference audio decoding. |
| VoxCPM2 runtime to playback queue | Only validated non-empty WAV chunks with timing and duration metadata enter playback. |
| Interrupt control to playback queue | Cancellation checks run before chunk enqueue and drain playback through existing stop logic. |
| Live runtime to evidence artifacts | Evidence is generated from live route and call-session events, then leak-checked by verifier. |
| Evidence artifacts to project docs | Decision writeback is gated on verifier success, CUDA evidence, streaming proof, and fallback rejection. |
| Local repo to OMEN runtime | Deployment evidence uses `scripts/deploy-omen.sh` and records CUDA/no-CPU-fallback runtime state. |

## Threat Verification

| Threat ID | Category | Component | Disposition | Status | Evidence |
|-----------|----------|-----------|-------------|--------|----------|
| T-08-01-01 | Information Disclosure | VoxCPM2 streaming | mitigate | CLOSED | `ai-backend/app/models/tts_voxcpm2.py:107` and `:133` use fixed stream failure; `ai-backend/app/call/session.py:1131` and `ai-backend/app/api/webrtc.py:329` map failures to fixed `call_tts_failed`; tests at `ai-backend/tests/test_tts_voxcpm2.py:327` and `ai-backend/tests/test_webrtc_signaling.py:447`. |
| T-08-01-02 | Denial of Service | TTS request bounds | mitigate | CLOSED | Reference audio constants and VoxCPM2 bounds in `ai-backend/app/models/tts_registry.py:34` and `:66`; route bounds in `ai-backend/app/api/webrtc.py:73`; call-session decode/input path in `ai-backend/app/call/session.py:84` and `:1701`. |
| T-08-01-03 | Elevation of Privilege | VoxCPM2 runtime loading | mitigate | CLOSED | CUDA guard is preserved in `ai-backend/app/models/tts_voxcpm2.py:39` and `:136`; tests at `ai-backend/tests/test_tts_voxcpm2.py:93`; OMEN/runtime evidence at `08-OMEN-EVIDENCE.md:122`; deploy CUDA checks in `scripts/deploy-omen.sh:148`. |
| T-08-01-04 | Tampering | Streamed chunk eligibility | mitigate | CLOSED | `TtsAudioChunk` metadata fields exist in `ai-backend/app/models/tts_registry.py:81`; adapter skips invalid/empty chunks and emits index/rate/duration/timing in `ai-backend/app/models/tts_voxcpm2.py:111`; tests at `ai-backend/tests/test_tts_voxcpm2.py:292`. |
| T-08-01-05 | Repudiation | Chunk timing evidence | mitigate | CLOSED | `generated_at_ms` field in `ai-backend/app/models/tts_registry.py:87`; adapter sets it in `ai-backend/app/models/tts_voxcpm2.py:121`; verifier checks timing/count fields in `08-verify-evidence.py:152`. |
| T-08-02-01 | Information Disclosure | `CallSession.speak_text` errors | mitigate | CLOSED | Fixed whole-WAV and streaming failure events in `ai-backend/app/call/session.py:895` and `:1129`; route maps failures at `ai-backend/app/api/webrtc.py:329`; leak-focused tests at `ai-backend/tests/test_call_session.py:1131` and `ai-backend/tests/test_webrtc_signaling.py:447`. |
| T-08-02-02 | Denial of Service | Reference audio/options | mitigate | CLOSED | Streaming request uses `_build_tts_synthesis_input` in `ai-backend/app/call/session.py:991`; bounded decode and registry input at `:1701`; route and registry bounds remain in `ai-backend/app/api/webrtc.py:73` and `ai-backend/app/models/tts_registry.py:34`. |
| T-08-02-03 | Elevation of Privilege | Production model path | mitigate | CLOSED | Route uses model manager resident adapter in `ai-backend/app/api/webrtc.py:495`; streaming branch only uses selected adapter in `ai-backend/app/call/session.py:807`; VoxCPM2 adapter keeps CUDA guard in `ai-backend/app/models/tts_voxcpm2.py:39`. |
| T-08-02-04 | Tampering | Interrupt after first chunk | mitigate | CLOSED | Producer and consumer check `_cancelled_ai_turns` before enqueue in `ai-backend/app/call/session.py:1006` and `:1025`; cancel drains via `stop_current()` at `:1145`; test coverage at `ai-backend/tests/test_call_session.py:1185`. |
| T-08-02-05 | Repudiation | Fallback evidence | mitigate | CLOSED | Whole-WAV and streamed paths include `streaming_used`, `fallback_used`, and `whole_wav_fallback_used` in `ai-backend/app/call/session.py:859`, `:976`, `:1064`, and `:1101`; tests at `ai-backend/tests/test_call_session.py:1109`. |
| T-08-03-01 | Information Disclosure | `/webrtc/speak` and Web UI SSE | mitigate | CLOSED | AI backend fixed detail at `ai-backend/app/api/webrtc.py:329`; backend leak tests at `ai-backend/tests/test_webrtc_signaling.py:447`; Web UI emits fixed failure in `web-ui/server/app/api/calls.py:443`; Web UI leak test at `web-ui/server/tests/test_calls.py:640`. |
| T-08-03-02 | Denial of Service | `SpeakRequest` | mitigate | CLOSED | `extra="forbid"`, text/reference/transcript limits, and numeric VoxCPM2 bounds are in `ai-backend/app/api/webrtc.py:73`; validation tests at `ai-backend/tests/test_webrtc_signaling.py:506`. |
| T-08-03-03 | Elevation of Privilege | Route surface | mitigate | CLOSED | Existing routers remain `/webrtc` in `ai-backend/app/api/webrtc.py:25` and `/api/calls` in `web-ui/server/app/api/calls.py:34`; targeted route grep found no VoxCPM2 runtime endpoint; route-surface assertion in `web-ui/server/tests/test_calls.py:631`. |
| T-08-03-04 | Tampering | Interrupt and late chunk evidence | mitigate | CLOSED | AI backend returns call-session event fields in `ai-backend/app/api/webrtc.py:348`; Web UI forwards `tts_playback` in `web-ui/server/app/api/calls.py:805`; cancellation/playback tests at `ai-backend/tests/test_webrtc_signaling.py:400` and `web-ui/server/tests/test_calls.py:800`. |
| T-08-03-05 | Repudiation | False streaming success | mitigate | CLOSED | Route/server tests prove forwarding of `streaming_used`, `fallback_used`, and `whole_wav_fallback_used` at `ai-backend/tests/test_webrtc_signaling.py:400` and `web-ui/server/tests/test_calls.py:800`; Web UI extraction at `web-ui/server/app/api/calls.py:805`. |
| T-08-04-01 | Information Disclosure | Evidence artifacts | mitigate | CLOSED | Verifier forbidden-pattern checks are in `08-verify-evidence.py:51` and `:98`; targeted leak grep over `results/voxcpm2-live-streaming-call-flow.json` and `results/voxcpm2-decision.json` returned no matches. |
| T-08-04-02 | Denial of Service | Evidence runner inputs | mitigate | CLOSED | Runner uses bounded `/webrtc/offer` and `/webrtc/sessions/{session_id}/speak` routes in `08-run-call-flow-evidence.py:263`; route contract bounds are in `ai-backend/app/api/webrtc.py:73`. |
| T-08-04-03 | Elevation of Privilege | Runtime claims | mitigate | CLOSED | Runner records runtime context in `08-run-call-flow-evidence.py:365`; live result has runtime context in `results/voxcpm2-live-streaming-call-flow.json:5`; OMEN CUDA/no-fallback evidence in `08-OMEN-EVIDENCE.md:102`. |
| T-08-04-04 | Tampering | Interrupt/cancellation claims | mitigate | CLOSED | Verifier requires immediate and final event carriers in `08-verify-evidence.py:119`; call session generates them in `ai-backend/app/call/session.py:1057` and `:1101`; live JSON proof at `results/voxcpm2-live-streaming-call-flow.json:136`. |
| T-08-04-05 | Repudiation | Fallback-as-success | mitigate | CLOSED | Verifier fails absent streaming, fallback use, whole-WAV fallback use, or losing median in `08-verify-evidence.py:145`, `:175`, and `:259`; live summary at `results/voxcpm2-live-streaming-call-flow.json:334`. |
| T-08-05-01 | Information Disclosure | Live evidence artifacts | mitigate | CLOSED | OMEN verifier pass is recorded in `08-OMEN-EVIDENCE.md:230`; sanitized evidence source recorded at `08-OMEN-EVIDENCE.md:167`; verifier leak checks in `08-verify-evidence.py:51`; result JSON leak grep returned no matches. |
| T-08-05-02 | Denial of Service | Live `/webrtc/speak` calls | mitigate | CLOSED | Runner default and CLI measured sample count is three in `08-run-call-flow-evidence.py:29` and `:391`; summary generation in `:311`; live result records three warm samples per engine at `results/voxcpm2-live-streaming-call-flow.json:10`. |
| T-08-05-03 | Elevation of Privilege | OMEN runtime path | mitigate | CLOSED | OMEN evidence cites canonical deploy in `08-OMEN-EVIDENCE.md:106` and `:174`; `cpu_fallback_detected: false` appears at `:184`; deploy script has dirty-check and CUDA checks in `scripts/deploy-omen.sh:53`, `:148`, `:218`, and `:230`. |
| T-08-05-04 | Tampering | Interrupt/call-flow semantics | mitigate | CLOSED | Verifier requires immediate first-audio metrics and final proof fields in `08-verify-evidence.py:119`; live JSON contains those proof fields at `results/voxcpm2-live-streaming-call-flow.json:136`, `:182`, and `:254`. |
| T-08-05-05 | Repudiation | Fallback evidence | mitigate | CLOSED | Verifier rejects missing streaming, fallback use, whole-WAV fallback use, and non-winning median in `08-verify-evidence.py:145`, `:175`, and `:259`; OMEN/live summary at `08-OMEN-EVIDENCE.md:242` and result JSON `:334`. |
| T-08-06-01 | Information Disclosure | Decision artifacts | mitigate | CLOSED | `--decision-ready` runs call-flow verification and decision leak checks in `08-verify-evidence.py:343` and `:347`; promotion decision references verified sanitized evidence at `08-PROMOTION-DECISION.md:23`; decision JSON at `results/voxcpm2-decision.json:1`. |
| T-08-06-02 | Denial of Service | Default decision writeback | accept | CLOSED | Accepted risk AR-08-01 documents that docs do not process runtime input; runtime DoS controls are covered by route/adapter mitigations T-08-01-02, T-08-02-02, and T-08-03-02. |
| T-08-06-03 | Elevation of Privilege | Production model default | mitigate | CLOSED | Decision-ready gate is in `08-verify-evidence.py:343`; OMEN CUDA/no-CPU evidence in `08-OMEN-EVIDENCE.md:184`; docs record promotion in `.planning/PROJECT.md:105`, `.planning/STATE.md:73`, and `.planning/ROADMAP.md:517`. |
| T-08-06-04 | Tampering | Late chunk/interrupt semantics | mitigate | CLOSED | Decision-ready first runs call-flow verifier in `08-verify-evidence.py:343`; verifier checks streaming/fallback/carriers in `:119`; decision JSON carries final proof flags at `results/voxcpm2-decision.json:8`. |
| T-08-06-05 | Repudiation | False promotion | mitigate | CLOSED | Verifier requires VoxCPM2 median below F5 and streaming/no-whole-WAV flags in `08-verify-evidence.py:145`, `:175`, and `:259`; decision JSON records those conditions at `results/voxcpm2-decision.json:6`. |

## Accepted Risks Log

| Risk ID | Threat ID | Category | Rationale | Owner | Accepted On | Review Trigger |
|---------|-----------|----------|-----------|-------|-------------|----------------|
| AR-08-01 | T-08-06-02 | Denial of Service | Phase 08 default decision writeback updates project planning docs only and does not process runtime input. Runtime DoS controls remain enforced and separately verified in the AI backend route, call session, and TTS adapter. | Project maintainer | 2026-05-11 | Revisit if planning docs become executable runtime configuration or accept untrusted live input. |

## Unregistered Flags

None. No explicit `Threat Flags` sections were present in the Phase 08 summary files, and the prompt-provided summary flag scan reported none.

## Verification Commands

```bash
python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --decision-ready
```

Result: PASS.

## Security Audit Trail

| Date | Auditor | Scope | Closed | Open | Notes |
|------|---------|-------|--------|------|-------|
| 2026-05-11 | gsd-security-auditor | Phase 08 declared threat register only | 30 | 0 | Implementation files read-only; only this SECURITY.md was written. |

## Sign-Off

- [x] All required reading loaded before analysis.
- [x] Threat register extracted from the provided Phase 08 register.
- [x] Each mitigate, accept, and transfer disposition classified and verified.
- [x] Summary threat flags incorporated.
- [x] Implementation files were not modified.
- [x] SECURITY.md written for Phase 08.
