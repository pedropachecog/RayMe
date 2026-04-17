# Architecture Research

**Domain:** Self-hosted real-time voice-AI web app over LAN (RayMe)
**Researched:** 2026-04-16
**Confidence:** HIGH for transport + pipeline shape; MEDIUM for VRAM coexistence on RTX 3060; MEDIUM for framework selection

---

## Executive Summary

RayMe is a three-service system connected over LAN. The load-bearing architectural decisions are:

1. **Audio transport:** WebRTC (not raw WebSocket + PCM). WebSocket-based audio pipelines stall on packet loss, lack built-in echo cancellation/AGC/noise suppression, and provide no JS-level jitter buffer. WebRTC is the standard-of-care for realtime voice AI agents in 2026 and the path most compatible with mobile Safari's media pipeline.
2. **Duplex loop:** Streaming, cancellable pipeline — browser mic -> server VAD gates STT -> streaming LLM -> sentence-chunked streaming TTS -> browser playback. Barge-in is detected **server-side** on the same mic stream, not in the browser, so cancellation is race-free.
3. **AI backend shape:** A single Python asyncio orchestrator with one in-process STT, one VAD, and a **single hot TTS engine** (F5 *or* XTTS, swapped on demand). Each TTS engine's footprint (~6-8 GB each) makes coexistence on a 12 GB 3060 fragile once STT and VAD are loaded.
4. **Persistence:** Web UI host owns durable state (SQLite + filesystem blob store). AI backend is **stateless per call**. This is what lets the GPU box be restarted without losing chat history.
5. **HTTPS is non-negotiable for mobile:** iOS Safari blocks `getUserMedia()` without a secure context. mkcert-signed certs (with root CA installed on each device) are the pragmatic LAN answer.

Two decisions most likely to need revisiting:

- **Framework: custom orchestrator vs Pipecat.** Starting custom gives full control over barge-in semantics and state; Pipecat could replace it later if orchestration becomes the bottleneck. If a single call works end-to-end in two weeks, custom was right.
- **F5 ↔ XTTS cold-swap vs keeping one engine loaded.** If swap latency is noticeable (1-3 s on first use after change), we may need to pick one engine as the hot default and lazy-load the other only when a voice explicitly requires it.

---

## Standard Architecture

### System Overview

```
                    ┌──────────────────────────────────────────┐
                    │              Browser (client)             │
                    │  ┌─────────────┐  ┌────────────────────┐  │
                    │  │ Web UI app  │  │ RTCPeerConnection  │  │
                    │  │ (React/SPA) │  │ + <audio> playback │  │
                    │  └──────┬──────┘  └──────────┬─────────┘  │
                    └─────────┼─────────────────────┼──────────┘
                              │ HTTPS (REST)        │ WebRTC (SRTP/UDP)
                              │ WSS (chat events)   │ + RTCDataChannel (captions/control)
                              │                     │
        ┌─────────────────────┼─────────┐           │
        │      Web UI Host    │         │           │
        │  (serves SPA + API) │         │           │
        │  ┌────────────────┐ │         │           │
        │  │ Chat API       │ │         │           │
        │  │ Characters API │ │         │           │
        │  │ Voices API     │ │         │           │
        │  │ Settings API   │ │         │           │
        │  │ Audio blob API │ │         │           │
        │  └───────┬────────┘ │         │           │
        │  ┌───────┴────────┐ │         │           │
        │  │ SQLite + FS    │ │         │           │
        │  │ blob store     │ │         │           │
        │  └────────────────┘ │         │           │
        └──────────┬──────────┘         │           │
                   │ HTTPS (REST)       │           │
                   │ thread writeback   │           │
                   │                    │           │
                   │         ┌──────────┴───────────┴──────┐
                   │         │      AI Backend (GPU box)   │
                   │         │  ┌────────────────────────┐ │
                   │         │  │ aiortc WebRTC endpoint │ │
                   │         │  │ (SRTP in/out, DC)      │ │
                   │         │  └───────────┬────────────┘ │
                   │         │  ┌───────────┴────────────┐ │
                   │         │  │ Call Orchestrator      │ │
                   │         │  │ (asyncio state machine)│ │
                   │         │  └───────────┬────────────┘ │
                   │         │      ┌───────┼───────┐       │
                   │         │   ┌──┴──┐ ┌──┴──┐ ┌──┴──┐    │
                   │         │   │ VAD │ │ STT │ │ TTS │    │
                   │         │   │ Sil.│ │fW-v3│ │F5|X │    │
                   │         │   └─────┘ └─────┘ └─────┘    │
                   │         └──────────────┬───────────────┘
                   │                        │ HTTPS (streaming)
                   │                        │ OpenAI Chat Completions
                   │                        │
                   │                ┌───────┴───────┐
                   └───────────────>│ LLM server    │
                  (also allowed;    │ (llama-server │
                   Web UI may call  │  or OpenAI    │
                   for non-call     │  API)         │
                   text replies)    └───────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|---------------|------------------------|
| **Browser (Web UI)** | Render SPA, capture mic via `getUserMedia`, play TTS via `<audio>`, show live captions, own user gestures | React/Svelte SPA + `RTCPeerConnection` |
| **Browser (RTC)** | Full-duplex media: send mic Opus track, receive TTS Opus track, exchange control/caption events on data channel | Native WebRTC in Chromium + WebKit |
| **Web UI Host** | Serve SPA (TLS), expose REST API for durable state (chats, characters, voices, settings, saved audio), bootstrap endpoint config to browser | FastAPI or Node Fastify behind a self-signed HTTPS cert |
| **Persistence (on UI host)** | Chat threads + interleaved text/call turns, characters, voices (metadata + reference audio), saved call audio blobs, settings | SQLite file + `data/blobs/` directory on disk |
| **AI Backend (RTC endpoint)** | Terminate WebRTC media from browser, decode Opus, feed PCM frames into VAD/STT, re-encode TTS frames to Opus outbound | aiortc (Python asyncio WebRTC) |
| **AI Backend (Orchestrator)** | Run the cancellable call state machine, coordinate VAD/STT/LLM/TTS, publish captions + control on data channel, POST turn records to Web UI host | Custom Python asyncio module (Pipecat optional later) |
| **AI Backend (VAD)** | Gate STT, detect barge-in during TTS playback | Silero VAD (ONNX) on CPU, <1 ms/30 ms frame |
| **AI Backend (STT)** | Stream transcripts from mic PCM, tolerant of Spanish-accented English | `faster-whisper` large-v3 or large-v3-turbo, INT8/FP16, CTranslate2 |
| **AI Backend (TTS)** | Stream synthesized audio chunks from LLM text deltas | F5-TTS *or* XTTS v2 (one hot at a time), sentence-chunked |
| **LLM server** | OpenAI-compatible `/v1/chat/completions` streaming | `llama-server` (llama.cpp) on LLM box, or OpenAI API |

### Ownership Table

| State | Owner | Rationale |
|-------|-------|-----------|
| Chat threads, turns, saved audio blobs, characters, voice metadata, settings | **Web UI host** | AI backend is restartable mid-project; user never wants to lose history because the GPU box rebooted |
| Active call in-memory state (current LLM stream, TTS cancel handles, transcript buffer) | **AI backend** | Dies with the call; nothing to persist |
| Endpoint config (where AI backend and LLM live) | **Web UI host** (served to browser at bootstrap) | Browser is a thin client; we don't want users editing JSON in localStorage |
| Voice reference audio files | **Web UI host filesystem** | AI backend streams them over HTTP at call setup; stateless GPU box |

---

## Architectural Patterns

### Pattern 1: WebRTC peer-to-peer (no SFU), browser ↔ AI backend

**What:** Browser opens one RTCPeerConnection directly to the AI backend. The Web UI host mediates signaling (offer/answer exchange over HTTPS) but never carries media. No SFU, no TURN on LAN, optionally no STUN.

**Why:**
- Two peers only (browser + AI backend) -> SFU is overhead with zero benefit.
- On a LAN both peers reach each other directly; ICE will find host candidates without STUN most of the time.
- WebRTC gives us SRTP, Opus encoding, jitter buffer, AEC/AGC/NS, and bandwidth adaptation for free — all of which we would otherwise have to reimplement badly over WebSockets.

**Trade-offs:**
- (+) Native mobile Safari support, native echo cancellation, automatic Opus, adaptive buffering.
- (+) Simpler than raw WS + PCM once you accept the signaling step.
- (-) Signaling and ICE feel ceremonious for a LAN app, but can be reduced to two HTTP POSTs (`/call/offer`, `/call/answer`).
- (-) Adds `aiortc` as a heavier Python dep than `websockets`.

**Sketch of call setup:**

```
1. User taps "Call" in browser
2. Browser: POST /api/call/start to Web UI host
   -> returns { aiBackendUrl, callId }
