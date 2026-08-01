#!/usr/bin/env python3
"""Independently verify Phase 09 Qwen release evidence from raw samples."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import math
import re
import statistics
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


PHASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = PHASE_DIR / "09-evidence-manifest.json"
SPEAKER_TOOL = PHASE_DIR / "09-speaker-score.py"
TEST_TOOL = PHASE_DIR / "test_phase09_evidence.py"
DEFAULT_RESULTS_DIR = PHASE_DIR / "results"

CORE_FILES = {
    "runtime": "qwen3-runtime.json",
    "status": "qwen3-webrtc-status.json",
    "call_flow": "qwen3-call-flow.json",
    "soak": "qwen3-soak.json",
    "stt": "qwen3-stt.json",
}
DECISION_FILES = {
    "speaker": "qwen3-speaker.json",
    "leak_scan": "qwen3-log-leak-scan.json",
    "browser": "qwen3-browser.json",
}
REQUIRED_CRITICAL_GATES = (
    "runtime_identity_cuda_one_hot",
    "reference_authorization",
    "all_scenarios_observed",
    "early_playback_before_completion",
    "bounded_bridge_and_track",
    "no_whole_synthesis_fallback",
    "terminal_safe_cancellation",
    "fifty_turn_non_degradation",
    "spoken_message_integrity",
    "private_evidence_clean",
)
CORE_CRITICAL_GATES = set(REQUIRED_CRITICAL_GATES) - {"private_evidence_clean"}
EXPECTED_SCENARIOS = {
    "clone-valid-short",
    "clone-valid-medium",
    "clone-valid-long",
    "message-integrity-names-numbers",
    "message-integrity-negation-abbreviations",
    "message-integrity-punctuation-final-word",
    "alignment-tolerant-punctuation-case",
    "alignment-tolerant-accented-english",
    "alignment-invalid-blank",
    "alignment-invalid-known-mismatch",
    "runaway-ceiling",
    "slow-stream-backpressure",
    "cancel-after-audio",
    "cancel-before-audio",
    "hangup-and-switch-hangup",
    "hangup-and-switch-engine-switch",
    "runtime-identity-one-hot",
    "worker-failure-sanitized",
    "hot-50-turn",
    "canonical-deployed-call",
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_PATH = re.compile(r"(?i)(?:^|[\s\"'])(?:[a-z]:[\\/]|\\\\[^\\]+\\)")
UNIX_PRIVATE_PATH = re.compile(r"(?:^|[\s\"'])/(?:home|users|tmp|var|mnt|d)/[A-Za-z0-9_.-]")
TOKEN_VALUE = re.compile(r"(?i)(?:bearer\s+|access[_-]?token[=: ]+|api[_-]?key[=: ]+|rayme_secret_)[A-Za-z0-9._~+/=-]{8,}")
BASE64_VALUE = re.compile(r"^[A-Za-z0-9+/]{512,}={0,2}$")
AUDIO_EXTENSION = re.compile(r"(?i)\.(?:wav|mp3|flac|ogg|m4a|opus)(?:$|[?#\s\"'])")
FINAL_ONLY_FIELDS = {
    "generation_complete_ms",
    "native_generation_ms",
    "playout_complete_ms",
    "chunk_count",
    "natural_eos",
    "rtfx",
    "underflow_count",
    "join_violation_count",
}


class EvidenceError(Exception):
    """Evidence is incomplete, stale, private, or fails a release threshold."""


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise EvidenceError(f"missing required evidence file: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON in {path.name}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def _objects(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise EvidenceError(f"{label} must be a list of objects")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(float(value)):
        raise EvidenceError(f"{label} must be a finite number")
    return float(value)


def _boolean(value: Any, *, expected: bool, label: str) -> None:
    if value is not expected:
        raise EvidenceError(f"{label} must be {expected}")


def _string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be a non-empty string")
    return value


def _sha(value: Any, *, label: str, length: int) -> str:
    pattern = HEX40 if length == 40 else HEX64
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise EvidenceError(f"{label} must be a lowercase {length}-character hex digest")
    return value


def _require_fields(payload: dict[str, Any], required: Iterable[str], *, label: str) -> None:
    missing = set(required) - set(payload)
    if missing:
        raise EvidenceError(f"{label} missing fields: {sorted(missing)}")


def _median(values: Iterable[float], *, label: str) -> float:
    numbers = [_number(value, label=label) for value in values]
    if not numbers:
        raise EvidenceError(f"{label} needs at least one raw sample")
    return float(statistics.median(numbers))


def _mean(values: Iterable[float], *, label: str) -> float:
    numbers = [_number(value, label=label) for value in values]
    if not numbers:
        raise EvidenceError(f"{label} needs at least one raw sample")
    return float(statistics.fmean(numbers))


def _parse_time(value: Any, *, label: str) -> datetime:
    text = _string(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{label} must be ISO-8601 UTC") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _now(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return _parse_time(value, label="verification time")


def verify_no_private_leaks(value: Any, *, label: str) -> None:
    """Scan both JSON keys and values; committed evidence contains hashes/scalars only."""

    def visit(item: Any, location: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                key_text = str(key)
                lowered = key_text.lower()
                if WINDOWS_PATH.search(key_text) or UNIX_PRIVATE_PATH.search(key_text):
                    raise EvidenceError(f"{label} contains a private path in a key at {location}")
                if (
                    "transcript" in lowered
                    and not lowered.endswith("sha256")
                    and lowered not in {"integrated_human_listening_status"}
                ):
                    raise EvidenceError(f"{label} contains a full transcript field at {location}.{key_text}")
                if lowered in {"wav_b64", "audio_b64", "audio_bytes", "embedding", "embeddings", "prompt_tensors"}:
                    raise EvidenceError(f"{label} contains raw audio/base64/embedding material at {location}.{key_text}")
                if lowered in {"access_token", "api_key", "secret", "authorization_header"}:
                    raise EvidenceError(f"{label} contains an access token field at {location}.{key_text}")
                visit(child, f"{location}.{key_text}")
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{location}[{index}]")
            return
        if not isinstance(item, str):
            return
        if WINDOWS_PATH.search(item) or UNIX_PRIVATE_PATH.search(item) or item.lower().startswith("file://"):
            raise EvidenceError(f"{label} contains a private path at {location}")
        if TOKEN_VALUE.search(item):
            raise EvidenceError(f"{label} contains an access token at {location}")
        if AUDIO_EXTENSION.search(item):
            raise EvidenceError(f"{label} contains a forbidden audio extension at {location}")
        if BASE64_VALUE.fullmatch(item):
            raise EvidenceError(f"{label} contains a base64-sized field at {location}")
        if len(item) > 160 and item.count(" ") >= 8:
            raise EvidenceError(f"{label} contains a probable full transcript at {location}")

    visit(value, "$.__root__")


def _manifest() -> dict[str, Any]:
    return _object(_read_json(MANIFEST_PATH), label="manifest")


def _validate_authorization(value: Any, manifest: dict[str, Any], *, label: str) -> None:
    authorization = _object(value, label=label)
    fixture = _object(manifest.get("selected_fixture"), label="manifest selected_fixture")
    required = {
        "fixture_kind",
        "opaque_asset_id",
        "voice_data_steward",
        "authorization_basis",
        "use_scope",
        "reference_sha256",
        "transcript_sha256",
    }
    _require_fields(authorization, required, label=label)
    for field in required:
        if authorization.get(field) != fixture.get(field):
            raise EvidenceError(f"{label} {field} does not match the selected hash-bound fixture")
    if authorization["use_scope"] != "rayme_lan_call_testing":
        raise EvidenceError(f"{label} scope must be rayme_lan_call_testing")
    _sha(authorization["reference_sha256"], label=f"{label} reference_sha256", length=64)
    _sha(authorization["transcript_sha256"], label=f"{label} transcript_sha256", length=64)


def verify_contracts_only() -> dict[str, Any]:
    for path in (MANIFEST_PATH, SPEAKER_TOOL, Path(__file__).resolve(), TEST_TOOL):
        if not path.is_file():
            raise EvidenceError(f"missing contract tool: {path.name}")
    for path in (SPEAKER_TOOL, Path(__file__).resolve(), TEST_TOOL):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        except SyntaxError as exc:
            raise EvidenceError(f"contract tool is not valid Python: {path.name}: {exc}") from exc

    manifest = _manifest()
    _require_fields(
        manifest,
        {
            "schema_version",
            "phase",
            "runtime",
            "speaker_scorer",
            "selected_fixture",
            "evidence_policy",
            "acceptance_status",
            "artifact_inventory",
            "critical_gate_ids",
            "thresholds",
            "seed_policy",
            "scenarios",
        },
        label="manifest",
    )
    if manifest["schema_version"] != 1 or manifest["phase"] != "09":
        raise EvidenceError("manifest schema_version/phase must be 1/09")

    runtime = _object(manifest["runtime"], label="manifest runtime")
    expected_runtime = {
        "engine_id": "qwen3_1_7b",
        "package": "faster-qwen3-tts==0.3.2",
        "source_commit": "a70afc0f81f7f5f8801c3227968f1102f43f211c",
        "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "model_revision": "fd4b254389122332181a7c3db7f27e918eec64e3",
        "torch_version": "2.10.0+cu126",
        "cuda_version": "12.6",
        "device": "cuda",
    }
    if runtime != expected_runtime:
        raise EvidenceError("manifest runtime identity is not the pinned Phase 09 runtime")
    scorer = _object(manifest["speaker_scorer"], label="manifest speaker_scorer")
    if scorer != {
        "model_id": "microsoft/wavlm-base-plus-sv",
        "model_revision": "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e",
        "model_class": "WavLMForXVector",
        "transformers_version": "4.57.3",
        "sample_rate_hz": 16000,
        "device": "cuda",
        "maximum_late_drop": 0.05,
    }:
        raise EvidenceError("manifest speaker scorer is not the pinned local WavLM contract")

    fixture = _object(manifest["selected_fixture"], label="manifest selected_fixture")
    _validate_authorization(fixture, manifest, label="manifest selected_fixture")
    policy = _object(manifest["evidence_policy"], label="manifest evidence_policy")
    if policy.get("audio_storage") != "local_only_uncommitted" or policy.get("embedding_storage") != "local_only_uncommitted":
        raise EvidenceError("manifest audio and embeddings must remain local and uncommitted")
    if policy.get("committed_payload") != "opaque_ids_hashes_and_scalars_only":
        raise EvidenceError("manifest committed evidence must be opaque ids, hashes, and scalars only")
    if policy.get("hosted_audio_judge_allowed") is not False:
        raise EvidenceError("hosted audio judging is prohibited")
    if policy.get("product_owner_direction_is_speaker_permission") is not False:
        raise EvidenceError("product-owner direction/listening cannot be speaker permission")

    acceptance = _object(manifest["acceptance_status"], label="manifest acceptance_status")
    if acceptance.get("autonomous_release_ready") != "pending":
        raise EvidenceError("manifest autonomous readiness must start pending")
    if acceptance.get("integrated_human_listening_status") != "pending" or acceptance.get("physical_call_status") != "pending":
        raise EvidenceError("integrated listening and physical call must remain independently pending")
    if acceptance.get("candidate_spike_listening_status") != "accepted_separately":
        raise EvidenceError("candidate spike listening must remain separate")

    if manifest["critical_gate_ids"] != list(REQUIRED_CRITICAL_GATES):
        raise EvidenceError("manifest critical gate inventory is incomplete or reordered")
    scenarios = _objects(manifest["scenarios"], label="manifest scenarios")
    ids = [scenario.get("scenario_id") for scenario in scenarios]
    if len(ids) != 20 or len(set(ids)) != 20 or set(ids) != EXPECTED_SCENARIOS:
        raise EvidenceError("manifest must freeze exactly the twenty AI-SPEC scenario ids")
    seeds: list[int] = []
    inventory = _object(manifest["artifact_inventory"], label="manifest artifact_inventory")
    artifact_names = set(inventory.get("core", [])) | set(inventory.get("decision", []))
    for scenario in scenarios:
        _require_fields(
            scenario,
            {"scenario_id", "criticality", "seed", "expected_events", "evidence_artifact", "thresholds"},
            label=f"scenario {scenario.get('scenario_id')}",
        )
        if scenario["criticality"] not in {"critical", "high"}:
            raise EvidenceError(f"scenario {scenario['scenario_id']} has invalid criticality")
        if not isinstance(scenario["seed"], int) or isinstance(scenario["seed"], bool):
            raise EvidenceError(f"scenario {scenario['scenario_id']} seed must be an integer")
        seeds.append(scenario["seed"])
        if not isinstance(scenario["expected_events"], list) or not scenario["expected_events"]:
            raise EvidenceError(f"scenario {scenario['scenario_id']} expected_events must be non-empty")
        if scenario["evidence_artifact"] not in artifact_names:
            raise EvidenceError(f"scenario {scenario['scenario_id']} names an unknown evidence artifact")
        if not isinstance(scenario["thresholds"], dict) or not scenario["thresholds"]:
            raise EvidenceError(f"scenario {scenario['scenario_id']} thresholds must be non-empty")
    if len(set(seeds)) != 20:
        raise EvidenceError("scenario seeds must be unique")
    if manifest["seed_policy"].get("anchor_turns") != [1, 10, 20, 30, 40, 50]:
        raise EvidenceError("manifest anchor turns must be 1/10/20/30/40/50")
    return manifest


def _artifact_header(
    payload: Any,
    *,
    artifact: str,
    expected_commit: str | None,
    now: datetime,
    max_age_seconds: float,
) -> tuple[dict[str, Any], str]:
    item = _object(payload, label=f"{artifact} evidence")
    _require_fields(item, {"schema_version", "phase", "artifact", "generated_at", "deployed_commit"}, label=f"{artifact} evidence")
    if item["schema_version"] != 1 or item["phase"] != "09" or item["artifact"] != artifact:
        raise EvidenceError(f"{artifact} evidence schema/phase/artifact mismatch")
    commit = _sha(item["deployed_commit"], label=f"{artifact} deployed_commit", length=40)
    if expected_commit is not None and commit != expected_commit:
        raise EvidenceError(f"{artifact} deployed-commit mismatch")
    generated = _parse_time(item["generated_at"], label=f"{artifact} generated_at")
    age = (now - generated).total_seconds()
    if age < -300 or age > max_age_seconds:
        raise EvidenceError(f"{artifact} evidence timestamp is stale or from the future")
    verify_no_private_leaks(item, label=f"{artifact} evidence")
    return item, commit


def _gate_ids(payloads: Iterable[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for payload in payloads:
        gates = payload.get("critical_gates")
        if not isinstance(gates, list) or not all(isinstance(gate, str) and gate for gate in gates):
            raise EvidenceError(f"{payload.get('artifact', 'unknown')} critical_gates must be a list of ids")
        found.update(gates)
    return found


def _verify_runtime(payload: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    identity = _object(payload.get("identity"), label="runtime identity")
    locked = manifest["runtime"]
    expected = {
        "engine_id": locked["engine_id"],
        "package": locked["package"],
        "runtime_source_commit": locked["source_commit"],
        "model_id": locked["model_id"],
        "model_revision": locked["model_revision"],
        "torch_version": locked["torch_version"],
        "torch_cuda_version": locked["cuda_version"],
    }
    for field, value in expected.items():
        if identity.get(field) != value:
            raise EvidenceError(f"runtime {field} is a model/runtime substitution")
    if identity.get("device") != "cuda" or identity.get("cuda_available") is not True:
        raise EvidenceError("runtime must use available CUDA")
    _boolean(identity.get("cpu_fallback_detected"), expected=False, label="runtime cpu_fallback_detected")
    _boolean(identity.get("model_parameters_cuda_only"), expected=True, label="runtime model_parameters_cuda_only")
    if "RTX 3060" not in _string(identity.get("gpu_name"), label="runtime gpu_name"):
        raise EvidenceError("runtime GPU must be the RTX 3060")
    if int(_number(identity.get("resident_tts_count"), label="runtime resident_tts_count")) != 1:
        raise EvidenceError("runtime must have exactly one resident TTS engine")
    if identity.get("resident_tts_engine") != "qwen3_1_7b" or identity.get("other_resident_engines") != []:
        raise EvidenceError("runtime one-hot resident engine must be qwen3_1_7b only")
    thresholds = manifest["thresholds"]
    if _number(identity.get("torch_reserved_mib"), label="runtime torch_reserved_mib") > thresholds["torch_reserved_mib"]:
        raise EvidenceError("runtime Torch reserved memory exceeds the bound")
    if _number(identity.get("system_gpu_mib"), label="runtime system_gpu_mib") > thresholds["system_gpu_mib"]:
        raise EvidenceError("runtime whole-system GPU memory exceeds the bound")
    return _objects(payload.get("scenario_results"), label="runtime scenario_results")


def _verify_status(payload: dict[str, Any], manifest: dict[str, Any]) -> None:
    readiness = _object(payload.get("readiness"), label="status readiness")
    if readiness.get("model_state") != "resident" or readiness.get("resident_engine") != "qwen3_1_7b":
        raise EvidenceError("status must show the Qwen model resident")
    if readiness.get("prompt_state") != "ready":
        raise EvidenceError("status must show the selected prompt ready separately")
    if readiness.get("model_state") == readiness.get("prompt_state"):
        raise EvidenceError("model and prompt readiness must be separate state machines")
    if readiness.get("loading_engine") is not None:
        raise EvidenceError("status must not remain loading")
    if int(_number(readiness.get("resident_tts_count"), label="status resident_tts_count")) != 1:
        raise EvidenceError("status resident_tts_count must be one")
    cache = _object(payload.get("prompt_cache"), label="status prompt_cache")
    if int(_number(cache.get("capacity"), label="prompt cache capacity")) > manifest["thresholds"]["prompt_cache_capacity"]:
        raise EvidenceError("unbounded prompt cache capacity")
    if int(_number(cache.get("high_water"), label="prompt cache high_water")) > int(cache["capacity"]):
        raise EvidenceError("prompt cache high-water exceeds capacity")
    limits = _object(payload.get("output_limits"), label="status output_limits")
    if limits.get("bounded") is not True:
        raise EvidenceError("output limits must be bounded")
    if _number(limits.get("max_segment_words"), label="max_segment_words") > manifest["thresholds"]["max_segment_words"]:
        raise EvidenceError("unbounded output segment word ceiling")
    if _number(limits.get("max_new_tokens"), label="max_new_tokens") > manifest["thresholds"]["max_new_tokens"]:
        raise EvidenceError("unbounded output token ceiling")
    if _number(limits.get("max_audio_seconds"), label="max_audio_seconds") > manifest["thresholds"]["max_audio_seconds"]:
        raise EvidenceError("unbounded output audio ceiling")
    _validate_authorization(payload.get("reference_authorization"), manifest, label="status reference_authorization")
    acceptance = _object(payload.get("acceptance_status"), label="status acceptance_status")
    if acceptance.get("integrated_human_listening_status") != "pending":
        raise EvidenceError("integrated human listening status must remain pending")
    if acceptance.get("physical_call_status") != "pending":
        raise EvidenceError("physical call status must remain pending")
    if acceptance.get("candidate_spike_listening_status") != "accepted_separately":
        raise EvidenceError("candidate listening acceptance must remain separate")


def _scenario_map(rows: Sequence[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected = {row["scenario_id"]: row for row in manifest["scenarios"]}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        scenario_id = _string(row.get("scenario_id"), label="scenario_result scenario_id")
        if scenario_id in result:
            raise EvidenceError(f"duplicate scenario result: {scenario_id}")
        if scenario_id not in expected:
            raise EvidenceError(f"unknown scenario result: {scenario_id}")
        events = row.get("observed_events")
        if events != expected[scenario_id]["expected_events"]:
            raise EvidenceError(f"scenario {scenario_id} observed events do not match the frozen order")
        result[scenario_id] = row
    return result


def _stream_measurements(row: dict[str, Any], manifest: dict[str, Any], *, label: str) -> dict[str, Any]:
    values = _object(row.get("measurements"), label=f"{label} measurements")
    thresholds = manifest["thresholds"]
    _boolean(values.get("streaming_used"), expected=True, label=f"{label} streaming_used")
    _boolean(values.get("fallback_used"), expected=False, label=f"{label} fallback_used")
    _boolean(values.get("whole_wav_fallback_used"), expected=False, label=f"{label} whole_wav_fallback_used")
    _boolean(values.get("valid_audio"), expected=True, label=f"{label} valid_audio")
    first_playback = _number(values.get("first_playback_ms"), label=f"{label} first_playback_ms")
    completion = _number(values.get("generation_complete_ms"), label=f"{label} generation_complete_ms")
    if not first_playback < completion:
        raise EvidenceError(f"{label} first playback must precede stream completion")
    if first_playback > thresholds["rayme_first_playback_ms"]:
        raise EvidenceError(f"{label} first playback exceeds the bound")
    if _number(values.get("native_first_chunk_ms"), label=f"{label} native_first_chunk_ms") < 0:
        raise EvidenceError(f"{label} native first chunk must be non-negative")
    if _number(values.get("native_generation_ms"), label=f"{label} native_generation_ms") <= 0:
        raise EvidenceError(f"{label} native generation time must be positive")
    if _number(values.get("rtfx"), label=f"{label} rtfx") < thresholds["minimum_sample_rtfx"]:
        raise EvidenceError(f"{label} realtime supply failed")
    _boolean(values.get("natural_eos"), expected=True, label=f"{label} natural EOS")
    if int(_number(values.get("underflow_count"), label=f"{label} underflow_count")) != 0:
        raise EvidenceError(f"{label} active-playout underflow is forbidden")
    bridge_capacity = int(_number(values.get("bridge_capacity"), label=f"{label} bridge_capacity"))
    bridge_high_water = int(_number(values.get("bridge_high_water"), label=f"{label} bridge_high_water"))
    if bridge_capacity > thresholds["bridge_capacity_chunks"] or bridge_high_water > min(bridge_capacity, thresholds["bridge_high_water_chunks"]):
        raise EvidenceError(f"{label} bridge queue is absent or unbounded")
    track_capacity = _number(values.get("track_capacity_audio_ms"), label=f"{label} track_capacity_audio_ms")
    track_high_water = _number(values.get("track_high_water_audio_ms"), label=f"{label} track_high_water_audio_ms")
    if track_capacity > thresholds["track_capacity_audio_ms"] or track_high_water > track_capacity:
        raise EvidenceError(f"{label} track audio credit is absent or unbounded")
    immediate_fields = values.get("immediate_fields")
    final_fields = values.get("final_fields")
    if not isinstance(immediate_fields, list) or not isinstance(final_fields, list):
        raise EvidenceError(f"{label} immediate/final field inventories are required")
    leaked = FINAL_ONLY_FIELDS & set(immediate_fields)
    if leaked:
        raise EvidenceError(f"{label} immediate metrics contain final-only fields: {sorted(leaked)}")
    if not FINAL_ONLY_FIELDS <= set(final_fields):
        raise EvidenceError(f"{label} terminal metrics are incomplete")
    return values


def _verify_call_flow(payload: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    _validate_authorization(payload.get("reference_authorization"), manifest, label="call-flow reference_authorization")
    rows = _objects(payload.get("scenario_results"), label="call-flow scenario_results")
    mapped = _scenario_map(rows, manifest)
    normal_ids = {
        "clone-valid-short",
        "clone-valid-medium",
        "clone-valid-long",
        "message-integrity-names-numbers",
        "message-integrity-negation-abbreviations",
        "message-integrity-punctuation-final-word",
        "slow-stream-backpressure",
    }
    normal_values: list[dict[str, Any]] = []
    clone_values: list[dict[str, Any]] = []
    for scenario_id in normal_ids:
        if scenario_id not in mapped:
            raise EvidenceError(f"missing scenario result: {scenario_id}")
        values = _stream_measurements(mapped[scenario_id], manifest, label=scenario_id)
        normal_values.append(values)
        if scenario_id.startswith("clone-valid"):
            clone_values.append(values)
        if scenario_id.startswith("message-integrity"):
            if _number(values.get("wer"), label=f"{scenario_id} wer") > 0.20:
                raise EvidenceError(f"{scenario_id} WER exceeds the message-integrity gate")
            _boolean(values.get("final_word_pass"), expected=True, label=f"{scenario_id} final_word_pass")
    if _median((value["native_first_chunk_ms"] for value in clone_values), label="native first chunk median") > manifest["thresholds"]["native_hot_median_first_chunk_ms"]:
        raise EvidenceError("native hot median first chunk exceeds 500 ms")
    if _median((value["rtfx"] for value in normal_values), label="call RTFx median") < manifest["thresholds"]["minimum_median_rtfx"]:
        raise EvidenceError("call-flow median RTFx is below 1.25")

    for scenario_id in ("alignment-tolerant-punctuation-case", "alignment-tolerant-accented-english"):
        values = _object(mapped[scenario_id].get("measurements"), label=f"{scenario_id} measurements")
        _boolean(values.get("alignment_accepted"), expected=True, label=f"{scenario_id} alignment_accepted")
        _boolean(values.get("prompt_ready"), expected=True, label=f"{scenario_id} prompt_ready")
        coverage = _number(values.get("token_coverage"), label=f"{scenario_id} token_coverage")
        similarity = _number(values.get("edit_similarity"), label=f"{scenario_id} edit_similarity")
        if coverage < 0.45 and similarity < 0.50:
            raise EvidenceError(f"{scenario_id} should tolerate the public alignment variant")

    blank = _object(mapped["alignment-invalid-blank"].get("measurements"), label="alignment-invalid-blank measurements")
    _boolean(blank.get("alignment_accepted"), expected=False, label="blank alignment_accepted")
    _boolean(blank.get("generation_started"), expected=False, label="blank generation_started")
    if blank.get("public_error_code") != "qwen_reference_transcript_required":
        raise EvidenceError("blank transcript must use the fixed public error code")
    mismatch = _object(mapped["alignment-invalid-known-mismatch"].get("measurements"), label="known mismatch measurements")
    _boolean(mismatch.get("alignment_accepted"), expected=False, label="known mismatch alignment_accepted")
    _boolean(mismatch.get("generation_started"), expected=False, label="known mismatch generation_started")
    if _number(mismatch.get("token_coverage"), label="known mismatch token_coverage") >= 0.45:
        raise EvidenceError("known mismatch token coverage must remain below 0.45")
    if _number(mismatch.get("edit_similarity"), label="known mismatch edit_similarity") >= 0.50:
        raise EvidenceError("known mismatch edit similarity must remain below 0.50")

    runaway = _object(mapped["runaway-ceiling"].get("measurements"), label="runaway measurements")
    _boolean(runaway.get("ceiling_triggered"), expected=True, label="runaway ceiling_triggered")
    _boolean(runaway.get("natural_eos"), expected=False, label="runaway natural_eos")
    if _number(runaway.get("max_new_tokens"), label="runaway max_new_tokens") > manifest["thresholds"]["max_new_tokens"]:
        raise EvidenceError("runaway output token ceiling is unbounded")
    if _number(runaway.get("audio_seconds"), label="runaway audio_seconds") > manifest["thresholds"]["max_audio_seconds"]:
        raise EvidenceError("runaway audio duration ceiling is unbounded")
    if int(_number(runaway.get("normal_ai_done_count"), label="runaway normal_ai_done_count")) != 0:
        raise EvidenceError("runaway failure cannot emit normal ai_done")
    if int(_number(runaway.get("complete_persistence_count"), label="runaway complete_persistence_count")) != 0:
        raise EvidenceError("runaway failure cannot persist complete speech")

    for scenario_id in (
        "cancel-after-audio",
        "cancel-before-audio",
        "hangup-and-switch-hangup",
        "hangup-and-switch-engine-switch",
    ):
        values = _object(mapped[scenario_id].get("measurements"), label=f"{scenario_id} measurements")
        if _number(values.get("cancel_ack_ms"), label=f"{scenario_id} cancel_ack_ms") >= manifest["thresholds"]["cancel_hard_limit_ms"]:
            raise EvidenceError(f"{scenario_id} cancellation exceeded the hard limit")
        for field, message in (
            ("late_audio_count", "late audio after cancel"),
            ("late_enqueue_count", "late enqueue after cancel"),
            ("normal_ai_done_count", "ai_done after cancel"),
            ("complete_persistence_count", "persistence after cancel"),
        ):
            if int(_number(values.get(field), label=f"{scenario_id} {field}")) != 0:
                raise EvidenceError(f"{scenario_id} {message} is forbidden")
        if scenario_id == "cancel-before-audio" and int(_number(values.get("audio_started_count"), label="cancel-before audio_started_count")) != 0:
            raise EvidenceError("cancel-before-audio cannot emit audio_started")
        if scenario_id.startswith("hangup-and-switch"):
            _boolean(values.get("recovery"), expected=True, label=f"{scenario_id} recovery")

    failure = _object(mapped["worker-failure-sanitized"].get("measurements"), label="worker failure measurements")
    if failure.get("stable_error_code") != "qwen_runtime_failed":
        raise EvidenceError("worker failure must use the fixed Qwen-scoped error")
    for field in ("backend_healthy", "other_engines_usable", "recovery"):
        _boolean(failure.get(field), expected=True, label=f"worker failure {field}")
    if int(_number(failure.get("private_leak_count"), label="worker failure private_leak_count")) != 0:
        raise EvidenceError("worker failure exposed private data")

    canonical = _object(mapped["canonical-deployed-call"].get("measurements"), label="canonical call measurements")
    _boolean(canonical.get("canonical_public_api"), expected=True, label="canonical call public API")
    if int(_number(canonical.get("normal_persistence_count"), label="canonical normal_persistence_count")) != 1:
        raise EvidenceError("canonical call must persist exactly one normal speech row")
    if int(_number(canonical.get("cancelled_persistence_count"), label="canonical cancelled_persistence_count")) != 0:
        raise EvidenceError("canonical cancelled turn cannot persist")
    if int(_number(canonical.get("late_audio_count"), label="canonical late_audio_count")) != 0:
        raise EvidenceError("canonical call cannot play late audio")
    return rows


def _verify_soak(payload: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _objects(payload.get("turns"), label="soak turns")
    required_turns = int(manifest["thresholds"]["required_soak_turns"])
    if [row.get("turn") for row in rows] != list(range(1, required_turns + 1)):
        raise EvidenceError("soak must contain exactly ordered turns 1 through 50")
    for row in rows:
        turn = row["turn"]
        for field in ("valid_audio", "natural_eos", "streaming_used"):
            field_label = "natural EOS" if field == "natural_eos" else field
            _boolean(row.get(field), expected=True, label=f"soak turn {turn} {field_label}")
        for field in ("fallback_used", "whole_wav_fallback_used"):
            _boolean(row.get(field), expected=False, label=f"soak turn {turn} {field}")
        if _number(row.get("first_playback_ms"), label=f"soak turn {turn} first_playback_ms") >= _number(row.get("generation_complete_ms"), label=f"soak turn {turn} generation_complete_ms"):
            raise EvidenceError(f"soak turn {turn} first playback must precede stream completion")
        if _number(row.get("rtfx"), label=f"soak turn {turn} rtfx") < manifest["thresholds"]["minimum_sample_rtfx"]:
            raise EvidenceError(f"soak turn {turn} realtime supply failed")
        if int(_number(row.get("underflow_count"), label=f"soak turn {turn} underflow_count")) != 0:
            raise EvidenceError(f"soak turn {turn} active-playout underflow")
        peak = _number(row.get("peak"), label=f"soak turn {turn} peak")
        silence = _number(row.get("silence_fraction"), label=f"soak turn {turn} silence_fraction")
        clipping = _number(row.get("clipping_fraction"), label=f"soak turn {turn} clipping_fraction")
        if peak < manifest["thresholds"]["minimum_peak"] or silence > manifest["thresholds"]["maximum_silence_fraction"] or clipping > manifest["thresholds"]["maximum_clipping_fraction"]:
            raise EvidenceError(f"soak turn {turn} audio validity failed")
        for field in ("ttfa_ms", "rms_db", "spectral_centroid_hz", "spectral_flatness", "torch_reserved_mib", "system_gpu_mib"):
            _number(row.get(field), label=f"soak turn {turn} {field}")
        _sha(
            row.get("source_audio_sha256"),
            label=f"soak turn {turn} source_audio_sha256",
            length=64,
        )
        if row["torch_reserved_mib"] > manifest["thresholds"]["torch_reserved_mib"] or row["system_gpu_mib"] > manifest["thresholds"]["system_gpu_mib"]:
            raise EvidenceError(f"soak turn {turn} memory budget failed")

    early = rows[:5]
    late = rows[45:50]
    early_rms = _median((row["rms_db"] for row in early), label="early RMS")
    late_rms = _median((row["rms_db"] for row in late), label="late RMS")
    if abs(late_rms - early_rms) > manifest["thresholds"]["absolute_rms_delta_db"]:
        raise EvidenceError("soak early-to-late RMS drift exceeds the bound")
    centroid_ratio = _median((row["spectral_centroid_hz"] for row in late), label="late centroid") / _median((row["spectral_centroid_hz"] for row in early), label="early centroid")
    if centroid_ratio < manifest["thresholds"]["minimum_centroid_ratio"]:
        raise EvidenceError("soak spectral centroid ratio indicates muffling")
    flatness_growth = _median((row["spectral_flatness"] for row in late), label="late flatness") - _median((row["spectral_flatness"] for row in early), label="early flatness")
    if flatness_growth > manifest["thresholds"]["maximum_flatness_growth"]:
        raise EvidenceError("soak spectral flatness growth indicates noise")
    rtfx_ratio = _median((row["rtfx"] for row in late), label="late RTFx") / _median((row["rtfx"] for row in early), label="early RTFx")
    if rtfx_ratio < manifest["thresholds"]["minimum_rtfx_ratio"]:
        raise EvidenceError("soak RTFx ratio degraded")
    ttfa_growth = _median((row["ttfa_ms"] for row in late), label="late TTFA") - _median((row["ttfa_ms"] for row in early), label="early TTFA")
    if ttfa_growth > manifest["thresholds"]["maximum_ttfa_growth_ms"]:
        raise EvidenceError("soak TTFA growth exceeds the bound")
    memory_growth = _median((row["torch_reserved_mib"] for row in late), label="late reserved memory") - _median((row["torch_reserved_mib"] for row in early), label="early reserved memory")
    if memory_growth > manifest["thresholds"]["reserved_growth_mib"]:
        raise EvidenceError("soak reserved-memory growth exceeds the bound")

    anchor_turns = manifest["seed_policy"]["anchor_turns"]
    anchors = [row.get("anchor_sha256") for row in rows if row["turn"] in anchor_turns]
    if len(anchors) != len(anchor_turns) or any(HEX64.fullmatch(value or "") is None for value in anchors) or len(set(anchors)) != 1:
        raise EvidenceError("soak deterministic anchors are not bit-identical")
    return _objects(payload.get("scenario_results"), label="soak scenario_results")


def _verify_stt(payload: dict[str, Any], manifest: dict[str, Any]) -> None:
    rows = _objects(payload.get("samples"), label="STT samples")
    if [row.get("turn") for row in rows] != list(range(1, 51)):
        raise EvidenceError("STT evidence must contain ordered turns 1 through 50")
    for row in rows:
        _boolean(row.get("accepted"), expected=True, label=f"STT turn {row.get('turn')} accepted")
        _boolean(row.get("final_word_pass"), expected=True, label=f"STT turn {row.get('turn')} final_word_pass")
        wer = _number(row.get("wer"), label=f"STT turn {row.get('turn')} WER")
        if wer < 0.0 or wer > 1.0:
            raise EvidenceError("STT WER must be between zero and one")
    early = _mean((row["wer"] for row in rows[:5]), label="early WER")
    late = _mean((row["wer"] for row in rows[45:50]), label="late WER")
    overall = _mean((row["wer"] for row in rows), label="overall WER")
    thresholds = manifest["thresholds"]
    if late > thresholds["late_wer"] or late - early > thresholds["early_to_late_wer_delta"] or overall > thresholds["overall_wer"]:
        raise EvidenceError("STT early/late/overall WER gate failed")
    integrity = _objects(payload.get("message_integrity"), label="STT message_integrity")
    expected = {
        "message-integrity-names-numbers",
        "message-integrity-negation-abbreviations",
        "message-integrity-punctuation-final-word",
    }
    if {row.get("scenario_id") for row in integrity} != expected:
        raise EvidenceError("STT message-integrity scenarios are incomplete")
    for row in integrity:
        if _number(row.get("wer"), label=f"{row.get('scenario_id')} WER") > 0.20:
            raise EvidenceError("message-integrity WER failed")
        _boolean(row.get("final_word_pass"), expected=True, label=f"{row.get('scenario_id')} final_word_pass")
        _boolean(row.get("consequential_terms_pass"), expected=True, label=f"{row.get('scenario_id')} consequential_terms_pass")


def _verify_speaker(payload: dict[str, Any], manifest: dict[str, Any]) -> None:
    scorer = _object(payload.get("scorer"), label="speaker scorer")
    expected = manifest["speaker_scorer"]
    for field in ("model_id", "model_revision", "model_class", "transformers_version", "sample_rate_hz"):
        if scorer.get(field) != expected[field]:
            raise EvidenceError(f"speaker scorer {field} is not pinned")
    if not str(scorer.get("device", "")).startswith("cuda"):
        raise EvidenceError("speaker scorer must run on CUDA")
    if scorer.get("local_files_only") is not True:
        raise EvidenceError("speaker scorer must use the local pinned snapshot")
    if scorer.get("torch_version") != manifest["runtime"]["torch_version"] or scorer.get("torch_cuda_version") != manifest["runtime"]["cuda_version"]:
        raise EvidenceError("speaker scorer Torch/CUDA revision mismatch")
    if payload.get("baseline_commit") != payload.get("deployed_commit"):
        raise EvidenceError("speaker integrated baseline commit mismatch")
    if payload.get("reference_sha256") != manifest["selected_fixture"]["reference_sha256"]:
        raise EvidenceError("speaker reference hash mismatch")

    specs = {
        "baseline_scores": ["short", "medium", "long"],
        "early_scores": list(range(1, 6)),
        "middle_scores": list(range(23, 28)),
        "late_scores": list(range(46, 51)),
    }
    medians: dict[str, float] = {}
    for field, expected_ids in specs.items():
        rows = _objects(payload.get(field), label=f"speaker {field}")
        if [row.get("bucket_id") for row in rows] != expected_ids:
            raise EvidenceError(f"speaker {field} bucket ids are incomplete")
        for row in rows:
            _sha(row.get("audio_sha256"), label=f"speaker {field} audio_sha256", length=64)
            cosine = _number(row.get("cosine"), label=f"speaker {field} cosine")
            if cosine < -1.0 or cosine > 1.0:
                raise EvidenceError("speaker cosine must be between -1 and 1")
        medians[field] = _median((row["cosine"] for row in rows), label=f"speaker {field} median")
    baseline = medians["baseline_scores"]
    early = medians["early_scores"]
    late = medians["late_scores"]
    maximum_drop = manifest["thresholds"]["maximum_speaker_drop"]
    if late < early - maximum_drop:
        raise EvidenceError("late speaker median dropped more than 0.05 below early")
    if late < baseline - maximum_drop:
        raise EvidenceError("late speaker median dropped more than 0.05 below integrated baseline")
    reported = {
        "integrated_baseline_median": baseline,
        "early_median": early,
        "middle_median": medians["middle_scores"],
        "late_median": late,
        "late_minus_early": late - early,
        "late_minus_integrated_baseline": late - baseline,
    }
    for field, computed in reported.items():
        if not math.isclose(_number(payload.get(field), label=f"speaker {field}"), computed, abs_tol=1e-9):
            raise EvidenceError(f"speaker {field} does not match raw cosine samples")
    if payload.get("absolute_cosine_is_human_likeness_judgment") is not False:
        raise EvidenceError("absolute cosine cannot be treated as human likeness judgment")
    if payload.get("audio_and_embeddings_retained") != "local_only_uncommitted":
        raise EvidenceError("speaker audio and embeddings must remain local and uncommitted")
    if _number(payload.get("maximum_late_drop"), label="speaker maximum_late_drop") != manifest["thresholds"]["maximum_speaker_drop"]:
        raise EvidenceError("speaker maximum late drop must remain frozen at 0.05")
    if payload.get("autonomous_release_ready") not in {"pending_other_gates", "pass"}:
        raise EvidenceError("speaker autonomous readiness must remain separate from human acceptance")
    if payload.get("integrated_human_listening_status") != "pending" or payload.get("physical_call_status") != "pending":
        raise EvidenceError("speaker evidence must keep human listening and physical call pending")


def _verify_browser(payload: dict[str, Any], manifest: dict[str, Any]) -> None:
    if payload.get("web_url") != "https://192.168.1.199:8443" or payload.get("ai_health_url") != "https://192.168.1.199:9443/health":
        raise EvidenceError("browser evidence must use the canonical OMEN URLs")
    if payload.get("engine_id") != "qwen3_1_7b" or payload.get("mocked") is not False or payload.get("live_e2e_enabled") is not True:
        raise EvidenceError("browser evidence must be a real qwen3_1_7b live E2E")
    if payload.get("expected_commit") != payload.get("deployed_commit") or payload.get("observed_commit") != payload.get("deployed_commit"):
        raise EvidenceError("browser expected/observed/deployed commit mismatch")
    _validate_authorization(payload.get("reference_authorization"), manifest, label="browser reference_authorization")
    if payload.get("observed_events") != ["model_resident", "prompt_ready", "ai_audio_started", "ai_done"]:
        raise EvidenceError("browser readiness and call event order is incomplete")
    if int(_number(payload.get("test_exit_code"), label="browser test_exit_code")) != 0 or payload.get("browser_errors") != []:
        raise EvidenceError("browser live E2E did not pass cleanly")
    if payload.get("canonical_public_api") is not True:
        raise EvidenceError("browser call must use the canonical public API")
    if payload.get("integrated_human_listening_status") != "pending" or payload.get("physical_call_status") != "pending":
        raise EvidenceError("browser evidence must keep integrated listening and physical call pending")


def _verify_leak_scan(payload: dict[str, Any]) -> None:
    required = set(CORE_FILES.values()) | {DECISION_FILES["speaker"], DECISION_FILES["browser"]}
    scanned = payload.get("scanned_artifacts")
    if not isinstance(scanned, list) or not required <= set(scanned):
        raise EvidenceError("leak scan did not cover every committed release artifact")
    streams = payload.get("scanned_log_streams")
    if not isinstance(streams, list) or not {"ai-backend", "web-ui-server"} <= set(streams):
        raise EvidenceError("leak scan did not cover both service log streams")
    findings = payload.get("findings")
    if findings != []:
        raise EvidenceError("leak scan contains private-data findings")


def _load_bundle(
    results_dir: Path,
    names: dict[str, str],
    *,
    expected_commit: str | None,
    now: datetime,
    max_age_seconds: float,
) -> tuple[dict[str, dict[str, Any]], str]:
    payloads: dict[str, dict[str, Any]] = {}
    commit = expected_commit
    for artifact, filename in names.items():
        payload, observed = _artifact_header(
            _read_json(results_dir / filename),
            artifact=artifact,
            expected_commit=commit,
            now=now,
            max_age_seconds=max_age_seconds,
        )
        if commit is None:
            commit = observed
        payloads[artifact] = payload
    assert commit is not None
    return payloads, commit


def _verify_core_payloads(payloads: dict[str, dict[str, Any]], manifest: dict[str, Any]) -> None:
    gates = _gate_ids(payloads.values())
    missing_gates = CORE_CRITICAL_GATES - gates
    if missing_gates:
        raise EvidenceError(f"missing critical gate ids: {sorted(missing_gates)}")
    runtime_rows = _verify_runtime(payloads["runtime"], manifest)
    _verify_status(payloads["status"], manifest)
    call_rows = _verify_call_flow(payloads["call_flow"], manifest)
    soak_rows = _verify_soak(payloads["soak"], manifest)
    _verify_stt(payloads["stt"], manifest)
    scenarios = _scenario_map([*runtime_rows, *call_rows, *soak_rows], manifest)
    if set(scenarios) != EXPECTED_SCENARIOS:
        raise EvidenceError(f"missing scenario results: {sorted(EXPECTED_SCENARIOS - set(scenarios))}")
    expected_artifact = {row["scenario_id"]: row["evidence_artifact"] for row in manifest["scenarios"]}
    for artifact, rows in (("qwen3-runtime.json", runtime_rows), ("qwen3-call-flow.json", call_rows), ("qwen3-soak.json", soak_rows)):
        for row in rows:
            if expected_artifact[row["scenario_id"]] != artifact:
                raise EvidenceError(f"scenario {row['scenario_id']} was recorded in the wrong artifact")


def verify_core_ready(
    *,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    expected_commit: str | None = None,
    now: str | datetime | None = None,
) -> str:
    manifest = verify_contracts_only()
    if expected_commit is not None:
        _sha(expected_commit, label="expected commit", length=40)
    payloads, commit = _load_bundle(
        results_dir,
        CORE_FILES,
        expected_commit=expected_commit,
        now=_now(now),
        max_age_seconds=float(manifest["thresholds"]["max_evidence_age_seconds"]),
    )
    _verify_core_payloads(payloads, manifest)
    return commit


def verify_decision_ready(
    *,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    expected_commit: str | None = None,
    now: str | datetime | None = None,
) -> str:
    manifest = verify_contracts_only()
    verification_now = _now(now)
    core, commit = _load_bundle(
        results_dir,
        CORE_FILES,
        expected_commit=expected_commit,
        now=verification_now,
        max_age_seconds=float(manifest["thresholds"]["max_evidence_age_seconds"]),
    )
    _verify_core_payloads(core, manifest)
    decision, decision_commit = _load_bundle(
        results_dir,
        DECISION_FILES,
        expected_commit=commit,
        now=verification_now,
        max_age_seconds=float(manifest["thresholds"]["max_evidence_age_seconds"]),
    )
    if decision_commit != commit:
        raise EvidenceError("decision artifacts do not match the core deployed commit")
    gates = _gate_ids([*core.values(), *decision.values()])
    missing = set(REQUIRED_CRITICAL_GATES) - gates
    if missing:
        raise EvidenceError(f"missing critical/high release gates: {sorted(missing)}")
    _verify_speaker(decision["speaker"], manifest)
    _verify_browser(decision["browser"], manifest)
    _verify_leak_scan(decision["leak_scan"])
    for payload in [*core.values(), decision["speaker"], decision["browser"], decision["leak_scan"]]:
        verify_no_private_leaks(payload, label=f"decision-ready {payload['artifact']}")
    return commit


def _scenario_measurements(scenario_id: str) -> dict[str, Any]:
    stream = {
        "streaming_used": True,
        "fallback_used": False,
        "whole_wav_fallback_used": False,
        "valid_audio": True,
        "native_first_chunk_ms": 380.0,
        "native_generation_ms": 1800.0,
        "first_playback_ms": 720.0,
        "generation_complete_ms": 2100.0,
        "rtfx": 1.5,
        "natural_eos": True,
        "underflow_count": 0,
        "bridge_capacity": 2,
        "bridge_high_water": 2,
        "track_capacity_audio_ms": 1500.0,
        "track_high_water_audio_ms": 1320.0,
        "immediate_fields": ["first_chunk_generated_ms", "first_chunk_enqueued_ms", "ai_audio_started_ms"],
        "final_fields": sorted(FINAL_ONLY_FIELDS),
    }
    if scenario_id.startswith("clone-valid"):
        return stream
    if scenario_id.startswith("message-integrity"):
        return {**stream, "wer": 0.01, "final_word_pass": True}
    if scenario_id.startswith("alignment-tolerant"):
        return {"alignment_accepted": True, "prompt_ready": True, "token_coverage": 0.82, "edit_similarity": 0.78}
    if scenario_id == "alignment-invalid-blank":
        return {"alignment_accepted": False, "generation_started": False, "public_error_code": "qwen_reference_transcript_required"}
    if scenario_id == "alignment-invalid-known-mismatch":
        return {"alignment_accepted": False, "generation_started": False, "token_coverage": 0.1, "edit_similarity": 0.2}
    if scenario_id == "runaway-ceiling":
        return {"ceiling_triggered": True, "natural_eos": False, "max_new_tokens": 384, "audio_seconds": 31.0, "normal_ai_done_count": 0, "complete_persistence_count": 0}
    if scenario_id == "slow-stream-backpressure":
        return stream
    if scenario_id in {"cancel-after-audio", "cancel-before-audio", "hangup-and-switch-hangup", "hangup-and-switch-engine-switch"}:
        return {
            "cancel_ack_ms": 180.0,
            "late_audio_count": 0,
            "late_enqueue_count": 0,
            "normal_ai_done_count": 0,
            "complete_persistence_count": 0,
            "audio_started_count": 0 if scenario_id == "cancel-before-audio" else 1,
            "recovery": True,
        }
    if scenario_id == "worker-failure-sanitized":
        return {"stable_error_code": "qwen_runtime_failed", "backend_healthy": True, "other_engines_usable": True, "recovery": True, "private_leak_count": 0}
    if scenario_id == "canonical-deployed-call":
        return {"canonical_public_api": True, "normal_persistence_count": 1, "cancelled_persistence_count": 0, "late_audio_count": 0}
    if scenario_id == "runtime-identity-one-hot":
        return {"attested": True}
    if scenario_id == "hot-50-turn":
        return {"turn_count": 50}
    raise AssertionError(scenario_id)


def write_synthetic_bundle(results_dir: Path, *, deployed_commit: str, generated_at: str) -> None:
    """Create scalar-only passing fixtures used exclusively by verifier self-tests."""
    manifest = verify_contracts_only()
    _sha(deployed_commit, label="synthetic deployed commit", length=40)
    results_dir.mkdir(parents=True, exist_ok=True)
    scenario_defs = {row["scenario_id"]: row for row in manifest["scenarios"]}

    def scenario_row(scenario_id: str) -> dict[str, Any]:
        return {
            "scenario_id": scenario_id,
            "observed_events": scenario_defs[scenario_id]["expected_events"],
            "measurements": _scenario_measurements(scenario_id),
            "overall_status": True,
        }

    header = {"schema_version": 1, "phase": "09", "generated_at": generated_at, "deployed_commit": deployed_commit, "overall_status": True}
    runtime = {
        **header,
        "artifact": "runtime",
        "critical_gates": ["runtime_identity_cuda_one_hot"],
        "identity": {
            "engine_id": "qwen3_1_7b",
            "package": "faster-qwen3-tts==0.3.2",
            "runtime_source_commit": "a70afc0f81f7f5f8801c3227968f1102f43f211c",
            "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            "model_revision": "fd4b254389122332181a7c3db7f27e918eec64e3",
            "torch_version": "2.10.0+cu126",
            "torch_cuda_version": "12.6",
            "cuda_available": True,
            "device": "cuda",
            "gpu_name": "NVIDIA GeForce RTX 3060",
            "cpu_fallback_detected": False,
            "model_parameters_cuda_only": True,
            "resident_tts_count": 1,
            "resident_tts_engine": "qwen3_1_7b",
            "other_resident_engines": [],
            "torch_reserved_mib": 5604.0,
            "system_gpu_mib": 8348.0,
        },
        "scenario_results": [scenario_row("runtime-identity-one-hot")],
    }
    status = {
        **header,
        "artifact": "status",
        "critical_gates": ["reference_authorization"],
        "readiness": {"model_state": "resident", "resident_engine": "qwen3_1_7b", "prompt_state": "ready", "loading_engine": None, "resident_tts_count": 1},
        "prompt_cache": {"capacity": 1, "high_water": 1},
        "output_limits": {"bounded": True, "max_segment_words": 60, "max_new_tokens": 384, "max_audio_seconds": 32.0},
        "reference_authorization": copy.deepcopy(manifest["selected_fixture"]),
        "acceptance_status": {
            "autonomous_release_ready": "pending_decision_gates",
            "integrated_human_listening_status": "pending",
            "physical_call_status": "pending",
            "candidate_spike_listening_status": "accepted_separately",
        },
    }
    call_ids = [row["scenario_id"] for row in manifest["scenarios"] if row["evidence_artifact"] == "qwen3-call-flow.json"]
    call_flow = {
        **header,
        "artifact": "call_flow",
        "critical_gates": [
            "all_scenarios_observed",
            "early_playback_before_completion",
            "bounded_bridge_and_track",
            "no_whole_synthesis_fallback",
            "terminal_safe_cancellation",
        ],
        "scenario_results": [scenario_row(scenario_id) for scenario_id in call_ids],
        "reference_authorization": copy.deepcopy(manifest["selected_fixture"]),
    }
    turns = []
    anchor_hash = "f" * 64
    for turn in range(1, 51):
        turns.append(
            {
                "turn": turn,
                "valid_audio": True,
                "natural_eos": True,
                "streaming_used": True,
                "fallback_used": False,
                "whole_wav_fallback_used": False,
                "first_playback_ms": 700.0 + turn * 0.1,
                "generation_complete_ms": 1800.0 + turn,
                "rtfx": 1.5,
                "underflow_count": 0,
                "peak": 0.72,
                "silence_fraction": 0.08,
                "clipping_fraction": 0.0,
                "ttfa_ms": 380.0 + turn * 0.1,
                "rms_db": -18.0 - turn * 0.001,
                "spectral_centroid_hz": 2100.0 - turn,
                "spectral_flatness": 0.05,
                "torch_reserved_mib": 5604.0,
                "system_gpu_mib": 8348.0,
                "audio_sha256": f"{turn:064x}",
                "source_audio_sha256": (
                    anchor_hash
                    if turn in manifest["seed_policy"]["anchor_turns"]
                    else f"{turn + 100:064x}"
                ),
                "anchor_sha256": anchor_hash if turn in manifest["seed_policy"]["anchor_turns"] else None,
            }
        )
    soak = {
        **header,
        "artifact": "soak",
        "critical_gates": ["fifty_turn_non_degradation"],
        "turns": turns,
        "scenario_results": [scenario_row("hot-50-turn")],
    }
    stt = {
        **header,
        "artifact": "stt",
        "critical_gates": ["spoken_message_integrity"],
        "samples": [{"turn": turn, "accepted": True, "wer": 0.01 if turn % 10 == 0 else 0.0, "final_word_pass": True} for turn in range(1, 51)],
        "message_integrity": [
            {"scenario_id": scenario_id, "wer": 0.01, "final_word_pass": True, "consequential_terms_pass": True}
            for scenario_id in (
                "message-integrity-names-numbers",
                "message-integrity-negation-abbreviations",
                "message-integrity-punctuation-final-word",
            )
        ],
    }
    scorer = manifest["speaker_scorer"]
    speaker = {
        **header,
        "artifact": "speaker",
        "critical_gates": [],
        "baseline_commit": deployed_commit,
        "reference_sha256": manifest["selected_fixture"]["reference_sha256"],
        "scorer": {
            "model_id": scorer["model_id"],
            "model_revision": scorer["model_revision"],
            "model_class": scorer["model_class"],
            "transformers_version": scorer["transformers_version"],
            "torch_version": manifest["runtime"]["torch_version"],
            "torch_cuda_version": manifest["runtime"]["cuda_version"],
            "device": "cuda:0",
            "gpu_name": "NVIDIA GeForce RTX 3060",
            "sample_rate_hz": 16000,
            "local_files_only": True,
        },
        "baseline_scores": [{"bucket_id": bucket, "audio_sha256": str(index) * 64, "cosine": 0.82} for index, bucket in enumerate(("short", "medium", "long"), 1)],
        "early_scores": [{"bucket_id": turn, "audio_sha256": f"{turn:064x}", "cosine": 0.81} for turn in range(1, 6)],
        "middle_scores": [{"bucket_id": turn, "audio_sha256": f"{turn:064x}", "cosine": 0.805} for turn in range(23, 28)],
        "late_scores": [{"bucket_id": turn, "audio_sha256": f"{turn:064x}", "cosine": 0.80} for turn in range(46, 51)],
        "integrated_baseline_median": 0.82,
        "early_median": 0.81,
        "middle_median": 0.805,
        "late_median": 0.80,
        "late_minus_early": -0.01,
        "late_minus_integrated_baseline": -0.02,
        "speaker_stability_gate": True,
        "absolute_cosine_is_human_likeness_judgment": False,
        "audio_and_embeddings_retained": "local_only_uncommitted",
        "maximum_late_drop": 0.05,
        "autonomous_release_ready": "pending_other_gates",
        "integrated_human_listening_status": "pending",
        "physical_call_status": "pending",
    }
    browser = {
        **header,
        "artifact": "browser",
        "critical_gates": [],
        "web_url": "https://192.168.1.199:8443",
        "ai_health_url": "https://192.168.1.199:9443/health",
        "engine_id": "qwen3_1_7b",
        "expected_commit": deployed_commit,
        "observed_commit": deployed_commit,
        "reference_authorization": copy.deepcopy(manifest["selected_fixture"]),
        "observed_events": ["model_resident", "prompt_ready", "ai_audio_started", "ai_done"],
        "test_exit_code": 0,
        "browser_errors": [],
        "canonical_public_api": True,
        "mocked": False,
        "live_e2e_enabled": True,
        "integrated_human_listening_status": "pending",
        "physical_call_status": "pending",
    }
    leak_scan = {
        **header,
        "artifact": "leak_scan",
        "critical_gates": ["private_evidence_clean"],
        "scanned_artifacts": [*CORE_FILES.values(), DECISION_FILES["speaker"], DECISION_FILES["browser"]],
        "scanned_log_streams": ["ai-backend", "web-ui-server"],
        "findings": [],
    }
    payloads = {"runtime": runtime, "status": status, "call_flow": call_flow, "soak": soak, "stt": stt, "speaker": speaker, "browser": browser, "leak_scan": leak_scan}
    for artifact, filename in {**CORE_FILES, **DECISION_FILES}.items():
        _write_json(results_dir / filename, payloads[artifact])


def _mutate(path: Path, change: Callable[[dict[str, Any]], None]) -> None:
    payload = _object(_read_json(path), label=path.name)
    change(payload)
    _write_json(path, payload)


def _call_scenario(payload: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    return next(row for row in payload["scenario_results"] if row["scenario_id"] == scenario_id)


def _self_test_cases() -> list[tuple[str, str, Callable[[Path], None]]]:
    call = CORE_FILES["call_flow"]
    return [
        ("false-overall-status", "core", lambda root: _mutate(root / CORE_FILES["soak"], lambda p: (p.__setitem__("overall_status", True), p["turns"][-1].__setitem__("natural_eos", False)))),
        ("stale-timestamp", "core", lambda root: _mutate(root / CORE_FILES["runtime"], lambda p: p.__setitem__("generated_at", "2026-07-29T00:00:00Z"))),
        ("deployed-commit-mismatch", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p.__setitem__("deployed_commit", "b" * 40))),
        ("whole-synthesis-fallback", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "clone-valid-short")["measurements"].__setitem__("whole_wav_fallback_used", True))),
        ("missing-critical-gate", "core", lambda root: _mutate(root / call, lambda p: p["critical_gates"].remove("bounded_bridge_and_track"))),
        ("missing-scenario", "core", lambda root: _mutate(root / call, lambda p: p.__setitem__("scenario_results", p["scenario_results"][1:]))),
        ("authorization-missing", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p.pop("reference_authorization"))),
        ("authorization-malformed", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p.__setitem__("reference_authorization", "invalid"))),
        ("authorization-wrong-reference-hash", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p["reference_authorization"].__setitem__("reference_sha256", "0" * 64))),
        ("authorization-wrong-transcript-hash", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p["reference_authorization"].__setitem__("transcript_sha256", "0" * 64))),
        ("authorization-wrong-scope", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p["reference_authorization"].__setitem__("use_scope", "internet_publication"))),
        ("bridge-capacity-absent", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "slow-stream-backpressure")["measurements"].pop("bridge_capacity"))),
        ("bridge-high-water-unbounded", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "slow-stream-backpressure")["measurements"].__setitem__("bridge_high_water", 3))),
        ("track-capacity-absent", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "slow-stream-backpressure")["measurements"].pop("track_capacity_audio_ms"))),
        ("track-high-water-unbounded", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "slow-stream-backpressure")["measurements"].__setitem__("track_high_water_audio_ms", 1600.0))),
        ("speaker-late-drop", "decision", lambda root: _mutate(root / DECISION_FILES["speaker"], lambda p: [row.__setitem__("cosine", 0.70) for row in p["late_scores"]])),
        ("speaker-baseline-drop", "decision", lambda root: _mutate(root / DECISION_FILES["speaker"], lambda p: [row.__setitem__("cosine", 0.90) for row in p["baseline_scores"]])),
        ("private-path-leak", "decision", lambda root: _mutate(root / call, lambda p: p.__setitem__("debug_value", "C:\\Users\\private\\voice"))),
        ("full-transcript-leak", "decision", lambda root: _mutate(root / call, lambda p: p.__setitem__("reference_transcript", "the complete private transcript sentinel"))),
        ("base64-audio-leak", "decision", lambda root: _mutate(root / call, lambda p: p.__setitem__("wav_b64", "A" * 1024))),
        ("access-token-leak", "decision", lambda root: _mutate(root / call, lambda p: p.__setitem__("authorization_header", "Bearer rayme_secret_access_token_1234567890"))),
        ("forbidden-audio-extension-leak", "decision", lambda root: _mutate(root / call, lambda p: p.__setitem__("sample", "results/private-reference.wav"))),
        ("cpu-substitution", "core", lambda root: _mutate(root / CORE_FILES["runtime"], lambda p: p["identity"].__setitem__("device", "cpu"))),
        ("model-substitution", "core", lambda root: _mutate(root / CORE_FILES["runtime"], lambda p: p["identity"].__setitem__("model_revision", "0" * 40))),
        ("non-natural-eos", "core", lambda root: _mutate(root / CORE_FILES["soak"], lambda p: p["turns"][49].__setitem__("natural_eos", False))),
        ("active-playout-underflow", "core", lambda root: _mutate(root / CORE_FILES["soak"], lambda p: p["turns"][20].__setitem__("underflow_count", 1))),
        ("realtime-supply-failure", "core", lambda root: _mutate(root / CORE_FILES["soak"], lambda p: p["turns"][30].__setitem__("rtfx", 1.0))),
        ("late-audio-after-cancel", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "cancel-after-audio")["measurements"].__setitem__("late_audio_count", 1))),
        ("ai-done-after-cancel", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "cancel-after-audio")["measurements"].__setitem__("normal_ai_done_count", 1))),
        ("persistence-after-cancel", "core", lambda root: _mutate(root / call, lambda p: _call_scenario(p, "cancel-after-audio")["measurements"].__setitem__("complete_persistence_count", 1))),
        ("unbounded-prompt-cache", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p["prompt_cache"].__setitem__("capacity", 2))),
        ("unbounded-output-ceiling", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p["output_limits"].__setitem__("max_new_tokens", 385))),
        ("missing-human-pending-separation", "core", lambda root: _mutate(root / CORE_FILES["status"], lambda p: p["acceptance_status"].pop("integrated_human_listening_status"))),
    ]


def run_self_tests() -> list[str]:
    passed: list[str] = []
    commit = "a" * 40
    generated_at = "2026-07-31T00:00:00Z"
    verification_time = "2026-07-31T01:00:00Z"
    with tempfile.TemporaryDirectory(prefix="rayme-phase09-verifier-") as temp:
        root = Path(temp)
        for name, mode, mutate in _self_test_cases():
            case_dir = root / name
            case_dir.mkdir()
            write_synthetic_bundle(case_dir, deployed_commit=commit, generated_at=generated_at)
            mutate(case_dir)
            try:
                if mode == "decision":
                    verify_decision_ready(results_dir=case_dir, expected_commit=commit, now=verification_time)
                else:
                    verify_core_ready(results_dir=case_dir, expected_commit=commit, now=verification_time)
            except EvidenceError:
                passed.append(name)
            else:
                raise EvidenceError(f"self-test mutation was falsely accepted: {name}")
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts-only", action="store_true")
    parser.add_argument("--core-ready", action="store_true")
    parser.add_argument("--decision-ready", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--print-deployed-commit", action="store_true")
    parser.add_argument("--expected-commit")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    modes = [args.contracts_only, args.core_ready, args.decision_ready, args.self_test, args.print_deployed_commit]
    if sum(bool(mode) for mode in modes) != 1:
        parser.error("choose exactly one verification mode")
    try:
        if args.contracts_only:
            verify_contracts_only()
        elif args.core_ready:
            verify_core_ready(results_dir=args.results_dir, expected_commit=args.expected_commit, now=args.now)
        elif args.decision_ready:
            verify_decision_ready(results_dir=args.results_dir, expected_commit=args.expected_commit, now=args.now)
        elif args.self_test:
            for name in run_self_tests():
                print(f"PASS self-test: {name}")
        else:
            commit = verify_core_ready(results_dir=args.results_dir, expected_commit=args.expected_commit, now=args.now)
            print(commit)
            return 0
    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
