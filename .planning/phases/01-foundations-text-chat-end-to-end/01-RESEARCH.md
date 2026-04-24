# Phase 01: Foundations & Text Chat End-to-End - Research

**Researched:** 2026-04-24 [VERIFIED: system current_date]
**Domain:** SvelteKit static client, FastAPI HTTPS/API host, SQLite/filesystem persistence, OpenAI-compatible streaming text chat, SillyTavern card import/export [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md]
**Confidence:** HIGH for locked stack and Phase 1 boundaries; MEDIUM for exact chat schema column names because Phase 1 still has to implement the first production schema [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md]

<user_constraints>
## User Constraints (from CONTEXT.md)

Source for this section: copied from `.planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md`. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md]

### Locked Decisions

#### Discussion Mode
- **D-01:** The project now has `workflow.text_mode: true`, so future GSD discussion workflows must use plain numbered prompts and must not skip discussion because structured prompt UI is unavailable.
- **D-02:** Recommendations should always be shown clearly and listed first. User selections in this file are explicit discussion decisions, not inferred defaults.

#### Phase 1 Delivery Shape
- **D-03:** Prioritize a balanced vertical slice: Home -> Character Gallery/import -> Character Editor basics -> Chat -> streaming LLM reply -> persisted unified messages. This is preferred over backend-only progress or broad but shallow screen scaffolding.
- **D-04:** Phase 1 acceptance target is an end-to-end imported-character chat over HTTPS: import a v2/v3 card, start a chat, stream a reply, persist unified messages, reload, and continue.
- **D-05:** Run `$gsd-ui-phase 1` before implementation planning. Planning should consume a UI design contract for Home, Character Gallery, Character Editor, Settings, and Chat instead of relying only on the Stitch handoff.

#### Service And Repo Shape
- **D-06:** Use a monorepo with three top-level runtime areas: `web-ui/`, `ai-backend/`, and `llm/` docs/config only. The LLM is external and OpenAI-compatible; RayMe does not ship local inference.
- **D-07:** Split `web-ui/` into a SvelteKit 2 / Svelte 5 static client and a Python FastAPI API/static host. The FastAPI host owns SQLite, file blobs, app APIs, TLS serving, and LLM proxying for text chat.
- **D-08:** Create an `ai-backend/` FastAPI health stub in Phase 1 only. It must answer `/health` over HTTPS and support Settings connection tests, but model residency and WebRTC signaling are Phase 2+.
- **D-09:** Text chat uses a server-side LLM proxy. The browser talks to RayMe; RayMe streams from the configured OpenAI-compatible endpoint so API keys and endpoint details stay server-side.

#### HTTPS And LAN Safety
- **D-10:** Use the Phase 0 mkcert-on-LAN workflow as the only supported Phase 1 HTTPS path. The known passing Android URL was `https://192.168.1.199:8443`.
- **D-11:** First-launch or Settings should visibly check `window.isSecureContext` and `navigator.mediaDevices` because certificate appearance alone is not the real mobile readiness signal.
- **D-12:** Use explicit LAN bind with guided setup: default to configured LAN IP/host, show setup guidance when missing, and do not bind `0.0.0.0` by default.
- **D-13:** CORS and WebSocket origin policy must be explicit allow-lists. No `Access-Control-Allow-Origin: *` for app APIs.

#### Storage And Schema
- **D-14:** Use schema-first SQLite: build migrations and real tables up front, including future `message_kind` values and branch/swipe structure.
- **D-15:** Binary assets are files on disk, not SQLite BLOBs. Phase 1 needs this for character portraits and future compatibility with voice/audio blobs.
- **D-16:** Establish the unified `messages` table immediately with `message_kind` values for `user_text`, `ai_text`, `user_speech`, `ai_speech`, `call_start`, and `call_end`, even though Phase 1 only writes text kinds.
- **D-17:** Message branch/swipe support should be represented in schema now, so Regenerate, Swipes, Edit stale-state, and Continue do not require a later migration.
- **D-18:** Character deletion should preserve existing chat history. Prefer soft delete or detached historical snapshots over cascading thread deletion.

#### Character Cards
- **D-19:** Normalize all imported cards to one internal v3-shaped character model, while preserving original source JSON for safe round-trip and later export work.
- **D-20:** Use best-effort safe import: import what RayMe can safely parse, preserve raw source JSON, warn clearly about ignored/invalid fields, and reject dangerous or malformed payloads that could crash parsing or create XSS risk.
- **D-21:** PNG import must prefer the `ccv3` tEXt chunk and fall back to `chara`.
- **D-22:** v2 JSON export ships in Phase 1. v3 PNG export remains deferred to v1.x per requirements.
- **D-23:** Lorebook/world-info data must be preserved in storage and surfaced as "present, not used in v1"; it must not be injected into the LLM context in this phase.
- **D-24:** Character-rendered fields are untrusted content. Render with sanitized Markdown: preserve common card formatting, but strip/escape HTML and dangerous content. Never render raw HTML.
- **D-25:** Character Gallery is the import entry point. Imported cards should open in Character Editor for review/save.

#### Text Chat Semantics
- **D-26:** Implement full SillyTavern text basics in Phase 1: streaming replies, Regenerate, Edit with stale downstream turns, Swipes, Continue, and alternate greetings.
- **D-27:** New chats start immediately with the default `first_mes`. If alternate greetings exist, the opening message must clearly show an alternate-greeting control so the user can switch before continuing the thread.
- **D-28:** Streaming LLM output should render token-by-token, then persist the final message atomically when the stream completes.
- **D-29:** Regenerate replaces the current selected AI response for the last AI turn; it does not append a second visible canonical answer.
- **D-30:** Swipes store alternates for an AI turn and track the selected alternate. Only the selected branch contributes to future LLM context.
- **D-31:** Editing a prior user or AI turn marks downstream turns stale. Use an explicit stale flag with branch choice: when continuing after an edit, the user chooses truncate stale downstream turns or keep stale history.
- **D-32:** Continue uses the composer text, when present, as an instruction/prefix to extend the previous AI turn.
- **D-33:** Use per-message contextual actions: hover/tap menu on AI turns for Regenerate, Swipe, Edit, and Continue; user turns get Edit.
- **D-34:** Long threads should be virtualized once they cross the requirement threshold, approximately 500 messages.

#### UI And Design
- **D-35:** Build the actual app shell as the first screen, not a landing page. Home is the operational dashboard.
- **D-36:** Use Stitch-faithful, scope-corrected UI: keep the True Dark visual language and layout feel, but remove fake account/billing/logout/noise and show only real Phase 1 controls.
- **D-37:** Home is threads-first: recent threads list is primary; new chat/import/create actions are nearby.
- **D-38:** Chat thread layout should be a spacious modern messenger, not a cramped SillyTavern clone. Preserve enough density for long threads and virtualization while favoring a polished RayMe conversational feel.
- **D-39:** Settings in Phase 1 should show real endpoint settings only: Web UI URL/status, AI backend URL/status, LLM URL/key/model/status, and HTTPS/secure-context status.
- **D-40:** Follow the design system's tonal layering and no-divider/no-raw-border direction while still preserving accessibility. Use ghost outlines only when needed for usable focus/structure.

#### Testing And Verification
- **D-41:** Use contract-heavy tests for Phase 1: schema migrations, card parser/importer, sanitizer, LLM streaming proxy, message actions, endpoint health, and the end-to-end imported-character chat target.

### Claude's Discretion
- Exact folder names inside `web-ui/client`, `web-ui/server`, and `ai-backend`.
- Exact migration tool wiring, as long as SQLite migrations are reproducible.
- Exact component breakdown for Stitch-derived screens.
- Exact loading skeletons, empty states, and toast wording.
- Whether chat streaming reaches the browser via SSE or WebSocket, as long as it is reliable, testable, and fits the later call architecture.
- Exact visual treatment of contextual message menus, stale flags, and alternate-greeting controls, subject to the UI-SPEC.