3. Browser: getUserMedia({ audio: { echoCancellation, noiseSuppression, autoGainControl } })
4. Browser: new RTCPeerConnection, add mic track, create data channel "control"
5. Browser: createOffer -> POST {offer} to aiBackendUrl/call/{callId}/offer
6. AI backend: aiortc accepts, attaches mic sink + synth source, createAnswer -> returns {answer}
7. Browser: setRemoteDescription(answer). ICE host candidates exchanged.
8. Connected. Orchestrator state = IDLE_LISTENING.
```

### Pattern 2: Server-side VAD + barge-in (not browser-side VAD)

**What:** The same mic PCM stream the AI backend is transcribing is also run through Silero VAD continuously. When VAD fires during TTS playback, the orchestrator cancels in-flight TTS and LLM and sends `stop_playback` on the data channel.

**Why not browser-side VAD?**
- Two VADs (one in browser, one on server) disagree in corner cases and produce race conditions — "did the user actually interrupt?"
- Moving VAD to the browser adds JS ONNX runtime weight and does not actually reduce latency materially: the mic frames already arrive at the server within ~20 ms on LAN.
- Keeping all turn-taking logic on the server means the state machine is authoritative.

**Trade-offs:**
- (-) If the user says "uhm" mid-sentence, the server may falsely fire barge-in. Mitigate with a minimum speech-duration threshold (e.g. 200 ms of voiced frames) before declaring interruption.
- (+) One source of truth for "who is talking."

### Pattern 3: Sentence-chunked streaming TTS

**What:** LLM token stream -> buffer -> sentence boundary detector -> send sentence to TTS -> TTS emits Opus frames that the RTCPeerConnection forwards to the browser. The first sentence is spoken while sentences 2..N are still being generated.

**Why:** Time-to-first-audio is the primary perceived-latency metric for call feel. Waiting for a full LLM response is a hard no.

**Boundaries considered:** `.` `!` `?` `;` `:` `\n`, plus soft flush on comma after 60+ chars to avoid "sentence too long" latency spikes.

**Trade-offs:**
- (-) Prosody is worse than whole-response TTS — synthesized sentences don't know what comes next.
- (+) Latency collapses from seconds to <300-500 ms TTFA on the 3060 once pipeline is warm.

### Pattern 4: Stateless AI backend, durable UI host

**What:** Every call writes its turns (user STT + AI response text, plus pointers to saved audio) back to the Web UI host over HTTPS. The AI backend holds no long-lived data. Restarting it terminates the active call but loses nothing persistent.

**Why:** The GPU box is the most likely service to crash or need a restart (driver issues, OOM, model reloads). If chat history lived on it, every blip would feel like data loss.

---

## Duplex Voice Loop — State Machine

### States

```
        ┌─────────────────────┐
        │     IDLE_LISTENING  │<──────────────────┐
        │ (VAD gate open,     │                   │
        │  STT streaming off) │                   │
        └──────────┬──────────┘                   │
                   │ VAD: speech_start            │
                   v                              │
        ┌─────────────────────┐                   │
        │       USER_SPEAKING │                   │
        │ (STT streaming on,  │                   │
        │  partial transcript │                   │
        │  -> data channel)   │                   │
        └──────────┬──────────┘                   │
                   │ VAD: speech_end (>X ms silence)
                   v                              │
        ┌─────────────────────┐                   │
        │  LLM_GENERATING     │                   │
        │ (final transcript,  │                   │
        │  LLM stream open,   │                   │
        │  sentence buffer)   │───── sentence ───┐│
        └──────────┬──────────┘                   │
                   │ first sentence ready         │
                   v                              │
        ┌─────────────────────┐                   │
        │    AI_SPEAKING      │<── next sentence ─┘
        │ (TTS -> Opus -> RTC │
        │  track, VAD still   │
        │  monitoring mic)    │
        └──────────┬──────────┘
                   │ LLM done + TTS queue drained
                   │
                   │ OR
                   │
                   │ VAD: speech_start (barge-in)
                   │   └─> fire CANCEL(all_inflight)
                   └────────> USER_SPEAKING
