---
phase: 00-measurement-gate
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/phases/00-measurement-gate/probes/__init__.py
  - .planning/phases/00-measurement-gate/probes/bench_utils.py
  - .planning/phases/00-measurement-gate/probes/conftest.py
  - .planning/phases/00-measurement-gate/probes/test_smoke.py
  - .planning/phases/00-measurement-gate/probes/pytest.ini
  - .planning/phases/00-measurement-gate/results/.gitkeep
  - .planning/phases/00-measurement-gate/.gitignore
  - .planning/phases/00-measurement-gate/requirements-phase0.txt
autonomous: true
requirements: []
user_setup: []

must_haves:
  truths:
    - "Python 3.11.5 venv exists at .venv-phase0/ with torch 2.5.1+cu121 importable"
    - "All Phase 0 AI packages (faster-whisper, f5-tts, coqui-tts, qwen-tts, jiwer, soundfile, librosa, pynvml) are importable under the venv"
    - "Whisper weights (distil-large-v3, large-v3-turbo, large-v3) are cached locally"
    - "probes/bench_utils.py provides VRAM polling, timing helpers, and JSON result writer shared by every probe"
    - "probes/ is a valid pytest package; the smoke test passes confirming venv + CUDA + bench_utils wiring"
  artifacts:
    - path: ".planning/phases/00-measurement-gate/requirements-phase0.txt"
      provides: "Exact pinned package versions for all Phase 0 probes"
      contains: "faster-whisper==1.2.1"
    - path: ".planning/phases/00-measurement-gate/probes/bench_utils.py"
      provides: "Shared measurement primitives — VRAM sampler, monotonic timer, results JSON writer, GPU metadata probe"
      exports: ["sample_vram_mb", "Timer", "write_results", "gpu_info"]
    - path: ".planning/phases/00-measurement-gate/probes/test_smoke.py"
      provides: "End-to-end smoke test verifying venv health"
      contains: "torch.cuda.is_available()"
    - path: ".planning/phases/00-measurement-gate/probes/pytest.ini"
      provides: "pytest config rooted at probes/ so individual probes are discoverable"
      contains: "[pytest]"
    - path: ".planning/phases/00-measurement-gate/.gitignore"
      provides: "Excludes .venv-phase0/, *.wav, HF caches from git"
      contains: ".venv-phase0"
  key_links:
    - from: ".planning/phases/00-measurement-gate/probes/bench_utils.py"
      to: "torch.cuda / pynvml"
      via: "torch.cuda.memory_allocated() + pynvml.nvmlDeviceGetMemoryInfo()"
      pattern: "nvmlDeviceGetMemoryInfo|memory_allocated"
    - from: ".planning/phases/00-measurement-gate/probes/test_smoke.py"
      to: ".planning/phases/00-measurement-gate/probes/bench_utils.py"
      via: "direct import"
      pattern: "from bench_utils import"
---

<objective>
Install Phase 0's measurement environment so every downstream probe can run unattended.

Purpose: The six Phase 0 measurements (HTTPS, Whisper WER, TTS TTFA, VRAM soak, LLM cancel, FA2 install) all require the same Python 3.11 venv, the same AI packages at pinned versions, the same Whisper model weights, and the same benchmarking primitives (VRAM polling, timing, JSON writer, GPU metadata). Installing and wiring these once here avoids N × duplication and N × version-drift bugs across downstream plans.

Output: A runnable `.venv-phase0/` venv; `requirements-phase0.txt` pinning every package; three Whisper checkpoints cached in `%USERPROFILE%/.cache/huggingface/hub/`; a `probes/` package with `bench_utils.py`, `pytest.ini`, and a passing smoke test; a `results/` directory ready to receive JSON output from each subsequent plan.
</objective>

<execution_context>
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/workflows/execute-plan.md
@D:/Pedro/Repos/Program/RayMe/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/00-measurement-gate/00-RESEARCH.md
@.planning/phases/00-measurement-gate/00-VALIDATION.md
@.planning/research/STACK.md
@.planning/research/PITFALLS.md
@.planning/research/QWEN3-TTS.md

<interfaces>
Key facts the executor must use (already verified in 00-RESEARCH.md):

