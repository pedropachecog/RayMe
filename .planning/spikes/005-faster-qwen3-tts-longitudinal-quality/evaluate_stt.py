#!/usr/bin/env python3
"""Transcribe soak WAVs with RayMe STT and compare early versus late WER."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soak-result", required=True)
    parser.add_argument("--audio-dir", required=True)
    parser.add_argument("--endpoint", default="https://192.168.1.199:9443/stt/transcribe")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, ref_word in enumerate(reference, start=1):
        current = [row]
        for column, hyp_word in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (ref_word != hyp_word),
                )
            )
        previous = current
    return previous[-1]


def wer(reference: str, hypothesis: str) -> float:
    reference_words = words(reference)
    return edit_distance(reference_words, words(hypothesis)) / max(len(reference_words), 1)


def main() -> int:
    args = parse_args()
    soak = json.loads(Path(args.soak_result).read_text(encoding="utf-8"))
    audio_dir = Path(args.audio_dir)
    results: list[dict[str, Any]] = []
    with httpx.Client(verify=False, timeout=120.0) as client:
        for turn in soak["turns"]:
            audio_path = audio_dir / turn["audio_file"]
            with audio_path.open("rb") as handle:
                response = client.post(
                    args.endpoint,
                    files={"file": (audio_path.name, handle, "audio/wav")},
                )
            response.raise_for_status()
            body = response.json()
            transcript = str(body.get("transcript") or "")
            result = {
                "turn": turn["turn"],
                "anchor": turn["anchor"],
                "status": body.get("status"),
                "target": turn["text"],
                "transcript": transcript,
                "wer": round(wer(turn["text"], transcript), 6),
            }
            results.append(result)
            print(json.dumps(result), flush=True)

    early = results[:5]
    late = results[-5:]
    early_wer = float(statistics.mean(result["wer"] for result in early))
    late_wer = float(statistics.mean(result["wer"] for result in late))
    gates = {
        "all_50_transcribed": len(results) == 50,
        "all_stt_accepted": all(result["status"] == "accepted" for result in results),
        "late_wer_at_most_0_20": late_wer <= 0.20,
        "late_wer_degradation_at_most_0_15": late_wer - early_wer <= 0.15,
    }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "endpoint": args.endpoint,
        "stt_model": "distil-large-v3/int8_float16",
        "turns": results,
        "summary": {
            "early_mean_wer": round(early_wer, 6),
            "late_mean_wer": round(late_wer, 6),
            "late_minus_early_wer": round(late_wer - early_wer, 6),
            "overall_mean_wer": round(float(statistics.mean(result["wer"] for result in results)), 6),
        },
        "gates": gates,
        "overall_status": "passed" if all(gates.values()) else "failed",
    }
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"overall_status": payload["overall_status"], "summary": payload["summary"], "gates": gates}), flush=True)
    return 0 if payload["overall_status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
