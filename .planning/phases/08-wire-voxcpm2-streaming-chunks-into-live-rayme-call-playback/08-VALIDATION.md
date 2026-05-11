---
phase: 08
slug: wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-11
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
| 08-01-01 | 08-01 | 1 | P8-R1 | T-08-01 | No empty or invalid chunk is queued; no raw VoxCPM2 errors are exposed | unit | `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py -q` | yes | pending |
| 08-04-01 | 08-04 | 1 | P8-R2 / P8-R5 | T-08-04 | Evidence tooling reads TTFA from immediate `ai_audio_started_event.tts_playback` and final proof fields from `tts_playback_final` | evidence contract | `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --contract-only` | no - Wave 1 creates | pending |
| 08-02-01 | 08-02 | 2 | P8-R1 / P8-R3 / P8-R4 | T-08-02 | Cancelled turns cannot enqueue later chunks or emit duplicate completion | integration | `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` | yes | pending |
| 08-03-01 | 08-03 | 3 | P8-R3 / P8-R4 | T-08-03 | Streaming failures return sanitized call TTS failure behavior only, and public call surfaces preserve immediate/final metric carriers | route/server integration | `uv run --project ai-backend pytest ai-backend/tests/test_webrtc_signaling.py -q && uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` | yes | pending |
| 08-05-01 | 08-05 | 4 | P8-R2 / P8-R3 / P8-R4 | T-08-05 | OMEN dirty checkout handling is user-gated; evidence cannot pass if streaming is absent, fallback is used, or VoxCPM2 median first-audio does not beat F5 | live evidence | `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --call-flow-only` | no - Wave 4 creates | pending |
| 08-06-01 | 08-06 | 5 | P8-R5 | T-08-06 | Durable decision writeback occurs only after decision-ready evidence passes | docs/evidence | `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py --decision-ready` | no - Wave 5 creates | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] Extend `ai-backend/tests/test_tts_voxcpm2.py` for `generate_streaming` chunk validation, sample-rate extraction, empty/invalid chunk rejection, and no fallback during evidence mode.
- [ ] Extend `ai-backend/tests/test_call_session.py` for first enqueue before final chunk completion, `ai_audio_started` timing, single `ai_done`, and interrupt-after-first-chunk discard.
- [ ] Extend `ai-backend/tests/test_webrtc_signaling.py` if speak-route response metrics or sanitized streaming failures change.
- [ ] Extend `web-ui/server/tests/test_calls.py` only if nested backend event/response shape changes for SSE keepalive or `ai_audio_started` forwarding.
- [ ] Create `.planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-run-call-flow-evidence.py`, `08-verify-evidence.py`, and `results/` artifacts by mirroring Phase 7 evidence patterns.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OMEN live same-run warm comparison | P8-R2 / P8-R5 | Requires RTX 3060 runtime, canonical OMEN deployment, microphone/WebRTC environment, and live evidence collection | Deploy only via `scripts/deploy-omen.sh`, run the Phase 8 evidence runner on OMEN, then run `python3 .planning/phases/08-wire-voxcpm2-streaming-chunks-into-live-rayme-call-playback/08-verify-evidence.py` and archive results under the Phase 8 `results/` directory |
| Durable promotion/default decision writeback | P8-R5 | Must be gated on the live evidence artifact produced in the same run | Verify `PROJECT.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, and the Phase 8 decision artifact agree with the evidence verdict |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency target is below 120 seconds for local targeted tests.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
