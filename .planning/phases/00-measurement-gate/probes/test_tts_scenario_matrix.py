from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tts_scenario_matrix import (
    ENGINE_CHUNK_LIMITS,
    ENGINE_ORDER,
    MODEL_ID_VOXCPM2,
    ScenarioSpec,
    _chunk_playback_metadata,
    _estimate_tts_tokens,
    _voxcpm2_model_sample_rate,
    _split_sentence_units,
    build_chunk_plan,
    build_result_row,
    build_summary,
    scenario_specs,
)


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


def test_sentence_splitter_ignores_common_abbreviations() -> None:
    text = "Dr. Vale checked the line. It worked, e.g. on the second pass. Done?"

    assert _split_sentence_units(text) == [
        "Dr. Vale checked the line.",
        "It worked, e.g. on the second pass.",
        "Done?",
    ]


def test_xtts_chunk_plan_stays_under_conservative_token_cap() -> None:
    text = (
        "First, keep this opening sentence short. "
        + " ".join(f"word{i}" for i in range(150))
        + ". Final sentence lands cleanly."
    )

    plan = build_chunk_plan("xtts", text)

    assert len(plan.chunks) > 1
    assert plan.max_estimated_tokens < 400
    assert all(_estimate_tts_tokens(chunk) < plan.max_estimated_tokens for chunk in plan.chunks)
    assert plan.chunks[0] == "First, keep this opening sentence short."


def test_chunk_playback_metadata_tracks_hidden_generation_and_gaps() -> None:
    plan = build_chunk_plan(
        "f5",
        "First sentence is quick. Second sentence is long enough to matter.",
    )

    metadata = _chunk_playback_metadata(
        plan=plan,
        chunk_ttfa_ms=[200.0, 500.0],
        chunk_total_ms=[400.0, 900.0],
        chunk_audio_duration_s=[1.2, 0.8],
    )

    assert metadata["chunk_audio_ready_offsets_ms"] == [200.0, 900.0]
    assert metadata["inter_chunk_gap_ms"] == [0.0]
    assert metadata["stitched_playback_ms"] == 2200.0


def test_voxcpm2_chunk_plan_uses_shared_planner() -> None:
    text = (
        "First, answer quickly so the call feels alive. "
        + " ".join(f"voxcpm2word{i}" for i in range(130))
        + ". Finish on a natural sentence boundary."
    )

    plan = build_chunk_plan("voxcpm2", text)

    assert "voxcpm2" in ENGINE_CHUNK_LIMITS
    assert plan.engine == "voxcpm2"
    assert plan.strategy == "sentence_boundary_token_cap_v1"
    assert len(plan.chunks) > 1
    assert all(_estimate_tts_tokens(chunk) < plan.max_estimated_tokens for chunk in plan.chunks)


def test_voxcpm2_scenario_rows_require_short_medium_long_outputs() -> None:
    scenarios = [spec for spec in scenario_specs() if spec.name in {"short_reply", "medium_reply", "long_reply"}]
    rows = [
        build_result_row(
            engine="voxcpm2",
            runtime="omen_cuda",
            host_account="rayme-pmpg",
            profile="optimized",
            scenario=scenario,
            backend="voxcpm_python_api",
            mode="shared_chunked_playback",
            streaming_support="simulated",
            true_streaming=False,
            model_load_ms=1200.0,
            warmup_ms=300.0,
            cached_prompt_build_ms=50.0,
            request_prompt_prep_ms=0.0,
            generate_ttfa_ms=250.0,
            generate_total_ms=900.0,
            audio_duration_s=4.0,
            peak_vram_mb=4000.0,
            sample_rate=48000,
            output_wav=None,
            optimizations_applied=["shared_chunk_planner"],
            optimization_notes="VoxCPM2 rows must use the same RayMe chunk planner evidence schema.",
        )
        for scenario in scenarios
    ]

    assert [row["scenario"] for row in rows] == ["short_reply", "medium_reply", "long_reply"]
    required_fields = {
        "request_ttfa_ms",
        "request_total_ms",
        "request_rtf",
        "generation_rtf",
        "stitched_playback_ms",
        "max_inter_chunk_gap_ms",
        "peak_vram_mb",
        "sample_path",
        "backend",
        "mode",
        "optimizations_applied",
    }
    for row in rows:
        assert required_fields <= row.keys()


def test_voxcpm2_promotion_summary_compares_against_f5() -> None:
    scenario = ScenarioSpec(
        name="short_reply",
        text="Short reply.",
        description="Short reply",
    )
    f5_row = build_result_row(
        engine="f5",
        runtime="windows_native",
        host_account="rayme-ssh",
        profile="optimized",
        scenario=scenario,
        backend="native_pytorch_chunked",
        mode="shared_chunked_playback",
        streaming_support="simulated",
        true_streaming=False,
        model_load_ms=100.0,
        warmup_ms=50.0,
        cached_prompt_build_ms=40.0,
        request_prompt_prep_ms=0.0,
        generate_ttfa_ms=220.0,
        generate_total_ms=320.0,
        audio_duration_s=2.0,
        peak_vram_mb=1900.0,
        sample_rate=24000,
        output_wav=None,
        optimizations_applied=["prepared_ref_cache", "shared_chunk_planner"],
        optimization_notes="Current F5 call-feel path.",
    )
    voxcpm2_row = build_result_row(
        engine="voxcpm2",
        runtime="omen_cuda",
        host_account="rayme-pmpg",
        profile="optimized",
        scenario=scenario,
        backend="voxcpm_python_api",
        mode="shared_chunked_playback",
        streaming_support="simulated",
        true_streaming=False,
        model_load_ms=100.0,
        warmup_ms=50.0,
        cached_prompt_build_ms=40.0,
        request_prompt_prep_ms=0.0,
        generate_ttfa_ms=210.0,
        generate_total_ms=310.0,
        audio_duration_s=2.0,
        peak_vram_mb=3600.0,
        sample_rate=48000,
        output_wav=None,
        optimizations_applied=["shared_chunk_planner"],
        optimization_notes="Candidate path must beat F5 before promotion.",
    )

    summary = build_summary([f5_row, voxcpm2_row])

    assert "f5" in ENGINE_ORDER
    assert "voxcpm2" in ENGINE_ORDER
    assert summary["promotion_comparison"]["baseline_engine"] == "f5"
    assert summary["promotion_comparison"]["candidate_engine"] == "voxcpm2"


def test_voxcpm2_runner_contract_uses_standard_python_cuda_path() -> None:
    source = Path(__file__).with_name("tts_scenario_matrix.py").read_text(encoding="utf-8")

    assert MODEL_ID_VOXCPM2 == "openbmb/VoxCPM2"
    assert 'from_pretrained(MODEL_ID_VOXCPM2, load_denoiser=False, device="cuda")' in source
    assert 'backend="standard_python_api"' in source
    assert 'mode="standard_python_streaming_collected"' in source


def test_voxcpm2_sample_rate_comes_from_runtime_model() -> None:
    class FakeTtsModel:
        sample_rate = 48_000

    class FakeRuntime:
        tts_model = FakeTtsModel()

    assert _voxcpm2_model_sample_rate(FakeRuntime()) == 48_000
