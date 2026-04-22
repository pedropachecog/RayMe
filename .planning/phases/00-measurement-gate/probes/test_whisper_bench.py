"""Unit tests for whisper_bench.py pure-Python helpers."""

from __future__ import annotations

import pytest

from whisper_bench import build_result, compute_wer, pick_default


def test_wer_perfect_match() -> None:
    assert compute_wer("hello world", "hello world") == pytest.approx(0.0)


def test_wer_one_substitution() -> None:
    assert compute_wer("hello world", "hello mars") == pytest.approx(0.5)


def test_wer_ignores_punctuation() -> None:
    assert compute_wer("Hello, world!", "hello world") == pytest.approx(0.0)


def test_wer_ignores_case() -> None:
    assert compute_wer("Hello World", "hello world") == pytest.approx(0.0)


def test_build_result_schema() -> None:
    rungs = [
        {
            "model": "distil-large-v3",
            "compute_type": "int8_float16",
            "wer": 0.11,
            "p50_latency_ms": 2500,
            "p95_latency_ms": 3100,
            "peak_vram_mb": 1500,
            "hypothesis": "...",
        },
        {
            "model": "large-v3-turbo",
            "compute_type": "int8_float16",
            "wer": 0.10,
            "p50_latency_ms": 2800,
            "p95_latency_ms": 3400,
            "peak_vram_mb": 1800,
            "hypothesis": "...",
        },
        {
            "model": "large-v3",
            "compute_type": "float16",
            "wer": 0.09,
            "p50_latency_ms": 5200,
            "p95_latency_ms": 6000,
            "peak_vram_mb": 3200,
            "hypothesis": "...",
        },
    ]

    result = build_result(rungs)

    assert "rungs" in result
    assert len(result["rungs"]) == 3
    assert result["default_rung"] == "distil-large-v3"
    assert sum(1 for rung in result["rungs"] if rung.get("default")) == 1

    required = (
        "model",
        "compute_type",
        "wer",
        "p50_latency_ms",
        "p95_latency_ms",
        "peak_vram_mb",
        "hypothesis",
        "default",
    )
    for rung in result["rungs"]:
        for key in required:
            assert key in rung


def test_pick_default_distil_wins_when_within_2pp() -> None:
    rungs = [
        {"model": "distil-large-v3", "wer": 0.11},
        {"model": "large-v3-turbo", "wer": 0.10},
        {"model": "large-v3", "wer": 0.095},
    ]

    assert pick_default(rungs) == "distil-large-v3"


def test_pick_default_promotes_when_distil_falls_behind() -> None:
    rungs = [
        {"model": "distil-large-v3", "wer": 0.15},
        {"model": "large-v3-turbo", "wer": 0.095},
        {"model": "large-v3", "wer": 0.090},
    ]

    assert pick_default(rungs) == "large-v3-turbo"


def test_pick_default_falls_through_to_fp16_when_all_quantized_bad() -> None:
    rungs = [
        {"model": "distil-large-v3", "wer": 0.17},
        {"model": "large-v3-turbo", "wer": 0.15},
        {"model": "large-v3", "wer": 0.08},
    ]

    assert pick_default(rungs) == "large-v3"
