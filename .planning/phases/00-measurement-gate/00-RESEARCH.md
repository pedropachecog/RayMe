# Phase 0: Measurement Gate — Research

**Researched:** 2026-04-22
**Domain:** Empirical spike — HTTPS cert strategy, Whisper WER on accented English, TTS TTFA/RTF on actual hardware, VRAM soak methodology, LLM mid-stream cancel verification, FlashAttention 2 Windows install
**Confidence:** HIGH for backend machine state (probed directly over SSH); MEDIUM for install-path recommendations where the machine is not yet provisioned

---

## Summary

Phase 0 is a **pure measurement spike**. No production code ships here; the output is a set of empirical decisions that unblock Phases 1–6.

**Critical discovery from the corrected environment audit:** the real backend is the separate LAN machine `OMEN-PC` at `192.168.1.199`, and it **does** match the project constraint hardware: **RTX 3060 12 GB, driver 560.94, compute capability 8.6 / sm_86**. The previous research was wrong because it probed a different machine (`pedro-2023`, RTX 4090 24 GB).

**Execution guard:** every Phase 0 host command must run on `OMEN-PC` over SSH at `192.168.1.199`. If SSH is unavailable, stop and repair SSH access; do **not** fall back to this local Codex workstation or its WSL shell for backend measurements.

The backend is also much less provisioned than the prior research assumed:

- `python` and `py` resolve only to **Python 3.10.8**.
- `py -3.11` is **not installed**.
- `torch`, `faster_whisper`, `f5_tts`, `TTS`, and `flash_attn` are **not installed** in the system Python.
- `tailscale` is **not installed / not on PATH**.
- `ollama` and `llama-server` are **not installed / not on PATH**.
- `nvcc` is present and reports **CUDA toolkit 11.7**.
- `cl.exe` is **not on PATH**, so MSVC Build Tools are not currently usable from the shell.
- The user profile drive has about **40.2 GB free**, which is enough for Phase 0 model downloads and probe artifacts.

That changes the six Phase 0 questions materially:

1. **HTTPS on Android**: this backend cannot use the previously assumed Tailscale cert flow today because there is no Tailscale install or `.ts.net` hostname. The default path is now **mkcert over direct LAN**.
2. **Whisper WER**: the hardware target is finally correct (RTX 3060 12 GB), but the Python/torch stack must be installed first.
3. **TTS TTFA**: measurements will be on the intended 3060, but only after Python 3.11, torch, and the TTS packages are installed.
4. **VRAM soak**: the 11 GB budget gate is now a real hardware constraint instead of an extrapolation.
5. **LLM cancel**: a local OpenAI-compatible server is not present yet, so plan 06 must begin with server installation or explicit selection.
6. **FlashAttention 2 install**: this is now a higher-risk, more realistic Windows test because the host has CUDA 11.7 on PATH and no `cl.exe` on PATH yet.

**Primary recommendation:** treat plan 01 as real machine provisioning, not just a venv bootstrap. The corrected sequence is:

1. install Python 3.11 on the backend;
2. create `.venv-phase0` and install torch + Phase 0 packages;
3. use **mkcert** as the HTTPS primary path on `192.168.1.199`;
4. install or choose a local LLM server before the cancel probe;
5. expect FA2 to fail until MSVC Build Tools are installed or surfaced on PATH.

---

## Architectural Responsibility Map

Phase 0 still produces no application tiers. It only answers the six empirical questions that later phases depend on.

| Measurement | Informs Tier | Downstream Decision |
|---|---|---|
| HTTPS / cert trust on Android | Web UI host + LAN networking | Phase 1 HTTPS implementation choice (mkcert on LAN) |
| Whisper WER on Spanish-accented English | AI Backend — STT | Default STT model frozen before Phase 2 |
| TTS TTFA (F5, XTTS, Qwen3-TTS) | AI Backend — TTS | Default TTS engine frozen; Qwen3-TTS v1 inclusion/exclusion decided |
| VRAM 30-min soak | AI Backend — GPU resident | 3060-fit rule verified on the actual target hardware |
| LLM mid-stream cancel | AI Backend → LLM endpoint | Local LLM server choice confirmed; barge-in architecture validated |
| FlashAttention 2 install | AI Backend — Qwen3-TTS only | Qwen3-TTS 1.7B inclusion/exclusion decided |

