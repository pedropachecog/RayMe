# Phase 8: Wire VoxCPM2 Streaming Chunks Into Live RayMe Call Playback - Specification

**Created:** 2026-05-11
**Ambiguity score:** 0.15 (gate: <= 0.20)
**Requirements:** 5 locked

## Goal

Live RayMe calls using VoxCPM2 start audible playback from VoxCPM2 streaming audio chunks and beat F5 warm first-audio time in the same live evidence run; if that passes, RayMe updates its durable call-engine decision toward VoxCPM2.

## Background

Phase 7 made VoxCPM2 selectable with caveats. Manual listening judged VoxCPM2 far better than F5, runtime smoke and VRAM evidence passed on the RTX 3060, and saved VoxCPM2 metadata already reaches real call playback. The remaining blocker is live call latency: `results/voxcpm2-call-flow.json` recorded VoxCPM2 warm call TTFA at `14425.6 ms` while F5 was `1117.1 ms`, because the current call path waits for whole-response VoxCPM2 synthesis before enqueuing audio.

The current AI backend implementation reflects that limitation: `ai-backend/app/models/tts_voxcpm2.py` calls `runtime.generate(...)` and returns one complete WAV, while `ai-backend/app/call/session.py` queues outbound audio only after `_synthesize_speech(...)` returns. Phase 7 scenario evidence shows the native VoxCPM2 streaming path can produce first audio around `381-399 ms` in benchmark collection, but RayMe calls do not yet consume those chunks live.

## Requirements

1. **VoxCPM2 live chunk playback**: In live calls, VoxCPM2 playback must enqueue the first viable streaming audio chunk before full VoxCPM2 generation finishes.
   - Current: VoxCPM2 call playback waits for one completed WAV from the generic synthesis path before audio is enqueued.
   - Target: VoxCPM2 call playback consumes streaming audio chunks and starts outbound WebRTC playback from the first viable chunk while later chunks continue to generate.
   - Acceptance: An automated call-session or WebRTC speak contract proves first-chunk enqueue and `ai_audio_started` occur before a scripted streaming adapter completes its final chunk.

2. **Faster than F5 in live evidence**: VoxCPM2 warm live call first-audio time must be lower than F5 warm live call first-audio time in the same evidence run.
   - Current: Phase 7 live evidence reports VoxCPM2 `14425.6 ms` and F5 `1117.1 ms`.
   - Target: Phase 8 evidence reports `voxcpm2_warm_call_ttfa_ms < f5_warm_call_ttfa_ms`, with no artificial wait after the first playable VoxCPM2 chunk.
   - Acceptance: A machine-readable Phase 8 evidence artifact records both warm TTFA values, the comparison result, and enough timing fields to show VoxCPM2 first audio came from streaming playback rather than whole-WAV completion.

3. **Interrupt and barge-in preservation**: Existing interrupt and VAD barge-in semantics must still cancel in-flight VoxCPM2 speech.
   - Current: The whole-WAV call path cancels the active AI turn task, stops the outbound track, drains buffered audio, and returns the call to listening.
   - Target: The streamed VoxCPM2 path cancels pending generation, stops future chunk enqueue, drains already queued speech as the existing interrupt path requires, and returns to listening without duplicate completion events.
   - Acceptance: Automated tests prove interrupt after the first streamed chunk prevents later chunks from playing, emits the existing interrupt/cancel behavior, and does not emit duplicate `ai_done` or raw backend errors.

4. **Single call turn semantics**: Streaming audio chunks must not fragment the visible or durable AI call turn.
   - Current: The Web UI records one final `ai_speech` row for the visible LLM response and then asks the AI backend to speak that text.
   - Target: VoxCPM2 streaming affects playback timing only; captions, final transcript persistence, and any existing AI-audio artifact semantics remain one AI turn per LLM response.
   - Acceptance: Server tests or call-flow evidence show one durable `ai_speech` row for a streamed VoxCPM2 reply, with the exact visible text, and no per-audio-chunk transcript rows.

