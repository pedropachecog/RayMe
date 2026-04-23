# Phase 1: Foundations & Text Chat End-to-End - Context

**Gathered:** 2026-04-23T23:39:24Z
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 creates the production foundation for RayMe: repo/app scaffold, HTTPS LAN serving, three-service health checks, durable storage, SillyTavern character CRUD/import/export, the unified `messages` schema, Home/Gallery/Editor/Settings/Text Chat surfaces, and a streaming text-chat loop against an OpenAI-compatible LLM.

This phase does not implement Voice Lab synthesis, resident STT/TTS/VAD models, WebRTC calls, live call captions, barge-in, saved call audio replay, PWA hardening, or voice-engine swapping. It must still shape the schema and interfaces so those later phases plug in without migration.

</domain>

<decisions>
## Implementation Decisions

### Workflow Fallback
- **D-01:** Structured interactive prompts are unavailable in this Codex session, so this context uses the `gsd-discuss-phase` fallback: present the gray areas conceptually and lock conservative defaults from `PROJECT.md`, `REQUIREMENTS.md`, Phase 0 decisions, and existing research.
- **D-02:** These decisions should be treated as builder defaults, not new product scope. If the user later wants a different UX preference, update this context before planning.

### Service And Repo Shape
- **D-03:** Use a monorepo with three top-level runtime areas: `web-ui/`, `ai-backend/`, and `llm/` docs/config only. The LLM is external and OpenAI-compatible; RayMe does not ship local inference.
- **D-04:** Split `web-ui/` into a SvelteKit 2 / Svelte 5 static client and a Python FastAPI API/static host. The FastAPI host owns SQLite, file blobs, app APIs, TLS serving, and LLM proxying for text chat.
- **D-05:** Create an `ai-backend/` FastAPI health stub in Phase 1 only. It must answer `/health` over HTTPS and support Settings connection tests, but model residency and WebRTC signaling are Phase 2+.
- **D-06:** Text chat calls the LLM from the Web UI host, not directly from the browser, so API keys stay server-side and streaming behavior is centralized.

### HTTPS And LAN Safety
- **D-07:** Use the Phase 0 mkcert-on-LAN workflow as the only supported Phase 1 HTTPS path. The known passing Android URL was `https://192.168.1.199:8443`.
- **D-08:** First-launch or Settings should visibly check `window.isSecureContext` and `navigator.mediaDevices` because certificate appearance alone is not the real mobile readiness signal.
- **D-09:** Bind services to explicit configured LAN interfaces by default. If `0.0.0.0` is needed to satisfy local LAN reachability during development, require an explicit config value and a visible LAN-trust warning.
- **D-10:** CORS and WebSocket origin policy must be explicit allow-lists. No `Access-Control-Allow-Origin: *` for app APIs.

### Storage And Schema
- **D-11:** SQLite is the durable metadata store from day one, with migrations checked in. Use WAL mode and predictable local data paths.
- **D-12:** Binary assets are files on disk, not SQLite BLOBs. Phase 1 needs this for character portraits and future compatibility with voice/audio blobs.
- **D-13:** Establish the unified `messages` table immediately with `message_kind` values for `user_text`, `ai_text`, `user_speech`, `ai_speech`, `call_start`, and `call_end`, even though Phase 1 only writes text kinds.
- **D-14:** Message branch/swipe support should be represented in schema now, so Regenerate, Swipes, Edit stale-state, and Continue do not require a later migration.
- **D-15:** Character deletion should preserve existing chat history. Prefer soft delete or detached historical snapshots over cascading thread deletion.

### Character Cards
- **D-16:** Normalize all imported cards to one internal v3-shaped character model, while preserving original source JSON for safe round-trip and later export work.
- **D-17:** PNG import must prefer the `ccv3` tEXt chunk and fall back to `chara`. Malformed base64, oversized chunks, or schema-invalid payloads must fail with clear import errors.
- **D-18:** v2 JSON export ships in Phase 1. v3 PNG export remains deferred to v1.x per requirements.
- **D-19:** Lorebook/world-info data must be preserved in storage and surfaced as "present, not used in v1"; it must not be injected into the LLM context in this phase.
- **D-20:** Character-rendered fields are untrusted content. Render as escaped text or through a strict Markdown pipeline with sanitization; never raw HTML.

