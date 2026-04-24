# RayMe Roadmap

**Version:** v1
**Granularity:** Standard (7 phases)
**Created:** 2026-04-17
**Sources:** `PROJECT.md`, `REQUIREMENTS.md`, `research/SUMMARY.md`, `research/STACK.md`, `research/ARCHITECTURE.md`, `research/PITFALLS.md`

---

## Executive Summary

RayMe ships in **seven phases**: one measurement spike (Phase 0) followed by six delivery phases that culminate in a full-duplex, barge-in-capable voice-call app usable from a mobile browser on LAN. The load-bearing core value — "call feel" — is validated **twice**: first as an MVP call in Phase 3 (flat, one-sentence reply, no streaming) and then as a tuned duplex experience in Phase 4 (sentence-streamed TTS, VAD barge-in with LLM cancel, live bidirectional captions). Everything after Phase 4 exists to broaden (up to three TTS engines — F5-TTS, XTTS v2, and Qwen3-TTS — with cold-swap UX, unified thread polish) and harden (mobile hardening, ship polish) what Phase 4 proves works.

## v1 Milestone Definition

### What's in v1

The v1 milestone delivers every requirement marked `[v1]` in `REQUIREMENTS.md`. This includes:

- Three-service topology (Web UI host, AI backend, LLM endpoint), independently configurable over LAN.
- Mobile-browser support over HTTPS with a trusted cert workflow (Android Chrome on LAN).
- Full SillyTavern character management: v2/v3 import (JSON + PNG), v2 JSON export, CRUD, full editor field set, per-character default voice, alternate-greeting picker, lorebook preserved-not-injected.
- Voice Lab with STT-auto-transcribed reference, three TTS engines (F5-TTS, XTTS v2, Qwen3-TTS — the last Phase-0-conditional), test-play, library management.
- Unified thread: single messages table with `message_kind` discriminator; text and call turns interleave chronologically.
- SillyTavern text-UX parity: Regenerate, Edit, Swipes, Continue, virtualized long threads.
- Full-duplex voice calls with VAD-driven barge-in, sentence-streamed TTS, streaming STT with live captions, streaming LLM with live AI captions, Voice Visualizer three-state, call-end summary row.
- Per-chat voice override on top of per-character default.
- AI audio saved per turn by default; mic audio off by default; both togglable in Settings.
- PWA manifest + icons for add-to-home-screen on Android.
- Settings with three-endpoint config + connection tests, VAD sensitivity, device defaults, save-audio toggles, clear-data.
- Ethereal Core / True Dark design system applied across the canonical Stitch screen set.

### What's explicitly deferred

- **v1.x:** v3 PNG export, lorebook injection, waveform scrubber on saved audio, thread search, gallery search/tag filters, mixed-WAV call export, per-thread LLM sampling overrides, full PWA offline-shell polish.
- **v2+:** Summarization memory, multilingual, speech-to-speech models, optional auth / beyond-LAN, RVC post-processing, emotion/style swap mid-call.
- **Out of scope permanently:** Multi-user, native mobile apps, video/avatar, managed cloud TTS/STT, tool-using agents, built-in LLM inference, cloud deployment.

### Single acceptance statement

**v1 ships when the builder can, on their Android phone over LAN with a mkcert-trusted cert and a Bluetooth headset connected, import a SillyTavern v3 PNG card, record a voice in Voice Lab, assign that voice as the character default, start a call from a chat thread, have a back-and-forth conversation with mid-sentence barge-in that feels like a phone call, and later reopen the same thread on desktop to see the call transcripts interleaved with any prior text messages.**

---

## Phases

- [ ] **Phase 0: Measurement Gate** — 2–3 day spike that validates VRAM, STT WER, TTS TTFA, HTTPS-on-Android, and FA2 viability before Phase 1 freezes stack commitments.
- [x] **Phase 1: Foundations & Text Chat** — Three-service skeleton with HTTPS, the unified `messages` schema, SillyTavern card CRUD + import/export, and full-featured text chat end-to-end against a streaming LLM.
- [x] **Phase 01.1: UI Acceptance & Regression Test Hardening** — Inserted verification pass to convert manually discovered Phase 1 UI regressions into durable Playwright/API coverage before Phase 2.
- [ ] **Phase 2: AI Backend Skeleton & Voice Lab** — FastAPI + aiortc signaling, resident Whisper + Silero VAD + one-hot TTS engine on the GPU, Voice Lab upload → auto-transcript → edit → synth-preview → save, Settings with three-endpoint connection tests.
- [ ] **Phase 3: First Working Call (MVP)** — Voice Call screen with `RTCPeerConnection`, AudioContext gesture unlock, orchestrator FSM skeleton, one-sentence non-streaming reply. Proves the media plumbing end-to-end.
- [ ] **Phase 4: Call Feel** — Sentence-chunked streaming TTS, VAD-driven barge-in with LIFO cancel and mid-stream LLM abort, live bidirectional captions over data channel, echo-loop mitigation, Voice Visualizer three-state. The core-value phase.
- [ ] **Phase 5: Voice Breadth & Unified Thread Polish** — Both TTS engines with cold-swap UX, per-character default + per-chat override, saved-audio toggles + inline replay, unified thread visual treatment, full SillyTavern text-UX parity (Regenerate / Edit / Swipes / Continue / alternate greetings / virtualization).
- [ ] **Phase 6: Mobile Hardening & Ship Polish** — Full Android Chrome pass (Bluetooth routing, Wake Lock, visibility change), PWA manifest + icons, storage housekeeping (orphan reaper, retention), full Settings surface, error states, soak-test acceptance. v1 ships.

---

## Phase Details

### Phase 0: Measurement Gate

**Goal:** Answer the five open empirical questions that determine whether Phase 1+ defaults are the right ones, before any production code is committed.

**Depends on:** Nothing.

**Requirements delivered:** None from the REQ set (this is a spike — outputs become Key Decisions in `PROJECT.md`, not shipped features). Establishes the empirical baseline for REQ-02, REQ-45, REQ-46, REQ-A1, REQ-A3.