```

### Cancellation semantics (barge-in)

When VAD detects speech while state is `AI_SPEAKING`:

1. Orchestrator issues `cancel_token.set()`.
2. **LLM task:** async iterator on the httpx streaming response is broken; the HTTP stream is closed so the server stops generating.
3. **TTS task:** the current synthesis future is cancelled; any queued sentences are dropped; the outbound audio track stops enqueueing frames.
4. **Data channel:** `{"type": "playback_stop"}` is sent. Browser calls `audioElement.pause()` or lets the track drain its jitter buffer (~40-120 ms).
5. Orchestrator transitions to `USER_SPEAKING`; the barge-in phrase becomes the next user turn (or is discarded if it was just "mm" and fails the duration threshold).

Each cancellable unit owns an `asyncio.CancelledError`-aware task. The orchestrator holds a `dict[TaskName, asyncio.Task]` and cancels them in LIFO order (TTS first so audio stops immediately, LLM second so the model is freed).

### Per-call in-memory state

```python
@dataclass
class CallState:
    call_id: str
    character_id: str
    voice_id: str
    chat_id: str
    sliding_window_messages: list[ChatMessage]   # hydrated at start from UI host
    fsm_state: Literal["IDLE","USER","LLM","AI"]
    current_stt_buffer: str
    current_llm_task: asyncio.Task | None
    current_tts_task: asyncio.Task | None
    current_tts_cancel: asyncio.Event
    inflight_sentences: asyncio.Queue[str]
    recorded_ai_audio: io.BytesIO | None   # if save toggle on
    recorded_user_audio: io.BytesIO | None # if save toggle on
