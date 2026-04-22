# Stack Research — RayMe

**Domain:** Self-hosted, single-user, LAN-only real-time voice AI call app (full-duplex voice + barge-in, character-card characters, voice cloning)
**Researched:** 2026-04-16
**Overall Confidence:** HIGH on transport / framework / STT / VAD / storage / character cards. MEDIUM on exact VRAM sums for F5-TTS under concurrent load (no public 3060 benchmark). MEDIUM-LOW on Qwen3-TTS RTF / TTFA on 3060 (no direct benchmark — extrapolated from GTX 1080 and RTX 3060 Ti / 3090 / 4060 datapoints; Phase 0 measures). F5-TTS and XTTS v2 are fixed by product decision; **Qwen3-TTS (added 2026-04-17)** ships as the third engine in v1 conditional on Phase 0 acceptance (see `QWEN3-TTS.md` §7 triggers).

---

## Executive Recommendation (TL;DR)

- **Transport:** WebRTC (bidirectional media) via **Pipecat `SmallWebRTCTransport`** (aiortc under the hood). WebSocket is only a fallback when mic constraints fail in an iOS in‑app webview.
- **STT:** **faster-whisper** running `distil-large-v3` (or `large-v3-turbo`) in `int8_float16`, driven by a streaming wrapper (ufal `whisper_streaming` pattern, packaged into the AI backend). **Not Parakeet** — Parakeet is faster but noticeably worse on accented English, which is the builder's literal voice.
- **TTS:** Three engines in v1 — **F5-TTS** (`f5-tts` 1.1.x), **Coqui XTTS v2** (`coqui-tts` 0.27.x, idiap fork), and **Qwen3-TTS 0.6B-Base** (`qwen-tts` 0.1.x, Apache-2.0, Alibaba official). The 1.7B-Base Qwen variant is VRAM-conditional and only enabled if FlashAttention 2 installs cleanly on the builder's Windows box. All three hosted as local HTTP/WebSocket inference servers in a single Python process per engine. Only one TTS is resident on GPU at a time (swap on voice selection) to fit the VRAM budget. Full Qwen3-TTS assessment in `.planning/research/QWEN3-TTS.md`.
- **VAD:** **Silero VAD v5** as the authoritative turn-taker, running **server-side** inside Pipecat. A second lightweight copy runs **in-browser** (@ricky0123/vad-web) purely to give the UI instant "user started speaking" feedback and trigger barge-in locally.
- **LLM client:** Official **openai-python** (`openai` SDK) in async streaming mode, pointed at a configurable `base_url` (OpenAI, `llama.cpp` server, Ollama, etc.). No tool/function calling in v1.
- **Web UI:** **SvelteKit 2 / Svelte 5** with Vite. Small bundle, compiler-based (no React runtime tax on mobile), trivial to paste in the Stitch HTML exports as starting templates, first-class WebRTC access via browser APIs. Static adapter — served straight off a local HTTP server.
- **AI backend framework:** **Pipecat 1.x** on top of FastAPI + uvicorn, with custom `F5TTSService` and `Qwen3TTSService` (subclasses of `TTSService`) since Pipecat ships XTTS but not F5 or Qwen3-TTS. Don't reinvent the pipeline; Pipecat already solves VAD→STT→LLM→TTS interruption correctly. Qwen3-TTS wrapper also needs to honor Pipecat's frame-cancellation semantics for barge-in (see `QWEN3-TTS.md` §10 open question).
- **Storage:** **SQLite** (via `aiosqlite` + `sqlalchemy` 2.x) for threads/messages/characters/voices metadata. **Plain files** on disk for binary assets (voice reference WAV, saved call audio, character avatars). No Postgres.
- **Character cards:** **Pillow** (read PNG) + a tiny custom tEXt/ccv3 chunk reader (use `png-parser` or just 200 lines of Python). Follow the v2 spec and v3 spec verbatim — prefer `ccv3` when present, else fall back to `chara`.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|---|---|---|---|---|
| Python | 3.11.x | AI backend runtime | Required by Pipecat 1.0; supported by f5-tts, coqui-tts, faster-whisper, aiortc, openai | HIGH |
| **Pipecat** | `pipecat-ai` 1.0.0 (2026-04-14) | Voice-agent orchestration (VAD → STT → LLM → TTS with interruption) | Solves every hard part of a call loop: barge-in on partial LLM output, sentence-aggregated TTS streaming, frame cancellation, bidirectional WebRTC. Self-hostable via `SmallWebRTCTransport` with no Daily/LiveKit dependency. Ships XTTS, Silero VAD, Ollama, OpenAI-compatible LLM, aiortc transport. Avoids 2000+ lines of hand-rolled asyncio orchestration that you would otherwise get subtly wrong on turn boundaries. | HIGH |
| FastAPI | 0.115+ | HTTP server for signalling + app API (threads, characters, voices) | Pipecat's `SmallWebRTCTransport` mounts on FastAPI; one process for signalling and app CRUD. | HIGH |
| uvicorn | 0.30+ | ASGI server | Standard Pipecat/FastAPI pairing. | HIGH |
| aiortc | 1.9+ (pulled by Pipecat) | Python WebRTC peer (audio tracks, DTLS, ICE) | Pipecat SmallWebRTC uses it directly. Opus 48 kHz in, Opus/PCM16 out — matches mobile browser defaults. | HIGH |
| **F5-TTS** | `f5-tts` 1.1.19 (2026-04-16) | Zero-shot TTS engine #1 (requires reference audio + transcript) | Fixed requirement. v1 base model (2025-03-12) has better training/inference perf. Python package on PyPI. No official REST — we wrap the inference functions in a small FastAPI/WebSocket server (or reuse the bundled `socket_server.py`). RTF ~0.15 on L20; target 7-step Sway sampling for RTF ~0.03 on 3060. | MEDIUM (no public 3060 benchmark) |
| **Coqui XTTS v2** | `coqui-tts` 0.27.5 (2026-01-26, idiap fork) | Zero-shot TTS engine #2 (reference audio only, no transcript needed) | Fixed requirement. Idiap fork is the live maintained line after Coqui's Dec 2025 shutdown. Native streaming API, <200 ms first-chunk latency advertised. ~2.1 GB VRAM at inference. Built-in HTTP server via `[server]` extra. | HIGH |
| **Qwen3-TTS** | `qwen-tts` 0.1.1 (2026-02-06) — HF `Qwen/Qwen3-TTS-12Hz-0.6B-Base` (default), `Qwen/Qwen3-TTS-12Hz-1.7B-Base` (FA2-gated) | Zero-shot TTS engine #3 (reference audio + transcript, same contract as F5) | Apache-2.0 (only commercially-permissive engine). Discrete multi-codebook LM with streaming-capable API (`stream_generate_voice_clone`). 0.6B fits comfortably on 3060 12 GB with FA2; 1.7B is VRAM-tight. FlashAttention 2 required for viable TTFA — install friction on Windows (see Known bugs below). Phase 0 measures TTFA/RTF on actual 3060 before freezing as v1 default candidate. Full assessment: `.planning/research/QWEN3-TTS.md`. | MEDIUM-LOW (no direct 3060 benchmark; 2-month-old Python package) |
| **faster-whisper** | 1.1+ (`SYSTRAN/faster-whisper`) | STT — streaming transcription with CTranslate2 | 4× faster than openai-whisper, int8_float16 quant fits a distil-large-v3 in ~1.5 GB VRAM. Distil-large-v3 is explicitly designed to work with the faster-whisper chunking algorithm, making streaming with low latency straightforward. **Whisper handles Spanish-accented English far better than Parakeet**, which is the whole reason we don't pick Parakeet despite its throughput. | HIGH |
| **Silero VAD** | v5 (2024-late; still current) | Primary VAD for turn-taking and barge-in on the server side | <1 ms per 30 ms frame on a single CPU thread, ONNX. Pipecat has a first-class `SileroVADAnalyzer`. Can also run in the browser via @ricky0123/vad-web for instant local "I'm speaking" UX. | HIGH |
| **openai-python** | `openai` 1.50+ | LLM client (streaming chat completions) | Configurable `base_url` → works with OpenAI API, `llama-server` (llama.cpp), Ollama, vLLM, LM Studio, text-generation-webui. `stream=True` + `AsyncChatCompletionStream` is the canonical async interface. Pipecat wraps this in `OpenAILLMService` and `OLLamaLLMService`. | HIGH |
| **SvelteKit** | 2.x with **Svelte 5** | Web UI framework | Compiler-based → tiny bundle (mobile Safari friendly). No React runtime. Existing Stitch HTML exports can be dropped into `+page.svelte` files almost as-is since Svelte supports plain HTML+CSS without component wrappers. `@sveltejs/adapter-static` produces a plain static site served from any HTTP server on the LAN. WebRTC and WebSocket are plain browser APIs — no framework-specific glue needed. | HIGH |
| **SQLite** | 3.45+ via `aiosqlite` + SQLAlchemy 2.x (async) | Threads, messages, characters, voices metadata, settings | Single-user LAN — a process-local file is correct. No networked DB server to babysit. SQLAlchemy 2.x gives us migrations (alembic) and ergonomic async queries. Can always move to Postgres later; schema translates. | HIGH |
| **Pillow** | 10+ | PNG read/write for character avatars and card tEXt chunk extraction | Standard Python imaging lib. Used alongside a tiny chunk parser for `chara`/`ccv3` tEXt extraction. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---|---|---|---|
| `pipecat-ai-small-webrtc-prebuilt` | latest | Reference WebRTC test client mounted at `/prebuilt` on the FastAPI app | Development only. Confirms the backend is alive while the real SvelteKit UI is being built. Not shipped to end user. |
| `pipecat-client-web` | latest | Optional: official JS client SDK if we want their RTVI-style events | Only if we find a feature we need (event schema, reconnect logic). Otherwise raw `RTCPeerConnection` + small signalling in SvelteKit is fine. |
| `@ricky0123/vad-web` | 0.x | Browser-side Silero VAD for immediate UI feedback on user speech start | Triggers the "barge-in" UI cue locally before the server round-trips its own VAD decision. Not authoritative — the server VAD still owns the interrupt decision. |
| `sqlalchemy` | 2.x async | ORM + schema migrations driver | Use with `aiosqlite`. Pairs with Alembic for migrations when the schema changes. |
| `alembic` | latest | Schema migrations | Needed the moment we have more than one developer or one deployment. Minimal overhead up front. |
| `pydantic` | 2.x | Request/response models, character card schema validation | Already a Pipecat/FastAPI dep. Model the v2 and v3 card shapes as Pydantic so bad cards fail loudly. |
| `httpx` | 0.27+ | Outbound HTTP (LLM, TTS servers) | Used internally by `openai` SDK async client. |
| `soundfile` / `numpy` / `torchaudio` | current | Audio file IO and resampling (voice reference WAVs, saved call audio) | Standard for any TTS/STT pipeline. |
| `ffmpeg-python` or the `ffmpeg` CLI | current | Container conversion for saved call audio (Opus → MP3/WAV download) | Needed only for the "download saved audio" feature. |
| `python-multipart` | current | FastAPI file uploads (voice samples, character PNGs) | Standard FastAPI dep for multipart form uploads. |
| `loguru` | 0.7+ | Structured logging with nice colour in the dev terminal | Pipecat already uses it. Keep it uniform. |

