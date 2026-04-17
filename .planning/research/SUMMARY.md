# Project Research Summary — RayMe

**Project:** RayMe — self-hosted real-time AI voice-call app
**Domain:** Full-duplex voice AI (STT + LLM + TTS) with VAD barge-in, character-card characters, voice cloning, single-user LAN deployment
**Researched:** 2026-04-17
**Confidence:** HIGH on transport / STT / VAD / storage / character cards, MEDIUM on TTS VRAM + latency on the actual RTX 3060, MEDIUM on the AI-backend orchestration framework choice (resolved below).

## Executive Summary

RayMe is a three-service LAN app whose whole reason to exist is **call feel** — low-latency full-duplex audio with real VAD-driven barge-in, not a chatbot with TTS bolted on. The standard-of-care 2026 stack for this shape of product is converged across all four research threads: **WebRTC transport (aiortc) between the browser and a Python asyncio AI backend, Silero VAD server-side as the turn-taking authority, faster-whisper for STT, a streaming OpenAI-compatible LLM client, F5-TTS + XTTS v2 for voice cloning, SQLite + filesystem for persistence on the Web UI host, and SvelteKit for the client.** The Web UI host owns all durable state, the AI backend is stateless per call, and the LLM is reached through the same OpenAI Chat Completions streaming contract from both sides.

