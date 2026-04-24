# Phase 1: Foundations & Text Chat End-to-End - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` -- this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 1 - Foundations & Text Chat End-to-End
**Mode:** Plain text discussion. User requested that recommendations always be shown and that `workflow.text_mode` be enabled so future GSD discussion does not skip interactive decision capture.
**Areas discussed:** Delivery shape, UI fidelity, persistence, character import, text-chat depth, LLM handling, service binding, acceptance target, Settings scope, rendering safety, message actions, Home layout, thread layout, stale-turn handling, alternate greetings, import placement, test posture, UI contract sequencing.

---

## Delivery Shape

| Option | Description | Selected |
| --- | --- | --- |
| Balanced slice | Home -> Character -> Chat with enough UI and backend to prove the full flow. Recommended. | yes |
| Text loop first | Character import plus one thread and streaming LLM reply before broader app shell. |  |
| App shell first | Stitch-like Home/Gallery/Editor/Settings scaffold first, then wire text loop. |  |

**Captured decision:** Phase 1 prioritizes a balanced vertical slice.

---

## UI Fidelity

| Option | Description | Selected |
| --- | --- | --- |
| Stitch-faithful, scope-corrected | Keep True Dark look and layout language, remove fake account/billing/logout/noise, show real Phase 1 controls. Recommended. | yes |
| Pixel-close Stitch port | Maximize visual match, even if some controls are placeholders. |  |
| Functional first | Use design system lightly and prioritize speed over visual fidelity. |  |

**Captured decision:** Stitch-faithful, scope-corrected UI.

---

## Persistence

| Option | Description | Selected |
| --- | --- | --- |
| Schema-first SQLite | Build migrations and real tables up front, including future message kinds and branch/swipe structure. Recommended. | yes |
| Minimal SQLite | Only build tables needed for Phase 1 text chat, migrate later for calls/voices. |  |
| File-backed prototype | JSON/files first, convert to SQLite once flows settle. |  |

**Captured decision:** Schema-first SQLite.

---

## Character Import Strictness

| Option | Description | Selected |
| --- | --- | --- |
| Best-effort import | Import what can be parsed safely, warn about ignored or invalid fields. | yes |
| Strict import with clear errors | Validate v2/v3 JSON and PNG chunks, reject malformed cards, never silently drop fields. Recommended. |  |
| Permissive import now | Accept loose cards to reduce friction, tighten validation later. |  |

**Captured decision:** Best-effort safe import. Preserve raw source JSON, warn clearly, but reject dangerous or malformed payloads that could crash parsing or create XSS risk.

---

## Text Chat Feature Depth

| Option | Description | Selected |
| --- | --- | --- |
| Full SillyTavern text basics | Streaming replies, Regenerate, Edit with stale downstream turns, Swipes, Continue, alternate greetings. Recommended. | yes |
| Core chat first | Streaming replies plus persisted threads; add text actions later. |  |
| Middle path | Streaming replies, alternate greetings, Regenerate/Edit; defer Swipes and Continue. |  |

**Captured decision:** Full SillyTavern text basics.

---

## LLM Endpoint Handling

| Option | Description | Selected |
| --- | --- | --- |
| Server-side LLM proxy | Browser talks to RayMe server; RayMe streams from OpenAI-compatible endpoint. API keys stay server-side. Recommended. | yes |
| Browser-direct LLM | Browser calls the endpoint directly; simpler but leaks keys/config. |  |
| Both modes | Server proxy by default, optional browser-direct for local no-key endpoints. |  |

**Captured decision:** Server-side LLM proxy.

---

## Service Binding Policy

| Option | Description | Selected |
| --- | --- | --- |
| Explicit LAN bind with guided setup | Default to configured LAN IP/host and show setup guidance when missing. Recommended. | yes |
| Bind `0.0.0.0` by default | Easiest LAN testing, but exposes every network interface. |  |
| Localhost default only | Safest, but mobile testing requires manual config every time. |  |

**Captured decision:** Explicit LAN bind with guided setup.

---

## Phase 1 Acceptance Target

| Option | Description | Selected |
| --- | --- | --- |
| End-to-end imported character chat | HTTPS, import card, start chat, stream reply, persist messages, reload and continue. Recommended. | yes |
| All screens visibly complete | Home/Gallery/Editor/Settings look complete, even if some behavior is shallow. |  |
| Backend/data foundation complete | Schema, APIs, importer, and LLM streaming pass tests with minimal UI. |  |

**Captured decision:** End-to-end imported-character chat.

---

## Settings Scope

| Option | Description | Selected |
| --- | --- | --- |
| Real endpoint settings only | Web UI URL/status, AI backend URL/status, LLM URL/key/model/status, HTTPS/secure-context status. Recommended. | yes |
| Full Settings visual shell | Include disabled placeholders for future voice, VAD, audio, save-audio, and danger-zone controls. |  |
| Minimal connection page | Just enough fields to configure LLM and AI backend. |  |

