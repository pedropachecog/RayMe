# Phase 3: First Working Call (MVP) - Draft Context, Not User Discussed

**Gathered:** 2026-04-25
**Status:** Invalid for planning - discussion must be rerun with real user answers

> This file was produced by an incorrect non-interactive fallback that selected
> defaults without user discussion. It is retained only as a diagnostic draft.
> Downstream agents must not treat it as Phase 3 context. Rerun
> `$gsd-discuss-phase 3 --text` and write a canonical `03-CONTEXT.md` from
> actual user answers before planning.

<domain>
## Phase Boundary

Phase 3 establishes the first end-to-end call loop: a user starts a call from an existing chat or character, the browser creates a real `RTCPeerConnection` to the AI backend, Android-safe audio unlock and mic permission happen from the Start Call gesture, the AI backend receives mic media through aiortc, a single finalized user utterance is transcribed, one short non-streaming LLM reply is synthesized with the assigned voice, audio plays back in the browser, and the unified thread records `call_start`, `user_speech`, `ai_speech`, and `call_end`.

This phase is intentionally an MVP transport/proof phase. It does not implement Phase 4 call-feel semantics: VAD barge-in during AI speech, mid-stream LLM abort, sentence-streamed/chunked TTS playback, live partial captions, full three-state Voice Visualizer polish, echo-loop mitigation, or per-chat voice override UX. It may create stable interfaces and event names for those later behaviors, but Phase 3 acceptance is one finalized exchange that proves the media path works on desktop Chrome and Android Chrome.

</domain>

<decisions>
## Implementation Decisions

### Workflow Note
- **D-01:** This context was generated from `$gsd-next` -> `$gsd-discuss-phase 3` using an invalid non-interactive fallback because structured user prompts were unavailable. The choices below are diagnostic defaults only, not user decisions.

### Call Entry And Screen Shape
- **D-02:** Calls are contextual, not a top-level global destination. Add a Call affordance to the chat thread header; character-card entry should create or choose the appropriate thread, then enter the same call route.
- **D-03:** Use the canonical Stitch Voice Call screen as the visual reference, but scope it to real Phase 3 controls only: connection/call state, final transcript exchange, visualizer shell, mute, device selectors where browser support allows, and end call. Do not add share/account/billing/mock controls from the Stitch export.
- **D-04:** The call route should return to the originating thread composer after end-call, with the call-summary row visible in scrollback.

### Service Boundary
- **D-05:** The browser must talk to RayMe-owned app routes for durable call setup and thread state. It must not receive LLM API keys or provider details.
- **D-06:** The Web UI server remains the durable owner for threads, messages, settings, call-session metadata, prompt construction, and any saved audio/blob records.
- **D-07:** The AI backend owns live media transport, aiortc peer lifecycle, STT/VAD/TTS processing, and transient per-call runtime state. It must not become the source of truth for durable thread or voice records.
- **D-08:** Planning should design a minimal internal control contract between Web UI server and AI backend so the AI backend can run the media path while the Web UI server supplies thread context, selected voice/sample metadata, settings, and durable writeback. The exact protocol is the agent's discretion, but it must preserve the ownership boundary above.

### MVP Turn Semantics
- **D-09:** Phase 3 captures one finalized user utterance and one short non-streaming AI reply per MVP call acceptance run. This is enough to prove the path without prematurely implementing Phase 4 streaming/cancel semantics.
- **D-10:** The AI reply should be constrained to a short, natural single sentence for MVP acceptance. Long-form chunk planning and continuous multi-turn call feel remain Phase 4.
- **D-11:** Final user and AI transcript text should render in the call screen and persist as `user_speech` and `ai_speech` messages. Live partial captions are out of scope for this phase, but event names may reserve room for them.
- **D-12:** Persist `call_start` and `call_end` event messages in chronological order with enough structured metadata to render duration, character, voice used, start/end timestamps, and terminal state. Prefer a small schema/metadata extension over stuffing opaque JSON into `content_text`.

### Voice, Audio, And Storage
- **D-13:** Use the character default voice for Phase 3 calls. If no usable voice is assigned, the call UI should block start with a clear path to Voice Lab or character voice assignment instead of silently falling back to an arbitrary voice.
- **D-14:** If a referenced voice was force-deleted, surface the existing `Voice unavailable` state and block call start until the user chooses an available voice. Do not hide the broken reference.
- **D-15:** AI-generated speech may be persisted when `save_ai_audio` is enabled, but replay UI remains out of scope. Mic audio remains off by default; Phase 3 should persist the final user transcript, not raw mic audio, unless the existing setting explicitly enables storage and planning includes the storage path.
- **D-16:** Muting must stop server-side audio consumption, not only local playback. The acceptance path needs observable server-side evidence that incoming audio frames drop or are ignored while muted.

