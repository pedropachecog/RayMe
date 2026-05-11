#!/usr/bin/env python3
"""Verify Phase 07 VoxCPM2 evidence artifact contracts."""

from __future__ import annotations

import argparse
import csv
import json
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
    rows = _matrix_rows_from_json(_read_json(MATRIX_JSON))
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
        if not isinstance(sample_path, str) or not sample_path.startswith("results/audio/"):
            raise EvidenceError(f"invalid sample_path for {row.get('scenario')}: {sample_path!r}")
    if not MATRIX_CSV.exists():
        raise EvidenceError("missing scenario matrix CSV")


def verify_call_flow_only() -> None:
    payload = _read_json(CALL_FLOW_JSON)
    if not isinstance(payload, dict):
        raise EvidenceError("call-flow JSON must be an object")
    for field in ["engine", "call_tts_result", "sample_path", "public_error_code"]:
        if field not in payload:
            raise EvidenceError(f"call-flow JSON missing {field!r}")
    if payload.get("engine") != "voxcpm2":
        raise EvidenceError("call-flow JSON engine must be voxcpm2")


def verify_decision_ready() -> None:
    verify_contract_only()
    verify_matrix_only()
    verify_call_flow_only()
    for path in [VRAM_SOAK_JSON, RUNTIME_SMOKE_JSON]:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise EvidenceError(f"{path.name} must contain a JSON object")
    _verify_manual_quality_rows()


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
    parser.add_argument("--call-flow-only", action="store_true", help="verify live call-flow evidence contract")
    parser.add_argument("--decision-ready", action="store_true", help="verify all promotion-decision evidence")
    args = parser.parse_args(argv)

    selected = [
        args.contract_only,
        args.matrix_only,
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
