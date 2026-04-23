"""Cross-runtime TTS runtime matrix harness for Phase 0."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHORT_TEXT = "Hey, got it."
NO_EFFECT_TTFA_MS = 25.0
NO_EFFECT_RTF = 0.05
SSH_BOOTSTRAP = Path("scripts/bootstrap-rayme-ssh.sh")
SPIKE_DIR = Path(".planning/spikes/002-f5-triton-trtllm-wsl-path")
PHASE_DIR = Path(".planning/phases/00-measurement-gate")
RESULT_PATH = PHASE_DIR / "results" / "tts_runtime_matrix.json"
WINDOWS_RESULTS_DIR = PHASE_DIR / "results"
WINDOWS_SHORT_COMPARISON = (
    SPIKE_DIR / "results" / "f5_short_ttfa_comparison.json"
)
WSL_VENV = "/home/pmpg/rayme/.venv-cu121"
WSL_PROBE_ROOT = "/home/pmpg/rayme/phase0-probes"
WSL_RESULTS_DIR = f"{WSL_PROBE_ROOT}/results/runtime-matrix"
WSL_FIXTURE_ROOT = f"{WSL_PROBE_ROOT}/fixtures"
WSL_TRITON_FIXTURE_ROOT = "/home/pmpg/rayme/f5-triton-runtime/phase0-fixtures"
WIN_PROBE_ROOT_WSL = "/mnt/c/Users/rayme-ssh.OMEN-PC/phase0-probes"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_local(
    command: list[str] | str,
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def bootstrap_ssh(alias: str, user: str) -> None:
    env = os.environ.copy()
    env["RAYME_SSH_ALIAS"] = alias
    env["RAYME_SSH_USER"] = user
    subprocess.run(
        [str(SSH_BOOTSTRAP), "restore"],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )


def ssh_windows(command: str) -> str:
    proc = run_local(["ssh", "rayme-ssh", command])
    return proc.stdout


def ssh_wsl(script: str) -> str:
    proc = run_local(
        ["ssh", "rayme-pmpg", "wsl", "-d", "Ubuntu", "--cd", "/home/pmpg", "-e", "bash", "-s"],
        input_text=script,
    )
    return proc.stdout


def read_wsl_json(path: str) -> dict[str, Any]:
    stdout = ssh_wsl(
        f"set -euo pipefail\ncat {shlex.quote(path)}\n"
    )
    return json.loads(stdout)


def wsl_exists(path: str) -> bool:
    try:
        ssh_wsl(f"set -euo pipefail\ntest -f {shlex.quote(path)}\n")
    except subprocess.CalledProcessError:
        return False
    return True


def write_results(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def diff_status(
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> str:
    if not baseline or not candidate:
        return "measured"
    baseline_ttfa = baseline.get("ttfa_ms")
    candidate_ttfa = candidate.get("ttfa_ms")
    baseline_rtf = baseline.get("rtf")
    candidate_rtf = candidate.get("rtf")
    if None in (baseline_ttfa, candidate_ttfa, baseline_rtf, candidate_rtf):
        return "measured"
    if (
        abs(float(candidate_ttfa) - float(baseline_ttfa)) <= NO_EFFECT_TTFA_MS
        and abs(float(candidate_rtf) - float(baseline_rtf)) <= NO_EFFECT_RTF
    ):
        return "no_effect_observed"
    return "measured"


def build_row(
    *,
    engine: str,
    runtime: str,
    host_account: str,
    scenario: str,
    backend: str,
    source: str,
    metrics: dict[str, Any] | None = None,
    status: str = "measured",
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = metrics or {}
    row = {
        "engine": engine,
        "runtime": runtime,
        "host_account": host_account,
        "scenario": scenario,
        "backend": backend,
        "status": status,
        "ttfa_ms": metrics.get("ttfa_ms"),
        "rtf": metrics.get("rtf"),
        "peak_vram_mb": metrics.get("peak_vram_mb"),
        "audio_duration_s": metrics.get("audio_duration_s"),
        "sample_rate": metrics.get("sample_rate"),
        "mode": metrics.get("mode"),
        "streaming_support": metrics.get("streaming_support"),
        "true_streaming": metrics.get("true_streaming"),
        "source": source,
    }
    if reason:
        row["reason"] = reason
    for key in (
        "ack_ttfa_ms",
        "dead_air_after_ack_ms",
        "hidden_by_ack_playback_ms",
        "transport",
        "notes",
        "fallback_to_non_streaming",
    ):
        if key in metrics and metrics[key] is not None:
            row[key] = metrics[key]
    if extra:
        row.update(extra)
    return row


def choose_fastest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    measured = [
        row
        for row in rows
        if row.get("status") in {"measured", "no_effect_observed"}
        and row.get("ttfa_ms") is not None
        and row.get("rtf") is not None
    ]
    if not measured:
        return None
    return min(measured, key=lambda row: (row["ttfa_ms"], row["rtf"]))


def choose_xtts_runtime(
    baseline: dict[str, Any],
    deepspeed: dict[str, Any],
) -> tuple[str, str]:
    if deepspeed.get("status") == "not_available":
        return (
            "wsl_python_baseline",
            f"DeepSpeed unavailable: {deepspeed.get('reason', 'unknown reason')}",
        )
    if deepspeed.get("status") == "no_effect_observed":
        return ("wsl_python_baseline", "DeepSpeed ran but did not materially change TTFA/RTF.")
    winner = choose_fastest([baseline, deepspeed]) or baseline
    if winner is deepspeed:
        return ("wsl_python_deepspeed", "DeepSpeed produced the faster XTTS path.")
    return ("wsl_python_baseline", "Baseline XTTS remains the faster or safer path.")


def choose_qwen_backend(
    eager: dict[str, Any],
    fa2: dict[str, Any],
) -> tuple[str, str]:
    if fa2.get("status") == "not_available":
        return ("eager", f"FlashAttention 2 unavailable: {fa2.get('reason', 'unknown reason')}")
    if fa2.get("status") == "no_effect_observed":
        return ("eager", "FlashAttention 2 ran but did not materially change TTFA/RTF.")
    winner = choose_fastest([eager, fa2]) or eager
    if winner is fa2:
        return ("flash_attention_2", "FlashAttention 2 produced the faster Qwen path.")
    return ("eager", "The eager baseline remains the faster or safer Qwen path.")


def stage_shared_fixtures() -> None:
    run_local([str(SPIKE_DIR / "sync-phase0-fixtures.sh")])
    ssh_wsl(
        f"""set -euo pipefail
