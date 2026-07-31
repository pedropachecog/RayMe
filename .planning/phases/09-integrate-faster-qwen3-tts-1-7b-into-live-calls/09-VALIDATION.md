---
phase: 09
slug: integrate-faster-qwen3-tts-1-7b-into-live-calls
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-31
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3; Vitest 4.1.5; Playwright 1.59.1 |
| **Config file** | `ai-backend/pyproject.toml`, `web-ui/server/pyproject.toml`, `web-ui/client/vitest.config.ts`, `web-ui/client/playwright.config.ts` |
| **Quick run command** | `uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py ai-backend/tests/test_call_session.py ai-backend/tests/test_model_manager.py -q` |
| **Full suite command** | `uv run --project ai-backend pytest ai-backend/tests -q && uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run` |
| **Estimated runtime** | ~180 seconds locally; OMEN evidence is a separate hardware gate |

---

## Sampling Rate

- **After every task commit:** Run the focused test command named by that task; keep fake-worker feedback under 30 seconds.
- **After every plan wave:** Run `uv run --project ai-backend pytest ai-backend/tests -q && uv run --project web-ui/server pytest web-ui/server/tests -q && npm --prefix web-ui/client run test:unit -- --run` plus `git diff --check`.
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds for focused tests; hardware evidence is release-gated separately.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-W0-01 | W0 | 0 | REQ-22 | T-09-01 through T-09-06 | Worker events are request-scoped, bounded, validated, and sanitized. | unit | `uv run --project ai-backend pytest ai-backend/tests/test_tts_qwen3.py ai-backend/tests/test_tts_registry.py -q` | ❌ W0 | ⬜ pending |
| 09-W0-02 | W0 | 0 | REQ-45 | T-09-01, T-09-05 | Slow LLM/native streams play early; queue depth is bounded; no whole synthesis is called. | async contract | `uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` | ✅ extend | ⬜ pending |
| 09-W0-03 | W0 | 0 | REQ-45 | T-09-01, T-09-05 | Cancel/hangup rejects late chunks and normal completion/persistence. | API contract | `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q` | ✅ extend | ⬜ pending |
| 09-W0-04 | W0 | 0 | REQ-22 | T-09-04 | Voice/id migration, transcript alignment, readiness, and public errors cross backend/server/client. | integration | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q && npm --prefix web-ui/client run test:unit -- --run` | ✅ extend | ⬜ pending |
| 09-W0-05 | W0 | 0 | REQ-46 | T-09-05, T-09-06 | Exact CUDA identity, TTFA/RTF/VRAM, 50-turn stability, and real call-flow pass on OMEN. | hardware evidence | `RAYME_OMEN_VERIFY_QWEN3=1 scripts/deploy-omen.sh` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `ai-backend/tests/test_tts_qwen3.py` — worker protocol, runtime identity, prompt cache, alignment/ceiling, cancellation, crash/hang, and error sanitization.
- [ ] `web-ui/server/tests/test_call_tts_segments.py` — incremental natural segmentation and slow-LLM early submission.
- [ ] Migration fixture/test for exact legacy `qwen3_0_6b` voice/settings values and idempotent zero-row behavior.
- [ ] `09-evidence-manifest.json` — 20 locked scenarios and fixture hashes.
- [ ] `09-verify-evidence.py` — contracts-only and decision-ready verification modes.
- [ ] Integrated OMEN runner descended from Spikes 005/006, excluding private reference audio/transcript from git.
- [ ] Saved client E2E test/result for Voice Lab loading, prewarm, ready, and sanitized failure states.

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Clone likeness, naturalness, joins, and early/middle/late stability | REQ-22 | Automated STT/acoustic/speaker scores cannot make the final audible product judgment. | Listen blind to the pinned reference-set samples and longitudinal reel; require median likeness/naturalness at least 4/5, no item below 3/5, and no progressive muffling, whisper, noise, identity drift, or audible join. |
| Physical phone-call feel | REQ-45, REQ-46 | Browser/device acoustics, interruption feel, and human turn-taking require the builder's phone after agent-run gates pass. | Select the saved 1.7B voice in deployed RayMe, place a real call, confirm early speech, interrupt before and after first audio, continue multiple turns, and report any drift or stale audio. |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s for focused fake-worker tests
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