---

## Standard Stack

### Python Environment for AI Backend

| Component | Current Backend State | Purpose | Phase 0 Implication |
|---|---|---|---|
| Python launcher | `python` / `py` -> 3.10.8 only | Base runtime | Python 3.11 must be installed before `.venv-phase0` can exist |
| Python 3.11 | NOT installed | Required AI backend runtime | Plan 01 must install it first; do not use 3.10 for the measurement env |
| PyTorch | NOT installed | GPU compute | Plan 01 must install torch inside the venv before any probe can run |
| faster-whisper | NOT installed | STT inference | Install in plan 01 |
| f5-tts | NOT installed | TTS engine #1 | Install in plan 01 |
| coqui-tts / `TTS` | NOT installed | XTTS v2 | Install in plan 01 |
| qwen-tts | NOT installed | TTS engine #3 | Install in plan 01 |
| flash-attn | NOT installed | FA2 / Qwen3-TTS 1.7B gate | Plan 07 owns the attempt |
| jiwer / soundfile / librosa / pynvml / httpx / pytest | NOT installed | Probe support libs | Install in plan 01 |

**Package pin set:** the existing plan pins still make sense and are not invalidated by the machine correction:

- `faster-whisper==1.2.1`
- `f5-tts==1.1.17`
- `coqui-tts[server]==0.27.5`
- `qwen-tts==0.1.1`
- `flash-attn` target remains `2.8.3` for plan 07

**PyTorch wheel note:** official PyTorch 2.5.1 Windows wheels exist for both `cu118` and `cu121`. Because this backend exposes `nvcc` 11.7 on PATH and no CUDA 12.x toolkit, `cu118` is the lower-friction starting point for plan 01. This is an inference from the host state plus the official PyTorch wheel matrix, not something already installed on the backend.

### HTTPS Strategy Tools

| Tool | Installed | Purpose | Notes |
|---|---|---|---|
| Tailscale | NO | Optional HTTPS strategy | No command on PATH, no tailnet hostname, no tailnet IP available today |
| mkcert | NO | Primary HTTPS strategy on this backend | Must be installed before plan 02 can run |
| openssl | NO | Optional cert helper | Not on PATH; not the preferred path anyway |

**Networking identity for the real backend:**

- Hostname: `OMEN-PC`
- LAN IP: `192.168.1.199`
- No Tailscale hostname currently exists for this box

### LLM Servers

| Server | Installed | Path | Notes |
|---|---|---|---|
| ollama | NO | — | Must be installed before using the Ollama path in plan 06 |
| llama-server | NO | — | Must be installed or otherwise made available before using the llama.cpp path |

### Build / GPU Tooling

| Tool | Installed | Version / State | Notes |
|---|---|---|---|
| `nvidia-smi` | YES | RTX 3060, 12288 MiB, driver 560.94, compute cap 8.6 | This is the correct target hardware |
| `nvcc` | YES | CUDA toolkit 11.7.99 | Present on PATH |
| `cl.exe` | NO | not found on PATH | FA2 source builds will likely fail until MSVC Build Tools are installed or loaded into PATH |

---

## Architecture Patterns

### System Data Flow for Phase 0 Measurements

```text
Measurement Spike (Phase 0)
          |
          |--- [M1] HTTPS Probe
          |      Browser -> https://rayme.local or https://192.168.1.199:8443
          |      Android Chrome -> window.isSecureContext check
          |      Transport trust via mkcert-installed root CA
          |
          |--- [M2] STT WER Measurement
          |      Reference audio (builder voice) -> faster-whisper
          |      Three models: distil-large-v3 INT8, large-v3-turbo INT8, large-v3 FP16
          |      WER via jiwer, latency via monotonic timer, VRAM via torch + nvidia-smi
          |
          |--- [M3] TTS TTFA Measurement
          |      Short text (3-5 words) -> each TTS engine
          |      Engines: F5-TTS, XTTS v2, Qwen3-TTS 0.6B
          |
          |--- [M4] 30-Minute VRAM Soak
          |      Per-engine: {Whisper default + Silero + one TTS engine}
          |      Evaluate against the real 11 GB / 12 GB target budget
          |
          |--- [M5] LLM Cancel Probe
          |      Python script -> whichever local OpenAI-compatible server is installed
          |      Poll nvidia-smi after stream close
          |
          \--- [M6] FlashAttention 2 Install
                 Python 3.11 venv from plan 01 -> pip install flash-attn --no-build-isolation
                 Requires torch already installed; likely blocked until MSVC Build Tools are available
```