### Text Chat Semantics
- **D-21:** A new chat seeds the opening AI message from `first_mes`; if alternate greetings exist, show a picker before creating the thread.
- **D-22:** Streaming LLM output should render token-by-token, then persist the final message atomically when the stream completes.
- **D-23:** Regenerate replaces the current selected AI response for the last AI turn; it does not append a second visible canonical answer.
- **D-24:** Swipes store alternates for an AI turn and track the selected alternate. Only the selected branch contributes to future LLM context.
- **D-25:** Editing a prior user or AI turn marks downstream turns stale. The UI must offer truncate-and-continue or keep-stale-history instead of silently rewriting history.
- **D-26:** Continue uses the composer text, when present, as an instruction/prefix to extend the previous AI turn.
- **D-27:** Long threads should be virtualized once they cross the requirement threshold, approximately 500 messages.

### UI And Design
- **D-28:** Build the actual app shell as the first screen, not a landing page. Home is the operational dashboard.
- **D-29:** Use `docs/stitch/DESIGN.md` and the True Dark Stitch exports as the visual contract. Home, Character Gallery, Character Editor, and Settings are the Phase 1 primary screens; Voice Lab and Voice Call can appear as disabled/future nav entries only if needed for navigation consistency.
- **D-30:** Follow the design system's tonal layering and no-divider/no-raw-border direction while still preserving accessibility. Use ghost outlines only when needed for usable focus/structure.
- **D-31:** Settings in Phase 1 must include endpoint configuration and connection tests for Web UI host, AI backend stub, and LLM endpoint. Voice/VAD/audio controls may appear disabled or marked future if the screen needs to preserve layout.
- **D-32:** Avoid fake account, billing, logout, or notification behavior from the Stitch mockups. RayMe is single-user LAN with no auth in v1.

### the agent's Discretion
- Exact folder names inside `web-ui/client`, `web-ui/server`, and `ai-backend`.
- Exact migration tool wiring, as long as SQLite migrations are reproducible.
- Exact component breakdown for Stitch-derived screens.
- Exact loading skeletons, empty states, and toast wording.
- Whether chat streaming reaches the browser via SSE or WebSocket, as long as it is reliable, testable, and fits the later call architecture.

</decisions>

<specifics>
## Specific Ideas

- Phase 1 should start from the frozen Phase 0 decisions, not reopen model selection.
- Treat the Stitch True Dark screens as strong visual references, but remove mock-product affordances that conflict with the v1 scope, especially auth/account/billing concepts.
- The Settings connection-test UX is important because the project deliberately has three independently configurable endpoints.
- The malicious-card test from the roadmap should be implemented early enough that unsafe rendering patterns never enter the codebase.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Scope And Requirements
- `.planning/ROADMAP.md` - Phase 1 goal, requirements delivered, success criteria, pitfalls owned, and dependency on Phase 0.
- `.planning/REQUIREMENTS.md` - v1 requirements, especially REQ-01, REQ-03, REQ-04, REQ-10 through REQ-17, REQ-30 through REQ-36, REQ-60, REQ-70 through REQ-72, REQ-80, REQ-90, REQ-A0, and REQ-A1.
- `.planning/PROJECT.md` - Product vision, core value, constraints, out-of-scope boundaries, and Phase 0 frozen decisions.
- `.planning/STATE.md` - Current Phase 0 completion notes and decisions carried into Phase 1.

### Phase 0 Decisions
- `.planning/phases/00-measurement-gate/KEY_DECISIONS.md` - Human-readable Phase 0 decisions.
- `.planning/phases/00-measurement-gate/results/phase0_summary.json` - Machine-readable Phase 0 roll-up.
- `.planning/phases/00-measurement-gate/HTTPS-SETUP.md` - Reproducible mkcert-on-LAN workflow.
- `.planning/phases/00-measurement-gate/results/https_android.json` - Android Chrome HTTPS acceptance result.