### Deferred Ideas (OUT OF SCOPE)
- Voice Lab upload/transcription/synthesis and Voice Library management belong to Phase 2.
- WebRTC call transport, AudioContext unlock, call toolbar, and call-summary writeback belong to Phase 3.
- Barge-in, live captions, and Voice Visualizer state polish belong to Phase 4.
- Multi-engine voice breadth, per-chat voice override UI, and saved audio replay belong to Phase 5, though schema hooks should exist now.
- PWA install polish, Wake Lock, Bluetooth routing, storage retention controls, and mobile hardening belong to Phase 6.
- v3 PNG export, lorebook injection, thread search, gallery search/filtering, waveform scrubber, and per-thread LLM sampling overrides remain v1.x or later per requirements.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-01 | Three independently configurable LAN services: Web UI host, AI backend, LLM server. | Three-service responsibility map, health endpoints, Settings connection tests, and environment audit. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-03 | Runtime-configurable OpenAI-compatible streaming Chat Completions endpoint. | FastAPI server-side proxy with OpenAI Python async streaming; settings keep endpoint/key/model server-side. [VERIFIED: .planning/REQUIREMENTS.md] [CITED: Context7 /openai/openai-python] |
| REQ-04 | LAN trust posture explicit; original requirement says bind `0.0.0.0` with no auth. | Phase 1 context D-12 overrides default binding to explicit LAN host/IP, with no auth and visible LAN-trust guidance. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md] |
| REQ-10 | Character Gallery lists characters and actions. | UI-SPEC screen contract drives Svelte components and API list/delete/export endpoints. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-UI-SPEC.md] |
| REQ-11 | Character Editor exposes SillyTavern v2/v3 fields and portrait upload. | Internal v3-shaped Pydantic model, raw-source preservation, file-backed portraits, full editor field list. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-12 | Character create/edit/delete, with delete preserving chat threads. | Soft-delete/detached snapshot pattern; threads store historical character snapshot. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md] |
| REQ-13 | Import v2/v3 JSON and PNG cards, `ccv3` before `chara`. | Pillow metadata plus manual PNG tEXt chunk audit; normalize to v3-shaped model and preserve original JSON. [VERIFIED: .planning/REQUIREMENTS.md] [CITED: https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md] [CITED: Context7 /python-pillow/pillow] |
| REQ-14 | Export v2 JSON in v1. | Export from preserved normalized model plus raw-source metadata; v3 PNG export remains out of scope. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-16 | Preserve lorebook/world-info but do not inject it. | Schema stores lorebook payload and UI displays "present, not used in v1"; prompt builder excludes it. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-17 | Alternate greetings picker for new chat. | Opening AI message alternate model and selected-greeting UI before first user message. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-30 | Chronological chat thread with streaming LLM tokens. | Unified `messages` table, streaming transport, browser token rendering, final atomic persist. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-31 | Persist `first_mes` or selected alternate as opening AI message. | Thread creation inserts the opening `ai_text` message before user input. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-32 | Regenerate last AI turn by replacing selected response. | `message_alternates` with selected alternate; regeneration updates selected canonical content rather than appending a visible turn. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md] |
| REQ-33 | Edit previous turn and mark downstream stale. | Message rows include edit lineage and stale markers; continue flow asks truncate-or-keep. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-34 | Swipes store AI alternates and selected branch. | Alternates table and prompt-context builder include only selected alternate. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-35 | Continue extends previous AI turn with optional composer instruction. | Chat API supports a `continue` operation using composer text as extension instruction/prefix. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-36 | Virtualize message list around 500 messages and show jump-to-latest. | Use TanStack Svelte Virtual for long chat lists; Playwright verifies scroll stability. [VERIFIED: npm registry 2026-04-24] |
| REQ-60 | Unified chronological message table with text and future call kinds. | Day-one `messages.message_kind` enum/check constraint includes six required values. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-70 | Home shows recent threads sorted by activity. | Threads API and Home list contract from UI-SPEC. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-UI-SPEC.md] |
| REQ-71 | Threads support rename/delete. | Threads API plus Home row contextual menu and destructive confirmations. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-72 | Home can start chat with any character. | Home routes to Gallery or chat creation flow using Character Gallery as import/start entry. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-UI-SPEC.md] |
| REQ-90 (partial) | Implement True Dark Phase 1 screens. | UI-SPEC locks local Svelte components, tokens, shell, Home, Gallery, Editor, Chat, Settings. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-UI-SPEC.md] |
| REQ-A0 (partial) | Mobile LAN browser usability for Phase 1 text surfaces. | HTTPS secure-context checks, responsive UI, mobile Playwright coverage; mic/call behavior remains later phases. [VERIFIED: .planning/REQUIREMENTS.md] |
| REQ-A1 | HTTPS trusted LAN certificate. | Reuse Phase 0 mkcert workflow; Settings checks `window.isSecureContext` and `navigator.mediaDevices`. [VERIFIED: .planning/phases/00-measurement-gate/HTTPS-SETUP.md] [CITED: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts] |
</phase_requirements>

## Summary

Phase 1 is a scaffold plus vertical slice: build `web-ui/client`, `web-ui/server`, `ai-backend`, and `llm` documentation/config, then prove the app can import a SillyTavern card, create a thread, stream an OpenAI-compatible text reply over HTTPS, atomically persist the final message, reload, and continue. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md]

The stack is locked by prior decisions: SvelteKit 2/Svelte 5 static client, FastAPI API/static host, SQLite plus filesystem blobs, server-side OpenAI-compatible LLM proxy, and an AI-backend FastAPI health stub. Versions below were checked against npm/PyPI on 2026-04-24 and are newer than the broad versions in earlier local research. [VERIFIED: .planning/research/STACK.md] [VERIFIED: npm registry 2026-04-24] [VERIFIED: PyPI JSON API 2026-04-24]

**Primary recommendation:** Plan the first implementation wave around contracts: migrations/schema, character-card parser, sanitizer, LLM streaming proxy, health/settings contracts, and message-action semantics before heavy UI polish. [VERIFIED: .planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md]

## Project Constraints

No `AGENTS.md` or `CLAUDE.md` exists in the repository root, so there are no extra project-specific root instruction files to apply. [VERIFIED: `find . -maxdepth 2 -name AGENTS.md -o -name CLAUDE.md`]

No `.claude/skills/` or `.agents/skills/` project skill directory exists; only `.claude/agents` and `.claude/commands` are present. [VERIFIED: `find . -maxdepth 3 -type d`]

No production `src/`, `web-ui/`, or `ai-backend/` code exists yet; Phase 1 owns the first production scaffold. [VERIFIED: `rg --files`]