### Browser / Client Side

| Library / API | Purpose | Notes |
|---|---|---|
| `RTCPeerConnection` + `getUserMedia({audio: {echoCancellation, noiseSuppression, autoGainControl}})` | Full-duplex audio to the AI backend | iOS Safari 17+ supports these; echo cancellation needs ~1–2 s of training — design the call-join flow to tolerate this. Expect `echoCancellation` to be best-effort on mobile. |
| `AudioWorklet` | Any client-side audio processing (e.g., feeding @ricky0123/vad-web) | Use worklets, not the deprecated `ScriptProcessorNode`. |
| `WebSocket` | Signalling channel for SmallWebRTC + control channel (text messages, captions, thread updates) | SvelteKit `+page.svelte` talks to FastAPI WS endpoints for non-media traffic. |
| `@ricky0123/vad-web` | Browser-side Silero VAD | Optional but recommended for "user-speaking" UI state. |

### Development Tools

| Tool | Purpose | Notes |
|---|---|---|
| `uv` (astral-sh) | Python dependency + venv manager | Fast, reliable; coqui-tts README explicitly recommends it; Pipecat works fine with it. |
| `ruff` + `ruff format` | Lint + format Python | One tool, fast. |
| `pytest` + `pytest-asyncio` | Tests | Pipecat's own tests use this stack. |
| `vite` | Dev server for SvelteKit with HMR | Comes with SvelteKit. |
| `playwright` | E2E tests of the call flow on a real Chromium/WebKit | Only sane way to verify mic capture, WebRTC negotiation, and barge-in end-to-end. |
| Docker (optional) | Bundling the XTTS streaming server if we use the upstream image | Pipecat's `XTTSTTSService` docs assume a Docker-run XTTS server. We can skip Docker by running the idiap coqui-tts Python server directly in-process. |