**Captured decision:** Real endpoint settings only.

---

## Character Text Rendering

| Option | Description | Selected |
| --- | --- | --- |
| Sanitized Markdown | Preserve common card formatting, strip/escape HTML and dangerous content. Recommended. | yes |
| Plain text only | Safest and simplest, but imported cards may look flatter. |  |
| Rich HTML support | Closest to messy card ecosystem, but too risky for Phase 1 unless heavily sandboxed. |  |

**Captured decision:** Sanitized Markdown.

---

## Message Action UX

| Option | Description | Selected |
| --- | --- | --- |
| Per-message contextual actions | Hover/tap menu on AI turns for Regenerate, Swipe, Edit, Continue; user turns get Edit. Recommended. | yes |
| Always-visible buttons | More discoverable, but visually noisy. |  |
| Composer-level actions only | Cleaner, but weaker SillyTavern muscle memory. |  |

**Captured decision:** Per-message contextual actions.

---

## Home Screen

| Option | Description | Selected |
| --- | --- | --- |
| Threads-first Home | Recent threads list is primary; new chat/import/create actions nearby. Recommended. | yes |
| Character-first Home | Character gallery is primary; threads are secondary. |  |
| Dashboard-style Home | Keep Stitch stats/quick cards, with some sections shallow in Phase 1. |  |

**Captured decision:** Threads-first Home.

---

## Chat Thread Layout

| Option | Description | Selected |
| --- | --- | --- |
| Spacious modern messenger | Larger bubbles and more whitespace, polished RayMe feel. | yes |
| Dense SillyTavern-like chat with RayMe styling | Compact flow optimized for long conversations. Recommended. |  |
| Transcript/document style | Chronological prose log with minimal bubbles. |  |

**Captured decision:** Spacious modern messenger, while preserving enough density and virtualization for long chats.

---

## Edit Stale-Turn Handling

| Option | Description | Selected |
| --- | --- | --- |
| Explicit stale flag with branch choice | Edited prior turns mark downstream turns stale; user chooses truncate or keep when continuing. Recommended. | yes |
| Auto-truncate downstream | Simpler, but can destroy useful context unexpectedly. |  |
| Keep everything silently | Least disruptive, but future context may become incoherent. |  |

**Captured decision:** Explicit stale flag with branch choice.

---

## Alternate Greetings

| Option | Description | Selected |
| --- | --- | --- |
| Create with default, then allow switching | Start immediately with default, clearly show alternate-greeting control if alternates exist. | yes |
| Pick before thread creation | Show modal/list before creating chat. Recommended. |  |
| Always use default in Phase 1 | Simpler, but misses required SillyTavern behavior. |  |

**Captured decision:** Create with default, then allow switching, with a clear alternate-greetings indicator on the opening message before the user continues.

---

## Import Flow Placement

| Option | Description | Selected |
| --- | --- | --- |
| Gallery import action | Character Gallery has Import button/drop zone; imported card opens in Editor for review/save. Recommended. | yes |
| Home quick import | Home has an import shortcut for faster first-run. |  |
| Both Gallery and Home | More discoverable, but duplicates entry point. |  |

**Captured decision:** Gallery import action.

---

## API/Test Posture

| Option | Description | Selected |
| --- | --- | --- |
| Contract-heavy tests | Schema migrations, card parser/importer, sanitizer, LLM proxy, message actions, endpoint health. Recommended. | yes |
| UI-heavy tests | Prioritize Playwright flows and screenshots over lower-level API tests. |  |
| Smoke tests only | Keep tests light until app shape stabilizes. |  |

**Captured decision:** Contract-heavy tests.

---

## UI Design Contract Sequencing

| Option | Description | Selected |
| --- | --- | --- |
| Run UI phase before implementation planning | Generate UI-SPEC for Home, Gallery, Editor, Settings, and Chat before planning. Recommended. | yes |
| Plan directly from Stitch docs | Use existing Stitch handoff and skip another design artifact. |  |
| Only for Chat | Add extra UI detail only for the new text-chat/thread surface. |  |

**Captured decision:** Run `$gsd-ui-phase 1` before `$gsd-plan-phase 1`.

---

## the agent's Discretion

- Exact folder names inside each top-level runtime area.
- Exact migration framework and test-file layout.
- Exact Svelte component decomposition.
- Exact text streaming transport, provided it stays reliable and evolvable.
- Exact copy for empty, loading, error, connection-test, stale-turn, and alternate-greeting states.

## Deferred Ideas

- Voice Lab and voice-library behavior.
- WebRTC calls and call-state UI behavior.
- Full barge-in/caption/visualizer behavior.
- PWA and Android hardening.
- v1.x search, v3 PNG export, lorebook injection, waveform scrubber, and sampling override features.
