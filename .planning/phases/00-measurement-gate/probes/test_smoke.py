"""Wave 1 smoke test for the Phase 0 backend environment."""

from __future__ import annotations

import json
import time
from pathlib import Path

from bench_utils import Timer, gpu_info, sample_vram_mb, warmup_cuda, write_results


def test_gpu_info_returns_cuda_available() -> None:
    info = gpu_info()
    assert info["cuda_available"] is True, f"CUDA not available: {info}"
    assert info["vram_total_mb"] >= 8000, f"Unexpected GPU VRAM: {info}"
    assert info["compute_capability"].startswith("8."), (
        f"Expected Ampere-class GPU, got {info}"
    )


def test_vram_sample_keys_present() -> None:
    import torch

    torch.cuda.empty_cache()
    sample = sample_vram_mb()
    for key in ("allocated_mb", "reserved_mb", "peak_allocated_mb"):
        assert key in sample
    assert "used_mb_nvml" in sample


def test_timer_measures_elapsed() -> None:
    with Timer() as timer:
        time.sleep(0.05)
    assert 40 <= timer.elapsed_ms <= 200, f"timer elapsed_ms off: {timer.elapsed_ms}"


def test_warmup_cuda_runs_without_error() -> None:
    warmup_cuda()


def test_write_results_creates_file(tmp_path: Path) -> None:
    output = tmp_path / "smoke_result.json"
    write_results(output, {"probe": "smoke", "value": 42})
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["probe"] == "smoke"
    assert data["value"] == 42
    assert "meta" in data and "gpu" in data["meta"]
