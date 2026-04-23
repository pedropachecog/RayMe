from __future__ import annotations

from tts_scenario_matrix import ScenarioSpec, build_result_row, build_summary


def test_build_result_row_excludes_model_load_from_request_metrics() -> None:
    scenario = ScenarioSpec(
        name="short_reply",
        text="Short test reply.",
        description="Short reply",
    )
    row = build_result_row(
        engine="luxtts",
        runtime="windows_native",
        host_account="rayme-ssh",
        profile="optimized",
        scenario=scenario,
        backend="zipvoice_pytorch",
        mode="non_streaming_clone",
        streaming_support="none",
        true_streaming=False,
        model_load_ms=1000.0,
        warmup_ms=250.0,
        cached_prompt_build_ms=90.0,
        request_prompt_prep_ms=0.0,
        generate_ttfa_ms=320.0,
        generate_total_ms=320.0,
        audio_duration_s=1.6,
        peak_vram_mb=900.0,
        sample_rate=48000,
        output_wav=None,
        optimizations_applied=["prompt_cache"],
        optimization_notes="Cached prompt.",
    )

    assert row["model_load_ms"] == 1000.0
    assert row["request_ttfa_ms"] == 320.0
    assert row["request_total_ms"] == 320.0
    assert row["generation_rtf"] == 0.2
    assert row["request_rtf"] == 0.2


def test_build_result_row_includes_request_prompt_prep() -> None:
    scenario = ScenarioSpec(
        name="medium_reply",
        text="A somewhat longer reply for testing.",
        description="Medium reply",
    )
    row = build_result_row(
        engine="xtts",
        runtime="wsl_python",
        host_account="rayme-pmpg",
        profile="baseline",
        scenario=scenario,
        backend="native_stream",
        mode="streaming",
        streaming_support="native",
        true_streaming=True,
        model_load_ms=2100.0,
        warmup_ms=400.0,
        cached_prompt_build_ms=None,
        request_prompt_prep_ms=180.0,
        generate_ttfa_ms=240.0,
        generate_total_ms=600.0,
        audio_duration_s=2.0,
        peak_vram_mb=1900.0,
        sample_rate=24000,
        output_wav=None,
        optimizations_applied=[],
        optimization_notes="Fresh conditioning.",
    )

    assert row["request_ttfa_ms"] == 420.0
    assert row["request_total_ms"] == 780.0
    assert row["generation_rtf"] == 0.3
    assert row["request_rtf"] == 0.39


def test_build_summary_picks_fastest_measured_rows() -> None:
    scenario = ScenarioSpec(
        name="short_reply",
        text="Short reply.",
        description="Short reply",
    )
    faster = build_result_row(
        engine="f5",
        runtime="windows_native",
        host_account="rayme-ssh",
        profile="optimized",
        scenario=scenario,
        backend="native_pytorch_chunked",
        mode="simulated_streaming",
        streaming_support="simulated",
        true_streaming=False,
        model_load_ms=100.0,
        warmup_ms=50.0,
        cached_prompt_build_ms=40.0,
        request_prompt_prep_ms=0.0,
        generate_ttfa_ms=200.0,
        generate_total_ms=300.0,
        audio_duration_s=2.0,
        peak_vram_mb=1900.0,
        sample_rate=24000,
        output_wav=None,
        optimizations_applied=["prepared_ref_cache", "text_chunking"],
        optimization_notes="Optimized.",
    )
    slower = build_result_row(
        engine="xtts",
        runtime="windows_native",
        host_account="rayme-ssh",
        profile="optimized",
        scenario=scenario,
        backend="native_stream",
        mode="streaming",
        streaming_support="native",
        true_streaming=True,
        model_load_ms=200.0,
        warmup_ms=50.0,
        cached_prompt_build_ms=50.0,
        request_prompt_prep_ms=0.0,
        generate_ttfa_ms=260.0,
        generate_total_ms=280.0,
        audio_duration_s=2.0,
        peak_vram_mb=1900.0,
        sample_rate=24000,
        output_wav=None,
        optimizations_applied=["conditioning_cache"],
        optimization_notes="Optimized.",
    )
    failed = dict(slower)
    failed["status"] = "failed"
    failed["request_ttfa_ms"] = None
    failed["request_total_ms"] = None

    summary = build_summary([slower, faster, failed])

    assert summary["best_request_ttfa"]["short_reply"]["engine"] == "f5"
    assert summary["best_request_ttfa"]["short_reply"]["profile"] == "optimized"
    assert summary["best_request_total"]["short_reply"]["engine"] == "xtts"