- Python 3.11.5 is the target runtime, invoked on Windows via `py -3.11`. Do NOT use Python 3.12 or 3.13.
- PyTorch 2.5.1+cu121 is already installed under the system Python 3.11. The venv should inherit it via `--system-site-packages` OR reinstall the exact same torch build inside the venv. Prefer reinstall for isolation (slower but reproducible).
- Pinned package versions (all verified from PyPI on 2026-04-18):
    faster-whisper==1.2.1
    f5-tts==1.1.17          # STACK.md mentioned 1.1.19 but PyPI latest is 1.1.17 per research Pitfall #5
    coqui-tts[server]==0.27.5
    qwen-tts==0.1.1          # pin exactly; 0.2.x may break
    jiwer (latest on PyPI)
    soundfile (latest)
    librosa (latest)
    pynvml (latest)
    httpx>=0.27              # needed by plan 06 (LLM cancel)
    pytest>=7.0
    pytest-asyncio>=0.23
- flash-attn is EXCLUDED from this plan's install. Plan 07 owns the FA2 install as its own measurement.
- Whisper model identifiers for faster-whisper:
    "distil-large-v3"       (~1.5 GB)
    "large-v3-turbo"        (~0.75 GB)
    "large-v3"              (~3 GB)
- GPU is RTX 4090 (sm_89, 24 GB) per 00-RESEARCH.md §Summary. Record this metadata in every results JSON.
- Set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` in bench_utils.py BEFORE importing torch, per PITFALLS.md #7.

Expected bench_utils.py public API (downstream probes will import these):

```python
# .planning/phases/00-measurement-gate/probes/bench_utils.py

def gpu_info() -> dict:
    """Returns {name, vram_total_mb, compute_capability, driver_version, cuda_version}.
    Used as the metadata stamp on every results JSON."""

def sample_vram_mb() -> dict:
    """Returns {allocated_mb, reserved_mb, used_mb_nvml, peak_allocated_mb}.
    allocated_mb / reserved_mb from torch.cuda; used_mb_nvml from pynvml
    (captures fragmentation + other processes)."""

class Timer:
    """Monotonic timer. Use as:
        with Timer() as t:
            do_work()
        t.elapsed_ms  # float milliseconds
    """

def write_results(path: str, payload: dict) -> None:
    """Writes payload as pretty JSON to path. Adds 'meta' key with
    timestamp, gpu_info(), python_version, torch_version if not present.
    Creates parent dir if missing."""

