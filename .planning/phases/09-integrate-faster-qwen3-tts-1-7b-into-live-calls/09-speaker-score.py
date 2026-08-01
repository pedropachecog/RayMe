#!/usr/bin/env python3
"""Privacy-local, CUDA-only WavLM speaker-stability scorer for Phase 09."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


MODEL_ID = "microsoft/wavlm-base-plus-sv"
MODEL_REVISION = "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e"
MODEL_CLASS = "WavLMForXVector"
# Runtime pin: transformers==4.57.3. Do not float this release scorer.
TRANSFORMERS_VERSION = "4.57.3"
TORCH_VERSION = "2.10.0+cu126"
TORCH_CUDA_VERSION = "12.6"
SAMPLE_RATE_HZ = 16_000
MAXIMUM_LATE_DROP = 0.05
BASELINE_BUCKETS = ("short", "medium", "long")
EARLY_TURNS = tuple(range(1, 6))
MIDDLE_TURNS = tuple(range(23, 28))
LATE_TURNS = tuple(range(46, 51))


class SpeakerScoreError(Exception):
    """Pinned scorer contract failure."""


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SpeakerScoreError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise SpeakerScoreError(f"{label} must be a finite number")
    return number


def _require_sha(value: str, *, label: str, length: int) -> str:
    if not isinstance(value, str) or len(value) != length or any(char not in "0123456789abcdef" for char in value):
        raise SpeakerScoreError(f"{label} must be a lowercase {length}-character hex digest")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise SpeakerScoreError("cosine inputs must have the same non-zero length")
    left_values = [_finite_number(value, label="left embedding value") for value in left]
    right_values = [_finite_number(value, label="right embedding value") for value in right]
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm <= 0.0 or right_norm <= 0.0:
        raise SpeakerScoreError("cosine input has a zero-norm embedding")
    return sum(a * b for a, b in zip(left_values, right_values, strict=True)) / (left_norm * right_norm)


def linear_resample(samples: Sequence[float], source_rate: int, target_rate: int = SAMPLE_RATE_HZ) -> list[float]:
    if source_rate <= 0 or target_rate <= 0:
        raise SpeakerScoreError("sample rates must be positive")
    values = [_finite_number(value, label="audio sample") for value in samples]
    if not values:
        raise SpeakerScoreError("audio must contain at least one sample")
    if source_rate == target_rate:
        return values
    output_length = max(1, round(len(values) * target_rate / source_rate))
    if len(values) == 1 or output_length == 1:
        return [values[0]] * output_length
    scale = (len(values) - 1) / (output_length - 1)
    output: list[float] = []
    for output_index in range(output_length):
        source_position = output_index * scale
        lower = int(math.floor(source_position))
        upper = min(lower + 1, len(values) - 1)
        fraction = source_position - lower
        output.append(values[lower] * (1.0 - fraction) + values[upper] * fraction)
    return output


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _median(values: Iterable[float], *, label: str) -> float:
    numbers = [_finite_number(value, label=label) for value in values]
    if not numbers:
        raise SpeakerScoreError(f"{label} requires at least one score")
    return float(statistics.median(numbers))


def _score_rows(
    rows: Sequence[tuple[str | int, str, float]],
    *,
    label: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for bucket_id, audio_sha256, cosine in rows:
        _require_sha(audio_sha256, label=f"{label} audio_sha256", length=64)
        score = _finite_number(cosine, label=f"{label} cosine")
        if score < -1.0 or score > 1.0:
            raise SpeakerScoreError(f"{label} cosine must be between -1 and 1")
        result.append({"bucket_id": bucket_id, "audio_sha256": audio_sha256, "cosine": score})
    return result


def build_score_payload(
    *,
    deployed_commit: str,
    reference_sha256: str,
    baseline_commit: str,
    baseline_scores: Sequence[tuple[str, str, float]],
    early_scores: Sequence[tuple[int, str, float]],
    middle_scores: Sequence[tuple[int, str, float]],
    late_scores: Sequence[tuple[int, str, float]],
    runtime_metadata: dict[str, str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    _require_sha(deployed_commit, label="deployed commit", length=40)
    _require_sha(baseline_commit, label="baseline commit", length=40)
    if deployed_commit != baseline_commit:
        raise SpeakerScoreError("baseline commit must match the deployed commit")
    _require_sha(reference_sha256, label="reference_sha256", length=64)

    if tuple(row[0] for row in baseline_scores) != BASELINE_BUCKETS:
        raise SpeakerScoreError(f"baseline bucket ids must be {list(BASELINE_BUCKETS)}")
    if tuple(row[0] for row in early_scores) != EARLY_TURNS:
        raise SpeakerScoreError(f"early turn ids must be {list(EARLY_TURNS)}")
    if tuple(row[0] for row in middle_scores) != MIDDLE_TURNS:
        raise SpeakerScoreError(f"middle turn ids must be {list(MIDDLE_TURNS)}")
    if tuple(row[0] for row in late_scores) != LATE_TURNS:
        raise SpeakerScoreError(f"late turn ids must be {list(LATE_TURNS)}")

    required_runtime = {
        "transformers_version": TRANSFORMERS_VERSION,
        "torch_version": TORCH_VERSION,
        "torch_cuda_version": TORCH_CUDA_VERSION,
    }
    for key, expected in required_runtime.items():
        if runtime_metadata.get(key) != expected:
            raise SpeakerScoreError(f"{key} must be {expected}")
    device = runtime_metadata.get("device", "")
    if not device.startswith("cuda"):
        raise SpeakerScoreError("speaker scorer device must be CUDA")
    if not runtime_metadata.get("gpu_name"):
        raise SpeakerScoreError("speaker scorer GPU name is required")

    baseline = _score_rows(baseline_scores, label="baseline")
    early = _score_rows(early_scores, label="early")
    middle = _score_rows(middle_scores, label="middle")
    late = _score_rows(late_scores, label="late")
    integrated_baseline_median = _median((row["cosine"] for row in baseline), label="baseline cosine")
    early_median = _median((row["cosine"] for row in early), label="early cosine")
    middle_median = _median((row["cosine"] for row in middle), label="middle cosine")
    late_median = _median((row["cosine"] for row in late), label="late cosine")
    late_minus_early = late_median - early_median
    late_minus_baseline = late_median - integrated_baseline_median
    speaker_stability_gate = (
        late_median >= early_median - MAXIMUM_LATE_DROP
        and late_median >= integrated_baseline_median - MAXIMUM_LATE_DROP
    )

    return {
        "schema_version": 1,
        "phase": "09",
        "artifact": "speaker",
        "generated_at": generated_at or _utc_now(),
        "deployed_commit": deployed_commit,
        "critical_gates": ["speaker_stability"],
        "baseline_commit": baseline_commit,
        "reference_sha256": reference_sha256,
        "scorer": {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "model_class": MODEL_CLASS,
            "transformers_version": runtime_metadata["transformers_version"],
            "torch_version": runtime_metadata["torch_version"],
            "torch_cuda_version": runtime_metadata["torch_cuda_version"],
            "device": runtime_metadata["device"],
            "gpu_name": runtime_metadata["gpu_name"],
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "local_files_only": True,
        },
        "baseline_scores": baseline,
        "early_scores": early,
        "middle_scores": middle,
        "late_scores": late,
        "integrated_baseline_median": integrated_baseline_median,
        "early_median": early_median,
        "middle_median": middle_median,
        "late_median": late_median,
        "late_minus_early": late_minus_early,
        "late_minus_integrated_baseline": late_minus_baseline,
        "maximum_late_drop": MAXIMUM_LATE_DROP,
        "speaker_stability_gate": speaker_stability_gate,
        "absolute_cosine_is_human_likeness_judgment": False,
        "audio_and_embeddings_retained": "local_only_uncommitted",
        "autonomous_release_ready": "pending_other_gates",
        "integrated_human_listening_status": "pending",
        "physical_call_status": "pending",
    }


def _load_audio(path: Path) -> tuple[list[float], int]:
    try:
        import soundfile
    except ImportError as exc:
        raise SpeakerScoreError("the existing SoundFile runtime is required") from exc
    audio, sample_rate = soundfile.read(path, dtype="float32", always_2d=True)
    if audio.shape[0] == 0 or audio.shape[1] == 0:
        raise SpeakerScoreError("audio is empty")
    mono = audio.mean(axis=1).tolist()
    values = linear_resample(mono, int(sample_rate), SAMPLE_RATE_HZ)
    if not values or max(abs(value) for value in values) < 0.001:
        raise SpeakerScoreError("audio is empty or near-silent")
    return values, SAMPLE_RATE_HZ


def _load_local_runtime() -> dict[str, Any]:
    try:
        import torch
        import transformers
        from huggingface_hub import snapshot_download
        from transformers import AutoFeatureExtractor, WavLMForXVector
    except ImportError as exc:
        raise SpeakerScoreError("the pinned local Torch/transformers runtime is required") from exc

    if transformers.__version__ != TRANSFORMERS_VERSION:
        raise SpeakerScoreError(f"transformers=={TRANSFORMERS_VERSION} is required")
    if torch.__version__ != TORCH_VERSION:
        raise SpeakerScoreError(f"torch=={TORCH_VERSION} is required")
    if torch.version.cuda != TORCH_CUDA_VERSION:
        raise SpeakerScoreError(f"Torch CUDA {TORCH_CUDA_VERSION} is required")
    if not torch.cuda.is_available():
        raise SpeakerScoreError("speaker scoring requires CUDA")

    model_dir = Path(
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            local_files_only=True,
        )
    ).resolve()
    if model_dir.name != MODEL_REVISION:
        raise SpeakerScoreError("local WavLM snapshot is not the pinned revision")
    extractor = AutoFeatureExtractor.from_pretrained(str(model_dir), local_files_only=True)
    model = WavLMForXVector.from_pretrained(str(model_dir), local_files_only=True)
    if model.__class__ is not WavLMForXVector or model.__class__.__name__ != MODEL_CLASS:
        raise SpeakerScoreError("loaded model must be WavLMForXVector")
    device = torch.device("cuda")
    model = model.to(device).eval()
    parameters = list(model.parameters())
    if not parameters or any(parameter.device.type != "cuda" for parameter in parameters):
        raise SpeakerScoreError("all WavLM parameters must be CUDA-resident")
    return {
        "torch": torch,
        "extractor": extractor,
        "model": model,
        "device": device,
        "metadata": {
            "transformers_version": transformers.__version__,
            "torch_version": torch.__version__,
            "torch_cuda_version": str(torch.version.cuda),
            "device": str(device),
            "gpu_name": str(torch.cuda.get_device_name(device)),
        },
    }


def _embed(path: Path, runtime: dict[str, Any]) -> list[float]:
    values, _ = _load_audio(path)
    torch = runtime["torch"]
    encoded = runtime["extractor"](values, sampling_rate=SAMPLE_RATE_HZ, return_tensors="pt")
    inputs = {key: value.to(runtime["device"]) for key, value in encoded.items()}
    with torch.inference_mode():
        output = runtime["model"](**inputs)
        embedding = output.embeddings[0].float()
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=0)
    return [float(value) for value in embedding.cpu().tolist()]


def score_paths(
    *,
    deployed_commit: str,
    reference_path: Path,
    baseline_paths: dict[str, Path],
    soak_paths: dict[int, Path],
    generated_at: str | None = None,
) -> dict[str, Any]:
    if tuple(baseline_paths) != BASELINE_BUCKETS:
        raise SpeakerScoreError(f"baseline paths must be ordered as {list(BASELINE_BUCKETS)}")
    required_turns = set(EARLY_TURNS + MIDDLE_TURNS + LATE_TURNS)
    if set(soak_paths) != required_turns:
        raise SpeakerScoreError(f"soak paths must contain exactly turns {sorted(required_turns)}")

    runtime = _load_local_runtime()
    reference_embedding = _embed(reference_path, runtime)

    def score(path: Path) -> tuple[str, float]:
        return sha256_file(path), cosine_similarity(reference_embedding, _embed(path, runtime))

    baseline_scores = [(bucket, *score(baseline_paths[bucket])) for bucket in BASELINE_BUCKETS]
    early_scores = [(turn, *score(soak_paths[turn])) for turn in EARLY_TURNS]
    middle_scores = [(turn, *score(soak_paths[turn])) for turn in MIDDLE_TURNS]
    late_scores = [(turn, *score(soak_paths[turn])) for turn in LATE_TURNS]
    return build_score_payload(
        deployed_commit=deployed_commit,
        reference_sha256=sha256_file(reference_path),
        baseline_commit=deployed_commit,
        baseline_scores=baseline_scores,
        early_scores=early_scores,
        middle_scores=middle_scores,
        late_scores=late_scores,
        runtime_metadata=runtime["metadata"],
        generated_at=generated_at,
    )


def _assignment(value: str, *, numeric_key: bool) -> tuple[str | int, Path]:
    key, separator, path_text = value.partition("=")
    if not separator or not key or not path_text:
        raise argparse.ArgumentTypeError("expected KEY=PATH")
    try:
        parsed_key: str | int = int(key) if numeric_key else key
    except ValueError as exc:
        raise argparse.ArgumentTypeError("turn key must be an integer") from exc
    return parsed_key, Path(path_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployed-commit", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--baseline", action="append", default=[], help="short|medium|long=local-path")
    parser.add_argument("--soak", action="append", default=[], help="turn-number=local-path")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    args = parser.parse_args(argv)

    try:
        baseline_paths = dict(_assignment(value, numeric_key=False) for value in args.baseline)
        soak_paths = dict(_assignment(value, numeric_key=True) for value in args.soak)
        payload = score_paths(
            deployed_commit=args.deployed_commit,
            reference_path=args.reference,
            baseline_paths=baseline_paths,
            soak_paths=soak_paths,
            generated_at=args.generated_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, SpeakerScoreError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