```

---

## AI Backend Internal Architecture

### Process model

**Recommended:** one Python process, asyncio everywhere, all models in-process.

Rationale:
- Only one call at a time (single user). No need to process-isolate for concurrency.
- Subprocess-per-model pays the cost of IPC, shared-memory buffers, and coordinated shutdown with zero upside here.
- Hot paths (Silero VAD, faster-whisper streaming, TTS) release the GIL during inference because they all call into C/CUDA extensions.

**Exception:** If F5 and XTTS turn out to genuinely conflict (e.g. different torch versions, CUDA init conflicts), isolate them into two workers managed by the orchestrator over a local Unix socket / asyncio subprocess. This is a contingency, not a default.

### VRAM budget on RTX 3060 (12 GB)

Measured/reported footprints in FP16, model weights only (add ~1-2 GB for activations + CUDA context):

| Model | Approx VRAM |
|-------|-------------|
| `faster-whisper large-v3-turbo` INT8 | ~1.5-2 GB |
| `faster-whisper large-v3` FP16 | ~3 GB |
| Silero VAD | CPU-only (negligible; <50 MB if GPU) |
| F5-TTS | ~6-8 GB in inference |
| XTTS v2 | ~3-4 GB in inference (reports of 6 GB peak) |
| CUDA context, torch, activations | ~1-2 GB |

**Total if F5 + large-v3 both loaded:** ~10-13 GB. Close to the ceiling; one OOM away from a crash.
**Total if XTTS + large-v3-turbo INT8 both loaded:** ~6-8 GB. Comfortable.

### Recommendation: one hot TTS engine at a time

- Load `faster-whisper large-v3-turbo` INT8 at startup. Keep hot.
- Load **exactly one** of F5 or XTTS at startup based on the active voice's engine.
- When a call starts with a voice on the other engine:
  - Start TTS swap: `del old_tts; gc.collect(); torch.cuda.empty_cache()` then load new engine.
  - Expect 2-8 s cold-load. Show "Switching voice..." in UI.
- Cache the *last used* engine across calls so repeated calls with the same voice incur zero swap cost.
- If users frequently alternate engines, reconsider (see "Decisions likely to need revisiting").

**STT choice:** `large-v3-turbo` first. If Spanish-accented English accuracy is poor, fall back to `large-v3` FP16 — which is the strongest Whisper variant for accented speech but costs ~1 GB more and ~2x latency.

### Framework: custom vs Pipecat

| Factor | Custom orchestrator | Pipecat |
|--------|---------------------|---------|
| Barge-in semantics | We define exactly what we want | Built-in but opinionated; overriding can be awkward |
| F5-TTS support | Call F5 Python API directly | Needs a Pipecat service adapter (may or may not exist) |
| Footprint | 200-500 lines | Framework + its own abstractions |
| Learning curve | None (our own code) | Pipecat's frame/pipeline mental model |
| Upgrade path | We own all of it | We inherit framework-level improvements |

**Recommendation:** Start custom. Pipecat is genuinely good, but its abstractions (`Frame`, `FrameProcessor`, `Pipeline`) are best when the pipeline shape itself varies — multiple stacks, many service backends. RayMe has one fixed shape (VAD -> STT -> LLM -> TTS) with one user. The custom orchestrator will be ~1 file.

If later we need: multi-stack experimentation, voice agents with tools, function calling over voice, or swappable providers — port to Pipecat.

---

## Recommended Project Structure

Three repositories (or three top-level folders in a monorepo):

```
rayme/
├── web-ui/                              # Browser SPA + API host
│   ├── client/                          # SPA (Vite + React, for example)
│   │   ├── src/
│   │   │   ├── pages/
│   │   │   │   ├── Home.tsx
│   │   │   │   ├── VoiceLab.tsx
│   │   │   │   ├── CharacterGallery.tsx
│   │   │   │   ├── CharacterEditor.tsx
│   │   │   │   ├── VoiceCall.tsx        # owns RTCPeerConnection
│   │   │   │   └── Settings.tsx
│   │   │   ├── call/                    # WebRTC client logic
│   │   │   │   ├── peer.ts              # RTCPeerConnection setup
│   │   │   │   ├── signaling.ts         # offer/answer over HTTPS
│   │   │   │   └── captions.ts          # data channel handlers
│   │   │   └── design/                  # Ethereal Core / True Dark tokens
│   │   └── index.html
│   ├── server/                          # FastAPI app
│   │   ├── api/
│   │   │   ├── chats.py                 # GET/POST threads + turns
│   │   │   ├── characters.py            # v2/v3 card import/export
│   │   │   ├── voices.py                # metadata + reference audio
│   │   │   ├── audio_blobs.py           # saved call audio
│   │   │   ├── settings.py              # bootstrap config for browser
│   │   │   └── call_writeback.py        # AI backend posts turns here
│   │   ├── storage/
│   │   │   ├── db.py                    # SQLite via aiosqlite
│   │   │   ├── blobs.py                 # filesystem blob store
│   │   │   └── schema.sql
│   │   └── main.py                      # TLS setup, static SPA, mounts
│   └── data/                            # gitignored
│       ├── rayme.sqlite
│       └── blobs/
│           ├── voices/<voice_id>/reference.wav
│           └── calls/<chat_id>/<turn_id>-{ai|user}.opus
│
├── ai-backend/                          # Python asyncio, GPU
│   ├── rayme_ai/
│   │   ├── rtc/
│   │   │   ├── endpoint.py              # aiortc peer setup
│   │   │   ├── audio_in.py              # Opus -> PCM frames -> VAD + STT
│   │   │   └── audio_out.py             # TTS frames -> Opus track
│   │   ├── orchestrator/
│   │   │   ├── fsm.py                   # CallState + state transitions
│   │   │   ├── cancellation.py          # task registry + LIFO cancel
│   │   │   └── sentence_chunker.py      # streaming LLM text -> sentences
│   │   ├── models/
│   │   │   ├── vad_silero.py
│   │   │   ├── stt_faster_whisper.py
│   │   │   ├── tts_f5.py
│   │   │   ├── tts_xtts.py
│   │   │   └── tts_registry.py          # hot-swap logic
│   │   ├── llm/
│   │   │   └── openai_client.py         # streaming httpx client + cancel
│   │   ├── writeback/
│   │   │   └── ui_host.py               # POST turn to web-ui host
│   │   └── main.py                      # FastAPI serving signaling + RTC
│   └── config.yaml                      # LLM endpoint, UI host URL, voice dir
│
└── llm/                                 # external
    └── (llama-server or OpenAI; nothing to ship)
```

### Structure Rationale

- **web-ui/client vs web-ui/server** split keeps the SPA and its API together so a single deploy unit serves both. Simpler than three services; the split is logical, not physical.
- **ai-backend/rtc vs orchestrator vs models** enforces the layering: RTC never touches model code directly; orchestrator is the only thing that knows the state machine.
- **models/tts_registry.py** is where the F5 ↔ XTTS swap logic lives. Makes the swap decision a single testable surface.
- **writeback/ui_host.py** is the only outbound HTTP the AI backend makes (besides to the LLM). Easy to mock in tests.

---

## Data Flow

### Live call — happy path

```
[User voice]
     │
     │ mic capture (browser, AEC/AGC/NS applied by WebRTC)
     v
[Opus over SRTP]
     │
     │ RTCPeerConnection -> aiortc
     v
[AI backend: Opus decoder -> 16 kHz PCM frames (20 ms)]
     │
     ├───────────────────────────────────┐
     v                                    v
[Silero VAD]                         [faster-whisper streaming]
     │                                    │
     │ speech_start/end events            │ partial + final transcripts
     v                                    │
[Orchestrator FSM]  <────────────────────┘
     │
     │ on final transcript (USER->LLM)
     v
[LLM: httpx stream to OpenAI-compat endpoint with sliding-window]
     │
     │ text deltas
     v
[Sentence chunker]
     │
     │ one sentence at a time
     v
[TTS (F5 or XTTS)]
     │
     │ PCM frames
     v
[aiortc: PCM -> Opus -> outbound RTP track]
     │
     v
[Browser: <audio> element / track auto-play]

         ALSO (data channel, bidirectional):
         - server -> browser: partial STT captions, AI text tokens,
                               playback_stop, state changes
         - browser -> server: mute, hangup, push-to-talk overrides
```

### Barge-in

```
state = AI_SPEAKING
     │
     v
VAD fires speech_start  (voiced frames > 200 ms)
     │
     v