---

## Installation

```bash
# ----- AI Backend (Python, GPU box) -----
# Python 3.11 recommended
uv venv --python 3.11 .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# PyTorch first (install the CUDA build matching your driver, e.g. cu121)
# https://pytorch.org/get-started/locally/
uv pip install --index-url https://download.pytorch.org/whl/cu121 torch torchaudio

# Core orchestration + transports + VAD + LLM
uv pip install "pipecat-ai[webrtc,silero,openai]==1.0.*"

# STT
uv pip install faster-whisper

# TTS engines
uv pip install "f5-tts==1.1.*"
uv pip install "coqui-tts[server]==0.27.*"
uv pip install "qwen-tts==0.1.*"
# Qwen3-TTS strongly recommends FlashAttention 2 for viable TTFA on 3060.
# Windows install is reportedly brittle — Phase 0 verifies with a fallback to non-FA2 for 0.6B only.
uv pip install flash-attn --no-build-isolation   # may fail on Windows; fallback: skip and restrict Qwen to 0.6B-Base

# App server + storage
uv pip install fastapi "uvicorn[standard]" sqlalchemy aiosqlite alembic pydantic pillow python-multipart loguru httpx soundfile numpy

# Dev
uv pip install ruff pytest pytest-asyncio

# Dev-only prebuilt WebRTC tester (optional)
uv pip install pipecat-ai-small-webrtc-prebuilt

# ----- Web UI (separate box or same box) -----
npm create svelte@latest rayme-web   # SvelteKit 2 / Svelte 5, TypeScript, skeleton project
cd rayme-web
npm install
npm install -D @sveltejs/adapter-static
# Optional: in-browser VAD for UI-only barge-in feedback
npm install @ricky0123/vad-web onnxruntime-web
```

