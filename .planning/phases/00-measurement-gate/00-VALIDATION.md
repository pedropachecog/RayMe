---
phase: 0
slug: measurement-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 0 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (Python 3.11) |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `python -m pytest .planning/phases/00-measurement-gate/probes/ -q` |
| **Full suite command** | `python -m pytest .planning/phases/00-measurement-gate/probes/ -v` |
| **Estimated runtime** | ~30 seconds (excluding soak tests) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest .planning/phases/00-measurement-gate/probes/ -q`
- **After every plan wave:** Run `python -m pytest .planning/phases/00-measurement-gate/probes/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 0-01-01 | 01 | 1 | HTTPS cert | — | Safari loads https://rayme.local with no cert warning | manual | `curl -sk https://rayme.local | grep isSecureContext` | ❌ W0 | ⬜ pending |
| 0-02-01 | 02 | 1 | Whisper WER | — | N/A | script | `python probes/whisper_bench.py --output results/whisper.json` | ❌ W0 | ⬜ pending |
| 0-03-01 | 03 | 1 | TTS TTFA | — | N/A | script | `python probes/tts_ttfa.py --output results/tts_ttfa.json` | ❌ W0 | ⬜ pending |
| 0-04-01 | 04 | 1 | VRAM soak | — | N/A | script | `python probes/vram_soak.py --output results/vram_soak.json` | ❌ W0 | ⬜ pending |
| 0-05-01 | 05 | 1 | LLM cancel | — | GPU drops to idle within ~200ms | script | `python probes/llm_cancel.py --output results/llm_cancel.json` | ❌ W0 | ⬜ pending |
| 0-06-01 | 06 | 1 | FA2 install | — | N/A | script | `python probes/fa2_check.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `probes/whisper_bench.py` — WER + latency + VRAM measurement rig for 3 Whisper model rungs
- [ ] `probes/tts_ttfa.py` — TTFA measurement for F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base
- [ ] `probes/vram_soak.py` — 30-min cycling soak tracking peak VRAM via nvidia-smi
- [ ] `probes/llm_cancel.py` — streaming Chat Completions cancel probe with nvidia-smi logging
- [ ] `probes/fa2_check.py` — FlashAttention 2 install verification
- [ ] `results/` directory — output JSON/log files for each probe run

*All probes are standalone Python scripts, not production code — they are the deliverable of this spike.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HTTPS loads on iPhone with no cert warning | Success criterion #1 | Requires physical device (iPhone) + Safari browser interaction | 1. Load `https://rayme.local` (or Tailscale hostname) on iPhone Safari. 2. Confirm no cert warning. 3. Open browser console, run `window.isSecureContext`, confirm `true`. |
| Builder's subjective TTS listening test | Qwen3-TTS acceptance gate | Subjective voice quality assessment — accent-preservation | Play Qwen3-TTS clone output of Spanish-accented English sample; builder rates acceptability. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
