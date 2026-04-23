"""Pure helper tests for the VRAM soak probe."""

from __future__ import annotations

from vram_soak import (
    GROWTH_THRESHOLD_MB_PER_MIN,
    build_soak_result,
    detect_growth,
)


def _linear(points: list[int], start: float, slope_per_s: float) -> list[dict[str, float]]:
    return [{"t": float(point), "v": start + slope_per_s * point} for point in points]


def test_growth_flat() -> None:
    samples = [{"t": float(point), "v": 2000.0} for point in range(0, 1801, 60)]
    grew, slope = detect_growth(samples, window_s=1200)
    assert grew is False
    assert abs(slope) < 1.0


def test_growth_upward() -> None:
    samples = _linear(list(range(0, 1801, 60)), 2000.0, 100 / 60)
    grew, slope = detect_growth(samples, window_s=1200)
    assert grew is True
    assert slope > GROWTH_THRESHOLD_MB_PER_MIN


def test_growth_downward() -> None:
    samples = _linear(list(range(0, 1801, 60)), 3000.0, -50 / 60)
    grew, slope = detect_growth(samples, window_s=1200)
    assert grew is False
    assert slope < 0


def test_growth_within_noise_tolerance() -> None:
    samples = _linear(list(range(0, 1801, 60)), 2000.0, 20 / 60)
    grew, slope = detect_growth(samples, window_s=1200)
    assert grew is False
    assert 15 < slope < 25


def test_build_soak_result_schema() -> None:
    samples = [
        {"t": 0.0, "v": 4500.0, "allocated_mb": 4200.0, "peak_allocated_mb": 4400.0, "used_mb_nvml": 5000.0},
        {"t": 600.0, "v": 4600.0, "allocated_mb": 4250.0, "peak_allocated_mb": 4500.0, "used_mb_nvml": 5100.0},
        {"t": 1200.0, "v": 4700.0, "allocated_mb": 4300.0, "peak_allocated_mb": 4600.0, "used_mb_nvml": 5200.0},
        {"t": 1800.0, "v": 4800.0, "allocated_mb": 4350.0, "peak_allocated_mb": 4700.0, "used_mb_nvml": 5300.0},
    ]
    result = build_soak_result("f5", samples, cycles_completed=180)

    for key in (
        "engine",
        "peak_vram_mb",
        "growth_detected",
        "growth_slope_mb_per_min",
        "cycles_completed",
        "duration_s",
        "samples",
        "fits_3060_budget",
    ):
        assert key in result, f"missing key {key}"

    assert result["engine"] == "f5"
    assert result["peak_vram_mb"] == 4800.0
    assert result["fits_3060_budget"] is True
