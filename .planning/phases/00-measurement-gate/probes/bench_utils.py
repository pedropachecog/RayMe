"""Shared measurement primitives for Phase 0 probes."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# These must be set before any torch import in direct script usage.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

__all__ = [
    "Timer",
    "gpu_info",
    "sample_vram_mb",
    "warmup_cuda",
    "write_results",
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _driver_version() -> str:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            text=True,
            timeout=5,
        )
    except Exception:
        return "unknown"
    return output.strip().splitlines()[0]


def gpu_info() -> dict[str, Any]:
    """Return GPU metadata stamped into every results JSON."""
    import torch

    if not torch.cuda.is_available():
        return {"cuda_available": False}

    props = torch.cuda.get_device_properties(0)
    return {
        "cuda_available": True,
        "name": torch.cuda.get_device_name(0),
        "vram_total_mb": props.total_memory // (1024 * 1024),
        "compute_capability": f"{props.major}.{props.minor}",
        "driver_version": _driver_version(),
        "cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
    }


def sample_vram_mb() -> dict[str, Any]:
    """Return current process and NVML VRAM readings in MB."""
    import torch

    if not torch.cuda.is_available():
        return {
            "allocated_mb": 0.0,
            "reserved_mb": 0.0,
            "peak_allocated_mb": 0.0,
            "used_mb_nvml": None,
            "free_mb_nvml": None,
            "cuda_available": False,
        }

    result: dict[str, Any] = {
        "allocated_mb": round(torch.cuda.memory_allocated() / (1024 * 1024), 2),
        "reserved_mb": round(torch.cuda.memory_reserved() / (1024 * 1024), 2),
        "peak_allocated_mb": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2),
        "cuda_available": True,
    }

    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            result["used_mb_nvml"] = round(info.used / (1024 * 1024), 2)
            result["free_mb_nvml"] = round(info.free / (1024 * 1024), 2)
        finally:
            pynvml.nvmlShutdown()
    except Exception as exc:
        result["used_mb_nvml"] = None
        result["free_mb_nvml"] = None
        result["nvml_error"] = str(exc)

    return result


@dataclass
class Timer:
    """Context manager around time.perf_counter()."""

    _start: float = 0.0
    _end: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self._end = time.perf_counter()

    @property
    def elapsed_s(self) -> float:
        return self._end - self._start

    @property
    def elapsed_ms(self) -> float:
        return (self._end - self._start) * 1000.0


def warmup_cuda() -> None:
    """Create a warm CUDA context before any latency-sensitive probe."""
    import torch

    if not torch.cuda.is_available():
        return

    x = torch.randn(64, 64, device="cuda")
    y = x
    for _ in range(3):
        y = y @ x
    torch.cuda.synchronize()
    del x
    del y


def write_results(path: str | Path, payload: dict[str, Any]) -> None:
    """Write a pretty JSON artifact with standard metadata."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    meta = dict(payload.get("meta", {}))
    meta.setdefault("timestamp", _utcnow_iso())
    meta.setdefault("python_version", platform.python_version())
    meta.setdefault("platform", platform.platform())
    meta.setdefault("gpu", gpu_info())

    document = dict(payload)
    document["meta"] = meta
    target.write_text(json.dumps(document, indent=2), encoding="utf-8")
