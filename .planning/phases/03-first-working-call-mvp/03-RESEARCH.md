# Phase 03: First Working Call (MVP) - Research

**Researched:** 2026-04-25
**Domain:** Browser WebRTC audio call plumbing across SvelteKit + FastAPI + aiortc
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

Copied verbatim from `.planning/phases/03-first-working-call-mvp/03-CONTEXT.md`. [VERIFIED: repo file]

### Locked Decisions
- **D-01:** Calls can start from both the chat thread header and directly from a character card.
- **D-02:** If a call starts from a character card and no thread exists yet, create the thread immediately before entering the call.
- **D-03:** End Call always returns to the originating thread with the call rows visible in scrollback, regardless of whether the call began from a thread or a character card.
- **D-04:** Phase 3 uses a minimal operational call screen rather than a polished final-product call surface.
- **D-05:** The call screen should show connection/call state, the MVP voice visualizer states, live call transcript, mute, end call, and device pickers where browser support exists.
- **D-06:** Phase 3 is a multi-turn call, not a one-shot exchange.
- **D-07:** User turns still have a clean end-of-turn boundary before the AI takes over. Phase 3 does not start AI speech while the user is still talking.
- **D-08:** After the user turn finalizes, the AI reply streams once generation starts rather than waiting for the full reply to complete.
- **D-09:** The call transcript should show user turns once finalized, while AI text streams live during generation.
- **D-10:** Streamed AI text should be forward-stable only. Once visible, text should not be rewritten.
- **D-11:** Phase 3 does not include voice-detected interruption or VAD barge-in.
- **D-12:** Phase 3 does include a button-based interrupt control during AI turns.
- **D-13:** Pressing interrupt cancels both playback and the rest of AI generation.
- **D-14:** After interrupt, the call returns immediately to listening.
- **D-15:** Interrupt must behave consistently whether audio has already started or the AI is still generating before first playback; in both cases the AI turn is canceled and the call returns to listening.
- **D-16:** The Phase 3 toolbar includes mute, end call, audio input picker, and audio output picker.
- **D-17:** Unsupported device pickers remain visible but disabled with a clear explanation, rather than being hidden or left broken.
- **D-18:** Mute must stop server-side user-audio consumption while keeping the call connected.
- **D-19:** End Call is destructive: if the AI is speaking or generating, ending the call stops playback, cancels remaining work, tears down the session, and writes a truthful `call_end`.
- **D-20:** Calls use the character's assigned default voice.
- **D-21:** If the character has no usable assigned voice, or the assigned voice is unavailable, call start is blocked with a clear recovery path rather than falling back silently.
- **D-22:** If mic permission is denied, stay out of the call, explain the denial clearly, and offer a retry path.
- **D-23:** If the backend or required models are not ready, block call start with a clear readiness error and recovery guidance.
- **D-24:** Phase 3 prefers honest blocking and clean teardown over optimistic half-connected states or silent fallbacks.
- **D-25:** If the network or peer connection drops mid-call, end the call cleanly, show a clear failure/end state, and preserve truthful records for what happened before the drop.
- **D-26:** Each successful or partial call writes `call_start`, per-turn `user_speech`, per-turn `ai_speech`, and `call_end` rows in chronological order in the unified thread.
- **D-27:** The call screen shows the live call transcript during the call, not only after hangup.
- **D-28:** Phase 3 is voice-only while the call is active. Typed text resumes after hangup.
- **D-29:** Phase 3 includes the three core Voice Visualizer states now: listening, thinking, and speaking.
- **D-30:** Those visualizer states only need MVP fidelity in Phase 3; full polish remains Phase 4 work.
- **D-31:** Phase 3 uses the full verification gate: relevant automated tests, browser coverage, live `OMEN-PC` verification, saved evidence artifacts, and only then Android product-owner acceptance.

### Claude's Discretion
- Exact route names, endpoint names, and event names, as long as they preserve the thread-owned call model above.
- Exact FSM/state-machine shape for listening, thinking, speaking, interrupted, ended, and failed states.
- Exact transcript layout and visual treatment, as long as the live-streaming and finalized-turn rules above are preserved.
- Exact browser capability messaging for unsupported device pickers.
- Exact storage shape for streamed/final AI transcript chunks and call metadata, as long as the unified chronological message record remains the user-visible source of truth.

