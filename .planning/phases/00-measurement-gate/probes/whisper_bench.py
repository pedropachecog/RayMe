"""Whisper WER + latency + VRAM benchmark for Phase 0 success criterion #2."""

from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any

from bench_utils import Timer, sample_vram_mb, warmup_cuda, write_results

RUNGS: list[tuple[str, str]] = [
    ("distil-large-v3", "int8_float16"),
    ("large-v3-turbo", "int8_float16"),
    ("large-v3", "float16"),
]

DISTIL_WITHIN_PP = 0.02
TURBO_WITHIN_PP = 0.02


class NvmlPeakMonitor:
    """Track GPU memory used via NVML while CTranslate2 runs outside Torch."""

    def __init__(self, interval_s: float = 0.05) -> None:
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak_used_mb: float | None = None
        self._error: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            try:
                while not self._stop.is_set():
                    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    used_mb = info.used / (1024 * 1024)
                    if self._peak_used_mb is None or used_mb > self._peak_used_mb:
                        self._peak_used_mb = used_mb
                    time.sleep(self.interval_s)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                used_mb = info.used / (1024 * 1024)
                if self._peak_used_mb is None or used_mb > self._peak_used_mb:
                    self._peak_used_mb = used_mb
            finally:
                pynvml.nvmlShutdown()
        except Exception as exc:
            self._error = repr(exc)

    def stop(self) -> tuple[float | None, str | None]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        return self._peak_used_mb, self._error


def _normalize_transform() -> Any:
    from jiwer import (
        Compose,
        ReduceToListOfListOfWords,
        RemoveMultipleSpaces,
        RemovePunctuation,
        Strip,
        ToLowerCase,
    )

    return Compose(
        [
            ToLowerCase(),
            RemovePunctuation(),
            RemoveMultipleSpaces(),
            Strip(),
            ReduceToListOfListOfWords(),
        ]
    )


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute normalized word error rate."""
    import jiwer

    transform = _normalize_transform()
    return float(
        jiwer.wer(
            reference,
            hypothesis,
            reference_transform=transform,
            hypothesis_transform=transform,
        )
    )


def pick_default(rungs: list[dict[str, Any]]) -> str | None:
    """Pick the default rung per Resolved Tension #2."""
    measured = [rung for rung in rungs if rung.get("wer") is not None]
    if not measured:
        return None

    best_wer = min(rung["wer"] for rung in measured)
    by_name = {rung["model"]: rung for rung in measured}

    distil = by_name.get("distil-large-v3")
    turbo = by_name.get("large-v3-turbo")

    if distil and distil["wer"] - best_wer <= DISTIL_WITHIN_PP + 1e-9:
        return "distil-large-v3"
    if turbo and turbo["wer"] - best_wer <= TURBO_WITHIN_PP + 1e-9:
        return "large-v3-turbo"
    return min(measured, key=lambda rung: rung["wer"])["model"]


def build_result(
    rungs: list[dict[str, Any]], default_rung: str | None = None
) -> dict[str, Any]:
    """Build the persisted results payload and mark exactly one default when possible."""
    chosen = default_rung or pick_default(rungs)
    result_rungs: list[dict[str, Any]] = []

    for rung in rungs:
        entry = dict(rung)
        entry["default"] = entry.get("model") == chosen
        result_rungs.append(entry)

    return {
        "probe": "whisper_bench",
        "rungs": result_rungs,
        "default_rung": chosen,
    }