The recommended approach is to **build the orchestrator custom in ~1 file of Python asyncio for v1**, treat the Web UI host as durable state's source of truth, pin exactly one TTS engine to GPU per call, and ship HTTPS via mkcert + trusted root CA on every device from day one. The load-bearing engineering work is not any single model — it's the seven duplex concerns that compound: echo cancellation that survives a custom audio graph (Pitfall #1), HTTPS/cert trust on iOS (#2), AudioContext gesture unlock (#3), F5-TTS not streaming natively (#4), STT endpointing (#5), Whisper hallucinations on silence (#6), and mid-stream LLM cancellation that actually propagates to the GPU (#8). Every one of these is a "looks done but isn't" trap.

Key risks and mitigations: (1) **VRAM ceiling on 12 GB 3060** — force exactly one TTS engine resident, default STT to distil-large-v3 INT8, never eager-load both F5 and XTTS. (2) **F5-TTS non-native streaming** — split the LLM stream at sentence boundaries and dispatch one-sentence syntheses so time-to-first-audio is bounded by the *first* sentence, not the full reply. (3) **Echo loops on laptop speakers** — play TTS through `<audio>` / `MediaStreamAudioDestinationNode` so the browser's AEC can see it, and add a server-side playback gate against its own TTS timeline. (4) **Mobile Safari breakage** — commit to HTTPS-via-mkcert on day one, and keep iOS in the test loop every phase.

## Top-Line Stack

- **Audio transport:** WebRTC (aiortc on backend, `RTCPeerConnection` in browser). Brings Opus + AEC/AGC/NS + jitter buffer + adaptive bandwidth for free; WebSocket is fallback only for locked-down iOS in-app webviews.
- **STT:** `faster-whisper` with `distil-large-v3` INT8 as the default, `large-v3-turbo` INT8 as the first upgrade path, `large-v3` FP16 as the last resort. All three fit the 12 GB budget with one TTS engine resident.
- **VAD:** Silero VAD v5, server-side, ONNX, CPU-runnable. Authoritative for turn-taking and barge-in. (Optional in-browser Silero via `@ricky0123/vad-web` later, purely as a local UI hint — *not* as the barge-in trigger.)
- **TTS engines:** F5-TTS (`f5-tts` 1.1.x) and Coqui XTTS v2 via the **idiap fork** (`pip install coqui-tts`, NOT `TTS`). Exactly one engine resident on GPU at a time; cold-swap between calls, never mid-call.
- **LLM client:** Official `openai` Python SDK in async streaming mode, configurable `base_url`. Works against OpenAI, `llama-server`, Ollama, vLLM, LM Studio. No tool calling in v1. Must propagate cancellation all the way to the backend.
- **AI backend framework:** **Custom Python asyncio orchestrator on FastAPI + aiortc.** Pipecat is a revisit trigger, not a v1 dependency. (See Resolved Tensions #1.)
- **Web UI:** SvelteKit 2 / Svelte 5 with Vite, `adapter-static`. Compiler-based, tiny mobile bundle, trivial to ingest the Stitch HTML exports as page scaffolds.
- **Storage:** SQLite via `aiosqlite` + SQLAlchemy 2.x async on the Web UI host. Binary assets (voice reference WAVs, saved call audio, character avatars) as files on disk keyed by UUID. WAL mode, atomic temp-rename on write, startup orphan reaper.
- **Character cards:** Pillow + ~40 lines of custom PNG tEXt chunk walker. Parse `ccv3` first, fall back to `chara`. Up-convert v2 to a single internal v3-shaped Pydantic model.
- **HTTPS on LAN:** mkcert local root CA installed on every device. Tailscale tailnet cert is a documented fallback. Non-negotiable; do not ship on plain HTTP even in dev.

## Resolved Tensions

### Tension 1 — AI backend framework: **Custom asyncio orchestrator** (agrees with ARCHITECTURE.md and PITFALLS.md; overrides STACK.md)

**The pick:** Build a single-file Python asyncio orchestrator directly on top of FastAPI + aiortc + the individual model libraries. Do NOT adopt Pipecat for v1.

**Rationale:**
- RayMe's pipeline has **one fixed shape** (VAD → STT → LLM → TTS) for **one user** on a **LAN with no SFU, no TURN, no telephony integration, no tool-using agents, no function calling**. Pipecat's abstractions (`Frame`, `FrameProcessor`, `Pipeline`) exist for pipelines whose *shape* varies — multi-provider, multi-stack, cloud-orchestrated voice agents. Adopting it here pays framework tax for portability the product does not need.
- The load-bearing decisions in RayMe are subtle duplex semantics: the echo-loop gate, the minimum-duration barge-in threshold, the perceived-playback-end clock (Pitfalls #1, #10, #11). These are exactly the behaviors that are awkward to override inside Pipecat and trivial to implement directly. Owning the state machine is the point.
- Pipecat ships XTTS support but not F5-TTS. We would write a custom `F5TTSService` subclass anyway — half the custom-orchestrator work with none of the control.
- ARCHITECTURE.md estimates ~200–500 lines for the full orchestrator. That number is credible given what's in PITFALLS.md — the logic is gnarly but not large.
- STACK.md's Pipecat recommendation is defensible on "don't hand-roll what's been productized" grounds and would be correct for a LiveKit-style SaaS voice agent. For a LAN-only single-user app where barge-in semantics are the product, custom wins.

**Revisit triggers (flip to Pipecat when any lands):**
1. Orchestrator grows past ~800 lines.
2. A second developer joins and needs an ecosystem mental model on day one.
3. Scope expands to tool-using agent characters, function calling over voice, or runtime-swappable provider stacks.
4. Multi-user or cloud deployment becomes a goal.
5. A framework-level feature (new turn-taking model, better endpointing detector) lands in Pipecat and we want it for free.

**Implication for the stack list:** Drop `pipecat-ai` and `pipecat-ai-small-webrtc-prebuilt` from the install command. Keep `aiortc`, `fastapi`, `uvicorn`, `faster-whisper`, Silero VAD (ONNX), `f5-tts`, `coqui-tts`, `openai`, `sqlalchemy` + `aiosqlite`, `pillow`.

### Tension 2 — Whisper variant pick: **distil-large-v3 INT8 as the ship default, with a measured upgrade path**

**The pick:** Ship with **faster-whisper `distil-large-v3` INT8** as the default. Keep `large-v3-turbo` INT8 and `large-v3` FP16 as runtime-selectable upgrade rungs. Make a Spanish-accented-English WER measurement on the builder's own voice the **Phase 0 gate** that decides which rung is the default before freezing it.

**Rationale:**
- All three variants fit the VRAM budget alongside one TTS engine. This is a quality/latency call, not a feasibility call.
- distil-large-v3 was specifically designed for streaming with faster-whisper's chunking algorithm — lowest-friction streaming path, ~1.1–1.5 GB peak working set, ~6× faster than FP16 large-v3.
- large-v3-turbo INT8 is a middle rung: slightly more VRAM, slightly slower, slightly better on hard audio.
- large-v3 FP16 is the strongest accented-English performer but costs ~1 GB more and ~2× latency — only justifiable if distil is measurably worse on the builder's own voice.
- PITFALLS.md and FEATURES.md both flag Spanish-accented-English WER as the literal quality bar. Measure, don't guess.

**Revisit triggers:**
1. Distil WER on a 10-minute accented-English eval is >2 pp worse than turbo → promote turbo to default.
2. Turbo is still >2 pp worse than large-v3 FP16 → promote FP16 and accept the ~1 GB VRAM cost (only XTTS fits alongside, not F5 — flip TTS default accordingly).
3. First-token STT latency with distil exceeds ~200 ms end-to-end at realistic speech rates → re-benchmark; may indicate config bug, not model.

### Tension 3 — F5-TTS hosting: **One TTS engine resident per call; sentence-chunk streaming for F5**

**The pick:** The "cold-swap with XTTS" design (STACK.md) and the "exactly one TTS engine resident" design (ARCHITECTURE.md) are the same design stated two ways — both agree a TTS swap is acceptable *between* calls, unacceptable *mid* call. Adopt as stated. For F5's lack of native streaming (PITFALLS.md #4), adopt **sentence-chunk streaming**: split the LLM token stream at sentence boundaries, dispatch each sentence to F5 as a short synthesis job, play the resulting audio segments back-to-back.

**Rationale:**
- VRAM math: F5 (~4–6 GB) + Whisper (~1.5 GB) + VAD + CUDA context = ~8 GB worst case. Fits. XTTS (~2.1–3.5 GB) + Whisper + overhead = ~4–5 GB. Comfortable. Both engines resident simultaneously blows the 12 GB ceiling under realistic activation load.
- Cold-swap cost is 2–8 s on first load; happens between calls, not during. Cache the last-used engine so repeated calls with the same voice incur zero swap.
- F5's full-utterance synthesis pattern collapses to acceptable latency once the LLM is chunked at sentence boundaries — first-sentence TTS determines perceived latency. Bias the system prompt to "begin every reply with a short acknowledgment" to compress the first chunk structurally.
- Locking the voice for the duration of a call (ARCHITECTURE.md ownership rule) prevents mid-call swap races.

**Revisit triggers:**
1. Measured F5 first-sentence synthesis on the actual 3060 at 7-step Sway sampling exceeds 400 ms for a 3–5 word sentence → pin XTTS as the v1 default; keep F5 as an opt-in for voices that sound substantially better on it.
2. Users (we) repeatedly alternate F5 and XTTS voices in a single session and the 2–8 s swap feels jarring → pin one engine for v1 or run F5 in a subprocess with its own CUDA context (accept idle VRAM cost).
3. F5-TTS upstream lands real streaming → collapse the per-sentence chunker for F5 and treat it like XTTS.

## Table Stakes vs Differentiators

### Table stakes (missing any makes v1 feel broken)
- Full-duplex call loop: mic → streaming STT with live user captions → streaming LLM with live AI captions → sentence-chunked streaming TTS → browser playback.
- VAD-driven barge-in that cancels in-flight TTS *and* the LLM stream.
- Call controls: start, end, mute, audio device pickers (input/output), permission handling, speaking-state visualizer with listening/thinking/speaking.
- Character CRUD: Gallery, Editor (SillyTavern v2 + v3 field set), portrait, per-character default voice.
- Character import: v2 JSON, v3 JSON, PNG-embedded (`chara` + `ccv3`). Sanitized rendering (no raw HTML).
- Voice Lab: upload sample → Whisper auto-transcribes → user edits → save voice with engine choice (F5 or XTTS) → test-play before assign.
- Unified thread: single messages table with `message_kind` discriminator so text and call turns interleave chronologically.
- Per-chat voice override on top of per-character default.
- Settings covering all three endpoints with connection tests, VAD sensitivity, device defaults, save-audio toggles, clear-data.
- Persistence: threads list, thread rename/delete, AI audio saved per-turn and replayable inline, mic audio toggle (off by default).
- LAN-accessible from mobile on iOS Safari + Android Chrome over HTTPS with a trusted cert.

### Differentiators (why RayMe vs SillyTavern + TTS ext or Character.ai)
- True full-duplex with VAD barge-in (not tap-to-interrupt, not turn-based push-to-talk).
- End-to-end turn latency tuned for call feel (<800 ms target, stretch <500 ms).
- Unified text+call thread — mode-agnostic continuity.
- Voice Lab auto-transcription for F5 — removes manual-transcript friction.
- SillyTavern v2 + v3 PNG-embedded card import — rides the existing ecosystem.
- Per-chat voice override — recast without duplicating the card.
- Bidirectional live captions — shows your own STT in real time.
- Ethereal Core / True Dark UI execution.
- Privacy-asymmetric defaults (AI audio saved, mic audio off).
- Zero-auth LAN-scoped access.

### Defer (v1.x, v2+)
- v3 PNG export (v1 ships v2 JSON export).
- Alternate-greeting picker, lorebook / world info, thread search, conversation branching, regenerate/edit turns.
- Call export as single mixed WAV (v1 ships per-turn replay).
- Multi-language STT/TTS, speech-to-speech models, RVC post-processing, emotion tags.
- Summarization-based long-term memory (v1 = sliding window).
- PWA install polish.
- Any form of auth, multi-user, group calls, agent/tool use, cloud deployment — all explicitly out of scope.

## Critical Pitfalls (the top seven that MUST shape the roadmap)

1. **#1 Echo loop (TTS re-enters mic → VAD → cancels self):** Play TTS through `<audio>` or `MediaStreamAudioDestinationNode` so the browser's AEC can reference it. Server-side playback gate keyed to the TTS sample-accurate timeline. Headphones recommended as fallback, not required. *Phase:* first duplex phase.
2. **#2 HTTPS / cert trust on mobile:** iOS Safari will not grant `getUserMedia` without a secure context *and* a trusted cert. Commit to mkcert + installed root CA (or Tailscale) on day zero. Precheck `window.isSecureContext` and fail loudly. *Phase:* Phase 0 / Web UI bootstrap.
3. **#3 AudioContext gesture unlock:** Create/resume the `AudioContext` synchronously inside the Start Call tap handler; play a 1-sample silent buffer as the canonical unlock idiom. Handle `statechange` → resume on foreground. *Phase:* Voice Call UI.
4. **#4 F5 not streaming natively:** Sentence-chunk the LLM stream; dispatch first sentence the moment its boundary is seen. Bias the system prompt toward short openers. Budget F5 first-sentence synthesis <300 ms. *Phase:* TTS integration.
5. **#5 / #10 / #11 Endpointing, false barge-in, TTS/user-turn race (one cluster):** Silero VAD for endpointing; minimum-duration gate (≥250–400 ms) before calling barge-in; word-count gate (STT must produce at least one confident word) for cancel; perceived-playback-end clock from the browser to suppress false barge-in during the jitter-buffer tail. Tune on accented speech. *Phase:* duplex / barge-in.
6. **#7 VRAM budget on 12 GB:** Default STT to distil-large-v3 INT8; exactly one TTS engine resident; lock engine for call duration; `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`; 30-minute stress test showing stable memory. *Phase:* AI backend, before TTS integration.
7. **#8 Mid-stream LLM cancellation doesn't reach the GPU:** Verify — don't assume — that closing the HTTPS stream aborts generation on the chosen LLM server. Use OpenAI SDK context-manager cancellation or httpx with explicit abort. Log wasted-token-count per barge-in. *Phase:* barge-in, paired with #5 cluster.

Secondary but phase-shaping: **#9** (F5 transcript errors → editable-transcript + synth-preview non-negotiable in Voice Lab), **#12** (Coqui abandonware → `coqui-tts` idiap fork, never `TTS`), **#14** (Card XSS → sanitize + CSP), **#17** (`0.0.0.0` overexposure → bind to specific interface), **#20** (unbounded audio growth → atomic writes + orphan reaper + retention policy), **#24** (Desktop Chrome ≠ iOS Safari → iOS on every UI-touching phase's checklist).

## Suggested Phase Breakdown

### Phase 0 — Spikes & Foundations (measurement phase; gates all downstream)
Validate the uncertainty that makes v1 commitments honest: VRAM on the actual 3060, Whisper WER on the builder's voice, F5 first-sentence TTFA, HTTPS-on-iPhone end-to-end. Produces the numbers that pick the STT default and confirm the TTS cold-swap budget. **Why first:** three of the four known tensions collapse to "measure, don't argue."

### Phase 1 — Foundations & Text Chat End-to-End
Repo scaffold (Web UI host, AI backend skeleton, `/health` stubs), SQLite schema + migrations, character CRUD with sanitized rendering, character importer (v2+v3 JSON and PNG), Web UI host ↔ LLM streaming path. **Milestone:** typed conversation with an imported SillyTavern character works end-to-end.

### Phase 2 — AI Backend Skeleton & Voice Lab
AI backend: FastAPI signaling + aiortc WebRTC endpoint, Silero VAD, faster-whisper loaded with Phase-0-selected default, hot-swap-aware TTS registry (exactly-one-engine rule). Voice Lab: upload → STT auto-transcript → user edits → save → synth preview. Settings screen with endpoint config + connection tests. **Milestone:** a voice can be captured, transcribed, edited, saved, and played back with either F5 or XTTS. No call yet.

### Phase 3 — First Working Call (MVP)
VoiceCall screen with `RTCPeerConnection`, `getUserMedia` constraints, data channel, AudioContext gesture unlock. Orchestrator FSM skeleton: IDLE → USER → LLM → AI → back. One-sentence reply, no streaming, no barge-in yet. Single-call writeback with atomic blob writes. **Milestone: First working call.**

### Phase 4 — Call Feel (the load-bearing work)
Sentence-chunked streaming TTS with <500 ms TTFA target. Barge-in: VAD + minimum-duration + word-count gates + LIFO task cancel + playback_stop + perceived-playback-end clock. Live bidirectional captions over data channel. Mid-stream LLM cancel verified. Echo-loop mitigation wired. **Milestone:** a 5-minute call on laptop speakers with accented English feels like a call.

### Phase 5 — Voice Breadth & Unified Thread Polish
Both TTS engines + cold-swap UX feedback + cache. Per-character default voice + per-chat voice override. Saved-audio toggles wired with replay UI. Unified thread rendering (interleaved text+call turns, Stitch-faithful visual distinction). Character Editor full v2+v3 field set. **Milestone:** feature-complete MVP per PROJECT.md Active list.

### Phase 6 — Mobile Hardening & Ship Polish
Full iOS Safari pass: Bluetooth/AirPods routing (#21), screen-off / Wake Lock (#22), `visibilitychange` clean pause. VAD sensitivity slider wired + labelled. Error states with actionable messaging. Storage housekeeping: orphan reaper, retention policy in Settings, size indicator. **Milestone:** builder can cold-start phone over LAN and have a call on AirPods without setup friction.

### Phase ordering rationale
- Text before voice: shared LLM integration and sliding-window plumbing shakes out in a non-realtime path.
- Voice Lab before first call: a call needs a voice; a voice needs STT; Voice Lab is the minimum-viable path to get STT end-to-end without needing WebRTC yet.
- First working call before call feel: establish media plumbing under a simpler semantic, then layer streaming + barge-in on known-working transport.
- Voice breadth after call feel: do the hard semantic work with one engine before multiplying the bug surface.
- Mobile hardening last: iOS quirks are discrete and many can only be verified once the call loop works; mobile is still on every phase's test checklist.

### Research flags
- **Phase 0** — work *is* measurement.
- **Phase 4 (Call Feel)** — threshold-tuning is empirical on the builder's speech + hardware; research WhisperX / RealtimeTTS tuning strategies.
- **Phase 5 (Voice Breadth)** — F5-TTS cold-swap reliability may need a second look if Phase 2 surfaces instability.

Standard-pattern phases (skip research-phase unless a specific snag appears): Phase 1, Phase 3, Phase 6.

## Open Empirical Questions (Phase 0 gates)

1. F5-TTS first-sentence synthesis latency on the 3060, 7-step Sway sampling, 3–5 word sentence. Target <300 ms; if >400 ms, pin XTTS as v1 default.
2. F5-TTS + Whisper-distil-v3-INT8 + Silero + CUDA context peak VRAM over a 30-minute call. Target stable <11 GB.
3. distil-large-v3 INT8 WER on a 10-minute Spanish-accented-English read-aloud of the builder's own voice, vs turbo and FP16.
4. End-to-end TTFA in a warm pipeline. Target <800 ms, stretch <500 ms.
5. iOS Safari end-to-end on the builder's phone with chosen cert path (mkcert + installed root CA). Go/no-go, not a number.
6. llama-server (or chosen LLM) actually cancels generation on stream close. `nvidia-smi` idle within ~200 ms of simulated barge-in.
7. `coqui-tts[server]` integration on the 3060 without Docker, streaming cleanly from in-process Python to aiortc.

## Phase 0 Recommendation

Ship a **~2–3 day spike** that answers Empirical Questions 1–3, 5, and 6 before the roadmapper freezes Phase 1+ commitments.

**Deliverables:**
- (a) **STT measurement rig:** standalone script loading distil-large-v3 INT8, large-v3-turbo INT8, large-v3 FP16; runs each against a 10-minute accented-English eval; logs WER, latency, peak VRAM. *Output: default STT pick.*
- (b) **TTS cold-load + first-chunk benchmark:** loads each TTS engine, synthesizes a 3–5 word sentence with a stock reference voice, logs first-audio time and total time; measures cold-swap duration. *Output: F5 first-sentence TTFA + cold-swap budget.*
- (c) **LLM cancel smoke test:** 20-line script opening a streaming completion, closing after ~200 tokens, watching `nvidia-smi` / server log for abort. *Output: go/no-go on LLM server choice.*
- (d) **mkcert bootstrap:** local CA + certs for chosen `.local` hostnames, installed on builder's iPhone via Configuration Profile + Certificate Trust Settings, verify `https://rayme.local` loads cleanly on Safari. *Output: reproducible cert path doc.*
- (e) **30-minute soak test rig:** loop (a)+(b) 20 times with artificial pauses, log VRAM every 30 s, assert no OOM and no unbounded growth. *Output: VRAM stability signal.*

**Why Phase 0 before Phase 1:**
- Three of four resolved tensions have quantitative revisit triggers. Phase 0 is where numbers confirm or flip the defaults before the roadmapper commits Phase 2 to F5-as-default only to discover in Phase 4 that XTTS should have been the pin.
- mkcert on iPhone is cheap to verify on day zero and catastrophically expensive in Phase 3.
- Phase 0 outputs become the first Key Decision rows in PROJECT.md.

**Explicit non-goals of Phase 0:** no UI beyond "can a phone reach the server over HTTPS," no orchestrator/FSM/Voice Lab/chat schema, no Pipecat re-evaluation (resolved).

## Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | HIGH | Transport, STT, VAD, LLM, UI, storage, card parsing anchored to official sources. Pipecat-vs-custom is the only judgement call. |
| Features | HIGH | Card v2+v3 specs explicit; call-feel feature set is industry-standard 2026; Stitch screen set is authoritative. |
| Architecture | HIGH on topology + WebRTC + FSM; MEDIUM on VRAM coexistence under real load | Phase 0 is the tie-breaker on VRAM. |
| Pitfalls | HIGH | Every Critical pitfall has named sources and concrete mitigation. |

**Overall:** HIGH, gated on Phase 0 confirming VRAM, TTFA, and WER numbers.

**Gaps to address (all Phase 0 or early Phase 2):** F5 VRAM + TTFA on 3060; Whisper variant WER on builder's voice; LLM server cancellation semantics; mkcert-on-iPhone repeatability; `coqui-tts[server]` non-Docker streaming.

## Sources

Full source lists live in the four dimension research files (`STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md`). Primary sources are official package docs/READMEs (pipecat-ai, f5-tts, coqui-tts idiap, faster-whisper, silero-vad, aiortc, openai, SvelteKit, SQLite), the character card v2/v3 spec repos, and the project-local PROJECT.md + `docs/stitch/DESIGN.md`. Secondary sources are industry writeups on WebRTC-vs-WebSockets for voice AI, latency budgets, VAD comparison, and iOS Safari / mkcert guidance. Tertiary (needs Phase 0 validation): F5 VRAM estimates on Ampere, framework-comparison blog posts, llama-server cancellation behavior.

---

*Synthesized: 2026-04-17*
