# Phase 0 Re-Research Handoff

## What you need to do

The Phase 0 plans were written based on research of the **wrong machine**. The researcher probed `pedro-2023` (RTX 4090, 24GB), but the actual backend where Phase 0 measurements must run is a **separate LAN machine** (presumed RTX 3060 12GB). You need to re-research the LAN backend machine and rewrite `00-RESEARCH.md` with accurate findings, then identify which of the 8 PLAN.md files need patching.

---

## Project context

**Project:** RayMe — a local AI voice assistant (Whisper STT → LLM → TTS, running on a LAN-connected GPU machine).

**Phase 0 goal:** Pure measurement spike. Answer 6 empirical questions before writing any production code:
1. Can we get HTTPS trusted on an iPhone? (Tailscale cert or mkcert)
2. Which Whisper rung (distil-large-v3 INT8 / large-v3-turbo INT8 / large-v3 FP16) hits WER < 10% with acceptable latency?
3. Which TTS engine (F5-TTS, XTTS v2, Qwen3-TTS 0.6B-Base) has TTFA < 400ms?
4. Does each TTS engine stay within VRAM budget (< 11,000 MB peak) during a 30-min soak?
5. Can we cancel an in-flight LLM stream and return to idle in < 200ms?
6. Does FlashAttention 2 install successfully on this machine (gates Qwen3-TTS 1.7B)?

---

## What the current (wrong) research found — about `pedro-2023`

File: `.planning/phases/00-measurement-gate/00-RESEARCH.md`

Key findings that are WRONG for the backend:
- GPU: RTX 4090 24GB (sm_89) — backend is likely RTX 3060 12GB (sm_86)
- Hostname: `pedro-2023.tailc48d1c.ts.net` — wrong hostname for HTTPS cert
- Python: 3.11.9 installed, PyTorch 2.5.1+cu121 already present
- Tailscale 1.96.3 active, `tailscale cert` command available
- ollama 0.17.0 installed, llama-server installed
- FA2 not installed, requires source build

All of the above describes `pedro-2023`, NOT the backend.

---

## What you need to find out about the LAN backend machine

Use the SSH path that was set up for `OMEN-PC` at `192.168.1.199` first. Only ask for an alternate access method if SSH fails. Do **not** fall back to probing the local Codex workstation or its WSL shell.

Probe for:

### Hardware
- `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader`
- GPU name, VRAM total, driver version, compute capability (need to confirm it's sm_86 / RTX 3060)

### OS / Python
- `python --version` or `py -3.11 --version` (need Python 3.11 available)
- `python -c "import torch; print(torch.__version__, torch.cuda.get_device_name(0))"` (PyTorch installed?)
- `python -c "import faster_whisper"` (faster-whisper installed?)
- `python -c "import f5_tts"` (f5-tts installed?)
- `python -c "import TTS"` (coqui-tts installed?)

### Tailscale / networking
- `tailscale status` (is Tailscale installed and active?)
- `tailscale cert --help` (is cert command available?)
- Tailscale hostname (run `tailscale ip -4` and `hostname`) — needed for HTTPS plan
- Is the backend reachable at a LAN IP for iPhone HTTPS testing?

### LLM servers
- `ollama --version` or `ollama list` (is ollama installed?)
- `llama-server --version` (is llama-server / llama.cpp installed?)
- Is any LLM model already downloaded?

### FlashAttention 2
- `python -c "import flash_attn; print(flash_attn.__version__)"` (installed?)
- CUDA version: `nvcc --version` or `python -c "import torch; print(torch.version.cuda)"`
- MSVC / build tools available? `cl.exe` accessible?

### Disk
- Free disk space on the drive where models will be stored (Whisper large-v3 is ~3GB, TTS models 1–2GB each)

---

## Files to rewrite after re-research

1. **`00-RESEARCH.md`** — Full rewrite with backend machine findings. Keep the same sections/structure, update all hardware/software facts. The `## Open Questions (RESOLVED)` section must remain resolved — update answers to reflect backend reality.

2. **Plan patches needed (after research confirms facts):**
   - `00-01-wave0-setup-PLAN.md` — update `py -3.11 -m venv` command if Python path differs on backend; update package install steps if some are already installed
   - `00-02-https-iphone-PLAN.md` — replace `pedro-2023.tailc48d1c.ts.net` hostname with actual backend Tailscale hostname; update fallback strategy if Tailscale not installed on backend
   - `00-06-llm-cancel-PLAN.md` — update ollama/llama-server availability assumption
   - `00-07-fa2-install-PLAN.md` — update CUDA/compute cap assumptions for sm_86 vs sm_89

3. **`00-VALIDATION.md`** — likely no changes needed unless wave topology changes.

---

## Plans that probably don't need changes

- `00-03-whisper-wer-PLAN.md` — pure Python benchmark, hardware-agnostic logic; VRAM budget gate (<11GB) already correct for RTX 3060
- `00-04-tts-ttfa-PLAN.md` — same
- `00-05-vram-soak-PLAN.md` — `fits_3060_budget: peak_vram_mb < 11000` flag already correct
- `00-08-synthesis-writeback-PLAN.md` — pure file consolidation, no hardware assumptions

---

## Plan files location

All 8 plans are at:
```
.planning/phases/00-measurement-gate/
  00-01-wave0-setup-PLAN.md
  00-02-https-iphone-PLAN.md
  00-03-whisper-wer-PLAN.md
  00-04-tts-ttfa-PLAN.md
  00-05-vram-soak-PLAN.md
  00-06-llm-cancel-PLAN.md
  00-07-fa2-install-PLAN.md
  00-08-synthesis-writeback-PLAN.md
  00-RESEARCH.md         ← needs full rewrite
  00-VALIDATION.md       ← probably fine
```

---

## Your deliverables

1. Rewritten `00-RESEARCH.md` with accurate backend machine findings.
2. Patched PLAN.md files for plans 01, 02, 06, 07 (only the sections that reference hardware/hostname/package state).
3. A short summary of what changed and what was confirmed unchanged.

Do NOT re-run the plan-checker or re-do the full planning workflow — only update the facts that were wrong due to the wrong machine being probed. The plan structure, wave topology, and success criteria are correct.
