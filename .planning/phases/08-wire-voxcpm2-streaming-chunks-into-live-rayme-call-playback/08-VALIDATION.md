---
phase: 08
slug: wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
status: audited
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-11
last_audited: 2026-05-11
---

# Phase 08 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest==9.0.3` for `ai-backend` and `web-ui/server`; `vitest` only if client code is touched |
| **Config file** | `ai-backend/pyproject.toml`; `web-ui/server/pyproject.toml`; `web-ui/client/package.json` if client code is touched |
| **Quick run command** | `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` |
| **Full suite command** | `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q && uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` |
| **Estimated runtime** | ~90 seconds locally for targeted suites; OMEN live evidence runtime is environment-dependent |

---

## Sampling Rate

- **After every task commit:** Run the quick command for the modified subsystem.
- **After every plan wave:** Run the full suite command above.
- **Before `$gsd-verify-work`:** Full targeted suites plus Phase 8 evidence verifier must be green.
- **Max feedback latency:** 120 seconds for local targeted tests; live OMEN evidence is exempt but must be recorded.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 08-01 | 1 | P8-R1 | T-08-01 | No empty or invalid chunk is queued; no raw VoxCPM2 errors are exposed | unit | `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py -q` | yes | green |
| 08-04-01 | 08-04 | 1 | P8-R2 / P8-R5 | T-08-04 | Evidence tooling reads TTFA from immediate `ai_audio_started_event.tts_playback` and final proof fields from `tts_playback_final` | evidence contract | `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --contract-only` | yes | green |
| 08-02-01 | 08-02 | 2 | P8-R1 / P8-R3 / P8-R4 | T-08-02 | Cancelled turns cannot enqueue later chunks or emit duplicate completion | integration | `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` | yes | green |
| 08-03-01 | 08-03 | 3 | P8-R3 / P8-R4 | T-08-03 | Streaming failures return sanitized call TTS failure behavior only, and public call surfaces preserve immediate/final metric carriers | route/server integration | `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q && uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` | yes | green |
| 08-05-01 | 08-05 | 4 | P8-R2 / P8-R3 / P8-R4 | T-08-05 | OMEN dirty checkout handling is user-gated; evidence cannot pass if streaming is absent, fallback is used, or VoxCPM2 median first-audio does not beat F5 | live evidence | `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --call-flow-only` | yes | green |
| 08-06-01 | 08-06 | 5 | P8-R5 | T-08-06 | Durable decision writeback occurs only after decision-ready evidence passes | docs/evidence | `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --decision-ready` | yes | green |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [x] Extend `ai-backend/tests/test_tts_voxcpm2.py` for `generate_streaming` chunk validation, sample-rate extraction, empty/invalid chunk rejection, and no fallback during evidence mode.
- [x] Extend `ai-backend/tests/test_call_session.py` for first enqueue before final chunk completion, `ai_audio_started` timing, single `ai_done`, and interrupt-after-first-chunk discard.
- [x] Extend `ai-backend/tests/test_webrtc_signaling.py` for speak-route response metrics and sanitized streaming failures.
- [x] Extend `web-ui/server/tests/test_calls.py` for nested backend event/response shape preservation, SSE `ai_audio_started` forwarding, and single durable `ai_speech` row.
- [x] Create `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py`, `08-verify-evidence.py`, and `results/` artifacts by mirroring Phase 7 evidence patterns.

---

## Manual-Only Verifications

All Phase 8 behaviors have automated pass/fail verification. The live OMEN run is environment-gated, but its archived artifacts are verified by `08-verify-evidence.py --call-flow-only` and `08-verify-evidence.py --decision-ready`.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency target is below 120 seconds for local targeted tests.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-05-11

---

## Validation Audit 2026-05-11

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Automated checks recorded | 7 |

| Check | Result |
|-------|--------|
| `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` | 77 passed, 3 warnings |
| `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` | 31 passed |
| `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_verify_evidence.py` | 3 passed |
| `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/tests/test_08_call_flow_runner.py` | 1 passed |
| `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --contract-only` | PASS |
| `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --call-flow-only` | PASS |
| `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --decision-ready` | PASS |