### Browser And Mobile Audio
- **D-17:** The Start Call tap owns the Android-safe unlock sequence: create/resume `AudioContext`, play a one-sample silent buffer, request mic permission, and create/connect the peer connection inside the same user-gesture flow as much as browser APIs allow.
- **D-18:** Mic permission denial must show a clear retry path. Do not enter a half-connected call state after denial.
- **D-19:** Device selectors should use browser-supported `enumerateDevices`/`setSinkId` behavior when available and degrade clearly when output-device selection is unsupported on Android Chrome.
- **D-20:** The call implementation must keep HTTPS and secure-context checks visible because Android mic capture is non-negotiably tied to the existing mkcert LAN path.

### Error And State Handling
- **D-21:** Model/backend readiness failures should block call start or move the call into a clear failed state with public-safe errors. Do not expose local paths, tracebacks, model exception text, or provider secrets.
- **D-22:** End call must be idempotent. A user-initiated hangup, backend failure, or navigation away should close peer resources and write a coherent `call_end` row once.
- **D-23:** A failed MVP turn should still clean up media resources and preserve any durable records that truthfully describe what happened, rather than pretending the call completed.

### Verification And Evidence
- **D-24:** Phase 3 planning must include contract tests for signaling readiness, WebRTC offer handling, call session lifecycle, message persistence order, mute server-side consumption, and public-safe error shapes.
- **D-25:** Browser tests must cover rendered Call UI, Start Call gesture flow, mic-denied state, end-call return to thread, and persisted call rows. Console/page errors are acceptance failures.
- **D-26:** Live OMEN-PC verification is required before asking for Android product-owner acceptance. The handoff must state unit/API tests, browser checks, live LAN target, evidence artifact path, deployed commit, and exactly what remains for the user to verify on Android Chrome.

### the agent's Discretion
- Exact route names for call setup and the client call screen.
- Exact internal Web UI server <-> AI backend call-control protocol.
- Exact data-channel event names, as long as final transcript/audio/end events are explicit and Phase 4 can extend them.
- Exact minimal schema for call-session/audio metadata, as long as unified chronological messages remain the user-visible thread record.
- Exact visualizer shell animation in Phase 3, provided it does not claim full listening/thinking/speaking polish before Phase 4.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope And Requirements
- `.planning/ROADMAP.md` - Phase 3 goal, requirements delivered, pitfalls owned, and success criteria.
- `.planning/REQUIREMENTS.md` - Call requirements, especially REQ-40, REQ-47, REQ-48, REQ-49, REQ-50, REQ-60, REQ-63, REQ-A0, and REQ-A1; Phase 4-owned requirements REQ-41 through REQ-45 must be treated as future scope unless needed for interfaces.
- `.planning/PROJECT.md` - Core value, three-service topology, LAN/no-auth boundary, sliding-window call memory, and hardware/browser constraints.
- `.planning/STATE.md` - Current frozen decisions from Phases 0-2, including GPU runtime policy, Voice Lab, model residency, and Phase 3 readiness.
- `.planning/OPERATING-NOTES.md` - OMEN-PC, Android HTTPS, deployment, verification, and product-owner handoff rules.

### Prior Phase Context
- `.planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md` - Web UI server ownership, unified message schema, HTTPS, Settings, and text-chat decisions.
- `.planning/phases/01.1-ui-acceptance-and-regression-test-hardening/01.1-CONTEXT.md` - Agent-first browser/live verification rule and Android handoff discipline.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md` - AI backend processing boundary, full TTS roster, voice identity/delete semantics, and Settings/audio defaults.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/02-UI-SPEC.md` - Approved Voice Lab/Settings design contract and Phase 2 UI constraints that Phase 3 must not regress.

### Design
- `docs/stitch/DESIGN.md` - Ethereal Core / True Dark design system.
- `docs/stitch/manifest.md` - Canonical Stitch screen inventory.
- `docs/stitch/screens/voice-call-true-dark.md` - Voice Call screen notes.
- `docs/stitch/html/voice-call-true-dark.html` - Voice Call HTML reference.
- `docs/stitch/screenshots/voice-call-true-dark.png` - Voice Call visual reference.

### Runtime And Existing Evidence
- `ai-backend/docs/RUNTIME-EVIDENCE.md` - Runtime evidence expectations and VRAM/headroom guardrails.
- `ai-backend/docs/STT-GPU-RUNTIME.md` - CUDA STT/TTS runtime rules.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md` - Latest live GPU/Voice Lab evidence from Phase 2.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/PLAYWRIGHT-EVIDENCE.md` - Latest browser evidence style from Phase 2.