### Deferred Ideas (OUT OF SCOPE)
- Voice-detected interruption and VAD barge-in remain Phase 4.
- Full call-feel polish, richer visualizer treatment, and more advanced call-state presentation remain Phase 4.
- In-call typed messaging remains out of scope for Phase 3.
- Automatic reconnect behavior remains out of scope for Phase 3.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-40 | A call can be initiated from any chat thread or directly from a character card, and the call inherits thread history as LLM context. [VERIFIED: repo grep] | Use a same-origin Web UI call façade that can create a thread on-demand, then hydrate prompt context from the existing thread service and prompt builder. [VERIFIED: repo grep] |
| REQ-47 | Toolbar must provide mute, end call, audio input picker, and audio output picker. [VERIFIED: repo grep] | Browser owns mute UI, `getUserMedia`, `enumerateDevices()`, `selectAudioOutput()`/`setSinkId()` capability checks, while backend enforces server-side mute. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement] |
| REQ-48 | Mic permission prompt surfaces on first call attempt, with denial handling and retry. [VERIFIED: repo grep] | Gate call bootstrap on `getUserMedia()` inside the Start Call gesture and handle `NotAllowedError` as a first-class UI state. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia] |
| REQ-49 | Voice Visualizer must show listening, thinking, and speaking states. [VERIFIED: repo grep] | Keep state ownership in the browser call FSM; drive RMS from mic/remote audio through the Web Audio graph, and fall back to deterministic state styling when browser support is limited. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/createMediaStreamSource] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/createMediaStreamDestination] |
| REQ-50 | Call end persists a summary row and returns the user to the thread composer. [VERIFIED: repo grep] | Web UI server must durably write `call_start` / `user_speech` / `ai_speech` / `call_end` rows into the existing `messages` chronology, then redirect the browser back to the thread route. [VERIFIED: repo grep] |
| REQ-63 | Call memory uses a sliding window of recent typed and call turns. [VERIFIED: repo grep] | Extend the existing prompt builder, which currently includes full non-stale history with no explicit window cap, to apply a recency limit before each AI turn. [VERIFIED: repo file] |
| REQ-A0 | The flow must work from Android Chrome on LAN. [VERIFIED: repo grep] | Plan explicit Android-safe audio unlock, HTTPS secure-context requirements, and live OMEN + Android evidence as part of the phase, not as cleanup. [VERIFIED: repo file] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume] |
</phase_requirements>

## Summary

Phase 3 planning must follow `03-CONTEXT.md`, not the stale one-shot wording in `ROADMAP.md`: the locked scope is now a multi-turn voice call with forward-stable streaming AI text, button interrupt, live transcript, and entry from both a thread header and a character card. [VERIFIED: repo file]

The repo already has the right ownership split. The browser owns mic permission, device selection, AudioContext unlock/resume, remote audio playback, and the visible call FSM. The Web UI server owns thread creation, voice/readiness checks, prompt hydration, and durable message writes. The AI backend owns `aiortc` peer termination, RTP/media handling, STT/TTS orchestration, and transport stats. [VERIFIED: repo grep] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

The main planning risk is not transport feasibility; it is seam discipline. `ai-backend/app/api/webrtc.py` is still a Phase 2 skeleton that returns `501`, `build_prompt_context()` currently has no sliding-window cap, and the `messages` table currently stores only `content_text` plus chronology fields. Phase 3 therefore needs a coordinated backend/browser/server slice, plus tests and evidence, not an isolated frontend task. [VERIFIED: repo file]

