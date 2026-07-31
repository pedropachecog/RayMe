#!/usr/bin/env python3
"""Measure Faster Qwen3-TTS CUDA voice-clone streaming on OMEN.

This probe is deliberately standalone. It runs in an isolated environment and
does not import or mutate RayMe's deployed AI backend.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import random
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf
import torch

from faster_qwen3_tts import FasterQwen3TTS


TEXTS = {
    "short": "Hey, I am right here with you.",
    "medium": (
        "I know the last voice started clearly and then slowly became muffled. "
        "This test checks whether the same voice stays steady from beginning to end."
    ),
    "long": (
        "A live conversation should remain clear even after many turns. The voice must not "
        "fade into a whisper, lose its consonants, become metallic, or collapse into noise. "
        "Every sentence should keep the same speaker identity, natural volume, and readable "
        "cadence while audio begins early and continues without waiting for the entire response."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--reference-audio", required=True)
    reference_group = parser.add_mutually_exclusive_group(required=True)
    reference_group.add_argument("--reference-text")
    reference_group.add_argument("--reference-text-file")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--measured-samples", type=int, default=3)
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=[4, 8])
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--xvec-only", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--non-streaming-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefill the complete synthesis request before codec streaming.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def nvidia_memory() -> dict[str, float] | None:
    command = [
        "nvidia-smi",
        "--query-gpu=memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=15)
        values = [float(value.strip()) for value in completed.stdout.splitlines()[0].split(",")]
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    return {"total_mib": values[0], "used_mib": values[1], "free_mib": values[2]}


def model_is_cuda(model: FasterQwen3TTS) -> tuple[bool, list[str]]:
    devices = sorted({str(parameter.device) for parameter in model.model.model.parameters()})
    return bool(devices) and all(device.startswith("cuda") for device in devices), devices


def flatten_chunk(chunk: Any) -> np.ndarray:
    if hasattr(chunk, "detach"):
        chunk = chunk.detach().cpu().numpy()
    audio = np.asarray(chunk, dtype=np.float32).reshape(-1)
    return audio


def audio_metrics(audio: np.ndarray, sample_rate: int) -> dict[str, float | int | bool]:
    if audio.size == 0:
        return {
            "samples": 0,
            "duration_ms": 0.0,
            "finite": True,
            "peak": 0.0,
            "rms": 0.0,
            "rms_dbfs": -120.0,
            "silence_fraction": 1.0,
            "clipping_fraction": 0.0,
        }
    finite = bool(np.isfinite(audio).all())
    safe = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(safe)))
    rms = float(np.sqrt(np.mean(np.square(safe, dtype=np.float64))))
    return {
        "samples": int(audio.size),
        "duration_ms": round(audio.size / sample_rate * 1000.0, 1),
        "finite": finite,
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "rms_dbfs": round(20.0 * math.log10(max(rms, 1e-6)), 2),
        "silence_fraction": round(float(np.mean(np.abs(safe) < 1e-4)), 6),
        "clipping_fraction": round(float(np.mean(np.abs(safe) >= 0.999)), 6),
    }


def run_stream(
    model: FasterQwen3TTS,
    *,
    text: str,
    reference_audio: str,
    reference_text: str,
    chunk_size: int,
    seed: int,
    max_new_tokens: int,
    xvec_only: bool,
    non_streaming_mode: bool,
) -> tuple[dict[str, Any], np.ndarray, int]:
    seed_all(seed)
    started = time.perf_counter()
    yields: list[float] = []
    chunks: list[np.ndarray] = []
    timing_payloads: list[dict[str, Any]] = []
    sample_rate: int | None = None

    stream = model.generate_voice_clone_streaming(
        text=text,
        language="English",
        ref_audio=reference_audio,
        ref_text=reference_text,
        chunk_size=chunk_size,
        max_new_tokens=max_new_tokens,
        xvec_only=xvec_only,
        non_streaming_mode=non_streaming_mode,
        append_silence=True,
    )
    for raw_chunk, raw_sample_rate, timing in stream:
        now = time.perf_counter()
        yields.append(now - started)
        sample_rate = int(raw_sample_rate)
        chunks.append(flatten_chunk(raw_chunk))
        timing_payloads.append(dict(timing) if isinstance(timing, dict) else {"value": str(timing)})

    completed = time.perf_counter()
    if sample_rate is None:
        sample_rate = int(model.sample_rate)
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    metrics = audio_metrics(audio, sample_rate)
    duration_s = float(metrics["duration_ms"]) / 1000.0
    final_steps = (
        int(timing_payloads[-1].get("total_steps_so_far", 0))
        if timing_payloads
        else 0
    )
    hit_token_cap = final_steps >= max_new_tokens - chunk_size
    plausible_duration_limit_s = max(12.0, len(text.split()) * 0.85)
    wall_s = completed - started
    chunk_gaps_ms = [round((current - previous) * 1000.0, 1) for previous, current in zip(yields, yields[1:])]
    per_chunk_audio_ms = [round(chunk.size / sample_rate * 1000.0, 1) for chunk in chunks]
    chunk_debt_ms = [
        round(gap - playable, 1)
        for gap, playable in zip(chunk_gaps_ms, per_chunk_audio_ms[:-1])
    ]
    result = {
        "seed": seed,
        "chunk_size": chunk_size,
        "max_new_tokens": max_new_tokens,
        "final_steps": final_steps,
        "hit_token_cap": hit_token_cap,
        "natural_eos": bool(timing_payloads) and not hit_token_cap,
        "plausible_duration_limit_s": round(plausible_duration_limit_s, 2),
        "plausible_duration": duration_s <= plausible_duration_limit_s,
        "ttfa_ms": round(yields[0] * 1000.0, 1) if yields else None,
        "total_wall_ms": round(wall_s * 1000.0, 1),
        "rtfx": round(duration_s / wall_s, 4) if wall_s > 0 else 0.0,
        "stream_completed_after_first_chunk": bool(yields and completed > started + yields[0]),
        "chunk_count": len(chunks),
        "chunk_yield_ms": [round(value * 1000.0, 1) for value in yields],
        "chunk_gaps_ms": chunk_gaps_ms,
        "chunk_audio_ms": per_chunk_audio_ms,
        "chunk_debt_ms": chunk_debt_ms,
        "max_positive_chunk_debt_ms": round(max([0.0, *chunk_debt_ms]), 1),
        "audio": metrics,
        "upstream_timing": timing_payloads[-1] if timing_payloads else {},
    }
    return result, audio, sample_rate


def median(values: Iterable[float]) -> float | None:
    items = list(values)
    return round(float(statistics.median(items)), 2) if items else None


def main() -> int:
    args = parse_args()
    reference_text = (
        Path(args.reference_text_file).read_text(encoding="utf-8").strip()
        if args.reference_text_file
        else str(args.reference_text)
    )
    output_dir = Path(args.output_dir)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    if not torch.cuda.is_available() or not torch.version.cuda or "+cpu" in torch.__version__.lower():
        raise RuntimeError("CUDA PyTorch is mandatory for this probe")

    seed_all(20260731)
    gpu_before = nvidia_memory()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    model = FasterQwen3TTS.from_pretrained(
        args.model,
        device="cuda",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        max_seq_len=2048,
    )
    load_ms = round((time.perf_counter() - load_started) * 1000.0, 1)
    cuda_only, parameter_devices = model_is_cuda(model)

    warm_started = time.perf_counter()
    model.warmup(prefill_len=100)
    warmup_ms = round((time.perf_counter() - warm_started) * 1000.0, 1)
    warm_result, _, _ = run_stream(
        model,
        text=TEXTS["short"],
        reference_audio=args.reference_audio,
        reference_text=reference_text,
        chunk_size=8,
        seed=100,
        max_new_tokens=args.max_new_tokens,
        xvec_only=args.xvec_only,
        non_streaming_mode=args.non_streaming_mode,
    )

    samples: list[dict[str, Any]] = []
    for chunk_size in args.chunk_sizes:
        for sample_index in range(args.measured_samples):
            result, audio, sample_rate = run_stream(
                model,
                text=TEXTS["medium"],
                reference_audio=args.reference_audio,
                reference_text=reference_text,
                chunk_size=chunk_size,
                seed=1000 + chunk_size * 100 + sample_index,
                max_new_tokens=args.max_new_tokens,
                xvec_only=args.xvec_only,
                non_streaming_mode=args.non_streaming_mode,
            )
            result.update({"scenario": "medium", "sample_index": sample_index})
            samples.append(result)
            if sample_index == 0:
                sf.write(audio_dir / f"{args.model_label}-chunk{chunk_size}-medium.wav", audio, sample_rate)
            print(
                json.dumps(
                    {
                        "event": "sample_completed",
                        "model": args.model_label,
                        "scenario": "medium",
                        "chunk_size": chunk_size,
                        "sample_index": sample_index,
                        "ttfa_ms": result["ttfa_ms"],
                        "rtfx": result["rtfx"],
                        "natural_eos": result["natural_eos"],
                        "duration_ms": result["audio"]["duration_ms"],
                    }
                ),
                flush=True,
            )

    long_result, long_audio, long_sample_rate = run_stream(
        model,
        text=TEXTS["long"],
        reference_audio=args.reference_audio,
        reference_text=reference_text,
        chunk_size=8,
        seed=2000,
        max_new_tokens=args.max_new_tokens,
        xvec_only=args.xvec_only,
        non_streaming_mode=args.non_streaming_mode,
    )
    long_result.update({"scenario": "long", "sample_index": 0})
    samples.append(long_result)
    sf.write(audio_dir / f"{args.model_label}-chunk8-long.wav", long_audio, long_sample_rate)
    print(
        json.dumps(
            {
                "event": "sample_completed",
                "model": args.model_label,
                "scenario": "long",
                "chunk_size": 8,
                "sample_index": 0,
                "ttfa_ms": long_result["ttfa_ms"],
                "rtfx": long_result["rtfx"],
                "natural_eos": long_result["natural_eos"],
                "duration_ms": long_result["audio"]["duration_ms"],
            }
        ),
        flush=True,
    )

    allocated_mib = torch.cuda.max_memory_allocated() / 1024**2
    reserved_mib = torch.cuda.max_memory_reserved() / 1024**2
    gpu_after = nvidia_memory()

    measured = [sample for sample in samples if sample["scenario"] == "medium"]
    summaries: dict[str, Any] = {}
    for chunk_size in args.chunk_sizes:
        group = [sample for sample in measured if sample["chunk_size"] == chunk_size]
        summaries[str(chunk_size)] = {
            "median_ttfa_ms": median(float(sample["ttfa_ms"]) for sample in group if sample["ttfa_ms"] is not None),
            "median_rtfx": median(float(sample["rtfx"]) for sample in group),
            "max_chunk_debt_ms": max(float(sample["max_positive_chunk_debt_ms"]) for sample in group),
        }

    gated_samples = [warm_result, *samples]
    audio_valid = all(
        sample["audio"]["finite"]
        and sample["audio"]["samples"] > 0
        and sample["audio"]["rms"] > 1e-4
        and sample["audio"]["silence_fraction"] < 0.95
        and sample["audio"]["clipping_fraction"] < 0.01
        for sample in gated_samples
    )
    stream_valid = all(
        sample["chunk_count"] >= 2 and sample["stream_completed_after_first_chunk"]
        for sample in gated_samples
    )
    natural_stop_valid = all(
        sample["natural_eos"] and sample["plausible_duration"]
        for sample in gated_samples
    )
    realtime_valid = all(float(sample["rtfx"]) > 1.0 for sample in samples)
    ttfa_candidates = [
        float(summary["median_ttfa_ms"])
        for summary in summaries.values()
        if summary["median_ttfa_ms"] is not None
    ]
    ttfa_valid = bool(ttfa_candidates) and min(ttfa_candidates) < 500.0
    vram_valid = reserved_mib <= 11264.0
    passed = (
        cuda_only
        and vram_valid
        and audio_valid
        and stream_valid
        and natural_stop_valid
        and realtime_valid
        and ttfa_valid
    )

    payload = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "package": "faster-qwen3-tts",
        "package_version": importlib.metadata.version("faster-qwen3-tts"),
        "model": args.model,
        "model_label": args.model_label,
        "runtime": {
            "python_torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0),
            "parameter_devices": parameter_devices,
            "cuda_only": cuda_only,
            "load_ms": load_ms,
            "warmup_ms": warmup_ms,
            "torch_peak_allocated_mib": round(allocated_mib, 1),
            "torch_peak_reserved_mib": round(reserved_mib, 1),
            "system_gpu_before": gpu_before,
            "system_gpu_after": gpu_after,
        },
        "reference": {
            "audio_label": Path(args.reference_audio).name,
            "transcript_chars": len(reference_text),
            "mode": "xvec" if args.xvec_only else "icl",
            "non_streaming_mode": args.non_streaming_mode,
            "append_silence": True,
        },
        "warm_sample": warm_result,
        "samples": samples,
        "summary_by_chunk_size": summaries,
        "gates": {
            "cuda_only": cuda_only,
            "vram_within_11gib": vram_valid,
            "audio_valid": audio_valid,
            "streaming_before_completion": stream_valid,
            "natural_stop_and_plausible_duration": natural_stop_valid,
            "faster_than_realtime": realtime_valid,
            "ttfa_under_500ms": ttfa_valid,
        },
        "overall_status": "passed" if passed else "failed",
    }
    output_path = output_dir / "runtime-result.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"result": str(output_path), "overall_status": payload["overall_status"], "gates": payload["gates"]}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
