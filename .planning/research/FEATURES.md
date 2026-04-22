# Feature Research

**Domain:** Self-hosted real-time AI voice-call app with character cards (single-user, LAN-only)
**Researched:** 2026-04-16
**Confidence:** HIGH (domain pattern is mature; competitive references strong; SillyTavern + cloning workflow well-documented)

---

## Context from PROJECT.md

- **Core value is call feel.** Full-duplex audio with VAD-driven barge-in is the load-bearing differentiator; everything else supports it.
- **Single user, LAN only, self-hosted.** No auth, no multi-tenancy, no cloud. This inverts many of the usual "table stakes" of a SaaS voice app (billing, accounts, moderation dashboards are all anti-features here).
- **Three-service topology.** Web UI, AI backend (STT/TTS/VAD on the 3060 box), LLM endpoint. Each independently configurable.
- **English-only v1,** Spanish-accented English is a personal quality bar.
- **Canonical Stitch screen set:** Home, Voice Lab, Character Gallery, Character Editor, Voice Call, Settings. Features below are cross-referenced to these screens.
- **TTS engines:** F5-TTS (needs reference transcript, auto-generated via STT) and XTTS v2 (zero-shot, transcript optional). Both zero-shot cloning.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the user will assume exist. Missing any of these and the product feels broken.

#### Calling / In-Call Experience