**Primary recommendation:** Use a same-origin `/api/calls/*` façade in `web-ui/server` to validate thread + voice + AI-backend readiness and persist call rows, proxy SDP to an `aiortc` session manager in `ai-backend`, keep browser media/device state in a dedicated call store/FSM, and apply explicit sliding-window prompt hydration before every AI turn. [VERIFIED: repo grep] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Start-call preflight (`thread`, voice availability, backend readiness) | API / Backend (`web-ui/server`) | Browser / Client | The browser should call RayMe-owned routes, and the existing server already owns settings, thread creation, and sanitized AI-backend status bridging. [VERIFIED: repo grep] |
| Mic permission, input picker, output picker, AudioContext unlock/resume | Browser / Client | — | These are browser APIs gated by secure context, user activation, and device permissions. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume] |
| WebRTC offer/answer, RTP ingest/egress, connection stats | API / Backend (`ai-backend`) | Browser / Client | `aiortc` terminates the remote peer, exposes connection state and stats, and should own the server half of the transport/session lifecycle. [VERIFIED: repo file] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer] |
| Live call FSM, transcript rendering, visualizer states | Browser / Client | API / Backend (`web-ui/server`) | The user-facing state machine and waveform belong in the browser, while durable transcript boundaries and final truth still come from server writes. [VERIFIED: repo file] [VERIFIED: repo grep] |
| Sliding-window call context hydration | API / Backend (`web-ui/server`) | Database / Storage | Prompt assembly already lives in the web server prompt builder and reads the unified thread chronology. [VERIFIED: repo file] |
| Chronological `messages` writeback (`call_start`, `user_speech`, `ai_speech`, `call_end`) | API / Backend (`web-ui/server`) | Database / Storage | The existing SQLAlchemy thread/chat services already own sequence allocation and durable thread updates. [VERIFIED: repo file] |
| Server-side mute enforcement | API / Backend (`ai-backend`) | Browser / Client | REQ-47 explicitly requires server-side audio consumption to stop, which cannot be guaranteed by local UI muting alone. [VERIFIED: repo grep] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `aiortc` | `1.14.0` (PyPI 2025-10-13) [VERIFIED: PyPI] | Python WebRTC peer, RTP, SCTP/data channel, connection stats | It is already pinned in `ai-backend`, and its official API covers `RTCPeerConnection`, `addTrack()`, `createDataChannel()`, `setLocalDescription()`, and `getStats()`. [VERIFIED: repo file] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer] |
| `FastAPI` | `0.136.1` (PyPI 2026-04-23) [VERIFIED: PyPI] | Same-origin Web UI façade and AI backend APIs | Both services already use FastAPI, so Phase 3 should extend existing routers and dependency patterns rather than introduce a new control plane. [VERIFIED: repo file] |
| `SvelteKit` | `2.58.0` (npm 2026-04-23) [VERIFIED: npm registry] | Browser call route, FSM shell, transcript UI | The client already runs on SvelteKit/Svelte 5, with existing chat/thread patterns and Playwright coverage scaffolding. [VERIFIED: repo file] |
| `Svelte` | `5.55.5` (npm 2026-04-23) [VERIFIED: npm registry] | Reactive call store/UI state | Reuse the current rune-based client style instead of adding a separate state library. [VERIFIED: repo file] |
| `SQLAlchemy` | `2.0.49` (PyPI 2026-04-03) [VERIFIED: PyPI] | Thread/message durability and migrations | The unified thread model already exists here, and Phase 3 must preserve it as the user-visible source of truth. [VERIFIED: repo file] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@playwright/test` | `1.59.1` (npm 2026-04-01) [VERIFIED: npm registry] | Browser acceptance on desktop + Pixel 5 emulation | Use for persisted UI evidence before OMEN and Android handoff. The repo already has desktop and mobile Chromium projects configured. [VERIFIED: repo file] |
| `vitest` | `4.1.5` (npm 2026-04-21) [VERIFIED: npm registry] | Client FSM/store/unit coverage | Use for call-state, capability-messaging, and transcript-rendering logic that does not need a live peer. [VERIFIED: repo file] |
| `pytest` | `9.0.3` (PyPI 2026-04-07) [VERIFIED: PyPI] | Web server and ai-backend unit/integration coverage | Use for prompt-windowing, call-writeback, signaling contracts, and aiortc session teardown behavior. `uv run pytest` is available in both Python projects. [VERIFIED: exec] |
| Browser Web APIs | Current platform APIs [CITED: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/addTrack] | `getUserMedia()`, `enumerateDevices()`, `selectAudioOutput()`, `setSinkId()`, `AudioContext`, WebRTC tracks | Use the platform APIs directly; do not wrap them in an extra client transport abstraction in Phase 3. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `aiortc` remote peer | Custom PCM/WebSocket audio transport | Do not do this. `aiortc` already handles peer state, RTP, SCTP/data channels, and stats; a raw socket path would recreate transport, buffering, and cleanup work Phase 3 does not need. [VERIFIED: repo file] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer] |
| Same-origin Web UI call façade | Browser calling AI backend directly | Do not do this. Existing repo policy is that the browser talks to RayMe-owned routes, while the web server owns settings, readiness, and sanitized errors. [VERIFIED: repo grep] |
| Unified `messages` chronology | Separate call-history store | Do not do this. REQ-50 and the existing schema direction require interleaved text + call rows in one thread. [VERIFIED: repo grep] [VERIFIED: repo file] |

**Installation:**
```bash
uv sync --project ai-backend
uv sync --project web-ui/server
cd web-ui/client && npm install
```

**Version verification:** Current versions were verified against PyPI and npm on 2026-04-25. [VERIFIED: PyPI] [VERIFIED: npm registry]

## Architecture Patterns

### System Architecture Diagram

```text
User taps Start Call
  |
  v
Browser Call Route (SvelteKit)
  - getUserMedia()
  - AudioContext resume/unlock
  - enumerateDevices()/output capability check
  - local call FSM
  |
  | POST /api/calls/start + /offer + control actions
  v
Web UI Server (FastAPI)
  - create thread if needed
  - validate character default voice + backend readiness
  - write call_start
  - hydrate sliding-window prompt context
  - proxy SDP/control to AI backend
  - persist finalized user_speech / ai_speech / call_end
  |
  | SDP / session-control
  v
AI Backend (FastAPI + aiortc)
  - RTCPeerConnection session manager
  - inbound mic track
  - STT turn-finalize
  - LLM/TTS orchestration hooks
  - outbound AI audio track
  - connection/transport stats + timing instrumentation
  |
  | RTP audio up/down + RTCDataChannel events [ASSUMED]
  v
Browser Call Route
  - remote audio playback
  - live transcript rendering
  - visualizer state updates
  - interrupt / mute / end call UI
```

### Recommended Project Structure

```text
ai-backend/app/
├── api/webrtc.py              # Replace skeleton routes with live call signaling/session endpoints
├── call/session.py            # Per-call aiortc session object, timers, stats, cleanup
├── call/tracks.py             # Custom inbound/outbound audio track helpers
└── call/events.py             # Data-channel/control event contract [ASSUMED]

web-ui/server/app/
├── api/calls.py               # Same-origin call bootstrap/control/writeback routes
├── domain/call_service.py     # Thread/voice/readiness checks + durable call row writes
└── domain/prompt_builder.py   # Sliding-window extension over existing prompt assembly