The knowledge graph file `.planning/graphs/graph.json` is absent, so no graph-derived relationships were available. [VERIFIED: `ls .planning/graphs/graph.json`]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| HTTPS LAN serving | API / Backend | Browser / Client | FastAPI host owns TLS/static serving; browser verifies secure context and media-device visibility. [VERIFIED: 01-CONTEXT.md] |
| App shell and Phase 1 screens | Browser / Client | API / Backend | SvelteKit static client owns Home/Gallery/Editor/Chat/Settings UI; backend provides persisted state and health/settings APIs. [VERIFIED: 01-UI-SPEC.md] |
| Durable character/thread/message state | Database / Storage | API / Backend | SQLite and filesystem blobs are the source of truth; FastAPI mediates all writes. [VERIFIED: 01-CONTEXT.md] |
| Character-card import/export | API / Backend | Browser / Client | Backend parses, validates, normalizes, and stores untrusted cards; browser renders sanitized previews and warnings. [VERIFIED: REQUIREMENTS.md] |
| Text streaming loop | API / Backend | Browser / Client | FastAPI proxies OpenAI-compatible streaming and hides credentials; browser renders token updates and cancellation UI. [VERIFIED: 01-CONTEXT.md] |
| AI-backend Phase 1 health | API / Backend | Browser / Client | `ai-backend` only exposes `/health` for Settings tests in this phase. [VERIFIED: 01-CONTEXT.md] |
| LLM endpoint configuration | API / Backend | Browser / Client | Endpoint/key/model stay server-side; Settings UI edits configuration and triggers tests. [VERIFIED: REQUIREMENTS.md] |
| Blob storage and cleanup | Database / Storage | API / Backend | Portrait files live on disk, with SQLite metadata and atomic write/orphan cleanup coordinated by backend code. [VERIFIED: 01-CONTEXT.md] |
| Markdown/card rendering safety | Browser / Client | API / Backend | Browser must sanitize rendered Markdown; backend still validates import payloads and stores raw content as untrusted data. [CITED: Context7 /markedjs/marked] [CITED: Context7 /cure53/dompurify] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@sveltejs/kit` | 2.58.0, published 2026-04-23 | Static app framework and routing for `web-ui/client`. | Locked by context; adapter-static supports SPA fallback for static hosting. [VERIFIED: npm registry 2026-04-24] [CITED: Context7 /sveltejs/kit] |
| `svelte` | 5.55.5, published 2026-04-23 | Component/runtime layer. | Locked by context and UI-SPEC. [VERIFIED: npm registry 2026-04-24] |
| `@sveltejs/adapter-static` | 3.0.10, published 2025-10-02 | Build static client assets served by FastAPI. | SvelteKit docs support static SPA fallback with `fallback: '200.html'`. [VERIFIED: npm registry 2026-04-24] [CITED: Context7 /sveltejs/kit] |
| `vite` | 8.0.10, published 2026-04-23 | Frontend dev/build tool. | SvelteKit uses Vite-based builds. [VERIFIED: npm registry 2026-04-24] |
| `fastapi` | 0.136.1, uploaded 2026-04-23 | API/static host and AI-backend health stub. | Provides ASGI APIs, uploads, CORS middleware, `StreamingResponse`, static serving, and test client. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /fastapi/fastapi] |
| `uvicorn` | 0.46.0, uploaded 2026-04-23 | ASGI server for FastAPI services. | Standard FastAPI runtime server; supports HTTPS process configuration. [VERIFIED: PyPI JSON API 2026-04-24] |
| `sqlalchemy` | 2.0.49, uploaded 2026-04-03 | Async ORM/core for SQLite. | SQLAlchemy 2 async engine/session patterns cover `sqlite+aiosqlite`. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /websites/sqlalchemy_en_20] |
| `aiosqlite` | 0.22.1, uploaded 2025-12-23 | Async SQLite DBAPI for SQLAlchemy. | Required async driver for `sqlite+aiosqlite:///...`. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /websites/sqlalchemy_en_20] |
| `alembic` | 1.18.4, uploaded 2026-02-10 | Reproducible schema migrations. | Alembic autogenerate and command API support migration-first planning. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /websites/alembic_sqlalchemy] |
| `pydantic` | 2.13.3, uploaded 2026-04-20 | API/settings/card/message contracts. | Pydantic v2 supports explicit extra-field policies for safe parsing. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /pydantic/pydantic] |
| `openai` | 2.32.0, uploaded 2026-04-15 | OpenAI-compatible async streaming client. | `AsyncOpenAI` streaming API fits server-side proxying. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /openai/openai-python] |
| `pillow` | 12.2.0, uploaded 2026-04-01 | PNG image metadata and portrait validation. | Pillow exposes PNG text metadata and image decoding; do not hand-roll image decoding. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /python-pillow/pillow] |
| `marked` | 18.0.2, published 2026-04-18 | Markdown rendering for card/chat prose. | Marked explicitly does not sanitize HTML, so pair it with DOMPurify. [VERIFIED: npm registry 2026-04-24] [CITED: Context7 /markedjs/marked] |
| `dompurify` | 3.4.1, published 2026-04-21 | Browser-side HTML sanitization. | DOMPurify removes dangerous HTML/event handlers from rendered markup. [VERIFIED: npm registry 2026-04-24] [CITED: Context7 /cure53/dompurify] |
| `lucide-svelte` | 1.0.1, published 2026-03-23 | Icon components. | UI-SPEC locks `lucide-svelte` and local components. [VERIFIED: npm registry 2026-04-24] [VERIFIED: 01-UI-SPEC.md] |
| `@tanstack/svelte-virtual` | 3.13.24, published 2026-04-17 | Chat message virtualization. | Avoid bespoke long-list virtualization around the 500-message threshold. [VERIFIED: npm registry 2026-04-24] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-multipart` | 0.0.26, uploaded 2026-04-10 | File upload parsing for FastAPI. | Required for JSON/PNG card import and portrait upload endpoints. [VERIFIED: PyPI JSON API 2026-04-24] [CITED: Context7 /fastapi/fastapi] |
| `httpx` | 0.28.1, uploaded 2024-12-06 | Async HTTP tests or non-SDK endpoint probes. | Use for AI-backend/LLM connection tests if the OpenAI SDK path cannot cover a probe. [VERIFIED: PyPI JSON API 2026-04-24] |
| `pytest` | 9.0.3, uploaded 2026-04-07 | Backend test framework. | Contract-heavy backend tests for migrations, parser, sanitizer, streaming proxy, and message actions. [VERIFIED: PyPI JSON API 2026-04-24] |
| `pytest-asyncio` | 1.3.0, uploaded 2025-11-10 | Async backend tests. | Use for async SQLAlchemy/FastAPI streaming tests. [VERIFIED: PyPI JSON API 2026-04-24] |
| `ruff` | 0.15.11, uploaded 2026-04-16 | Python lint/format. | Use as the backend code-quality gate once scaffolding exists. [VERIFIED: PyPI JSON API 2026-04-24] |
| `vitest` | 4.1.5, published 2026-04-21 | Frontend unit/component tests. | Use with a DOM environment for sanitizer and UI state tests. [VERIFIED: npm registry 2026-04-24] [CITED: Context7 /vitest-dev/vitest] |
| `happy-dom` | 20.9.0, published 2026-04-13 | Vitest DOM environment. | Prefer for fast DOM tests unless a browser-only API requires jsdom/Playwright. [VERIFIED: npm registry 2026-04-24] [CITED: Context7 /vitest-dev/vitest] |
| `@playwright/test` | 1.59.1, published 2026-04-01 | Browser/mobile E2E and visual checks. | Use for HTTPS path smoke, responsive Home/Chat, import-chat-reload flow, and mobile viewport checks. [VERIFIED: npm registry 2026-04-24] [CITED: Context7 /microsoft/playwright] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `StreamingResponse` text/SSE-style stream | WebSocket | WebSocket is useful for future bidirectional realtime calls, but Phase 1 text streaming is request/response and simpler to test as a FastAPI streaming response. [CITED: Context7 /fastapi/fastapi] [ASSUMED] |
| `@tanstack/svelte-virtual` | Custom scroll windowing | Custom virtualization risks scroll-position bugs during streaming and stale/edit UI; use the maintained virtualizer unless it conflicts with Svelte 5 during implementation. [VERIFIED: npm registry 2026-04-24] [ASSUMED] |
| SQLAlchemy + Alembic | Direct `sqlite3` SQL strings only | Direct SQL is acceptable inside migrations, but day-one schema and async APIs need typed models, sessions, and reproducible migration commands. [CITED: Context7 /websites/sqlalchemy_en_20] [CITED: Context7 /websites/alembic_sqlalchemy] |
| DOMPurify + Marked | Raw `{@html}` / regex stripping | Marked docs warn it does not sanitize output; regex sanitizers miss XSS vectors. [CITED: Context7 /markedjs/marked] [CITED: Context7 /cure53/dompurify] |

**Installation:**

```bash
npm --prefix web-ui/client install @sveltejs/kit@2.58.0 svelte@5.55.5 @sveltejs/adapter-static@3.0.10 vite@8.0.10 lucide-svelte@1.0.1 marked@18.0.2 dompurify@3.4.1 @tanstack/svelte-virtual@3.13.24
npm --prefix web-ui/client install -D vitest@4.1.5 happy-dom@20.9.0 @playwright/test@1.59.1
uv add --project web-ui/server fastapi==0.136.1 uvicorn==0.46.0 sqlalchemy==2.0.49 aiosqlite==0.22.1 alembic==1.18.4 pydantic==2.13.3 openai==2.32.0 pillow==12.2.0 python-multipart==0.0.26 httpx==0.28.1
uv add --project web-ui/server --dev pytest==9.0.3 pytest-asyncio==1.3.0 ruff==0.15.11
```

**Version verification:** Package versions above were checked with `npm view <package> version time --json` and PyPI JSON metadata on 2026-04-24. [VERIFIED: npm registry 2026-04-24] [VERIFIED: PyPI JSON API 2026-04-24]

## Architecture Patterns

### System Architecture Diagram

```text
Android/Desktop Browser
  |
  | HTTPS GET static app, /api requests, streaming chat response
  v