---

## VRAM Budget on RTX 3060 12 GB

The load-bearing question. This is the *simultaneously resident* case:

| Component | Mode | VRAM (approx.) | Notes |
|---|---|---:|---|
| faster-whisper `distil-large-v3` | int8_float16 | ~1.5 GB | Benchmark: 1481 MB total, 1468 MB peak. Great candidate for 24/7 residence. |
| Silero VAD (server) | onnx | <100 MB (often CPU) | Can run CPU-only; negligible VRAM either way. |
| **One TTS resident at a time:** | | | |
| — XTTS v2 | fp16 | ~2.1 GB | Measured, idiap fork. 24 kHz native. |
| — F5-TTS | fp16 | ~4–6 GB | No authoritative 3060 number; Flow Matching + DiT. Sway sampling with 7 NFE keeps it under the ceiling. |
| — Qwen3-TTS 0.6B-Base | bf16 + FA2 | ~2–3 GB | Extrapolated from published 3060 Ti / 3090 numbers; needs Phase 0 confirmation on 3060. 24 kHz native output (48 kHz tokenizer variant also available). |
| — Qwen3-TTS 1.7B-Base | bf16 + FA2 | ~5–6 GB | FA2 effectively required; without FA2 creeps to ~8 GB and pushes total past 11 GB with Whisper + VAD + slack. VRAM-conditional in v1. |
| Headroom for CUDA runtime, cuDNN workspace, Opus encode | — | ~1.5 GB | Always leave this. |
| **Total worst case (F5 resident + Whisper + VAD)** | | **~8 GB** | Fits. |
| **Total middle case (Qwen 1.7B resident + Whisper + VAD + FA2)** | | **~9 GB** | Tight but feasible with FA2. Without FA2: ~11 GB → reject 1.7B. |
| **Total best case (XTTS or Qwen 0.6B resident + Whisper + VAD)** | | **~4.5–5.5 GB** | Plenty. |

