# RayMe Requirements

**Source**: Derived from `PROJECT.md` (Active requirements + Key Decisions + Constraints) cross-referenced against `.planning/research/FEATURES.md` (P1/P2/P3 prioritization) and `.planning/research/ARCHITECTURE.md`.

**Scoping decisions** (2026-04-17, confirmed by user):
- Full SillyTavern text-UX surface (Regenerate, Edit, Swipes, Alternate greetings, Continue) ships in v1 — the builder comes from ST muscle memory and these are table stakes for the text-chat half of the unified thread.
- Lorebook / world-info data from imported cards is **preserved but not injected** in v1 (no silent data loss; edit/injection = v1.x).
- PWA manifest + icons in v1 — the LAN-on-phone use case is core value, and add-to-home-screen is cheap.
- Character export: v2 JSON only in v1; v3 PNG export deferred to v1.x.

**Status legend**: `[v1]` = must ship. `[v1.x]` = add after v1 validates. `[v2+]` = future consideration.

---

## v1 — Must Ship

### Topology & Configuration

- **REQ-01** `[v1]` — The system runs as three independently-configurable services over LAN: Web UI host, AI backend (STT/TTS/VAD orchestrator), LLM server. No assumption of colocation.
  - *Source*: PROJECT.md Active + Key Decisions; constraints.
- **REQ-02** `[v1]` — The AI backend is a stateless real-time orchestrator targeting a single NVIDIA RTX 3060 (12 GB VRAM) with STT, VAD, and one resident TTS engine coexisting.
  - *Source*: PROJECT.md constraints; ARCHITECTURE.md VRAM coexistence.
- **REQ-03** `[v1]` — The LLM endpoint is reached via an OpenAI-compatible streaming Chat Completions API (works with official OpenAI API or a local `llama-server`). URL + optional API key + model name are user-configurable at runtime.
  - *Source*: PROJECT.md Active + constraints.
- **REQ-04** `[v1]` — The Web UI binds to `0.0.0.0` on LAN with no authentication. First-launch UX makes LAN-trust posture explicit.
  - *Source*: PROJECT.md Active + Key Decisions.
- **REQ-05** `[v1]` — Settings screen exposes per-endpoint configuration (Web UI → AI backend URL; Web UI → LLM URL + key + model) with a connection-test button per endpoint.

### Character Management

- **REQ-10** `[v1]` — Character Gallery shows all characters as a portrait grid with search-free listing, create-new entry, and per-card actions (edit / delete / export).
- **REQ-11** `[v1]` — Character Editor exposes the full SillyTavern v2 + v3 field set: name, description, personality, scenario, first message, example messages, system prompt, creator notes, character notes, tags, alternate greetings, post-history instructions, creator, character version, plus portrait upload/preview.
  - *Source*: PROJECT.md Active.
- **REQ-12** `[v1]` — Character CRUD: create, edit, delete with confirmation. Deleting a character must not orphan existing chat threads (soft delete or cascade-detach).
- **REQ-13** `[v1]` — Character importer accepts four inputs with format auto-detection: v2 JSON, v3 JSON, v2 PNG-embedded (`chara` tEXt chunk, base64 JSON), v3 PNG-embedded (`ccv3` tEXt chunk, base64 JSON, UTF-8). When a PNG contains both, v3 takes precedence.
  - *Source*: PROJECT.md Active.
- **REQ-14** `[v1]` — Character exporter produces v2 JSON files. (v3 PNG export = v1.x per scoping decision.)
- **REQ-15** `[v1]` — Each character has a default voice assigned from the Voice Library. Per-chat voice override shadows the character default without modifying the card.
  - *Source*: PROJECT.md Active + Key Decisions.
- **REQ-16** `[v1]` — Lorebook / world-info fields present on imported v2/v3 cards are **preserved in storage** but **not injected** into LLM context in v1. No silent data loss; the editor may display a read-only "Lorebook present — not used in v1" indicator.
  - *Source*: user scoping decision 2026-04-17.
- **REQ-17** `[v1]` — Alternate greetings: if a v3 card provides multiple first-messages, starting a new chat presents a picker. The card's `first_mes` remains the fallback.
  - *Source*: user scoping decision 2026-04-17.

### Voice Lab & Voice Library

- **REQ-20** `[v1]` — Voice Lab accepts a short audio sample upload (WAV / MP3 / FLAC). Recommended length 6–15 s, mono; warnings surfaced on clips outside that envelope.
  - *Source*: PROJECT.md Active.