**Pitfalls owned:**
- **#2 HTTPS / cert trust on mobile** — mkcert root CA installed on the builder's Android phone, `https://rayme.local` loads in Chrome, reproducible doc produced.
- **#7 VRAM budget on 12 GB** — 30-minute soak with Whisper + Silero + each of the three TTS engines (F5, XTTS, Qwen3-TTS 0.6B-Base) under realistic cycling, peak tracked per engine.
- Informs **#4 F5 streaming** (first-sentence TTFA measured), **#5/#6 Whisper WER on Spanish-accented English** (default STT rung picked from measurement), and **Qwen3-TTS acceptance gate** (TTFA + RTF + accent-preservation + FA2-Windows install — see `.planning/research/QWEN3-TTS.md` §7).

**Success criteria** (observable, testable):
1. The builder can load `https://rayme.local` on their Android phone with no cert warnings and `window.isSecureContext === true`, following a documented one-time setup procedure.
2. A measurement rig has logged WER, latency, and peak VRAM for `distil-large-v3 INT8`, `large-v3-turbo INT8`, and `large-v3 FP16` on a 10-minute read-aloud of the builder's Spanish-accented English voice, and the team has picked a default rung.
3. **TTS TTFA on the actual 3060** measured for: (a) F5-TTS with 7-step Sway sampling on a 3–5 word acknowledgment; (b) XTTS v2 first-chunk streaming; (c) Qwen3-TTS 0.6B-Base with the actual attention backend explicitly labeled (`eager`, `sdpa`, or `flash_attention_2` when available). If F5 TTFA >400 ms, XTTS or Qwen3-TTS is promoted to the v1 default (Resolved Tension #3 trigger). **Qwen3-TTS acceptance gate**: promoted to v1 third-engine status if TTFA <400 ms AND RTF <1 AND 30-min soak <11 GB AND builder's subjective listening test on Spanish-accented-English clone is acceptable; otherwise feature-flagged off for v1.
4. A 30-minute cycling soak test of `{Whisper default + Silero + one TTS engine}` stays under 11 GB peak VRAM and shows no unbounded growth — run once per engine: F5, XTTS, Qwen3-TTS 0.6B-Base (and 1.7B-Base if FA2 installs cleanly on Windows).
5. **FlashAttention 2 install verified** on the builder's Windows 11 + Python 3.11/3.12 + CUDA 12.1 + RTX 3060 (Ampere sm_86). If install fails, Qwen3-TTS adoption is restricted to 0.6B-Base only (1.7B without FA2 blows the VRAM budget).

**Plans:** 9 plans
- [ ] 00-01-wave0-setup-PLAN.md - Python 3.11 venv, pinned Phase 0 packages, Whisper weight cache, probes/ scaffolding + bench_utils (Wave 1)
- [ ] 00-02-https-android-PLAN.md - HTTPS on Android via mkcert on LAN, reproducible doc (Wave 2)
- [ ] 00-03-whisper-wer-PLAN.md - Whisper WER/latency/VRAM across 3 rungs on builder voice, pick default rung (Wave 2)
- [ ] 00-04-tts-ttfa-PLAN.md - F5/XTTS/Qwen3 TTFA+RTF, Qwen3 accent gate, pick v1 default (Wave 2)
- [ ] 00-05-vram-soak-PLAN.md - 30-min VRAM soak per TTS engine F5/XTTS/Qwen3-0.6B (Wave 2)
- [ ] 00-07-fa2-install-PLAN.md - FlashAttention 2 install verification (gates Qwen3-1.7B eligibility) (Wave 2)
- [ ] 00-07.1-attention-backend-matrix-PLAN.md - Benchmark per-engine optimization backends (`eager` / `sdpa` / `flash_attention_2` where supported) and separate no-FA2 baselines from optimized runs before final TTS writeback (Wave 3) (INSERTED)
- [ ] 00-07.2-runtime-acceleration-matrix-PLAN.md - Benchmark the omitted cross-runtime TTS matrix: native Windows, WSL Python, WSL Triton, XTTS DeepSpeed, and Qwen eager vs FlashAttention 2 before final writeback (Wave 3) (INSERTED)
- [ ] 00-08-synthesis-writeback-PLAN.md - Key Decisions roll-up + PROJECT.md/STATE.md writeback (Wave 4)

**UI hint:** no

**Scope signal:** S–M (3–4 days wall time; one-person spike — expanded from 2–3 days with the Qwen3-TTS acceptance-gate measurements added 2026-04-17).

---

### Phase 1: Foundations & Text Chat End-to-End

**Goal:** Stand up the three-service skeleton on HTTPS and deliver a full-featured text-chat loop against the streaming LLM, with the unified `messages` schema committed on day one so nothing migrates later.

**Depends on:** Phase 0 (HTTPS path proven, stack defaults frozen).

**Requirements delivered:** REQ-01, REQ-03, REQ-04, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-16, REQ-17, REQ-30, REQ-31, REQ-32, REQ-33, REQ-34, REQ-35, REQ-36, REQ-60, REQ-70, REQ-71, REQ-72, REQ-90 (partial: design tokens + Home + Gallery + Editor screens), REQ-A0 (partial: desktop + mobile text-chat reachability), REQ-A1.

**Pitfalls owned:**
- **#2 HTTPS / cert trust** — shipped cert workflow, first-launch precheck of `window.isSecureContext`.
- **#14 Card XSS** — sanitized Markdown renderer + CSP from the first import.
- **#15 v2/v3 card parse** — both formats + both tEXt keys (`ccv3` preferred, `chara` fallback); corpus test.
- **#16 CORS / WS origin** — explicit allow-list across the three-service topology.
- **#17 0.0.0.0 over-exposure** — bind to specific LAN interface, documented.
- **#18 Framework vs Stitch import** — SvelteKit chosen, first Stitch screen ported in <1 day as acceptance.
- **#20 Audio storage atomicity (pattern only, no audio yet)** — establish the atomic-temp-rename + orphan-reaper pattern for avatars now, audio reuses it later.

**Success criteria** (observable, testable):
1. The builder can hit `https://rayme.local` from both desktop Chrome and Android Chrome on LAN; the three services (Web UI host, AI-backend health stub, LLM server) each answer `/health` and the Web UI Settings screen shows connection-test green for each.
2. The builder can import a SillyTavern character card in any of four formats (v2 JSON, v3 JSON, v2 PNG, v3 PNG), see it in the Gallery with a portrait, open it in the Editor with all v2+v3 fields populated and a "Lorebook present — not used in v1" indicator where applicable, and export it back out as v2 JSON.
3. The builder can start a new chat with an imported character, see its `first_mes` (or pick an alternate greeting from the v3 picker) as the opening AI turn, send a typed message, and watch the LLM reply stream in token-by-token.
4. On any AI turn the builder can Regenerate, Edit (with downstream-stale flagging and truncate-or-keep choice), Swipe across N alternates, or Continue the turn using composer content — and stored messages round-trip through the unified `messages` table with a `kind` discriminator that can distinguish `user_text` / `ai_text` / `user_speech` / `ai_speech` / `call_start` / `call_end` (the last three still unused but schema-ready).
5. A malicious character card containing `<img src=x onerror=alert(1)>` in its description renders as plain text with no script execution, verified by import + render test.

**Plans:** 24 plans

Plans:
- [x] 01-01-PLAN.md - Backend project harness and app factory (Wave 1)
- [x] 01-02-PLAN.md - Backend chat/schema/message-action contracts, including LLM-backed action tests (Wave 2)
- [x] 01-03-PLAN.md - Backend card/character/settings contracts (Wave 2)
- [x] 01-04-PLAN.md - Card parser fixtures and malicious payload corpus (Wave 2)
- [x] 01-05-PLAN.md - SvelteKit static client scaffold (Wave 1)
- [x] 01-06-PLAN.md - Sanitizer boundary and Playwright acceptance shells (Wave 2)
- [x] 01-07-PLAN.md - AI-backend health stub, external LLM docs/config, and LAN HTTPS examples (Wave 1)
- [x] 01-08-PLAN.md - Wave 0 validation marker and initial SQLite/Alembic schema (Wave 3)
- [x] 01-09-PLAN.md - Atomic blob storage and orphan reaper (Wave 3)
- [x] 01-10-PLAN.md - Web host config, CORS/CSP, static serving, and HTTPS runner (Wave 4)
- [x] 01-11-PLAN.md - Web health and Settings connection-test APIs (Wave 5)
- [x] 01-12-PLAN.md - Character card import/export, CRUD, lorebook preservation, and portrait storage (Wave 4)
- [x] 01-13-PLAN.md - Thread APIs, opening greetings, and full thread hydration (Wave 5)
- [x] 01-14-PLAN.md - Prompt builder and streaming LLM proxy with full SSE done-message shape (Wave 6)
- [x] 01-15-PLAN.md - LLM-backed Regenerate, Swipes, Edit stale handling, and Continue (Wave 7)
- [x] 01-16-PLAN.md - True Dark client shell and shared UI primitives (Wave 2)
- [x] 01-17-PLAN.md - Client API wrappers, stream reader, and browser readiness helpers (Wave 2)
- [x] 01-18-PLAN.md - Home threads dashboard (Wave 6)
- [x] 01-19-PLAN.md - Character Gallery import flow and cards (Wave 5)
- [x] 01-20-PLAN.md - Character Editor and Settings screens (Wave 6)
- [x] 01-21-PLAN.md - Chat route hydration, composer, and streaming send UI (Wave 7)
- [x] 01-22-PLAN.md - Chat message actions, generated swipes, stale flags, and continue UI (Wave 8)
- [x] 01-23-PLAN.md - Chat virtualization, jump-to-latest, and mobile layout coverage (Wave 9)
- [x] 01-24-PLAN.md - Full automated acceptance, HTTPS/mobile runbooks, and Android Chrome checkpoint (Wave 10)

**UI hint:** yes

**Scope signal:** L (the largest phase by surface area — full text-UX, full card CRUD, full schema).

---

### Phase 01.1: UI acceptance and regression test hardening (INSERTED)

**Goal:** Turn the Phase 1 UI defects found during live LAN/Android acceptance into durable automated coverage, then re-run the full Phase 1 browser acceptance path before Phase 2 planning begins.

**Depends on:** Phase 1 plan 01-24 discovery work.

**Requirements delivered:** Verification hardening for REQ-03, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-16, REQ-17, REQ-30, REQ-31, REQ-32, REQ-33, REQ-34, REQ-35, REQ-36, REQ-60, REQ-70, REQ-71, REQ-72, REQ-90, REQ-A0, REQ-A1.

**Pitfalls owned:**
- User manual testing is product-owner acceptance, not first-line QA; the agent must run backend/API/browser/deployed checks first.
- UI behavior must be browser-verified by the agent before asking for physical-device testing.
- Settings connection tests must use the currently configured form values, not stale persisted defaults.
- Portrait upload/import must prove image persistence through editor, gallery, home picker, chat header, reload, and live backend deployment.
- Local LLM endpoints remain configurable through Settings; no code hardcoding of `192.168.1.190:8001` or any other local endpoint.

**Success criteria** (observable, testable):
1. Playwright E2E tests cover PNG import portrait persistence, direct portrait upload persistence, reload persistence, gallery/home/chat portrait rendering, and deletion/replacement behavior.
2. Playwright E2E tests cover Settings save-before-test behavior for Web UI, AI backend, and LLM, including an OpenAI-compatible local LLM with no API key.
3. Playwright E2E tests cover the full Phase 1 user path: import/create/edit character, start chat, alternate greeting, stream reply, regenerate, swipe, continue, reload, and continue again.
4. Live LAN verification against `OMEN-PC` is browser-checked before the user is asked to test Android Chrome.
5. Any request for user manual testing includes a concise statement of what the agent already verified and what product-owner signal is still needed.
6. Phase 1 `01-24-SUMMARY.md` is created only after the hardened acceptance suite and Android checkpoint pass.

**Plans:** 6 plans

Plans:
- [x] 01.1-01-PLAN.md - Shared Playwright acceptance helper and fixture foundation (Wave 0)
- [x] 01.1-02-PLAN.md - Portrait persistence E2E coverage for import, upload, replacement, removal, and reload (Wave 1)
- [x] 01.1-03-PLAN.md - Settings save-before-test and local no-key LLM E2E coverage (Wave 1)
- [x] 01.1-04-PLAN.md - Guarded full Phase 1 browser acceptance path and existing E2E guard integration (Wave 2)
- [x] 01.1-05-PLAN.md - Live OMEN-PC functional browser checks and Android product-owner checkpoint (Wave 3)
- [x] 01.1-06-PLAN.md - Phase 1 plan 01-24 summary gate after Android approval (Wave 4)

**UI hint:** yes

**Scope signal:** S-M (focused verification and regression hardening, not new product scope).

### Phase 2: AI Backend Skeleton & Voice Lab

**Goal:** Get the AI backend models resident on GPU behind the correct topology — STT, VAD, and one-hot TTS — and deliver Voice Lab end-to-end so that a call in Phase 3 has a voice to speak in.

**Depends on:** Phase 01.1 (Phase 1 UI acceptance hardened and Android/LAN checkpoint complete).

**Requirements delivered:** REQ-02, REQ-05, REQ-15 (schema + default-voice UI; in-call usage verified in Phase 3), REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-80 (partial: three-endpoint config + connection tests + save-audio toggles stored; VAD slider wired in Phase 4), REQ-A3 (STT default frozen from Phase 0 measurement), REQ-90 (partial: Voice Lab + Settings screens ported).

**Pitfalls owned:**
- **#6 Whisper hallucinations** — VAD-gated input + `condition_on_previous_text=False` + hallucination blocklist.
- **#7 VRAM budget** — exactly one TTS engine resident, documented hot-swap registry for the full measured roster (`F5-TTS`, `XTTS v2`, `Qwen3-TTS 0.6B-Base`, `LuxTTS`, `Chatterbox Turbo`, `TADA 1B`), `expandable_segments` CUDA allocator config, startup self-test asserts headroom per engine.
- **#9 F5 transcript error** — Voice Lab forces an editable-transcript step and offers synth-preview as a convenience, but save does not require a successful preview. (Same editable transcript is captured for Qwen3-TTS voices, which also require a reference transcript; XTTS does not require one but still stores it for portability.)
- **#12 Coqui abandonware** — `coqui-tts` idiap fork pinned; never `TTS`. (Qwen3-TTS is the medium-term v1.x fallback if idiap fork stalls.)
- **#13 Non-commercial licenses** — `LICENSES.md` shipped with F5 (CC-BY-NC) + XTTS (CPML) non-commercial notices and a **Qwen3-TTS Apache-2.0** entry (the only commercially-permissive engine; activates if RayMe ever pivots past PROJECT.md's non-commercial scope).
- **Qwen3-TTS install friction** — backend bringup script verifies `qwen-tts==0.1.1` load and FlashAttention 2 availability; falls back to 0.6B-Base without FA2 if the install fails. Pinned dependency prevents 0.2.x breaking upgrades.

**Success criteria** (observable, testable):
1. The AI backend boots, loads Whisper (Phase 0 default) + Silero VAD + one TTS engine (default per Phase 0 outcome — F5, XTTS, or Qwen3-TTS 0.6B-Base), and reports GPU residency < 11 GB in its `/health` response; the Web UI Settings screen shows all three endpoints green on connection-test.
2. The builder can upload a 6–15 s WAV/MP3/FLAC voice sample in Voice Lab, see an auto-generated reference transcript appear within a few seconds or enter one manually after STT failure, edit it inline, pick any available engine from the full measured roster, optionally preview a stock phrase, and save the voice with a name without a preview gate.
3. The Voice Library lists all saved voices and supports rename, delete with explicit force-delete handling for referents, and test-play with custom text.
4. Assigning a voice as a character's default in the Character Editor persists the stable voice ID and surfaces in the Gallery; deleting a referenced voice surfaces `Voice unavailable` without crashing or silently clearing the reference.
5. Settings exposes save-AI-audio (default ON) and save-mic-audio (default OFF) toggles, VAD threshold/end-of-utterance values marked as Call Feel-owned behavior, and compact AI backend status with resident engine, available engines, loading state, and VRAM/headroom.

**Plans:** 18 plans

Plans:
- [ ] 02-01-PLAN.md — Wave 0 Web UI server voice/schema/settings validation scaffolding
- [ ] 02-02-PLAN.md — Wave 0 AI backend model/STT/TTS validation scaffolding
- [ ] 02-03-PLAN.md — Wave 0 client Voice Lab, Settings, and live E2E validation scaffolding
- [ ] 02-04-PLAN.md — Web UI voice schema, migration, and sample-asset storage
- [ ] 02-05-PLAN.md — Web UI AI backend client and status bridge
- [ ] 02-06-PLAN.md — AI backend config, model manager, lifespan, and health residency payload
- [ ] 02-07-PLAN.md — AI backend STT/VAD processing and transient transcription API
- [ ] 02-08-PLAN.md — AI backend TTS registry, adapters, switching, and transient synthesis API
- [ ] 02-09-PLAN.md — Web UI voice domain/API for upload, transcribe, save, library, delete, and test-play
- [ ] 02-10-PLAN.md — Web UI Settings service/API for save-audio, VAD values, and AI backend status
- [ ] 02-11-PLAN.md — Character default voice server persistence and unavailable state
- [ ] 02-12-PLAN.md — Client Voice Lab creation flow with six-engine picker and optional preview
- [ ] 02-13-PLAN.md — Client Voice Library list, rename, delete, and test-play
- [ ] 02-14-PLAN.md — Client Settings panels and Voice Lab navigation
- [ ] 02-15-PLAN.md — Character Editor/Gallery default voice assignment and badges
- [ ] 02-16-PLAN.md — License, runtime evidence, Voice Lab, and LAN runbook documentation
- [ ] 02-17-PLAN.md — Non-call aiortc signaling skeleton
- [ ] 02-18-PLAN.md — Full local, live OMEN-PC, and Android product-owner acceptance

**UI hint:** yes

**Scope signal:** M.

---

### Phase 3: First Working Call (MVP)

**Goal:** Establish the media plumbing end-to-end — browser `RTCPeerConnection` to aiortc, AudioContext unlocked correctly on Android, orchestrator FSM skeleton, a single-sentence non-streaming reply — so that the harder semantics of Phase 4 layer on known-working transport.

**Depends on:** Phase 2 (voices exist, one TTS engine is warm, STT resident). Phase 1 (threads + characters exist).

**Requirements delivered:** REQ-40, REQ-47 (start/end/mute/device pickers at MVP fidelity), REQ-48, REQ-49 (partial: state transitions wired; full three-state visual polish in Phase 4), REQ-50, REQ-63 (sliding-window hydration at call start), REQ-A0 (call loop verified on both desktop and mobile at MVP fidelity).

**Pitfalls owned:**
- **#3 AudioContext gesture unlock** — canonical idiom (create/resume inside tap, play 1-sample silent buffer), `statechange` handler for foreground resume.
- **#11 TTS/user-turn boundary race (foundation)** — end-to-end timing instrumentation added to every call-session object (shared clock); exercised in Phase 4.
- **#24 Mobile parity** — Android Chrome on the builder's phone is in every acceptance check from this phase onward.

**Success criteria** (observable, testable):
1. The builder can tap "Call" on a chat thread on desktop Chrome, grant mic permission on first attempt, hear a clear AI response read out by the assigned voice, and end the call; a `call_start` + one `user_speech` turn + one `ai_speech` turn + `call_end` row are written to the unified `messages` table with a call-summary row rendering in the thread.
2. The same flow works on Android Chrome: mic permission prompt surfaces, AudioContext unlocks on the Start-Call tap with `state === 'running'` verified, TTS audio plays through `<audio>` / `MediaStreamAudioDestinationNode`.
3. Muting on the call toolbar stops server-side audio consumption (not just local silencing), verified by inspecting server logs for incoming frame-rate drop.
4. Ending a call drops the user back into the thread's text composer with the call-summary row visible in scrollback.
5. A 5-minute call on desktop speakers does not exhibit catastrophic behavior (no ping-pong, no uncaught exceptions); call-feel polish is Phase 4's job, but the loop holds.

**Plans:** TBD

**UI hint:** yes

**Scope signal:** M.

---

### Phase 4: Call Feel (the load-bearing phase)

**Goal:** Turn the Phase-3 MVP call into something that actually feels like a phone call: streaming TTS with <500 ms TTFA target, VAD-driven barge-in with LIFO cancel that reaches the GPU, live bidirectional captions, echo-loop mitigated on laptop speakers. This phase is the reason the product exists.

**Depends on:** Phase 3 (media plumbing, FSM skeleton, timing instrumentation in place).

**Requirements delivered:** REQ-41, REQ-42, REQ-43, REQ-44, REQ-45, REQ-46, REQ-49 (full three-state Voice Visualizer), REQ-61 (call turns visually distinct in scrollback), REQ-80 (VAD sensitivity slider wired end-to-end).

**Pitfalls owned:**
- **#1 Echo loop** — TTS routed through `<audio>` / `MediaStreamAudioDestinationNode` so browser AEC sees the reference; server-side playback gate keyed to the TTS sample-accurate timeline.
- **#4 TTS streaming/chunking across engines** — shared chunk planner on the LLM token stream; native streaming where available, chunked playback where not; enforce engine-specific limits such as XTTS's 400-token stream cap; system-prompt bias toward short acknowledgments.
- **#5 STT endpointing** — Silero VAD endpoint with tuned silence window (500–700 ms default, adaptive shrink during AI playback for aggressive barge-in).
- **#8 LLM mid-stream cancel** — verified GPU-drop on barge-in via `nvidia-smi`; wasted-token-count logged per cancel.
- **#10 False barge-in** — minimum-duration (≥250–400 ms) + word-count (≥1 confident word) + energy-threshold gates before cancel fires; optional TTS ducking as a first tier.
- **#11 TTS/user-turn race** — perceived-playback-end clock from browser; server-side VAD suppression during jitter-buffer tail.
- **#23 Sentence boundary extraction / chunk planning** — abbreviation-aware splitter (`Dr.` `Mr.` `i.e.` etc.), short-first-sentence 150 ms flush, minimum useful chunk sizing, model-specific token/character caps, stitched-audio gap measurement, and fallback chunking for non-streaming engines.

**Success criteria** (observable, testable):
1. The builder can hold a 5-minute back-and-forth call on laptop speakers (no headphones) in Spanish-accented English with **no** self-interrupt ping-pongs, **no** false barge-in on breath or back-channel "mm-hmm", and confident barge-in when they genuinely interrupt a sentence.
2. Time-to-first-audio measured end-to-end (user stops speaking → first TTS sample plays) lands under 800 ms in the warm pipeline on the 3060, with <500 ms as a stretch; numbers logged and tracked.
2a. Long-form TTS is measured through the shared chunk planner for every enabled engine. Metrics include first-chunk TTFA, total stitched playback time, inter-chunk gaps, and a stitched WAV for listening; raw whole-generation fallback numbers are not accepted as final long-form engine comparisons.
3. During a call, the Voice Call screen shows the user's STT partial captions updating within ~500 ms of speech and streaming AI tokens rendering ahead of TTS playback; interim vs final STT state is visually distinct per the DESIGN.md Transcription Chips treatment.
4. On a barge-in, `nvidia-smi` shows the LLM server's GPU utilization drop to idle within ~200 ms and the wasted-token-count log is non-empty (confirming cancel reaches the GPU, not just the client).
5. The Voice Visualizer cleanly transitions across listening (user RMS pulse) → thinking (indeterminate shimmer) → speaking (AI TTS waveform) with no flickers on the state transitions, matching DESIGN.md §5.

**Plans:** TBD

**UI hint:** yes

**Scope signal:** L (the hardest phase; empirical tuning on the builder's actual voice and hardware).

---

### Phase 5: Voice Breadth & Unified Thread Polish

**Goal:** Broaden the Phase-4 core — all TTS engines (up to three: F5, XTTS, Qwen3-TTS) with cold-swap UX, per-chat voice override, saved-audio replay — and close out the unified-thread rendering so text and call turns interleave exactly as DESIGN.md prescribes.

**Depends on:** Phase 4 (a call feels right with one engine; adding the second and third engines multiplies bug surface only after the hard semantic work is done).

**Requirements delivered:** REQ-15 (per-chat override verified in a call), REQ-22 (all Phase-0-accepted engines live per voice — 2 or 3), REQ-61 (grouped collapsible "Call — Nm Ns" header treatment), REQ-62, REQ-63 (window now spans text + call turns; verified in call-after-text scenarios).

**Pitfalls owned:**
- **#7 VRAM (swap path)** — 2–8 s cold-swap between calls with UI feedback ("Switching voice…"); last-used engine cached; swap never mid-call. Six directed swap paths across three engines (or two, if Qwen3-TTS was rejected at Phase 0). Swap-correctness test matrix scales O(N²).
- **#20 Audio storage** — atomic temp-rename writes for per-turn Opus blobs, orphan reaper on startup, storage size indicator in Settings.

**Success criteria** (observable, testable):
1. The builder can assign a voice built on F5-TTS as a character's default and have a call; then switch to a voice built on XTTS v2 (and, if Phase 0 accepted Qwen3-TTS, a third voice on Qwen3-TTS) for the same character in a different chat and have a call; each cold-swap between calls shows a "Switching voice…" state and completes without OOM across all pairwise engine transitions.
2. A per-chat voice override is settable from the chat header, persists across resume, and shadows the character default for calls in that chat only — the underlying character card is not modified.
3. Saved AI audio blobs have an inline play button per `ai_speech` turn that replays the exact call audio; the save-AI-audio toggle and save-mic-audio toggle in Settings take effect on the next call and retroactive replay shows "audio not saved" cleanly when toggled off.
4. A thread that mixes text and call turns renders chronologically with call turns visually distinct (left-rail accent, grouped under a collapsible "Call — Nm Ns" header per DESIGN.md) and the sliding window fed to the LLM mid-call includes both text and call transcripts from recent history.
5. Killing the AI backend mid-call-audio-write leaves no corrupt blobs on the next startup: the orphan reaper logs how many orphans it removed and the thread view is consistent.

**Plans:** TBD

**UI hint:** yes

**Scope signal:** M.

---

### Phase 6: Mobile Hardening & Ship Polish

**Goal:** Close out the Android Chrome long tail, install the PWA surface, finish storage housekeeping, and sign off on the single-sentence v1 acceptance. v1 ships.

**Depends on:** Phase 5 (feature-complete MVP).

**Requirements delivered:** REQ-A2 (PWA manifest + icons + `theme-color`), REQ-A0 (full mobile parity verified across the builder's Bluetooth headset, Wake Lock, visibilitychange), REQ-80 (full Settings surface complete including clear-all-data danger zone, VAD sensitivity tuned on real speech, retention/size indicator). Closes any remaining REQ gaps surfaced during the phase.

**Pitfalls owned:**
- **#21 Bluetooth routing on Android** — known-limitation banner where appropriate and `devicechange` event handling on mobile.
- **#22 Screen-off / visibilitychange** — Wake Lock during active call, "call paused — tap to resume" overlay on background, clean end-on-background fallback.
- **#24 Mobile parity (final gate)** — full checklist run on the builder's actual devices with the actual hardware (Android phone + Bluetooth headset + desktop Chrome).
- **#20 Audio storage (final)** — retention policy configurable in Settings, storage-size indicator live, tested across months-of-use simulation.

**Success criteria** (observable, testable):
1. The builder can add RayMe to their Android home screen, launching it in standalone-launcher mode with the correct `theme-color` chrome, and successfully place a call from the installed PWA.
2. An active call with the builder's Bluetooth headset connected routes audio correctly (or, if not, surfaces the documented known-limitation banner rather than failing silently); disconnecting the headset mid-call triggers a `devicechange`-driven warning with a reconnect affordance.
3. Locking the Android phone screen during a call triggers Wake Lock where supported; backgrounding the tab shows a "Call paused — tap to resume" overlay instead of silent death, and returning to foreground either resumes cleanly or ends the call gracefully with the transcript intact.
4. Settings shows current storage footprint and a configurable retention policy; the danger-zone clear-all-data flow requires confirmation and leaves no dangling blob files.
5. The v1 acceptance statement runs end-to-end on the builder's Android phone: import a v3 PNG card, record a voice in Voice Lab, assign it, start a call from a chat thread, have a barge-in-capable conversation, reopen the thread on desktop and see interleaved text + call turns. All other v1 success criteria from prior phases still hold.

**Plans:** TBD

**UI hint:** yes

**Scope signal:** M.

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Measurement Gate | 0/? | Not started | - |
| 1. Foundations & Text Chat | 0/? | Not started | - |
| 2. AI Backend Skeleton & Voice Lab | 0/? | Not started | - |
| 3. First Working Call (MVP) | 0/? | Not started | - |
| 4. Call Feel | 0/? | Not started | - |
| 5. Voice Breadth & Unified Thread Polish | 0/? | Not started | - |
| 6. Mobile Hardening & Ship Polish | 0/? | Not started | - |

---

## REQ → Phase Coverage Matrix

Every v1 requirement from `REQUIREMENTS.md` is covered. Phase-0 requirements are spike outputs (Key Decisions), not shipped features.

| REQ-ID | Title (short) | Phase |
|--------|---------------|-------|
| REQ-01 | Three services over LAN | 1 |
| REQ-02 | AI backend on RTX 3060, STT+VAD+one TTS coexist | 2 (informed by Phase 0) |
| REQ-03 | OpenAI-compatible streaming LLM | 1 |
| REQ-04 | `0.0.0.0` bind, no auth, LAN-trust UX | 1 |
| REQ-05 | Settings: per-endpoint config + tests | 2 |
| REQ-10 | Character Gallery grid + CRUD actions | 1 |
| REQ-11 | Character Editor full v2+v3 field set + portrait | 1 |
| REQ-12 | Character CRUD with safe delete | 1 |
| REQ-13 | Importer: v2/v3 JSON + PNG (chara/ccv3) | 1 |
| REQ-14 | Exporter: v2 JSON | 1 |
| REQ-15 | Character default voice + per-chat override | 2 (schema + UI) / 5 (per-chat override verified in call) |
| REQ-16 | Lorebook preserved-not-injected | 1 |
| REQ-17 | Alternate-greeting picker on v3 cards | 1 |
| REQ-20 | Voice Lab sample upload (WAV/MP3/FLAC) | 2 |
| REQ-21 | STT auto-transcript, editable | 2 |
| REQ-22 | Voice save: name + engine + sample + transcript | 0 (Qwen3-TTS acceptance gate) / 2 (Phase-0-accepted engines live in 2; in-call usage across engines verified in 5) |
| REQ-23 | Voice Library: list / rename / delete / test-play | 2 |
| REQ-24 | Voice delete safe against references | 2 |
| REQ-30 | Chat thread chronological list + streaming LLM output | 1 |
| REQ-31 | `first_mes` / alternate greeting as opening AI turn | 1 |
| REQ-32 | Regenerate last AI turn | 1 |
| REQ-33 | Edit previous turn + stale-flag downstream | 1 |
| REQ-34 | Swipes / branching alternates | 1 |
| REQ-35 | Continue from composer content | 1 |
| REQ-36 | Virtualized thread + jump-to-latest | 1 |
| REQ-40 | Call initiable from thread or character card | 3 |
| REQ-41 | Full-duplex call audio | 4 |
| REQ-42 | VAD-driven barge-in with gates | 4 |
| REQ-43 | Streaming STT with live user captions | 4 |
| REQ-44 | Streaming LLM with live AI captions | 4 |
| REQ-45 | Sentence-boundary streaming TTS | 4 |
| REQ-46 | End-to-end turn latency <800 ms target | 4 (measured in 0, achieved in 4) |
| REQ-47 | Call toolbar: mute / end / device pickers | 3 |
| REQ-48 | Mic permission prompt + denial handling | 3 |
| REQ-49 | Voice Visualizer three-state | 3 (partial: transitions) / 4 (full visual polish) |
| REQ-50 | Call-end persists summary row; back to text composer | 3 |
| REQ-60 | Unified `messages` table + `kind` discriminator | 1 |
| REQ-61 | Call turns visually distinct in scrollback | 4 (minimal) / 5 (full DESIGN.md treatment) |
| REQ-62 | AI audio saved per turn by default; mic off by default | 5 |
| REQ-63 | Sliding-window memory for call context | 3 (hydration at call start) / 5 (spans text + call turns) |
| REQ-70 | Home threads list | 1 |
| REQ-71 | Thread rename + delete | 1 |
| REQ-72 | Start-new-chat entry point from Home | 1 |
| REQ-80 | Settings full surface | 2 (endpoints + save toggles) / 4 (VAD slider wired) / 6 (retention, clear-data, final) |
| REQ-90 | Ethereal Core / True Dark design system + canonical screens | 1 (Home, Gallery, Editor) / 2 (Voice Lab, Settings) / 3–4 (Voice Call) |
| REQ-A0 | Mobile + desktop parity on LAN | 1 (text-chat) / 3 (MVP call) / 6 (full hardening) |
| REQ-A1 | HTTPS with trusted cert on LAN | 0 (workflow) / 1 (shipped) |
| REQ-A2 | PWA manifest + icons + `theme-color` | 6 |
| REQ-A3 | English-only STT/TTS with Spanish-accented English quality bar | 0 (measured) / 2 (default frozen) |

**Coverage:** 40/40 v1 REQs mapped. No orphans. REQs with multi-phase entries are either (a) schema/UI landed early and in-call use-cases verified later, or (b) minimum viable in an earlier phase with full treatment in a later one — flagged explicitly above.

---

## Sequencing Rationale

1. **Phase 0 first because three of four Resolved Tensions in `SUMMARY.md` have quantitative revisit triggers.** Without Phase 0, Phase 2 may freeze F5-as-default only for Phase 4 to discover XTTS should have been the pin. Without Phase 0's mkcert-on-Android verification, Phase 3 may be the first time we discover the mobile browser won't trust the cert — a catastrophically expensive failure at that stage. Phase 0 outputs become the first Key Decision rows in `PROJECT.md`.

2. **Text chat before voice in Phase 1.** Shared LLM integration and sliding-window assembly shake out in a non-realtime path, which halves the bug surface when voice arrives. The unified `messages` schema lands here — researchers explicitly flagged this as "change it later and pay the migration tax," so it must be chosen at Phase 1, not Phase 3. The three-service topology is the Phase 1 skeleton so everything after drops into a stable bones.

3. **Voice Lab before first call in Phase 2.** A call needs a voice. A voice needs STT. Voice Lab is the minimum-viable path to exercise STT end-to-end without yet needing WebRTC, and it forces the VRAM coexistence rule (exactly-one TTS engine resident) to be real before Phase 3 depends on it. Settings' three-endpoint connection tests land here so Phase 3's call setup is a tap, not a debugging session.

4. **First working call before call feel in Phase 3–4.** Establishes the media plumbing (aiortc, AudioContext gesture unlock, FSM skeleton, timing instrumentation) under the simplest possible semantics — one-sentence non-streaming reply — so the load-bearing Phase 4 work (streaming, barge-in, echo-loop, mid-stream LLM cancel) layers on known-working transport. Research explicitly warned against compressing these two.

5. **Call feel (Phase 4) is where the product either lives or dies.** Phase 4 validates the single line in PROJECT.md that justifies the whole project: "It must feel like an actual phone call with an AI." If Phase 4 doesn't land, nothing after it matters. This is why call feel is validated as early as Phase 4 and not left for the end.

6. **Voice breadth in Phase 5 after Phase 4 proves one engine works.** Doing the hard semantic work with a single engine first prevents multiplying the bug surface during tuning. Cold-swap between calls is an additive feature; it's not the load-bearing path. With three engines (up from two) the swap test matrix scales from 2 paths to 6 — Phase 5 scope was re-checked 2026-04-17 when Qwen3-TTS was added; M remains the right signal.

7. **Mobile hardening last in Phase 6 because mobile-browser quirks are discrete and many can only be verified once the call loop works.** Android Chrome is on every prior phase's test checklist, but the Bluetooth routing / Wake Lock / visibilitychange long tail is its own phase rather than a distraction layered across every feature phase.

---

## Risks & Open Questions

Roadmap-level decisions that remain open after Phase-0 resolves the empirical questions. These are not yet scoped into specific plans.

1. **F5-TTS first-sentence TTFA on the 3060 may exceed the 300 ms budget.** Phase 0 measures. If it does, the Resolved Tension #3 trigger fires and either **XTTS v2** (proven) or **Qwen3-TTS 0.6B-Base** (Apache-2.0 advantage, Phase-0-gated) becomes the v1 default; F5 becomes opt-in per-voice. This flips Phase 2's default engine and affects Phase 5's cold-swap UX emphasis. **Owner: Phase 0 outputs.**

1a. **Qwen3-TTS (added 2026-04-17 as third engine) may fail Phase 0 acceptance on any of four gates**: TTFA ≥400 ms, RTF ≥1, FA2 install failure on Windows, or Spanish-accented-English clone drift. If any gate fails, Qwen3-TTS is feature-flagged off for v1, REQ-22 falls back to two engines, Voice Lab engine picker hides the third option, and `QWEN3-TTS.md` stays as v2+ reference. If all gates pass, the three-engine plan ships as currently documented. **Owner: Phase 0 outputs; see `.planning/research/QWEN3-TTS.md` §7 for conditional triggers.**

2. **Whisper `distil-large-v3 INT8` WER on Spanish-accented English may be >2 pp worse than turbo or FP16.** Phase 0 measures against the builder's own voice. If it is, the Resolved Tension #2 trigger fires and the default STT rung is promoted — which in the FP16 case forces XTTS over F5 (VRAM math). **Owner: Phase 0 outputs.**

3. **LLM mid-stream cancel on the chosen server may not actually reach the GPU within the latency budget.** `llama-server` is the current presumed pick; if Phase 0's probe shows it cancels lazily or not at all, the recommended fallback is to pin a specific known-good server (or the OpenAI API) in `PROJECT.md` as the v1 LLM contract. **Owner: Phase 0 outputs; falls back to Phase 4 as a hard gate.**

4. **Orchestrator custom vs Pipecat decision is conditional on implementation size.** Research resolved this for v1 (custom), but the revisit trigger — orchestrator grows past ~800 lines — may fire during Phase 4's barge-in work. If it does, Phase 5 absorbs a port to Pipecat. Not an acceptance gate for v1, but could reshape Phase 5 scope. **Owner: Phase 4 implementation checkpoint.**

5. **VAD sensitivity tuning (REQ-80 slider) is empirical on the builder's actual speech and hardware.** Phase 4 ships a tuned default; Phase 6 may need a second tuning pass after real-world call hours accumulate. No fixed threshold is committed in the roadmap — only the gate pattern (minimum-duration + word-count + energy) is. **Owner: Phase 4 initial, Phase 6 re-tune.**

6. **`coqui-tts[server]` streaming to aiortc without Docker is not explicitly documented in upstream Pipecat docs** (flagged in `STACK.md` as a Phase-0-ish verification item). If the in-process Python path has issues, Phase 2 may need to run XTTS in a subprocess with its own CUDA context — which changes the "one-hot engine" implementation without changing the rule. **Owner: Phase 2 spike during AI-backend bringup.**

6a. **Long-form TTS measurements are invalid if model limits are ignored.** Phase 0 follow-up found XTTS long-form streaming hit the 400-token `inference_stream` cap and fell back to full-render timing. Going forward, benchmarks and runtime code must implement a shared chunk planner before comparing long-form engines. The planner must enforce each model's token/character caps, preserve natural boundaries where possible, and measure first-chunk TTFA, total stitched playback time, inter-chunk gaps, and stitched audio quality. **Owner: Phase 4 implementation checkpoint; Phase 2 may scaffold shared utilities.**

7. **Requirements traceability flagged no gaps between `PROJECT.md` Active bullets and `REQUIREMENTS.md` v1 set** — see the coverage table at the end of `REQUIREMENTS.md`. If any Phase-0 output (e.g., "XTTS is the v1 default") materially changes a `PROJECT.md` Key Decision row, the roadmapper-owned traceability must update `PROJECT.md` first, not this roadmap. **Owner: Phase-0 closeout; `/gsd-transition` at Phase-0 boundary.**

8. **The 7-phase structure assumes no v1.x regressions creep back into v1.** If the SillyTavern text-UX surface (Regenerate / Edit / Swipes / Continue) proves more complex than budgeted in Phase 1, the overflow should go into Phase 1.1 via `/gsd-insert-phase` — not silently expand Phase 1 or compress Phase 2. This is a process note, not a commitment. **Owner: Phase 1 mid-phase checkpoint.**

---

*Roadmap derived 2026-04-17 from requirements + research synthesis. Next: `/gsd-plan-phase 0`.*