**Design rule:** Only one TTS engine is GPU-resident per call. The hot-swap registry now covers **three engines** (F5-TTS ↔ XTTS v2 ↔ Qwen3-TTS). Swap paths: 6 directed (3 engines × 2). When the user picks a voice tied to a different engine, we unload the current model and load the target — a ~2–5 s cold-swap is acceptable because it happens between calls, not mid-call. If we ever need two simultaneously (e.g., a character-switching feature), the LLM must be *off-box* (on another machine via OpenAI-compatible API), which is already the design.

**What does NOT fit on a 3060 alongside this:** a local LLM. The LLM is designed to run on a separate box (or the OpenAI API) — the topology assumes three independent endpoints, and the 12 GB budget is all for STT+TTS+VAD.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| Pipecat SmallWebRTC | LiveKit Agents | If we ever go multi-user, cloud-hosted, or need a SFU to reach non-LAN clients. Adds infra weight we do not need. |
| Pipecat | Raw FastAPI + custom asyncio | If the pipeline needs drop to ~3 frame types and no interruption logic. For a real call with barge-in, hand-rolling is a net loss. |
| WebRTC transport | WebSocket + raw PCM16 frames | If we hit an iOS webview where `getUserMedia` is blocked (some in-app browsers). Pipecat also supports `WebsocketServerTransport` — keep as fallback. |
| faster-whisper distil-large-v3 | NVIDIA Parakeet TDT 0.6B v2 | If the builder becomes a *native* speaker (unlikely) or if throughput dominates and minor accented-English WER is acceptable. Parakeet is ~10× faster but measurably worse on accented/non-native English. |
| faster-whisper distil-large-v3 | WhisperLive / whisper_streaming | We borrow the *pattern* from `ufal/whisper_streaming` (rolling window + LocalAgreement) but run it inside our own backend next to faster-whisper. Pulling WhisperLive as a separate service is fine if we want an out-of-process microservice later. |
| Silero VAD server-side | WebRTC VAD (GMM) | Only if we target dirt-old browsers or CPU-constrained clients where ONNX web won't load. Lower accuracy. |
| SvelteKit | Next.js | If we need React ecosystem components. Heavier bundle, larger mobile download, React runtime overhead. |
| SvelteKit | Astro + island | Good pick for content-first sites; overkill routing model for an SPA that is 80% a phone-call screen. |
| SvelteKit | Plain Vite + React | Viable, but ~3× the JS on the wire vs Svelte 5 for the same result. |
| SvelteKit | HTMX + plain HTML | Attractive for text-chat CRUD, but WebRTC negotiation and bidirectional audio state machine is pure client JS — HTMX buys you nothing there and costs us a second paradigm. |
| SQLite | Postgres | If v2 ever becomes multi-user or multi-host with concurrent writers. Not now. |
| SQLite + files on disk | Everything in DB (BLOBs) | Don't stuff WAVs into SQLite. Files on disk with FK'd paths is standard and keeps DB small and backupable. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| **OpenAI Realtime API / ElevenLabs streaming / managed TTS-STT clouds** | Out of scope per PROJECT.md. "Your hardware" product. | Self-hosted F5-TTS + XTTS + Qwen3-TTS + faster-whisper. |
| **Third-party Qwen3-TTS CUDA-graph forks** (`andimarafioti/faster-qwen3-tts`, `rekuenkdr/Qwen3-TTS-streaming`, `groxaxo/Qwen3-TTS-Openai-Fastapi`) as runtime dependencies | 2-month-old, single-maintainer, no release cadence. RayMe depends only on the official `QwenLM/Qwen3-TTS` + `qwen-tts` PyPI. Third-party wrappers are *reference* for techniques (CUDA graphs, FastAPI wiring), not dependencies. | Vendor the relevant technique into RayMe's own `Qwen3TTSService` with a pinned `qwen-tts==0.1.1`. |
| **NVIDIA Parakeet** for STT | Degraded accuracy on accented English (builder is Spanish-accented English speaker — this *is* the target). Parakeet's docs themselves note weaker informal/accented performance vs Whisper. | `faster-whisper distil-large-v3` or `large-v3-turbo` int8_float16. |
| **`openai-whisper`** (the original Python package) | 4× slower than faster-whisper at the same accuracy, poor streaming story. | `faster-whisper` (CTranslate2). |
| **Original `coqui-ai/TTS` repo** | Company shut down Dec 2025; no updates. | `idiap/coqui-ai-TTS` fork on PyPI as `coqui-tts`. |
| **Building WebRTC signalling from scratch** | Lots of ICE/DTLS/SDP edge cases, especially on mobile Safari. | Pipecat `SmallWebRTCTransport` — it's aiortc wired correctly. |
| **WebRTC VAD (the old GMM algorithm)** | Noticeably worse than Silero in real rooms. | Silero VAD v5. |
| **ScriptProcessorNode** in browser | Deprecated; janky on mobile Safari. | `AudioWorklet`. |
| **Postgres, Redis, message queues** | Single-user LAN app. Operational weight for nothing. | SQLite + in-process asyncio. |
| **Next.js App Router** | Heavy for this; server components buy us nothing for a single-user SPA; React runtime on mobile is costly. | SvelteKit static. |
| **Turn-taking / push-to-talk as v1 design** | PROJECT.md explicitly requires full barge-in. | VAD-driven interruption via Pipecat frame cancellation. |
| **Storing AI audio in DB as BLOBs** | Makes backups expensive and DB hot. | Files on disk keyed by UUID, path stored in SQLite. |

