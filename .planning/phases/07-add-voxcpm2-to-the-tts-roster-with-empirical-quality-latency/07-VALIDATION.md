---
phase: 07
slug: add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-11
---

# Phase 07 - Validation Strategy

Per-phase validation contract for VoxCPM2 roster integration, runtime evidence, and promotion gating.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| AI backend framework | `pytest==9.0.3`, configured in `ai-backend/pyproject.toml` |
| Web UI server framework | `pytest==9.0.3` and `pytest-asyncio==1.3.0`, configured in `web-ui/server/pyproject.toml` |
| Client unit framework | `vitest==4.1.5`, configured by `web-ui/client/package.json` |
| Client E2E framework | `@playwright/test==1.59.1`, configured by `web-ui/client/package.json` |
| Quick run command | `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py -q` plus targeted tests for the touched tier |
| Full suite command | `uv run --project ai-backend pytest -q && uv run --project web-ui/server pytest -q && npm --prefix web-ui/client run test:unit && npm --prefix web-ui/client run test:e2e` |
| Estimated runtime | Quick: under 60 seconds for targeted unit tests; full suite depends on Playwright and live-gated tests |

---

## Sampling Rate

- **After every task commit:** Run the narrow unit or browser test for the touched tier plus `git diff --check`.
- **After every plan wave:** Run AI backend pytest, Web UI server pytest, client unit tests, and affected Playwright specs.
- **Before `$gsd-verify-work`:** Full suite must be green, OMEN deployment must use `scripts/deploy-omen.sh`, live RTX 3060 artifacts must be saved, and manual quality evidence must be complete.
- **Max feedback latency:** No implementation task may defer automated feedback for more than two subsequent task commits. Live OMEN and manual-listening checks may remain wave-gated but must have explicit artifact paths.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-00-01 | Wave 0 contracts | 0 | REQ-02, REQ-45 | T-07-01 / T-07-05 | VoxCPM2 tests fail first for registry, CUDA-only load, option mapping, and scenario rows | unit | `uv run --project ai-backend pytest ai-backend/tests/test_tts_voxcpm2.py ai-backend/tests/test_tts_registry.py -q` | No, planner must add | pending |
| 07-00-02 | Wave 0 contracts | 0 | REQ-20, REQ-21, REQ-22, REQ-23 | T-07-04 | Voice metadata tests fail first for VoxCPM2 mode/style persistence and bounded payloads | server + client | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q && npm --prefix web-ui/client run test:unit -- voice-lab` | Partial, planner must extend | pending |
| 07-00-03 | Wave 0 contracts | 0 | REQ-41, REQ-42, REQ-62 | T-07-03 / T-07-04 | Call tests fail first for VoxCPM2 payload forwarding and sanitized engine-scoped failures | server + backend | `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q && uv run --project ai-backend pytest ai-backend/tests/test_call_session.py ai-backend/tests/test_webrtc_signaling.py -q` | Partial, planner must extend | pending |
| 07-00-04 | Wave 0 evidence scaffolding | 0 | REQ-45, REQ-A3 | T-07-01 / T-07-06 | Evidence filenames, CSV headers, generated audio paths, and promotion gate fields are deterministic | probe + artifact | `python -m pytest .planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py -q` | Partial, planner must extend | pending |
| 07-01-* | Metadata and optional runtime | 1 | REQ-02, REQ-80 | T-07-01 / T-07-02 / T-07-05 | Missing `voxcpm` marks only VoxCPM2 unavailable with sanitized reasons; other engines remain usable | unit | `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py ai-backend/tests/test_tts_voxcpm2.py -q` | No, after Wave 0 | pending |
| 07-02-* | Voice Lab and client controls | 2 | REQ-20, REQ-21, REQ-22, REQ-23, REQ-80 | T-07-04 | Style/mode text and numeric controls are bounded and ignored for non-VoxCPM2 engines | server + client | `uv run --project web-ui/server pytest web-ui/server/tests/test_voices.py -q && npm --prefix web-ui/client run test:unit -- voice-lab && npm --prefix web-ui/client run test:e2e -- voice-lab` | Partial | pending |
| 07-03-* | Call integration | 3 | REQ-41, REQ-42, REQ-62 | T-07-03 / T-07-04 | VoxCPM2 failures are call-visible but do not expose traceback/model paths or break other engines | server + backend + E2E | `uv run --project web-ui/server pytest web-ui/server/tests/test_calls.py -q && uv run --project ai-backend pytest ai-backend/tests/test_call_session.py -q` | Partial | pending |
| 07-04-* | OMEN runtime evidence | 4 | REQ-02, REQ-45 | T-07-01 / T-07-02 / T-07-05 | `voxcpm==2.0.2` load uses CUDA on OMEN, logs cache/model paths, and rejects CPU fallback | live artifact | `scripts/deploy-omen.sh` followed by documented AI backend runtime smoke on `rayme-pmpg` | No | pending |
| 07-05-* | Runtime path decision and backend runtime | 1 | REQ-02, REQ-22, REQ-45, REQ-80, REQ-A3 | T-07-01 / T-07-05 | Standard Python API, `generate_streaming`, NanoVLLM-VoxCPM, and vLLM-Omni-style serving are evaluated before implementation | artifact + unit | `uv run --project ai-backend pytest ai-backend/tests/test_tts_registry.py ai-backend/tests/test_model_manager.py ai-backend/tests/test_tts_voxcpm2.py -q` | No | pending |
| 07-11-* | Live matrix and call-flow evidence | 4 | REQ-02, REQ-20, REQ-21, REQ-23, REQ-41, REQ-42, REQ-45, REQ-62, REQ-A3 | T-07-03 / T-07-06 | Scenario matrix, generated WAVs, preview/test-play, and call speak evidence are saved and independently verified | live artifact | `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --matrix-only && python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --call-flow-only` | No | pending |
| 07-12-* | Manual quality and promotion decision | 5 | REQ-02, REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-41, REQ-42, REQ-45, REQ-62, REQ-80, REQ-A3 | T-07-06 | Promotion/caveat/unavailable outcome is backed by scenario matrix, WAVs, VRAM soak, call-flow proof, and manual CSV | artifact + manual | `python3 .planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/07-verify-evidence.py --decision-ready` | No | pending |

---

## Wave 0 Requirements

- [ ] `ai-backend/tests/test_tts_voxcpm2.py` - RED tests for adapter load guard, option mapping, cloning-mode fallback, sample-rate handling, streaming contract, and sanitized failures.
- [ ] `web-ui/server/tests/test_voices.py` additions - RED tests for VoxCPM2 metadata persistence, save/update behavior, preview payloads, and test-play payloads.
- [ ] `web-ui/server/tests/test_calls.py` additions - RED tests proving call voice references include VoxCPM2 mode/style options without changing the public browser API.
- [ ] `web-ui/client/tests/unit/voice-lab.test.ts` and `web-ui/client/tests/e2e/voice-lab.spec.ts` additions - RED tests for conditional VoxCPM2 controls, missing-transcript warning, preserved metadata on engine switch, and fallback roster rendering.
- [ ] `.planning/phases/00-measurement-gate/probes/test_tts_scenario_matrix.py` additions - RED tests for `voxcpm2` short/medium/long scenario rows and generated artifact paths.
- [ ] Phase 7 evidence scaffold - create deterministic paths under `.planning/phases/07-add-voxcpm2-to-the-tts-roster-with-empirical-quality-latency/results/` and `MANUAL-QUALITY.csv`.
- [ ] OMEN install/load smoke evidence template - records `uv sync --project ai-backend --extra tts`, `import voxcpm`, `VoxCPM.from_pretrained(... device="cuda")`, model cache path, sample rate, VRAM, and sanitized failure behavior.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Builder voice quality | REQ-A3, REQ-45 | Voice match, accent preservation, prosody, sample leakage, and mumbling artifacts require human listening | Fill `MANUAL-QUALITY.csv` for short/medium/long VoxCPM2 samples and comparable F5 samples using intelligibility, voice match, accent preservation, prosody, leakage, and artifact columns |
| Real call feel | REQ-41, REQ-42, REQ-45, REQ-62 | Automated tests can prove plumbing but not perceived call latency and interruption feel | Run a real call on OMEN after `scripts/deploy-omen.sh`, save call-flow evidence JSON, and record whether warm VoxCPM2 beats F5 on call-feel latency without regressions |
| Promotion decision | REQ-45, REQ-A3 | The final default/caveat choice combines measured latency, VRAM, call behavior, and listening judgment | Write the final Phase 7 decision to a summary artifact naming one outcome: promoted, selectable with caveats, visible unavailable, or rejected from runtime loading |

---

## Threat References

| Threat | Description | Required Control |
|--------|-------------|------------------|
| T-07-01 | VoxCPM2 package/model supply-chain drift | Pin `voxcpm==2.0.2`, record HF model SHA/cache path, and keep large downloads out of git |
| T-07-02 | User audio path traversal or unsafe filenames | Use existing asset-id blob storage and temp files; never use original filenames as paths |
| T-07-03 | Raw traceback, model path, or local cache disclosure | Return fixed public `tts_failed` or `call_tts_failed` details and sanitized unavailable reasons |
| T-07-04 | Unbounded transcript/style/control inputs causing resource exhaustion | Bound style text, transcript length, synthesis text length, `cfg_value`, `inference_timesteps`, retry counts, and sample duration |
| T-07-05 | CPU fallback produces false acceptance | Require CUDA torch, pass `device="cuda"`, and fail visible when CUDA is unavailable |
| T-07-06 | Generated voice misuse or ambiguous evidence | Keep generated evidence local, label samples as AI-generated, and limit quality scoring to builder-owned local samples |

---

## Validation Sign-Off

- [x] All planned implementation areas have automated verify hooks or Wave 0 dependencies.
- [x] Sampling continuity rule defined: no 3 consecutive implementation tasks without automated verify.
- [x] Wave 0 covers current missing test and evidence references.
- [x] No watch-mode flags in validation commands.
- [x] Manual-only checks have artifact paths and acceptance fields.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
