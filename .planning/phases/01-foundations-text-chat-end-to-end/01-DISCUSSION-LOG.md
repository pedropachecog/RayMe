# Phase 1: Foundations & Text Chat End-to-End - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` -- this log preserves the alternatives considered.

**Date:** 2026-04-23T23:39:24Z
**Phase:** 1 - Foundations & Text Chat End-to-End
**Mode:** `gsd-next` routed to `gsd-discuss-phase 1`; structured question UI unavailable, so workflow fallback selected conservative defaults from existing project artifacts.
**Areas discussed:** Service and repo shape, HTTPS and LAN safety, storage and schema, character cards, text chat semantics, UI and design.

---

## Service And Repo Shape

| Option | Description | Selected |
| --- | --- | --- |
| SvelteKit static client plus FastAPI API/static host | Matches local stack research, keeps Python storage/API close to later AI backend patterns, and serves Stitch-derived UI cleanly. | yes |
| SvelteKit full-stack server routes | Fewer processes, but weaker fit with the Python-heavy backend/storage plan and static-serving recommendation. |  |
| One combined FastAPI-rendered app | Simpler backend, but throws away the SvelteKit/Stitch client recommendation. |  |

**Captured decision:** Use `web-ui/client` for SvelteKit and `web-ui/server` for FastAPI/SQLite/static serving, with an `ai-backend` health stub and external LLM endpoint.

---

## HTTPS And LAN Safety

| Option | Description | Selected |
| --- | --- | --- |
| Phase 0 mkcert path, explicit bind IPs, origin allow-lists | Reuses validated Android HTTPS flow and addresses Pitfalls 2, 16, and 17. | yes |
| Plain HTTP during early development | Faster initial setup but breaks mobile mic assumptions and delays the hard trust problem. |  |
| Bind everything to `0.0.0.0` by default | Easy LAN reachability but conflicts with the over-exposure risk already called out in research. |  |

**Captured decision:** Use mkcert HTTPS from day one, secure-context checks in UI, explicit bind configuration, and strict CORS/WS origin allow-lists.

---

## Storage And Schema

| Option | Description | Selected |
| --- | --- | --- |
| SQLite metadata plus filesystem blobs | Matches single-user LAN scope and keeps future audio/portrait assets out of DB BLOBs. | yes |
| JSON files only | Quick to start but brittle for message branching, migrations, and future call records. |  |
| Postgres from day one | More scalable, but operational weight is not justified for the v1 single-user LAN app. |  |

**Captured decision:** Create migrations and the unified `messages` schema immediately, including future call message kinds and branch/swipe metadata.

---

## Character Cards

| Option | Description | Selected |
| --- | --- | --- |
| Normalize to internal v3-shaped model, preserve raw source JSON | Supports v2/v3 import, safe round-trip, and later export without coupling runtime code to raw card shapes. | yes |
| Store raw cards only | Easy import but makes editor, search-free gallery, LLM prompt assembly, and validation fragile. |  |
| Invent a RayMe-only character schema | Simpler in isolation but violates SillyTavern compatibility goals. |  |

**Captured decision:** Prefer `ccv3`, fall back to `chara`, validate strictly, preserve lorebook-not-injected, and sanitize all displayed card text.

---

## Text Chat Semantics

| Option | Description | Selected |
| --- | --- | --- |
| Implement full SillyTavern text-UX semantics in Phase 1 | Required by REQ-32 through REQ-36 and prevents schema churn later. | yes |
| Ship basic send/reply first and add ST parity later | Lower initial cost but conflicts with the Phase 1 success criteria. |  |
| Defer branch/swipe schema until UI polish | Creates likely migration risk before Phase 5 unified-thread work. |  |

**Captured decision:** Streaming token output, alternate greeting picker, regenerate replace semantics, stored swipes, explicit stale downstream turns after edit, continue from composer text, and virtualization around 500 messages.

---

## UI And Design

| Option | Description | Selected |
| --- | --- | --- |
| Build actual app shell from Stitch True Dark references | Aligns with REQ-90 and avoids a marketing/placeholder first screen. | yes |
| Implement generic CRUD UI first | Faster but throws away the existing design handoff. |  |
| Copy Stitch mockups literally including account/billing affordances | Visual match is higher, but those affordances conflict with no-auth single-user scope. |  |

**Captured decision:** Use Home, Character Gallery, Character Editor, and Settings as Phase 1 primary screens; keep future screens non-functional or omitted unless navigation requires them; remove fake account/billing/logout behavior.

---

## the agent's Discretion

- Exact folder names inside each top-level runtime area.
- Exact migration framework and test-file layout.
- Exact Svelte component decomposition.
- Exact streaming transport for text chat, provided it is reliable and easy to evolve.
- Exact copy for empty, loading, error, and connection-test states.

## Deferred Ideas

- Voice Lab and voice-library behavior.
- WebRTC calls and call-state UI behavior.
- Full barge-in/caption/visualizer behavior.
- PWA and Android hardening.
- v1.x search, v3 PNG export, lorebook injection, waveform scrubber, and sampling override features.