mkdir -p {shlex.quote(WSL_FIXTURE_ROOT)} {shlex.quote(WSL_RESULTS_DIR)} {shlex.quote(WSL_TRITON_FIXTURE_ROOT)}
cp {WIN_PROBE_ROOT_WSL}/fixtures/short_ref_audio.wav {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_audio.wav
cp {WIN_PROBE_ROOT_WSL}/fixtures/short_ref_transcript.txt {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_transcript.txt
cp {WIN_PROBE_ROOT_WSL}/fixtures/target_text_1min.txt {shlex.quote(WSL_FIXTURE_ROOT)}/target_text_1min.txt
cp {WIN_PROBE_ROOT_WSL}/fixtures/target_text_1min.txt {shlex.quote(WSL_TRITON_FIXTURE_ROOT)}/target_text_1min.txt
"""
    )


def triton_ready() -> bool:
    try:
        ssh_wsl("set -euo pipefail\ncurl -sf http://127.0.0.1:18000/v2/health/ready >/dev/null\n")
    except subprocess.CalledProcessError:
        return False
    return True


def ensure_triton_server() -> None:
    if triton_ready():
        return
    run_local([str(SPIKE_DIR / "launch-runtime-server.sh")])


def benchmark_wsl_f5_short() -> dict[str, Any]:
    output = f"{WSL_RESULTS_DIR}/f5_wsl_python_short.json"
    if wsl_exists(output):
        return read_wsl_json(output)
    sample = f"{WSL_RESULTS_DIR}/f5_wsl_python_short.wav"
    ssh_wsl(
        f"""set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
python {WIN_PROBE_ROOT_WSL}/tts_ttfa.py \\
  --run-engine f5 \\
  --ref-audio {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_audio.wav \\
  --ref-text {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_transcript.txt \\
  --target-text {shlex.quote(SHORT_TEXT)} \\
  --sample-out {shlex.quote(sample)} \\
  --engine-output {shlex.quote(output)}
"""
    )
    return read_wsl_json(output)


def benchmark_wsl_f5_long() -> dict[str, Any]:
    output = f"{WSL_RESULTS_DIR}/f5_wsl_python_longform.json"
    if wsl_exists(output):
        return read_wsl_json(output)
    combined = f"{WSL_RESULTS_DIR}/f5_wsl_python_longform.wav"
    ssh_wsl(
        f"""set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
python {WIN_PROBE_ROOT_WSL}/f5_production_chunking.py \\
  --ref-audio {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_audio.wav \\
  --ref-text {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_transcript.txt \\
  --target-text-file {shlex.quote(WSL_FIXTURE_ROOT)}/target_text_1min.txt \\
  --speed 1.5 \\
  --output {shlex.quote(output)} \\
  --combined-out {shlex.quote(combined)}
"""
    )
    return read_wsl_json(output)


def benchmark_wsl_xtts_baseline() -> dict[str, Any]:
    output = f"{WSL_RESULTS_DIR}/xtts_wsl_baseline.json"
    if wsl_exists(output):
        return read_wsl_json(output)
    sample = f"{WSL_RESULTS_DIR}/xtts_wsl_baseline.wav"
    ssh_wsl(
        f"""set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
export COQUI_TOS_AGREED=1
python {WIN_PROBE_ROOT_WSL}/tts_ttfa.py \\
  --run-engine xtts \\
  --ref-audio {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_audio.wav \\
  --ref-text {shlex.quote(WSL_FIXTURE_ROOT)}/short_ref_transcript.txt \\
  --target-text {shlex.quote(SHORT_TEXT)} \\
  --sample-out {shlex.quote(sample)} \\
  --engine-output {shlex.quote(output)}
"""
    )
    return read_wsl_json(output)


def benchmark_wsl_xtts_deepspeed() -> dict[str, Any]:
    output = f"{WSL_RESULTS_DIR}/xtts_wsl_deepspeed.json"
    if wsl_exists(output):
        return read_wsl_json(output)
    ssh_wsl(
        f"""set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
export COQUI_TOS_AGREED=1
python - <<'PY'
import json
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from TTS.api import TTS
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

sys.path.insert(0, "{WIN_PROBE_ROOT_WSL}")
from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results
from tts_ttfa import _maybe_cuda_sync, compute_rtf

ref_audio = Path("{WSL_FIXTURE_ROOT}/short_ref_audio.wav")
target_text = {SHORT_TEXT!r}
output = Path("{output}")
sample_out = output.with_suffix(".wav")
local_appdata = Path.home() / "AppData" / "Local"
roaming_appdata = Path.home() / "AppData" / "Roaming"
tts_home = local_appdata / "rayme-tts-home"
os.environ.setdefault("LOCALAPPDATA", str(local_appdata))
os.environ.setdefault("APPDATA", str(roaming_appdata))
os.environ.setdefault("XDG_DATA_HOME", str(local_appdata))
os.environ.setdefault("TTS_HOME", str(tts_home))
tts_home.mkdir(parents=True, exist_ok=True)
model_dir = tts_home / "tts" / "tts_models--multilingual--multi-dataset--xtts_v2"

try:
    if not (model_dir / "config.json").exists():
        bootstrap = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
        del bootstrap
        torch.cuda.empty_cache()

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    config = XttsConfig()
    config.load_json(model_dir / "config.json")
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=str(model_dir), eval=True, use_deepspeed=True)
    warmup_cuda()

    chunks = []
    first_chunk_s = None
    with Timer() as timer:
        started = torch.cuda.Event(enable_timing=True)
        finished = torch.cuda.Event(enable_timing=True)
        started.record()
        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(audio_path=str(ref_audio))
        for chunk in model.inference_stream(
            text=target_text,
            language="en",
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
        ):
            if first_chunk_s is None:
                finished.record()
                torch.cuda.synchronize()
                first_chunk_s = started.elapsed_time(finished) / 1000.0
            if isinstance(chunk, torch.Tensor):
                chunk = chunk.detach().cpu().numpy()
            chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
        _maybe_cuda_sync(torch)

    wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    sample_rate = 24000
    audio_duration_s = len(wav) / sample_rate
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, wav, sample_rate)
    payload = {{
        "engine": "xtts",
        "mode": "streaming",
        "streaming_support": "native",
        "true_streaming": True,
        "backend": "deepspeed",
        "ttfa_ms": round((first_chunk_s or timer.elapsed_s) * 1000, 1),
        "rtf": round(compute_rtf(audio_duration_s, timer.elapsed_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(timer.elapsed_s, 3),
        "peak_vram_mb": round(sample_vram_mb()["peak_allocated_mb"], 1),
        "sample_rate": sample_rate,
        "output_wav": str(sample_out),
    }}
except Exception as exc:
    payload = {{
        "engine": "xtts",
        "backend": "deepspeed",
        "status": "not_available",
        "ttfa_ms": None,
        "rtf": None,
        "peak_vram_mb": None,
        "reason": f"{{type(exc).__name__}}: {{exc}}",
        "traceback": traceback.format_exc(limit=12),
    }}

write_results(output, payload)
PY
"""
    )
    return read_wsl_json(output)


def benchmark_wsl_qwen(attn_implementation: str) -> dict[str, Any]:
    slug = "fa2" if attn_implementation == "flash_attention_2" else "eager"
    output = f"{WSL_RESULTS_DIR}/qwen_wsl_{slug}.json"
    if wsl_exists(output):
        return read_wsl_json(output)
    ssh_wsl(
        f"""set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
python - <<'PY'
import traceback
from pathlib import Path
import sys

import soundfile as sf
import torch

sys.path.insert(0, "{WIN_PROBE_ROOT_WSL}")
from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results
from tts_ttfa import _maybe_cuda_sync, _read_reference_text, compute_rtf
from qwen_tts import Qwen3TTSModel

output = Path("{output}")
sample_out = output.with_suffix(".wav")
ref_audio = Path("{WSL_FIXTURE_ROOT}/short_ref_audio.wav")
ref_text = _read_reference_text(Path("{WSL_FIXTURE_ROOT}/short_ref_transcript.txt"))
target_text = {SHORT_TEXT!r}
backend = {attn_implementation!r}

try:
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        device_map="cuda:0",
        torch_dtype=torch.bfloat16,
        attn_implementation=backend,
    )
    warmup_cuda()
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(ref_audio),
        ref_text=ref_text,
        x_vector_only_mode=False,
    )
    _ = model.generate_voice_clone(
        text="Warm.",
        voice_clone_prompt=prompt,
        language="English",
        non_streaming_mode=False,
    )
    _maybe_cuda_sync(torch)
    with Timer() as timer:
        wavs, sample_rate = model.generate_voice_clone(
            text=target_text,
            voice_clone_prompt=prompt,
            language="English",
            non_streaming_mode=False,
        )
        _maybe_cuda_sync(torch)
    wav = wavs[0] if hasattr(wavs, "__len__") and len(wavs) > 0 else wavs
    if hasattr(wav, "detach"):
        wav = wav.detach().cpu().numpy()
    sample = wav.astype("float32").flatten()
    audio_duration_s = len(sample) / float(sample_rate)
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, sample, int(sample_rate))
    payload = {{
        "engine": "qwen3",
        "mode": "simulated_streaming_text",
        "streaming_support": "simulated",
        "true_streaming": False,
        "backend": backend,
        "ttfa_ms": round(timer.elapsed_s * 1000, 1),
        "rtf": round(compute_rtf(audio_duration_s, timer.elapsed_s), 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(timer.elapsed_s, 3),
        "peak_vram_mb": round(sample_vram_mb()["peak_allocated_mb"], 1),
        "sample_rate": int(sample_rate),
        "output_wav": str(sample_out),
    }}
except Exception as exc:
    payload = {{
        "engine": "qwen3",
        "backend": backend,
        "status": "not_available",
        "ttfa_ms": None,
        "rtf": None,
        "peak_vram_mb": None,
        "reason": f"{{type(exc).__name__}}: {{exc}}",
        "traceback": traceback.format_exc(limit=12),
    }}

write_results(output, payload)
PY
"""
    )
    return read_wsl_json(output)


def benchmark_wsl_triton(scenario: str) -> dict[str, Any]:
    target_path = (
        f"{WSL_TRITON_FIXTURE_ROOT}/target_text_1min.txt"
        if scenario == "longform"
        else None
    )
    target_text_expr = SHORT_TEXT if target_path is None else None
    output = f"{WSL_RESULTS_DIR}/f5_wsl_triton_{scenario}.json"
    if wsl_exists(output):
        return read_wsl_json(output)
    ssh_wsl(
        f"""set -euo pipefail
source {shlex.quote(WSL_VENV)}/bin/activate
python - <<'PY'
import json
import subprocess
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

output = Path("{output}")
ref_audio = Path("{WSL_TRITON_FIXTURE_ROOT}/short_ref_audio.wav")
ref_text = Path("{WSL_TRITON_FIXTURE_ROOT}/short_ref_transcript.txt").read_text(encoding="utf-8").strip()
target_text = {target_text_expr!r}
target_path = {target_path!r}
if target_path:
    target_text = " ".join(Path(target_path).read_text(encoding="utf-8").split())

def sample_used_mb() -> float | None:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        return float(raw.strip().splitlines()[0])
    except Exception:
        return None

try:
    waveform, sample_rate = sf.read(ref_audio)
    waveform = np.asarray(waveform, dtype=np.float32)
    payload = {{
        "inputs": [
            {{
                "name": "reference_wav",
                "shape": [1, len(waveform)],
                "datatype": "FP32",
                "data": waveform.reshape(1, -1).tolist(),
            }},
            {{
                "name": "reference_wav_len",
                "shape": [1, 1],
                "datatype": "INT32",
                "data": [[len(waveform)]],
            }},
            {{
                "name": "reference_text",
                "shape": [1, 1],
                "datatype": "BYTES",
                "data": [[ref_text]],
            }},
            {{
                "name": "target_text",
                "shape": [1, 1],
                "datatype": "BYTES",
                "data": [[target_text]],
            }},
        ]
    }}
    max_used = [0.0]
    stop = False

    def poll() -> None:
        while not stop:
            used = sample_used_mb()
            if used is not None:
                max_used[0] = max(max_used[0], used)
            time.sleep(0.2)

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    started = time.perf_counter()
    response = requests.post(
        "http://127.0.0.1:18000/v2/models/f5_tts/infer",
        headers={{"Content-Type": "application/json"}},
        json=payload,
        params={{"request_id": "{scenario}"}},
        timeout=600,
    )
    elapsed_s = time.perf_counter() - started
    stop = True
    thread.join(timeout=2.0)
    response.raise_for_status()
    body = response.json()
    audio = np.asarray(body["outputs"][0]["data"], dtype=np.float32)
    audio_duration_s = audio.shape[0] / 24000.0
    sample_out = output.with_suffix(".wav")
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(sample_out, audio, 24000, "PCM_16")
    payload = {{
        "engine": "f5",
        "mode": "http_unary_triton",
        "transport": "http",
        "streaming_support": "remote_unary",
        "true_streaming": False,
        "ttfa_ms": round(elapsed_s * 1000, 1),
        "rtf": round(elapsed_s / audio_duration_s, 3),
        "audio_duration_s": round(audio_duration_s, 3),
        "synthesis_time_s": round(elapsed_s, 3),
        "peak_vram_mb": round(max_used[0], 1) if max_used[0] else None,
        "sample_rate": 24000,
        "output_wav": str(sample_out),
    }}
except Exception as exc:
    payload = {{
        "engine": "f5",
        "backend": "triton_tensorrt_llm",
        "status": "not_available",
        "ttfa_ms": None,
        "rtf": None,
        "peak_vram_mb": None,
        "reason": f"{{type(exc).__name__}}: {{exc}}",
        "traceback": traceback.format_exc(limit=12),
    }}

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
"""
    )
    return read_wsl_json(output)


def build_matrix_rows(
    windows_short: dict[str, Any],
    windows_long: dict[str, Any],
    wsl_f5_short: dict[str, Any],
    wsl_f5_long: dict[str, Any],
    wsl_triton_short: dict[str, Any],
    wsl_triton_long: dict[str, Any],
    xtts_baseline: dict[str, Any],
    xtts_deepspeed: dict[str, Any],
    qwen_eager: dict[str, Any],
    qwen_fa2: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [
        build_row(
            engine="f5",
            runtime="windows_native",
            host_account="rayme-ssh",
            scenario="short_ack",
            backend="not_applicable",
            source=str(WINDOWS_SHORT_COMPARISON),
            metrics={
                "ttfa_ms": windows_short["fresh_native_summary"]["median_ttfa_ms"],
                "rtf": windows_short["fresh_native_summary"]["median_rtf"],
                "peak_vram_mb": windows_short["phase0_native_baseline"]["peak_vram_mb"],
                "mode": windows_short["phase0_native_baseline"]["mode"],
                "streaming_support": windows_short["phase0_native_baseline"]["streaming_support"],
                "true_streaming": windows_short["phase0_native_baseline"]["true_streaming"],
            },
        ),
        build_row(
            engine="f5",
            runtime="windows_native",
            host_account="rayme-ssh",
            scenario="longform",
            backend="not_applicable",
            source=str(WINDOWS_RESULTS_DIR / "f5_production_chunked_speed15.json"),
            metrics={
                "ttfa_ms": windows_long["ack_ttfa_ms"],
                "rtf": windows_long["remainder_rtf"],
                "peak_vram_mb": windows_long["peak_vram_mb"],
                "audio_duration_s": windows_long["combined_audio_duration_s"],
                "mode": windows_long["mode"],
                "ack_ttfa_ms": windows_long["ack_ttfa_ms"],
                "dead_air_after_ack_ms": windows_long["dead_air_after_ack_ms"],
                "hidden_by_ack_playback_ms": windows_long["hidden_by_ack_playback_ms"],
            },
        ),
        build_row(
            engine="f5",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="not_applicable",
            source=f"{WSL_RESULTS_DIR}/f5_wsl_python_short.json",
            metrics=wsl_f5_short,
        ),
        build_row(
            engine="f5",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="longform",
            backend="not_applicable",
            source=f"{WSL_RESULTS_DIR}/f5_wsl_python_longform.json",
            metrics={
                "ttfa_ms": wsl_f5_long.get("ack_ttfa_ms"),
                "rtf": wsl_f5_long.get("remainder_rtf"),
                "peak_vram_mb": wsl_f5_long.get("peak_vram_mb"),
                "audio_duration_s": wsl_f5_long.get("combined_audio_duration_s"),
                "mode": wsl_f5_long.get("mode"),
                "ack_ttfa_ms": wsl_f5_long.get("ack_ttfa_ms"),
                "dead_air_after_ack_ms": wsl_f5_long.get("dead_air_after_ack_ms"),
                "hidden_by_ack_playback_ms": wsl_f5_long.get("hidden_by_ack_playback_ms"),
            },
        ),
        build_row(
            engine="f5",
            runtime="wsl_triton",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="triton_tensorrt_llm",
            source=f"{WSL_RESULTS_DIR}/f5_wsl_triton_short_ack.json",
            metrics=wsl_triton_short,
            status=wsl_triton_short.get("status", "measured"),
            reason=wsl_triton_short.get("reason"),
        ),
        build_row(
            engine="f5",
            runtime="wsl_triton",
            host_account="rayme-pmpg",
            scenario="longform",
            backend="triton_tensorrt_llm",
            source=f"{WSL_RESULTS_DIR}/f5_wsl_triton_longform.json",
            metrics=wsl_triton_long,
            status=wsl_triton_long.get("status", "measured"),
            reason=wsl_triton_long.get("reason"),
        ),
    ]

    rows.append(
        build_row(
            engine="xtts",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="baseline",
            source=f"{WSL_RESULTS_DIR}/xtts_wsl_baseline.json",
            metrics=xtts_baseline,
        )
    )

    xtts_status = xtts_deepspeed.get("status", "measured")
    if xtts_status != "not_available":
        xtts_status = diff_status(xtts_baseline, xtts_deepspeed)
    rows.append(
        build_row(
            engine="xtts",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="deepspeed",
            source=f"{WSL_RESULTS_DIR}/xtts_wsl_deepspeed.json",
            metrics=xtts_deepspeed,
            status=xtts_status,
            reason=xtts_deepspeed.get("reason"),
        )
    )

    rows.append(
        build_row(
            engine="qwen3",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="eager",
            source=f"{WSL_RESULTS_DIR}/qwen_wsl_eager.json",
            metrics=qwen_eager,
            status=qwen_eager.get("status", "measured"),
            reason=qwen_eager.get("reason"),
        )
    )
    qwen_status = qwen_fa2.get("status", "measured")
    if qwen_status != "not_available":
        qwen_status = diff_status(qwen_eager, qwen_fa2)
    rows.append(
        build_row(
            engine="qwen3",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="flash_attention_2",
            source=f"{WSL_RESULTS_DIR}/qwen_wsl_fa2.json",
            metrics=qwen_fa2,
            status=qwen_status,
            reason=qwen_fa2.get("reason"),
        )
    )
    return rows


def build_recommendations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    f5_short_rows = [row for row in rows if row["engine"] == "f5" and row["scenario"] == "short_ack"]
    f5_long_rows = [row for row in rows if row["engine"] == "f5" and row["scenario"] == "longform"]
    xtts_rows = [row for row in rows if row["engine"] == "xtts"]
    qwen_rows = [row for row in rows if row["engine"] == "qwen3"]

    f5_short = choose_fastest(f5_short_rows)
    f5_long = choose_fastest(f5_long_rows)
    xtts_baseline = next(row for row in xtts_rows if row["backend"] == "baseline")
    xtts_deepspeed = next(row for row in xtts_rows if row["backend"] == "deepspeed")
    qwen_eager = next(row for row in qwen_rows if row["backend"] == "eager")
    qwen_fa2 = next(row for row in qwen_rows if row["backend"] == "flash_attention_2")
    xtts_runtime, xtts_reason = choose_xtts_runtime(xtts_baseline, xtts_deepspeed)
    qwen_backend, qwen_reason = choose_qwen_backend(qwen_eager, qwen_fa2)

    return {
        "f5_short_ack_winner": f5_short["runtime"] if f5_short else "pending",
        "f5_short_ack_reason": (
            f"{f5_short['runtime']} led short TTFA at {f5_short['ttfa_ms']} ms."
            if f5_short
            else "No measured short-response F5 rows."
        ),
        "f5_longform_winner": f5_long["runtime"] if f5_long else "pending",
        "f5_longform_reason": (
            f"{f5_long['runtime']} led long-form TTFA at {f5_long['ttfa_ms']} ms."
            if f5_long
            else "No measured long-form F5 rows."
        ),
        "xtts_recommended_runtime": xtts_runtime,
        "xtts_reason": xtts_reason,
        "qwen_recommended_backend": qwen_backend,
        "qwen_reason": qwen_reason,
    }


def run_matrix(output: Path) -> dict[str, Any]:
    bootstrap_ssh("rayme-ssh", "rayme-ssh")
    bootstrap_ssh("rayme-pmpg", "pmpg")
    stage_shared_fixtures()
    ensure_triton_server()

    windows_short = read_json(WINDOWS_SHORT_COMPARISON)
    windows_long = read_json(WINDOWS_RESULTS_DIR / "f5_production_chunked_speed15.json")
    wsl_f5_short = benchmark_wsl_f5_short()
    wsl_f5_long = benchmark_wsl_f5_long()
    wsl_triton_short = benchmark_wsl_triton("short_ack")
    wsl_triton_long = benchmark_wsl_triton("longform")
    xtts_baseline = benchmark_wsl_xtts_baseline()
    xtts_deepspeed = benchmark_wsl_xtts_deepspeed()
    qwen_eager = benchmark_wsl_qwen("eager")
    qwen_fa2 = benchmark_wsl_qwen("flash_attention_2")

    rows = build_matrix_rows(
        windows_short,
        windows_long,
        wsl_f5_short,
        wsl_f5_long,
        wsl_triton_short,
        wsl_triton_long,
        xtts_baseline,
        xtts_deepspeed,
        qwen_eager,
        qwen_fa2,
    )
    payload = {
        "probe": "tts_runtime_matrix",
        "generated_at": utc_now(),
        "rows": rows,
        "recommendations": build_recommendations(rows),
    }
    write_results(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(RESULT_PATH))
    args = parser.parse_args()
    payload = run_matrix(Path(args.output))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