| Feature | Why Expected | Complexity | Notes / Screen |
|---------|--------------|------------|----------------|
| Call start button on character / thread | "Call" is the core verb of the product | LOW | Home + Voice Call. Also present on thread header. |
| Call end button with clear "hang up" affordance | Phone-call metaphor demands it | LOW | Voice Call. Red/destructive styling, unambiguous. |
| Full-duplex audio capture + playback in browser | Core value — without this it's a walkie-talkie, not a call | HIGH | WebRTC / WebAudio; depends on server-side audio protocol (WebSocket PCM or WebRTC). |
| VAD-driven barge-in (user can interrupt mid-AI-speech) | Called out in PROJECT.md as non-negotiable | HIGH | Silero VAD (industry standard, <1 MB, CPU-runnable, ~1 ms/chunk). On user speech detection, TTS playback stops immediately. |
| Mute button (mic mute, both locally and server-side) | Universal phone-app expectation | LOW | Voice Call toolbar. Must also tell backend to stop consuming audio (don't just silence locally — saves upload bandwidth and avoids false VAD triggers on background noise). |
| Speaking indicator — "AI is speaking" vs "listening" vs "thinking" | Audio-only interactions require explicit status feedback (NN/G: feedback replaces visual cues) | LOW-MEDIUM | Voice Visualizer is the signature component (per DESIGN.md §5). Three distinct states: listening (pulse waveform driven by user mic level), thinking (indeterminate shimmer), speaking (waveform driven by AI TTS output). |
| Live user captions (user STT transcript, streaming) | Accessibility + confirms "the system heard you" | MEDIUM | Streaming partial transcripts under 500 ms. Distinguish confirmed (final) from interim (processing) text per DESIGN.md Transcription Chips spec. |
| Live AI captions (AI response text, streaming as generated) | Debugging, accessibility, confirmation | MEDIUM | LLM token stream rendered in real time; TTS lags slightly behind. Optional: highlight the sentence currently being spoken. |
| Call ended state / call summary card | User needs closure — "did the call actually end?" | LOW | Persist call row in thread: duration, character, voice used, timestamp. Replaces last-turn ambiguity. |
| Audio output device selection (browser) | Users have headphones, speakers, bluetooth — must be routable | LOW | Browser `navigator.mediaDevices.enumerateDevices()`. Settings + quick-select in Voice Call. |
| Audio input device selection (browser) | Same reason, for mic | LOW | Same API. Must request permission before enumerating labels. |
| Mic permission prompt + graceful denial state | Browser will gate mic; rejection must have a clear path to retry | LOW | Show explanation and a "retry" button if denied. |

#### Text Chat ↔ Call Unification

| Feature | Why Expected | Complexity | Notes / Screen |
|---------|--------------|------------|----------------|
| Single chat thread per (user, character, chat session) holding both typed messages and call transcripts, interleaved chronologically | Called out as core in PROJECT.md | MEDIUM | One `messages` table, message_kind ∈ {user_text, ai_text, user_speech, ai_speech, call_start, call_end}. Render chronologically. |
| Start a call from a text thread | Continuity — "continue this conversation by voice" | LOW | Phone icon in thread header. Uses current thread's history as context. |
| Resume text chat after a call ends | Same continuity, other direction | LOW | Call-end state drops user back into the thread at a new message composer. |
| Visually distinguish call turns from text turns in scrollback | Users need to know "did I say this, or was this transcribed?" | LOW | Call turns get a subtle left-rail accent (e.g., `secondary` #00e3fd per DESIGN.md). Wrap each call in a collapsible "Call — 3m 12s" group. |
| Scrollback / virtual scroll on long threads | Performance expectation on any chat UI | MEDIUM | Needed once threads exceed ~500 messages. |
| Jump-to-latest on new turn during scrollback | Standard chat UX | LOW | Floating button when user has scrolled up. |

#### Character Management

| Feature | Why Expected | Complexity | Notes / Screen |
|---------|--------------|------------|----------------|
| Character Gallery — grid of characters with portraits | Entry point to every chat; must feel like "contacts" | LOW | Character Gallery screen. Card radius `xl` per DESIGN.md. |
| Character creator / editor form | Can't use the product without creating at least one | MEDIUM | Character Editor screen. SillyTavern v2 + v3 field set: name, description, personality, scenario, first message, example messages, system prompt, creator notes, character notes, tags, alternate greetings, post-history instructions, creator, character version. |
| Character portrait upload + preview | Gallery and call screen both show a face; must be editable | LOW | Accept PNG/JPG/WebP. Crop/center to square for gallery tile. |
| Edit existing character | Standard CRUD expectation | LOW | |
| Delete character (with confirmation) | Standard CRUD; confirmation because threads reference it | LOW | Soft delete or cascade-detach from threads — don't orphan chat history. |
| Character importer — SillyTavern v2 JSON | Core interop; users will arrive with existing cards | MEDIUM | Parse chara_card_v2 spec. JSON keyword `chara` when embedded. |
| Character importer — SillyTavern v3 JSON | v3 is current; CCv3 adds assets + extended metadata | MEDIUM | Spec: `character-card-spec-v3`. tEXt keyword `ccv3`. v3 takes precedence over v2 when both are present. |
| Character importer — PNG-embedded cards (v2 + v3) | This is how ~90% of SillyTavern cards are distributed | MEDIUM | Parse PNG tEXt chunk: keyword `chara` (v2, base64-encoded JSON) or `ccv3` (v3, base64-encoded JSON, utf-8). The portrait image itself IS the card; use it as the character portrait. |
| Character export (at least to v2 JSON, ideally v3 PNG) | User will want to back up or share | LOW-MEDIUM | v2 JSON export is trivial. v3 PNG embedding is moderate (encode base64, inject tEXt chunk). v2 JSON is P1; PNG export is P2. |
| Per-character default voice assignment | Already a PROJECT.md requirement | LOW | Dropdown in Character Editor sourced from Voice Library. |
| Per-chat voice override | PROJECT.md requirement | LOW | Thread settings / call setup lets user pick a different voice for this chat. |
| First-message / greeting shown on new chat | SillyTavern convention; sets the scene | LOW | When a new chat is created, the character's `first_mes` is seeded as the first AI message. |

#### Voice Lab

| Feature | Why Expected | Complexity | Notes / Screen |
|---------|--------------|------------|----------------|
| Upload short audio sample (WAV/MP3/FLAC) | Core entry point to voice cloning | LOW | Voice Lab screen. Recommend 6–15 s clean mono sample. Show warnings for noisy/short clips. |
| Auto-generate reference transcript via STT | PROJECT.md requirement; F5-TTS requires exact transcript | MEDIUM | Run Whisper over the uploaded sample. Present editable text. Accuracy matters — user may need to fix artifacts. |
| Editable reference transcript | Same | LOW | Standard textarea with save. |
| Save voice (name + engine = F5-TTS or XTTS v2, selectable per voice) | PROJECT.md requirement | LOW | Voice Library entry records: name, engine, sample path, transcript, created_at. |
| Voice test playback (synthesize a sample line with the new voice) | Users must be able to A/B before assigning | LOW | "Try it" button synthesizes a stock phrase; also allow custom test text. |
| Voice library — list, rename, delete | Standard CRUD | LOW | Voice Lab secondary panel or Settings subsection. |

#### Settings / Configuration

| Feature | Why Expected | Complexity | Notes / Screen |
|---------|--------------|------------|----------------|
| Web UI → AI backend endpoint config | Three-service topology requirement | LOW | Settings. URL + connection test. |
| Web UI → LLM endpoint config (OpenAI-compatible base URL + API key) | Works with OpenAI or local llama-server | LOW | Settings. URL + optional key + connection test. Model name field. |
| STT model selection (if multiple loaded) | Flexibility for GPU budget | LOW-MEDIUM | Dropdown populated from backend. |
| TTS engine default (F5-TTS vs XTTS v2) | Per-voice override exists, but a default is expected | LOW | Radio/select. |
| VAD sensitivity knob | Users will hit false barge-ins or missed barge-ins; they need a lever | LOW | Slider mapping to Silero VAD threshold + end-of-utterance silence duration. |
| Audio device pickers (input/output) | Called out above; also lives in Settings | LOW | |
| "Save AI audio" toggle (default ON) | PROJECT.md default | LOW | Per-chat or global? Recommend global default + per-chat override. |
| "Save mic audio" toggle (default OFF) | PROJECT.md privacy default | LOW | Same. |
| Clear data / delete all history | GDPR-style hygiene; users want a reset | LOW | Danger zone in Settings. |

#### Persistence / Housekeeping

| Feature | Why Expected | Complexity | Notes / Screen |
|---------|--------------|------------|----------------|
| Threads list / recent conversations | Home screen needs to surface "where was I?" | LOW | Home screen. Sorted by last message; show character portrait + last snippet. |
| Delete thread | Standard | LOW | |
| Rename thread | Useful when multiple chats with same character | LOW | |
| AI audio replay inline in transcript | PROJECT.md: AI audio saved by default — must be usable | LOW-MEDIUM | Play button on each AI call turn. Waveform scrubber optional (P2). |
| Timestamps on messages (user-configurable granularity) | Expected on any chat UI | LOW | Relative ("2m ago") in list, absolute on hover. |

---

### Differentiators (Competitive Advantage)

Features that set RayMe apart from the adjacent ecosystem (SillyTavern + TTS extension, Character.ai voice calls, generic local-voice-chat tools).

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **True full-duplex with VAD barge-in** (not turn-based push-to-talk, not Character.ai's "tap to interrupt") | The single most important differentiator. Character.ai requires a button tap to interrupt; most SillyTavern voice setups are strict turn-taking. RayMe interrupts on voice. | HIGH | Silero VAD on incoming mic stream, running continuously even during TTS playback. On speech detected → cancel TTS, cancel in-flight LLM generation (or let it finish silently), begin new STT turn. |
| **End-to-end turn latency tuned for call feel (<800 ms target; stretch <500 ms)** | Character.ai is known for latency complaints; local SillyTavern + TTS setups are often 2–5 s turns. 500–800 ms is the threshold where it feels conversational. | HIGH | Requires streaming STT → streaming LLM → streaming TTS, with TTS starting on first LLM sentence boundary (not after full completion). |
| **Unified chat + call thread** (text and speech turns share one chronological timeline) | Character.ai separates voice and text. SillyTavern TTS is layered onto chat but calls aren't first-class. RayMe makes "continue this conversation, either way" the default. | MEDIUM | Single message store; message_kind enum drives rendering. |
| **Voice Lab auto-transcription for F5-TTS reference** | F5-TTS needs an exact transcript. Most F5 workflows require users to type it manually. Auto-generating + making it editable removes friction. | MEDIUM | Whisper over sample → pre-fill editable text box. |
| **SillyTavern v2 + v3 PNG-embedded card import** | SillyTavern has a huge card ecosystem. Most voice-AI apps reinvent character schemas and lose compatibility. RayMe rides the existing format. | MEDIUM | PNG tEXt chunk parser for both `chara` (v2) and `ccv3` (v3). |
| **Per-chat voice override** (same character can sound different in different chats) | Users can "recast" a character per story without duplicating the card. | LOW | Thread settings field that shadows character default. |
| **Bidirectional live captions** (both your speech and the AI's response, streaming) | Most voice apps show only AI text. Seeing your own STT in real time builds trust ("the system heard me right") and helps debug accent/noise issues. | MEDIUM | Relevant for a Spanish-accented English user — partial transcripts reveal STT quality immediately. |
| **Ethereal Core / True Dark design system** (Voice Visualizer, glassmorphism, no-line rule) | Most self-hosted tools look utilitarian (SillyTavern is notoriously "WebUI of 2004"). Premium visual language is a product differentiator for a personal-use app that the builder will stare at daily. | MEDIUM | Already designed in `docs/stitch/`; execution is the work. |
| **Privacy-sensible recording defaults** (AI audio saved, mic audio off by default) | Most tools either save everything or nothing. Differentiated defaults respect the asymmetry: you want to replay the character's voice, not your own. | LOW | Toggle pair. |
| **Zero-auth LAN-scoped access** | SillyTavern requires running a tunnel or VPN for phone access; Character.ai is cloud-only. Opening the RayMe URL from a phone on the same Wi-Fi "just works." | LOW-MEDIUM | Bind to 0.0.0.0 on LAN; no login. Warn on first launch that this is LAN-trust. |
| **Three-endpoint topology** (Web UI, AI backend, LLM independent) | Matches real home-lab setups (GPU box, app box, optional OpenAI API) without assuming colocation. | LOW | Config-driven. |
| **Voice preview in Voice Lab before assigning** | Cuts the "assign, call, hate it, reassign" loop. | LOW | "Try it" button with custom test phrase. |

---

### Anti-Features (Explicitly NOT Building)

Features that seem like natural additions but hurt the v1 scope. Most are already listed in PROJECT.md "Out of Scope" — expanded here with reasoning for the roadmap.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Multi-user accounts / authentication** | "Shouldn't apps have logins?" | LAN trust is sufficient; auth brings sessions, password reset flows, OAuth providers, cookie domains, CSRF — weeks of scope for zero user value on a personal LAN. | Deploy-time environment var for a bind address if ever needed beyond LAN. |
| **Avatars / lip-sync video / visemes** | Character.ai and other competitors ship avatars | Audio-first is the product thesis (PROJECT.md). Visemes + face rendering = weeks of work, heavy GPU contention with TTS, and doesn't improve call feel. | Static character portrait on the call screen, pulsing with TTS amplitude. |
| **Multilingual STT/TTS** | F5-TTS and XTTS v2 both support multiple languages | Each language needs tuning, prompt handling, and voice-engine validation. Spanish-accented *English* is the personal quality bar — keep the target narrow. | English-only v1; revisit after v1 ships. |
| **Managed TTS/STT APIs** (OpenAI Realtime, ElevenLabs, Deepgram) | Faster, often higher quality, avoids GPU setup | Defeats the "your hardware" positioning; recurring cost; network dependency; no local-sovereignty story. | Self-hosted F5/XTTS + Whisper only. LLM is the sole optional cloud endpoint because OpenAI-compatible is a true standard. |
| **Native mobile apps (iOS/Android)** | "Apps feel better than mobile web" | Responsive web app covers it; WebKit on iOS has WebRTC via 14.3+, Chrome Android is full WebRTC; App Store/Play Store distribution for a single-user LAN app is absurd. | PWA polish: add-to-home-screen, offline shell, lock-screen call styling. |
| **Tool-using agent characters** (browse web, run code, call APIs) | Agent framing is trendy | Conversational personas is the product shape. Tool use requires sandboxing, trust model, streaming tool events mid-call — massive scope. | Characters remain chat personas. If tool use is ever added, it's a separate product. |
| **Cloud / internet-facing deployment** | Convenience | Out of scope per PROJECT.md. Brings auth, rate limiting, billing, abuse prevention, TLS provisioning, content moderation. | Self-hosted LAN. Document how to Tailscale/VPN if the user wants remote access — that's their call, not RayMe's. |
| **Group calls / multi-character calls** | "Can I have three characters talk to each other?" | Adds speaker diarization, voice-routing, turn arbitration, conflicting barge-in semantics. Novel research problem on top of already-hard real-time stack. | Single-character calls only in v1. |
| **Real-time voice-to-voice models** (NVIDIA Nemotron-3 VoiceChat, PersonaPlex, FireRedChat) | Lower latency than cascaded STT→LLM→TTS | Single-model S2S eliminates the LLM choice (no OpenAI API compat, no llama-server), burns much more VRAM, and locks voice+character into one model. Breaks the three-service architecture. | Cascaded pipeline (STT + LLM + TTS) with aggressive streaming. Revisit S2S in v2+ if 3060 can fit a capable model. |
| **Built-in LLM inference server** | One-click install | Three-service architecture is deliberate — user already runs llama-server or uses OpenAI. Bundling an LLM inference engine doubles install complexity. | Config field for existing endpoint. |
| **RVC-style post-processing voice conversion** (SillyTavern RVC extension pattern) | Character voice customization | F5-TTS + XTTS v2 are already zero-shot clones — no need for a second pass. RVC would add latency and GPU pressure. | Direct cloning in TTS engine. |
| **Voice marketplace / sharing / public character directory** | Ecosystem features | Multi-user implication; moderation scope; LAN-only stance. | Local Voice Library + SillyTavern card import covers sharing via file exchange. |
| **Emotion/style tags in TTS** ("say this sadly") | Expressive speech | F5-TTS and XTTS v2 both infer style from reference audio, not prompt tags. Adding a tag layer the engines don't natively consume is fake polish. | Pick the right reference sample for the desired tone. |
| **Per-phrase TTS voice mixing / effects chains** | Production-style voice control | Creative tool surface, not a call-feel feature. Scope creep. | None in v1. |
| **Summarization-based long-term memory** | "Remember everything" | PROJECT.md decides on sliding-window memory for v1. Summarization costs an extra LLM call per turn and complicates state management. | Sliding window of recent turns. |
| **In-call text messaging** (send a text while on a call) | "What if I want to type mid-call?" | Muddles the mental model — call is for voice. Interrupting with text means pausing TTS and branching the thread. | End call, switch to text. One mode at a time. |
| **Call recording export as WAV with mixed channels** (v1) | Users may want shareable recordings | AI audio is already saved as individual turn files (PROJECT.md). A stitched full-call export is a nice-to-have, not table stakes for a single user. | P3 — add a "download call" button in v1.x if requested. |
| **Push notifications** | "Missed call" style UX | Nobody is calling the user — the user initiates every call. No notifications needed. | None. |
| **Content moderation / NSFW filter** | Consumer-app norm | Single-user, self-hosted, no third-party liability. User chooses model and characters. | None. |

---

## Feature Dependencies

```
[Web UI + LLM endpoint config]
    └── [Text chat with character]
            └── [Character editor (SillyTavern field set)]
                    └── [Character gallery / CRUD]
                            └── [Character importer v2 + v3 JSON]
                                    └── [Character importer PNG-embedded]

[AI backend endpoint config]
    └── [STT engine]
            └── [Voice Lab: auto-transcription]
                    └── [Voice Lab: editable transcript]
                            └── [Voice Lab: save voice]
                                    └── [Voice library CRUD]
                                            └── [Per-character default voice]
                                                    └── [Per-chat voice override]

[STT engine] + [TTS engine] + [VAD engine]
    └── [Streaming STT]
            └── [Live user captions]
    └── [Streaming TTS]
            └── [Live AI captions (synced with TTS)]
            └── [AI audio saved turns (replayable)]
    └── [Silero VAD on mic stream]
            └── [End-of-turn detection]
                    └── [Turn boundary → LLM call]
            └── [Barge-in detection (VAD active DURING TTS)]
                    └── [TTS cancel + LLM cancel]
                            └── [Full-duplex call experience]
                                    └── [Call start/end flow]
                                            └── [Speaking indicator / Voice Visualizer states]
                                            └── [Mute / audio device pickers]
                                            └── [Call summary row in thread]

[Text chat with character] + [Full-duplex call experience]
    └── [Unified thread (text + call interleaved)]
            └── [Start call from thread / Resume text after call]
            └── [Visual distinction of call vs text turns]

[All of the above]
    └── [Settings screen for all endpoints + toggles]
    └── [Threads list / Home screen]
```

### Dependency Notes

- **Voice Lab requires STT before save.** F5-TTS needs an exact transcript; users won't hand-type it reliably. This makes STT a prerequisite for *any* voice work, not just calls.
- **Barge-in is an emergent feature of [VAD + streaming TTS + cancelable LLM request].** All three must exist. If the LLM call can't be canceled mid-stream, barge-in leaks partial responses into the transcript. Plan cancellation semantics early.
- **Unified thread rendering requires a single message store with a `kind` discriminator.** If text messages and call transcripts live in separate tables, interleaving becomes a join nightmare. Pick one table with `message_kind` at phase 0.
- **Character importer (PNG) depends on the editor being able to render all imported fields.** Don't ship import before editor supports the full v2 field set — you'll silently drop data.
- **Per-chat voice override depends on Voice Library and per-character default both existing.** Ship them in order: library → character default → per-chat override.
- **Streaming TTS depends on an early sentence-boundary segmenter.** You want TTS to start on the LLM's first sentence, not after full completion. That means the frontend (or backend orchestrator) needs a streaming tokenizer that yields complete sentences as soon as punctuation lands.
- **Mobile browser call support depends on WebRTC / WebAudio compatibility.** iOS Safari WebRTC is usable since 14.3 but has WebKit-imposed limits (H.264 only, no Insertable Streams). Plan for audio-only — video was never in scope — but test on mobile Safari early, not at the end.
- **VAD sensitivity setting conflicts with barge-in aggressiveness.** Too sensitive = false barge-ins from background noise, coughs, keyboard clicks; too loose = user has to shout. Expose the slider; default on the conservative side.

---

## MVP Definition

### Launch With (v1) — Phase-Gated Minimum

Every item here maps to the PROJECT.md "Active" requirements; if any is cut, PROJECT.md must be updated first.

- [ ] **Character Editor** with SillyTavern v2 + v3 field set and portrait upload — can't start without at least one character
- [ ] **Character Gallery** showing all characters — the Home/entry surface
- [ ] **Character Importer** (v2 JSON, v3 JSON, PNG-embedded for both) — users arrive with existing cards
- [ ] **Text chat thread** with streaming LLM responses — baseline interaction
- [ ] **Voice Lab** (upload sample → Whisper auto-transcript → editable → save with engine choice F5/XTTS) — prerequisite for any voice
- [ ] **Voice library CRUD** — list, rename, delete, test-play
- [ ] **Per-character default voice + per-chat override** — PROJECT.md decisions
- [ ] **Full-duplex voice call** with:
  - [ ] Streaming STT with live user captions
  - [ ] Streaming LLM with live AI captions
  - [ ] Streaming TTS starting on first sentence boundary
  - [ ] VAD-driven barge-in during TTS playback
  - [ ] Mute, end-call, device pickers
  - [ ] Voice Visualizer with listening / thinking / speaking states
- [ ] **Unified thread** with text + call turns interleaved chronologically, visually distinguished
- [ ] **AI audio saved per turn, replayable inline** (default on); mic audio toggle (default off)
- [ ] **Settings** — all three endpoints configurable with connection tests; VAD sensitivity; audio device pickers; save toggles
- [ ] **Threads list on Home** — most recent at top
- [ ] **LAN-accessible from phone browser** — 0.0.0.0 bind, mobile-responsive layout, tested on iOS Safari + Chrome Android

### Add After Validation (v1.x)

- [ ] Character v3 PNG export (v1 ships v2 JSON export; v3 PNG is polish)
- [ ] Waveform scrubber for replay (v1 = play button only)
- [ ] Alternate-greeting picker when starting a new chat (v3 cards support multiple first-messages)
- [ ] Lorebook / world-info support (SillyTavern v2+ field; skip for v1 unless trivial)
- [ ] Call export as single WAV (currently per-turn files)
- [ ] Thread search
- [ ] Global character search in Gallery
- [ ] Tag-based character filtering in Gallery
- [ ] Conversation branching / swipe alternate responses (SillyTavern core feature; v1 does linear only)
- [ ] Regenerate last AI turn
- [ ] Edit previous user or AI turn
- [ ] Per-thread LLM override (different sampling params per chat)
- [ ] PWA install + add-to-home-screen polish

### Future Consideration (v2+)

- [ ] Summarization-based long-term memory (v1 = sliding window)
- [ ] Emotion/style reference swapping mid-call
- [ ] Multi-language support (v1 = English only)
- [ ] End-to-end speech-to-speech model option (Nemotron/PersonaPlex) as an alternative pipeline
- [ ] Optional auth / remote-access preset (for users who want beyond-LAN)
- [ ] Voice conversion post-processing (RVC-style) if cloning quality demands it

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Full-duplex call with VAD barge-in | HIGH | HIGH | P1 |
| Streaming STT + live user captions | HIGH | MEDIUM | P1 |
| Streaming LLM + live AI captions | HIGH | MEDIUM | P1 |
| Streaming TTS with sentence-boundary start | HIGH | MEDIUM | P1 |
| Voice Visualizer (3 states) | HIGH | MEDIUM | P1 |
| Mute / end-call / device pickers | HIGH | LOW | P1 |
| Voice Lab (upload → auto-transcript → save) | HIGH | MEDIUM | P1 |
| Voice library CRUD + test playback | HIGH | LOW | P1 |
| Character Editor (v2 + v3 fields) | HIGH | MEDIUM | P1 |
| Character Gallery | HIGH | LOW | P1 |
| Character importer (v2 + v3 JSON + PNG) | HIGH | MEDIUM | P1 |
| Unified thread (text + call interleaved) | HIGH | MEDIUM | P1 |
| Per-character default voice + per-chat override | HIGH | LOW | P1 |
| AI audio saved + replayable | HIGH | LOW | P1 |
| Settings (3 endpoints + toggles) | HIGH | LOW | P1 |
| Mobile-responsive LAN access | HIGH | MEDIUM | P1 |
| Ethereal Core design system execution | MEDIUM | MEDIUM | P1 |
| VAD sensitivity knob | MEDIUM | LOW | P1 |
| Call summary row in thread | MEDIUM | LOW | P1 |
| Thread rename / delete | MEDIUM | LOW | P1 |
| Alternate greeting picker | MEDIUM | LOW | P2 |
| Character v3 PNG export | MEDIUM | MEDIUM | P2 |
| Regenerate last turn | MEDIUM | LOW | P2 |
| Edit previous turn | MEDIUM | LOW | P2 |
| Conversation branching (swipes) | MEDIUM | MEDIUM | P2 |
| Thread search | MEDIUM | LOW | P2 |
| Call WAV export (mixed) | LOW | LOW | P3 |
| Lorebook / world info | LOW | MEDIUM | P3 |
| Waveform scrubber for replay | LOW | MEDIUM | P3 |
| Speech-to-speech model option | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must ship for v1 to fulfill Core Value ("feels like a real phone call with an AI character")
- P2: Add in v1.x after core validates; noticeable quality-of-life gains
- P3: Future/deferred; interesting but not load-bearing

---

## Cross-Reference to Stitch Canonical Screens

From `docs/stitch/DESIGN.md` and PROJECT.md: Home, Voice Lab, Character Gallery, Character Editor, Voice Call, Settings.

| Screen | Features Anchored Here |
|--------|------------------------|
| **Home** | Threads list (recent first), new-chat entry, character-gallery shortcut, call shortcut from a thread |
| **Character Gallery** | Character grid with portraits, create-new entry, importer drop-zone, per-character context menu (edit/delete/export), search/filter (P2) |
| **Character Editor** | All v2 + v3 fields, portrait upload/preview, default-voice dropdown, save/cancel, delete with confirmation |
| **Voice Lab** | Sample upload, auto-transcript display + edit, engine selector (F5 / XTTS), name input, test-play, save to library, library list (rename/delete/test) |
| **Voice Call** | Voice Visualizer (listening/thinking/speaking states), live bidirectional captions, mute, end-call, in-call voice override (optional), audio device quick-picker, character portrait and name |
| **Settings** | Three-endpoint config + test, STT/TTS/VAD model dropdowns, VAD sensitivity slider, audio-device defaults, save-audio toggles, clear-data danger zone |

---

## Competitor Feature Analysis

| Feature | SillyTavern + TTS ext | Character.ai voice calls | Local voice-chat-ai repos (KoljaB, bigsk1) | RayMe approach |
|---------|----------------------|---------------------------|---------------------------------------------|----------------|
| Call feel | Turn-based; TTS plays after full LLM response | Near-real-time, button-tap interrupt | Turn-based with silence timeout | **Full-duplex VAD barge-in** |
| Voice cloning | Via RVC extension (post-TTS conversion) | Pre-built voice library | XTTS v2 direct cloning | **F5-TTS + XTTS v2, user-cloned in Voice Lab** |
| Character cards | v2 + v3 native | Proprietary format | None / hardcoded | **v2 + v3 import/edit/export** |
| Self-hosted | Yes | No (cloud only) | Yes | **Yes, LAN only** |
| Mobile browser | Works but janky; no first-class call UI | Mobile-native app | Desktop-first | **Mobile-responsive PWA, LAN-accessible** |
| Live user captions | Via STT extension; not streaming | No | Sometimes | **Yes, streaming partial + final** |
| Live AI captions | Yes (chat view) | Yes | Via console usually | **Yes, synced to TTS playback** |
| Chat+call unification | No — calls are extension layer over chat, not integrated turns | Separated modes | No | **Unified thread, interleaved kinds** |
| Endpoint flexibility | OpenAI-compatible LLM; extension-specific TTS/STT | N/A | Often hardcoded | **Three independent LAN endpoints** |
| UI polish | "Utilitarian" (generous) | Premium consumer | Minimal / CLI-ish | **Ethereal Core / True Dark** |

---

## Sources

- PROJECT.md + DESIGN.md (authoritative — Stitch canonical set, Ethereal Core tokens, out-of-scope list)
- [SillyTavern Character Management docs (DeepWiki)](https://deepwiki.com/SillyTavern/SillyTavern/5.1-character-management)
- [character-card-spec-v3 on GitHub](https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md) — v3 PNG tEXt chunk `ccv3`, base64-encoded JSON, v3 takes precedence over v2
- [character-card-spec-v2 on GitHub](https://github.com/malfoyslastname/character-card-spec-v2) — v2 PNG tEXt chunk `chara`
- [SillyTavern TTS extension docs](https://docs.sillytavern.app/extensions/tts/)
- [SillyTavern RVC docs](https://docs.sillytavern.app/extensions/rvc/) — explains second-pass conversion pattern (NOT adopting)
- [Character.ai — Introducing Character Calls](https://blog.character.ai/introducing-character-calls/)
- [Character Calls & Voice FAQ (Character.ai Help)](https://support.character.ai/hc/en-us/articles/23957274129691-Character-Calls-Voice-FAQ)
- [Silero VAD on GitHub](https://github.com/snakers4/silero-vad) — industry-standard VAD, <1 MB, CPU, ~1 ms/chunk
- [LiveKit — Silero VAD plugin docs](https://docs.livekit.io/agents/logic/turns/vad/)
- [LiveKit — End-of-turn detection blog](https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection)
- [Gnani — Real-Time Barge-In AI](https://www.gnani.ai/resources/blogs/real-time-barge-in-ai-for-voice-conversations-31347) — <100 ms barge-in target
- [FireRedChat (arxiv 2509.06502)](https://arxiv.org/html/2509.06502v1) — pVAD + EoT detector pattern for full-duplex
- [NVIDIA PersonaPlex](https://research.nvidia.com/labs/adlr/personaplex/) — dual-stream S2S reference (NOT adopting)
- [NVIDIA Nemotron-3 VoiceChat](https://build.nvidia.com/nvidia/nemotron-voicechat/modelcard) — same (NOT adopting)
- [Pipecat on GitHub](https://github.com/pipecat-ai/pipecat) — open-source voice-AI orchestration framework
- [KoljaB/LocalAIVoiceChat](https://github.com/KoljaB/LocalAIVoiceChat) — RealtimeSTT + RealtimeTTS reference pattern
- [bigsk1/voice-chat-ai](https://github.com/bigsk1/voice-chat-ai)
- [F5-TTS on GitHub](https://github.com/swivid/f5-tts) — reference-transcript-required workflow
- [XTTS v2 multilingual voice cloning guide (HF)](https://huggingface.co/blog/norwooodsystems/multilingual-voice-cloning-with-xtts-v2)
- [Voice AI stack 2026 overview](https://www.digitado.com.br/voice-ai-in-2026-the-complete-stack-from-whisper-to-speaker/)
- [NN/G — Audio Signifiers for Voice Interaction](https://www.nngroup.com/articles/audio-signifiers-voice-interaction/)
- [OpenAI Voice Mode FAQ](https://help.openai.com/en/articles/8400625-voice-mode-faq) — mute / cc / interrupt patterns
- [WebRTC browser support 2026](https://antmedia.io/webrtc-browser-support/)
- [WebRTC Safari 2025 guide (VideoSDK)](https://www.videosdk.live/developer-hub/webrtc/webrtc-safari)
- [Guide to WebRTC with Safari in the Wild (webrtcHacks)](https://webrtchacks.com/guide-to-safari-webrtc/)

---

## Confidence Notes

- **HIGH** on character-card format details (v2 + v3 specs are explicit and well-documented).
- **HIGH** on VAD/barge-in pattern (Silero VAD + cancel-on-voice is the industry standard; multiple 2026 references).
- **HIGH** on F5-TTS requiring an exact reference transcript — confirmed against upstream repo and multiple workflow writeups.
- **HIGH** on Character.ai voice-call baseline features (blog.character.ai is authoritative for their product).
- **MEDIUM** on latency targets — 500–800 ms is widely cited as the "feels natural" threshold, but actual numbers depend on the 3060 budget, model picks, and network. Treat as a design target, not a contract.
- **MEDIUM** on iOS Safari WebRTC quirks — usable since 14.3 but WebKit-constrained; needs empirical validation on real devices early.
- **LOW** on exact downstream behavior of cancel-mid-stream for OpenAI-compatible LLM servers (some llama-server implementations handle client disconnect cleanly, others leak tokens). Flag for stack research and early integration test.

---

*Feature research for: RayMe — self-hosted real-time AI voice-call app with SillyTavern character-card compatibility*
*Researched: 2026-04-16*
