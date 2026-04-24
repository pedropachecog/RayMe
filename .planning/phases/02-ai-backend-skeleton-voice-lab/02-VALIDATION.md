---
phase: 02
slug: ai-backend-skeleton-voice-lab
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-24
---

# Phase 02 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest for Web UI server and AI backend, Vitest for client unit checks, Playwright for browser acceptance |
| **Config file** | `web-ui/server/pyproject.toml`, `ai-backend/pyproject.toml`, `web-ui/client/vitest.config.ts`, `web-ui/client/playwright.config.ts` |
| **Quick run command** | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_health_settings.py -q && uv run --project ai-backend pytest ai-backend/tests -q` |
| **Full suite command** | `uv run --project web-ui/server pytest web-ui/server/tests -q && uv run --project ai-backend pytest ai-backend/tests -q && npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e` |
| **Live suite command** | `RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npm --prefix web-ui/client run test:e2e -- live-voice-lab.spec.ts --project=desktop-chromium` |
| **Estimated runtime** | Quick: ~60-120 seconds after Wave 0; full local: ~5-10 minutes; live OMEN-PC suite depends on model warmup |

---

## Sampling Rate

- **After every task commit:** Run the narrow pytest, Vitest, or Playwright spec for the files touched.
- **After every plan wave:** Run the full local suite command.
- **Before `$gsd-verify-work`:** Full local suite, live OMEN-PC health/status check, live desktop Playwright, then Android Chrome product-owner checkpoint.
- **Max feedback latency:** 10 minutes for local gates; live GPU/model gates may exceed this but must be isolated to explicit runtime evidence tasks.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-W0-01 | Wave 0 validation | 0 | REQ-15, REQ-20, REQ-22, REQ-23, REQ-24 | T-02-01 / T-02-04 | Voice APIs use stable IDs, generated blob names, tombstones, and `Voice unavailable` instead of dangling references | pytest | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q` | No - W0 creates | pending |
| 02-W0-02 | Wave 0 validation | 0 | REQ-02, REQ-A3 | T-02-02 / T-02-05 | AI backend reports model residency without leaking raw exceptions and degrades per failed engine | pytest | `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py ai-backend/tests/test_stt.py ai-backend/tests/test_tts_registry.py -q` | No - W0 creates | pending |
| 02-W0-03 | Wave 0 validation | 0 | REQ-05, REQ-80, REQ-90 | T-02-03 / T-02-06 | Settings keeps keys masked, saves before test, and exposes privacy defaults without pretending Phase 4 VAD wiring is complete | Vitest + Playwright | `npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e -- settings-connection.spec.ts voice-lab.spec.ts` | Partial - W0 extends | pending |
| 02-API-01 | Voice storage/API | 1 | REQ-15, REQ-20, REQ-22, REQ-23, REQ-24 | T-02-01 / T-02-04 | Uploads validate type/size/duration, ignore user filenames, and persist original samples atomically under internal IDs | pytest | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py web-ui/server/tests/test_characters.py -q` | No - W0 creates | pending |
| 02-SET-01 | Settings/API | 1 | REQ-05, REQ-80 | T-02-03 | Endpoint tests persist current values before probing and audio defaults are server-owned | pytest + Playwright | `uv run --project web-ui/server pytest web-ui/server/tests/test_health_settings.py -q && npm --prefix web-ui/client run test:e2e -- settings-connection.spec.ts` | Existing tests extend | pending |
| 02-AI-01 | AI backend model manager | 2 | REQ-02, REQ-A3 | T-02-02 / T-02-05 | Exactly one resident TTS engine is active; failed engines mark unavailable with reason while service stays healthy | pytest + live health | `uv run --project ai-backend pytest ai-backend/tests/test_model_manager.py ai-backend/tests/test_health.py -q` | No - W0 creates | pending |
| 02-AI-02 | STT/VAD processing | 2 | REQ-21, REQ-A3 | T-02-02 / T-02-05 | Transcription uses English `distil-large-v3`, VAD gate, `condition_on_previous_text=False`, and hallucination filters | pytest | `uv run --project ai-backend pytest ai-backend/tests/test_stt.py -q` | No - W0 creates | pending |
| 02-AI-03 | TTS registry/adapters | 2 | REQ-02, REQ-22, REQ-23 | T-02-02 / T-02-07 | Full six-engine roster is metadata-driven; engine switch status is visible and no engine failure takes down the service | pytest + live self-test | `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py -q` | No - W0 creates | pending |
| 02-UI-01 | Voice Lab/Library UI | 3 | REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-90 | T-02-01 / T-02-04 / T-02-06 | User text renders as text, preview is optional, and delete/unavailable states are recoverable | Vitest + Playwright | `npm --prefix web-ui/client run test:unit -- --run && npm --prefix web-ui/client run test:e2e -- voice-lab.spec.ts` | No - W0 creates | pending |
| 02-LIVE-01 | Live OMEN-PC acceptance | 4 | REQ-02, REQ-05, REQ-20, REQ-21, REQ-22, REQ-23, REQ-80, REQ-90 | T-02-02 / T-02-05 | Live backend uses canonical checkout/TLS, reports VRAM/headroom < 11 GB, and passes browser-verified Voice Lab flow before user Android testing | Playwright + curl + product-owner checkpoint | `RAYME_ENABLE_LIVE_E2E=1 RAYME_LIVE_WEB_URL=https://192.168.1.199:8443 RAYME_LIVE_AI_HEALTH_URL=https://192.168.1.199:9443/health npm --prefix web-ui/client run test:e2e -- live-voice-lab.spec.ts --project=desktop-chromium` | No - W0 creates | pending |