def warmup_cuda() -> None:
    """One tiny tensor op to trigger CUDA context creation and kernel
    compilation. Call before any TTFA/RTF measurement."""
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create probes/ package + requirements-phase0.txt + .gitignore</name>
  <files>
    .planning/phases/00-measurement-gate/probes/__init__.py
    .planning/phases/00-measurement-gate/probes/pytest.ini
    .planning/phases/00-measurement-gate/probes/conftest.py
    .planning/phases/00-measurement-gate/requirements-phase0.txt
    .planning/phases/00-measurement-gate/results/.gitkeep
    .planning/phases/00-measurement-gate/.gitignore
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/00-RESEARCH.md (Standard Stack table and Environment Availability table — for exact pinned versions)
    .planning/phases/00-measurement-gate/00-VALIDATION.md (probes/ layout and pytest config)
    .planning/research/PITFALLS.md (Pitfalls #7 and #12 for env config rationale)
  </read_first>
  <action>
    Create the probe package skeleton.

    1. `.planning/phases/00-measurement-gate/probes/__init__.py` — empty file (marks probes/ as a Python package so pytest can import bench_utils).

    2. `.planning/phases/00-measurement-gate/probes/pytest.ini` — minimal pytest config:
       ```
       [pytest]
       testpaths = .
       asyncio_mode = auto
       addopts = -ra -q --tb=short
       ```

    3. `.planning/phases/00-measurement-gate/probes/conftest.py` — sets the CUDA alloc config env var before torch is imported anywhere:
       ```python
       import os
       os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
       os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
       ```

    4. `.planning/phases/00-measurement-gate/requirements-phase0.txt` — pin every package referenced by any Phase 0 plan (flash-attn excluded; plan 07 installs it separately):
       ```
       # Phase 0 measurement gate — pinned dependencies
       # Install into .venv-phase0/ created with: py -3.11 -m venv .venv-phase0
       # Then: .venv-phase0\Scripts\pip install -r requirements-phase0.txt
       # (On Windows: .venv-phase0\Scripts\activate)

       # Torch MUST already be present at 2.5.1+cu121. If not, run:
       #   pip install torch==2.5.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
       # This file assumes torch is pre-installed (system site-packages or explicit install).

       faster-whisper==1.2.1
       f5-tts==1.1.17
       coqui-tts[server]==0.27.5
       qwen-tts==0.1.1
       jiwer>=3.0
       soundfile>=0.12
       librosa>=0.10
       pynvml>=11.5
       httpx>=0.27
       pytest>=7.0
       pytest-asyncio>=0.23
       ```

    5. `.planning/phases/00-measurement-gate/results/.gitkeep` — empty file so the directory exists in git even before any probe runs.

    6. `.planning/phases/00-measurement-gate/.gitignore` — exclude artifacts that must never be committed:
       ```
       # Venv and model caches
       .venv-phase0/
       __pycache__/
       *.pyc

       # Audio samples (voice PII) and recorded WAVs — see threat_model
       *.wav
       *.mp3
       *.flac
       !probes/fixtures/silence_for_tests.wav   # allow the 1-second silence asset only

       # HTTPS artifacts never committed
       *.key
       *.pem
       *.crt
       *.p12
       iphone-cert.mobileconfig

       # Raw nvidia-smi logs (verbose; summaries in results/*.json are the artifact)
       *.smi.log
       ```

    Commit these files; do not yet install anything.
  </action>
  <verify>
    <automated>test -f .planning/phases/00-measurement-gate/probes/__init__.py &amp;&amp; test -f .planning/phases/00-measurement-gate/probes/pytest.ini &amp;&amp; test -f .planning/phases/00-measurement-gate/probes/conftest.py &amp;&amp; test -f .planning/phases/00-measurement-gate/requirements-phase0.txt &amp;&amp; test -f .planning/phases/00-measurement-gate/results/.gitkeep &amp;&amp; test -f .planning/phases/00-measurement-gate/.gitignore &amp;&amp; grep -q "faster-whisper==1.2.1" .planning/phases/00-measurement-gate/requirements-phase0.txt &amp;&amp; grep -q "qwen-tts==0.1.1" .planning/phases/00-measurement-gate/requirements-phase0.txt &amp;&amp; grep -q "asyncio_mode = auto" .planning/phases/00-measurement-gate/probes/pytest.ini &amp;&amp; grep -q "expandable_segments:True" .planning/phases/00-measurement-gate/probes/conftest.py</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/probes/__init__.py` exists.
    - File `.planning/phases/00-measurement-gate/probes/pytest.ini` exists and contains `asyncio_mode = auto`.
    - File `.planning/phases/00-measurement-gate/probes/conftest.py` contains the string `PYTORCH_CUDA_ALLOC_CONF` and `expandable_segments:True`.
    - File `.planning/phases/00-measurement-gate/requirements-phase0.txt` exists and contains exact lines `faster-whisper==1.2.1`, `f5-tts==1.1.17`, `coqui-tts[server]==0.27.5`, `qwen-tts==0.1.1`.
    - File `.planning/phases/00-measurement-gate/results/.gitkeep` exists (empty).
    - File `.planning/phases/00-measurement-gate/.gitignore` contains `.venv-phase0/` and `*.wav` entries.
  </acceptance_criteria>
  <done>Probe package skeleton and pinned requirements committed to the repo.</done>
</task>

<task type="auto">
  <name>Task 2: Create .venv-phase0, install packages, pre-download Whisper weights</name>
  <files>
    .planning/phases/00-measurement-gate/.venv-phase0/  (directory, excluded from git)
    .planning/phases/00-measurement-gate/results/setup_install.json
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/requirements-phase0.txt
    .planning/phases/00-measurement-gate/00-RESEARCH.md (Open Questions #3 — why Python 3.11 not 3.13; Pitfall #4 — why pre-download Whisper weights)
    .planning/research/PITFALLS.md (Pitfall #7 — PYTORCH_CUDA_ALLOC_CONF rationale)
  </read_first>
  <action>
    From `.planning/phases/00-measurement-gate/`:

    1. Create venv:
       ```bash
       py -3.11 -m venv .venv-phase0
       ```
       Confirm `py -3.11 --version` outputs `Python 3.11.5`. If it reports a different 3.11.x, proceed but record the actual version in setup_install.json.

    2. Upgrade pip inside the venv (Windows paths):
       ```bash
       .venv-phase0/Scripts/python.exe -m pip install --upgrade pip setuptools wheel
       ```

    3. Confirm torch is reachable. Run:
       ```bash
       .venv-phase0/Scripts/python.exe -c "import sys; print(sys.version); import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)"
       ```
       Expected: `Python 3.11.5 ...`, `2.5.1+cu121 True 12.1`.

       If torch is NOT found inside the venv (because `python -m venv` does NOT inherit system site-packages by default), install the exact matching build into the venv:
       ```bash
       .venv-phase0/Scripts/python.exe -m pip install torch==2.5.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
       ```
       Record in setup_install.json whether torch came from system site-packages or was freshly installed.

    4. Install all pinned Phase 0 packages:
       ```bash
       .venv-phase0/Scripts/python.exe -m pip install -r requirements-phase0.txt
       ```
       If coqui-tts[server] or f5-tts fails install, capture the full stderr and record in setup_install.json under `install_errors` — do NOT abort the task; downstream plans 03/04 will surface the real blocker and the orchestrator may route to a repair plan.

    5. Verify every package imports cleanly (smoke check, not the pytest smoke test):
       ```bash
       .venv-phase0/Scripts/python.exe -c "import torch, faster_whisper, TTS, qwen_tts, jiwer, soundfile, librosa, pynvml, httpx; print('all imports OK')"
       ```
       Note: coqui-tts imports as `TTS`, not `coqui_tts`. f5-tts imports as `f5_tts`. Try `import f5_tts` and record outcome.

    6. Pre-download Whisper model weights (avoids in-probe stalls per Pitfall #4). Run from within the venv:
       ```bash
       .venv-phase0/Scripts/python.exe -c "
       from faster_whisper import WhisperModel
       for m in ('distil-large-v3', 'large-v3-turbo', 'large-v3'):
           print(f'Downloading {m}...')
           _ = WhisperModel(m, device='cpu', compute_type='int8')  # device cpu avoids touching GPU during download
           print(f'  cached: {m}')
       "
       ```
       This triggers the HF downloader and caches to the user HF hub cache. Expect ~5 GB total download. On slow network this is 5–15 min; run attended.

    7. Write a final setup summary to `.planning/phases/00-measurement-gate/results/setup_install.json`:
       ```json
       {
         "meta": {
           "timestamp": "<ISO8601>",
           "python_version": "3.11.x",
           "gpu": "<from nvidia-smi>",
           "cuda_version": "12.1",
           "torch_version": "2.5.1+cu121"
         },
         "venv_path": ".venv-phase0",
         "torch_origin": "system_site_packages" | "reinstalled_in_venv",
         "installed_versions": {
           "faster-whisper": "1.2.1",
           "f5-tts": "1.1.17",
           "coqui-tts": "0.27.5",
           "qwen-tts": "0.1.1",
           "jiwer": "<resolved>",
           "soundfile": "<resolved>",
           "librosa": "<resolved>",
           "pynvml": "<resolved>",
           "httpx": "<resolved>"
         },
         "import_check_passed": true | false,
         "import_errors": [],
         "whisper_weights_cached": ["distil-large-v3", "large-v3-turbo", "large-v3"],
         "install_errors": []
       }
       ```
  </action>
  <verify>
    <automated>test -f .planning/phases/00-measurement-gate/results/setup_install.json &amp;&amp; .planning/phases/00-measurement-gate/.venv-phase0/Scripts/python.exe -c "import torch; assert torch.cuda.is_available(); import faster_whisper, jiwer, pynvml, httpx; print('OK')" &amp;&amp; grep -q "\"import_check_passed\": true" .planning/phases/00-measurement-gate/results/setup_install.json</automated>
  </verify>
  <acceptance_criteria>
    - Directory `.planning/phases/00-measurement-gate/.venv-phase0/` exists and contains `Scripts/python.exe`.
    - Command `.venv-phase0/Scripts/python.exe --version` outputs `Python 3.11.x`.
    - Command `.venv-phase0/Scripts/python.exe -c "import torch; print(torch.cuda.is_available())"` outputs `True`.
    - Command `.venv-phase0/Scripts/python.exe -c "import faster_whisper, jiwer, pynvml, httpx"` exits 0.
    - File `results/setup_install.json` exists, has valid JSON, includes keys `meta`, `installed_versions`, `whisper_weights_cached`, `import_check_passed`.
    - `results/setup_install.json` has `import_check_passed: true`.
    - HuggingFace cache contains directories matching `models--Systran--faster-distil-whisper-large-v3`, `models--Systran--faster-whisper-large-v3-turbo`, `models--Systran--faster-whisper-large-v3` (exact names from faster-whisper's HF repo scheme).
  </acceptance_criteria>
  <done>Venv is populated with all Phase 0 dependencies; Whisper weights are locally cached; setup_install.json documents the environment for downstream plans to reference.</done>
</task>

<task type="auto">
  <name>Task 3: Write bench_utils.py + smoke test + verify pytest green</name>
  <files>
    .planning/phases/00-measurement-gate/probes/bench_utils.py
    .planning/phases/00-measurement-gate/probes/test_smoke.py
  </files>
  <read_first>
    .planning/phases/00-measurement-gate/probes/conftest.py  (to know env vars are already set)
    .planning/phases/00-measurement-gate/00-RESEARCH.md (§Code Examples for VRAM soak skeleton — exact torch API pattern)
    .planning/phases/00-measurement-gate/results/setup_install.json (to confirm gpu name + torch version for meta stamp)
    .planning/research/PITFALLS.md (Pitfall #7 warm-up rationale — cold CUDA inflates TTFA)
  </read_first>
  <action>
    1. Create `.planning/phases/00-measurement-gate/probes/bench_utils.py` with the exact public API declared in the `<interfaces>` block above. Implementation requirements:

       ```python
       """Shared measurement primitives for Phase 0 probes.

       Every probe (whisper_bench, tts_ttfa, vram_soak, llm_cancel, fa2_check)
       imports from this module so timing, VRAM sampling, and results-JSON
       schema are consistent.
       """
       from __future__ import annotations
       import json
       import os
       import platform
       import subprocess
       import sys
       import time
       from dataclasses import dataclass
       from datetime import datetime, timezone
       from pathlib import Path
       from typing import Any

       # conftest.py has already set PYTORCH_CUDA_ALLOC_CONF before this module is imported.

       def _utcnow_iso() -> str:
           return datetime.now(timezone.utc).isoformat(timespec="seconds")

       def gpu_info() -> dict[str, Any]:
           """Returns GPU metadata stamped into every results JSON.

           Uses torch.cuda for canonical fields and nvidia-smi for the
           human-readable GPU name + driver version (torch doesn't expose those).
           """
           import torch
           if not torch.cuda.is_available():
               return {"cuda_available": False}
           idx = 0
           props = torch.cuda.get_device_properties(idx)
           result = {
               "cuda_available": True,
               "name": torch.cuda.get_device_name(idx),
               "vram_total_mb": props.total_memory // (1024 * 1024),
               "compute_capability": f"{props.major}.{props.minor}",
               "cuda_version": torch.version.cuda,
               "torch_version": torch.__version__,
           }
           # Best-effort driver version via nvidia-smi
           try:
               out = subprocess.check_output(
                   ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                   text=True, timeout=5,
               ).strip().splitlines()[0]
               result["driver_version"] = out
           except Exception:
               result["driver_version"] = "unknown"
           return result

       def sample_vram_mb() -> dict[str, float]:
           """Returns VRAM sample in MB. Used by vram_soak and every probe
           that reports peak VRAM in its results JSON.

           - allocated_mb / reserved_mb / peak_allocated_mb come from torch
             (only counts this process's allocations).
           - used_mb_nvml comes from NVML (counts ALL processes + fragmentation).
           """
           import torch
           result = {
               "allocated_mb": round(torch.cuda.memory_allocated() / (1024 * 1024), 2),
               "reserved_mb": round(torch.cuda.memory_reserved() / (1024 * 1024), 2),
               "peak_allocated_mb": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2),
           }
           try:
               import pynvml
               pynvml.nvmlInit()
               try:
                   h = pynvml.nvmlDeviceGetHandleByIndex(0)
                   info = pynvml.nvmlDeviceGetMemoryInfo(h)
                   result["used_mb_nvml"] = round(info.used / (1024 * 1024), 2)
                   result["free_mb_nvml"] = round(info.free / (1024 * 1024), 2)
               finally:
                   pynvml.nvmlShutdown()
           except Exception as e:
               result["used_mb_nvml"] = None
               result["nvml_error"] = str(e)
           return result

       @dataclass
       class Timer:
           """Context manager around time.perf_counter().
           Use: `with Timer() as t: ...; t.elapsed_ms`"""
           _start: float = 0.0
           _end: float = 0.0
           def __enter__(self) -> "Timer":
               self._start = time.perf_counter()
               return self
           def __exit__(self, *exc) -> None:
               self._end = time.perf_counter()
           @property
           def elapsed_s(self) -> float:
               return self._end - self._start
           @property
           def elapsed_ms(self) -> float:
               return (self._end - self._start) * 1000.0

       def warmup_cuda() -> None:
           """Trigger CUDA context creation + a few kernel compilations.
           Call BEFORE any TTFA/latency measurement to avoid cold-load inflation.
           """
           import torch
           if not torch.cuda.is_available():
               return
           x = torch.randn(64, 64, device="cuda")
           for _ in range(3):
               y = x @ x
           torch.cuda.synchronize()
           del x, y

       def write_results(path: str | Path, payload: dict[str, Any]) -> None:
           """Writes payload to path as pretty JSON. Adds meta stamp if absent.
           Creates parent dirs.
           """
           p = Path(path)
           p.parent.mkdir(parents=True, exist_ok=True)
           if "meta" not in payload:
               payload = {
                   "meta": {
                       "timestamp": _utcnow_iso(),
                       "python_version": platform.python_version(),
                       "platform": platform.platform(),
                       "gpu": gpu_info(),
                   },
                   **payload,
               }
           p.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
       ```

    2. Create `.planning/phases/00-measurement-gate/probes/test_smoke.py`:

       ```python
       """Wave-1 smoke test: confirms venv + CUDA + bench_utils wiring.

       Run with:
         .venv-phase0/Scripts/python.exe -m pytest .planning/phases/00-measurement-gate/probes/test_smoke.py -v
       """
       from pathlib import Path

       import pytest

       from bench_utils import Timer, gpu_info, sample_vram_mb, warmup_cuda, write_results


       def test_gpu_info_returns_cuda_available():
           info = gpu_info()
           assert info["cuda_available"] is True, f"CUDA not available: {info}"
           assert info["vram_total_mb"] >= 8000, f"Unexpected GPU VRAM: {info}"
           assert info["compute_capability"].startswith("8."), (
               f"Expected Ampere or Ada GPU, got {info}"
           )

       def test_vram_sample_keys_present():
           import torch
           torch.cuda.empty_cache()
           s = sample_vram_mb()
           for k in ("allocated_mb", "reserved_mb", "peak_allocated_mb"):
               assert k in s
           # nvml_error is acceptable; used_mb_nvml may be None if nvml import failed
           assert "used_mb_nvml" in s

       def test_timer_measures_elapsed():
           import time
           with Timer() as t:
               time.sleep(0.05)
           assert 40 <= t.elapsed_ms <= 200, f"timer elapsed_ms off: {t.elapsed_ms}"

       def test_warmup_cuda_runs_without_error():
           warmup_cuda()  # no assertion; just must not raise

       def test_write_results_creates_file(tmp_path: Path):
           out = tmp_path / "smoke_result.json"
           write_results(out, {"probe": "smoke", "value": 42})
           import json
           data = json.loads(out.read_text())
           assert data["probe"] == "smoke"
           assert data["value"] == 42
           assert "meta" in data and "gpu" in data["meta"]
       ```

    3. Run the smoke test from the venv:
       ```bash
       cd .planning/phases/00-measurement-gate/probes
       ../.venv-phase0/Scripts/python.exe -m pytest test_smoke.py -v
       ```
       Must exit 0 with 5 passing tests. If any fail, diagnose before committing (common cause: smoke test cannot import bench_utils — confirm you ran pytest from inside the probes/ directory so pytest's rootdir discovers bench_utils.py as a local module).

    4. Commit both files.
  </action>
  <verify>
    <automated>cd .planning/phases/00-measurement-gate/probes &amp;&amp; ../.venv-phase0/Scripts/python.exe -m pytest test_smoke.py -v 2&gt;&amp;1 | tee /tmp/smoke.out &amp;&amp; grep -q "5 passed" /tmp/smoke.out</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-measurement-gate/probes/bench_utils.py` exists and exports all four symbols: `gpu_info`, `sample_vram_mb`, `Timer`, `warmup_cuda`, `write_results` (verify with `grep -E "^def (gpu_info|sample_vram_mb|warmup_cuda|write_results)" probes/bench_utils.py` returns 4 lines, plus `class Timer`).
    - File `.planning/phases/00-measurement-gate/probes/test_smoke.py` exists with 5 `def test_*` functions.
    - Running `.venv-phase0/Scripts/python.exe -m pytest .planning/phases/00-measurement-gate/probes/test_smoke.py -v` from the repo root exits 0 and output contains `5 passed`.
    - `test_gpu_info_returns_cuda_available` confirms CUDA is reachable from the venv.
  </acceptance_criteria>
  <done>bench_utils.py API is live and tested; downstream plans can `from bench_utils import ...` without further setup.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| None (internal) | All Phase 0 setup is local — venv creation, package install, model weight download. No network endpoints exposed. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-01-01 | Tampering | requirements-phase0.txt | accept | Pinned versions verified against PyPI 2026-04-18 in 00-RESEARCH.md; any tampering would be caught by downstream import failures. No supply-chain hash pinning at this spike stage. |