web-ui/server: FastAPI API + static host + TLS
  |
  +--> /health, /api/settings/test-web
  |
  +--> Settings connection tests
  |      |
  |      +--> ai-backend /health over HTTPS
  |      +--> External OpenAI-compatible LLM probe
  |
  +--> Character import/export
  |      |
  |      +--> JSON/PNG parser -> Pydantic validation -> normalized v3-shaped model
  |      +--> filesystem portrait blob write -> SQLite metadata
  |
  +--> Chat actions
  |      |
  |      +--> SQLite threads/messages/message_alternates
  |      +--> prompt context builder selects non-stale selected branch
  |      +--> OpenAI-compatible streaming Chat Completions
  |      +--> token stream to browser -> final atomic DB update
  |
  +--> StaticFiles serves SvelteKit adapter-static build
```

This diagram follows the locked topology: the browser never calls the LLM directly, the AI backend is health-only in Phase 1, and durable app state belongs to the FastAPI web host. [VERIFIED: 01-CONTEXT.md]

### Recommended Project Structure

```text
web-ui/
├── client/
│   ├── src/routes/              # SvelteKit app shell and screens
│   ├── src/lib/components/      # Local Stitch-derived components
│   ├── src/lib/api/             # Typed API wrappers and stream readers
│   ├── src/lib/sanitizer/       # marked + DOMPurify rendering boundary
│   ├── static/                  # Manifest, icons, static assets
│   └── tests/                   # Vitest unit/component tests
├── server/
│   ├── app/main.py              # FastAPI app factory/static mount
│   ├── app/api/                 # health, settings, characters, threads, chat
│   ├── app/domain/              # card parsing, prompt building, chat actions
│   ├── app/storage/             # SQLAlchemy models, sessions, blob store
│   ├── alembic/                 # SQLite migrations
│   ├── data/                    # local SQLite DB and blobs, gitignored
│   └── tests/                   # pytest contract tests
ai-backend/
├── app/main.py                  # FastAPI /health stub
└── tests/                       # health test
llm/
└── README.md                    # External OpenAI-compatible endpoint setup notes
```

The exact inner folder names are discretionary, but the service boundaries are not: `web-ui/server` owns data, TLS, static serving, and LLM proxying; `web-ui/client` owns UI; `ai-backend` owns only `/health` in this phase. [VERIFIED: 01-CONTEXT.md]

### Pattern 1: Static SvelteKit Client Served by FastAPI

**What:** Build the SvelteKit client with `adapter-static` and SPA fallback, then mount the output through FastAPI `StaticFiles`. [CITED: Context7 /sveltejs/kit] [CITED: Context7 /fastapi/fastapi]

**When to use:** Phase 1 because SvelteKit server runtime is not the source of truth; FastAPI owns API, TLS, static hosting, SQLite, and LLM proxying. [VERIFIED: 01-CONTEXT.md]

**Example:**

```js
// web-ui/client/svelte.config.js
// Source: Context7 /sveltejs/kit adapter-static docs
import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: '200.html'
    })
  }
};
```

```js
// web-ui/client/src/routes/+layout.js
// Source: Context7 /sveltejs/kit SPA mode docs
export const ssr = false;
```

### Pattern 2: FastAPI Streaming Proxy

**What:** Use a FastAPI endpoint that yields stream chunks from the OpenAI-compatible async client to the browser; persist final AI text only after completion. [CITED: Context7 /fastapi/fastapi] [CITED: Context7 /openai/openai-python] [VERIFIED: 01-CONTEXT.md]

**When to use:** All Phase 1 text chat sends, regenerates, swipes, and continue actions. [VERIFIED: REQUIREMENTS.md]

**Example:**

```python
# Source: Context7 /fastapi/fastapi StreamingResponse and /openai/openai-python async streaming
from collections.abc import AsyncIterator
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

router = APIRouter()

async def token_events(client: AsyncOpenAI, messages: list[dict[str, str]]) -> AsyncIterator[bytes]:
    final: list[str] = []
    async with client.chat.completions.stream(
        model="configured-model",
        messages=messages,
    ) as stream:
        async for event in stream:
            if event.type == "content.delta":
                final.append(event.delta)
                yield f"data: {event.delta}\n\n".encode("utf-8")
    # Store ''.join(final) in the same operation boundary that marks stream completion.

@router.post("/api/chat/{thread_id}/send")
async def send_message(thread_id: str, client: AsyncOpenAI = Depends(...)) -> StreamingResponse:
    messages = await build_prompt_context(thread_id)
    return StreamingResponse(token_events(client, messages), media_type="text/event-stream")
```

Planning implication: the actual implementation should pass configured `base_url`, API key, and model from persisted settings, not hard-coded values. [VERIFIED: REQUIREMENTS.md]

### Pattern 3: Async SQLAlchemy With SQLite

**What:** Use `create_async_engine("sqlite+aiosqlite:///...")`, `async_sessionmaker`, and Alembic migrations. [CITED: Context7 /websites/sqlalchemy_en_20] [CITED: Context7 /websites/alembic_sqlalchemy]

**When to use:** All Phase 1 persistent state: characters, source cards, assets, settings, threads, messages, and alternates. [VERIFIED: 01-CONTEXT.md]

**Schema planning baseline:**

```sql
-- Source: Phase requirements and context, not an external schema standard.
CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES threads(id),
  parent_message_id TEXT REFERENCES messages(id),
  message_kind TEXT NOT NULL CHECK (
    message_kind IN ('user_text', 'ai_text', 'user_speech', 'ai_speech', 'call_start', 'call_end')
  ),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'event')),
  sequence INTEGER NOT NULL,
  content_text TEXT,
  selected_alternate_id TEXT,
  edited_from_message_id TEXT REFERENCES messages(id),
  stale_after_edit INTEGER NOT NULL DEFAULT 0,
  branch_root_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE message_alternates (
  id TEXT PRIMARY KEY,
  message_id TEXT NOT NULL REFERENCES messages(id),
  alternate_index INTEGER NOT NULL,
  content_text TEXT NOT NULL,
  source_action TEXT NOT NULL CHECK (source_action IN ('first_mes', 'regenerate', 'swipe', 'continue')),
  created_at TEXT NOT NULL,
  UNIQUE (message_id, alternate_index)
);
```

Planning implication: exact column names can change, but the first migration must support six `message_kind` values, selected AI alternates, edit lineage, stale downstream turns, and chronological rendering. [VERIFIED: REQUIREMENTS.md] [VERIFIED: 01-CONTEXT.md]

### Pattern 4: Character Card Parse Boundary

**What:** Parse file bytes on the backend, detect JSON vs PNG, prefer `ccv3` over `chara`, base64-decode embedded JSON, validate through Pydantic, normalize into an internal v3-shaped model, and preserve original JSON. [VERIFIED: REQUIREMENTS.md] [CITED: https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md] [CITED: Context7 /python-pillow/pillow] [CITED: Context7 /pydantic/pydantic]

**When to use:** Import flow, editor review, v2 JSON export, malicious-card tests. [VERIFIED: REQUIREMENTS.md]

**Example:**

```python
# Source: Pillow PNG text metadata docs plus Phase 1 ccv3/chara decision.
import base64
import json
from PIL import Image

PNG_KEYS_IN_ORDER = ("ccv3", "chara")

def parse_png_card(path: str) -> dict:
    with Image.open(path) as image:
        metadata = dict(image.text)

    for key in PNG_KEYS_IN_ORDER:
        if key in metadata:
            raw = base64.b64decode(metadata[key], validate=True)
            return json.loads(raw.decode("utf-8"))

    raise ValueError("PNG does not contain a supported character-card chunk")
```

Planning implication: add a small manual PNG chunk-walk test fixture too, because local research flags PNG tEXt key handling as a pitfall and Pillow metadata should not be the only assertion of precedence behavior. [VERIFIED: .planning/research/STACK.md] [VERIFIED: .planning/research/PITFALLS.md]

### Pattern 5: Sanitized Markdown Rendering

**What:** Convert card/chat Markdown to HTML and then sanitize with DOMPurify before any `{@html}` usage. [CITED: Context7 /markedjs/marked] [CITED: Context7 /cure53/dompurify]

**When to use:** Character descriptions, first messages, example messages, chat bubbles, import preview warnings. [VERIFIED: 01-CONTEXT.md]

**Example:**

```ts
// Source: Marked docs warn output is not sanitized; DOMPurify docs sanitize HTML.
import { marked } from 'marked';
import DOMPurify from 'dompurify';