---

## Threat References

| Ref | Threat | Required Mitigation |
|-----|--------|---------------------|
| T-02-01 | Malicious or oversized uploaded audio | Validate extension/content type/size/duration server-side, generate internal blob names, and reject unsupported files before AI processing. |
| T-02-02 | Model OOM or failed engine load | Maintain one resident TTS engine, unload before switching, expose unavailable engines with reasons, and keep `/health` responsive. |
| T-02-03 | Settings secret or endpoint leakage | Keep LLM API keys server-side, expose only configured status, validate absolute HTTP(S) endpoint URLs, and preserve save-before-test behavior. |
| T-02-04 | Voice delete corrupts character references | Use stable voice IDs plus soft-delete/tombstone or equivalent state so UI can render `Voice unavailable`. |
| T-02-05 | Raw AI backend exceptions leak to the browser | Convert adapter failures into typed errors/status reasons and log details server-side only. |
| T-02-06 | Transcript, filename, or voice-name XSS | Render all user-controlled text as text, never raw HTML. |
| T-02-07 | License/caveat misrepresentation | Store engine metadata and ship license/caveat notes for F5-TTS, XTTS v2, Qwen3-TTS, LuxTTS, Chatterbox Turbo, and TADA 1B. |

---

## Wave 0 Requirements

- [ ] `web-ui/server/tests/test_voices.py` - voice schema/API/storage/upload/delete/default-voice coverage.
- [ ] `ai-backend/tests/test_model_manager.py` - one-hot residency, engine status, unavailable-engine degradation, VRAM payload coverage.
- [ ] `ai-backend/tests/test_stt.py` - STT option contract, VAD-gated transcription fallback, hallucination blocklist coverage.
- [ ] `ai-backend/tests/test_tts_registry.py` - six-engine registry metadata and one-resident switching coverage.
- [ ] `web-ui/client/tests/e2e/voice-lab.spec.ts` - upload/transcript/edit/save/library/default voice/delete unavailable states.
- [ ] `web-ui/client/tests/e2e/live-voice-lab.spec.ts` - opt-in live OMEN-PC health/status and one short engine self-test path.
- [ ] `web-ui/client/tests/unit/voice-lab.test.ts` - six-engine roster, optional preview, and `Save Voice` behavior contract checks.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Android Chrome Voice Lab smoke | REQ-A0 adjacent, REQ-90 | Physical Android trust, file picker, and audio output behavior require the user's device after agent browser/live checks pass | After full local, live OMEN-PC, and desktop Playwright checks pass, ask the user to open `https://192.168.1.199:8443`, upload a short sample, verify transcript/edit/save, and test-play one saved voice. |
| Subjective generated-voice quality | REQ-22, REQ-23 | The agent can verify audio generation and playback, but voice quality/caveat acceptance is product-owner judgment | After live synthesis succeeds, ask the user whether the generated sample is acceptable enough for Phase 3 call testing; record caveats rather than blocking all Phase 2 completion. |

---

## Validation Sign-Off

- [x] All phase requirements have automated coverage planned.
- [x] Sampling continuity: no 3 consecutive tasks without an automated verify command.
- [x] Wave 0 covers all missing validation references.
- [x] No watch-mode flags in required commands.
- [x] Feedback latency target is explicit.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
