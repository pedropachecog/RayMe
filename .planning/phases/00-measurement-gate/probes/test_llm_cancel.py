"""Unit tests for llm_cancel.py parser and summary helpers."""

from __future__ import annotations

from llm_cancel import compute_p50_cancel_ms, first_idle_ms, parse_nvidia_smi_gpu_util


def test_parse_nvidia_smi_simple() -> None:
    assert parse_nvidia_smi_gpu_util("45\n") == 45


def test_parse_nvidia_smi_whitespace() -> None:
    assert parse_nvidia_smi_gpu_util("  12  \n") == 12


def test_parse_nvidia_smi_with_percent_suffix() -> None:
    assert parse_nvidia_smi_gpu_util("23 %\n") == 23


def test_first_idle_ms_detects_idle() -> None:
    samples = [
        {"t": 0.0, "util": 95},
        {"t": 0.1, "util": 80},
        {"t": 0.2, "util": 10},
        {"t": 0.3, "util": 2},
    ]
    assert first_idle_ms(samples) == 300.0


def test_first_idle_ms_returns_none_if_never_idle() -> None:
    samples = [{"t": 0.0, "util": 95}, {"t": 0.1, "util": 80}]
    assert first_idle_ms(samples) is None


def test_compute_p50_median() -> None:
    trials = [
        {"cancel_to_idle_ms": 120},
        {"cancel_to_idle_ms": 150},
        {"cancel_to_idle_ms": 180},
        {"cancel_to_idle_ms": 200},
        {"cancel_to_idle_ms": 250},
    ]
    assert compute_p50_cancel_ms(trials) == 180.0


def test_compute_p50_skips_none() -> None:
    trials = [{"cancel_to_idle_ms": 120}, {"cancel_to_idle_ms": None}]
    assert compute_p50_cancel_ms(trials) == 120.0


def test_compute_p50_all_none() -> None:
    trials = [{"cancel_to_idle_ms": None}, {"cancel_to_idle_ms": None}]
    assert compute_p50_cancel_ms(trials) is None