5. **Decision writeback on pass**: If Phase 8 proves VoxCPM2 live first-audio time beats F5, RayMe must update its durable project decision so the speed caveat no longer blocks VoxCPM2 as the preferred/default call TTS choice.
   - Current: `PROJECT.md`, `STATE.md`, `ROADMAP.md`, and Phase 7 decision artifacts keep F5 as default because live VoxCPM2 calls do not consume streaming chunks.
   - Target: Passing Phase 8 evidence updates the project decision/default wording to prefer VoxCPM2 for live calls; F5 remains available but no longer wins by default on call-feel speed.
   - Acceptance: `PROJECT.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, and a Phase 8 decision/evidence artifact agree on the outcome and cite the live F5 comparison.

## Boundaries

**In scope:**
- VoxCPM2 live call playback changes needed to consume streaming audio chunks.
- AI backend adapter/session/track contracts needed for first-chunk enqueue and later chunk stitching/playout.
- Web UI call facade changes only if required to preserve SSE keepalive, captions, interrupt, or call-state behavior while VoxCPM2 streams.
- Same-run live evidence comparing warm VoxCPM2 first-audio time against warm F5 first-audio time.
- Phase 8 evidence artifacts and durable decision writeback if VoxCPM2 beats F5.

**Out of scope:**
- Redesigning the Voice Call UI - Phase 8 is about call playback behavior, not visual layout.
- Reworking Voice Lab controls or character editing - VoxCPM2 metadata already exists from Phase 7.
- Replacing every engine's TTS implementation - shared abstractions are allowed only when required to make VoxCPM2 streaming playback work safely.
- Adding managed/cloud TTS providers - project scope remains self-hosted engines.
- Treating benchmark-only streaming evidence as sufficient - Phase 8 requires live RayMe call playback evidence.
- Implementing unrelated mobile, PWA, auth, or thread-management features - they do not decide whether VoxCPM2 calls are usable.

## Constraints

- OMEN deployment or runtime evidence must use `scripts/deploy-omen.sh`; no ad-hoc OMEN deployment scripts, launcher files, or manual scheduled-task edits.
- The runtime must remain CUDA-only for production AI model paths; CPU fallback for VoxCPM2, STT, or VAD is a regression.
- Evidence must run on the target RTX 3060 class environment and record VRAM/runtime context sufficiently to detect regressions.
- Public errors must stay sanitized: no tracebacks, local paths, model-cache paths, or raw model identifiers in browser-visible failure payloads.
- Existing reference-audio size limits and VoxCPM2 bounded option validation must remain enforced.
- The call should keep existing full-duplex, interrupt, data-channel, SSE, and durable-message contracts unless a change is explicitly required for VoxCPM2 streaming playback.
- First-audio timing is the hard optimization target: the phase should minimize it, with the pass/fail floor being faster than F5 in the same evidence run.

## Acceptance Criteria

- [ ] VoxCPM2 WebRTC speak/call-session tests prove first streamed chunk enqueue happens before full generation completion.
- [ ] Warm live evidence records `voxcpm2_warm_call_ttfa_ms < f5_warm_call_ttfa_ms`.
- [ ] Evidence records first-chunk TTFA, total generation/playback timing, chunk count, enqueue timing, and whether any whole-WAV fallback occurred.
- [ ] Interrupt or VAD barge-in during streamed VoxCPM2 playback cancels pending chunks and returns the call to listening without duplicate final events.
- [ ] Streaming VoxCPM2 playback produces one visible/durable AI speech turn per LLM reply, not one message per audio chunk.
- [ ] VoxCPM2 public failure paths remain sanitized and reference-audio / option bounds remain enforced.
- [ ] OMEN live evidence, if deployment is needed, is produced through `scripts/deploy-omen.sh`.
- [ ] If VoxCPM2 beats F5, project decision/default wording is updated in `PROJECT.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, and the Phase 8 evidence/decision artifact.

## Ambiguity Report

| Dimension          | Score | Min   | Status | Notes |
|--------------------|-------|-------|--------|-------|
| Goal Clarity       | 0.92  | 0.75  | PASS   | Goal is VoxCPM2 usable live calls by streaming first audio and beating F5. |
| Boundary Clarity   | 0.78  | 0.70  | PASS   | Scope may touch required call/TTS plumbing, but excludes unrelated redesign. |
| Constraint Clarity | 0.82  | 0.65  | PASS   | Faster-than-F5 live evidence, OMEN deploy rules, CUDA-only runtime, and sanitized errors are locked. |
| Acceptance Criteria| 0.84  | 0.70  | PASS   | Pass/fail checks are evidence-backed and comparative. |
| **Ambiguity**      | 0.15  | <=0.20| PASS   | Ready for discuss-phase. |

Status: PASS = met minimum; WARN = below minimum, planner treats as assumption.

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|-------|-------------|------------------|-----------------|
| 1 | Researcher | What should be user-visible after Phase 8? | Make VoxCPM2 usable in live calls by playing streaming chunks instead of waiting for whole synthesis; quality is the reason because F5 sounds bad. |
| 1 | Researcher / Simplifier | How fast is good enough? | Make first audio as short as possible; hard pass/fail is VoxCPM2 beating F5 in the same live evidence run. |
| 1 | Boundary Keeper | Can scope include adjacent plumbing? | Yes, include whatever call/TTS plumbing is required for VoxCPM2 calls to be good and usable, but avoid unrelated redesign. |
| 1 | Seed Closer | If VoxCPM2 beats F5, should durable decisions/defaults update? | Yes. Update project decision/default wording so VoxCPM2 becomes preferred/default for live calls when evidence passes. |

---

*Phase: 08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback*
*Spec created: 2026-05-11*
*Next step: $gsd-discuss-phase 8 - implementation decisions (how to build what is specified above)*
