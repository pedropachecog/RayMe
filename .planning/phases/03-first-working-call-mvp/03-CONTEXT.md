# Phase 03: First Working Call (MVP) - Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 establishes the first real voice call flow on top of the existing RayMe thread model: browser `RTCPeerConnection` to the AI backend, Android-safe audio unlock, live call UI, real mic capture, real AI speech playback, unified thread writeback, and desktop plus Android Chrome verification.

This discussion intentionally changes the earlier "one-sentence non-streaming reply" MVP framing. Phase 3 now includes a streaming multi-turn call loop, but it still stops short of Phase 4 call-feel work: no voice-detected interruption/barge-in, no automatic user-speech interruption of AI playback, and no full visual polish beyond MVP fidelity.

</domain>

<decisions>
## Implementation Decisions

### Call Entry And Thread Ownership
- **D-01:** Calls can start from both the chat thread header and directly from a character card.
- **D-02:** If a call starts from a character card and no thread exists yet, create the thread immediately before entering the call.
- **D-03:** End Call always returns to the originating thread with the call rows visible in scrollback, regardless of whether the call began from a thread or a character card.

### Call Screen Shape
- **D-04:** Phase 3 uses a minimal operational call screen rather than a polished final-product call surface.
- **D-05:** The call screen should show connection/call state, the MVP voice visualizer states, live call transcript, mute, end call, and device pickers where browser support exists.

### Turn Model And Streaming Behavior
- **D-06:** Phase 3 is a multi-turn call, not a one-shot exchange.
- **D-07:** User turns still have a clean end-of-turn boundary before the AI takes over. Phase 3 does not start AI speech while the user is still talking.
- **D-08:** After the user turn finalizes, the AI reply streams once generation starts rather than waiting for the full reply to complete.
- **D-09:** The call transcript should show user turns once finalized, while AI text streams live during generation.
- **D-10:** Streamed AI text should be forward-stable only. Once visible, text should not be rewritten.

### Interruption And Turn Control
- **D-11:** Phase 3 does not include voice-detected interruption or VAD barge-in.
- **D-12:** Phase 3 does include a button-based interrupt control during AI turns.
- **D-13:** Pressing interrupt cancels both playback and the rest of AI generation.
- **D-14:** After interrupt, the call returns immediately to listening.
- **D-15:** Interrupt must behave consistently whether audio has already started or the AI is still generating before first playback; in both cases the AI turn is canceled and the call returns to listening.

### Toolbar And Device Handling
- **D-16:** The Phase 3 toolbar includes mute, end call, audio input picker, and audio output picker.
- **D-17:** Unsupported device pickers remain visible but disabled with a clear explanation, rather than being hidden or left broken.
- **D-18:** Mute must stop server-side user-audio consumption while keeping the call connected.
- **D-19:** End Call is destructive: if the AI is speaking or generating, ending the call stops playback, cancels remaining work, tears down the session, and writes a truthful `call_end`.

### Voice And Start Preconditions
- **D-20:** Calls use the character's assigned default voice.
- **D-21:** If the character has no usable assigned voice, or the assigned voice is unavailable, call start is blocked with a clear recovery path rather than falling back silently.
- **D-22:** If mic permission is denied, stay out of the call, explain the denial clearly, and offer a retry path.
- **D-23:** If the backend or required models are not ready, block call start with a clear readiness error and recovery guidance.

### Failure Handling
- **D-24:** Phase 3 prefers honest blocking and clean teardown over optimistic half-connected states or silent fallbacks.
- **D-25:** If the network or peer connection drops mid-call, end the call cleanly, show a clear failure/end state, and preserve truthful records for what happened before the drop.

### Transcript And Thread Writeback
- **D-26:** Each successful or partial call writes `call_start`, per-turn `user_speech`, per-turn `ai_speech`, and `call_end` rows in chronological order in the unified thread.
- **D-27:** The call screen shows the live call transcript during the call, not only after hangup.
- **D-28:** Phase 3 is voice-only while the call is active. Typed text resumes after hangup.

### Voice Visualizer
- **D-29:** Phase 3 includes the three core Voice Visualizer states now: listening, thinking, and speaking.
- **D-30:** Those visualizer states only need MVP fidelity in Phase 3; full polish remains Phase 4 work.

### Verification And Acceptance
- **D-31:** Phase 3 uses the full verification gate: relevant automated tests, browser coverage, live `OMEN-PC` verification, saved evidence artifacts, and only then Android product-owner acceptance.

### the agent's Discretion
- Exact route names, endpoint names, and event names, as long as they preserve the thread-owned call model above.
- Exact FSM/state-machine shape for listening, thinking, speaking, interrupted, ended, and failed states.
- Exact transcript layout and visual treatment, as long as the live-streaming and finalized-turn rules above are preserved.
- Exact browser capability messaging for unsupported device pickers.
- Exact storage shape for streamed/final AI transcript chunks and call metadata, as long as the unified chronological message record remains the user-visible source of truth.

</decisions>

<specifics>
## Specific Ideas

