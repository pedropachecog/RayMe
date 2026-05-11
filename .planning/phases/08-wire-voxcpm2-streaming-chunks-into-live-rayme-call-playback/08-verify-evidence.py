#!/usr/bin/env python3
"""Verify Phase 8 VoxCPM2 live streaming evidence contracts."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

PHASE_DIR = Path(__file__).resolve().parent
CALL_FLOW_JSON = PHASE_DIR / "results" / "voxcpm2-live-streaming-call-flow.json"
DECISION_JSON = PHASE_DIR / "results" / "voxcpm2-decision.json"

TOP_LEVEL_FIELDS = {"schema_version", "phase", "summary", "samples"}
SUMMARY_FIELDS = {
    "warm_sample_count",
    "voxcpm2_warm_call_ttfa_ms",
    "f5_warm_call_ttfa_ms",
    "voxcpm2_beats_f5",
}
IMMEDIATE_VOXCPM2_FIELDS = {
    "streaming_used",
    "fallback_used",
    "whole_wav_fallback_used",
    "chunk_count_at_start",
    "first_chunk_generated_ms",
    "first_chunk_enqueued_ms",
    "ai_audio_started_ms",
    "inter_chunk_gaps_ms",
}
FINAL_VOXCPM2_FIELDS = {
    "streaming_used",
    "fallback_used",
    "whole_wav_fallback_used",
    "chunk_count",
    "total_generation_ms",
    "total_playback_ms",
    "inter_chunk_gaps_ms",
}
FINAL_ONLY_FIELDS = {"chunk_count", "total_generation_ms", "total_playback_ms"}
DECISION_FIELDS = {
    "final_outcome",
    "preferred_call_tts_engine",
    "voxcpm2_warm_call_ttfa_ms",
    "f5_warm_call_ttfa_ms",
    "evidence_path",
}
FORBIDDEN_LEAK_PATTERNS = (
    "Traceback",
    'File "',
    "C:\\",
    "/home/",
    ".cache",
    "huggingface",
    "openbmb/VoxCPM2",
)


class EvidenceError(Exception):
    """Evidence contract failure."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise EvidenceError(f"missing required file: {path.relative_to(PHASE_DIR)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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


def _require_bool(value: Any, *, expected: bool, label: str) -> None:
    if value is not expected:
        raise EvidenceError(f"{label} must be {expected}")


def _require_list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{label} must be a list")
    return value


def _verify_no_raw_error_leak(value: Any, *, label: str) -> None:
    text = json.dumps(value, sort_keys=True)
    leaked = [pattern for pattern in FORBIDDEN_LEAK_PATTERNS if pattern in text]
    if leaked:
        raise EvidenceError(f"{label} appears to expose raw runtime details: {leaked}")


def _median(values: list[float]) -> float:
    if not values:
        raise EvidenceError("median requires at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return round(float(ordered[middle]), 1)
    return round((ordered[middle - 1] + ordered[middle]) / 2.0, 1)


def _sample_label(sample: dict[str, Any]) -> str:
    return f"{sample.get('engine', 'unknown')} sample {sample.get('sample_index', '?')}"


def _event_metrics(sample: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    label = _sample_label(sample)
    audio_event = sample.get("ai_audio_started_event")
    if not isinstance(audio_event, dict):
        raise EvidenceError(f"{label} missing ai_audio_started_event")
    immediate = audio_event.get("tts_playback")
    if not isinstance(immediate, dict):
        raise EvidenceError(f"{label} missing ai_audio_started_event.tts_playback")
    tts_playback_final = sample.get("tts_playback_final")
    if not isinstance(tts_playback_final, dict):
        raise EvidenceError(f"{label} missing tts_playback_final")
    return audio_event, immediate, tts_playback_final


def _verify_voxcpm2_sample(sample: dict[str, Any]) -> float:
    label = _sample_label(sample)
    _, immediate, tts_playback_final = _event_metrics(sample)

    leaked_final_fields = sorted(FINAL_ONLY_FIELDS & set(immediate))
    if leaked_final_fields:
        raise EvidenceError(
            f"{label} immediate tts_playback must not contain final-only fields "
            f"{leaked_final_fields}; read them from tts_playback_final"
        )

    _require_fields(immediate, IMMEDIATE_VOXCPM2_FIELDS, label=f"{label} immediate tts_playback")
    _require_bool(immediate.get("streaming_used"), expected=True, label=f"{label} immediate streaming_used")
    _require_bool(immediate.get("fallback_used"), expected=False, label=f"{label} immediate fallback_used")
    _require_bool(
        immediate.get("whole_wav_fallback_used"),
        expected=False,
        label=f"{label} immediate whole_wav_fallback_used",
    )
    first_chunk_generated_ms = _require_number(
        immediate.get("first_chunk_generated_ms"),
        label=f"{label} first_chunk_generated_ms",
    )
    first_chunk_enqueued_ms = _require_number(
        immediate.get("first_chunk_enqueued_ms"),
        label=f"{label} first_chunk_enqueued_ms",
    )
    ai_audio_started_ms = _require_number(
        immediate.get("ai_audio_started_ms"),
        label=f"{label} ai_audio_started_ms",
    )
    if first_chunk_generated_ms < 0 or first_chunk_enqueued_ms < 0 or ai_audio_started_ms < 0:
        raise EvidenceError(f"{label} immediate timing fields must be non-negative")
    chunk_count_at_start = _require_number(
        immediate.get("chunk_count_at_start"),
        label=f"{label} chunk_count_at_start",
    )
    if chunk_count_at_start < 1:
        raise EvidenceError(f"{label} chunk_count_at_start must be >= 1")
    _require_list(immediate.get("inter_chunk_gaps_ms"), label=f"{label} immediate inter_chunk_gaps_ms")

    _require_fields(tts_playback_final, FINAL_VOXCPM2_FIELDS, label=f"{label} tts_playback_final")
    _require_bool(tts_playback_final.get("streaming_used"), expected=True, label=f"{label} final streaming_used")
    _require_bool(tts_playback_final.get("fallback_used"), expected=False, label=f"{label} final fallback_used")
    _require_bool(
        tts_playback_final.get("whole_wav_fallback_used"),
        expected=False,
        label=f"{label} final whole_wav_fallback_used",
    )
    chunk_count = _require_number(tts_playback_final.get("chunk_count"), label=f"{label} final chunk_count")
    if chunk_count < 1:
        raise EvidenceError(f"{label} final chunk_count must be >= 1")
    total_generation_ms = _require_number(
        tts_playback_final.get("total_generation_ms"),
        label=f"{label} final total_generation_ms",
    )
    _require_number(tts_playback_final.get("total_playback_ms"), label=f"{label} final total_playback_ms")
    _require_list(tts_playback_final.get("inter_chunk_gaps_ms"), label=f"{label} final inter_chunk_gaps_ms")
    if not ai_audio_started_ms < total_generation_ms:
        raise EvidenceError(f"{label} ai_audio_started_ms < tts_playback_final.total_generation_ms must hold")

    sample_ttfa = _require_number(sample.get("warm_call_ttfa_ms"), label=f"{label} warm_call_ttfa_ms")
    if round(sample_ttfa, 1) != round(ai_audio_started_ms, 1):
        raise EvidenceError(f"{label} warm_call_ttfa_ms must match immediate ai_audio_started_ms")
    return sample_ttfa


def _verify_comparator_sample(sample: dict[str, Any]) -> float:
    label = _sample_label(sample)
    _, immediate, _ = _event_metrics(sample)
    ai_audio_started_ms = _require_number(
        immediate.get("ai_audio_started_ms"),
        label=f"{label} ai_audio_started_ms",
    )
    sample_ttfa = _require_number(sample.get("warm_call_ttfa_ms"), label=f"{label} warm_call_ttfa_ms")
    if round(sample_ttfa, 1) != round(ai_audio_started_ms, 1):
        raise EvidenceError(f"{label} warm_call_ttfa_ms must match immediate ai_audio_started_ms")
    return sample_ttfa


def _verify_call_flow(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise EvidenceError("call-flow JSON must be an object")
    _verify_no_raw_error_leak(payload, label="call-flow JSON")
    _require_fields(payload, TOP_LEVEL_FIELDS, label="call-flow JSON")
    if payload.get("schema_version") != 1:
        raise EvidenceError("schema_version must be 1")
    if payload.get("phase") != "08":
        raise EvidenceError('phase must be "08"')

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise EvidenceError("summary must be an object")
    _require_fields(summary, SUMMARY_FIELDS, label="summary")
    warm_sample_count = int(_require_number(summary.get("warm_sample_count"), label="warm_sample_count"))
    if warm_sample_count < 3:
        raise EvidenceError("warm_sample_count must be at least 3")

    samples = payload.get("samples")
    if not isinstance(samples, list) or not all(isinstance(sample, dict) for sample in samples):
        raise EvidenceError("samples must be a list of objects")

    f5_ttfas: list[float] = []
    voxcpm2_ttfas: list[float] = []
    for sample in samples:
        engine = sample.get("engine")
        if engine == "voxcpm2":
            voxcpm2_ttfas.append(_verify_voxcpm2_sample(sample))
        elif engine == "f5":
            f5_ttfas.append(_verify_comparator_sample(sample))

    if len(voxcpm2_ttfas) < 3:
        raise EvidenceError("call-flow JSON requires at least three measured VoxCPM2 samples")
    if len(f5_ttfas) < 3:
        raise EvidenceError("call-flow JSON requires at least three measured F5 samples")
    if len(voxcpm2_ttfas) < warm_sample_count or len(f5_ttfas) < warm_sample_count:
        raise EvidenceError("warm_sample_count exceeds measured sample count")

    voxcpm2_median = _median(voxcpm2_ttfas)
    f5_median = _median(f5_ttfas)
    reported_voxcpm2 = round(_require_number(summary.get("voxcpm2_warm_call_ttfa_ms"), label="voxcpm2_warm_call_ttfa_ms"), 1)
    reported_f5 = round(_require_number(summary.get("f5_warm_call_ttfa_ms"), label="f5_warm_call_ttfa_ms"), 1)
    if reported_voxcpm2 != voxcpm2_median:
        raise EvidenceError("summary voxcpm2_warm_call_ttfa_ms must match measured median")
    if reported_f5 != f5_median:
        raise EvidenceError("summary f5_warm_call_ttfa_ms must match measured median")
    if not voxcpm2_median < f5_median:
        raise EvidenceError("VoxCPM2 median first-audio time must be lower than F5 median")
    if summary.get("voxcpm2_beats_f5") is not True:
        raise EvidenceError("voxcpm2_beats_f5 must be true")


def _sample(
    *,
    engine: str,
    sample_index: int,
    ttfa_ms: float,
    streaming_used: bool,
    chunk_count: int,
    total_generation_ms: float,
) -> dict[str, Any]:
    return {
        "engine": engine,
        "sample_index": sample_index,
        "warm_call_ttfa_ms": ttfa_ms,
        "ai_audio_started_event": {
            "audio": True,
            "tts_playback": {
                "streaming_used": streaming_used,
                "fallback_used": False,
                "whole_wav_fallback_used": False,
                "chunk_count_at_start": 1,
                "first_chunk_generated_ms": max(ttfa_ms - 35.0, 0.0),
                "first_chunk_enqueued_ms": max(ttfa_ms - 12.0, 0.0),
                "ai_audio_started_ms": ttfa_ms,
                "inter_chunk_gaps_ms": [22.0, 31.0] if streaming_used else [],
            },
        },
        "tts_playback_final": {
            "streaming_used": streaming_used,
            "fallback_used": False,
            "whole_wav_fallback_used": False,
            "chunk_count": chunk_count,
            "total_generation_ms": total_generation_ms,
            "total_playback_ms": total_generation_ms - 100.0,
            "inter_chunk_gaps_ms": [22.0, 31.0] if streaming_used else [],
        },
    }


def _synthetic_contract_payload() -> dict[str, Any]:
    f5_samples = [
        _sample(engine="f5", sample_index=1, ttfa_ms=1110.0, streaming_used=False, chunk_count=1, total_generation_ms=1500.0),
        _sample(engine="f5", sample_index=2, ttfa_ms=1120.0, streaming_used=False, chunk_count=1, total_generation_ms=1510.0),
        _sample(engine="f5", sample_index=3, ttfa_ms=1130.0, streaming_used=False, chunk_count=1, total_generation_ms=1520.0),
    ]
    voxcpm2_samples = [
        _sample(engine="voxcpm2", sample_index=1, ttfa_ms=410.0, streaming_used=True, chunk_count=3, total_generation_ms=1800.0),
        _sample(engine="voxcpm2", sample_index=2, ttfa_ms=420.0, streaming_used=True, chunk_count=3, total_generation_ms=1810.0),
        _sample(engine="voxcpm2", sample_index=3, ttfa_ms=430.0, streaming_used=True, chunk_count=3, total_generation_ms=1820.0),
    ]
    return {
        "schema_version": 1,
        "phase": "08",
        "generated_at": "2026-05-11T00:00:00Z",
        "web_base_url": "configured-web-ui",
        "ai_base_url": "configured-ai-backend",
        "runtime": {
            "engine_order": ["f5", "voxcpm2"],
            "warmup_samples_per_engine": 1,
            "measured_warm_samples_per_engine": 3,
        },
        "samples": [*f5_samples, *voxcpm2_samples],
        "summary": {
            "warm_sample_count": 3,
            "voxcpm2_warm_call_ttfa_ms": 420.0,
            "f5_warm_call_ttfa_ms": 1120.0,
            "voxcpm2_beats_f5": True,
        },
    }


def verify_contract_only() -> None:
    _verify_call_flow(_synthetic_contract_payload())


def verify_call_flow_only() -> None:
    _verify_call_flow(_read_json(CALL_FLOW_JSON))


def verify_decision_ready() -> None:
    verify_call_flow_only()
    decision = _read_json(DECISION_JSON)
    if not isinstance(decision, dict):
        raise EvidenceError("voxcpm2-decision.json must be an object")
    _verify_no_raw_error_leak(decision, label="voxcpm2-decision.json")
    _require_fields(decision, DECISION_FIELDS, label="voxcpm2-decision.json")
    _require_number(decision.get("voxcpm2_warm_call_ttfa_ms"), label="decision voxcpm2_warm_call_ttfa_ms")
    _require_number(decision.get("f5_warm_call_ttfa_ms"), label="decision f5_warm_call_ttfa_ms")
    if not isinstance(decision.get("final_outcome"), str) or not decision["final_outcome"]:
        raise EvidenceError("decision final_outcome must be a non-empty string")
    if not isinstance(decision.get("preferred_call_tts_engine"), str) or not decision["preferred_call_tts_engine"]:
        raise EvidenceError("decision preferred_call_tts_engine must be a non-empty string")
    if not isinstance(decision.get("evidence_path"), str) or not decision["evidence_path"]:
        raise EvidenceError("decision evidence_path must be a non-empty string")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-only", action="store_true", help="verify the synthetic evidence contract only")
    parser.add_argument("--call-flow-only", action="store_true", help="verify live call-flow evidence only")
    parser.add_argument("--decision-ready", action="store_true", help="verify call-flow and decision evidence")
    args = parser.parse_args(argv)

    selected = [args.contract_only, args.call_flow_only, args.decision_ready]
    if sum(1 for value in selected if value) > 1:
        parser.error("choose at most one verification mode")

    try:
        if args.contract_only:
            verify_contract_only()
        elif args.decision_ready:
            verify_decision_ready()
        else:
            verify_call_flow_only()
    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
