---
phase: 03-first-working-call-mvp
verified: 2026-05-12T01:09:05Z
status: passed
score: 5/5 success criteria verified
overrides_applied: 0
---

# Phase 03: First Working Call MVP Verification Report

**Phase Goal:** Establish the media plumbing end-to-end: browser
`RTCPeerConnection` to aiortc, Android-safe AudioContext unlock, orchestrator
FSM skeleton, and a single-sentence non-streaming reply so Phase 4 can build on
known-working transport.

**Verified:** 2026-05-12T01:09:05Z
**Status:** passed

## Goal Achievement

Phase 3 achieved the First Working Call MVP goal. The implemented call path
starts from a thread or character, negotiates browser media through same-origin
Web UI call routes into the AI backend WebRTC session, finalizes user speech
through VAD/STT, streams an LLM response through the Web UI server, plays TTS
audio, persists call rows, supports mute/end/reconnect behavior, and has both
agent-run and physical Android acceptance evidence.

## Success Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Desktop Chrome can start a call, hear AI response, end, and persist call rows. | VERIFIED | `03-10-SUMMARY.md`, `PLAYWRIGHT-EVIDENCE.md`, `03-12-SUMMARY.md`; final desktop sweep passed `call-start.spec.ts` and `call-summary.spec.ts` with `16 passed`. |
| 2 | Android Chrome call path works with secure context, mic prompt, AudioContext unlock, and audio playback. | VERIFIED | `OMEN-PC-LIVE-EVIDENCE.md` records `Android Chrome product-owner acceptance: approved` with secure context, mic grant, AudioContext/audio playback, two user turns, two AI audio responses, mute/unmute, end call, and thread scrollback. |
| 3 | Mute stops server-side audio consumption. | VERIFIED | `OMEN-PC-LIVE-EVIDENCE.md` records `/mute`, `type=muted`, and `dropped_audio_frames` equaling all sampled frames while `state=muted`. |
| 4 | End Call returns to thread composer with call-summary rows visible. | VERIFIED | Local Playwright final sweep passed `call-summary.spec.ts`; live OMEN `live-call.spec.ts` verified thread rows after return; Android product-owner approval confirmed scrollback rows. |
| 5 | Five-minute desktop speaker stability has no catastrophic loopback or browser exceptions. | VERIFIED | `OMEN-PC-LIVE-EVIDENCE.md` records the OMEN-local 5-minute stability line: `duration_ms=300000 before_user=2 before_ai=2 after_user=13 after_ai=12`, no browser guard failures, and no catastrophic loopback observed. |

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-40 | SATISFIED | Start Call entry points covered by `call-start.spec.ts` and final sweep. |
| REQ-47 | SATISFIED | Mute/unmute covered by local specs and server-side mute frame-drop evidence. |
| REQ-48 | SATISFIED | Mic permission and retry behavior covered by local specs; Android approval confirms physical mic grant. |
| REQ-49 | SATISFIED at MVP fidelity | Visualizer state specs passed in `PLAYWRIGHT-EVIDENCE.md`; roadmap reserves full visual polish for Phase 4. |
| REQ-50 | SATISFIED | Durable `call_start`, `user_speech`, `ai_speech`, and `call_end` rows covered by server tests, local Playwright, live OMEN, and Android approval. |
| REQ-63 | SATISFIED | Prompt builder tests and final server sweep passed `test_prompt_builder.py`. |
| REQ-A0 | SATISFIED | Mobile Chromium local evidence and physical Android approval are recorded. |
| REQ-A1 | SATISFIED | Live OMEN LAN/GPU acceptance passed and evidence records deployed SHA, health, mute, and stability. |

## Automated Checks

| Check | Result | Status |
|-------|--------|--------|
| AI backend call/WebRTC tests | `66 passed, 3 warnings` | PASS |
| Web UI server call/prompt tests | `40 passed` | PASS |
| Desktop Chromium call-start/call-summary specs | `16 passed` | PASS |
| Isolated patched call-summary spec | `1 passed (1.2m)` | PASS |
| Schema drift | `drift_detected=false`, `blocking=false` | PASS |

## Live And Human Evidence

- Local Phase 3 automated evidence: `PLAYWRIGHT-EVIDENCE.md`.
- Live OMEN-PC desktop evidence: `OMEN-PC-LIVE-EVIDENCE.md`, deployed SHA
  `e48e2ce57cc31a30e7df97c1f0ea9215c136dc45`, live spec `1 passed (6.1m)`.
- Android product-owner acceptance: approved on 2026-05-12.
- Runtime TTS setting during Phase 3 Android approval: F5-TTS
  (`tts_default_engine=f5`, `resident_tts_engine=f5`); VoxCPM2 was available
  but idle.

## Gaps Summary

No blocking gaps found.

Residual scope note: Phase 3 intentionally proves MVP transport and call-loop
functionality. Full call-feel polish, streaming TTFA targets, and advanced
barge-in semantics remain Phase 4+ concerns.

---
_Verified: 2026-05-12T01:09:05Z_
_Verifier: Codex (inline, no delegated verifier)_
