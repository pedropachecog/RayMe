"""Unit tests for tts_ttfa.py pure-Python helpers."""

from __future__ import annotations

import pytest

from tts_ttfa import compute_rtf, pick_v1_default, qwen_gate_disposition


def test_pick_v1_default_f5_wins_when_under_400ms() -> None:
    engines = {
        "f5": {"ttfa_ms": 320, "rtf": 0.08},
        "xtts": {"ttfa_ms": 180, "rtf": 0.3},
        "qwen3": {"ttfa_ms": 600, "rtf": 1.1},
    }

    assert pick_v1_default(engines) == "f5"


def test_pick_v1_default_xtts_wins_when_f5_misses() -> None:
    engines = {
        "f5": {"ttfa_ms": 550, "rtf": 0.15},
        "xtts": {"ttfa_ms": 180, "rtf": 0.3},
        "qwen3": {"ttfa_ms": 600, "rtf": 1.1},
    }

    assert pick_v1_default(engines) == "xtts"


def test_pick_v1_default_qwen_wins_when_only_budget_clearer() -> None:
    engines = {
        "f5": {"ttfa_ms": 550, "rtf": 0.15},
        "xtts": {"ttfa_ms": 450, "rtf": 0.4},
        "qwen3": {"ttfa_ms": 380, "rtf": 0.9},
    }

    assert pick_v1_default(engines) == "qwen3"


def test_pick_v1_default_best_ttfa_when_all_miss() -> None:
    engines = {
        "f5": {"ttfa_ms": 600},
        "xtts": {"ttfa_ms": 500},
        "qwen3": {"ttfa_ms": 700},
    }

    assert pick_v1_default(engines) == "xtts"


def test_pick_v1_default_none_when_all_errored() -> None:
    engines = {
        "f5": {"ttfa_ms": None},
        "xtts": {"ttfa_ms": None},
        "qwen3": {"ttfa_ms": None},
    }

    assert pick_v1_default(engines) is None


def test_qwen_gate_accepts_on_all_conditions() -> None:
    result = qwen_gate_disposition({"ttfa_ms": 380, "rtf": 0.9}, accent_ok=True)

    assert result == {"accepted": True, "reasons": ["ttfa_ok", "rtf_ok", "accent_ok"]}


def test_qwen_gate_rejects_on_ttfa() -> None:
    result = qwen_gate_disposition({"ttfa_ms": 500, "rtf": 0.9}, accent_ok=True)

    assert result == {"accepted": False, "reasons": ["ttfa_too_high"]}


def test_qwen_gate_rejects_when_accent_not_ok() -> None:
    result = qwen_gate_disposition({"ttfa_ms": 380, "rtf": 0.9}, accent_ok=False)

    assert result == {"accepted": False, "reasons": ["accent_drift_or_untested"]}


def test_compute_rtf() -> None:
    assert compute_rtf(audio_duration_s=5.0, synthesis_time_s=1.0) == pytest.approx(0.2)
