# Phase 0: Measurement Gate — Research

**Researched:** 2026-04-18
**Domain:** Empirical spike — HTTPS cert strategy, Whisper WER on accented English, TTS TTFA/RTF on actual hardware, VRAM soak methodology, LLM mid-stream cancel verification, FlashAttention 2 Windows install
**Confidence:** HIGH (environment probed directly; all major claims verified from live system or official sources)

---

## Summary

Phase 0 is a **pure measurement spike** — no production code ships, all outputs become Key Decisions written back to `PROJECT.md` / `STATE.md`. It exists because four Resolved Tensions in the project's SUMMARY have quantitative revisit triggers, and the stack commitments in Phases 1–5 can only be frozen after the empirical numbers are in hand.

**Critical discovery from environment audit:** The physical machine running this codebase (`pedro-2023`) has an **RTX 4090 (24 GB VRAM, sm_89 Ada Lovelace)**, not the RTX 3060 (12 GB) described in the requirements. Python 3.13.1 is the system default; Python 3.11.5 and 3.12.10 are installed and available via the `py` launcher. PyTorch 2.5.1+cu121 is already installed under Python 3.11. Tailscale 1.96.3 is active with a `pedro-2023.tailc48d1c.ts.net` hostname that can receive a free Tailscale HTTPS cert — this eliminates mkcert as the required HTTPS strategy. `llama-server` (llama.cpp) and `ollama` are both installed. `flash-attn` 2.8.3 is on PyPI but has no prebuilt wheel for this Python/CUDA combination and builds from source — this is the FA2 install friction the research flagged.

The five Phase 0 questions re-stated in light of the actual environment:

1. **HTTPS on mobile** — Tailscale cert path is simpler than mkcert on this machine; both paths should be documented so the plan can verify either works on the builder's iPhone.
2. **Whisper WER** — `faster-whisper-large-v2` is already cached; distil-large-v3 and large-v3-turbo need to be downloaded. Python 3.11 + torch 2.5.1+cu121 is the target env.
3. **TTS TTFA on actual hardware** — measurements will be on RTX 4090, not RTX 3060. Results will be faster than the Phase 4 budget by a wide margin on this GPU; the 3060 extrapolation logic documented in STACK.md / QWEN3-TTS.md will need to be applied or noted as a future open question.
4. **VRAM soak** — 24 GB on the 4090 means the soak is not about headroom; it is about fragmentation growth, swap correctness, and model-loading behavior.
5. **LLM cancel** — llama-server is installed; cancel probe can be run immediately.

**Primary recommendation:** Run all measurements on the RTX 4090 as the available hardware. Document results, note the 4090 → 3060 extrapolation factor (~2.5×), and record the hardware discrepancy as an open question for the builder to resolve (does a 3060 box exist, or has the GPU been upgraded?). HTTPS strategy: use Tailscale cert first (zero friction), mkcert as the documented fallback.

---

## Architectural Responsibility Map

Phase 0 produces no application tiers — it is a measurement and documentation spike. The table below maps the five empirical questions to the components they inform.

