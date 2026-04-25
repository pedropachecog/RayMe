---
phase: 03
slug: first-working-call-mvp
status: ready_for_planning
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-25
updated: 2026-04-25
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest 9.0.3` for `ai-backend` and `web-ui/server`; `vitest 4.1.5`; `@playwright/test 1.59.1` |
| **Config file** | `ai-backend/pyproject.toml`, `web-ui/server/pyproject.toml`, `web-ui/client/vitest.config.ts`, `web-ui/client/playwright.config.ts` |
| **Quick run command** | `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e -- tests/e2e/chat-stream.spec.ts --project=desktop-chromium` |
| **Full suite command** | `uv run --project ai-backend pytest ai-backend/tests -q && uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e` |
| **Estimated runtime** | Quick: ~90-180 seconds after Wave 0 exists; full: project-dependent, run before live handoff |

---

## Sampling Rate

- **After every task commit:** Run the smallest affected pytest/vitest target plus one desktop Playwright call-flow spec when client behavior changed.
- **After every plan wave:** Run all new Phase 3 call pytest targets plus desktop and mobile-emulation Playwright call specs.
- **Before `$gsd-verify-work`:** Run the full local suite, then live OMEN-PC evidence, then Android product-owner acceptance.
- **Max feedback latency:** No three consecutive implementation tasks may proceed without an automated verification target.

---

## Requirement Verification Map

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| REQ-40 | Start call from thread header and character card, creating/selecting a thread when needed | Playwright + server integration | `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-start.spec.ts --project=desktop-chromium` | no, Wave 0 | pending |
| REQ-47 | Mute halts server-side consumption; input/output pickers show supported or disabled states honestly | ai-backend pytest + Playwright | `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py::test_mute_stops_server_consumption -q && npm --prefix web-ui/client run test:e2e -- tests/e2e/call-toolbar.spec.ts --project=desktop-chromium` | no, Wave 0 | pending |
| REQ-48 | First-call mic permission prompt, denial explanation, and retry affordance | Playwright | `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-permissions.spec.ts --project=desktop-chromium` | no, Wave 0 | pending |
| REQ-49 | Voice Visualizer states: listening, thinking, speaking | Vitest + Playwright | `npm --prefix web-ui/client run test:unit -- --run tests/unit/call-state.test.ts && npm --prefix web-ui/client run test:e2e -- tests/e2e/call-visualizer.spec.ts --project=desktop-chromium` | no, Wave 0 | pending |
| REQ-50 | `call_start`, `user_speech`, `ai_speech`, and `call_end` rows persist chronologically and return to composer | web-ui/server pytest + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py::test_call_summary_rows_written -q && npm --prefix web-ui/client run test:e2e -- tests/e2e/call-summary.spec.ts --project=desktop-chromium` | no, Wave 0 | pending |
| REQ-63 | Call prompt hydration uses a sliding window of recent text and call turns | web-ui/server pytest | `uv run --project web-ui/server pytest web-ui/server/tests/test_prompt_builder.py::test_call_context_sliding_window -q` | no, Wave 0 | pending |
| REQ-A0 | Browser call loop works on mobile browser path and real Android acceptance | Playwright mobile + live/manual | `npm --prefix web-ui/client run test:e2e -- tests/e2e/call-mobile.spec.ts --project=mobile-chromium` | no, Wave 0 | pending |
| REQ-A0 / REQ-A1 | Non-mocked live LAN call works against OMEN-PC Web UI and AI backend | Live Playwright + evidence | `RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npm --prefix web-ui/client run test:e2e -- tests/e2e/live-call.spec.ts --project=desktop-chromium` | no, Wave 0 | pending |

---

## Wave 0 Requirements

- [ ] `ai-backend/tests/test_call_session.py` — call session lifecycle, mute enforcement, interrupt, teardown, and stats.
- [ ] `web-ui/server/tests/test_calls.py` — call bootstrap/writeback APIs, thread creation from character card, and call summary persistence.
- [ ] `web-ui/server/tests/test_prompt_builder.py` — sliding-window prompt hydration over text and call rows.
- [ ] `web-ui/client/tests/unit/call-state.test.ts` — browser FSM transitions, visualizer state mapping, and capability messaging.
- [ ] `web-ui/client/tests/e2e/call-start.spec.ts` — desktop start/end flow with thread return.
- [ ] `web-ui/client/tests/e2e/call-toolbar.spec.ts` — mute/device picker behavior and disabled explanations.
- [ ] `web-ui/client/tests/e2e/call-permissions.spec.ts` — mic denial and retry behavior.
- [ ] `web-ui/client/tests/e2e/call-summary.spec.ts` — summary and speech rows in thread scrollback.
- [ ] `web-ui/client/tests/e2e/call-mobile.spec.ts` — Pixel 5 emulation path before real Android handoff.
- [ ] `web-ui/client/tests/e2e/live-call.spec.ts` — opt-in non-mocked LAN call acceptance; must skip unless `RAYME_ENABLE_LIVE_E2E=1` and must not route-mock `/api/calls/*` or `/webrtc/*`.
- [ ] `.planning/phases/03-first-working-call-mvp/PLAYWRIGHT-EVIDENCE.md` — saved browser evidence.
- [ ] `.planning/phases/03-first-working-call-mvp/OMEN-PC-LIVE-EVIDENCE.md` — live LAN/runtime evidence.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Android Chrome physical call acceptance | REQ-A0, REQ-A1 | `adb` is not available locally and product-owner acceptance is required after agent-run evidence | After full local and live OMEN-PC checks pass, open `https://192.168.1.199:8443` on the already trusted Android Chrome device, confirm `window.isSecureContext === true`, start a call, grant mic permission, confirm AudioContext unlock/audio playback, complete two user turns plus two AI turns in the same call, mute/unmute, end call, and report pass/fail details for the evidence file. |
| 5-minute desktop speaker stability check | Phase 3 success criterion | Long-running acoustic ping-pong behavior depends on the live speaker/mic environment | After automated desktop call specs pass, run one live 5-minute desktop speaker call with at least two user→AI cycles and record whether uncaught exceptions, runaway loopback, or catastrophic ping-pong occurred. |

---

## Security Validation Hooks

- ASVS L1 controls apply to call bootstrap/control payloads, sanitized call errors, secure-context media checks, transcript rendering, and deterministic session teardown.
- Every implementation plan must include a `<threat_model>` block and block high-severity gaps.
- Call evidence must not record API keys, TLS private key contents, raw local exception traces, or raw user mic audio unless the user explicitly enables mic-audio storage.

---

## Validation Sign-Off

- [x] Requirement-level automated targets are defined.
- [x] Wave 0 names missing test files before feature implementation.
- [x] Manual Android and 5-minute live checks are explicitly separated from automated gates.
- [x] No watch-mode commands are used.
- [x] `nyquist_compliant: true` is set in frontmatter for planning.

**Approval:** ready for Phase 3 planning, 2026-04-25