- **REQ-21** `[v1]` — Uploaded samples are transcribed by the STT engine into an editable reference transcript. User can edit before saving — the stored transcript is what F5-TTS and Qwen3-TTS consume (XTTS v2 does not require a transcript, but the same editable transcript is still captured for portability between engines).
  - *Source*: PROJECT.md Active (F5 and Qwen3 require transcript, STT auto-generates).
- **REQ-22** `[v1]` — Voice save captures: name, engine (**F5-TTS**, **XTTS v2**, or **Qwen3-TTS** — user-selected per voice), sample audio path, reference transcript, timestamps. The Phase 0 measurements keep `F5-TTS` as the default, keep `XTTS v2` as the second engine, and include **Qwen3-TTS `0.6B-Base`** as an explicit opt-in builder override even though its acceptance gate failed on TTFA/RTF and accent approval. `1.7B` remains out of scope for v1 because FA2 did not install on Windows. See `.planning/research/QWEN3-TTS.md` §7 for the original gate criteria.
  - *Source*: PROJECT.md Active + Key Decisions; amended 2026-04-17 to add Qwen3-TTS.
- **REQ-23** `[v1]` — Voice Library supports list / rename / delete / test-play. Test-play synthesizes a stock phrase (and optional custom text) using the voice, routed to the configured output device.
- **REQ-24** `[v1]` — Deleting a voice that is referenced by a character default or chat override must not leave dangling references. Either cascade-reassign to a default or block with a clear error listing referents.

### Text Chat

- **REQ-30** `[v1]` — A chat thread is bound to (user, character, chat session) and renders a chronological message list with streaming LLM token output.
  - *Source*: PROJECT.md Active.
- **REQ-31** `[v1]` — Each thread persists the character's `first_mes` (or selected alternate greeting) as the opening AI message when the chat is created.
- **REQ-32** `[v1]` — **Regenerate last AI turn**: re-run the LLM against the previous user input; the old AI turn is replaced, not appended.
  - *Source*: user scoping decision 2026-04-17.
- **REQ-33** `[v1]` — **Edit previous turn**: inline-edit any prior user or AI message. On save, downstream turns become stale (visually flagged); user can choose to truncate-and-continue or keep.
  - *Source*: user scoping decision 2026-04-17. Also critical for correcting STT mis-transcriptions from call turns.
- **REQ-34** `[v1]` — **Swipes (branching alternates)**: generate N alternate responses for any AI turn; user swipes between them and picks one to continue the thread. The branching is stored such that alternates are retrievable but only the selected branch contributes to future context.
  - *Source*: user scoping decision 2026-04-17.
- **REQ-35** `[v1]` — **Continue**: if the composer (textbox) contains text when the user triggers Continue, the LLM is invoked with the composer content appended to the last AI message, resuming/extending that turn.
  - *Source*: user scoping decision 2026-04-17 (explicit user addition).
- **REQ-36** `[v1]` — The message list virtualizes once a thread exceeds ~500 messages. Jump-to-latest appears when the user has scrolled up.

### Voice Call (Full-Duplex)

- **REQ-40** `[v1]` — A call can be initiated from any chat thread (phone icon on thread header) or directly from a character card. The call inherits the thread's message history as LLM context.
  - *Source*: PROJECT.md Active.
- **REQ-41** `[v1]` — Call audio is **full-duplex**: the user's mic stream and the AI's TTS output stream run concurrently; the user can speak while the AI is speaking.
  - *Source*: PROJECT.md Active + Key Decisions. Load-bearing for core value.
- **REQ-42** `[v1]` — **VAD-driven barge-in**: speech detected on the user's mic during AI TTS playback cancels TTS playback, cancels the in-flight LLM generation, and begins a new STT turn. Barge-in is gated to avoid false triggers (minimum speech duration, minimum word count, playback-clock-aware window).
  - *Source*: PROJECT.md Active + Key Decisions; PITFALLS.md critical item.
- **REQ-43** `[v1]` — **Streaming STT with live user captions**: partial transcripts render within ~500 ms; final transcripts replace interim text. Interim vs final state is visually distinct (per DESIGN.md Transcription Chips).
  - *Source*: PROJECT.md Active.
- **REQ-44** `[v1]` — **Streaming LLM with live AI captions**: tokens render in real time as the LLM produces them, ahead of TTS playback.
  - *Source*: PROJECT.md Active.