### Recommended Project Structure for Phase 0

```text
.planning/phases/00-measurement-gate/
  probes/
    bench_utils.py
    https_serve.py
    whisper_bench.py
    tts_bench.py
    llm_cancel.py
    fa2_check.py
  results/
    setup_install.json
    https_android.json
    whisper.json
    tts.json
    vram_soak.json
    llm_cancel.json
    fa2_install.json
```

This matches the existing plan files more closely than the previous `spikes/` recommendation.

### Pattern 1: WER Measurement Script

```python
from faster_whisper import WhisperModel
import jiwer
import time


def measure_wer(model_name: str, compute_type: str, audio_path: str, reference: str):
    model = WhisperModel(model_name, device="cuda", compute_type=compute_type)
    t0 = time.perf_counter()
    segments, _ = model.transcribe(
        audio_path,
        beam_size=5,
        condition_on_previous_text=False,
    )
    hypothesis = " ".join(s.text for s in segments)
    elapsed = time.perf_counter() - t0
    return {
        "wer": jiwer.wer(reference, hypothesis),
        "latency_s": elapsed,
        "hypothesis": hypothesis,
    }
```

### Pattern 2: TTFA Measurement for TTS Engines

```python
import time


def measure_ttfa_f5(ref_audio: str, ref_text: str, target_text: str) -> float:
    from f5_tts.api import F5TTS

    model = F5TTS()
    t0 = time.perf_counter()
    model.infer(ref_audio, ref_text, target_text, nfe_step=7)
    return time.perf_counter() - t0
```

Plan 04 still owns the concrete per-engine implementation details; the correction here is that the machine is finally the intended 3060 target.

### Pattern 3: LLM Cancel Probe

```python
import asyncio
import time
import httpx


async def probe_llm_cancel(base_url: str, model: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        async with client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Write a 500-word essay."}],
                "stream": True,
                "max_tokens": 500,
            },
        ) as response:
            t0 = time.perf_counter()
            tokens_seen = 0
            async for chunk in response.aiter_lines():
                tokens_seen += 1
                if time.perf_counter() - t0 > 0.5:
                    break
    return tokens_seen
```

The key correction is not the probe logic. It is that **no server is installed yet**, so the probe cannot start from a pre-existing local endpoint assumption.

### Pattern 4: HTTPS Probe on Direct LAN

```python
import ssl
import http.server

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("rayme.local.pem", "rayme.local-key.pem")

with http.server.HTTPServer(("192.168.1.199", 8443), http.server.SimpleHTTPRequestHandler) as server:
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
```

The important backend correction is that the machine has no Tailscale today, so the probe should start from a LAN-bound mkcert flow.

### Anti-Patterns to Avoid

- **Assuming `py -3.11` exists because it existed on the wrong machine:** it does not.
- **Assuming torch is preinstalled:** it is not.
- **Assuming the HTTPS path can start with `tailscale cert`:** it cannot on this backend until Tailscale is installed.
- **Assuming the cancel probe can run immediately against Ollama:** no local LLM server is currently available.
- **Assuming FA2 failure means “unsupported GPU”:** the more immediate blocker is likely missing MSVC tooling or Python/torch provisioning, not the Ampere GPU itself.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| WER calculation | Custom edit-distance code | `jiwer` | Standard, normalized WER metrics |
| HTTPS trust | Self-signed ad hoc cert workflow | `mkcert` | Simple LAN trust path for Android Chrome |
| VRAM monitoring | Manual spreadsheet logging | `torch.cuda` + `nvidia-smi` | Captures allocator state plus device totals |
| Local LLM API | Custom shim over raw model binaries | `ollama` or `llama-server` | OpenAI-compatible endpoint is what plan 06 needs |
| FA2 build logic | Custom C++ build steps | `pip install flash-attn --no-build-isolation` | Fastest way to measure whether the host supports it |