---

## Stack Patterns by Variant

**If the builder later adds a second person on the LAN:**
- SQLite still works for read-heavy multi-reader if they're not in the same call; otherwise migrate to Postgres. Pipecat supports this already — no code change for auth added because the scope is still LAN trust.

**If F5-TTS proves too slow on 3060 at full NFE:**
- Switch F5 inference to 7-step Sway-sampling + EPSS (RTF ~0.03 on 3090; expect ~0.06–0.10 on 3060). No model change.
- If Sway-7 also misses the <800 ms TTFA budget, the Resolved Tension #3 promotion path now has **two** candidates: XTTS v2 (proven) or Qwen3-TTS 0.6B-Base (Apache-2.0 advantage, if Phase 0 measured TTFA <400 ms AND clean Spanish-accented-English clone quality).

**If Qwen3-TTS fails Phase 0 acceptance (TTFA >400 ms, RTF ≥1, FA2 install fails, or accent drift):**
- Drop Qwen3-TTS from v1 and backlog to v2+. REQ-22 falls back to two engines (F5 + XTTS). Voice Lab engine picker hides the Qwen option behind a feature flag. Research artifact (`QWEN3-TTS.md`) stays as v2+ reference material.

**If iOS Safari blocks `getUserMedia` inside a given in-app webview:**
- Fall back to Pipecat's `WebsocketServerTransport` + raw PCM16 frames. The UI detects the failure and swaps the audio pipeline. Keep both code paths behind one `AudioTransport` abstraction.

**If the LLM ends up running on the same box later (against the design):**
- The TTS engine must then be the smaller of the two (XTTS ~2.1 GB) to leave room. F5-TTS on the same box as a 7B int4 LLM will OOM a 3060 12 GB.

---

## Version Compatibility

| Package | Compatible With | Notes |
|---|---|---|
| `pipecat-ai` 1.0.0 | Python 3.11+, PyTorch any | Python 3.12 OK. Older 0.x Pipecat APIs differ significantly — use 1.0+ only. |
| `f5-tts` 1.1.19 | Python 3.10+, PyTorch with CUDA | Conda/uv env with Python 3.11 recommended by upstream README. |
| `coqui-tts` 0.27.5 | Python ≥3.10, <3.15 | PyTorch must be installed separately since v0.27.4 (explicitly removed as a default dep). |
| `qwen-tts` 0.1.1 | Python ≥3.10, PyTorch with CUDA, bf16 capable (Ampere+) | 2 months old — pin exactly, no `^` or `>=`. Tokenizer borrowed from Mistral; emits `fix_mistral_regex=True` warning (cosmetic). FlashAttention 2 strongly recommended (install friction on Windows — see Known bugs). |
| `faster-whisper` 1.1.x | CTranslate2 4.x | For CUDA, install `ctranslate2` matching your CUDA version. int8_float16 requires Ampere or newer (3060 is Ampere → OK). |
| `aiortc` 1.9+ | Python 3.10+ | Bundled by Pipecat's `[webrtc]` extra; don't pin independently. |
| `openai` Python 1.50+ | httpx default; aiohttp optional | Streaming API is stable since 1.x GA. Pipecat's `OpenAILLMService` depends on the same package. |
| `@sveltejs/kit` 2.x | Node 20+, Svelte 5 | Svelte 5 is a breaking change from Svelte 4; all new tutorials target Svelte 5 runes. |

