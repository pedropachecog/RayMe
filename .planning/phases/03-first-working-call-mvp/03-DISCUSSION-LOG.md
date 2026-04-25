# Phase 03: First Working Call (MVP) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `03-CONTEXT.md` - this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 03-first-working-call-mvp
**Mode:** Plain-text sequential discussion, one question at a time with recommendations shown before each answer.
**Areas discussed:** Call entry, call screen shape, streaming multi-turn behavior, interruption behavior, toolbar/device handling, failure handling, thread writeback, visualizer states, verification.

---

## Decisions Captured

| Question | Selected |
|---|---|
| Call entry path | Thread + character entry |
| Call screen shape | Minimal operational call screen |
| Base turn model | Custom: streaming multi-turn call |
| Toolbar/device handling | Full toolbar with clear degradation |
| Failure/recovery behavior | Strict blocking before start, clean truthful teardown |
| Verification bar | Full gate: tests + browser + live OMEN + saved evidence + Android acceptance |
| AI start timing | Hybrid: wait for finalized user turn, then stream AI reply |
| Interrupt button behavior | Cancel both playback and generation |
| Post-interrupt state | Return immediately to listening |
| Call exit behavior | Always return to originating thread |
| Character-card call without existing thread | Create thread immediately |
| Unsupported device pickers | Show disabled with explanation |
| Missing/unavailable voice | Block start with recovery path |
| Mic denial | Explain and retry before entering call |
| Backend/model not ready | Block start with clear readiness error |
| Thread writeback | `call_start`, speech turns, `call_end` |
| In-call transcript visibility | Show live transcript during call |
| AI transcript rendering | Stream AI text live; user text appears on finalized turn |
| Mute behavior | Stop server-side audio consumption |
| End Call during AI speech | Stop playback/work immediately and tear down cleanly |
| Voice visualizer | Three MVP states now: listening, thinking, speaking |
| Mid-call connection drop | End cleanly with truthful records |
| Interrupt before first audio playback | Cancel AI turn anyway and return to listening |
| Voice source for character-card calls | Character's assigned default voice |
| Typed text during active call | Out of scope; voice-only while call is active |
| AI streaming text stability | Forward-stable chunks only; no rewrites |

## Notes

- The user explicitly rejected carrying forward any inferred or draft Phase 3 decisions.
- The user required the discussion format itself to be durable: one question at a time, recommendation shown first, no skip/update/view detours during a fresh discussion.
- The resulting Phase 3 call model is intentionally stronger than the earlier roadmap shorthand: multi-turn and AI-streaming are now in scope for this phase, while voice-detected interruption remains deferred.

## Deferred Ideas

- Voice-detected interruption / VAD barge-in - Phase 4
- Full call-feel polish - Phase 4
- In-call typed messaging - future phase
- Automatic reconnect within the same call session - future phase

