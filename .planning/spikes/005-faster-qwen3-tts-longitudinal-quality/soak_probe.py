#!/usr/bin/env python3
"""Run 50 sequential Faster Qwen3-TTS turns and detect degradation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch

from faster_qwen3_tts import FasterQwen3TTS


ANCHOR_TEXT = (
    "A long conversation should keep this voice clear, full, and easy to understand "
    "from the first turn through the final turn."
)
VARIED_TEXTS = [
    "I am still here with you, speaking at a natural volume and keeping every consonant clear.",
    "The rain eased after midnight, and the quiet street reflected every porch light like glass.",
    "We can take this one thought at a time, without rushing the pauses or swallowing the endings.",
    "Tomorrow I would like to walk by the water, find a warm cafe, and write down what matters.",
    "A real phone conversation needs a steady voice, quick playback, and room for you to interrupt.",
    "Nothing about this sentence should become muffled, breathy, metallic, noisy, or hard to follow.",
    "I remember the small details: the open window, the blue notebook, and the song from downstairs.",
    "Even after many replies, the speaker identity and natural cadence should remain recognizably stable.",
]
ANCHOR_TURNS = {1, 10, 20, 30, 40, 50}
TURN_COUNT = 50
MAX_NEW_TOKENS = 384
CHUNK_SIZE = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    parser.add_argument("--reference-audio", required=True)
    parser.add_argument("--reference-text-file", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def flatten(chunk: Any) -> np.ndarray:
    if hasattr(chunk, "detach"):
        chunk = chunk.detach().cpu().numpy()
    return np.asarray(chunk, dtype=np.float32).reshape(-1)


def acoustic_metrics(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    safe = np.nan_to_num(audio.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    rms = float(np.sqrt(np.mean(np.square(safe)))) if safe.size else 0.0
    active = safe[np.abs(safe) >= 1e-4]
    active_rms = float(np.sqrt(np.mean(np.square(active)))) if active.size else 0.0

    frame_size = 1024
    hop = 512
    centroids: list[float] = []
    high_ratios: list[float] = []
    flatnesses: list[float] = []
    window = np.hanning(frame_size)
    frequencies = np.fft.rfftfreq(frame_size, 1.0 / sample_rate)
    useful = (frequencies >= 80.0) & (frequencies <= 8000.0)
    high = (frequencies >= 3000.0) & (frequencies <= 8000.0)
    for start in range(0, max(0, safe.size - frame_size + 1), hop):
        frame = safe[start : start + frame_size]
        if float(np.sqrt(np.mean(np.square(frame)))) < 1e-3:
            continue
        power = np.abs(np.fft.rfft(frame * window)) ** 2
        useful_power = power[useful]
        total = float(useful_power.sum())
        if total <= 1e-12:
            continue
        centroids.append(float((frequencies[useful] * useful_power).sum() / total))
        high_ratios.append(float(power[high].sum() / total))
        flatnesses.append(
            float(np.exp(np.mean(np.log(useful_power + 1e-12))) / (np.mean(useful_power) + 1e-12))
        )

    return {
        "samples": int(safe.size),
        "duration_seconds": round(safe.size / sample_rate, 3),
        "finite": bool(np.isfinite(audio).all()),
        "peak": round(float(np.max(np.abs(safe))) if safe.size else 0.0, 6),
        "rms_dbfs": round(20.0 * math.log10(max(rms, 1e-6)), 3),
        "active_rms_dbfs": round(20.0 * math.log10(max(active_rms, 1e-6)), 3),
        "silence_fraction": round(float(np.mean(np.abs(safe) < 1e-4)) if safe.size else 1.0, 6),
        "clipping_fraction": round(float(np.mean(np.abs(safe) >= 0.999)) if safe.size else 0.0, 6),
        "spectral_centroid_hz": round(float(statistics.median(centroids)), 3) if centroids else 0.0,
        "high_frequency_ratio": round(float(statistics.median(high_ratios)), 6) if high_ratios else 0.0,
        "spectral_flatness": round(float(statistics.median(flatnesses)), 6) if flatnesses else 0.0,
    }


def gpu_memory_used_mib() -> float | None:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return float(completed.stdout.splitlines()[0].strip())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def turn_text(turn: int) -> tuple[str, bool]:
    if turn in ANCHOR_TURNS:
        return ANCHOR_TEXT, True
    return VARIED_TEXTS[(turn - 1) % len(VARIED_TEXTS)], False


def run_turn(
    model: FasterQwen3TTS,
    *,
    turn: int,
    text: str,
    is_anchor: bool,
    reference_audio: str,
    reference_text: str,
    audio_dir: Path,
) -> tuple[dict[str, Any], np.ndarray, int]:
    seed = 4242 if is_anchor else 5000 + turn
    seed_all(seed)
    chunks: list[np.ndarray] = []
    timings: list[dict[str, Any]] = []
    yields: list[float] = []
    sample_rate = int(model.sample_rate)
    started = time.perf_counter()
    stream = model.generate_voice_clone_streaming(
        text=text,
        language="English",
        ref_audio=reference_audio,
        ref_text=reference_text,
        chunk_size=CHUNK_SIZE,
        max_new_tokens=MAX_NEW_TOKENS,
        xvec_only=False,
        non_streaming_mode=True,
        append_silence=True,
    )
    for raw_chunk, raw_sample_rate, timing in stream:
        chunks.append(flatten(raw_chunk))
        timings.append(dict(timing))
        sample_rate = int(raw_sample_rate)
        yields.append(time.perf_counter() - started)
    wall_seconds = time.perf_counter() - started
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    final_steps = int(timings[-1].get("total_steps_so_far", 0)) if timings else 0
    hit_token_cap = final_steps >= MAX_NEW_TOKENS - CHUNK_SIZE
    audio_name = f"turn-{turn:03d}-{'anchor' if is_anchor else 'varied'}.wav"
    sf.write(audio_dir / audio_name, audio, sample_rate)
    metrics = acoustic_metrics(audio, sample_rate)
    result = {
        "turn": turn,
        "text": text,
        "anchor": is_anchor,
        "seed": seed,
        "audio_file": audio_name,
        "pcm_sha256": hashlib.sha256(audio.tobytes()).hexdigest(),
        "sample_rate": sample_rate,
        "final_steps": final_steps,
        "natural_eos": bool(timings) and not hit_token_cap,
        "hit_token_cap": hit_token_cap,
        "chunk_count": len(chunks),
        "first_playback_before_completion": bool(yields and wall_seconds > yields[0]),
        "ttfa_ms": round(yields[0] * 1000.0, 3) if yields else None,
        "wall_seconds": round(wall_seconds, 3),
        "rtfx": round(float(metrics["duration_seconds"]) / wall_seconds, 3)
        if wall_seconds
        else 0.0,
        "torch_allocated_mib": round(torch.cuda.memory_allocated() / 1024**2, 3),
        "torch_reserved_mib": round(torch.cuda.memory_reserved() / 1024**2, 3),
        "system_gpu_used_mib": gpu_memory_used_mib(),
        "audio": metrics,
        "last_timing": timings[-1] if timings else {},
    }
    return result, audio, sample_rate


def mean_for(results: list[dict[str, Any]], path: tuple[str, ...]) -> float:
    values = []
    for result in results:
        value: Any = result
        for key in path:
            value = value[key]
        values.append(float(value))
    return round(float(statistics.mean(values)), 4)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "soak-progress.jsonl"
    reference_text = Path(args.reference_text_file).read_text(encoding="utf-8").strip()

    seed_all(20260731)
    load_started = time.perf_counter()
    model = FasterQwen3TTS.from_pretrained(
        args.model,
        device="cuda",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        max_seq_len=2048,
    )
    model.warmup(prefill_len=100)
    load_and_warm_seconds = time.perf_counter() - load_started

    # Populate the reference prompt cache before timed turns. Production must do
    # this before a call reaches its first spoken response.
    warm_stream = model.generate_voice_clone_streaming(
        text="The voice is ready.",
        language="English",
        ref_audio=args.reference_audio,
        ref_text=reference_text,
        chunk_size=CHUNK_SIZE,
        max_new_tokens=128,
        xvec_only=False,
        non_streaming_mode=True,
        append_silence=True,
    )
    for _ in warm_stream:
        pass

    started_event = {
        "event": "soak_started",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "turn_count": TURN_COUNT,
    }
    progress_path.write_text(json.dumps(started_event) + "\n", encoding="utf-8")
    print(json.dumps(started_event), flush=True)

    results: list[dict[str, Any]] = []
    reel_audio: dict[int, tuple[np.ndarray, int]] = {}
    for turn in range(1, TURN_COUNT + 1):
        text, is_anchor = turn_text(turn)
        result, audio, sample_rate = run_turn(
            model,
            turn=turn,
            text=text,
            is_anchor=is_anchor,
            reference_audio=args.reference_audio,
            reference_text=reference_text,
            audio_dir=audio_dir,
        )
        results.append(result)
        if turn in {1, 25, 46, 50}:
            reel_audio[turn] = (audio, sample_rate)
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "event": "turn_completed",
                    "turn": turn,
                    "anchor": is_anchor,
                    "ttfa_ms": result["ttfa_ms"],
                    "rtfx": result["rtfx"],
                    "natural_eos": result["natural_eos"],
                    "rms_dbfs": result["audio"]["rms_dbfs"],
                    "gpu_mib": result["system_gpu_used_mib"],
                }
            ),
            flush=True,
        )

    early = results[:5]
    late = results[-5:]
    anchors = [result for result in results if result["anchor"]]
    anchor_hashes = sorted({result["pcm_sha256"] for result in anchors})
    rms_delta_db = mean_for(late, ("audio", "rms_dbfs")) - mean_for(early, ("audio", "rms_dbfs"))
    centroid_ratio = mean_for(late, ("audio", "spectral_centroid_hz")) / max(
        mean_for(early, ("audio", "spectral_centroid_hz")), 1e-6
    )
    flatness_delta = mean_for(late, ("audio", "spectral_flatness")) - mean_for(
        early, ("audio", "spectral_flatness")
    )
    rtfx_ratio = mean_for(late, ("rtfx",)) / max(mean_for(early, ("rtfx",)), 1e-6)
    ttfa_delta_ms = mean_for(late, ("ttfa_ms",)) - mean_for(early, ("ttfa_ms",))
    reserved_growth_mib = max(result["torch_reserved_mib"] for result in late) - max(
        result["torch_reserved_mib"] for result in early
    )

    gates = {
        "all_50_turns_completed": len(results) == TURN_COUNT,
        "all_natural_eos": all(result["natural_eos"] for result in results),
        "all_stream_live": all(result["first_playback_before_completion"] for result in results),
        "all_faster_than_realtime": all(result["rtfx"] > 1.0 for result in results),
        "all_audio_valid": all(
            result["audio"]["finite"]
            and result["audio"]["peak"] > 0.001
            and result["audio"]["silence_fraction"] < 0.95
            and result["audio"]["clipping_fraction"] < 0.01
            for result in results
        ),
        "anchors_bit_identical": len(anchor_hashes) == 1,
        "late_rms_within_3db": abs(rms_delta_db) <= 3.0,
        "late_centroid_at_least_70pct": centroid_ratio >= 0.70,
        "late_flatness_growth_below_0_15": flatness_delta <= 0.15,
        "late_throughput_at_least_75pct": rtfx_ratio >= 0.75,
        "late_ttfa_growth_below_200ms": ttfa_delta_ms <= 200.0,
        "reserved_memory_growth_below_256mib": reserved_growth_mib <= 256.0,
    }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "package": "faster-qwen3-tts==0.3.2",
        "load_and_warm_seconds": round(load_and_warm_seconds, 3),
        "settings": {
            "turn_count": TURN_COUNT,
            "chunk_size": CHUNK_SIZE,
            "max_new_tokens": MAX_NEW_TOKENS,
            "mode": "icl",
            "non_streaming_mode": True,
            "anchor_turns": sorted(ANCHOR_TURNS),
        },
        "turns": results,
        "early_late": {
            "early_turns": [result["turn"] for result in early],
            "late_turns": [result["turn"] for result in late],
            "early_mean_rms_dbfs": mean_for(early, ("audio", "rms_dbfs")),
            "late_mean_rms_dbfs": mean_for(late, ("audio", "rms_dbfs")),
            "rms_delta_db": round(rms_delta_db, 4),
            "centroid_ratio": round(centroid_ratio, 4),
            "flatness_delta": round(flatness_delta, 6),
            "rtfx_ratio": round(rtfx_ratio, 4),
            "ttfa_delta_ms": round(ttfa_delta_ms, 3),
            "reserved_growth_mib": round(reserved_growth_mib, 3),
            "anchor_unique_hashes": len(anchor_hashes),
        },
        "gates": gates,
        "overall_status": "passed" if all(gates.values()) else "failed",
    }
    (output_dir / "soak-result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    reel_parts = []
    reel_rate = 24000
    for turn in (1, 25, 46, 50):
        audio, reel_rate = reel_audio[turn]
        reel_parts.extend([audio, np.zeros(reel_rate, dtype=np.float32)])
    sf.write(output_dir / "listening-reel-turns-001-025-046-050.wav", np.concatenate(reel_parts), reel_rate)
    print(json.dumps({"event": "soak_completed", "overall_status": payload["overall_status"], "gates": gates}), flush=True)
    return 0 if payload["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