Orchestrator.cancel():
     1. TTS cancel event set      -> stops enqueueing Opus frames
     2. LLM httpx stream closed   -> server stops generating tokens
     3. DC send "playback_stop"   -> browser flushes any jitter buffer
     4. STT buffer reset, fsm=USER_SPEAKING
     v
STT resumes with the new user utterance.
When VAD signals speech_end, new LLM call begins with updated history.
```

### Post-call writeback

```
Call ends (hangup or silence timeout)
     │
     v
AI backend POSTs to web-ui host:
     POST /api/chats/{chat_id}/turns  (array of alternating user/ai turns,
                                        each with text + optional audio blob URL)
     PUT  /api/blobs/calls/{chat_id}/{turn_id}-ai.opus   (if ai save on)
     PUT  /api/blobs/calls/{chat_id}/{turn_id}-user.opus (if user save on)
     │
     v
Web UI host writes SQLite row + files.
     │
     v
Browser refreshes thread view.
```

### Text chat (no call)

```
Browser -> Web UI host /api/chats/{id}/send
     │
     │ Web UI host loads char card + sliding window
     v
Web UI host -> LLM (streaming)
     │
     │ SSE or WS back to browser with deltas
     v
Browser renders.
Web UI host writes the turn to SQLite on finish.
```

Note: for **text** chat, the Web UI host talks to the LLM directly. For **voice** chat, the AI backend talks to the LLM. Both use the same OpenAI-compatible contract.

---

## Data Model

### SQLite schema (sketch)

```sql
-- Characters (SillyTavern v2/v3 card fields)
CREATE TABLE characters (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  personality TEXT,
  scenario TEXT,
  first_mes TEXT,
  mes_example TEXT,
  system_prompt TEXT,
  post_history_instructions TEXT,
  creator_notes TEXT,
  tags_json TEXT,                 -- JSON array
  alternate_greetings_json TEXT,  -- v3
  character_book_json TEXT,       -- v3
  extensions_json TEXT,           -- passthrough
  avatar_blob_path TEXT,
  default_voice_id TEXT REFERENCES voices(id),
  spec_version TEXT,              -- "v2" or "v3"
  created_at INTEGER,
  updated_at INTEGER
);

-- Voices
CREATE TABLE voices (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  engine TEXT CHECK (engine IN ('f5','xtts')) NOT NULL,
  reference_audio_blob_path TEXT NOT NULL,
  reference_transcript TEXT NOT NULL,      -- required by F5, useful for XTTS too
  params_json TEXT,                        -- engine-specific knobs
  created_at INTEGER
);

-- Chat threads: a character can have many threads
CREATE TABLE chats (
  id TEXT PRIMARY KEY,
  character_id TEXT REFERENCES characters(id),
  voice_override_id TEXT REFERENCES voices(id),  -- NULL = use character default
  title TEXT,
  created_at INTEGER,
  updated_at INTEGER
);

-- Turns: text and call transcript turns interleaved per chat
CREATE TABLE turns (
  id TEXT PRIMARY KEY,
  chat_id TEXT REFERENCES chats(id),
  idx INTEGER NOT NULL,                 -- order within chat
  source TEXT CHECK (source IN ('text','call')) NOT NULL,
  role TEXT CHECK (role IN ('user','assistant','system')) NOT NULL,
  content TEXT NOT NULL,
  audio_blob_path TEXT,                 -- NULL for text turns; set for call turns w/ audio saved
  call_id TEXT,                         -- groups turns that belong to the same call session
  created_at INTEGER,
  UNIQUE (chat_id, idx)
);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- settings rows include:
--   ai_backend_url        e.g. https://gpubox.local:8443
--   llm_endpoint_url      e.g. http://llmbox.local:8000/v1
--   llm_api_key           (may be empty for local)
--   llm_model             e.g. "qwen3-8b-instruct"
--   save_ai_audio         "true" | "false"
--   save_user_audio       "true" | "false"
```

### Blob layout

```
data/blobs/
├── characters/<character_id>/avatar.png
├── voices/<voice_id>/reference.wav
└── calls/<chat_id>/<turn_id>-ai.opus
    calls/<chat_id>/<turn_id>-user.opus
```

Rationale: filesystem is simpler than BLOB columns for audio — easy to serve with `StaticFiles`, easy to delete in bulk, easy to back up.

### Sliding-window assembly

Done on the AI backend at call start (so the backend can keep the full context hot in memory without re-fetching per turn):

1. Call begins -> AI backend requests `GET /api/chats/{id}?window=N` (N ~ 20 turns by default).
2. Web UI host returns: character system prompt + character card summary + last N interleaved turns (both text and call transcripts, since they're one thread).
3. AI backend holds this in `CallState.sliding_window_messages` and appends as the call progresses.
4. On each new user turn: build messages = `[system] + window + [user: stt_final]`, send to LLM with streaming=true.

---

## Service Boundaries

| Edge | Protocol | Direction | Purpose |
|------|----------|-----------|---------|
| Browser ↔ Web UI host | HTTPS (REST), WSS (optional for text-chat SSE) | both | Load SPA, durable-state CRUD, bootstrap config, text chat streaming |
| Browser ↔ AI backend | WebRTC (SRTP + DTLS + DataChannel), HTTPS for signaling | both | Full-duplex audio + live captions + control |
| Web UI host ↔ AI backend | HTTPS (REST) | Web UI host gets hit by AI backend's writebacks; AI backend pulls character + voice + window at call start | Per-call history hydration, turn writeback, blob upload |
| AI backend ↔ LLM | HTTPS (OpenAI Chat Completions streaming) | AI backend -> LLM | Live LLM calls during voice turns |
| Web UI host ↔ LLM | HTTPS (OpenAI Chat Completions streaming) | Web UI host -> LLM | Text-chat turns when no call is active |

### What does *not* happen

- Browser never talks directly to the LLM. Keeps the LLM API key (if any) server-side.
- AI backend does not read SQLite directly. Keeps one source of truth.
- Web UI host never carries media. Its job ends at signaling.

### Independent restart guarantees

- **AI backend restart:** kills any active call; all persistent data intact. On reconnect, browser can resume chat thread and start a new call.
- **Web UI host restart:** kills browser session but SPA reconnects on refresh; active call technically survives the WebRTC channel (since it's peer-to-peer with AI backend), but call writebacks will queue/fail during the outage. Simplest: end call when Web UI host is unreachable.
- **LLM restart:** active turn fails; orchestrator surfaces an error caption and returns to IDLE_LISTENING.

---

## Configuration & Discovery

### Endpoint bootstrap

1. User visits `https://rayme.local/` (the Web UI host).
2. Browser loads SPA. SPA calls `GET /api/config`.
3. Response includes: `{ aiBackendUrl, aiBackendPort, turnServerUrl (null for LAN), llmHealthy: true/false }`.
4. SPA uses `aiBackendUrl` as the signaling endpoint for `POST /call/offer`.