def measure_rung(
    model_name: str,
    compute_type: str,
    audio_path: str,
    reference: str,
    trials: int = 3,
) -> dict[str, Any]:
    """Load a Whisper rung, run timed trials, and return metrics."""
    import torch
    from faster_whisper import WhisperModel

    print(f"[bench] Loading {model_name} ({compute_type})...", flush=True)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    baseline_used_mb = sample_vram_mb().get("used_mb_nvml")
    monitor = NvmlPeakMonitor()
    monitor.start()
    model: Any | None = None
    latencies: list[float] = []
    torch_vram_peaks: list[float] = []
    hypothesis = ""

    try:
        model = WhisperModel(model_name, device="cuda", compute_type=compute_type)
        warmup_cuda()

        for index in range(trials):
            torch.cuda.reset_peak_memory_stats()
            with Timer() as timer:
                segments, _info = model.transcribe(
                    audio_path,
                    beam_size=5,
                    condition_on_previous_text=False,
                    vad_filter=False,
                    language="en",
                )
                parts = [segment.text.strip() for segment in segments]
            latencies.append(timer.elapsed_ms)
            torch_vram_peaks.append(sample_vram_mb()["peak_allocated_mb"])
            if index == 0:
                hypothesis = " ".join(part for part in parts if part)
            print(
                f"[bench]   trial {index + 1}/{trials}: {timer.elapsed_ms:.0f} ms",
                flush=True,
            )
    finally:
        peak_used_mb, monitor_error = monitor.stop()

    if model is not None:
        del model
    torch.cuda.empty_cache()

    p95_latency = (
        max(latencies)
        if len(latencies) < 20
        else statistics.quantiles(latencies, n=20, method="inclusive")[-1]
    )

    if peak_used_mb is not None and baseline_used_mb is not None:
        peak_vram_mb = max(0.0, peak_used_mb - baseline_used_mb)
    else:
        peak_vram_mb = max(torch_vram_peaks)

    return {
        "model": model_name,
        "compute_type": compute_type,
        "wer": round(compute_wer(reference, hypothesis), 4),
        "p50_latency_ms": round(statistics.median(latencies), 1),
        "p95_latency_ms": round(p95_latency, 1),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "hypothesis": hypothesis[:4000],
        "trials": trials,
        "peak_vram_source": "nvml_delta_mb" if peak_used_mb is not None and baseline_used_mb is not None else "torch_peak_allocated_mb",
        "baseline_used_mb_nvml": round(baseline_used_mb, 1) if baseline_used_mb is not None else None,
        "peak_used_mb_nvml": round(peak_used_mb, 1) if peak_used_mb is not None else None,
        "nvml_monitor_error": monitor_error,
    }


def _read_reference(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, help="Path to the reference WAV")
    parser.add_argument("--reference", required=True, help="Path to the reference transcript")
    parser.add_argument("--output", required=True, help="Path to write results JSON")
    parser.add_argument("--trials", type=int, default=3, help="Trials per model rung")
    args = parser.parse_args()

    audio = Path(args.audio)
    reference_path = Path(args.reference)
    if not audio.exists():
        print(f"ERROR: audio file not found: {audio}", file=sys.stderr)
        print("Builder must record probes/fixtures/reference_audio.wav first.", file=sys.stderr)
        return 2
    if not reference_path.exists():
        print(f"ERROR: reference transcript not found: {reference_path}", file=sys.stderr)
        return 2

    reference = _read_reference(reference_path)
    rung_metrics: list[dict[str, Any]] = []

    for model_name, compute_type in RUNGS:
        try:
            metrics = measure_rung(model_name, compute_type, str(audio), reference, args.trials)
        except Exception as exc:
            print(
                f"[bench] FAILED {model_name} ({compute_type}): {exc!r}",
                file=sys.stderr,
            )
            metrics = {
                "model": model_name,
                "compute_type": compute_type,
                "wer": None,
                "p50_latency_ms": None,
                "p95_latency_ms": None,
                "peak_vram_mb": None,
                "hypothesis": "",
                "trials": 0,
                "error": repr(exc),
            }
        rung_metrics.append(metrics)

    payload = build_result(rung_metrics)
    write_results(args.output, payload)
    print(f"[bench] Default rung: {payload['default_rung']}", flush=True)
    print(f"[bench] Wrote {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
