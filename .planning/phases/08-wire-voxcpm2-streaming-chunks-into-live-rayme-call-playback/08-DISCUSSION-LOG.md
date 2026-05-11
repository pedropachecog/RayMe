# Phase 08: Wire VoxCPM2 Streaming Chunks Into Live RayMe Call Playback - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-11
**Phase:** 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
**Areas discussed:** Streaming Boundary, Playback Timing, Call Completion Contract, Failure And Fallback Policy, Evidence Strictness

---

## User Direction

The user chose not to discuss individual gray areas and accepted the recommended defaults for all implementation areas.

---

## Streaming Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Reusable internal contract | Add an internal AI backend streaming TTS contract, with VoxCPM2 as the first real implementation. | yes |
| VoxCPM2-only path | Build only the minimum VoxCPM2-specific streaming path. | |
| Browser/API route change | Add a VoxCPM2-specific public route or browser-facing behavior. | |

**User's choice:** Accept recommended default.
**Notes:** Keep one public RayMe call API; make streaming reusable internally.

---

## Playback Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Latency-first first chunk | Enqueue the first viable chunk as soon as it can play, with minimal validity checks. | yes |
| Buffer for smoothness | Hold a small buffer before playback to reduce gap risk. | |
| Wait for full response | Preserve whole-WAV behavior. | |

**User's choice:** Accept recommended default.
**Notes:** Phase 8 exists to convert benchmark streaming TTFA into live call TTFA, so avoid artificial waits.

---

## Call Completion Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Keep speak request open | Existing Web UI SSE wait/keepalive behavior remains; `ai_audio_started` fires on first chunk and one final completion fires at the end. | yes |
| Return after first audio | Let playback continue in the background after the first chunk. | |
| Split completion per chunk | Treat chunks as separate completion units. | |

**User's choice:** Accept recommended default.
**Notes:** Preserve Android Chrome connection behavior and current single-turn semantics.

---

## Failure And Fallback Policy

| Option | Description | Selected |
|--------|-------------|----------|
| No silent evidence fallback | Evidence runs cannot pass if the path falls back to whole-WAV synthesis; production fallback is explicit and pre-first-audio only. | yes |
| Always fallback to whole WAV | Preserve speech if streaming fails by silently using current synthesis. | |
| Always fail hard | Any streaming problem fails the turn immediately. | |

**User's choice:** Accept recommended default.
**Notes:** Fallback after first audio would confuse turn completion and evidence. Sanitized failures and no duplicate final events remain mandatory.

---

## Evidence Strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Repeated median same-run comparison | Compare repeated warm VoxCPM2 and F5 samples in one evidence command and promote only if median VoxCPM2 TTFA beats median F5 TTFA. | yes |
| Single same-run comparison | One warm VoxCPM2 run and one warm F5 run are enough. | |
| Manual-only confidence | Use benchmark confidence plus a smoke call rather than repeated live evidence. | |

**User's choice:** Accept recommended default.
**Notes:** Evidence must include streaming proof fields: first chunk, first enqueue, `ai_audio_started`, chunk count, total timing, gaps, and fallback status.

---

## the agent's Discretion

- Exact internal streaming adapter names.
- Exact chunk viability thresholds, as long as they stay minimal and latency-first.
- Exact evidence filenames/schema, as long as verifier-enforced metrics cover the Phase 8 SPEC.
- Exact test fixture design.

## Deferred Ideas

None.