Endpoints are editable on the Settings screen; changes persist to the `settings` table and the SPA re-fetches config.

### HTTPS on LAN — the iOS blocker

iOS Safari **will not grant `getUserMedia()` without a secure context**. "Secure context" = HTTPS or `localhost`. Neither the Web UI host nor the AI backend is localhost from a phone's perspective.

**Plan:**

1. Use **mkcert** to generate a local root CA + leaf certs for `rayme.local` and `gpubox.local` (or whatever hostnames the user picks via mDNS / `.local`).
2. Install the mkcert root CA as a trusted profile on each iOS device (AirDrop / email / serve from HTTP -> Settings > General > VPN & Device Management > Install Profile > then enable full trust in Certificate Trust Settings).
3. Web UI host serves HTTPS with the mkcert leaf.
4. AI backend also serves HTTPS with the mkcert leaf (WebRTC requires HTTPS context on the signaling origin; media itself is DTLS-SRTP regardless).
5. Document this as a one-time setup in README.

Alternatives considered:
- **Tailscale / Cloudflare Tunnel:** both can issue real certs for `.ts.net` or a custom domain. Good fallback if the mkcert install is too painful. Costs: a third-party dependency in a "your hardware" product.
- **Self-signed without root CA install:** iOS Safari will refuse. Non-starter.
- **HTTP-only on desktop + "just don't use phone":** breaks the product's core promise of phone + desktop.

### getUserMedia parameters

Browser-side constraints to request:

```js
navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: { ideal: true },
    noiseSuppression: { ideal: true },
    autoGainControl:  { ideal: true },
    channelCount:     { ideal: 1 },
    sampleRate:       { ideal: 48000 },  // WebRTC Opus native
  },
  video: false,
});
```

Plus `<audio playsinline autoplay />` for iOS to play inbound media without a user gesture **while the PC is already capturing** (which it is during a call).

---

## Scaling Considerations

This is a single-user LAN app. Scaling is not the concern — survivability on one box, per-call latency, and restartability are.

| Scale | Adjustments |
|-------|-------------|
| 1 user, 1 call | Current architecture |
| 1 user, multiple concurrent calls | Out of scope (single user) |
| Multi-user, if it ever happens | Auth on Web UI host; AI backend gets call-id scoping (already true); LLM quotas; per-user blob namespacing. Would require re-planning. |

### What will break first

1. **VRAM ceiling on 3060** when user tries F5 + large-v3 FP16 simultaneously. Solution: force large-v3-turbo INT8 or force XTTS; show a clear error.
2. **LLM latency** if the local `llama-server` runs a model too big for the LLM box. Not RayMe's problem architecturally, but surface it in UI as "LLM responding slowly..."
3. **iOS Safari audio autoplay** if the user backgrounds the tab during a call — iOS may suspend the media. Handle with visible "call paused" state and reconnect on foreground.

---

## Anti-Patterns

### Anti-Pattern 1: Raw WebSocket + PCM16 for call audio

**What people do:** Send binary WS frames of 20ms PCM16 chunks both ways.
**Why it's wrong:**
- No AEC/AGC/NS in browser -> user hears themselves + TTS, and server hears its own TTS leaking from speakers (feedback loop).
- TCP head-of-line blocking: one dropped packet stalls the stream.
- No jitter buffer -> audible glitches on WiFi.
- Twice the work we have to maintain.
**Do this instead:** WebRTC. The browser does the hard parts for free.

### Anti-Pattern 2: Browser-side VAD as the source of barge-in truth

**What people do:** Run Silero VAD in JS, send "user is speaking" events over WS; server reacts.
**Why it's wrong:**
- Two VADs (server's STT gating + browser's barge-in) will disagree.
- Adds ~50 ms network RTT to barge-in detection for no accuracy gain.
- Requires shipping an ONNX VAD model to every device.
**Do this instead:** One VAD, server-side, running on the already-decoded mic PCM.

### Anti-Pattern 3: AI backend owns chat history

**What people do:** SQLite on the GPU box, because "that's where the LLM conversation happens."
**Why it's wrong:** GPU box is the most likely to crash / restart / run out of VRAM. Losing a chat thread because CUDA OOM'd is absurd.
**Do this instead:** Web UI host owns durable state. AI backend is a stateless worker.

### Anti-Pattern 4: Loading both TTS engines eagerly at startup

**What people do:** Warm both F5 and XTTS in GPU memory so engine switching is instant.
**Why it's wrong:** 14-16 GB demanded on a 12 GB card -> OOM on first call.
**Do this instead:** One hot engine, swap on voice change, show UI feedback during swap.