### Architecture And Stack
- `.planning/research/SUMMARY.md` - Synthesized architecture and risk summary.
- `.planning/research/STACK.md` - Recommended SvelteKit, FastAPI, SQLite, LLM, and character-card stack details.
- `.planning/research/ARCHITECTURE.md` - Three-service topology, data ownership, schema sketch, and service-boundary guidance.
- `.planning/research/FEATURES.md` - Product feature surface and text-chat/character-management priorities.
- `.planning/research/PITFALLS.md` - Pitfalls for HTTPS, card XSS, v2/v3 parsing, CORS/origin checks, interface binding, and atomic storage.

### Design
- `docs/stitch/DESIGN.md` - Ethereal Core / True Dark design system.
- `docs/stitch/manifest.md` - Canonical Stitch screen inventory and artifact mapping.
- `docs/stitch/screens/home-true-dark.md` - Home screen notes.
- `docs/stitch/screens/character-gallery-true-dark.md` - Character Gallery notes.
- `docs/stitch/screens/character-editor-true-dark.md` - Character Editor notes.
- `docs/stitch/screens/settings-true-dark.md` - Settings notes.
- `docs/stitch/html/home-true-dark.html` - HTML reference for Home.
- `docs/stitch/html/character-gallery-true-dark.html` - HTML reference for Character Gallery.
- `docs/stitch/html/character-editor-true-dark.html` - HTML reference for Character Editor.
- `docs/stitch/html/settings-true-dark.html` - HTML reference for Settings.
- `docs/rayme-source.md` - Concise product brief from the Stitch handoff.

### External Specs Cited By Local Research
- `https://github.com/kwaroran/character-card-spec-v3` - Character Card v3 and `ccv3` PNG chunk behavior.
- `https://github.com/malfoyslastname/character-card-spec-v2` - Character Card v2 and `chara` PNG chunk behavior.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/stitch/html/*.html` - Static HTML exports that can be used as visual/component scaffolding for the SvelteKit screens.
- `docs/stitch/screenshots/*.png` - Screenshot references for visual regression and manual comparison.
- `.planning/phases/00-measurement-gate/probes/https_serve.py` - Minimal secure-context probe pattern for HTTPS validation.
- `.planning/phases/00-measurement-gate/HTTPS-SETUP.md` - Working mkcert procedure to adapt into Phase 1 docs/first-launch guidance.

### Established Patterns
- No production `src/`, `web-ui/`, or `ai-backend/` code exists yet. Phase 1 is the scaffold phase.
- Planning and research consistently choose SvelteKit 2 / Svelte 5 for the client, FastAPI for Python services, SQLite plus filesystem blobs for durable data, and OpenAI-compatible Chat Completions for LLM access.
- Phase 0 used explicit JSON result files and reproducible docs; Phase 1 should continue that pattern for health checks, migrations, and acceptance evidence.

### Integration Points
- `web-ui/server` should be the source of truth for characters, threads, messages, settings, and file blobs.
- `web-ui/client` should consume the API, render streaming text, and own browser-only checks like secure context.
- `ai-backend` should expose `/health` in Phase 1 and later grow into the STT/TTS/VAD/WebRTC service.
- The LLM endpoint remains external and configurable; Phase 1 only needs connection testing and streaming text completion.

</code_context>

<deferred>
## Deferred Ideas

- Voice Lab upload/transcription/synthesis and Voice Library management belong to Phase 2.
- WebRTC call transport, AudioContext unlock, call toolbar, and call-summary writeback belong to Phase 3.
- Barge-in, live captions, and Voice Visualizer state polish belong to Phase 4.
- Multi-engine voice breadth, per-chat voice override UI, and saved audio replay belong to Phase 5, though schema hooks should exist now.
- PWA install polish, Wake Lock, Bluetooth routing, storage retention controls, and mobile hardening belong to Phase 6.
- v3 PNG export, lorebook injection, thread search, gallery search/filtering, waveform scrubber, and per-thread LLM sampling overrides remain v1.x or later per requirements.

</deferred>

---

*Phase: 01-foundations-text-chat-end-to-end*
*Context gathered: 2026-04-23T23:39:24Z*