- The user wants discussion-driven planning, not inferred defaults. This context is based on explicit one-question-at-a-time answers.
- The desired Phase 3 experience is a real streaming conversational loop, but without voice-detected interruption yet.
- The interrupt button should behave like "stop this AI turn now" and immediately hand the floor back to the user.
- The call screen should stay operational and honest rather than trying to feel fully polished too early.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope And Requirements
- `.planning/ROADMAP.md` - Phase 3 goal, requirements delivered, pitfalls owned, success criteria, and dependency boundaries.
- `.planning/REQUIREMENTS.md` - Phase 3-related requirements, especially `REQ-40`, `REQ-47`, `REQ-48`, `REQ-49`, `REQ-50`, `REQ-60`, `REQ-63`, `REQ-A0`, and `REQ-A1`.
- `.planning/PROJECT.md` - Core product goal, thread ownership, mobile-browser target, and service-topology constraints.
- `.planning/STATE.md` - Current frozen decisions from Phases 0-2, including TTS/STT/runtime policy and Phase 3 readiness context.
- `.planning/OPERATING-NOTES.md` - Verification, Android/LAN HTTPS, OMEN-PC deployment, and discussion/handoff rules.

### Prior Phase Context
- `.planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md` - Unified thread/message model, thread ownership, and text-chat context rules.
- `.planning/phases/01.1-ui-acceptance-and-regression-test-hardening/01.1-CONTEXT.md` - Agent-first verification and Android handoff discipline.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/02-CONTEXT.md` - Voice ownership, missing/unavailable voice semantics, settings defaults, and AI-backend ownership boundaries.

### Design
- `docs/stitch/DESIGN.md` - Ethereal Core / True Dark design system.
- `docs/stitch/manifest.md` - Canonical Stitch screen inventory.
- `docs/stitch/screens/voice-call-true-dark.md` - Voice Call screen reference notes.
- `docs/stitch/html/voice-call-true-dark.html` - Voice Call HTML reference.

### Existing Runtime And Evidence Rules
- `ai-backend/docs/RUNTIME-EVIDENCE.md` - Runtime evidence expectations and guardrails for live AI runtime work.
- `ai-backend/docs/STT-GPU-RUNTIME.md` - CUDA/STT/TTS runtime rules and deployment constraints.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/OMEN-PC-LIVE-EVIDENCE.md` - Latest live OMEN-PC evidence style to match.
- `.planning/phases/02-ai-backend-skeleton-voice-lab/PLAYWRIGHT-EVIDENCE.md` - Saved browser evidence style to match.

### Existing Code Entry Points
- `ai-backend/app/api/webrtc.py` - Current Phase 2 signaling skeleton to extend into real call handling.
- `ai-backend/tests/test_webrtc_signaling.py` - Existing signaling contract tests to evolve.
- `ai-backend/app/api/stt.py` - Existing transient STT behavior to build on for user-turn finalization.
- `ai-backend/app/api/tts.py` - Existing transient synthesis behavior to build on for streamed AI turns.
- `ai-backend/app/models/model_manager.py` - TTS residency and switching behavior.
- `web-ui/server/app/storage/models.py` - Unified message schema including call-related kinds.
- `web-ui/server/app/domain/thread_service.py` - Thread hydration and chronological message reads.
- `web-ui/server/app/domain/prompt_builder.py` - Sliding-window prompt assembly that should feed call context.
- `web-ui/server/app/domain/voice_service.py` - Durable voice ownership and unavailable-voice behavior.
- `web-ui/server/app/domain/ai_backend_client.py` - Public-safe AI backend client and error-mapping patterns.
- `web-ui/client/src/routes/chat/[threadId]/+page.svelte` - Existing thread route and likely call-entry integration point.
- `web-ui/client/src/lib/components/ChatMessageBubble.svelte` - Existing message rendering hooks for call rows.
- `web-ui/client/src/lib/components/AppShell.svelte` - Existing top-level shell and secure-context/media-readiness cues.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The AI backend already exposes `/webrtc/status` and `/webrtc/offer` as a non-call Phase 2 skeleton that Phase 3 can now replace with real call behavior.
- The unified message model already includes `call_start`, `call_end`, `user_speech`, and `ai_speech` kinds, so Phase 3 can extend the existing thread model instead of inventing a separate call history store.
- `VoiceService` already owns durable saved-voice state and `Voice unavailable` semantics, which Phase 3 should reuse for call-start validation.
- `AiBackendClient` already provides a sanitized error boundary between Web UI and AI backend.

### Established Patterns
- Durable state belongs in the Web UI server; transient media/runtime work belongs in the AI backend.
- The browser should talk to RayMe-owned routes rather than directly to provider/runtime details.
- Android and live-OMEN verification are mandatory before product-owner acceptance for browser/media/runtime work.
- UI should preserve the existing True Dark design language and avoid premature over-polish.

### Integration Points
- Add call setup and durable writeback APIs near the existing thread/chat APIs in the Web UI server.
- Extend the Phase 2 WebRTC skeleton in the AI backend into real peer connection, media, and streamed AI-turn handling.
- Add call affordances to thread and character entry surfaces while keeping the thread as the durable owner.
- Extend the thread renderer to display call boundary rows and speech rows chronologically.

</code_context>

<deferred>
## Deferred Ideas

- Voice-detected interruption and VAD barge-in remain Phase 4.
- Full call-feel polish, richer visualizer treatment, and more advanced call-state presentation remain Phase 4.
- In-call typed messaging remains out of scope for Phase 3.
- Automatic reconnect behavior remains out of scope for Phase 3.

</deferred>

---

*Phase: 03-first-working-call-mvp*
*Context gathered: 2026-04-25*