web-ui/client/src/
├── lib/call/client.ts         # Browser peer/bootstrap helpers
├── lib/call/store.svelte.ts   # Call FSM and capability state
├── lib/call/audio.ts          # AudioContext unlock, device enumeration, visualizer hooks
└── routes/(chat|call)/...     # Minimal operational call screen and return-to-thread flow
```

### Pattern 1: Same-Origin Call Bootstrap

**What:** The browser should call a RayMe-owned Web UI route first, not the AI backend directly. The server validates thread ownership, default voice availability, and backend readiness before any offer/answer exchange starts. [VERIFIED: repo grep]

**When to use:** Always, for both thread-header entry and character-card entry. [VERIFIED: repo file]

**Example:**
```typescript
// Source: adapted from current repo routing + REQ-40 / D-01..D-03
const bootstrap = await fetch('/api/calls/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ threadId, characterId })
}).then((r) => r.json());

// bootstrap returns the durable thread id and server-approved session metadata
```

### Pattern 2: Explicit Offer/Answer With aiortc Session Objects

**What:** Use one `RTCPeerConnection` per live call session on the AI backend, with explicit state listeners and deterministic teardown. `aiortc` exposes connection state, ICE state, `createOffer()/createAnswer()`, `setLocalDescription()`, and `getStats()`. [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

**When to use:** Every live call. Treat the session object as the unit of cleanup, logging, and mute/interrupt enforcement. [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

**Example:**
```python
# Source: adapted from aiortc docs
pc = RTCPeerConnection()

@pc.on("connectionstatechange")
async def on_connectionstatechange() -> None:
    if pc.connectionState == "failed":
        await pc.close()

offer = RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
await pc.setRemoteDescription(offer)
answer = await pc.createAnswer()
await pc.setLocalDescription(answer)
return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
```

### Pattern 3: Browser Track Wiring With `addTrack()` and `ontrack`

**What:** Add the mic track to the browser peer with `addTrack()`, and attach inbound AI audio via `ontrack`. `addTrack()` is the current browser API; do not build around legacy `addStream()`. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/addTrack]

**When to use:** During initial peer setup and whenever you rebind the mic track after device changes. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/addTrack]

**Example:**
```typescript
// Source: adapted from MDN addTrack/ontrack examples
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
stream.getTracks().forEach((track) => pc.addTrack(track, stream));

pc.ontrack = ({ streams }) => {
  remoteAudio.srcObject = streams[0];
};
```

### Pattern 4: AudioContext-Owned Unlock, Metering, and Foreground Resume

**What:** Create/resume the `AudioContext` during the Start Call gesture, observe `statechange`, and keep foreground-resume handling in the call audio helper. `resume()` resolves when the context resumes, and `statechange` fires whenever the state changes. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/statechange_event]

**When to use:** Before the first call starts, after visibility/foreground return, and before any output picker action that requires transient activation. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput]

**Example:**
```typescript
// Source: adapted from MDN resume/statechange docs
const audioCtx = new AudioContext();
audioCtx.onstatechange = () => console.log(audioCtx.state);