### Existing Code Entry Points
- `ai-backend/app/api/webrtc.py` - Current Phase 2 signaling skeleton to replace/extend.
- `ai-backend/tests/test_webrtc_signaling.py` - Current non-call skeleton contract tests.
- `ai-backend/app/main.py` - AI backend router/lifespan/model-manager integration.
- `ai-backend/app/api/stt.py` - Existing transient STT/VAD endpoint behavior.
- `ai-backend/app/api/tts.py` - Existing transient TTS synthesis endpoint behavior.
- `ai-backend/app/models/model_manager.py` - TTS residency, switching, and health model.
- `web-ui/server/app/storage/models.py` - Unified message kinds and current schema patterns.
- `web-ui/server/app/domain/thread_service.py` - Thread hydration/listing and message chronology.
- `web-ui/server/app/api/chat.py` - Current text message append and LLM streaming route.
- `web-ui/server/app/domain/prompt_builder.py` - Selected-branch, stale-message, and persona prompt context behavior to reuse for call memory.
- `web-ui/server/app/domain/voice_service.py` - Durable voice/sample ownership and soft-delete behavior.
- `web-ui/server/app/domain/ai_backend_client.py` - Public-safe AI backend client/error pattern.
- `web-ui/client/src/routes/chat/[threadId]/+page.svelte` - Existing thread UI, virtualization, composer, and message actions.
- `web-ui/client/src/lib/components/ChatMessageBubble.svelte` - Message rendering and `data-message-kind` hooks.
- `web-ui/client/src/lib/components/AppShell.svelte` - Top-level navigation and secure/media readiness chips.
- `web-ui/client/src/lib/api/types.ts` - Existing client types for message kinds, settings, voices, and engines.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The AI backend already depends on `aiortc==1.14.0` and exposes `/webrtc/status` plus `/webrtc/offer` as a Phase 2 skeleton.
- The Web UI server already has `message_kind` values for `user_speech`, `ai_speech`, `call_start`, and `call_end`.
- `ThreadService.get_thread_detail` hydrates chronological messages for the chat screen; this is the right read path for showing call rows after hangup.
- `ChatRepository` and `prompt_builder` already know how to append text turns and build selected-branch prompt context while excluding stale rows.
- `VoiceService` owns saved voices, sample blobs, soft-delete tombstones, test-play synthesis, and `Voice unavailable` behavior.
- `AiBackendClient` already maps backend status/STT/TTS failures to public-safe errors.
- `AppShell` already checks `window.isSecureContext` and `navigator.mediaDevices`.
- `ChatMessageBubble` already emits `data-message-kind`, which can support call-row styling without rewriting the whole thread renderer.

### Established Patterns
- Durable state belongs in the Web UI server with SQLite plus filesystem blobs.
- The AI backend is a transient processing/runtime service with sanitized public errors.
- The browser should use RayMe-owned routes rather than provider/backend-specific implementation details.
- UI is Svelte 5 with local components, `lucide-svelte` icons, and True Dark CSS tokens.
- Product-owner Android testing happens only after agent-run API tests, browser tests, live OMEN-PC deployment, saved evidence, and deployed commit reporting.

### Integration Points
- Replace the Phase 2 `/webrtc/offer` rejection with real offer handling and update its tests from "not ready" to "MVP media ready".
- Add Web UI server call setup/writeback APIs near existing thread/chat/message routes.
- Add a contextual call route and Call affordances from `web-ui/client/src/routes/chat/[threadId]/+page.svelte` and character-card flows.
- Extend message/thread storage minimally for call metadata and optional audio references while preserving the unified chronological message table as the primary user-visible record.
- Use existing Settings values for AI backend URL, LLM endpoint/model/key, VAD settings, save-audio toggles, STT model, and TTS default/voice engine metadata.

</code_context>

<specifics>
## Specific Ideas

- The first successful call should feel like "the line opens, I say one thing, the character answers out loud, and the thread shows what happened."
- The call MVP should be honest about state: connecting, listening for the first utterance, thinking, speaking, ended, failed.
- Avoid implementing fake call UI that only simulates audio. The acceptance target is real `RTCPeerConnection` media on desktop and Android Chrome.
- Keep the UI calm and operational. This is a tool screen, not a landing page.
- The MVP should create Phase 4-ready interfaces without pulling Phase 4 behavior into Phase 3.

</specifics>

<deferred>
## Deferred Ideas

- VAD barge-in during AI playback, LLM cancellation, and TTS cancellation belong to Phase 4.
- Sentence-streamed/chunked TTS playback and live AI captions belong to Phase 4.
- Live partial user captions belong to Phase 4, though Phase 3 may reserve event names.
- Full Voice Visualizer listening/thinking/speaking polish belongs to Phase 4.
- Per-chat voice override UX and inline saved-audio replay belong to Phase 5.
- Bluetooth routing, Wake Lock, PWA hardening, and mobile edge-case soak testing belong to Phase 6.

</deferred>

---

*Phase: 03-first-working-call-mvp*
*Context gathered: 2026-04-25*
