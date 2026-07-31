#!/usr/bin/env python3
"""Bounded Faster Qwen3-TTS voice-clone termination diagnostic.

Runs known-good upstream and RayMe references through the same loaded model.
Every case is capped at 256 codec steps so a missing EOS cannot create another
minute-long sample. Results are flushed after each case for incident evidence.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch

from faster_qwen3_tts import FasterQwen3TTS


TEXT = (
    "I know the last voice started clearly and then slowly became muffled. "
    "This test checks whether the same voice stays steady from beginning to end."
)
UPSTREAM_TRANSCRIPT = (
    "I'm confused why some people have super short timelines, yet at the same time are "
    "bullish on scaling up reinforcement learning atop LLMs. If we're actually close to "
    "a human-like learner, then this whole approach of training on verifiable outcomes is doomed."
)
MAX_NEW_TOKENS = 256
CHUNK_SIZE = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
    parser.add_argument("--rayme-reference-audio", required=True)
    parser.add_argument("--rayme-reference-text-file", required=True)
    parser.add_argument("--upstream-reference-audio", required=True)
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


def append_result(path: Path, result: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, sort_keys=True) + "\n")


def run_case(
    model: FasterQwen3TTS,
    *,
    name: str,
    reference_audio: str,
    reference_text: str,
    xvec_only: bool,
    non_streaming_mode: bool,
    output_dir: Path,
    seed: int,
) -> dict[str, Any]:
    seed_all(seed)
    chunks: list[np.ndarray] = []
    timings: list[dict[str, Any]] = []
    yields: list[float] = []
    sample_rate = int(model.sample_rate)
    started = time.perf_counter()
    stream = model.generate_voice_clone_streaming(
        text=TEXT,
        language="English",
        ref_audio=reference_audio,
        ref_text=reference_text,
        chunk_size=CHUNK_SIZE,
        max_new_tokens=MAX_NEW_TOKENS,
        xvec_only=xvec_only,
        non_streaming_mode=non_streaming_mode,
        append_silence=True,
    )
    for raw_chunk, raw_sample_rate, timing in stream:
        chunks.append(flatten(raw_chunk))
        timings.append(dict(timing))
        sample_rate = int(raw_sample_rate)
        yields.append(time.perf_counter() - started)

    wall_seconds = time.perf_counter() - started
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    duration_seconds = audio.size / sample_rate
    final_steps = int(timings[-1].get("total_steps_so_far", 0)) if timings else 0
    hit_token_cap = final_steps >= MAX_NEW_TOKENS - CHUNK_SIZE
    result = {
        "name": name,
        "seed": seed,
        "reference": Path(reference_audio).name,
        "mode": "xvec" if xvec_only else "icl",
        "non_streaming_mode": non_streaming_mode,
        "max_new_tokens": MAX_NEW_TOKENS,
        "final_steps": final_steps,
        "hit_token_cap": hit_token_cap,
        "natural_eos": bool(timings) and not hit_token_cap,
        "chunk_count": len(chunks),
        "ttfa_ms": round(yields[0] * 1000.0, 1) if yields else None,
        "wall_seconds": round(wall_seconds, 3),
        "duration_seconds": round(duration_seconds, 3),
        "rtfx": round(duration_seconds / wall_seconds, 3) if wall_seconds else 0.0,
        "finite": bool(np.isfinite(audio).all()),
        "rms": round(float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))), 6)
        if audio.size
        else 0.0,
        "last_timing": timings[-1] if timings else {},
    }
    sf.write(output_dir / f"{name}.wav", audio, sample_rate)
    return result


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "termination-diagnostic.jsonl"
    rayme_text = Path(args.rayme_reference_text_file).read_text(encoding="utf-8").strip()

    seed_all(20260731)
    model = FasterQwen3TTS.from_pretrained(
        args.model,
        device="cuda",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        max_seq_len=2048,
    )
    model.warmup(prefill_len=100)

    cases = [
        ("upstream-icl-step", args.upstream_reference_audio, UPSTREAM_TRANSCRIPT, False, False),
        ("upstream-icl-prefill", args.upstream_reference_audio, UPSTREAM_TRANSCRIPT, False, True),
        ("rayme-icl-step", args.rayme_reference_audio, rayme_text, False, False),
        ("rayme-icl-prefill", args.rayme_reference_audio, rayme_text, False, True),
        ("upstream-xvec", args.upstream_reference_audio, "", True, False),
        ("rayme-xvec", args.rayme_reference_audio, "", True, False),
    ]
    header = {
        "event": "diagnostic_started",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "text": TEXT,
    }
    append_result(jsonl_path, header)
    print(json.dumps(header), flush=True)

    results = []
    for index, (name, audio, transcript, xvec, prefill) in enumerate(cases):
        print(json.dumps({"event": "case_started", "name": name}), flush=True)
        result = run_case(
            model,
            name=name,
            reference_audio=audio,
            reference_text=transcript,
            xvec_only=xvec,
            non_streaming_mode=prefill,
            output_dir=output_dir,
            seed=3000 + index,
        )
        results.append(result)
        append_result(jsonl_path, result)
        print(json.dumps(result), flush=True)

    summary = {
        "event": "diagnostic_completed",
        "natural_eos_cases": [result["name"] for result in results if result["natural_eos"]],
        "token_cap_cases": [result["name"] for result in results if result["hit_token_cap"]],
    }
    append_result(jsonl_path, summary)
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