await audioCtx.resume();
if (audioCtx.state !== 'running') {
  throw new Error('audio_context_not_running');
}
```

### Pattern 5: Sliding-Window Prompt Hydration Before Each AI Turn

**What:** Extend the existing prompt builder to cap recent turns instead of replaying the full non-stale thread. The current implementation appends every non-stale `user` and `assistant` message and has no explicit window limit. [VERIFIED: repo file]

**When to use:** At call start and after each finalized user turn before generation begins. [VERIFIED: repo grep]

**Example:**
```python
# Source: adapted from current build_prompt_context()
history = await build_prompt_context(thread_id, repository=SqlAlchemyPromptRepository(session))
window = history[-N_RECENT_TURNS:]
```

### Anti-Patterns to Avoid

- **Direct browser -> AI backend signaling:** It bypasses the existing server-owned readiness, thread creation, and sanitized error boundaries. [VERIFIED: repo grep]
- **Local-only mute:** REQ-47 requires server-side audio consumption to stop, so muting only the HTML audio element or local track is insufficient. [VERIFIED: repo grep]
- **Separate call-history store:** It fights the existing unified chronology model and will force thread rehydration complexity immediately. [VERIFIED: repo file]
- **Treating `ROADMAP.md` as the final phase contract:** For this phase it is stale on the turn model; `03-CONTEXT.md` is the authoritative scope artifact. [VERIFIED: repo file]
- **Letting aiortc sessions outlive UI teardown:** Session objects must close on hangup, network failure, and navigation-away paths, or you will leak tracks, timers, and model work. [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RTP/media transport | Custom raw audio framing over WebSocket | `aiortc` peer/session objects | WebRTC transport, ICE, DTLS/SRTP, SCTP, and stats are already solved there. [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer] |
| Input/output device discovery | Custom browser heuristics | `getUserMedia()`, `enumerateDevices()`, `selectAudioOutput()`, `setSinkId()` | Device exposure is permission- and secure-context-gated by the browser. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement] |
| Remote audio graph export | Ad hoc hidden-element hacks | `AudioContext.createMediaStreamDestination()` / `createMediaStreamSource()` | The Web Audio API already gives you graph nodes and `MediaStream` interop for metering and routing. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/createMediaStreamDestination] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/createMediaStreamSource] |
| Message chronology | Separate call table or shadow store | Existing `messages` table sequence model | The repo already enforces one chronology with `message_kind` values for call rows. [VERIFIED: repo file] |
| AI-backend readiness mapping | Duplicated client-side probing logic | Existing `AiBackendClient` + `/api/ai-backend/status` bridge | The server already centralizes sanitized status/errors and should stay the single readiness source. [VERIFIED: repo file] |

**Key insight:** Phase 3 should spend engineering effort on session boundaries, cleanup, and durable writeback, not on rebuilding transport or browser capability layers that the current stack already provides. [VERIFIED: repo grep] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

## Common Pitfalls

### Pitfall 1: Planning Against the Wrong Scope Document

**What goes wrong:** The plan implements the old one-shot/non-streaming MVP from `ROADMAP.md` and misses multi-turn streaming, live transcript, and interrupt behavior. [VERIFIED: repo file]

**Why it happens:** The roadmap phrasing predates the fresh user discussion; `03-CONTEXT.md` supersedes it for this phase. [VERIFIED: repo file]

**How to avoid:** Treat `03-CONTEXT.md` as the locked phase contract and cite it explicitly in every plan touching turn flow or UI scope. [VERIFIED: repo file]

**Warning signs:** Plan tasks say "single reply", "one sentence only", or omit interrupt/live transcript work. [VERIFIED: repo file]

### Pitfall 2: Audio Unlock Happens Too Late

**What goes wrong:** Android Chrome shows the mic prompt but remote TTS never becomes audible because the audio context did not reach `running` during the user gesture. [VERIFIED: phase brief]

**Why it happens:** `AudioContext.resume()` is asynchronous, output selection requires secure context and transient activation, and background/foreground transitions can change audio state. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/statechange_event] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput]

**How to avoid:** Build a dedicated `unlockAudioForCall()` path that runs inside the Start Call tap, verifies `audioCtx.state === 'running'`, and re-checks state on visibility/foreground resume. [VERIFIED: phase brief] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume]

**Warning signs:** TTS arrives over the peer but `<audio>` stays silent on Android; `AudioContext.state` logs `suspended` or `interrupted`. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/state]

### Pitfall 3: Device Pickers Assumed To Work Everywhere

**What goes wrong:** The UI treats input/output pickers as universally available and breaks on browsers that omit devices, block labels, or do not support output selection. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput]

**Why it happens:** `enumerateDevices()` omits blocked or unpermitted devices, and `selectAudioOutput()` is secure-context-only, activation-gated, and experimental. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput]

**How to avoid:** Keep both pickers visible, but derive `supported`, `enabled`, and `explanation` state separately for input and output. That matches locked decision D-17. [VERIFIED: repo file]

**Warning signs:** Empty device labels before permission, missing `audiooutput` entries, or output switch failures after persisting an old device id. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput]

### Pitfall 4: Mute Only Silences Locally

**What goes wrong:** The toolbar says muted, but the backend still receives and processes user audio, violating REQ-47. [VERIFIED: repo grep]

**Why it happens:** UI muting an element or gain node does not automatically stop server-side track consumption. [VERIFIED: repo grep]

**How to avoid:** Make mute a session-level control that reaches the AI backend and changes inbound-track handling or STT consumption, then log the resulting frame/packet-rate drop. [VERIFIED: phase brief] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

**Warning signs:** STT continues emitting speech events while the UI shows muted, or backend stats/logs do not change after mute. [VERIFIED: phase brief]

### Pitfall 5: Prompt Builder Accidentally Replays The Whole Thread

**What goes wrong:** Long threads bloat call latency and token cost because call turns reuse the current text-chat prompt builder without a recency cap. [VERIFIED: repo file]

**Why it happens:** `build_prompt_context()` currently appends all non-stale `user` and `assistant` messages and has no explicit sliding-window rule. [VERIFIED: repo file]

**How to avoid:** Add a dedicated windowing layer for call turns now, and make the limit configurable in one place. [VERIFIED: repo file]

**Warning signs:** Prompt payload size grows monotonically with thread length or Phase 3 plans mention "hydrate full thread". [VERIFIED: repo file]

### Pitfall 6: Call Summary Needs Structured Data But The Message Schema Is Minimal

**What goes wrong:** You can render transcript text, but `call_end` cannot reliably show duration, voice used, or truthful end reason without awkward parsing or duplicated state. [VERIFIED: repo file] [VERIFIED: repo grep]

**Why it happens:** `Message` currently stores chronology, kind, role, and `content_text`, but no per-message metadata field. [VERIFIED: repo file]

**How to avoid:** Decide early whether Phase 3 adds structured call metadata to `messages` or keeps a deliberately text-only summary row. My recommendation is to add structured metadata now. [ASSUMED]

**Warning signs:** Planning discussions start inventing string formats for duration/voice/end-reason parsing. [ASSUMED]

## Code Examples

Verified patterns from official sources:

### Browser Mic Track + Remote Audio
```typescript
// Source: MDN addTrack/ontrack
const pc = new RTCPeerConnection();
const localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
for (const track of localStream.getTracks()) {
  pc.addTrack(track, localStream);
}