- **REQ-45** `[v1]` — **Streaming/chunked TTS playback for every engine**: the orchestrator uses a shared chunk planner for all TTS engines. It must prefer natural sentence boundaries, enforce engine-specific token/character caps (for example XTTS `inference_stream` must never receive a segment at or above its 400-token limit), avoid tiny unnatural fragments, start playback from the first viable chunk, stitch later chunks cleanly, and log first-chunk TTFA, total stitched playback time, and inter-chunk gaps. Engines with native streaming use it inside each safe chunk; engines without native streaming still use chunked playback instead of waiting for full-response synthesis.
  - *Source*: ARCHITECTURE.md; FEATURES.md differentiators; PITFALLS.md critical item (F5 lacks native streaming); Phase 0 TTS matrix follow-up 2026-04-23.
- **REQ-46** `[v1]` — End-to-end turn latency (user finishes speaking → AI starts speaking) is targeted at **<800 ms** (stretch: <500 ms). This is a design budget, not a blocking acceptance gate — Phase 0 measurement sets the achievable floor.
  - *Source*: PROJECT.md constraints; FEATURES.md differentiators.
- **REQ-47** `[v1]` — Call toolbar provides: mute (must also stop server-side audio consumption, not just silence locally), end-call (unambiguous destructive affordance), audio input device picker, audio output device picker.
- **REQ-48** `[v1]` — A call mic-permission prompt surfaces on first call attempt. Denial surfaces a clear explanation and retry affordance.
- **REQ-49** `[v1]` — **Voice Visualizer** shows three explicit states: listening (pulse waveform driven by user mic RMS), thinking (indeterminate shimmer), speaking (waveform driven by AI TTS output). Per DESIGN.md §5.
  - *Source*: PROJECT.md Active design reference; FEATURES.md table stakes.
- **REQ-50** `[v1]` — Call-end state persists a call-summary row in the thread: duration, character, voice used, start/end timestamps. The user drops back into the thread's text composer.

### Unified Thread

- **REQ-60** `[v1]` — A thread's message store holds both typed messages and call transcripts in a single table, keyed by a `message_kind` discriminator (`user_text` | `ai_text` | `user_speech` | `ai_speech` | `call_start` | `call_end`). Rendering is strictly chronological.
  - *Source*: PROJECT.md Active + Key Decisions; FEATURES.md dependency note.
- **REQ-61** `[v1]` — Call turns are visually distinct from text turns in scrollback (e.g., left-rail accent, grouped under a collapsible "Call — Nm Ns" header per DESIGN.md).
- **REQ-62** `[v1]` — AI call audio is saved per turn by default (user-togglable). A play button on each AI speech turn replays the saved audio inline. Mic audio is NOT saved by default (user-togglable).
  - *Source*: PROJECT.md Active + Key Decisions (privacy defaults).
- **REQ-63** `[v1]` — Call memory uses a **sliding window** of the thread's most recent turns (both text and call transcripts). No summarization in v1.
  - *Source*: PROJECT.md Active + Key Decisions.

### Home & Thread Management

- **REQ-70** `[v1]` — Home screen surfaces a threads list sorted by most-recent activity, each row showing character portrait, character name, last-message snippet, and relative timestamp.
- **REQ-71** `[v1]` — Threads support rename and delete.
- **REQ-72** `[v1]` — From Home, users can start a new chat with any character (entry point to Character Gallery).

### Settings

- **REQ-80** `[v1]` — Settings consolidates: three-endpoint configuration + tests (REQ-05); STT model dropdown (when multiple loaded); TTS engine default (**F5 / XTTS / Qwen3-TTS** — per-voice still overrides; Qwen3-TTS is present but should be labeled as a non-default/experimental `0.6B-Base` path because Phase 0 did not clear it for default use); VAD sensitivity slider (threshold + end-of-utterance silence duration); default audio input/output device; save-AI-audio toggle (default ON); save-mic-audio toggle (default OFF); clear-all-data danger zone.
  - *Source*: PROJECT.md Active + constraints.

### Design System

- **REQ-90** `[v1]` — UI implements the "Ethereal Core / True Dark" design system from `docs/stitch/DESIGN.md` — glassmorphism, no-line rule, Voice Visualizer, Transcription Chips, and the canonical screen inventory (Home, Voice Lab, Character Gallery, Character Editor, Voice Call, Settings). Deviations allowed only when functional needs demand.
  - *Source*: PROJECT.md Active + Key Decisions.

### Platform

- **REQ-A0** `[v1]` — The Web UI is fully usable from a mobile browser on LAN: Chrome on Android. Mic capture, output routing, and full-duplex audio work on the builder's phone.
  - *Source*: PROJECT.md Active + constraints.
