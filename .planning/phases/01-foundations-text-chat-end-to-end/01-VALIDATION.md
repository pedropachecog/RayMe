---
phase: 01
slug: foundations-text-chat-end-to-end
status: automated-green-pending-android
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-24
---

# Phase 01 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest 9.0.3 + pytest-asyncio 1.3.0. Frontend: Vitest 4.1.5 + happy-dom 20.9.0. E2E: Playwright 1.59.1. |
| **Config file** | None yet. Wave 0 must create `web-ui/server/pyproject.toml`, backend pytest config, `web-ui/client/package.json`, `vitest.config.ts`, and `playwright.config.ts`. |
| **Quick run command** | `uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run` |
| **Full suite command** | `uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e` |
| **Estimated runtime** | ~90 seconds after Wave 0, excluding manual Android HTTPS checks and dependency install time. |

---

## Sampling Rate

- **After every task commit:** Run the narrow backend pytest file, frontend Vitest spec, or Playwright spec tied to the changed behavior.
- **After every plan wave:** Run `uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run`.
- **Before `$gsd-verify-work`:** Run the full suite plus the manual Android HTTPS secure-context check from Phase 0.
- **Max feedback latency:** 90 seconds for automated sampling once the scaffold exists.

---

## Per-Task Verification Map

Rows map requirements to the required verification surface. Plan IDs are provisional until `*-PLAN.md` files are generated.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-00-01 | Wave 0 scaffold | 1 | All Phase 1 test harnesses | T-01-TEST | No watch-mode flags in CI commands | scaffold | `test -f web-ui/server/pyproject.toml && test -f web-ui/client/package.json` | no - W0 | pending |
| 01-01-01 | Service health/settings | 1 | REQ-01 | T-01-LAN | Web UI and AI backend expose health; LLM status is server-side probe | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q` | no - W0 | pending |
| 01-01-02 | Streaming proxy | 1 | REQ-03 | T-01-KEY | Browser never receives LLM API key or raw endpoint secret | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_chat_stream.py -q` | no - W0 | pending |
| 01-01-03 | LAN config | 1 | REQ-04 | T-01-BIND | Default bind is explicit configured LAN host/IP, not silent wildcard | unit/integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_config.py -q` | no - W0 | pending |
| 01-02-01 | Character gallery | 2 | REQ-10 | T-01-XSS | Gallery snippets use sanitized rendering only | unit/e2e | `npm --prefix web-ui/client run test:unit -- Gallery` | no - W0 | pending |
| 01-02-02 | Character editor | 2 | REQ-11 | T-01-XSS | Untrusted card fields never render raw HTML | unit/e2e | `npm --prefix web-ui/client run test:unit -- CharacterEditor` | no - W0 | pending |
| 01-02-03 | Character delete | 2 | REQ-12 | T-01-DATA | Deleting a character preserves existing thread history | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_characters.py -q` | no - W0 | pending |
| 01-02-04 | Card import | 2 | REQ-13 | T-01-PARSE | Malformed JSON, oversized files, bad base64, and wrong PNG chunks reject safely | unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_card_import.py -q` | no - W0 | pending |
| 01-02-05 | Card export | 2 | REQ-14 | T-01-DATA | Export omits executable HTML and emits v2 JSON only | unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_card_export.py -q` | no - W0 | pending |
| 01-02-06 | Lorebook preservation | 2 | REQ-16 | T-01-PROMPT | Lorebook payload is stored and excluded from Phase 1 prompt context | unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py -q` | no - W0 | pending |
| 01-03-01 | Alternate greetings | 3 | REQ-17 | T-01-DATA | Selected greeting is persisted as the opening AI turn | integration/e2e | `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q` | no - W0 | pending |
| 01-03-02 | Streaming thread | 3 | REQ-30 | T-01-STREAM | Partial tokens do not persist as final messages before completion | integration/e2e | `npm --prefix web-ui/client run test:e2e -- chat-stream.spec.ts` | no - W0 | pending |
| 01-03-03 | Opening message | 3 | REQ-31 | T-01-DATA | Thread creation inserts first message before user input | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q` | no - W0 | pending |
| 01-03-04 | Regenerate | 3 | REQ-32 | T-01-DATA | Regenerate replaces selected AI response, not a second canonical answer | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - W0 | pending |
| 01-03-05 | Edit/stale turns | 3 | REQ-33 | T-01-DATA | Downstream turns are flagged stale and truncate/keep choice is recorded | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - W0 | pending |
| 01-03-06 | Swipes | 3 | REQ-34 | T-01-DATA | Only the selected alternate feeds future prompt context | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - W0 | pending |
| 01-03-07 | Continue | 3 | REQ-35 | T-01-DATA | Composer text is used as extension instruction/prefix | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_message_actions.py -q` | no - W0 | pending |
| 01-03-08 | Virtualized chat | 3 | REQ-36 | T-01-UX | 500+ message thread keeps scroll position and jump-to-latest usable | e2e | `npm --prefix web-ui/client run test:e2e -- chat-virtualization.spec.ts` | no - W0 | pending |
| 01-01-04 | Unified schema | 1 | REQ-60 | T-01-SCHEMA | `messages.message_kind` supports user_text, ai_text, user_speech, ai_speech, call_start, call_end | migration/unit | `uv run --project web-ui/server pytest web-ui/server/tests/test_migrations.py -q` | no - W0 | pending |
| 01-04-01 | Home threads | 4 | REQ-70 | T-01-UX | Recent threads are sorted by activity without exposing deleted character internals | unit/e2e | `npm --prefix web-ui/client run test:unit -- HomeThreads` | no - W0 | pending |
| 01-04-02 | Thread management | 4 | REQ-71 | T-01-DATA | Rename/delete affects only selected thread | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_threads.py -q` | no - W0 | pending |
| 01-04-03 | Start chat from Home | 4 | REQ-72 | T-01-UX | Empty state routes to real Gallery/import/create flows only | e2e | `npm --prefix web-ui/client run test:e2e -- home-start-chat.spec.ts` | no - W0 | pending |
| 01-05-01 | True Dark UI contract | 5 | REQ-90 | T-01-UX | No fake account, billing, logout, voice, or call controls in Phase 1 screens | e2e/visual/manual | `npm --prefix web-ui/client run test:e2e -- ui-contract.spec.ts` | no - W0 | pending |
| 01-05-02 | Mobile text surfaces | 5 | REQ-A0 | T-01-MOBILE | Android-like viewport can import, chat, reload, and continue | e2e/manual | `npm --prefix web-ui/client run test:e2e -- mobile-text.spec.ts` | no - W0 | pending |
| 01-01-05 | HTTPS secure context | 1 | REQ-A1 | T-01-TLS | `window.isSecureContext === true` is visible in Settings/Home over trusted LAN HTTPS | e2e/manual | `npm --prefix web-ui/client run test:e2e -- https-status.spec.ts` | no - W0 | pending |