### Anti-Pattern 5: Full-response TTS (wait for LLM to finish)

**What people do:** Collect the entire LLM response, then synthesize, then play.
**Why it's wrong:** Adds the full LLM generation time to perceived response latency. Kills call feel.
**Do this instead:** Sentence-chunked streaming, play sentence 1 while generating sentence 2+.

### Anti-Pattern 6: Assuming `localhost` HTTPS exemption applies on mobile

**What people do:** Trust browser docs that say "secure context = HTTPS or localhost" and then try to use `http://192.168.x.x` from a phone.
**Why it's wrong:** `localhost` exemption means 127.0.0.1 / ::1 on the device itself. LAN IPs are not localhost.
**Do this instead:** mkcert + installed root CA on every device that will place calls.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenAI API (optional) | Streaming Chat Completions over HTTPS | httpx async client with `stream=True`; cancel by closing the stream |
| `llama-server` (local) | Same OpenAI-compatible contract | Document that the server must be started with `--api` or equivalent; health-check via `/v1/models` |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| RTC endpoint ↔ orchestrator | In-process asyncio queues (audio-in frames, control events) | Single-process, no IPC |
| Orchestrator ↔ models | Direct Python calls, each model encapsulated behind an async interface | Model code hidden from FSM |
| AI backend ↔ Web UI host (writeback) | HTTPS REST with retries and a small queue for during-outage buffering | If writeback fails, retain in-memory until user hangs up; show a soft warning |
| Web UI host ↔ LLM | httpx async streaming | Same adapter used by AI backend — share a tiny module |

---

## Build Order & Critical Path

This is the order that produces the earliest credible "first working call" end-to-end, with parallelizable work called out.

### Phase 0 — Foundations (parallelizable)

- A1: Repo layout + TLS/mkcert docs + three runnable stubs (Web UI host, AI backend, LLM box or OpenAI API key) that each answer a `/health` endpoint.
- A2: Design-system tokens and shell layout for the SPA (follow `docs/stitch/`). Home screen navigation only.
- A3: SQLite schema + migrations on Web UI host. Characters and Voices CRUD (minimum viable).

### Phase 1 — Text chat end-to-end (no voice yet)

- B1: Character importer (v2 + v3 JSON + PNG tEXt parsing).
- B2: Chat threads API + turns table + text chat UI.
- B3: Web UI host ↔ LLM streaming (shared adapter).
- **Milestone:** typed conversation with an imported character works. This validates the LLM integration and sliding-window assembly before we add voice.

### Phase 2 — Voice call MVP (half pipeline)

- C1: Voice entity + Voice Lab upload + reference-transcript generation (requires STT already loaded on AI backend).
- C2: AI backend: faster-whisper loaded, Silero VAD loaded, `/call/{id}/offer` aiortc signaling endpoint.
- C3: Web UI host: bootstrap config endpoint, Settings screen for AI backend URL.
- C4: Browser: VoiceCall screen with RTCPeerConnection, mic capture, playback element, data channel wiring.
- C5: Orchestrator: FSM skeleton + USER_SPEAKING -> LLM_GENERATING -> plays back a single TTS sentence (no streaming, no barge-in yet).
- **Milestone: First working call.** User says something, hears a one-sentence reply, even if barge-in and streaming are crude.

### Phase 3 — Call feel (the load-bearing work)

- D1: Sentence-chunked streaming TTS; time-to-first-audio under 500 ms.
- D2: Barge-in cancellation — VAD-triggered LIFO cancel of TTS and LLM.
- D3: Live captions on the data channel (partial STT + AI text deltas) rendering in VoiceCall screen.
- D4: Call-turn writeback to Web UI host; chat thread now has interleaved text + call turns.

### Phase 4 — Voice breadth

- E1: Both TTS engines working (F5 + XTTS); cold-swap logic; UI feedback during swap.
- E2: Voice Lab edit + save polish; per-chat voice override.
- E3: Saved audio toggles (AI on by default, user off by default) wired through orchestrator, blobs, and playback UI.

### Phase 5 — Polish

- F1: Settings screen: endpoints, model selection, save toggles.
- F2: Character editor (full field set).
- F3: Accessibility + mobile Safari validation pass.
- F4: Error states: LLM down, AI backend down, VAD false-positive floor.

### Critical path (serial dependencies)

```
repo + TLS (A1)
    -> SQLite + char/voice CRUD (A3)
    -> char importer (B1)
    -> text chat working (B2+B3)
    -> AI backend RTC + models loaded (C1+C2)
    -> browser RTC wiring (C3+C4)
    -> first working call (C5)   ◄── MVP milestone
    -> streaming TTS + barge-in (D1+D2)
    -> captions (D3) + writeback (D4)   ◄── call-feel milestone
    -> 2nd TTS engine + swap (E1)   ◄── feature-complete MVP
```

Parallelizable at any point: design-system polish (A2), settings UX (F1), character editor depth (F2).

---

## Decisions Most Likely to Need Revisiting

### 1. Custom orchestrator vs Pipecat

**Current bet:** custom.
**Revisit when:** orchestration logic grows past ~800 lines, or when we want to add tool-using agents (explicitly out of scope now, but a plausible v2 item), or when a second person joins the project and needs a mental model on day one.
**How we'd switch:** Pipecat has a SmallWebRTCTransport and matching Silero VAD, Whisper STT, and XTTS service wrappers. F5 would need a custom service. Signal + FSM would be replaced by a Pipecat Pipeline.

### 2. F5 ↔ XTTS cold-swap vs pinning one engine

