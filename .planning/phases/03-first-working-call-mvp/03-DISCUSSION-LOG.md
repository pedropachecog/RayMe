# Phase 3: First Working Call (MVP) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 03-first-working-call-mvp
**Areas discussed:** Call entry and screen shape, service boundary, MVP turn semantics, browser and mobile audio, verification and evidence
**Mode:** Non-interactive fallback from `$gsd-next`; structured prompts unavailable, so recommended defaults were selected from prior project context and existing code.

---

## Call Entry And Screen Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Contextual call route | Start from chat thread/character and return to the same thread after hangup. | yes |
| Top-level Call nav | Add Call as a global navigation item independent of thread context. | |
| Agent discretion | Let planning pick later. | |

**User's choice:** Recommended default selected.
**Notes:** Prior requirements say calls inherit thread history and write back to the same unified thread. Existing `AppShell` has no Call nav, and Phase 2 explicitly kept Call navigation out of scope.

---

## Service Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Split ownership | Web UI server owns durable state/settings/LLM prompt context; AI backend owns WebRTC/media/STT/TTS runtime. | yes |
| AI backend owns entire call | Put durable call state and LLM settings in the AI backend. | |
| Browser orchestrates everything | Let the browser coordinate LLM/STT/TTS/backend directly. | |

**User's choice:** Recommended default selected.
**Notes:** Prior Phase 1 and Phase 2 context locked durable state to the Web UI server and transient processing/model residency to the AI backend. Browser exposure of provider credentials remains disallowed.

---

## MVP Turn Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| One finalized exchange | One final user utterance, one short non-streaming AI reply, persisted call rows. | yes |
| Continuous multi-turn call feel | Full duplex loop with barge-in, streaming captions, and cancellation. | |
| UI-only simulator | Fake a call screen without real WebRTC media. | |

**User's choice:** Recommended default selected.
**Notes:** The roadmap defines Phase 3 as media plumbing proof and leaves call feel to Phase 4. Acceptance still requires real audio, real transcript rows, and real playback.

---

## Browser And Mobile Audio

| Option | Description | Selected |
|--------|-------------|----------|
| Gesture-owned unlock | Start Call tap performs AudioContext resume, silent buffer, mic permission, and peer connection setup. | yes |
| Lazy unlock later | Start UI first and unlock/play audio later when needed. | |
| Desktop-first only | Delay Android-specific unlock behavior. | |

**User's choice:** Recommended default selected.
**Notes:** AudioContext gesture unlock is a named Phase 3 pitfall, and Android Chrome is in every call acceptance check from this phase onward.

---

## Verification And Evidence

| Option | Description | Selected |
|--------|-------------|----------|
| Full evidence gate | Unit/API contracts, browser Playwright checks, live OMEN-PC verification, saved artifacts, then Android product-owner acceptance. | yes |
| Local-only verification | Rely on local tests before user device testing. | |
| Manual-first verification | Ask the user to test early and fill gaps afterward. | |

**User's choice:** Recommended default selected.
**Notes:** Phase 01.1 and operating notes make this non-negotiable: manual testing is product-owner acceptance, not first-line QA.

---

## the agent's Discretion

- Exact call route and API names.
- Exact internal Web UI server to AI backend control protocol.
- Exact data-channel event names.
- Exact minimal schema additions for call metadata/audio references.
- Exact visualizer shell details before Phase 4 polish.

## Deferred Ideas

- Phase 4: barge-in, cancellation, live partial captions, sentence/chunk streaming, full Voice Visualizer polish.
- Phase 5: per-chat voice override UX and saved-audio replay.
- Phase 6: Bluetooth routing, Wake Lock, PWA/mobile hardening, and soak testing.