---

## Topology (what runs where)

Three independent, LAN-configurable endpoints per PROJECT.md:

```
┌────────────────────┐    ┌────────────────────────────────────┐    ┌──────────────────┐
│  Web UI host       │    │  AI Backend (GPU box, RTX 3060)    │    │  LLM endpoint    │
│  SvelteKit static  │◄──►│  FastAPI + Pipecat                 │◄──►│  OpenAI API /    │
│  served by any     │WS  │   ├─ SmallWebRTCTransport (aiortc) │    │  llama-server /  │
│  HTTP server       │    │   ├─ SileroVADAnalyzer              │    │  Ollama (any     │
│  (Caddy/nginx/     │WebRTC  │   ├─ FasterWhisperSTTService        │    │   OpenAI-compat) │
│   Python http)     │◄──►│   ├─ OpenAILLMService (base_url)    │    │                  │
│                    │    │   └─ XTTSTTSService  OR  F5TTSService  OR  Qwen3TTSService (one resident) │    │                  │
└────────────────────┘    │   + SQLite (threads, voices, chars)│    └──────────────────┘
                          │   + files on disk (audio, images)  │
                          └────────────────────────────────────┘
```

- **Signalling**: HTTPS/WS from UI to AI backend for WebRTC SDP exchange + app API.
- **Media**: WebRTC peer between browser and AI backend (Opus, ~20 ms frames).
- **LLM**: Plain HTTPS from AI backend to the configured LLM `base_url` with `stream=True`.

---

## Character Card Parsing (v2 + v3)

Minimal, no heavyweight lib needed:

1. **Read PNG** with Pillow: `Image.open(buf).text` gives you the tEXt chunks Pillow recognises, but it can miss some — for safety also walk chunks manually.
2. **Walk chunks**: 8-byte PNG header → then `(length, type, data, crc)` tuples until `IEND`. Look for `type == b"tEXt"` and split `data` on the first `\x00` to get `(keyword, text)`. This is ~40 lines of Python.
3. **Prefer `ccv3` keyword**, else fall back to `chara`.
4. **Decode** base64 → UTF-8 → JSON.
5. **Validate** against Pydantic models matching the v2 and v3 specs from the official spec repos (`malfoyslastname/character-card-spec-v2`, `kwaroran/character-card-spec-v3`).
6. **On v2 ingest**, up-convert to the internal v3-shaped model so the rest of the app only has one shape.

Libraries to pull:
- `Pillow` (already listed) — PNG read/write.
- No npm/Python library required for chunk walking; it's a 1-file utility. Alternative if you want one: `png-parser` (`pip install git+https://github.com/Hedroed/png-parser`).

---

## Sources

### Context7 / Official docs / PyPI (HIGH confidence)
- https://pypi.org/project/pipecat-ai/ — Pipecat 1.0.0, Python ≥3.11, extras list verified
- https://pypi.org/project/f5-tts/ — f5-tts 1.1.19 (2026-04-16), Python ≥3.10
- https://pypi.org/project/coqui-tts/ — coqui-tts 0.27.5 (2026-01-26), Python ≥3.10 <3.15, PyTorch separate
- https://github.com/SWivid/F5-TTS — v1 base model 2025-03-12; Python ≥3.10; gradio + socket server bundled, no official REST
- https://github.com/idiap/coqui-ai-TTS — Idiap-maintained Coqui fork; XTTS v2 streaming <200 ms; server extra
- https://huggingface.co/coqui/XTTS-v2 — XTTS v2 model card; ~2.1 GB VRAM inference
- https://github.com/QwenLM/Qwen3-TTS — Official Alibaba Qwen3-TTS repo (Apache-2.0); discrete multi-codebook LM; voice-clone API
- https://pypi.org/project/qwen-tts/ — `qwen-tts` 0.1.1 package (2026-02-06); Apache-2.0 classifier
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base — Qwen3-TTS 0.6B-Base model card
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base — Qwen3-TTS 1.7B-Base model card
- https://github.com/jamiepine/voicebox — Reference integration (non-streaming); MIT; reusable backend plumbing pattern
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2 — Parakeet card; streaming via chunked inference
- https://github.com/SYSTRAN/faster-whisper — faster-whisper benchmarks (distil-large-v3 int8 ~1.5 GB VRAM)
- https://github.com/snakers4/silero-vad — Silero VAD v5; <1 ms per 30 ms frame CPU
- https://docs.pipecat.ai/server/services/transport/small-webrtc — SmallWebRTCTransport, aiortc-based, no external service
- https://docs.pipecat.ai/server/services/tts/xtts — Pipecat XTTSTTSService expects a local XTTS streaming server
- https://github.com/aiortc/aiortc — aiortc; Opus 48 kHz, PCM 8/16 kHz supported
- https://github.com/openai/openai-python — openai SDK async streaming via `AsyncChatCompletionStream`
- https://github.com/kwaroran/character-card-spec-v3 — ccv3 PNG tEXt chunk; precedence over v2
- https://github.com/malfoyslastname/character-card-spec-v2 — chara tEXt chunk; field set

