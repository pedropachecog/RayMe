"""Unit tests for tts_ttfa.py pure-Python helpers."""

from __future__ import annotations

import pytest

from tts_ttfa import (
    build_attention_matrix,
    compute_rtf,
    pick_v1_default,
    qwen_gate_disposition,
    qwen_optimization_metadata,
)


def test_pick_v1_default_fastest_budget_clearer_wins() -> None:
    engines = {
        "f5": {"ttfa_ms": 320, "rtf": 0.08},
        "xtts": {"ttfa_ms": 180, "rtf": 0.3},
        "qwen3": {"ttfa_ms": 600, "rtf": 1.1},
    }

    assert pick_v1_default(engines) == "xtts"


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


def test_pick_v1_default_new_engine_can_win() -> None:
    engines = {
        "f5": {"ttfa_ms": 550, "rtf": 0.15},
        "xtts": {"ttfa_ms": 450, "rtf": 0.4},
        "luxtts": {"ttfa_ms": 210, "rtf": 0.12},
        "chatterbox_turbo": {"ttfa_ms": 260, "rtf": 0.2},
        "tada_1b": {"ttfa_ms": 900, "rtf": 0.7},
    }

    assert pick_v1_default(engines) == "luxtts"


def test_pick_v1_default_best_ttfa_when_all_miss() -> None:
    engines = {
        "f5": {"ttfa_ms": 600},
        "xtts": {"ttfa_ms": 500},
        "luxtts": {"ttfa_ms": 430},
        "qwen3": {"ttfa_ms": 700},
    }

    assert pick_v1_default(engines) == "luxtts"


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


def test_qwen_optimization_metadata_marks_eager_when_fa2_missing() -> None:
    metadata = qwen_optimization_metadata(
        {"installed": False, "version": None, "reason": "ImportError('flash_attn')"}
    )

    assert metadata["optimization_backend"] == "eager"
    assert metadata["optimization_modes"]["eager"]["status"] == "measured"
    assert metadata["optimization_modes"]["flash_attention_2"]["status"] == "unavailable"
    assert metadata["unsupported_optimization_backends"] == ["sdpa"]


def test_qwen_optimization_metadata_marks_fa2_when_available() -> None:
    metadata = qwen_optimization_metadata(
        {"installed": True, "version": "2.8.3", "reason": "import_ok"}
    )

    assert metadata["optimization_backend"] == "flash_attention_2"
    assert metadata["optimization_modes"]["flash_attention_2"]["status"] == "measured"
    assert metadata["optimization_modes"]["flash_attention_2"]["version"] == "2.8.3"


def test_build_attention_matrix_preserves_backend_labels() -> None:
    engines = {
        "f5": {
            "optimization_backend": "not_applicable",
            "optimization_backend_reason": "static",
            "supported_optimization_backends": ["not_applicable"],
            "optimization_modes": {
                "eager": {"status": "not_applicable"},
                "sdpa": {"status": "not_applicable"},
                "flash_attention_2": {"status": "not_applicable"},
            },
            "mode": "simulated_streaming",
            "streaming_support": "simulated",
            "true_streaming": False,
            "ttfa_ms": 530.3,
            "rtf": 0.398,
            "peak_vram_mb": 1990.2,
        },
        "qwen3": {
            "optimization_backend": "eager",
            "optimization_backend_reason": "fa2 missing",
            "supported_optimization_backends": ["eager", "flash_attention_2"],
            "unsupported_optimization_backends": ["sdpa"],
            "optimization_modes": {
                "eager": {"status": "measured"},
                "sdpa": {"status": "not_supported"},
                "flash_attention_2": {"status": "unavailable"},
            },
            "mode": "simulated_streaming_text",
            "streaming_support": "simulated",
            "true_streaming": False,
            "ttfa_ms": 7527.3,
            "rtf": 3.035,
            "peak_vram_mb": 2520.1,
            "variant": "0.6B-Base",
            "flash_attn_probe": {"installed": False},
        },
    }

    matrix = build_attention_matrix(
        engines,
        {
            "installed": False,
            "failure_reason": "windows_build_compile_error",
            "build_duration_s": 56.1,
            "qwen17b_recommended": False,
        },
    )

    assert matrix["engines"]["f5"]["measured_backend"] == "not_applicable"
    assert matrix["engines"]["qwen3"]["measured_backend"] == "eager"
    assert matrix["fa2_install"]["failure_reason"] == "windows_build_compile_error"