**Current bet:** swap on demand, cache last-used.
**Revisit when:** users (us) frequently switch between voices on different engines in the same session and the 2-8 s swap feels jarring.
**Options if it's bad:**
- Pin XTTS only in v1, treat F5 as v1.5 (XTTS is smaller, faster to load, and handles most voices adequately).
- Run F5 in a separate subprocess with its own CUDA context, accept the extra idle-VRAM cost, swap becomes "kill + respawn."
- Upgrade the GPU (explicitly not an option per constraints).

### 3. Server-side VAD only vs hybrid

**Current bet:** server-side only.
**Revisit when:** tuning the minimum-speech-duration threshold (to avoid barge-in triggering on "uhm") starts feeling fragile.
**Fallback:** add a cheap browser-side energy-based "the user might be talking" hint on the data channel that the server treats as a **confirmation** of its own VAD, not as the trigger.

### 4. SQLite only vs SQLite + lightweight queue

**Current bet:** SQLite only.
**Revisit when:** call writebacks regularly collide with user text-chat writes and SQLite's single-writer lock becomes visible (unlikely at one user, but possible on a reconnect flood after a crash).
**Fallback:** WAL mode already recommended; or split call turns to a separate SQLite file.

---

## Sources

### WebRTC vs WebSockets for voice AI

- [LiveKit — Why WebRTC beats WebSockets for realtime voice AI](https://livekit.com/blog/why-webrtc-beats-websockets-for-voice-ai-agents)
- [Switching my AI voice agent from WebSocket to WebRTC (DEV)](https://dev.to/aws-builders/switching-my-ai-voice-agent-from-websocket-to-webrtc-what-broke-and-what-i-learned-3dkn)
- [Stream — WebRTC vs WebSockets Audio/Video Sync](https://getstream.io/blog/webrtc-websocket-av-sync/)
- [Ant Media — WebRTC vs WebSockets 2026 Comparison](https://antmedia.io/webrtc-vs-websockets-what-are-the-differences/)

### Mobile Safari / getUserMedia / HTTPS

- [MDN — MediaDevices.getUserMedia()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [webrtcHacks — Guide to WebRTC with Safari in the Wild](https://webrtchacks.com/guide-to-safari-webrtc/)
- [webrtcHacks — Autoplay restrictions and WebRTC](https://webrtchacks.com/autoplay-restrictions-and-webrtc/)
- [WebKit bug 179411 — getUserMedia echoCancellation](https://bugs.webkit.org/show_bug.cgi?id=179411)
- [mkcert — locally trusted development certificates](https://github.com/FiloSottile/mkcert)
- [Self-signed SSL certificates on iOS (Jozef Cipa)](https://jozefcipa.com/blog/self-signed-ssl-certificates-on-ios/)

### Voice AI frameworks / orchestration / barge-in

- [Pipecat (GitHub)](https://github.com/pipecat-ai/pipecat)
- [Pipecat vs LiveKit — Cekura](https://www.cekura.ai/blogs/pipecat-vs-livekit-the-real-difference)
- [Sequential Pipeline Architecture for Voice Agents — LiveKit](https://livekit.com/blog/sequential-pipeline-architecture-voice-agents)
- [Voice AI pipeline: STT, LLM, TTS and the 300ms budget](https://www.channel.tel/blog/voice-ai-pipeline-stt-tts-latency-budget)
- [Real-Time vs Turn-Based Voice Agent Architecture — Softcery](https://softcery.com/lab/ai-voice-agents-real-time-vs-turn-based-tts-stt-architecture)
- [Toward Low-Latency End-to-End Voice Agents (arXiv 2508.04721)](https://arxiv.org/html/2508.04721v1)

### STT / VAD / TTS components

- [faster-whisper (SYSTRAN)](https://github.com/SYSTRAN/faster-whisper)
- [Choosing between Whisper variants — Modal](https://modal.com/blog/choosing-whisper-variants)
- [STT-faster-whisper (live streaming, 3060 12GB)](https://github.com/traegh/STT-faster-whisper)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [Silero VAD plugin — LiveKit docs](https://docs.livekit.io/agents/logic/turns/vad/)
- [F5-TTS — SWivid](https://github.com/SWivid/F5-TTS)
- [F5-TTS VRAM requirements (issue 197)](https://github.com/SWivid/F5-TTS/issues/197)
- [Coqui XTTS — Hugging Face](https://huggingface.co/coqui/XTTS-v2)
- [XTTS v2 VRAM discussion](https://github.com/coqui-ai/TTS/discussions/3268)

### Character cards

- [Character Card V2 spec](https://github.com/malfoyslastname/character-card-spec-v2)
- [Character Card V3 JSON Schema (gist)](https://gist.github.com/nossebro/a50dbc86368ae0d7fbe793ffd4509214)
- [SillyTavern Character Management (DeepWiki)](https://deepwiki.com/SillyTavern/SillyTavern/5.1-character-management)

### WebRTC / Python / signaling

- [aiortc](https://github.com/aiortc/aiortc)
- [MDN — WebRTC Signaling and video calling](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Signaling_and_video_calling)
- [WebRTC data channels](https://webrtc.org/getting-started/data-channels)

### Streaming TTS + LLM cancellation

- [Deepgram — Text chunking for streaming TTS](https://developers.deepgram.com/docs/text-chunking-for-tts-streaming-optimization)
- [Stopping the Stream: Controlling OpenAI Responses (DEV)](https://dev.to/biancassilva/stopping-the-stream-a-pythonic-guide-to-controlling-openai-responses-4gpb)
- [Interrupting completion stream in Python — OpenAI community](https://community.openai.com/t/interrupting-completion-stream-in-python/30628)
- [RealtimeTTS](https://github.com/KoljaB/RealtimeTTS)

### Storage

- [SQLite — Appropriate uses for SQLite](https://sqlite.org/whentouse.html)

---
*Architecture research for: RayMe self-hosted real-time voice AI*
*Researched: 2026-04-16*
