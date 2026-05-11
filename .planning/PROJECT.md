# RayMe

## What This Is

RayMe is a self-hosted web app that lets you have AI conversations that feel like real phone calls. You create or import characters (SillyTavern v2/v3 cards), clone voices from short audio samples with F5-TTS or XTTS v2, and then call them — with full-duplex audio, barge-in, and live bidirectional captions. Every chat thread holds both typed messages and call transcripts, so you can seamlessly switch between texting and calling the same character.

## Core Value

It must feel like an actual phone call with an AI — low-latency full-duplex audio with real barge-in, not a chatbot with audio bolted on. Everything else (voice fidelity, character depth, UI polish) is secondary to call feel.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

- [ ] Web app works on both phone and desktop browsers over LAN
- [ ] No authentication — LAN-level trust is sufficient
- [ ] English-only system in v1 (Spanish-accented English speakers still supported)
- [ ] A "chat" thread holds typed messages AND call transcripts interleaved
- [ ] Calls run full-duplex with barge-in via VAD
- [ ] Live captions show both user STT and AI response text during a call
- [ ] TTS playback uses a shared best-in-class chunk planner for every engine, including non-streaming engines and engines with token limits
- [ ] Text chat and call from a character can be started/resumed from the same thread
- [ ] LLM is OpenAI-compatible — works with the official OpenAI API or a local server (e.g., `llama-server`)
- [ ] STT is fast and accurate for accented English (Spanish-accented English specifically)
- [ ] TTS supports three engines in v1: F5-TTS, XTTS v2, and Qwen3-TTS 0.6B-Base, selectable per voice
- [ ] Voice Lab: upload a voice sample, STT auto-generates the reference transcript, user can edit and save the voice
- [ ] Character creator/editor supports the SillyTavern character-card field set plus a picture
- [ ] Character importer accepts SillyTavern v2 and v3 card formats (JSON and PNG-embedded)
- [ ] A character has a default voice, but each chat can override which voice is used
- [ ] Call memory uses a sliding-window of the chat's recent turns
- [ ] AI-generated audio is saved by default; user mic audio is off by default; both are togglable
- [ ] Three services run independently and connect over LAN: Web UI host, AI backend (STT/TTS/VAD), LLM server
- [ ] AI backend is optimized for an NVIDIA RTX 3060 (12 GB VRAM)
- [ ] UI follows the existing "Ethereal Core / True Dark" design system in `docs/stitch/`
- [ ] Screen inventory at minimum matches the Stitch canonical set: Home, Voice Lab, Character Gallery, Character Editor, Voice Call, Settings

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Multi-user / multi-tenant — single user, LAN only, scope stays tight in v1
- Authentication / accounts — LAN trust is acceptable; can add later if the product ever opens beyond self
- Bilingual or multilingual STT/TTS — English only in v1 to narrow model selection and tuning
- Native mobile apps — the responsive web app covers mobile via the browser
- Avatar / video / lip-sync — audio-first experience is the core; visuals not required to nail call feel
- Managed TTS/STT APIs (OpenAI Realtime, ElevenLabs streaming, etc.) — self-hosted engines only; keeps it a "your hardware" product
- Tool-using agent characters — conversational personas only, not task agents
- Cloud deployment / internet-facing hosting — designed for LAN

## Context

- Personal project, single user. The builder is a Spanish-accented English speaker, so STT quality on accented English is a concrete, personal quality bar.
- Home LAN topology: the GPU lives on one box (the AI backend), the web app may be served from a different box, and the LLM may run on yet another box or a remote API. The three endpoints are configured independently.
- Characters will often come from the SillyTavern ecosystem, so compatibility with v2 and v3 character cards matters more than inventing a new format.
- The "phone call" framing is load-bearing — it drives duplex audio, VAD/barge-in, live captions, and mobile browser support. If any of those slip, the core value erodes.
- F5-TTS and XTTS v2 are both zero-shot voice cloning systems; F5 specifically requires a transcript of the reference audio, which the Voice Lab will generate automatically via STT (and let the user edit).
- A design package already exists in `docs/stitch/`: an "Ethereal Core / True Dark" design system (DESIGN.md) and a canonical Stitch screen set (Home, Voice Lab, Character Gallery, Character Editor, Voice Call, Settings) with HTML exports and screenshots. The UI should follow this as a strong reference, deviating only when functional requirements demand it.

## Constraints

