#!/usr/bin/env python3
"""Local-only OMEN sweep for Qwen voice-clone semantic fidelity."""

from __future__ import annotations

import argparse
import gc
import json
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


PHASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PHASE_DIR.parents[2]
AI_BACKEND_ROOT = REPO_ROOT / "ai-backend"
sys.path.insert(0, str(AI_BACKEND_ROOT))

REFERENCE_TEXT = (
    "This is a deterministic synthetic voice generated for RayMe hardware testing. "
    "It is not a real person and it is authorized only for local call validation."
)
TARGETS = {
    "names-numbers": "Pedro asked Maya to call room 17 at 4:35 p.m. on October 12.",
    "negation-abbreviations": "No, the U.S. office did not approve version 2.4, and Dr. Lee did not sign it.",
    "punctuation-final-word": "We can stop, wait, or continue; whichever you choose, remember the final word: lighthouse.",
}
PROFILES = {
    "upstream-default": {
        "temperature": 0.9,
        "top_k": 50,
        "top_p": 1.0,
        "do_sample": True,
        "repetition_penalty": 1.05,
    },
    "fidelity-075": {
        "temperature": 0.75,
        "top_k": 30,
        "top_p": 0.95,
        "do_sample": True,
        "repetition_penalty": 1.10,
    },
    "fidelity-060": {
        "temperature": 0.60,
        "top_k": 20,
        "top_p": 0.90,
        "do_sample": True,
        "repetition_penalty": 1.10,
    },
    "greedy": {
        "temperature": 1.0,
        "top_k": 0,
        "top_p": 1.0,
        "do_sample": False,
        "repetition_penalty": 1.10,
    },
}
TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


def _generate_reference(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    escaped_path = str(path).replace("'", "''")
    escaped_text = REFERENCE_TEXT.replace("'", "''")
    command = "\n".join(
        (
            "$ErrorActionPreference = 'Stop'",
            "$speaker = New-Object -ComObject SAPI.SpVoice",
            "$voice = $speaker.GetVoices() | Where-Object { $_.GetAttribute('Name') -eq 'Microsoft David Desktop' } | Select-Object -First 1",
            "if (-not $voice) { throw 'Deterministic SAPI voice is unavailable' }",
            "$speaker.Voice = $voice",
            "$speaker.Rate = -1",
            "$speaker.Volume = 100",
            "$stream = New-Object -ComObject SAPI.SpFileStream",
            f"$stream.Open('{escaped_path}', 3, $false)",
            "$speaker.AudioOutputStream = $stream",
            f"[void]$speaker.Speak('{escaped_text}')",
            "$stream.Close()",
        )
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not path.is_file():
        raise RuntimeError("SAPI reference generation failed")


def _silenced_reference(source: Path, destination: Path) -> None:
    audio, sample_rate = sf.read(source, dtype="float32", always_2d=False)
    mono = np.asarray(audio, dtype=np.float32).reshape(-1)
    padded = np.concatenate((mono, np.zeros(int(sample_rate * 0.5), dtype=np.float32)))
    sf.write(destination, padded, sample_rate, format="WAV", subtype="PCM_16")


def _reset_rng(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def generate(model_dir: Path, output_dir: Path) -> None:
    import torch
    from app.models.tts_qwen3_worker import load_runtime

    output_dir.mkdir(parents=True, exist_ok=True)
    reference = output_dir / "reference.wav"
    reference_with_silence = output_dir / "reference-with-silence.wav"
    _generate_reference(reference)
    _silenced_reference(reference, reference_with_silence)

    runtime = load_runtime(model_dir)
    prompt = runtime.model.create_voice_clone_prompt(
        ref_audio=str(reference_with_silence),
        ref_text=REFERENCE_TEXT,
        x_vector_only_mode=False,
    )
    manifest: list[dict[str, Any]] = []
    for profile_index, (profile_name, profile) in enumerate(PROFILES.items()):
        for target_index, (target_name, target_text) in enumerate(TARGETS.items()):
            seed = 92100 + target_index
            _reset_rng(seed)
            chunks: list[np.ndarray] = []
            sample_rate = 24000
            for audio, sample_rate, _timing in runtime.generate_voice_clone_streaming(
                text=target_text,
                language="English",
                ref_text=REFERENCE_TEXT,
                voice_clone_prompt=prompt,
                max_new_tokens=384,
                min_new_tokens=2,
                chunk_size=4,
                non_streaming_mode=True,
                append_silence=True,
                parity_mode=False,
                **profile,
            ):
                chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
            if not chunks:
                raise RuntimeError(f"empty sweep output: {profile_name}/{target_name}")
            path = output_dir / f"{profile_index:02d}-{profile_name}-{target_name}.wav"
            sf.write(path, np.concatenate(chunks), sample_rate, format="WAV", subtype="PCM_16")
            manifest.append(
                {
                    "profile": profile_name,
                    "profile_settings": profile,
                    "target": target_name,
                    "target_text": target_text,
                    "seed": seed,
                    "wav": path.name,
                }
            )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    del prompt, runtime
    gc.collect()
    torch.cuda.empty_cache()


def _words(text: str) -> list[str]:
    return TOKEN.findall(text.casefold())


def _wer(reference: str, hypothesis: str) -> float:
    expected = _words(reference)
    actual = _words(hypothesis)
    previous = list(range(len(actual) + 1))
    for index, expected_word in enumerate(expected, start=1):
        current = [index]
        for offset, actual_word in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[offset] + 1,
                    previous[offset - 1] + (expected_word != actual_word),
                )
            )
        previous = current
    return float(previous[-1]) / max(len(expected), 1)


def score(output_dir: Path) -> None:
    from app.models.stt import WhisperSttAdapter

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    stt = WhisperSttAdapter()
    rows: list[dict[str, Any]] = []
    for item in manifest:
        transcript = str(
            stt.transcribe(audio=output_dir / item["wav"], apply_vad_filter=True).get(
                "transcript"
            )
            or ""
        )
        expected_words = _words(item["target_text"])
        actual_words = _words(transcript)
        rows.append(
            {
                **item,
                "transcript": transcript,
                "wer": round(_wer(item["target_text"], transcript), 6),
                "final_word_pass": bool(
                    expected_words
                    and actual_words
                    and expected_words[-1] == actual_words[-1]
                ),
            }
        )
    profiles: list[dict[str, Any]] = []
    for profile_name in PROFILES:
        selected = [row for row in rows if row["profile"] == profile_name]
        wers = sorted(float(row["wer"]) for row in selected)
        profiles.append(
            {
                "profile": profile_name,
                "mean_wer": round(sum(wers) / len(wers), 6),
                "median_wer": wers[len(wers) // 2],
                "max_wer": max(wers),
                "final_word_pass_count": sum(bool(row["final_word_pass"]) for row in selected),
            }
        )
    result = {"profiles": profiles, "rows": rows}
    (output_dir / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("__RAYME_QWEN3_FIDELITY_SWEEP__" + json.dumps(result, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("generate", "score"))
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.mode == "generate":
        if args.model_dir is None:
            parser.error("--model-dir is required for generate")
        generate(args.model_dir.resolve(strict=True), args.output_dir.resolve())
    else:
        score(args.output_dir.resolve(strict=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