| T-00-01-02 | Info Disclosure | HF cache (.venv-phase0 + user HF hub) | accept | Contains model weights only, no PII. `.gitignore` excludes `.venv-phase0/` so nothing enters the repo. |
| T-00-01-03 | Info Disclosure | `*.wav` voice samples (future probes) | mitigate | `.gitignore` excludes `*.wav`/`*.mp3`/`*.flac` by default; downstream plans document retention + deletion. |
| T-00-01-04 | Denial of Service | Disk space during HF download | accept | ~5 GB one-time download; user has a 4090 workstation with ample space. Download can be re-run if interrupted. |

No high-severity threats. This plan creates no network endpoints, no credentials, no user-facing services.
</threat_model>

<verification>
Run after all three tasks complete:

```bash
# From repo root
cd .planning/phases/00-measurement-gate/probes
../.venv-phase0/Scripts/python.exe -m pytest test_smoke.py -v
# Expect: 5 passed

# Confirm whisper weights cached
../.venv-phase0/Scripts/python.exe -c "
from faster_whisper import WhisperModel
for m in ('distil-large-v3', 'large-v3-turbo', 'large-v3'):
    # Load-only check (no transcribe)
    model = WhisperModel(m, device='cuda', compute_type='int8_float16')
    print(f'{m}: OK')
    del model
"
# Expect: three 'OK' lines, no HF downloads triggered (already cached)
```
</verification>

<success_criteria>
- [ ] `.venv-phase0/` venv runs Python 3.11 with torch 2.5.1+cu121 + all Phase 0 packages importable
- [ ] Three Whisper checkpoints are HF-cached locally
- [ ] `probes/bench_utils.py` exports the declared API (Timer, gpu_info, sample_vram_mb, warmup_cuda, write_results)
- [ ] `probes/test_smoke.py` passes 5/5 tests inside the venv
- [ ] `results/setup_install.json` documents resolved versions and import-check status
- [ ] No artifact in `.venv-phase0/`, no `*.wav`, and no HF cache dir is staged for git
</success_criteria>

<output>
After completion, create `.planning/phases/00-measurement-gate/00-01-SUMMARY.md` summarizing:
- Resolved package versions (from `results/setup_install.json`)
- HF cache location and total size of Whisper weights
- bench_utils.py public API reference (one line per symbol)
- Any install failures or surprises that downstream plans must accommodate
</output>