| Measurement | Informs Tier | Downstream Decision |
|---|---|---|
| HTTPS / cert trust on iPhone | Web UI host + LAN networking | Phase 1 HTTPS implementation choice (mkcert vs Tailscale vs Let's Encrypt) |
| Whisper WER on Spanish-accented English | AI Backend — STT | Default STT model frozen before Phase 2 |
| TTS TTFA (F5, XTTS, Qwen3-TTS) | AI Backend — TTS | Default TTS engine frozen; Qwen3-TTS v1 inclusion/exclusion decided |
| VRAM 30-min soak | AI Backend — GPU resident | VRAM coexistence rule verified; swap strategy confirmed |
| LLM mid-stream cancel | AI Backend → LLM endpoint | LLM server choice confirmed; barge-in architecture validated |
| FlashAttention 2 install | AI Backend — Qwen3-TTS only | Qwen3-TTS 1.7B inclusion/exclusion decided |

---

## Standard Stack

### Python Environment for AI Backend

| Package | Version | Purpose | Why Standard |
|---|---|---|---|
| Python | 3.11.5 (via `py -3.11`) | AI backend runtime | Pipecat 1.0 requires 3.11+; PyTorch 2.5.1+cu121 already installed in this env; 3.13 not yet safe for ML dependencies |
| PyTorch | 2.5.1+cu121 (installed) | GPU compute | Already present in Python 3.11 env; CUDA 12.1 runtime matches toolkit 12.8 |
| uv | 0.5.22 (installed) | Venv + dep management | Available at `/c/Users/pmpg/.local/bin/uv`; recommended by coqui-tts README |
| faster-whisper | 1.2.1 (latest, verified PyPI) | STT inference | CTranslate2 backend, 4x faster than openai-whisper; int8_float16 requires Ampere+ (RTX 4090 is Ada = sm_89, supported) |
| f5-tts | 1.1.17 (latest, verified PyPI) | TTS engine #1 | Note: PyPI shows 1.1.17, STACK.md shows 1.1.19 — 1.1.19 may be pulled; use latest available |
| coqui-tts | 0.27.5 (latest, verified PyPI) | TTS engine #2 (XTTS v2) | Idiap fork; only available version is 0.27.5 |
| qwen-tts | 0.1.1 (latest, verified PyPI) | TTS engine #3 (Qwen3-TTS) | No newer version; pin exactly |
| flash-attn | 2.8.3 (latest, verified PyPI) | Qwen3-TTS performance | Builds from source on this machine — FA2 install friction confirmed; RTX 4090 sm_89 is supported by FA2 |
| jiwer | current | WER calculation | Standard Python library for Word Error Rate measurement; not currently installed |
| soundfile | current | Audio I/O for measurement scripts | Standard; not currently installed |

[VERIFIED: PyPI registry via `pip index versions`]

**Version notes (STACK.md vs verified PyPI):**
- `f5-tts`: STACK.md says 1.1.19; PyPI shows 1.1.17 as latest. [VERIFIED: PyPI registry 2026-04-18] — use 1.1.17.
- `faster-whisper`: STACK.md says 1.1+; latest is 1.2.1. [VERIFIED: PyPI registry 2026-04-18]

### HTTPS Strategy Tools

| Tool | Installed | Purpose | Notes |
|---|---|---|---|
| Tailscale | 1.96.3 (installed) | Primary HTTPS strategy | `pedro-2023.tailc48d1c.ts.net` is the node hostname; `tailscale cert <hostname>` issues a real Let's Encrypt cert for the tailnet domain |
| mkcert | NOT installed | Fallback HTTPS strategy | Available via `choco install mkcert`; required if phone is not on the Tailscale tailnet |
| openssl | 3.2.1 (installed, MinGW) | Fallback cert generation | Available but mkcert is the simpler path for CA trust |

[VERIFIED: `command -v mkcert`, `tailscale version`, `openssl version` probed directly]

### LLM Servers

| Server | Installed | Path | Notes |
|---|---|---|---|
| llama-server (llama.cpp) | YES | `/c/Users/pmpg/AppData/Local/Microsoft/WinGet/Packages/ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe/llama-server` | Installed via WinGet; available in PATH |
| ollama | YES | `/c/Users/pmpg/AppData/Local/Programs/Ollama/ollama` | v0.17.0; not running at research time |

[VERIFIED: `command -v llama-server`, `command -v ollama` probed directly]

---

## Architecture Patterns

### System Data Flow for Phase 0 Measurements

```
Measurement Spike (Phase 0)
          │
          ├─── [M1] HTTPS Probe
          │         Browser → https://pedro-2023.tailc48d1c.ts.net
          │         iPhone Safari → window.isSecureContext check
          │
          ├─── [M2] STT WER Measurement
          │         Reference audio (builder's voice) → faster-whisper
          │         Three models: distil-large-v3 INT8, large-v3-turbo INT8, large-v3 FP16
          │         WER via jiwer, latency via time.perf_counter()
          │         nvidia-smi VRAM logged per model
          │
          ├─── [M3] TTS TTFA Measurement
          │         Short text (3–5 words) → each TTS engine
          │         Timestamps: synthesis_start → first_audio_sample_ready
          │         Engines: F5-TTS (7-step Sway), XTTS v2, Qwen3-TTS 0.6B-Base + FA2
          │
          ├─── [M4] 30-Minute VRAM Soak
          │         Per-engine: {Whisper default + Silero + TTS engine}
          │         Cycle: synthesize 10s phrase → transcribe 10s audio → repeat
          │         Log: torch.cuda.memory_reserved() every 60s via nvidia-smi
          │
          ├─── [M5] LLM Cancel Probe
          │         Python script → llama-server streaming request → AbortController
          │         nvidia-smi GPU util logged every 100ms for 2s post-cancel
          │
          └─── [M6] FlashAttention 2 Install
                    py -3.11 -m pip install flash-attn --no-build-isolation
                    Import check: from flash_attn import flash_attn_func
                    Qwen3-TTS 1.7B load test if FA2 succeeds
```

### Recommended Project Structure for Phase 0

```
spikes/
├── 00-https/
│   ├── serve.py               # minimal HTTPS server with tailscale cert
│   └── README.md              # one-time iPhone setup procedure
├── 01-stt-wer/
│   ├── measure_wer.py         # download models, run WER benchmark
│   ├── reference_audio.wav    # 10-min builder voice recording
│   └── reference_transcript.txt
├── 02-tts-ttfa/
│   ├── measure_ttfa.py        # F5, XTTS, Qwen3-TTS first-audio latency
│   └── results.json           # output consumed by KEY_DECISIONS.md
├── 03-vram-soak/
│   ├── soak_test.py           # 30-min cycling soak per engine
│   └── soak_results.json
├── 04-llm-cancel/
│   └── cancel_probe.py        # ~20-line streaming cancel verifier
├── 05-flash-attn/
│   └── verify_fa2.sh          # install + import + Qwen3-TTS 1.7B load
└── KEY_DECISIONS.md           # filled in after all measurements
```

### Pattern 1: WER Measurement Script

```python
# Source: faster-whisper docs + jiwer API
from faster_whisper import WhisperModel
import jiwer, time

def measure_wer(model_size: str, quantization: str, audio_path: str, reference: str):
    model = WhisperModel(model_size, device="cuda", compute_type=quantization)
    t0 = time.perf_counter()
    segments, info = model.transcribe(audio_path, beam_size=5,
                                       condition_on_previous_text=False)
    hypothesis = " ".join(s.text for s in segments)
    elapsed = time.perf_counter() - t0
    wer = jiwer.wer(reference, hypothesis)
    return {"wer": wer, "latency_s": elapsed, "hypothesis": hypothesis}

# Run for three models:
# measure_wer("distil-large-v3", "int8_float16", audio, ref)
# measure_wer("large-v3-turbo",  "int8_float16", audio, ref)
# measure_wer("large-v3",        "float16",      audio, ref)
```
[CITED: https://github.com/SYSTRAN/faster-whisper — API verified from official docs]

### Pattern 2: TTFA Measurement for TTS Engines

```python
# Source: derived from qwen-tts PyPI docs and f5-tts README
import time, numpy as np

def measure_ttfa_f5(ref_audio: str, ref_text: str, target_text: str) -> float:
    from f5_tts.api import F5TTS
    model = F5TTS()
    t0 = time.perf_counter()
    # 7-step Sway sampling for minimum latency
    wav, sr, _ = model.infer(ref_audio, ref_text, target_text, nfe_step=7)
    return time.perf_counter() - t0  # TTFA = full generation for non-streaming F5

def measure_ttfa_xtts(ref_audio: str, target_text: str) -> float:
    from TTS.api import TTS  # using coqui-tts import
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
    t0 = time.perf_counter()
    # XTTS streams; first chunk time is TTFA
    chunks = list(model.tts_with_vc_to_file_streaming(target_text, speaker_wav=ref_audio))
    return time.perf_counter() - t0

def measure_ttfa_qwen(ref_audio: str, ref_text: str, target_text: str) -> float:
    import torch
    from qwen_tts import Qwen3TTSModel
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        device_map="cuda:0", dtype=torch.bfloat16,
        attn_implementation="flash_attention_2"
    )
    prompt = model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text)
    t0 = time.perf_counter()
    wavs, sr = model.generate_voice_clone(text=target_text, voice_clone_prompt=prompt)
    return time.perf_counter() - t0
```
[CITED: https://pypi.org/project/qwen-tts/ — voice_clone API; https://github.com/SWivid/F5-TTS — inference API]

### Pattern 3: LLM Cancel Probe

```python
# Source: Pitfalls.md #8 mitigation pattern
import asyncio, time, httpx

async def probe_llm_cancel(base_url: str, model: str):
    """Verifies that closing the stream actually stops GPU generation."""
    async with httpx.AsyncClient(base_url=base_url) as client:
        # Start generation of a long response
        async with client.stream("POST", "/v1/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": "Write a 500-word essay."}],
            "stream": True, "max_tokens": 500
        }) as response:
            t0 = time.perf_counter()
            async for chunk in response.aiter_bytes():
                if time.perf_counter() - t0 > 0.5:  # cancel after ~500ms
                    break  # closes the stream
            cancel_time = time.perf_counter()

    # After stream close: watch nvidia-smi for 2 seconds
    # GPU util should drop to ~0% within 200ms if cancel propagates
    print(f"Stream closed at {cancel_time - t0:.3f}s. Check nvidia-smi now.")
    await asyncio.sleep(2.0)  # monitor window

asyncio.run(probe_llm_cancel("http://localhost:8080", "<model-name>"))
```
[CITED: PITFALLS.md #8; httpx stream cancellation pattern]

### Pattern 4: VRAM Soak Test

```python
# Source: Pitfalls.md #7 prevention strategy
import torch, time, json

def log_vram(label: str):
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved  = torch.cuda.memory_reserved()  / 1024**3
    print(f"[{label}] allocated={allocated:.2f}GB reserved={reserved:.2f}GB")
    return {"label": label, "allocated_gb": allocated, "reserved_gb": reserved}

# During soak: call log_vram every 60 seconds
# Expected: reserved should plateau, not grow unboundedly
# Warning threshold: reserved > 11 GB on 12 GB device (or > 22 GB here on 4090)
```
[ASSUMED] — specific threshold numbers adapted from STACK.md/PITFALLS.md design rules

### Anti-Patterns to Avoid

- **Running VRAM soak without `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`:** This env var must be set before torch initializes, not after. Set it in the measurement script's `os.environ` before any import of torch. [VERIFIED: PITFALLS.md #7]
- **Measuring TTFA with model cold-loaded:** Always warm the model with one dummy inference before timing. Cold-load includes CUDA kernel compilation which inflates first-run numbers by 2–10×.
- **Using the `openai-whisper` package instead of `faster-whisper`:** `openai-whisper` is 4× slower and lacks the `compute_type` parameter needed for INT8 measurement. [VERIFIED: faster-whisper README]
- **Measuring F5-TTS TTFA at default NFE (32 steps):** The plan targets 7-step Sway sampling. Always set `nfe_step=7` in the measurement. [CITED: STACK.md F5-TTS entry]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| WER calculation | Custom string edit-distance | `jiwer` library | Handles normalization, punctuation, case, multiple references |
| VRAM monitoring | Custom `nvidia-smi` parser | `torch.cuda.memory_allocated()` + `torch.cuda.memory_reserved()` | Direct Python API; no subprocess overhead |
| Audio recording for WER test | Custom mic capture script | Any existing audio recorder; 10-min WAV file produced externally | Phase 0 is a spike; the measurement rig doesn't need to match the production audio pipeline |
| FlashAttention build | Source compile from scratch | `pip install flash-attn --no-build-isolation` | Prebuilt wheels exist for supported configurations; only falls back to source on mismatch |
| Tailscale cert | Manual Let's Encrypt workflow | `tailscale cert <hostname>` | Single command issues a real LE cert; no ACME dance required |

---

## Runtime State Inventory

Phase 0 is a greenfield spike with no rename/refactor component. This section is not applicable.

---

## Common Pitfalls

### Pitfall 1: Hardware Mismatch — RTX 4090 vs Documented RTX 3060

**What goes wrong:** All Phase 0 measurements run on the RTX 4090 (sm_89, 24 GB). The requirements, STACK.md, and QWEN3-TTS.md all assume RTX 3060 (sm_86, 12 GB). If results are recorded without noting the hardware difference, Phase 2 plans may inherit incorrect VRAM budgets and TTFA baselines.

**Why it happens:** The machine `pedro-2023` has an RTX 4090. Either the builder upgraded GPUs after requirements were written, or the 3060 is in a separate box not connected at research time.

**How to avoid:**
- Record all measurements with GPU name, VRAM, and compute capability in the results JSON.
- Apply the ~2.5× RTX 4090 → RTX 3060 slowdown factor when projecting TTFA/RTF results downward.
- Flag in KEY_DECISIONS.md: "Measured on RTX 4090; 3060 extrapolation applied."
- Ask the builder to clarify: is this machine the "AI backend box," or does a 3060 box also exist?

**Warning signs:** Phase 2 plans VRAM budget that assumes 12 GB but deployment box has 24 GB (or vice versa).

### Pitfall 2: FlashAttention 2 Builds From Source (Slow, Potentially Fragile)

**What goes wrong:** `pip install flash-attn` on this machine (Python 3.11, CUDA 12.1, RTX 4090 sm_89) downloads the source tarball (8.4 MB) and attempts compilation. This takes 10–30 minutes and requires a working C++ build chain. If any build dep is missing, the install silently fails with a long compilation log.

**Why it happens:** PyPI has prebuilt wheels for specific `(Python, CUDA, torch)` combinations. Python 3.11 + CUDA 12.1 + sm_89 may not match a prebuilt wheel exactly, triggering a source build.

**How to avoid:**
- Check available prebuilt wheels: `pip install flash-attn==2.8.3 --dry-run` — if it shows "no matching distribution" without downloading source, a prebuilt exists.
- Use `--no-build-isolation` as shown in STACK.md; this reuses the existing torch/numpy environment.
- Set a 30-minute timeout on the install step. If it fails, record "FA2 install: FAILED (source build timed out)" and restrict Qwen3-TTS to 0.6B-Base only per the Phase 0 success criterion #6 fallback.

**Warning signs:** `pip install flash-attn` shows "Building wheel for flash-attn" — this is a source build. Watch for build errors in the gcc/MSVC output.

### Pitfall 3: Tailscale Cert Requires HTTPS Serve on the Tailnet Interface

**What goes wrong:** Tailscale cert is obtained successfully. Builder hits `https://pedro-2023.tailc48d1c.ts.net` from iPhone. iPhone is not on the Tailscale tailnet → connection refused or `NET::ERR_CERT_AUTHORITY_INVALID` (different from a cert trust issue — this is about routing).

**Why it happens:** Tailscale cert covers `*.tailc48d1c.ts.net` — only accessible from devices that are on the tailnet. The builder's iPhone may or may not have Tailscale installed.

**How to avoid:**
- If iPhone has Tailscale installed: bind the test server to `100.100.8.103` (the tailnet IP) — works immediately.
- If iPhone does not have Tailscale: fall back to mkcert path or install Tailscale on iPhone (free; one tap).
- Test `window.isSecureContext` from Safari's JavaScript console as the acceptance gate — this is the definitive check.
- Document both paths (Tailscale and mkcert) in the Phase 0 output for Phase 1 to choose from.

**Warning signs:** `navigator.mediaDevices` is `undefined` in Safari console — this means the context is not secure.

### Pitfall 4: Whisper Distil-Large-V3 Is Not in the HF Cache Yet

**What goes wrong:** The HF cache contains `faster-whisper-large-v2` but not `distil-large-v3` or `large-v3-turbo`. First run triggers a ~1.5 GB download. If the machine is offline or HF is slow, the measurement script stalls.

**Why it happens:** These models haven't been used on this machine before.

**How to avoid:** Pre-download all three models before the measurement session: `faster_whisper.WhisperModel("distil-large-v3", device="cpu")` (the device doesn't matter for the download) will cache them. Do this at the start of Phase 0 before recording any timings.

### Pitfall 5: F5-TTS Latest PyPI Version Discrepancy

**What goes wrong:** STACK.md references f5-tts 1.1.19 but PyPI shows 1.1.17 as the latest at research time. If the install command pins to 1.1.19, `pip install f5-tts==1.1.19` will fail with "no matching distribution."

**Why it happens:** Either 1.1.19 was briefly published and yanked, or the STACK.md was written from a different PyPI state.

**How to avoid:** Use `pip install "f5-tts>=1.1.17"` and record the exact installed version in the results. [VERIFIED: PyPI registry 2026-04-18 — 1.1.17 is latest]

---

## Code Examples

### FlashAttention 2 Install and Verify

```bash
# On Python 3.11 with CUDA 12.1 (the AI backend env)
# First: try to find prebuilt wheel
pip install flash-attn==2.8.3 --dry-run 2>&1 | head -5

# If source build is needed (no prebuilt):
# Ensure MSVC / Visual Studio Build Tools are installed (Windows requirement)
# Then:
FLASH_ATTENTION_SKIP_CUDA_BUILD=FALSE pip install flash-attn --no-build-isolation

# Verify install:
python -c "from flash_attn import flash_attn_func; print('FA2 installed successfully')"
```
[CITED: https://github.com/QwenLM/Qwen3-TTS README; Pitfall research]

### Tailscale HTTPS Server (Minimal)

```python
# Source: Tailscale docs pattern
import ssl, http.server

# Assumes: tailscale cert pedro-2023.tailc48d1c.ts.net already run
# Produces: pedro-2023.tailc48d1c.ts.net.crt + pedro-2023.tailc48d1c.ts.net.key
hostname = "pedro-2023.tailc48d1c.ts.net"
cert_path = f"{hostname}.crt"
key_path  = f"{hostname}.key"

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)

class CheckSecureContext(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        html = b"""
        <script>
          document.body.innerText = 'isSecureContext: ' + window.isSecureContext;
          console.log('mediaDevices defined:', !!navigator.mediaDevices);
        </script>
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html)

with http.server.HTTPServer((hostname, 443), CheckSecureContext) as server:
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print(f"Serving at https://{hostname}")
    server.serve_forever()
```
[ASSUMED] — Tailscale cert mechanism is standard; exact Python ssl binding is training knowledge

### VRAM Soak Script Skeleton

```python
# Source: Pitfalls.md #7 prevention + torch docs
import os, torch, time, json

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

def run_soak(engine_name: str, engine_instance, soak_minutes=30):
    readings = []
    start = time.time()
    cycle = 0
    while time.time() - start < soak_minutes * 60:
        # Simulate realistic inference cycle
        engine_instance.synthesize("This is a test utterance for VRAM soak validation.")
        cycle += 1
        if cycle % 10 == 0:
            torch.cuda.empty_cache()  # optional: mitigate fragmentation
        reading = {
            "time_s": round(time.time() - start),
            "cycle": cycle,
            "allocated_gb": round(torch.cuda.memory_allocated() / 1e9, 2),
            "reserved_gb": round(torch.cuda.memory_reserved() / 1e9, 2),
            "peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
        }
        readings.append(reading)
        print(reading)
        time.sleep(2)
    return readings

# Run once per engine configuration:
# F5 + distil-large-v3 INT8 + Silero
# XTTS v2 + distil-large-v3 INT8 + Silero
# Qwen3-TTS 0.6B + distil-large-v3 INT8 + Silero
# (+ Qwen3-TTS 1.7B if FA2 installed)
```
[ASSUMED] — pattern derived from Pitfalls.md; specific torch API is verified

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Manual mkcert on every device | Tailscale automatic Let's Encrypt cert | Tailscale 1.x (2022+) | Zero-friction HTTPS on LAN for Tailscale users; eliminates the "install Root CA on iPhone" step |
| `openai-whisper` for STT | `faster-whisper` with CTranslate2 INT8 | 2023+ | 4× faster, 50% less VRAM, identical accuracy |
| Full-sentence TTS synthesis | Sentence-boundary streaming TTS | F5 workaround pattern established 2024 | First audio in <500 ms instead of 2–3 s for multi-sentence replies |
| Manual `nvidia-smi` polling | `torch.cuda.memory_allocated()` + `max_memory_allocated()` | PyTorch 2.x | Programmatic VRAM tracking in measurement scripts |
| WER by hand | `jiwer` library | ~2020 | Standard, normalized WER/WIL/MER metrics in one library call |

**Deprecated/outdated:**
- `openai-whisper` package: use `faster-whisper`. The `openai-whisper` on this machine (`openai-whisper 20250625`) is the system Python 3.13 install and should not be used for AI backend work.
- Reliance on `pip install TTS` for XTTS v2: use `coqui-tts` (idiap fork). [VERIFIED: PITFALLS.md #12]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | Tailscale cert binds to the tailnet IP and is trusted by Safari if iPhone has Tailscale installed | Common Pitfalls #3 | If Tailscale cert is not trusted on iOS Safari, mkcert fallback must be used; one extra setup day |
| A2 | The RTX 4090 → RTX 3060 slowdown factor is ~2.5× for autoregressive TTS inference | Summary, Common Pitfalls #1 | If the 3060 box has different drivers/thermals, actual measurements may differ; Phase 0 results would need a hardware note |
| A3 | `tailscale cert` command can be run without elevated privileges on Windows | Code Examples | If cert issuance requires admin, the HTTPS setup procedure gains a step |
| A4 | F5-TTS 1.1.17's inference API (`F5TTS` class, `nfe_step` parameter) matches the pattern shown | Code Examples | API may differ; verify from the installed package's README or source |
| A5 | XTTS v2 streaming via `coqui-tts[server]` works in-process without Docker | Code Examples | Pipecat docs show Docker path as default; in-process may require additional config (STACK.md open question) |
| A6 | `jiwer.wer()` accepts raw string hypothesis and reference without any pre-normalization needed | Code Examples | If jiwer requires normalized text (lowercase, no punctuation), the WER numbers will be inflated until normalization is added |

---

## Open Questions

1. **Does the builder have a separate RTX 3060 box?**
   - What we know: The `pedro-2023` machine has an RTX 4090, 24 GB VRAM. The requirements, STACK.md, and QWEN3-TTS.md all assume a 3060.
   - What's unclear: Whether this is an upgrade (no 3060 exists) or whether the 3060 is a separate "AI backend" machine.
   - Recommendation: Record this as "hardware TBD" in KEY_DECISIONS.md. If only the 4090 exists, the VRAM budgets in STACK.md are far more comfortable than planned, and the Qwen3-TTS 1.7B option becomes viable even without FA2.

2. **Is the builder's iPhone on the Tailscale tailnet?**
   - What we know: `tailscale status` shows `pixel-10-pro` (Android) and `siss-macbook-pro` but no iPhone.
   - What's unclear: Whether the iPhone simply wasn't online at research time, or whether it isn't enrolled.
   - Recommendation: Test both Tailscale path (if iPhone gets enrolled) and mkcert path; document whichever works as the standard procedure.

3. **Is Python 3.13 (system default) acceptable for any measurement scripts?**
   - What we know: Python 3.13.1 is the system default. PyTorch 2.6.0+cu124 is installed in 3.13. Pipecat 1.0 requires 3.11+.
   - What's unclear: Whether F5-TTS, coqui-tts, and qwen-tts install cleanly on 3.13.
   - Recommendation: Use Python 3.11 (via `py -3.11`) for all AI backend measurement scripts. Python 3.13 can serve as the web/tooling environment but should not be the AI inference env for v1.

4. **Does flash-attn build successfully on this machine?**
   - What we know: No prebuilt wheel was found (download started, then source build began). CUDA toolkit 12.8 is installed. The RTX 4090 is Ada Lovelace (sm_89) — FA2 supports sm_80+.
   - What's unclear: Whether the MSVC build toolchain is present and compatible.
   - Recommendation: This is exactly what Phase 0 success criterion #6 measures. Proceed with the build and record the outcome.

5. **What LLM is loaded in llama-server for the cancel probe?**
   - What we know: `llama-server` is installed. No GGUF models were found in the `~/.cache` quick scan (the search timed out).
   - What's unclear: Whether a model is locally available or needs to be downloaded before the cancel probe.
   - Recommendation: Use Ollama with any available model (e.g., `ollama run llama3.2`) for the cancel probe if a GGUF is not at hand; Ollama is installed and the probe verifies cancel semantics, not model quality.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Python 3.11 | AI backend (all measurement scripts) | YES | 3.11.5 (via `py -3.11`) | Python 3.12.10 also available |
| PyTorch + CUDA | All AI inference scripts | YES | 2.5.1+cu121 (Python 3.11 env) | — |
| RTX 4090 (24 GB) | VRAM soak + TTS/STT measurements | YES | sm_89, 24 GB | Hardware docs say 3060 (see Open Q #1) |
| CUDA toolkit 12.8 | FA2 build + torch compilation | YES | 12.8 | — |
| uv | Python venv management | YES | 0.5.22 | pip with venv |
| Tailscale | Primary HTTPS strategy | YES | 1.96.3 | mkcert (choco install mkcert) |
| mkcert | HTTPS fallback | NO | — | `choco install mkcert` |
| llama-server | LLM cancel probe | YES | (WinGet install, version not checked) | ollama (also installed) |
| ollama | LLM cancel probe fallback | YES | 0.17.0 | llama-server |
| faster-whisper | STT WER measurement | NOT installed | — | `pip install faster-whisper==1.2.1` |
| f5-tts | TTS TTFA measurement | NOT installed | — | `pip install f5-tts==1.1.17` |
| coqui-tts | XTTS TTFA measurement | NOT installed | — | `pip install "coqui-tts[server]==0.27.5"` |
| qwen-tts | Qwen3-TTS measurement | NOT installed | — | `pip install qwen-tts==0.1.1` |
| flash-attn | Qwen3-TTS 1.7B + perf | NOT installed | — | Skip (restricts Qwen to 0.6B only) |
| jiwer | WER calculation | NOT installed | — | `pip install jiwer` |
| distil-large-v3 weights | STT WER measurement | NOT cached | — | Auto-downloads on first use (~1.5 GB) |
| large-v3-turbo weights | STT WER measurement | NOT cached | — | Auto-downloads (~0.75 GB) |
| large-v3 FP16 weights | STT WER measurement | NOT cached | — | Auto-downloads (~3 GB) |

**Missing dependencies with no fallback:**
- None. All dependencies have a clear install path or fallback.

**Missing dependencies with install required before measurement:**
- `faster-whisper`, `f5-tts`, `coqui-tts`, `qwen-tts`, `jiwer` — all installable via pip in the Python 3.11 env.
- `flash-attn` — install attempted; outcome is itself a Phase 0 measurement.
- Whisper model weights — auto-download on first use; plan for time and bandwidth.

---

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest + pytest-asyncio (for the LLM cancel probe async script) |
| Config file | None — Wave 0 creates pytest.ini under `spikes/` |
| Quick run command | `py -3.11 -m pytest spikes/ -x -q` |
| Full suite command | `py -3.11 -m pytest spikes/ -v` |

### Phase Requirements → Test Map

Phase 0 delivers no REQ-IDs (spike only). Tests are measurement scripts, not unit tests.

| Spike Item | Behavior | Test Type | Automated? |
|---|---|---|---|
| HTTPS probe | `window.isSecureContext === true` on iPhone Safari | Manual verification + automated server script | Server script automated; iPhone check is manual |
| STT WER | WER, latency, VRAM logged for 3 models | Automated measurement script | YES — `spikes/01-stt-wer/measure_wer.py` |
| TTS TTFA | TTFA (ms) and RTF logged for 3 engines | Automated measurement script | YES — `spikes/02-tts-ttfa/measure_ttfa.py` |
| VRAM soak | Peak VRAM < 11 GB (3060) or no unbounded growth | Automated 30-min script | YES — `spikes/03-vram-soak/soak_test.py` |
| LLM cancel | GPU drops to idle ≤200 ms after stream close | Automated probe + manual nvidia-smi check | Probe automated; GPU check manual |
| FA2 install | `from flash_attn import flash_attn_func` succeeds | Automated install script | YES — `spikes/05-flash-attn/verify_fa2.sh` |

### Wave 0 Gaps

- [ ] `spikes/` directory — does not exist yet; create with the five measurement subdirs
- [ ] `spikes/pytest.ini` — needed only if pytest is used for any automated assertions
- [ ] Python 3.11 venv at `.venv311/` — none exists; Wave 0 creates it

---

## Security Domain

Phase 0 produces no application code, no network endpoints, and no stored secrets. Security domain is not applicable for this spike. No ASVS categories apply.

The one security-adjacent note: the HTTPS probe server (minimal Python HTTPS server with a Tailscale cert) should be run only during the measurement session and terminated immediately after. It should not be left running unattended since it exposes a port on the Tailscale tailnet.

---

## Sources

### Primary (HIGH confidence)

- Live environment probe (2026-04-18) — `nvidia-smi`, `python --version`, `py -3.11 -c "import torch..."`, `tailscale version`, `tailscale status`, `command -v llama-server`, `command -v ollama`, `pip index versions` — all commands run directly against the `pedro-2023` machine
- [PyPI: faster-whisper](https://pypi.org/project/faster-whisper/) — version 1.2.1 verified as latest [VERIFIED]
- [PyPI: f5-tts](https://pypi.org/project/f5-tts/) — version 1.1.17 verified as latest [VERIFIED]
- [PyPI: coqui-tts](https://pypi.org/project/coqui-tts/) — version 0.27.5 [VERIFIED]
- [PyPI: qwen-tts](https://pypi.org/project/qwen-tts/) — version 0.1.1 [VERIFIED]
- [PyPI: flash-attn](https://pypi.org/project/flash-attn/) — version 2.8.3 [VERIFIED]
- [PyPI: pipecat-ai](https://pypi.org/project/pipecat-ai/) — version 1.0.0 [VERIFIED]
- `.planning/research/STACK.md` — technology stack decisions and VRAM budget math
- `.planning/research/PITFALLS.md` — all critical pitfalls for this phase (#2, #4, #5, #6, #7, #8)
- `.planning/research/QWEN3-TTS.md` — full Qwen3-TTS assessment including Phase 0 acceptance gate triggers

### Secondary (MEDIUM confidence)

- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) — `compute_type` parameters, `condition_on_previous_text` flag
- [QwenLM/Qwen3-TTS GitHub](https://github.com/QwenLM/Qwen3-TTS) — voice clone API, FA2 requirement
- [jamiepine/voicebox](https://github.com/jamiepine/voicebox) — voicebox integration patterns for Qwen3-TTS (non-streaming reference)
- [Hacker News: Qwen3-TTS family is now open sourced](https://news.ycombinator.com/item?id=46719229) — FA2 Windows install friction reports, GTX 1080 RTF 2.11 datapoint

### Tertiary (LOW confidence)

- [qwen3-tts.app benchmark article](https://qwen3-tts.app/blog/qwen3-tts-performance-benchmarks-hardware-guide-2026) — RTF numbers for RTX 3060 Ti (closest hardware to 3060 with published data)
- [andimarafioti/faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts) — CUDA graph capture TTFA numbers on RTX 4060 (extrapolation basis)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all package versions verified live from PyPI registry
- Architecture: HIGH — measurement patterns derived from official docs and PITFALLS.md
- Environment: HIGH — probed directly on the target machine
- Hardware accuracy: MEDIUM — 4090 vs 3060 discrepancy unresolved; 3060 may exist as separate box
- TTFA extrapolation for 3060: LOW — derived from indirect benchmarks on adjacent hardware

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (30 days; PyPI package versions are stable; HW environment should not change)