- **Hardware**: AI backend runs on a single NVIDIA RTX 3060 (12 GB VRAM) — STT, TTS, and VAD model choices must fit inside that budget simultaneously.
- **Latency**: End-to-end turn latency (user stops speaking → AI starts speaking) must be low enough to feel like a phone call — the entire stack is budgeted against this.
- **TTS chunking**: Long-form TTS must be segmented by a shared planner that respects model-specific token/character limits, prefers natural sentence boundaries, avoids tiny fragments, and measures first-chunk latency, total stitched playback time, and inter-chunk gaps.
- **Topology**: Three endpoints (Web UI, AI backend, LLM) must be independently configurable and connectable over LAN. No assumption that they share a host.
- **LLM contract**: The LLM must be reachable via an OpenAI-compatible Chat Completions API (streaming).
- **Browsers**: Must work on desktop Chrome and Chrome on Android, including mic capture, output routing, and full-duplex streaming.
- **Language**: English only for STT and TTS in v1.
- **Tech stack**: No strong a-priori preference — research picks the stack.
- **Design**: UI aligns with the "Ethereal Core / True Dark" design system and the canonical Stitch screen set in `docs/stitch/` as a strong reference; deviations allowed only when functional needs demand.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Core value is "call feel" over voice/character quality | The phone-call experience is the differentiator; everything else is table stakes | — Pending |
| Three independent services: Web UI, AI backend, LLM | Enables running the GPU box on LAN while the LLM can be OpenAI API or a separate local server | — Pending |
| Full barge-in via VAD, not turn-taking or push-to-talk | Required to feel like a real call | — Pending |
| Per-chat voice choice (character has a default, overridable per chat) | Lets the same character sound different across chats without duplicating characters | — Pending |
| Sliding-window memory for call context | Simpler than summarization; adequate for v1 and avoids extra LLM calls | — Pending |
| Single user, no auth, LAN only | Matches actual usage; removes major complexity (sessions, permissions, multi-tenancy) | — Pending |
| English-only v1 | Keeps STT/TTS model selection and tuning narrow; Spanish-accented English still fully supported | — Pending |
| AI-generated audio saved by default; mic audio off by default; both togglable | Privacy default for the user's own voice; replay value for the character's output | — Pending |
| SillyTavern v2 + v3 card import | Rides existing character ecosystem instead of inventing a format | — Pending |
| TTS engines in v1: F5-TTS and XTTS v2 | Both zero-shot clone from short samples; trade-offs between them handled via per-voice selection | — Pending |
| Engine-agnostic TTS chunk planner is required | Native streaming is inconsistent and some engines have hard token limits; benchmarks and runtime behavior must use the best chunked path per engine, not raw whole-generation fallbacks | — Pending |
| 3060 (12 GB) as the backend GPU target | Constrains model size choices across STT, TTS, and VAD | — Pending |
| Text chat and calls share one chat thread | "Continue a conversation" is the story, regardless of modality | — Pending |
| UI honors the existing Stitch "Ethereal Core / True Dark" design system as a strong reference | Visual language and screen set are already designed; rebuilding without it wastes prior work | — Pending |

## Phase 0 Key Decisions

*Frozen 2026-04-23 from `.planning/phases/00-measurement-gate/KEY_DECISIONS.md`
(machine-readable: `.planning/phases/00-measurement-gate/results/phase0_summary.json`).*

- **HTTPS strategy (REQ-A1):** `mkcert` on LAN. The passing Android validation used `https://192.168.1.199:8443` because `rayme.local` name resolution was not configured on the phone. Setup: see `.planning/phases/00-measurement-gate/HTTPS-SETUP.md`.
- **STT default (REQ-A3):** faster-whisper `distil-large-v3` (`int8_float16`). WER on the builder's Spanish-accented English sample = `0.0627`. Peak VRAM = `1731.4` MB.
- **TTS v1 default (Resolved Tension #3):** `f5` was the Phase 0 baseline. TTFA = `517.3` ms, RTF = `0.388`. `results/tts_runtime_matrix.json` kept native Windows as the fastest measured F5 runtime for both short-ack and long-form paths.
- **TTS live-call default (Phase 8):** `voxcpm2`. Phase 8 same-run warm median first-audio beat F5 using live streaming call playback (`762.7 ms` vs `948.0 ms`); evidence: `results/voxcpm2-live-streaming-call-flow.json`.
- **TTS v1 engine roster (REQ-22):** `F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`, and `VoxCPM2`. Qwen3-TTS is explicitly **not** the default: it failed the acceptance gate on TTFA/RTF and still lacks approved accent quality, but it remains included as an opt-in engine. VoxCPM2 is now promoted as the preferred/default live-call TTS engine after Phase 8 live streaming evidence; F5 remains available as fallback/comparator.
- **TTS chunking requirement (REQ-45):** all engines need a shared chunk planner before final long-form decisions. The planner must enforce model-specific limits such as XTTS `inference_stream`'s 400-token cap, preserve natural sentence boundaries where possible, and benchmark first chunk, total stitched playback, inter-chunk gaps, and the stitched WAV.
- **FA2 (Qwen3-TTS 1.7B eligibility):** not installed; reason: `windows_build_compile_error`. Qwen3-TTS 1.7B is ineligible for v1, so the included Qwen path is `0.6B-Base` only.
- **Hardware note:** measured directly on the target RTX 3060; no 4090-to-3060 extrapolation was needed. Per-engine 3060 fit: F5=`yes`, XTTS=`yes`, Qwen3-0.6B=`yes`.
- **Runtime mandate:** AI model paths for the real-time call simulator are GPU
  paths. CPU fallback for STT/TTS/VAD/LLM/embedding runtime is a regression, not
  a quick fix. Deployments must fail fast when CUDA runtime, CUDA PyTorch, or
  model device configuration is missing.
- **Overrides:** none.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-17 after initialization*