export function renderTrustedMarkdown(untrustedMarkdown: string): string {
  const html = marked.parse(untrustedMarkdown, { async: false }) as string;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'a'],
    ALLOWED_ATTR: ['href', 'title'],
    ALLOW_DATA_ATTR: false
  });
}
```

Planning implication: the function name should make the boundary explicit; the input is untrusted, the returned HTML is what may be rendered. [CITED: Context7 /markedjs/marked] [CITED: Context7 /cure53/dompurify]

### Pattern 6: Atomic Filesystem Blob Writes

**What:** Store binary portraits on disk via write-to-temp-in-same-directory, fsync, `os.replace`, then commit SQLite metadata; run an orphan reaper for stale temp/unreferenced blobs. [VERIFIED: .planning/research/PITFALLS.md]

**When to use:** Character portrait upload/import and future audio blob compatibility. [VERIFIED: 01-CONTEXT.md]

**Example:**

```python
# Source: .planning/research/PITFALLS.md storage pattern; implementation detail uses Python stdlib.
import os
import tempfile
from pathlib import Path

def atomic_write_blob(blob_dir: Path, final_name: str, data: bytes) -> Path:
    blob_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{final_name}.", suffix=".tmp", dir=blob_dir)
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        final_path = blob_dir / final_name
        os.replace(tmp_name, final_path)
        return final_path
    except Exception:
        try:
            os.unlink(tmp_name)
        finally:
            raise
```

### Anti-Patterns to Avoid

- **Browser calls LLM directly:** Leaks endpoint/key/model details and contradicts the server-side proxy decision. [VERIFIED: 01-CONTEXT.md]
- **Raw card HTML in Svelte `{@html}`:** Marked output is not sanitized, and card fields are untrusted. [CITED: Context7 /markedjs/marked] [VERIFIED: 01-CONTEXT.md]
- **`Access-Control-Allow-Origin: *`:** Phase context explicitly forbids wildcard app API origins. [VERIFIED: 01-CONTEXT.md]
- **Default `0.0.0.0` bind:** Phase context D-12 overrides the older requirement wording; default to explicit configured LAN host/IP. [VERIFIED: 01-CONTEXT.md] [VERIFIED: REQUIREMENTS.md]
- **Cascading character delete into thread history:** Phase 1 must preserve chats when a character is deleted. [VERIFIED: REQUIREMENTS.md]
- **Persisting partial AI tokens as final messages:** Context D-28 requires token rendering followed by final atomic persistence. [VERIFIED: 01-CONTEXT.md]
- **Lorebook injection in Phase 1:** Lorebook/world-info is preserved and surfaced, not used in LLM context. [VERIFIED: REQUIREMENTS.md]
- **Treating Stitch HTML as source-of-truth app code:** UI-SPEC says to use Stitch as visual/layout reference while removing fake account/billing/logout/noise and building local Svelte components. [VERIFIED: 01-UI-SPEC.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP API, uploads, CORS, static serving, streaming responses | Custom ASGI/router glue | FastAPI + Starlette primitives | FastAPI documents `UploadFile`, CORS middleware, `StreamingResponse`, `StaticFiles`, and test support. [CITED: Context7 /fastapi/fastapi] |
| Schema migration history | Manual one-off SQL init script only | Alembic | Phase 1 needs reproducible migrations and future schema evolution. [CITED: Context7 /websites/alembic_sqlalchemy] [VERIFIED: 01-CONTEXT.md] |
| Async DB session management | Ad hoc global SQLite connections | SQLAlchemy async + aiosqlite | SQLAlchemy provides documented async engine/session patterns. [CITED: Context7 /websites/sqlalchemy_en_20] |
| Markdown sanitization | Regex stripping or trust card HTML | Marked + DOMPurify | Marked does not sanitize; DOMPurify removes dangerous HTML. [CITED: Context7 /markedjs/marked] [CITED: Context7 /cure53/dompurify] |
| LLM streaming protocol | Browser direct fetch to LLM or raw socket framing | Server-side OpenAI Python async streaming proxy | Keeps credentials server-side and matches OpenAI-compatible requirement. [VERIFIED: REQUIREMENTS.md] [CITED: Context7 /openai/openai-python] |
| Image decoding | Manual PNG image decoder | Pillow | Pillow opens PNGs and exposes text metadata; only the card chunk selection logic should be custom. [CITED: Context7 /python-pillow/pillow] |
| Long chat virtualization | Custom scroll math | `@tanstack/svelte-virtual` | Maintained virtualizer is safer for 500+ message lists than custom row windowing. [VERIFIED: npm registry 2026-04-24] [ASSUMED] |
| Browser E2E/mobile checks | Manual clicking only | Playwright | Playwright supports device emulation and screenshot/browser checks. [CITED: Context7 /microsoft/playwright] |

**Key insight:** The hard parts in this phase are contracts and boundaries, not UI quantity: untrusted card input, durable schema semantics, streaming-finalization state, and LAN exposure all become expensive if they are improvised after the UI exists. [VERIFIED: .planning/research/PITFALLS.md] [VERIFIED: 01-CONTEXT.md]

## Common Pitfalls

### Pitfall 1: HTTPS Certificate Looks Valid but Browser APIs Still Fail

**What goes wrong:** Mobile appears to load the app, but secure-context-dependent APIs remain unavailable or Android trust differs from desktop trust. [VERIFIED: .planning/phases/00-measurement-gate/HTTPS-SETUP.md] [CITED: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts]

**Why it happens:** Certificate trust, hostname/IP SANs, and browser secure-context classification are separate checks. [CITED: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts]

**How to avoid:** Reuse the Phase 0 mkcert workflow, test the known direct LAN URL path, and show `window.isSecureContext` plus `navigator.mediaDevices` in Settings/Home. [VERIFIED: 01-CONTEXT.md] [VERIFIED: .planning/phases/00-measurement-gate/results/https_android.json]

**Warning signs:** `window.isSecureContext === false`, `navigator.mediaDevices` missing, Android Chrome warning page, or testing only `localhost`. [VERIFIED: 01-CONTEXT.md]

### Pitfall 2: Card XSS Enters Through Import Preview or Chat Bubbles

**What goes wrong:** Malicious card fields execute script or unsafe HTML when previewed or rendered in chat. [VERIFIED: .planning/research/PITFALLS.md]

**Why it happens:** Marked parses Markdown but does not sanitize the output HTML. [CITED: Context7 /markedjs/marked]

**How to avoid:** Treat every card-rendered field as untrusted, sanitize with DOMPurify after Markdown rendering, and add fixtures with event handlers, script tags, and dangerous URLs. [CITED: Context7 /cure53/dompurify] [VERIFIED: 01-CONTEXT.md]

**Warning signs:** Direct `{@html card.description}`, sanitizer bypasses in component code, or tests that assert only happy-path Markdown. [VERIFIED: .planning/research/PITFALLS.md]

### Pitfall 3: v2/v3 Card Parsing Loses Data or Picks Wrong PNG Chunk

**What goes wrong:** Cards with both `ccv3` and `chara` import as v2, lorebook data disappears, or malformed base64 crashes parsing. [VERIFIED: REQUIREMENTS.md]

**Why it happens:** PNG card formats encode JSON into metadata keys, and Phase 1 must prefer v3 while preserving raw source JSON. [VERIFIED: REQUIREMENTS.md] [CITED: https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md]

**How to avoid:** Detect JSON vs PNG by content, prefer `ccv3`, fall back to `chara`, base64-decode strictly, validate sizes, normalize internally, store raw JSON, and warn on ignored/invalid fields. [VERIFIED: 01-CONTEXT.md]

**Warning signs:** Parser returns only editor fields with no raw source, no precedence test for `ccv3` + `chara`, or lorebook fields missing from stored records. [VERIFIED: REQUIREMENTS.md]

### Pitfall 4: CORS/WebSocket Origin Policy Is Overbroad

**What goes wrong:** Any origin on the LAN can call app APIs or future sockets. [VERIFIED: 01-CONTEXT.md]

**Why it happens:** Development defaults often allow wildcard origins. [CITED: Context7 /fastapi/fastapi]

**How to avoid:** Configure explicit origin allowlists, reject unknown `Origin` values, and carry the same rule into future WebSocket endpoints. OWASP's WebSocket guidance specifically calls for origin validation. [VERIFIED: 01-CONTEXT.md] [CITED: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html]

**Warning signs:** `allow_origins=["*"]`, missing origin tests, or local IP/hostname variants not represented in config. [VERIFIED: 01-CONTEXT.md]

### Pitfall 5: LAN Bind Exposes More Than Intended

**What goes wrong:** The app starts on every network interface without auth and becomes reachable outside the intended LAN path. [VERIFIED: REQUIREMENTS.md] [VERIFIED: 01-CONTEXT.md]

**Why it happens:** REQ-04 says `0.0.0.0`, but Phase 1 context later locks explicit LAN bind as the safer default. [VERIFIED: REQUIREMENTS.md] [VERIFIED: 01-CONTEXT.md]

**How to avoid:** Plan a config variable for host/IP, refuse silent wildcard defaults, and show setup guidance when host/IP is missing. [VERIFIED: 01-CONTEXT.md]

**Warning signs:** `host="0.0.0.0"` hard-coded in dev scripts or tests that only check local startup. [VERIFIED: .planning/research/PITFALLS.md]

### Pitfall 6: Message Actions Do Not Match Durable Schema

**What goes wrong:** Regenerate appends duplicate visible AI turns, swipes are UI-only, edit loses stale lineage, or Continue cannot distinguish extending from sending a new message. [VERIFIED: REQUIREMENTS.md]

**Why it happens:** Chat UX actions look simple but require branch/alternate/edit semantics in storage. [VERIFIED: 01-CONTEXT.md]

**How to avoid:** Implement schema/migration tests before UI tasks; define action contracts for send, regenerate, swipe, edit, truncate, keep-stale, and continue. [VERIFIED: 01-CONTEXT.md]

**Warning signs:** Only one `messages.content` field with no alternate/stale metadata, or prompt builder that includes all swipe alternates. [VERIFIED: REQUIREMENTS.md]

### Pitfall 7: Blob Writes Leave Orphans or Broken References

**What goes wrong:** Imported portraits point at missing files, temp files pile up, or DB rows commit when file writes fail. [VERIFIED: .planning/research/PITFALLS.md]

**Why it happens:** Filesystem writes and SQLite transactions are not one atomic transaction. [ASSUMED]

**How to avoid:** Write temp files in the same directory, `os.replace` only after successful write/fsync, commit DB metadata after final file placement, and run an orphan reaper. [VERIFIED: .planning/research/PITFALLS.md]

**Warning signs:** Direct writes to final filenames, no cleanup command/test, or no failure-mode tests for upload interruption. [VERIFIED: .planning/research/PITFALLS.md]

### Pitfall 8: Roadmap LLM `/health` Conflicts With External LLM Boundary

**What goes wrong:** Planner tries to implement a local LLM service health endpoint even though Phase 1 says `llm/` is docs/config only. [VERIFIED: ROADMAP.md] [VERIFIED: 01-CONTEXT.md]

**Why it happens:** Roadmap success criteria mention three services answering `/health`, while context D-06 locks external OpenAI-compatible LLM with no RayMe-shipped inference server. [VERIFIED: ROADMAP.md] [VERIFIED: 01-CONTEXT.md]

**How to avoid:** Treat `web-ui/server /health` and `ai-backend /health` as RayMe-owned endpoints, and implement LLM status as a Settings connection test against the configured OpenAI-compatible endpoint. [VERIFIED: 01-CONTEXT.md] [ASSUMED]

**Warning signs:** Creating a third local FastAPI LLM server in `llm/` or failing acceptance because an external provider lacks `/health`. [VERIFIED: 01-CONTEXT.md] [ASSUMED]

## Code Examples

Verified patterns from official/local sources are included in Architecture Patterns. Additional focused snippets:

### Explicit CORS Allowlist

```python
# Source: Context7 /fastapi/fastapi CORSMiddleware docs and Phase 1 D-13
from fastapi.middleware.cors import CORSMiddleware

