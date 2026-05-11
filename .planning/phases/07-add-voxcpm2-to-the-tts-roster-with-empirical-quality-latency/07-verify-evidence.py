#!/usr/bin/env python3
"""Verify Phase 07 VoxCPM2 evidence artifact contracts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

PHASE_DIR = Path(__file__).resolve().parent
MANUAL_QUALITY = PHASE_DIR / "MANUAL-QUALITY.csv"
OMEN_EVIDENCE = PHASE_DIR / "07-OMEN-EVIDENCE.md"
RESULTS_README = PHASE_DIR / "results" / "README.md"
RESULTS_AUDIO_DIR = PHASE_DIR / "results" / "audio"
MATRIX_JSON = PHASE_DIR / "results" / "voxcpm2-scenario-matrix.json"
MATRIX_CSV = PHASE_DIR / "results" / "voxcpm2-scenario-matrix.csv"
VRAM_SOAK_JSON = PHASE_DIR / "results" / "voxcpm2-vram-soak.json"
CALL_FLOW_JSON = PHASE_DIR / "results" / "voxcpm2-call-flow.json"
RUNTIME_SMOKE_JSON = PHASE_DIR / "results" / "voxcpm2-runtime-smoke.json"

MANUAL_QUALITY_HEADER = [
    "engine",
    "scenario",
    "sample_path",
    "listener",
    "transcript",
    "intelligibility_1_5",
    "voice_match_1_5",
    "accent_preservation_1_5",
    "prosody_1_5",
    "leakage_artifacts_1_5",
    "mumbling_artifacts_1_5",
    "pass",
    "notes",
]

REQUIRED_PATH_DECLARATIONS = [
    "results/voxcpm2-scenario-matrix.json",
    "results/voxcpm2-scenario-matrix.csv",
    "results/audio/",
    "results/voxcpm2-vram-soak.json",
    "results/voxcpm2-call-flow.json",
    "results/voxcpm2-runtime-smoke.json",
]

OMEN_REQUIRED_STRINGS = [
    "scripts/deploy-omen.sh",
    "voxcpm==2.0.2",
    "openbmb/VoxCPM2",
    'device="cuda"',
    "Commit SHA",
    "CUDA torch version",
    "Model cache path",
    "Output sample rate",
    "Before VoxCPM2 load",
    "After VoxCPM2 load",
    "Sanitized failure category",
]

SCENARIOS = {"short_reply", "medium_reply", "long_reply"}
MATRIX_REQUIRED_FIELDS = {
    "engine",
    "scenario",
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
RUNTIME_SMOKE_REQUIRED_FIELDS = {
    "package",
    "model_id",
    "device",
    "runtime_sample_rate",
    "cpu_fallback_detected",
}
VRAM_SOAK_REQUIRED_FIELDS = {
    "peak_vram_mb",
    "vram_budget_mb",
    "within_11gb_budget",
}
CALL_FLOW_REQUIRED_FIELDS = {
    "engine",
    "preview_result",
    "test_play_result",
    "call_speak_result",
    "call_audio_enqueued",
    "saved_ai_audio_path",
    "sanitized_failure_category",
    "warm_call_ttfa_ms",
    "f5_warm_call_ttfa_ms",
}
ACCEPTED_FAILURE_CATEGORIES = {
    "none",
    "tts_failed",
    "call_tts_failed",
    "voxcpm2_unavailable",
    "runtime_unavailable",
    "validation_failed",
}
ACCEPTED_FINAL_OUTCOMES = {
    "promoted",
    "selectable_with_caveats",
    "visible_unavailable",
    "rejected_from_runtime_loading",
}
MAX_PRODUCTION_VRAM_MB = 11 * 1024


class EvidenceError(Exception):
    """Evidence contract failure."""


def _read_text(path: Path) -> str:
    if not path.exists():
        raise EvidenceError(f"missing required file: {path.relative_to(PHASE_DIR)}")
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON in {path.relative_to(PHASE_DIR)}: {exc}") from exc


def _require_fields(payload: dict[str, Any], required: set[str], *, label: str) -> None:
    missing = required - set(payload)
    if missing:
        raise EvidenceError(f"{label} missing fields: {sorted(missing)}")


def _require_number(value: Any, *, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise EvidenceError(f"{label} must be a finite number")
    return float(value)


def _verify_relative_audio_path(value: Any, *, label: str, must_exist: bool = True) -> None:
    if not isinstance(value, str) or not value.startswith("results/audio/"):
        raise EvidenceError(f"{label} must point under results/audio/: {value!r}")
    audio_path = PHASE_DIR / value
    try:
        audio_path.resolve().relative_to(RESULTS_AUDIO_DIR.resolve())
    except ValueError as exc:
        raise EvidenceError(f"{label} escapes results/audio/: {value!r}") from exc
    if must_exist and not audio_path.is_file():
        raise EvidenceError(f"{label} does not exist: {value}")


def _verify_no_raw_error_leak(value: Any, *, label: str) -> None:
    text = json.dumps(value, sort_keys=True)
    forbidden = ["Traceback", "File \"", "C:\\", "/home/", ".cache", "huggingface", "openbmb/VoxCPM2"]
    leaked = [pattern for pattern in forbidden if pattern in text]
    if leaked:
        raise EvidenceError(f"{label} appears to expose raw runtime details: {leaked}")


def _verify_manual_quality_header() -> None:
    with MANUAL_QUALITY.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
    if header != MANUAL_QUALITY_HEADER:
        raise EvidenceError(
            "MANUAL-QUALITY.csv header mismatch: "
            f"expected {MANUAL_QUALITY_HEADER!r}, got {header!r}"
        )


def _verify_path_declarations() -> None:
    readme = _read_text(RESULTS_README)
    omen = _read_text(OMEN_EVIDENCE)
    for declaration in REQUIRED_PATH_DECLARATIONS:
        if declaration not in readme:
            raise EvidenceError(f"results README does not declare {declaration}")
        if declaration not in omen:
            raise EvidenceError(f"OMEN evidence template does not declare {declaration}")
    if not RESULTS_AUDIO_DIR.is_dir():
        raise EvidenceError("results/audio/ directory is missing")


def verify_contract_only() -> None:
    _verify_manual_quality_header()
    _verify_path_declarations()
    omen = _read_text(OMEN_EVIDENCE)
    for required in OMEN_REQUIRED_STRINGS:
        if required not in omen:
            raise EvidenceError(f"OMEN evidence template missing {required!r}")


def _matrix_rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    elif isinstance(payload, dict) and isinstance(payload.get("matrix"), list):
        rows = payload["matrix"]
    else:
        raise EvidenceError("matrix JSON must be a list, or an object with rows/matrix list")
    if not all(isinstance(row, dict) for row in rows):
        raise EvidenceError("matrix JSON rows must be objects")
    return rows


def verify_matrix_only() -> None:
    matrix_payload = _read_json(MATRIX_JSON)
    rows = _matrix_rows_from_json(matrix_payload)
    voxcpm2_rows = [row for row in rows if row.get("engine") == "voxcpm2"]
    scenarios = {str(row.get("scenario")) for row in voxcpm2_rows}
    missing = SCENARIOS - scenarios
    if missing:
        raise EvidenceError(f"missing VoxCPM2 scenario rows: {sorted(missing)}")
    for row in voxcpm2_rows:
        missing_fields = MATRIX_REQUIRED_FIELDS - set(row)
        if missing_fields:
            raise EvidenceError(
                f"VoxCPM2 {row.get('scenario')} row missing fields: {sorted(missing_fields)}"
            )
        sample_path = row.get("sample_path")
        _verify_relative_audio_path(sample_path, label=f"matrix {row.get('scenario')} sample_path")

    f5_rows = [row for row in rows if row.get("engine") == "f5"]
    f5_scenarios = {str(row.get("scenario")) for row in f5_rows}
    missing_f5 = SCENARIOS - f5_scenarios
    if missing_f5:
        raise EvidenceError(f"missing F5 comparator rows: {sorted(missing_f5)}")

    summary = matrix_payload.get("summary") if isinstance(matrix_payload, dict) else None
    comparison = summary.get("promotion_comparison") if isinstance(summary, dict) else None
    if not isinstance(comparison, dict):
        raise EvidenceError("matrix summary missing promotion_comparison")
    if comparison.get("baseline_engine") != "f5" or comparison.get("candidate_engine") != "voxcpm2":
        raise EvidenceError("promotion_comparison must compare baseline f5 against candidate voxcpm2")

    if not MATRIX_CSV.exists():
        raise EvidenceError("missing scenario matrix CSV")
    with MATRIX_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        csv_fields = set(reader.fieldnames or [])
    missing_csv_fields = MATRIX_REQUIRED_FIELDS - csv_fields
    if missing_csv_fields:
        raise EvidenceError(f"matrix CSV missing fields: {sorted(missing_csv_fields)}")


def verify_runtime_only() -> None:
    smoke = _read_json(RUNTIME_SMOKE_JSON)
    soak = _read_json(VRAM_SOAK_JSON)
    if not isinstance(smoke, dict):
        raise EvidenceError("runtime smoke JSON must be an object")
    if not isinstance(soak, dict):
        raise EvidenceError("VRAM soak JSON must be an object")

    _require_fields(smoke, RUNTIME_SMOKE_REQUIRED_FIELDS, label="runtime smoke JSON")
    if smoke.get("package") != "voxcpm==2.0.2":
        raise EvidenceError('runtime smoke package must be "voxcpm==2.0.2"')
    if smoke.get("model_id") != "openbmb/VoxCPM2":
        raise EvidenceError('runtime smoke model_id must be "openbmb/VoxCPM2"')
    if smoke.get("device") != "cuda":
        raise EvidenceError('runtime smoke device must be "cuda"')
    if smoke.get("cpu_fallback_detected") is not False:
        raise EvidenceError("runtime smoke cpu_fallback_detected must be false")
    sample_rate = _require_number(smoke.get("runtime_sample_rate"), label="runtime_sample_rate")
    if sample_rate <= 0:
        raise EvidenceError("runtime_sample_rate must be positive")

    _require_fields(soak, VRAM_SOAK_REQUIRED_FIELDS, label="VRAM soak JSON")
    peak_vram_mb = _require_number(soak.get("peak_vram_mb"), label="peak_vram_mb")
    budget_mb = _require_number(soak.get("vram_budget_mb"), label="vram_budget_mb")
    if budget_mb > MAX_PRODUCTION_VRAM_MB:
        raise EvidenceError(f"vram_budget_mb must be <= {MAX_PRODUCTION_VRAM_MB}")
    if soak.get("within_11gb_budget") is not True:
        raise EvidenceError("within_11gb_budget must be true")
    if peak_vram_mb > budget_mb:
        raise EvidenceError("peak_vram_mb exceeds vram_budget_mb")


def verify_call_flow_only() -> None:
    payload = _read_json(CALL_FLOW_JSON)
    if not isinstance(payload, dict):
        raise EvidenceError("call-flow JSON must be an object")
    _require_fields(payload, CALL_FLOW_REQUIRED_FIELDS, label="call-flow JSON")
    if payload.get("engine") != "voxcpm2":
        raise EvidenceError("call-flow JSON engine must be voxcpm2")
    for field in ["preview_result", "test_play_result", "call_speak_result"]:
        if payload.get(field) not in {"passed", "failed", "skipped"}:
            raise EvidenceError(f"call-flow {field} must be passed, failed, or skipped")
    if payload.get("call_audio_enqueued") is not True:
        raise EvidenceError("call_audio_enqueued must be true")
    _verify_relative_audio_path(
        payload.get("saved_ai_audio_path"),
        label="saved_ai_audio_path",
    )
    category = payload.get("sanitized_failure_category")
    if category not in ACCEPTED_FAILURE_CATEGORIES:
        raise EvidenceError(
            f"sanitized_failure_category must be one of {sorted(ACCEPTED_FAILURE_CATEGORIES)}"
        )
    _verify_no_raw_error_leak(payload, label="call-flow JSON")
    _require_number(payload.get("warm_call_ttfa_ms"), label="warm_call_ttfa_ms")
    _require_number(payload.get("f5_warm_call_ttfa_ms"), label="f5_warm_call_ttfa_ms")


def _verify_final_outcome_if_present() -> None:
    decision_path = PHASE_DIR / "results" / "voxcpm2-decision.json"
    if not decision_path.exists():
        return
    payload = _read_json(decision_path)
    if not isinstance(payload, dict):
        raise EvidenceError("voxcpm2-decision.json must be an object")
    outcome = payload.get("final_outcome")
    if outcome not in ACCEPTED_FINAL_OUTCOMES:
        raise EvidenceError(f"final_outcome must be one of {sorted(ACCEPTED_FINAL_OUTCOMES)}")


def verify_decision_ready() -> None:
    verify_contract_only()
    verify_matrix_only()
    verify_runtime_only()
    verify_call_flow_only()
    _verify_manual_quality_rows()
    _verify_final_outcome_if_present()


def _verify_manual_quality_rows() -> None:
    with MANUAL_QUALITY.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != MANUAL_QUALITY_HEADER:
            raise EvidenceError("MANUAL-QUALITY.csv header changed after contract check")
        rows = list(reader)
    scenarios = {row.get("scenario") for row in rows if row.get("engine") == "voxcpm2"}
    missing = SCENARIOS - scenarios
    if missing:
        raise EvidenceError(f"missing manual VoxCPM2 quality rows: {sorted(missing)}")
    for row in rows:
        sample_path = row.get("sample_path", "")
        if row.get("engine") == "voxcpm2" and not sample_path.startswith("results/audio/"):
            raise EvidenceError(f"manual quality row has invalid sample_path: {sample_path!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-only", action="store_true", help="verify static headers and path declarations")
    parser.add_argument("--matrix-only", action="store_true", help="verify live scenario matrix JSON/CSV contracts")
    parser.add_argument("--runtime-only", action="store_true", help="verify VoxCPM2 runtime smoke and VRAM soak evidence")
    parser.add_argument("--call-flow-only", action="store_true", help="verify live call-flow evidence contract")
    parser.add_argument("--decision-ready", action="store_true", help="verify all promotion-decision evidence")
    args = parser.parse_args(argv)

    selected = [
        args.contract_only,
        args.matrix_only,
        args.runtime_only,
        args.call_flow_only,
        args.decision_ready,
    ]
    if sum(1 for value in selected if value) != 1:
        parser.error("choose exactly one verification mode")

    try:
        if args.contract_only:
            verify_contract_only()
        elif args.matrix_only:
            verify_matrix_only()
        elif args.runtime_only:
            verify_runtime_only()
        elif args.call_flow_only:
            verify_call_flow_only()
        elif args.decision_ready:
            verify_decision_ready()
    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