---

## Runtime State Inventory

This backend starts almost empty relative to the old research:

- no Phase 0 venv
- no Python 3.11
- no torch
- no AI packages
- no HTTPS toolchain
- no local LLM server

That means Phase 0 is now a real bootstrap on the correct hardware, not just a “run the measurements” pass.

---

## Common Pitfalls

### Pitfall 1: Python 3.11 Is Missing on the Backend

**What goes wrong:** plan 01 starts with `py -3.11 -m venv .venv-phase0` and immediately fails because `py -3.11` is not available.

**Why it happens:** only Python 3.10.8 is installed on `OMEN-PC`.

**How to avoid:**

- Install Python 3.11 first.
- Re-open the shell so the `py` launcher sees the new runtime.
- Do not try to force the ML stack into Python 3.10 just because it is present.

### Pitfall 2: HTTPS Research Assumed Tailscale, but the Backend Has No Tailscale

**What goes wrong:** plan 02 begins with `tailscale cert ...` and fails immediately because `tailscale` is not installed.

**Why it happens:** the wrong-machine research imported the dev machine’s tailnet setup.

**How to avoid:**

- Make **mkcert over direct LAN** the primary path.
- Use `rayme.local` or a LAN hostname plus `192.168.1.199`.
- Treat Tailscale as optional future convenience, not a current prerequisite.

### Pitfall 3: No Local LLM Server Exists Yet

**What goes wrong:** plan 06 assumes `ollama serve` or `llama-server --version` works and discovers neither binary exists.

**Why it happens:** this backend has not been provisioned with a local OpenAI-compatible LLM server.

**How to avoid:**

- Install a local server first, or explicitly defer the cancel probe until one exists.
- Prefer a small local model for the probe; the goal is cancel semantics, not model quality.

### Pitfall 4: FA2 Is More Likely to Fail on Missing Build Tooling Than on the GPU

**What goes wrong:** FA2 build logs may look like “unsupported” or “build failed,” but the actual blocker is missing `cl.exe` or an incompatible local toolchain.

**Why it happens:** `nvcc` is present, but MSVC is not on PATH.

**How to avoid:**

- Validate `cl.exe` before attempting plan 07.
- Record the exact failure mode in `results/fa2_install.json`.
- Treat “toolchain missing” as a provisioning issue, not a GPU-eligibility issue.

### Pitfall 5: First-Run Downloads and Installs Are Real Work on This Backend

**What goes wrong:** WER, TTS, and soak probes all appear “slow” or “hung” on first run because the machine is downloading weights and installing packages for the first time.

**Why it happens:** unlike the previously probed dev machine, this backend is not warm.

**How to avoid:**

- Pre-download Whisper weights in plan 01.
- Expect package install time and model-download time to dominate the first setup pass.

---

## Code Examples

### Python 3.11 Preflight

```powershell
py -3.11 --version
```

If this fails with “No suitable Python runtime found,” install Python 3.11 before continuing.

### PyTorch Wheel Install (Official Windows Wheel Matrix)

```powershell
.venv-phase0\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu118
```

This is the lower-friction starting point for this host because `nvcc` 11.7 is present and no CUDA 12.x toolkit was found on PATH.

### mkcert LAN HTTPS Flow

```powershell
mkcert -install
mkcert rayme.local 192.168.1.199

.venv-phase0\Scripts\python.exe probes\https_serve.py `
  --host rayme.local `
  --cert rayme.local+1.pem `
  --key  rayme.local+1-key.pem `
  --bind 192.168.1.199 `
  --port 8443