- **REQ-A1** `[v1]` — The Web UI is served over HTTPS with a trusted certificate on LAN (mobile-device trust workflow documented on the Settings/first-launch screen). Mobile mic capture requires HTTPS; this is non-negotiable.
  - *Source*: PITFALLS.md critical item; FEATURES.md mobile dependency note.
- **REQ-A2** `[v1]` — PWA manifest + icons + `theme-color` are served so that "Add to Home Screen" on Android produces a standalone-launcher experience. Full offline-shell polish is v1.x; the manifest itself is v1.
  - *Source*: user scoping decision 2026-04-17.
- **REQ-A3** `[v1]` — English-only STT and TTS in v1. Spanish-accented English is a quality bar for STT — Phase 0 measures WER on the builder's voice to confirm model selection.
  - *Source*: PROJECT.md Active + Key Decisions + constraints.

---

## v1.x — Add After v1 Validates

- **REQ-100** `[v1.x]` — Character v3 PNG export (tEXt chunk injection).
- **REQ-101** `[v1.x]` — Lorebook / world-info editor + injection into LLM context (v1 preserves only).
- **REQ-102** `[v1.x]` — Waveform scrubber on saved AI audio replay (v1 = play button only).
- **REQ-103** `[v1.x]` — Thread search.
- **REQ-104** `[v1.x]` — Character Gallery search + tag filtering.
- **REQ-105** `[v1.x]` — Call export as single mixed WAV (v1 stores per-turn files).
- **REQ-106** `[v1.x]` — Per-thread LLM sampling-parameter override.
- **REQ-107** `[v1.x]` — PWA offline-shell polish + lock-screen call styling hints.

## v2+ — Future Consideration

- **REQ-200** `[v2+]` — Summarization-based long-term memory (v1 = sliding window per REQ-63).
- **REQ-201** `[v2+]` — Multilingual STT/TTS beyond English.
- **REQ-202** `[v2+]` — End-to-end speech-to-speech model option (Nemotron / PersonaPlex) as alternative pipeline (breaks the three-service architecture — requires re-scoping).
- **REQ-203** `[v2+]` — Optional auth / beyond-LAN deployment preset.
- **REQ-204** `[v2+]` — RVC-style voice-conversion post-processing pass.
- **REQ-205** `[v2+]` — Emotion/style reference swapping mid-call.

## Explicitly Out of Scope (from PROJECT.md — do not re-add)

Multi-user / auth; native mobile apps; avatars / lip-sync / video; managed TTS/STT APIs (ElevenLabs, OpenAI Realtime, Deepgram); tool-using agent characters; cloud / internet-facing hosting; built-in LLM inference server; group calls; in-call text messaging; push notifications; content moderation / NSFW filter; voice marketplace.

---

## Requirements → PROJECT.md Active Coverage

Every Active bullet in PROJECT.md maps to one or more REQ-IDs. Dropped bullets or scope cuts must update PROJECT.md first.

| PROJECT.md Active | Covered by |
|---|---|
| Web app works on phone + desktop browsers over LAN | REQ-04, REQ-A0, REQ-A1 |
| No authentication — LAN-level trust | REQ-04 |
| English-only v1 | REQ-A3 |
| A chat thread holds typed + call transcripts interleaved | REQ-30, REQ-60, REQ-61 |
| Calls run full-duplex with barge-in via VAD | REQ-41, REQ-42 |
| Live captions during a call (user STT + AI response) | REQ-43, REQ-44 |
| Text chat and call startable/resumable from same thread | REQ-40, REQ-50, REQ-60 |
| LLM is OpenAI-compatible | REQ-03 |
| STT fast and accurate for accented English | REQ-43, REQ-A3 |
| TTS supports F5-TTS, XTTS v2, and Qwen3-TTS (Phase-0-conditional), selectable per voice | REQ-22 |
| Voice Lab: upload → auto-transcript → editable → save | REQ-20, REQ-21, REQ-22 |
| Character creator/editor supports SillyTavern fields + picture | REQ-11 |
| Importer accepts v2 + v3 JSON and PNG-embedded | REQ-13 |
| Character has default voice, per-chat override allowed | REQ-15 |
| Call memory = sliding window of recent turns | REQ-63 |
| AI audio saved by default; mic off by default; togglable | REQ-62, REQ-80 |
| Three independent services over LAN | REQ-01, REQ-05 |
| AI backend optimized for RTX 3060 (12 GB) | REQ-02 |
| UI follows Ethereal Core / True Dark in `docs/stitch/` | REQ-90 |
| Screen inventory matches Stitch canonical set | REQ-90 |

---

*Requirements defined 2026-04-17, after research synthesis and scoping confirmation. Next: roadmap.*