*Status: pending, green, red, flaky*

---

## Wave 0 Requirements

- [ ] `web-ui/server/pyproject.toml` - backend package, scripts, pytest config, and pinned FastAPI/SQLAlchemy/Alembic/OpenAI/Pillow dependencies.
- [ ] `web-ui/server/alembic/` - migration environment and initial SQLite schema migration.
- [ ] `web-ui/server/tests/test_migrations.py` - unified `messages` schema and six `message_kind` values.
- [ ] `web-ui/server/tests/test_card_import.py` - v2/v3 JSON and PNG parsing, `ccv3` precedence, malformed payloads, and malicious fixtures.
- [ ] `web-ui/server/tests/test_sanitizer_contract.py` or frontend equivalent - malicious card XSS boundary.
- [ ] `web-ui/server/tests/test_chat_stream.py` - OpenAI-compatible streaming proxy and final atomic persistence.
- [ ] `web-ui/server/tests/test_message_actions.py` - regenerate, swipes, edit stale flags, truncate/keep, and continue.
- [ ] `web-ui/server/tests/test_health_settings.py` - web health, AI backend health, and LLM connection probe behavior.
- [ ] `web-ui/client/package.json`, `vitest.config.ts`, and `playwright.config.ts` - frontend test harness with no watch-mode default for plan verification.
- [ ] `web-ui/client/tests/` - Home, Gallery, Editor, Chat, Settings component tests and Playwright E2E specs.
- [ ] `ai-backend/pyproject.toml` and health tests - Phase 1 AI backend `/health` stub.

---

## Plan 01-24 Automated Acceptance Update

**Date:** 2026-04-24

**Automated status:** green

- [x] Backend API acceptance covers import -> imported review update via `PATCH /api/characters/{character_id}` -> thread creation with `alternate_greeting_index` -> stream -> regenerate -> swipe -> continue -> reload/query -> same-thread send.
- [x] Browser acceptance covers imported-card review/save, selected alternate greeting thread creation, streamed chat, regenerate, swipe, continue, reload, Home Start Chat, Gallery Start Chat, Gallery export, Gallery delete confirmation, secure/media status, mobile text flow, and Phase 1 UI contract exclusions.
- [x] HTTPS runbooks exist at `web-ui/server/docs/HTTPS-LAN.md` and `web-ui/server/docs/PHASE1-ACCEPTANCE.md` with direct LAN IP URLs `https://192.168.1.199:8443` and `https://192.168.1.199:9443/health`.
- [x] Required automated commands passed: `uv run --project web-ui/server pytest web-ui/server/tests -q`, `npm --prefix web-ui/client run test:unit -- --run`, and `npm --prefix web-ui/client run test:e2e`.
- [x] `rg "test\.(skip|fixme|todo)" web-ui/client/tests web-ui/server/tests` returned no matches.
- [ ] Manual Android Chrome direct-IP HTTPS acceptance remains pending. Do not mark green until the physical-device flow is approved.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Android Chrome loads the trusted LAN HTTPS URL with secure context | REQ-A1 / REQ-A0 partial | Requires physical Android device trust store and LAN route | 1. Reuse `.planning/phases/00-measurement-gate/HTTPS-SETUP.md`. 2. Load the configured Phase 1 URL on Android Chrome. 3. Confirm no certificate warning. 4. Confirm Settings/Home reports `window.isSecureContext === true` and `navigator.mediaDevices` present. |
| True Dark visual fit against Stitch reference | REQ-90 partial | Requires design judgment against `docs/stitch/screenshots/*.png` | Compare Home, Gallery, Editor, Settings, and Chat against the UI-SPEC. Confirm no marketing landing page, fake account/billing/logout controls, raw borders, or disabled future voice/call controls. |
| End-to-end imported-character chat over the builder's actual LLM endpoint | REQ-03 / REQ-30 / REQ-A0 partial | Requires configured real or local OpenAI-compatible endpoint | Import a v2/v3 card, save it, start chat, stream a reply, reload, and continue the same thread. Confirm Settings never displays the API key. |

---

## Validation Sign-Off

- [x] All planned requirement rows have automated verify commands or Wave 0 dependencies.
- [x] Sampling continuity: no three consecutive implementation tasks may omit automated verification.
- [x] Wave 0 covers all missing test-harness references from research.
- [x] No watch-mode flags in required verification commands.
- [x] Feedback latency target is less than 90 seconds for automated sampling after scaffold setup.
- [x] `nyquist_compliant: true` set in frontmatter.
- [x] `wave_0_complete: true` set in frontmatter after Wave 0 execution.

**Approval:** ready for planning.