### Secondary (MEDIUM confidence)
- https://www.collabora.com/news-and-blog/blog/2024/05/28/transforming-speech-technology-with-whisperlive/ — streaming Whisper pattern
- https://modal.com/blog/open-source-stt — cross-model STT benchmarks
- https://modal.com/blog/low-latency-voice-bot — Pipecat + open models end-to-end latency profile
- https://www.daily.co/blog/you-dont-need-a-webrtc-server-for-your-voice-agents/ — rationale for serverless WebRTC
- https://picovoice.ai/blog/best-voice-activity-detection-vad-2025/ — VAD comparison
- https://webrtchacks.com/guide-to-safari-webrtc/ — iOS Safari WebRTC gotchas
- https://github.com/livekit/agents/issues/3758 — real-world mobile echo cancellation issue (informs UX design)
- https://github.com/ricky0123/vad — @ricky0123/vad-web browser Silero

### Opinion / blog (LOW confidence — used only to cross-check direction)
- https://medium.com/data-science-in-your-pocket/nvidia-parakeet-v2-vs-openai-whisper — accented-English comparison
- https://www.f22labs.com/blogs/difference-between-livekit-vs-pipecat-voice-ai-platforms/ — framework comparison
- https://dev.to/pockit_tools/nextjs-vs-remix-vs-astro-vs-sveltekit-in-2026-the-definitive-framework-decision-guide-lp5 — framework survey
- https://solodevstack.com/blog/svelte-vs-htmx-solo-developers — htmx vs svelte for small apps

### What I could NOT verify (flagged)
- **Exact F5-TTS VRAM on RTX 3060 under 7-step Sway sampling.** No public benchmark. The 4–6 GB estimate is derived from model size and DiT patterns for similar sizes; will need to be measured on the actual card as the first Phase 0 spike.
- **Whether `coqui-tts[server]` streams to aiortc out-of-the-box through Pipecat's `XTTSTTSService` without using the Docker image.** Pipecat docs show the Docker path as default. Non-Docker path is straightforward (it's just HTTP streaming on localhost) but not explicitly documented — call it a Phase 0 verification item.
- **Exact Qwen3-TTS TTFA and RTF on RTX 3060 (0.6B-Base and 1.7B-Base, with and without FA2).** No direct 3060 benchmark exists. Extrapolation from GTX 1080 / RTX 3060 Ti / 3090 / 4060 datapoints suggests 0.6B is RTF-borderline and 1.7B is below real-time; Phase 0 measures definitively. Full analysis in `QWEN3-TTS.md` §3.
- **Whether FlashAttention 2 installs cleanly on Python 3.12 + CUDA 12.1 + Windows 11 + RTX 3060 (Ampere sm_86).** HN discussion flags problems. Phase 0 verifies; fallback is 0.6B-Base without FA2.
- **Whether Qwen3-TTS preserves Spanish-accented English from reference audio.** No community benchmark; reports of Chinese-accent bleed on English. Subjective listening test required in Phase 0 on the builder's voice.
- **Whether Pipecat frame-cancellation semantics cooperate with a custom `Qwen3TTSService` for mid-stream barge-in.** `stream_generate_voice_clone` exists in `qwen-tts`; integration into Pipecat's interrupt pattern is untested.

---

*Stack research for: self-hosted real-time voice AI call app (RayMe)*
*Researched: 2026-04-16*
