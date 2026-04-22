---
phase: 0
slug: measurement-gate
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-18
---

# Phase 0 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (Python 3.11) |
| **Config file** | `.planning/phases/00-measurement-gate/probes/pytest.ini` (created in plan 01) |
| **Quick run command** | `python -m pytest .planning/phases/00-measurement-gate/probes/ -q` |
| **Full suite command** | `python -m pytest .planning/phases/00-measurement-gate/probes/ -v` |
| **Estimated runtime** | ~30 seconds (excluding 30-min soak runs and FA2 build) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest .planning/phases/00-measurement-gate/probes/ -q`
- **After every plan wave:** Run `python -m pytest .planning/phases/00-measurement-gate/probes/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds (excluding the soak/build subprocess runs which are gated by manual checkpoints)

---

## Per-Task Verification Map

Row N maps to plan `00-0N`. Every plan has a fast pytest-level verify for its pure-Python logic; measurement outputs (JSON files) are verified at the checkpoint level and re-checked by plan 08's consistency script.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 0-01-01 | 01 Wave 0 Setup | 1 | venv + smoke | — | No secrets in requirements-phase0.txt | smoke | `python -m pytest .planning/phases/00-measurement-gate/probes/ -q` | ✅ W0 | ⬜ pending |
| 0-02-01 | 02 HTTPS on iPhone | 2 | REQ-A1 | T-00-02-* | Cert trusted on iPhone Safari; `window.isSecureContext === true` | manual + script | `test -f .planning/phases/00-measurement-gate/results/https_iphone.json && python -c "import json; d=json.load(open('.planning/phases/00-measurement-gate/results/https_iphone.json')); assert d['strategy'] in ('tailscale','mkcert')"` | ❌ W0 | ⬜ pending |
| 0-03-01 | 03 Whisper WER | 2 | REQ-A3 | T-00-03-* | Voice sample gitignored (no PII in repo) | pytest | `python -m pytest .planning/phases/00-measurement-gate/probes/test_whisper_bench.py -q` (expect 8 passed) | ❌ W0 | ⬜ pending |
| 0-04-01 | 04 TTS TTFA | 2 | Resolved Tension #3 | T-00-04-* | Reference WAV gitignored | pytest | `python -m pytest .planning/phases/00-measurement-gate/probes/test_tts_ttfa.py -q` | ❌ W0 | ⬜ pending |
| 0-05-01 | 05 VRAM Soak | 3 | REQ-02 (VRAM budget) | T-00-05-* | No intermediate WAV staged for git | pytest | `python -m pytest .planning/phases/00-measurement-gate/probes/test_vram_soak.py -q` (expect 5 passed) | ❌ W0 | ⬜ pending |
| 0-06-01 | 06 LLM Cancel | 2 | REQ-03 (cancel <200ms) | T-00-06-* | No model weights committed | pytest | `python -m pytest .planning/phases/00-measurement-gate/probes/test_llm_cancel.py -q` | ❌ W0 | ⬜ pending |
| 0-07-01 | 07 FA2 Install | 2 | Phase 0 criterion #6 | T-00-07-* | Build logs tail-captured only | schema | `python -c "import json; d=json.load(open('.planning/phases/00-measurement-gate/results/fa2_install.json')); assert 'installed' in d and isinstance(d['installed'], bool); assert 'failure_reason' in d"` | ❌ W0 | ⬜ pending |
| 0-08-01 | 08 Synthesis + Writeback | 4 | All (consolidation) | T-00-08-* | No secrets in KEY_DECISIONS.md | structure | `test -f .planning/phases/00-measurement-gate/KEY_DECISIONS.md && grep -q "Phase 0 Key Decisions" .planning/PROJECT.md` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Wave topology note:** Plan 05 was bumped to Wave 3 (depends on plan 03's `results/whisper.json` + plan 04's `probes/fixtures/short_ref_audio.wav`). Plan 08 moved to Wave 4 accordingly. See each plan's frontmatter for authoritative `depends_on` / `wave` values.

---

## Wave 0 Requirements

All Wave 0 scaffolding is produced by plan 01 (wave 1) before any measurement plan runs:

- [x] `probes/__init__.py`, `probes/conftest.py`, `probes/pytest.ini` — pytest config
- [x] `probes/bench_utils.py` — shared helpers (`Timer`, `sample_vram_mb`, `warmup_cuda`, `write_results`, `gpu_info`)
- [x] `probes/test_smoke.py` — pytest smoke test proving the venv + imports work
- [x] `.venv-phase0/` — Python 3.11.5 venv pinned via `py -3.11 -m venv`
- [x] `requirements-phase0.txt` — pinned dep list
- [x] `.gitignore` entries — `*.wav`, `*.mp3`, `*.flac`, `*.onnx`, `.venv-phase0/`, `results/*.log`
- [x] `results/.gitkeep` — output directory placeholder

Per-plan artifacts (created by each plan, not Wave 0):

- Plan 03: `probes/whisper_bench.py`, `probes/test_whisper_bench.py`, `probes/fixtures/reference_transcript.txt`
- Plan 04: `probes/tts_ttfa.py`, `probes/test_tts_ttfa.py`, `probes/fixtures/short_ref_transcript.txt`
- Plan 05: `probes/vram_soak.py`, `probes/test_vram_soak.py`
- Plan 06: `probes/llm_cancel.py`, `probes/test_llm_cancel.py`
- Plan 07: `probes/fa2_check.py`

*All probes are standalone Python scripts, not production code — they are the deliverable of this spike.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HTTPS loads on iPhone with no cert warning | REQ-A1 / Phase 0 criterion #1 | Requires physical device (iPhone) + Safari browser interaction | 1. Load `https://rayme.local` (or Tailscale hostname) on iPhone Safari. 2. Confirm no cert warning. 3. Open browser console, run `window.isSecureContext`, confirm `true`. |
| Builder's read-aloud recording (reference_audio.wav) | Phase 0 criterion #2 | Only the builder can produce their own voice sample | Record ~10 min of the reference transcript in a quiet room, save to `probes/fixtures/reference_audio.wav` (mono, ≥16 kHz, gitignored). |
| Builder's short reference WAV (short_ref_audio.wav) | Phase 0 criterion #3 | Voice-clone reference — builder-only | Record 6–12 s of the short transcript, save to `probes/fixtures/short_ref_audio.wav` (mono, ≥24 kHz, gitignored). |
| Builder's subjective Qwen3-TTS listening test | Qwen3-TTS acceptance gate | Subjective voice quality assessment — accent preservation | Play Qwen3-TTS clone output of Spanish-accented English sample; builder rates acceptability per QWEN3-TTS.md §7. |
| Builder reviews KEY_DECISIONS.md before writeback | Plan 08 checkpoint | Decisions propagate to PROJECT.md + STATE.md — requires editorial judgment | Read KEY_DECISIONS.md, accept/override each of the 6 frozen decisions. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (plan 01 creates all shared helpers)
- [x] No watch-mode flags
- [x] Feedback latency < 30 s for pure-Python tests (measurement runs are gated by explicit checkpoints, not the sampling loop)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `wave_0_complete: true` set in frontmatter
- [x] Per-Task Verification Map covers all 8 plans (plans 01–08)

**Approval:** ready for execution.
