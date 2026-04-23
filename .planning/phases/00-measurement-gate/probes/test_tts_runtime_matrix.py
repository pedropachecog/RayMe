"""Pure helper tests for the runtime-matrix harness."""

from __future__ import annotations

from tts_runtime_matrix import (
    build_recommendations,
    build_row,
    choose_fastest,
    choose_qwen_backend,
    choose_xtts_runtime,
    diff_status,
)


def test_build_row_preserves_core_fields() -> None:
    row = build_row(
        engine="f5",
        runtime="wsl_python",
        host_account="rayme-pmpg",
        scenario="short_ack",
        backend="not_applicable",
        source="remote.json",
        metrics={"ttfa_ms": 590.2, "rtf": 0.443, "peak_vram_mb": 1988.7},
    )

    assert row["engine"] == "f5"
    assert row["runtime"] == "wsl_python"
    assert row["ttfa_ms"] == 590.2
    assert row["status"] == "measured"


def test_choose_fastest_prefers_lower_ttfa_then_rtf() -> None:
    winner = choose_fastest(
        [
            {"runtime": "windows_native", "status": "measured", "ttfa_ms": 520.0, "rtf": 0.40},
            {"runtime": "wsl_python", "status": "measured", "ttfa_ms": 520.0, "rtf": 0.38},
            {"runtime": "wsl_triton", "status": "measured", "ttfa_ms": 1800.0, "rtf": 1.12},
        ]
    )

    assert winner is not None
    assert winner["runtime"] == "wsl_python"


def test_diff_status_marks_no_effect_when_delta_small() -> None:
    assert diff_status(
        {"ttfa_ms": 525.0, "rtf": 0.60},
        {"ttfa_ms": 540.0, "rtf": 0.57},
    ) == "no_effect_observed"


def test_choose_xtts_runtime_handles_unavailable_deepspeed() -> None:
    runtime, reason = choose_xtts_runtime(
        {"backend": "baseline", "status": "measured", "ttfa_ms": 520.0, "rtf": 0.60},
        {"backend": "deepspeed", "status": "not_available", "reason": "init failed"},
    )

    assert runtime == "wsl_python_baseline"
    assert "init failed" in reason


def test_choose_qwen_backend_prefers_fa2_when_faster() -> None:
    backend, reason = choose_qwen_backend(
        {"backend": "eager", "status": "measured", "ttfa_ms": 5000.0, "rtf": 3.0},
        {"backend": "flash_attention_2", "status": "measured", "ttfa_ms": 3200.0, "rtf": 2.0},
    )

    assert backend == "flash_attention_2"
    assert "faster" in reason


def test_build_recommendations_uses_row_statuses() -> None:
    rows = [
        build_row(
            engine="f5",
            runtime="windows_native",
            host_account="rayme-ssh",
            scenario="short_ack",
            backend="not_applicable",
            source="a.json",
            metrics={"ttfa_ms": 521.8, "rtf": 0.391},
        ),
        build_row(
            engine="f5",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="not_applicable",
            source="b.json",
            metrics={"ttfa_ms": 590.2, "rtf": 0.443},
        ),
        build_row(
            engine="f5",
            runtime="windows_native",
            host_account="rayme-ssh",
            scenario="longform",
            backend="not_applicable",
            source="c.json",
            metrics={"ttfa_ms": 528.4, "rtf": 0.101},
        ),
        build_row(
            engine="f5",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="longform",
            backend="not_applicable",
            source="d.json",
            metrics={"ttfa_ms": 640.0, "rtf": 0.110},
        ),
        build_row(
            engine="xtts",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="baseline",
            source="e.json",
            metrics={"ttfa_ms": 524.6, "rtf": 0.595},
        ),
        build_row(
            engine="xtts",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="deepspeed",
            source="f.json",
            metrics={"ttfa_ms": 530.0, "rtf": 0.590},
            status="no_effect_observed",
        ),
        build_row(
            engine="qwen3",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="eager",
            source="g.json",
            metrics={"ttfa_ms": 4500.0, "rtf": 3.0},
        ),
        build_row(
            engine="qwen3",
            runtime="wsl_python",
            host_account="rayme-pmpg",
            scenario="short_ack",
            backend="flash_attention_2",
            source="h.json",
            metrics={},
            status="not_available",
            reason="kernel mismatch",
        ),
    ]

    recommendations = build_recommendations(rows)

    assert recommendations["f5_short_ack_winner"] == "windows_native"
    assert recommendations["f5_longform_winner"] == "windows_native"
    assert recommendations["xtts_recommended_runtime"] == "wsl_python_baseline"
    assert recommendations["qwen_recommended_backend"] == "eager"