def configure_cors(app, allowed_origins: list[str]) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
```

### Browser Stream Reader Boundary

```ts
// Source: Phase 1 streaming requirement; browser stream handling is an implementation recommendation.
export async function readChatStream(response: Response, onToken: (token: string) => void) {
  if (!response.body) throw new Error('No response stream');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    for (const line of chunk.split('\n')) {
      if (line.startsWith('data: ')) onToken(line.slice(6));
    }
  }
}
```

This stream reader shape is `[ASSUMED]` until implementation validates the exact wire format chosen by the FastAPI endpoint.

### Pydantic Strict Import Model Boundary

```python
# Source: Context7 /pydantic/pydantic extra-field behavior
from pydantic import BaseModel, ConfigDict

class CharacterCardV3(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_mes: str | None = None
```

Planning implication: use `extra="allow"` at the source-card boundary to preserve unknown card fields, then map only supported fields into the internal normalized model and warnings. [CITED: Context7 /pydantic/pydantic] [VERIFIED: 01-CONTEXT.md]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Broad version ranges from earlier research | Pin current npm/PyPI versions during scaffold | Verified 2026-04-24 | Planner should avoid stale package assumptions. [VERIFIED: npm registry 2026-04-24] [VERIFIED: PyPI JSON API 2026-04-24] |
| SvelteKit as an SSR server | SvelteKit static SPA served by FastAPI | Locked by Phase 1 context | No SvelteKit server-side app logic should be planned for Phase 1. [VERIFIED: 01-CONTEXT.md] [CITED: Context7 /sveltejs/kit] |
| Browser-to-LLM calls | Server-side LLM streaming proxy | Locked by Phase 1 context | API key/model/base URL remain server-side. [VERIFIED: 01-CONTEXT.md] |
| Raw Markdown rendering | Marked output sanitized with DOMPurify | Verified from current docs | Every `{@html}` use needs sanitizer provenance. [CITED: Context7 /markedjs/marked] [CITED: Context7 /cure53/dompurify] |
| SQLite rollback-journal default assumptions | Consider WAL for concurrent read/write app use | SQLite WAL docs current | WAL can improve read/write concurrency, but should be enabled deliberately and tested on local filesystem. [CITED: https://www.sqlite.org/wal.html] [ASSUMED] |

**Deprecated/outdated:**
- Treating `0.0.0.0` as the default bind is outdated for this phase because D-12 locks explicit LAN bind by default. [VERIFIED: REQUIREMENTS.md] [VERIFIED: 01-CONTEXT.md]
- Treating v3 PNG export as Phase 1 scope is outdated; Phase 1 only ships v2 JSON export. [VERIFIED: REQUIREMENTS.md]
- Treating lorebook data as prompt context is out of scope; Phase 1 preserves and surfaces it only. [VERIFIED: REQUIREMENTS.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SSE/fetch-style streaming is sufficient for Phase 1 text streaming and preferable to WebSocket for testability. | Standard Stack, Architecture Patterns | If later call architecture requires one shared socket now, transport tasks must change. |
| A2 | `@tanstack/svelte-virtual` works cleanly with this Svelte 5/SvelteKit setup. | Standard Stack, Don't Hand-Roll | If integration fails, planner needs a Wave 0 spike or alternative virtualizer. |
| A3 | Filesystem writes and SQLite metadata cannot be made a single atomic transaction; app-level compensation is required. | Common Pitfalls | If storage backend changes, blob transaction handling may differ. |
| A4 | External OpenAI-compatible LLM status is represented by `POST /api/settings/test/llm`, not a required local LLM `/health` endpoint. | Common Pitfalls, Open Questions (RESOLVED) | Resolved in planning: Phase 1 keeps `llm/` as docs/config only and probes the configured OpenAI-compatible endpoint server-side. |
| A5 | SQLite WAL is not enabled in Phase 1 unless future concurrency tests justify it. | State of the Art, Open Questions (RESOLVED) | Resolved in planning: keep SQLite journal mode conservative for the first migration/setup. |
| A6 | The browser stream reader example's `data:` framing will match the final FastAPI response format. | Code Examples | If the endpoint uses NDJSON or raw text chunks, the client parser changes. |

## Open Questions (RESOLVED)

1. **How should the roadmap's "LLM `/health`" acceptance be interpreted?**
   - Resolution: Phase 1 LLM status is `POST /api/settings/test/llm`, implemented by `web-ui/server` as a server-side probe against the configured OpenAI-compatible Chat Completions endpoint.
   - Decision basis: Context D-06 says `llm/` is docs/config only and RayMe does not ship local inference. Plans 03 and 05 document and implement the Settings probe instead of a local LLM `/health` server. [VERIFIED: 01-CONTEXT.md]

2. **Should `rayme.local` be supported in Phase 1?**
   - Resolution: Direct LAN IP HTTPS is sufficient for Phase 1. The known passing Android URL path is `https://192.168.1.199:8443`; `rayme.local` remains optional and only works when the user has local DNS/mDNS configured.
   - Decision basis: D-10 locks the Phase 0 mkcert-on-LAN workflow as the supported Phase 1 HTTPS path, and Phase 0 acceptance passed on the direct LAN IP. [VERIFIED: 01-CONTEXT.md] [VERIFIED: .planning/phases/00-measurement-gate/results/https_android.json]

3. **Should SQLite WAL be enabled in the first migration/setup?**
   - Resolution: SQLite WAL is not enabled in Phase 1. Keep journal mode conservative in the initial migration/setup unless future tests demonstrate a concrete concurrency need.
   - Decision basis: Plan 04 explicitly requires no `PRAGMA journal_mode=WAL` matches during Phase 1 verification while preserving the option to revisit after measured read/write contention. [CITED: https://www.sqlite.org/wal.html]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Node.js | SvelteKit/Vite frontend | yes | v22.22.2 | None needed. [VERIFIED: `node --version`] |
| npm | Frontend package install/version checks | yes | 10.9.7 | None needed. [VERIFIED: `npm --version`] |
| Python | FastAPI services/tests | yes | 3.12.3 | Project can still target Phase 0 Windows Python 3.11.15 if required by deployment notes. [VERIFIED: `python3 --version`] [VERIFIED: 00-RESEARCH.md] |
| uv | Python project/package management | yes | 0.11.6 | Use pip/venv if uv is unavailable on target machine. [VERIFIED: `uv --version`] |
| Python sqlite3 module | SQLite app runtime/tests | yes | SQLite 3.45.1 | None needed for Python runtime. [VERIFIED: `python3 -c 'import sqlite3'`] |
| `sqlite3` CLI | Manual DB inspection/migration debugging | no | - | Use Python/Alembic commands or install CLI for debugging. [VERIFIED: `command -v sqlite3`] |
| mkcert | Phase 1 HTTPS LAN setup | no in this shell | - | Use Phase 0 documented target-machine mkcert workflow; planner should include install/detect guidance. [VERIFIED: `command -v mkcert`] [VERIFIED: .planning/phases/00-measurement-gate/HTTPS-SETUP.md] |
| git | Commit/docs workflow | yes | 2.43.0 | None needed. [VERIFIED: `git --version`] |

**Missing dependencies with no fallback:**
- `mkcert` is missing in this shell for generating new trusted LAN certificates; Phase 1 can still plan against the documented Phase 0 workflow, but execution on this machine needs mkcert installed or existing certs supplied. [VERIFIED: `command -v mkcert`] [VERIFIED: .planning/phases/00-measurement-gate/HTTPS-SETUP.md]

**Missing dependencies with fallback:**
- `sqlite3` CLI is missing; Python's sqlite module is available, so automated tests and migrations can still run through Python/Alembic. [VERIFIED: `command -v sqlite3`] [VERIFIED: `python3 -c 'import sqlite3'`]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 9.0.3 + pytest-asyncio 1.3.0. [VERIFIED: PyPI JSON API 2026-04-24] |
| Frontend unit framework | Vitest 4.1.5 + happy-dom 20.9.0. [VERIFIED: npm registry 2026-04-24] |
| Browser/E2E framework | Playwright 1.59.1. [VERIFIED: npm registry 2026-04-24] |
| Existing config file | none because production scaffold does not exist yet. [VERIFIED: `rg --files`] |
| Quick run command | `uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run` [ASSUMED] |
| Full suite command | `uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e` [ASSUMED] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| REQ-01 | Web UI host and AI backend health, plus LLM Settings probe. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` | no - Wave 0 |
| REQ-03 | Server-side OpenAI-compatible streaming proxy emits tokens and finalizes. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_chat_stream.py -q` | no - Wave 0 |
| REQ-04 | Explicit LAN bind config and trust posture shown. | unit/integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_config.py -q` | no - Wave 0 |
| REQ-10 | Gallery lists characters and exposes actions. | unit/e2e | `npm --prefix web-ui/client run test:unit -- Gallery` | no - Wave 0 |
| REQ-11 | Editor exposes required v2/v3 fields. | unit/e2e | `npm --prefix web-ui/client run test:unit -- CharacterEditor` | no - Wave 0 |
| REQ-12 | Character delete preserves threads. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_characters.py -q` | no - Wave 0 |
| REQ-13 | Import v2/v3 JSON and PNG, `ccv3` precedence, malformed rejection. | unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_card_import.py -q` | no - Wave 0 |
| REQ-14 | Export v2 JSON. | unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_card_export.py -q` | no - Wave 0 |
| REQ-16 | Lorebook preserved, not injected into prompt. | unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py -q` | no - Wave 0 |
| REQ-17 | Alternate greeting selected and persisted as opening turn. | integration/e2e | `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q` | no - Wave 0 |
| REQ-30 | Chronological thread renders streaming output. | integration/e2e | `npm --prefix web-ui/client run test:e2e -- chat-stream.spec.ts` | no - Wave 0 |
| REQ-31 | Thread creation persists `first_mes`/alternate. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q` | no - Wave 0 |
| REQ-32 | Regenerate replaces selected AI response. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - Wave 0 |
| REQ-33 | Edit marks downstream stale and supports truncate/keep. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - Wave 0 |
| REQ-34 | Swipes store alternates; selected branch feeds context. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - Wave 0 |
| REQ-35 | Continue extends prior AI turn using composer text. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - Wave 0 |
| REQ-36 | Virtualized list handles 500+ messages and jump-to-latest. | e2e | `npm --prefix web-ui/client run test:e2e -- chat-virtualization.spec.ts` | no - Wave 0 |
| REQ-60 | Unified `messages` schema includes all six kinds. | migration/unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_migrations.py -q` | no - Wave 0 |
| REQ-70 | Home recent threads sorted by activity. | unit/e2e | `npm --prefix web-ui/client run test:unit -- HomeThreads` | no - Wave 0 |
| REQ-71 | Threads rename/delete. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q` | no - Wave 0 |
| REQ-72 | Home starts new chat through character selection. | e2e | `npm --prefix web-ui/client run test:e2e -- home-start-chat.spec.ts` | no - Wave 0 |
| REQ-90 | True Dark Phase 1 screen contract. | e2e/visual/manual | `npm --prefix web-ui/client run test:e2e -- ui-contract.spec.ts` | no - Wave 0 |
| REQ-A0 | Mobile text surfaces usable on Android-like viewport. | e2e/manual | `npm --prefix web-ui/client run test:e2e -- mobile-text.spec.ts` | no - Wave 0 |
| REQ-A1 | HTTPS secure context visible and validated. | e2e/manual | `npm --prefix web-ui/client run test:e2e -- https-status.spec.ts` | no - Wave 0 |

### Sampling Rate

- **Per task commit:** backend relevant `pytest` file or frontend relevant Vitest file. [VERIFIED: 01-CONTEXT.md]
- **Per wave merge:** backend pytest suite plus frontend unit tests. [VERIFIED: 01-CONTEXT.md]
- **Phase gate:** backend pytest, frontend unit tests, Playwright imported-character chat flow, and manual Android HTTPS secure-context check using Phase 0 workflow. [VERIFIED: 01-CONTEXT.md] [VERIFIED: .planning/phases/00-measurement-gate/HTTPS-SETUP.md]

### Wave 0 Gaps

- [ ] `web-ui/server/pyproject.toml` - backend package, scripts, pytest config. [VERIFIED: `rg --files`]
- [ ] `web-ui/server/alembic/` - migration environment and initial schema migration. [VERIFIED: `rg --files`]
- [ ] `web-ui/server/tests/test_migrations.py` - covers REQ-60. [VERIFIED: 01-CONTEXT.md]
- [ ] `web-ui/server/tests/test_card_import.py` - covers REQ-13 malicious/malformed/precedence cases. [VERIFIED: 01-CONTEXT.md]
- [ ] `web-ui/server/tests/test_sanitizer_contract.py` or frontend equivalent - covers card XSS boundary. [VERIFIED: 01-CONTEXT.md]
- [ ] `web-ui/server/tests/test_chat_stream.py` - covers REQ-03/REQ-30. [VERIFIED: 01-CONTEXT.md]
- [ ] `web-ui/server/tests/test_message_actions.py` - covers REQ-32 through REQ-35. [VERIFIED: REQUIREMENTS.md]
- [ ] `web-ui/client/package.json`, `vitest.config.ts`, `playwright.config.ts` - frontend test harness. [VERIFIED: `rg --files`]
- [ ] `web-ui/client/tests/` - Home/Gallery/Editor/Chat/Settings component and E2E tests. [VERIFIED: 01-UI-SPEC.md]

## Security Domain

Security enforcement is enabled because `.planning/config.json` does not explicitly set `security_enforcement: false`. [VERIFIED: .planning/config.json]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no for Phase 1 | No app auth by project scope; do not add fake login/account UI. [VERIFIED: REQUIREMENTS.md] [VERIFIED: 01-UI-SPEC.md] |
| V3 Session Management | no for Phase 1 | No sessions because no auth; do not create session assumptions. [VERIFIED: REQUIREMENTS.md] |
| V4 Access Control | yes, LAN/config boundary | Explicit LAN bind, no default `0.0.0.0`, explicit CORS/origin allowlists. [VERIFIED: 01-CONTEXT.md] |
| V5 Input Validation | yes | Pydantic request/card models, strict file type/size checks, malformed PNG/base64 rejection. [CITED: Context7 /pydantic/pydantic] [VERIFIED: REQUIREMENTS.md] |
| V6 Cryptography | yes | HTTPS with Phase 0 mkcert LAN workflow; never hand-roll crypto. [VERIFIED: .planning/phases/00-measurement-gate/HTTPS-SETUP.md] |
| V7 Error Handling and Logging | yes | Do not echo API keys; endpoint test statuses should be `Connected`, `Unreachable`, `Unauthorized`, or `Not configured`. [VERIFIED: 01-UI-SPEC.md] |
| V8 Data Protection | yes | Store binary assets as files, avoid path traversal, atomic writes, preserve chats on character delete. [VERIFIED: 01-CONTEXT.md] |
| V10 Malicious Code | yes | Sanitize card/chat Markdown with DOMPurify; use CSP where practical. [CITED: Context7 /cure53/dompurify] [CITED: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP] |
| V13 API and Web Service | yes | FastAPI validation, explicit CORS/origin rules, contract tests for endpoints. [CITED: Context7 /fastapi/fastapi] [VERIFIED: 01-CONTEXT.md] |

### Known Threat Patterns for Phase 1 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Character-card XSS through Markdown/HTML fields | Elevation of privilege / Tampering | Marked plus DOMPurify, no raw HTML, malicious-card fixtures. [CITED: Context7 /markedjs/marked] [CITED: Context7 /cure53/dompurify] |
| Path traversal in portrait/card upload filenames | Tampering | Ignore client filenames for storage paths; generate blob IDs; validate extensions/content. [ASSUMED] |
| LAN origin abuse against unauthenticated app APIs | Spoofing / Tampering | Explicit LAN bind and CORS/origin allowlists; no wildcard origins. [VERIFIED: 01-CONTEXT.md] |
| API key exposure in browser or logs | Information disclosure | Server-side LLM proxy; masked Settings input; never echo key in status. [VERIFIED: 01-CONTEXT.md] [VERIFIED: 01-UI-SPEC.md] |
| Malformed/large PNG metadata causing parser crash | Denial of service | File size limits, strict base64 decode, parser errors surfaced as import rejection. [VERIFIED: 01-CONTEXT.md] [CITED: Context7 /python-pillow/pillow] |
| Prompt contamination by preserved lorebook/world-info | Tampering | Store and display lorebook as present/not used; exclude from Phase 1 prompt builder tests. [VERIFIED: REQUIREMENTS.md] |
| Overbroad network bind with no authentication | Information disclosure / Tampering | Configured explicit host/IP default and setup warning when missing. [VERIFIED: 01-CONTEXT.md] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/01-foundations-text-chat-end-to-end/01-CONTEXT.md` - locked decisions, service boundaries, schema requirements, text-chat semantics, pitfalls owned. [VERIFIED: file read]
- `.planning/phases/01-foundations-text-chat-end-to-end/01-UI-SPEC.md` - Phase 1 UI and component contract. [VERIFIED: file read]
- `.planning/REQUIREMENTS.md` - requirement IDs and v1 scope. [VERIFIED: file read]
- `.planning/ROADMAP.md` - Phase 1 goal/success criteria and LLM health ambiguity. [VERIFIED: file read]
- `.planning/STATE.md` - Phase 0 completion and carry-forward decisions. [VERIFIED: file read]
- `.planning/phases/00-measurement-gate/00-RESEARCH.md` and `KEY_DECISIONS.md` - measured stack constraints and Phase 0 decisions. [VERIFIED: file read]
- `.planning/phases/00-measurement-gate/HTTPS-SETUP.md` and `results/https_android.json` - mkcert/Android secure-context path. [VERIFIED: file read]
- `.planning/research/STACK.md`, `ARCHITECTURE.md`, `FEATURES.md`, `PITFALLS.md`, `SUMMARY.md` - local architecture, stack, feature, and pitfall synthesis. [VERIFIED: file read]
- Context7 `/sveltejs/kit` - adapter-static and SPA fallback docs. [CITED: Context7]
- Context7 `/fastapi/fastapi` - `StreamingResponse`, CORS, uploads, static files, tests. [CITED: Context7]
- Context7 `/openai/openai-python` - `AsyncOpenAI` streaming. [CITED: Context7]
- Context7 `/websites/sqlalchemy_en_20` - async engine/session with `sqlite+aiosqlite`. [CITED: Context7]
- Context7 `/websites/alembic_sqlalchemy` - migrations/autogenerate/command API. [CITED: Context7]
- Context7 `/markedjs/marked` - Marked does not sanitize output. [CITED: Context7]
- Context7 `/cure53/dompurify` - DOMPurify sanitization behavior. [CITED: Context7]
- Context7 `/python-pillow/pillow` - PNG text metadata. [CITED: Context7]
- Context7 `/pydantic/pydantic` - `extra` behavior and validation. [CITED: Context7]
- Context7 `/vitest-dev/vitest` - Vitest config and DOM environments. [CITED: Context7]
- Context7 `/microsoft/playwright` - device emulation/browser checks. [CITED: Context7]
- npm registry queries on 2026-04-24 - frontend package versions and publish dates. [VERIFIED: npm registry]
- PyPI JSON API queries on 2026-04-24 - backend package versions and upload dates. [VERIFIED: PyPI JSON API]

### Secondary (MEDIUM confidence)

- `https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md` - Character Card v3 and `ccv3` behavior. [CITED: official GitHub spec]
- `https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts` - secure-context behavior. [CITED: MDN]
- `https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP` - Content Security Policy reference. [CITED: MDN]
- `https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html` - WebSocket origin validation guidance. [CITED: OWASP]
- `https://www.sqlite.org/wal.html` - SQLite WAL behavior. [CITED: SQLite official docs]

### Tertiary (LOW confidence)

- Exact browser stream wire format and TanStack integration ergonomics are implementation assumptions until Wave 0 tests exercise them. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions verified via npm/PyPI; frameworks locked by context. [VERIFIED: npm registry 2026-04-24] [VERIFIED: PyPI JSON API 2026-04-24] [VERIFIED: 01-CONTEXT.md]
- Architecture: HIGH - service boundaries and UI scope are locked; only LLM `/health` interpretation remains open. [VERIFIED: 01-CONTEXT.md] [VERIFIED: ROADMAP.md]
- Schema details: MEDIUM - required semantics are locked, but exact table/column names should be finalized in migration planning. [VERIFIED: REQUIREMENTS.md]
- Pitfalls: HIGH - phase explicitly owns HTTPS trust, card XSS, card parsing, CORS/origin, bind safety, Stitch import, and atomic blob storage. [VERIFIED: 01-CONTEXT.md] [VERIFIED: .planning/research/PITFALLS.md]
- Validation: MEDIUM - framework versions are verified, but all test harness files are Wave 0 gaps because no production scaffold exists. [VERIFIED: `rg --files`]

**Research date:** 2026-04-24 [VERIFIED: system current_date]
**Valid until:** 2026-05-24 for local architecture decisions; package versions should be rechecked before implementation if planning starts after that date. [ASSUMED]
