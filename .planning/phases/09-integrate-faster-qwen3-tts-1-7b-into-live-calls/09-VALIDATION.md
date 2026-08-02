---
phase: 09
slug: integrate-faster-qwen3-tts-1-7b-into-live-calls
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-31
---

# Phase 09 — Validation Strategy

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest 9.0.3; Vitest 4.1.5; Playwright 1.59.1 |
| Config | `ai-backend/pyproject.toml`, `web-ui/server/pyproject.toml`, client Vitest/Playwright configs |
| Fast feedback | Focused fake-worker/backend/server/component commands in each task; target <30 s |
| Wave acceptance | Full tier suite; saved Playwright only after fast component tests |
| Hardware gates | Plan 09-04 blocking early canonical deploy; Plan 09-14 final canonical deploy/core bundle; Plan 09-15 real live E2E/handoff |

## Sampling Rate

- After every code-producing task: run its focused command and `git diff --check`.
- At each wave boundary: run complete tests for touched tiers.
- UI edits use focused Vitest per task; saved mocked Playwright is wave acceptance, not the fast edit loop.
- No broad migration/UI/call/evidence work proceeds if Plan 09-04's real adapter/manager/saved-voice/CallSession/WebRTC tracer fails.
- Final handoff requires verifier `--self-test`, canonical deploy, real live E2E, `--decision-ready`, and exact operational-check arguments.

## Per-Plan Verification Map

| Plan | Wave | Requirement | Primary automated gate | Status |
|---|---:|---|---|---|
| 09-01 | 1 | REQ-22 | package-legitimacy/PyPI plus annotated-tag-object and peeled-commit checks; `uv lock --check`; roster/health pytest | pending |
| 09-02 | 2 | REQ-22/45 | `test_tts_qwen3.py` fake protocol/worker/adapter suite | pending |
| 09-03 | 3 | REQ-22/45/46 | manager/WebRTC/CallSession slow stream/cancel plus VoxCPM2 regressions | pending |
| 09-04 | 4 | REQ-22/45/46 | contained asset/byte-hash/transcript-integrity self-test; push plus verified remote-SHA gate before canonical deploy; commit-matched tracer verifier | pending |
| 09-05 | 5 | REQ-22/45 | alignment/ceiling/protocol/cache/error pytest | pending |
| 09-06 | 6 | REQ-22 | backend and server delete→invalidate/evict tests with unrelated-voice recovery | pending |
| 09-07 | 5 | REQ-22/45 | migration/voice/call server pytest plus Alembic upgrade | pending |
| 09-08 | 6 | REQ-22/45/46 | focused Voice Lab/Voice Library/EndpointSettingsPanel Vitest identity, assumed-authorized upload, readiness, retry, focus/a11y/mobile states | pending |
| 09-09 | 7 | REQ-22/45/46 | fast Playwright `--list`, then saved mocked Voice Lab/Library/Settings/call readiness UI wave acceptance | pending |
| 09-10 | 7 | REQ-22/45/46 | slow-LLM segment/persistence server pytest | pending |
| 09-11 | 6 | REQ-45/46 | slow producer/consumer, paced bound, metrics, all control causes, Vox regression pytest | pending |
| 09-12 | 8 | REQ-22/45/46 | manifest/scorer tests; verifier `--contracts-only` and named `--self-test` | pending |
| 09-13 | 9 | REQ-22/45/46 | production runner dry-run/scenario/scorer lifecycle tests | pending |
| 09-14 | 10 | REQ-22/45/46 | full suites; canonical deploy; exact-commit runtime/call/STT core bundle | pending |
| 09-15 | 11 | REQ-22/45/46 | pinned speaker/leak; real Qwen live E2E; decision-ready; exact operational handoff | pending |

## Required Regression Inventory

- Protocol: schema/version/request/index/time/audio/terminal mutations, crash/hang/restart, exact immutable identity.
- Reference: blank/missing/known mismatch reject before generation; punctuation/case/accent tolerance; exact transcript preserved; contained valid bytes and matching reference/transcript hashes required before private bytes are used; an explicitly selected deterministic non-person fixture remains transport evidence only and is never an automatic fallback.
- Streaming: slow LLM submission before completion; slow native first playback before completion; no Qwen or VoxCPM2 whole fallback.
- Bounds: segment scheduler, bridge capacity two, paced-track pending-audio credit, prompt capacity one, output ceilings.
- Cancellation: before/after audio, VAD/button/hangup/switch/close/delete; zero late audio/done/complete persistence; recovery.
- Deletion: matching prompt tensors/cache are evicted; unrelated saved voice remains usable.
- UI: canonical identity in EndpointSettingsPanel available/resident/loading fields; dynamic metadata; Loading/Resident versus Prewarming/Ready/Failed; assumed-authorized upload with no policy controls/states/fallback; VoiceLibraryRow/List `Preparing voice…` versus `Testing voice…`; retry and unrelated-row responsiveness; fixed role=status/alert, focus, reduced-motion, 44px/mobile; no premature Listening.
- Browser release: after deploy only, `RAYME_ENABLE_LIVE_E2E=1`, canonical URLs, qwen3_1_7b, explicitly selected transport fixture where appropriate, deployed-commit assertion.
- Evidence self-test: false overall status, stale/commit mismatch, fallback, missing gate, unbounded queue, speaker drop, private leak.
- Longitudinal: 50 valid/natural/realtime turns, STT/WER, acoustics, memory, anchors, WavLM baseline/early/middle/late cosine.

## Manual-Only Verifications

| Behavior | Why manual | Status before handoff |
|---|---|---|
| Integrated clone likeness, naturalness, joins, early/middle/late listening | Automated WER/acoustic/speaker scores cannot make final audible identity judgment | pending; candidate spike listening accepted separately |
| Physical phone-call feel and barge-in | Device acoustics and human turn-taking require the builder's phone | pending after autonomous release-ready pass |

## Validation Sign-Off

- [ ] Every task automated gate passes.
- [ ] Plan 09-04 early real production tracer passes before broad expansion.
- [ ] Verifier named self-tests all fail closed as expected.
- [ ] Final real live E2E and commit assertion pass after canonical deploy.
- [ ] Decision-ready evidence is sanitized/current/commit-matched.
- [ ] Operational check receives phase dir, deployed SHA, passing-test summary, UI/live/GPU artifacts.
- [ ] Automated readiness is separated from pending integrated listening and physical call.
- [ ] Set `nyquist_compliant: true` only after these gates.