pc.ontrack = ({ streams }) => {
  remoteAudio.srcObject = streams[0];
};
```
[CITED: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/addTrack]

### aiortc Answer Flow
```python
# Source: aiortc API docs
pc = RTCPeerConnection()
await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
answer = await pc.createAnswer()
await pc.setLocalDescription(answer)
payload = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
```
[CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]

### AudioContext Resume + State Tracking
```typescript
// Source: MDN resume/statechange docs
const audioCtx = new AudioContext();
audioCtx.onstatechange = () => console.log(audioCtx.state);

await audioCtx.resume();
if (audioCtx.state !== 'running') {
  throw new Error('audio_context_not_running');
}
```
[CITED: https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/statechange_event]

### Output Picker Capability Guard
```typescript
// Source: MDN selectAudioOutput docs
const canSelectOutput = Boolean(navigator.mediaDevices?.selectAudioOutput);
if (canSelectOutput) {
  const device = await navigator.mediaDevices.selectAudioOutput();
  await audioEl.setSinkId(device.deviceId);
}
```
[CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `RTCPeerConnection.addStream()` | `addTrack()` per track | Modern WebRTC API; MDN currently documents `addTrack()` as the standard path. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/addTrack] | Plan browser track wiring around individual audio tracks and `ontrack`, not legacy stream-only semantics. |
| Persist raw audio-output `deviceId` and call `setSinkId()` directly later | Re-authorize via `selectAudioOutput()` before `setSinkId()` | Current MDN guidance notes device ids may change and must be passed through `selectAudioOutput()` successfully before reuse. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput] | Output picker UX must tolerate unsupported browsers and stale device ids. |
| Poll or side-channel control transport | Reuse WebRTC data channels for call-adjacent messages | `RTCPeerConnection.createDataChannel()` is a first-class API in browsers and `aiortc`. [CITED: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/createDataChannel] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer] | Inference: using one peer for media + control reduces Phase 4 transport sprawl. [ASSUMED] |

**Deprecated/outdated:**
- `ROADMAP.md`'s "one-sentence non-streaming reply" phrasing is outdated for Phase 3 and should not drive planning. `03-CONTEXT.md` is newer and user-confirmed. [VERIFIED: repo file]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | RESOLVED in planning: Phase 3 intentionally ships text-only `messages.content_text` call rows and no message metadata migration. Required duration, voice, start/end, and call state details are written into the `call_start` / `call_end` content text and evidence files. Structured metadata can be added later only if Phase 4+ proves the string contract insufficient. | Common Pitfalls / Architecture Patterns | Could delay richer analytics, but avoids an unnecessary migration while the existing unified message kind model already satisfies Phase 3 user-visible truth. |
| A2 | RESOLVED in planning: Phase 3 uses WebRTC for browser-to-AI-backend audio plus a WebRTC `rayme-events` data channel for AI-backend call events such as `user_final` and `ai_audio_started`. Browser-to-Web-UI-server transcript/LLM streaming uses same-origin HTTP/SSE through `/api/calls/{call_id}/turns`. Server-to-AI-backend control and TTS playback uses HTTP routes under `/webrtc/sessions/{session_id}`. | System Architecture / State of the Art | Adds one data-channel schema now, but prevents the impossible gap where finalized speech appears without a transport from aiortc/STT to the browser/server turn loop. |

## Open Questions (RESOLVED)

1. **Should Phase 3 extend `messages` with structured metadata now, or intentionally ship text-only call rows first?**
   - What we know: the current `Message` model has no metadata field, but REQ-50 wants duration, voice used, and truthful call-end data. [VERIFIED: repo file] [VERIFIED: repo grep]
   - Decision: ship text-only call rows first. `call_start` and `call_end` rows must include human-readable duration, voice, start/end timestamp, and reason text. `user_speech` and `ai_speech` rows store finalized transcript text. No Phase 3 schema migration is required unless implementation discovers an existing testable blocker. [PLANNING DECISION: 2026-04-25]

2. **Will the live transcript/state path use a data channel or server-polling/SSE?**
   - What we know: the context locks live in-call transcript and interrupt behavior, and both browser WebRTC and aiortc support data channels. [VERIFIED: repo file] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/createDataChannel] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer]
   - Decision: use a narrow WebRTC `rayme-events` data channel only for AI-backend-originated call events (`user_final`, `ai_audio_started`, `muted`, `interrupted`, `ended`, `failed`). Browser-to-Web-UI-server LLM transcript streaming remains same-origin HTTP/SSE through `/api/calls/{call_id}/turns`, and server-to-AI-backend TTS/control remains HTTP. [PLANNING DECISION: 2026-04-25]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `node` | SvelteKit/Vite/Vitest/Playwright workflows | ✓ [VERIFIED: exec] | `v22.22.2` [VERIFIED: exec] | — |
| `npm` | Client dependency install and test commands | ✓ [VERIFIED: exec] | `10.9.7` [VERIFIED: exec] | — |
| `python3` | Both FastAPI services | ✓ [VERIFIED: exec] | `3.12.3` [VERIFIED: exec] | — |
| `uv` | Python project sync and pytest execution | ✓ [VERIFIED: exec] | `0.11.6` [VERIFIED: exec] | — |
| `pytest` via `uv run` | Server + AI-backend test execution | ✓ [VERIFIED: exec] | `9.0.3` [VERIFIED: exec] | — |
| `playwright` via `npx` | Browser acceptance tests | ✓ [VERIFIED: exec] | `1.59.1` [VERIFIED: exec] | — |
| `vitest` via `npx` | Client unit tests | ✓ [VERIFIED: exec] | `4.1.5` [VERIFIED: exec] | — |
| `ssh rayme-pmpg` alias | OMEN deployment / live verification | ✓ [VERIFIED: exec] | alias configured [VERIFIED: exec] | — |
| `mkcert` | New cert issuance if TLS material must change | ✗ [VERIFIED: exec] | — | Reuse existing Phase 1 TLS artifacts per operating notes. [VERIFIED: repo file] |
| `adb` | Android device automation | ✗ [VERIFIED: exec] | — | Manual Android product-owner acceptance only. [VERIFIED: repo file] |
| Local Chrome/Chromium CLI | Ad hoc browser probing from shell | ✗ [VERIFIED: exec] | — | Use Playwright-managed browser runs. [VERIFIED: repo file] |

**Missing dependencies with no fallback:**
- None for planning or local automated testing. [VERIFIED: exec]

**Missing dependencies with fallback:**
- `mkcert` is not present locally, but the project explicitly says to reuse existing TLS material rather than generate throwaway certs. [VERIFIED: exec] [VERIFIED: repo file]
- `adb` is not present, so Android evidence remains manual after agent-run browser and OMEN verification. [VERIFIED: exec] [VERIFIED: repo file]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3` for `ai-backend` and `web-ui/server`; `vitest 4.1.5`; `@playwright/test 1.59.1`. [VERIFIED: repo file] [VERIFIED: exec] |
| Config file | `ai-backend/pyproject.toml`, `web-ui/server/pyproject.toml`, `web-ui/client/vitest.config.ts`, `web-ui/client/playwright.config.ts`. [VERIFIED: repo file] |
| Quick run command | `cd ai-backend && uv run pytest tests/test_webrtc_signaling.py -q && cd ../web-ui/client && npx vitest tests/unit/app-shell.test.ts && npx playwright test tests/e2e/chat-stream.spec.ts --project=desktop-chromium` [VERIFIED: repo file] |
| Full suite command | `cd ai-backend && uv run pytest && cd ../web-ui/server && uv run pytest && cd ../client && npx vitest run && npx playwright test` [VERIFIED: repo file] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-40 | Start call from thread header and character card, creating a thread when needed | Playwright + server integration | `cd web-ui/client && npx playwright test tests/e2e/call-start.spec.ts --project=desktop-chromium` | ❌ Wave 0 |
| REQ-47 | Mute halts server-side consumption; device pickers show supported/disabled states honestly | ai-backend pytest + Playwright | `cd ai-backend && uv run pytest tests/test_call_session.py::test_mute_stops_server_consumption -q && cd ../web-ui/client && npx playwright test tests/e2e/call-toolbar.spec.ts --project=desktop-chromium` | ❌ Wave 0 |
| REQ-48 | First-call mic permission prompt and denial/retry handling | Playwright | `cd web-ui/client && npx playwright test tests/e2e/call-permissions.spec.ts --project=desktop-chromium` | ❌ Wave 0 |
| REQ-49 | Listening / thinking / speaking visualizer state transitions | Vitest + Playwright smoke | `cd web-ui/client && npx vitest tests/unit/call-state.test.ts && npx playwright test tests/e2e/call-visualizer.spec.ts --project=desktop-chromium` | ❌ Wave 0 |
| REQ-50 | `call_start` / `user_speech` / `ai_speech` / `call_end` rows render chronologically and return to composer | web-ui/server pytest + Playwright | `cd web-ui/server && uv run pytest tests/test_calls.py::test_call_summary_rows_written -q && cd ../client && npx playwright test tests/e2e/call-summary.spec.ts --project=desktop-chromium` | ❌ Wave 0 |
| REQ-63 | Call prompt hydration uses a sliding window of recent turns | web-ui/server pytest | `cd web-ui/server && uv run pytest tests/test_prompt_builder.py::test_call_context_sliding_window -q` | ❌ Wave 0 |
| REQ-A0 | Browser call loop works on mobile browser path and real Android acceptance | Playwright mobile + live/manual | `cd web-ui/client && npx playwright test tests/e2e/call-mobile.spec.ts --project=mobile-chromium` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** run the smallest affected pytest/vitest target plus one desktop Playwright call-flow spec. [VERIFIED: repo file]
- **Per wave merge:** rerun all new Phase 3 call pytest targets plus desktop + mobile-emulation Playwright call specs. [VERIFIED: repo file]
- **Phase gate:** full local suite, then live OMEN deployment/evidence, then Android product-owner acceptance. That sequence is explicitly required by D-31 and operating notes. [VERIFIED: repo file]

