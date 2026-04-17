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
- [ ] Text chat and call from a character can be started/resumed from the same thread
- [ ] LLM is OpenAI-compatible — works with the official OpenAI API or a local server (e.g., `llama-server`)
- [ ] STT is fast and accurate for accented English (Spanish-accented English specifically)
- [ ] TTS supports two engines in v1: F5-TTS and XTTS v2, selectable per voice
- [ ] Voice Lab: upload a voice sample, STT auto-generates the reference transcript, user can edit and save the voice
- [ ] Character creator/editor supports the SillyTavern character-card field set plus a picture
- [ ] Character importer accepts SillyTavern v2 and v3 card formats (JSON and PNG-embedded)
- [ ] A character has a default voice, but each chat can override which voice is used
- [ ] Call memory uses a sliding-window of the chat's recent turns
- [ ] AI-generated audio is saved by default; user mic audio is off by default; both are togglable
- [ ] Three services run independently and connect over LAN: Web UI host, AI backend (STT/TTS/VAD), LLM server
- [ ] AI backend is optimized for an NVIDIA RTX 3060 (12 GB VRAM)

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

## Constraints

- **Hardware**: AI backend runs on a single NVIDIA RTX 3060 (12 GB VRAM) — STT, TTS, and VAD model choices must fit inside that budget simultaneously.
- **Latency**: End-to-end turn latency (user stops speaking → AI starts speaking) must be low enough to feel like a phone call — the entire stack is budgeted against this.
- **Topology**: Three endpoints (Web UI, AI backend, LLM) must be independently configurable and connectable over LAN. No assumption that they share a host.
- **LLM contract**: The LLM must be reachable via an OpenAI-compatible Chat Completions API (streaming).
- **Browsers**: Must work on modern mobile Safari and Chrome, including mic capture, output routing, and full-duplex streaming — not just desktop.
- **Language**: English only for STT and TTS in v1.
- **Tech stack**: No strong a-priori preference — research picks the stack.

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
| 3060 (12 GB) as the backend GPU target | Constrains model size choices across STT, TTS, and VAD | — Pending |
| Text chat and calls share one chat thread | "Continue a conversation" is the story, regardless of modality | — Pending |

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