```

### FA2 Preflight

```powershell
where nvcc
where cl
```

If `cl.exe` is absent, expect plan 07 to fail until MSVC Build Tools are installed or the environment is loaded correctly.

---

## State of the Art

| Old Approach | Current Approach | Impact on RayMe |
|---|---|---|
| Trust Android Chrome via Tailscale-only assumptions | Trust Android Chrome via mkcert on LAN; add Tailscale later if desired | Matches the actual backend state |
| Extrapolate 3060 behavior from a 4090 dev box | Measure directly on the real 3060 | Removes the main Phase 0 hardware uncertainty |
| Assume backend is pre-provisioned | Treat backend as fresh Windows host | Makes setup steps explicit and reproducible |
| Assume local LLM server already exists | Install or choose one before the cancel probe | Prevents plan 06 from failing on missing binaries |

**Deprecated/outdated for this backend:**

- The old Tailscale hostname from the wrong machine.
- The assumption that Python 3.11 + torch are already installed.
- The assumption that Ollama and llama.cpp are already available.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | Installing Python 3.11 alongside 3.10 on this host is straightforward and low-risk | Summary, Common Pitfalls #1 | If installation is blocked by policy, plan 01 must begin with a machine-setup step |
| A2 | PyTorch 2.5.1 `cu118` is the lower-friction starting wheel for this backend | Standard Stack, Code Examples | If a different wheel works better, plan 01 should record the actual installed version instead of forcing this inference |
| A3 | mkcert is the right default HTTPS path because Tailscale is absent | Summary, Common Pitfalls #2 | If the user installs Tailscale before plan 02 runs, plan 02 can still take the Tailscale branch |
| A4 | FA2 will likely fail first on missing MSVC tooling rather than on GPU support | Common Pitfalls #4 | If `cl.exe` exists outside PATH or a dev shell is used, plan 07 may proceed further than expected |
| A5 | A small local model is sufficient for the cancel probe | Common Pitfalls #3 | If only a remote/API LLM is available, plan 06 cannot validate local GPU idle semantics |

---

## Open Questions (RESOLVED)

1. **Is `OMEN-PC` actually the real backend machine?**
   - What we know: it is the LAN box at `192.168.1.199` the user identified as the backend.
   - What's unclear: nothing material remains here.
   - **RESOLVED:** yes. This is the correct Phase 0 backend, and it has the intended RTX 3060 12 GB GPU.

2. **Does this backend support the Tailscale HTTPS path today?**
   - What we know: `tailscale` is not installed / not on PATH.
   - What's unclear: whether the user will later choose to install it.
   - **RESOLVED:** no, not today. Plan 02 must start from mkcert over LAN.

3. **Is Python 3.11 already available for the AI environment?**
   - What we know: only Python 3.10.8 is available through `python` and `py`.
   - What's unclear: nothing material.
   - **RESOLVED:** no. Plan 01 must install Python 3.11 before creating `.venv-phase0`.

4. **Are FA2 prerequisites already satisfied on this machine?**
   - What we know: `nvcc` 11.7 is present; `cl.exe` is not on PATH.
   - What's unclear: whether MSVC Build Tools are installed but not loaded into the shell.
   - **RESOLVED:** not currently. Plan 07 must expect missing MSVC tooling as a likely first blocker.

5. **Is a local OpenAI-compatible LLM server already available?**
   - What we know: `ollama` and `llama-server` are both absent from PATH.
   - What's unclear: whether the user intends to install one before plan 06 runs.
   - **RESOLVED:** no. Plan 06 must begin with installing or selecting a local server.

6. **Is there enough local disk for Phase 0 artifacts?**
   - What we know: user profile directory listing reported `40,232,869,888` bytes free.
   - What's unclear: exact free space on other volumes, if any.
   - **RESOLVED:** yes. There is enough space for the expected Phase 0 packages, weights, and result files.

---

## Environment Availability

| Dependency | Required By | Available | Version / State | Action |
|---|---|---|---|---|
| Python 3.11 | All AI probes | NO | `py -3.11` missing | Install before plan 01 continues |
| Python 3.10 | Host tooling only | YES | 3.10.8 | Do not use as the measurement runtime |
| PyTorch | All AI inference scripts | NO | import fails | Install in `.venv-phase0` |
| RTX 3060 (12 GB) | STT/TTS/VRAM probes | YES | 12288 MiB, driver 560.94, sm_86 | Correct target hardware |
| `nvcc` | FA2 build path | YES | CUDA 11.7.99 | Present on PATH |
| `cl.exe` | FA2 build path | NO | not found | Install / expose MSVC Build Tools |
| Tailscale | Optional HTTPS path | NO | command not found | Ignore for now or install later |
| mkcert | Primary HTTPS path | NO | command not found | Install in plan 02 |
| `ollama` | Preferred LLM cancel path | NO | command not found | Install before plan 06 |
| `llama-server` | LLM cancel fallback | NO | command not found | Install or provide separately |
| `faster-whisper` | STT WER | NO | import absent | Install in plan 01 |
| `f5-tts` | TTS TTFA | NO | import absent | Install in plan 01 |
| `TTS` / coqui-tts | XTTS TTFA | NO | import absent | Install in plan 01 |
| `qwen-tts` | Qwen3-TTS TTFA | NO | import absent | Install in plan 01 |
| `flash_attn` | FA2 gate | NO | import absent | Attempt in plan 07 |
| Disk free | Model downloads / results | YES | ~40.2 GB free in user profile volume | Sufficient for Phase 0 |

---

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | `pytest` + `pytest-asyncio` |
| Probe package root | `.planning/phases/00-measurement-gate/probes/` |
| Quick run command | `.venv-phase0/Scripts/python.exe -m pytest .planning/phases/00-measurement-gate/probes -x -q` |
| Full suite command | `.venv-phase0/Scripts/python.exe -m pytest .planning/phases/00-measurement-gate/probes -v` |

### Phase Requirements → Test Map

Phase 0 still delivers no shipped REQ IDs. Validation remains probe-driven.

| Spike Item | Behavior | Test Type | Automated? |
|---|---|---|---|
| HTTPS probe | `window.isSecureContext === true` on Android Chrome | Manual Android verification + automated local server | Partial |
| STT WER | WER, latency, VRAM logged for 3 models | Automated probe | YES |
| TTS TTFA | TTFA and RTF logged for 3 engines | Automated probe | YES |
| VRAM soak | Peak VRAM < 11 GB and no unbounded growth | Automated 30-min probe | YES |
| LLM cancel | GPU drops to idle <= 200 ms after stream close | Automated probe + local server install prerequisite | Partial |
| FA2 install | `from flash_attn import flash_attn_func` succeeds | Automated install probe | YES |

### Wave 0 Gaps

- [ ] Python 3.11 is not installed on the backend
- [ ] `.venv-phase0/` does not exist
- [ ] torch and all Phase 0 packages are missing
- [ ] mkcert is missing
- [ ] no local LLM server is available
- [ ] MSVC tooling is not available on PATH for FA2 builds

---

## Security Domain

Phase 0 still produces no persistent app surface, but the corrected backend state changes one operational note:

- HTTPS private keys generated by mkcert must remain local and gitignored.
- The temporary research SSH account should not be reused for production and can be rotated after the Phase 0 work is done.

No ASVS categories apply directly to the spike itself.

---

## Sources

### Primary (HIGH confidence)

- Live backend probe on `OMEN-PC` (`192.168.1.199`) over SSH on 2026-04-22 using:
  - `hostname`
  - `whoami`
  - `ipconfig`
  - `nvidia-smi --query-gpu=...`
  - `python --version`
  - `py -0p`
  - `python -c "import ..."`
  - `Get-Command ollama,llama-server,nvcc,cl`
  - `where mkcert`
  - `where tailscale`
  - `dir C:\Users\rayme-ssh`
- [PyTorch previous versions (official)](https://pytorch.org/get-started/previous-versions) — confirms Windows wheel availability for PyTorch 2.5.1 `cu118` and `cu121`
- `.planning/research/STACK.md`
- `.planning/research/PITFALLS.md`
- `.planning/research/QWEN3-TTS.md`

### Secondary (MEDIUM confidence)

- Existing Phase 0 plans under `.planning/phases/00-measurement-gate/`
- Existing package pins already captured in the plan set from the earlier non-machine-specific research

---

## Metadata

**Confidence breakdown:**

- Hardware / driver / GPU memory: HIGH
- Python / package / binary availability: HIGH
- HTTPS current-path recommendation: HIGH
- Local LLM server absence: HIGH
- FA2 install prognosis before running it: MEDIUM
- Exact final torch wheel choice for plan 01: MEDIUM

**Research date:** 2026-04-22
**Valid until:** 2026-05-22, unless the backend is reprovisioned