### Wave 0 Gaps

- [ ] `ai-backend/tests/test_call_session.py` — call session lifecycle, mute enforcement, interrupt, teardown, and stats. [VERIFIED: repo file]
- [ ] `web-ui/server/tests/test_calls.py` — bootstrap/writeback APIs, thread creation from character card, and call summary persistence. [VERIFIED: repo file]
- [ ] `web-ui/client/tests/unit/call-state.test.ts` — browser FSM transitions and capability messaging. [VERIFIED: repo file]
- [ ] `web-ui/client/tests/e2e/call-start.spec.ts` — desktop start/end flow with thread return. [VERIFIED: repo file]
- [ ] `web-ui/client/tests/e2e/call-toolbar.spec.ts` — mute/device picker behavior and disabled explanations. [VERIFIED: repo file]
- [ ] `web-ui/client/tests/e2e/call-summary.spec.ts` — summary row render in thread scrollback. [VERIFIED: repo file]
- [ ] `web-ui/client/tests/e2e/call-mobile.spec.ts` — Pixel 5 emulation path before real Android handoff. [VERIFIED: repo file]
- [ ] Saved Phase 3 evidence docs under `.planning/phases/03-first-working-call-mvp/` for Playwright and OMEN runs, per operating notes. [VERIFIED: repo file]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Project runs unauthenticated on LAN by design. [VERIFIED: repo file] |
| V3 Session Management | no | There is no user-login/session layer in this product scope. [VERIFIED: repo file] |
| V4 Access Control | no | Same-origin route ownership matters operationally, but there is no user-role access model in v1. [VERIFIED: repo file] |
| V5 Input Validation | yes | Use existing FastAPI/Pydantic validation on call bootstrap/control payloads and continue browser-side capability guards. [VERIFIED: repo file] |
| V6 Cryptography | yes | Rely on HTTPS secure context and WebRTC/aiortc DTLS-SRTP; do not hand-roll transport crypto. [VERIFIED: repo file] [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unsanitized live transcript or call-summary rendering | Tampering / XSS | Reuse the existing sanitized markdown/render boundary on thread messages; do not bypass it for call rows. [VERIFIED: repo file] |
| Raw backend exception leakage through call status/control APIs | Information Disclosure | Reuse the existing sanitized AI-backend client and public error mapping pattern. [VERIFIED: repo file] |
| Insecure-context media failures misdiagnosed as app bugs | Denial of Service | Keep HTTPS/secure-context checks visible and gate call start on them. `getUserMedia()` is secure-context-only. [VERIFIED: repo file] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia] |
| Long-lived orphaned peer sessions after hangup/navigation | Denial of Service | Make hangup and failure paths call `pc.close()` and clear session objects/timers deterministically. [CITED: https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer] |

## Sources

### Primary (HIGH confidence)
- Local repo files:
  - `.planning/phases/03-first-working-call-mvp/03-CONTEXT.md`
  - `.planning/REQUIREMENTS.md`
  - `.planning/STATE.md`
  - `.planning/ROADMAP.md`
  - `.planning/PROJECT.md`
  - `.planning/OPERATING-NOTES.md`
  - `.planning/LEARNINGS.md`
  - `ai-backend/app/api/webrtc.py`
  - `ai-backend/app/main.py`
  - `ai-backend/app/models/model_manager.py`
  - `web-ui/server/app/api/chat.py`
  - `web-ui/server/app/api/threads.py`
  - `web-ui/server/app/domain/prompt_builder.py`
  - `web-ui/server/app/domain/ai_backend_client.py`
  - `web-ui/server/app/storage/models.py`
  - `web-ui/client/package.json`
  - `web-ui/client/playwright.config.ts`
  - `web-ui/client/vitest.config.ts`
- Context7:
  - `/aiortc/aiortc` - `RTCPeerConnection`, `createDataChannel`, `getStats`, offer/answer patterns.
- Official docs:
  - https://aiortc.readthedocs.io/en/latest/api.html?highlight=createOffer
  - https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/addTrack
  - https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/createDataChannel
  - https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
  - https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices
  - https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/selectAudioOutput
  - https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement
  - https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume
  - https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/statechange_event
  - https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/createMediaStreamDestination
  - https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/createMediaStreamSource
  - https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/state

### Secondary (MEDIUM confidence)
- PyPI JSON API lookups for package versions and publish dates. [VERIFIED: PyPI]
- npm registry lookups for package versions and publish dates. [VERIFIED: npm registry]

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - the phase extends already-pinned repo dependencies, and versions were re-verified against PyPI/npm today. [VERIFIED: repo file] [VERIFIED: PyPI] [VERIFIED: npm registry]
- Architecture: HIGH - ownership boundaries are strongly established in the repo, with only two explicit discretion items left to planning (`messages` metadata shape and event transport). [VERIFIED: repo file] [ASSUMED]
- Pitfalls: HIGH - they are backed by the phase brief, repo operating rules, and current browser/API docs. [VERIFIED: repo file] [CITED: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia]

**Research date:** 2026-04-25
**Valid until:** 2026-05-25
