#!/usr/bin/env python3
"""Independent, fail-closed verifier for Phase 09.1 shared evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = PHASE_DIR / "09.1-evidence-manifest.json"
RESULTS_DIR = PHASE_DIR / "results"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
GATES = {"REF-01","REF-02","PROMPT-01","STREAM-01","CALL-01","STATE-01","QUALITY-01","DEPLOY-01","PRIV-01"}
RESULTS = {"results/omen-preflight.json","results/local-verification.json","results/omen-evidence.json","results/decision-report.json"}
FORBIDDEN_KEYS = {"prompt","prompts","history","messages","response","rejected_prose","authorization","authorization_header","api_key","credential","secret","runtime_seed","seed","audio","wav","transcript","path","url"}

class EvidenceError(RuntimeError):
    pass

def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"required artifact unavailable: {path.name}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"artifact is not an object: {path.name}")
    return value

def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EvidenceError("timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("timestamp is unparseable") from exc
    if parsed.tzinfo is None:
        raise EvidenceError("timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)

def verify_shared_privacy(value: Any, *, key: str = "root") -> None:
    normalized = key.lower().replace("-", "_")
    if normalized in FORBIDDEN_KEYS or any(token in normalized for token in ("credential","secret","runtime_seed","private_path")):
        raise EvidenceError(f"forbidden shared evidence field: {key}")
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise EvidenceError("shared evidence key is not a string")
            verify_shared_privacy(child, key=child_key)
    elif isinstance(value, list):
        for child in value:
            verify_shared_privacy(child, key=key)
    elif isinstance(value, str):
        lower = value.lower()
        if re.search(r"(?:[a-z]:\\|/home/|/users/|file://)", lower):
            raise EvidenceError("private path in shared evidence")
        if "bearer " in lower or lower.endswith((".wav",".mp3",".flac",".ogg")):
            raise EvidenceError("secret or audio in shared evidence")
        if len(value) > 256:
            raise EvidenceError("unbounded prose in shared evidence")
    elif value is None or isinstance(value, (bool, int)):
        return
    elif not isinstance(value, float) or not math.isfinite(value):
        raise EvidenceError("unsupported shared evidence value")

def verify_preflight(payload: dict[str, Any], *, expected_provider: dict[str, Any] | None = None, now: str | None = None, max_age_seconds: int = 3600) -> dict[str, Any]:
    if payload.get("schema_version") != 1 or payload.get("artifact") != "omen-preflight" or payload.get("phase") != "09.1":
        raise EvidenceError("preflight schema identity mismatch")
    if not HEX40.fullmatch(str(payload.get("deployed_commit", ""))):
        raise EvidenceError("preflight commit is invalid")
    health = payload.get("health")
    if not isinstance(health, dict) or health.get("ok") is not True or health.get("status_code") != 200:
        raise EvidenceError("preflight health is not ready")
    provider = payload.get("provider")
    required = {"model_id","context_capacity","chat_template_sha256","chat_template_bytes","chat_template_id","assistant_prefill","assistant_prefill_source"}
    if not isinstance(provider, dict) or set(provider) != required:
        raise EvidenceError("preflight provider identity fields mismatch")
    if not isinstance(provider["model_id"], str) or not provider["model_id"]:
        raise EvidenceError("preflight model identity is invalid")
    if not isinstance(provider["context_capacity"], int) or isinstance(provider["context_capacity"], bool) or provider["context_capacity"] <= 0:
        raise EvidenceError("preflight context capacity is invalid")
    if not HEX64.fullmatch(str(provider["chat_template_sha256"])) or not isinstance(provider["chat_template_bytes"], int) or provider["chat_template_bytes"] <= 0:
        raise EvidenceError("preflight template identity is invalid")
    if not isinstance(provider["assistant_prefill"], bool):
        raise EvidenceError("preflight assistant prefill is invalid")
    reference_now = _timestamp(now) if now else datetime.now(timezone.utc)
    age = (reference_now - _timestamp(payload.get("generated_at"))).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise EvidenceError("preflight is stale")
    if expected_provider is not None and provider != expected_provider:
        raise EvidenceError("preflight provider identity changed")
    verify_shared_privacy(payload)
    return provider

def verify_contracts_only() -> dict[str, int]:
    manifest = _load(MANIFEST_PATH)
    if manifest.get("schema_version") != 1 or manifest.get("phase") != "09.1":
        raise EvidenceError("manifest identity mismatch")
    scenarios = manifest.get("deployed_scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 12:
        raise EvidenceError("deployed scenario inventory mismatch")
    ids = [row.get("scenario_id") for row in scenarios if isinstance(row, dict)]
    seeds = [seed for row in scenarios for seed in row.get("evidence_seeds", [])]
    if len(set(ids)) != 12 or len(seeds) != 36 or len(set(seeds)) != 36 or not all(isinstance(seed, int) for seed in seeds):
        raise EvidenceError("deployed three-seed matrix mismatch")
    if manifest.get("ordinary_runtime_seed_policy") != "fresh_undisclosed_per_attempt":
        raise EvidenceError("ordinary runtime seed policy mismatch")
    if set(manifest.get("critical_gate_ids", [])) != GATES or set(manifest.get("generated_results", [])) != RESULTS:
        raise EvidenceError("gate or result inventory mismatch")
    for field, count in (("lifecycle_traces",6),("request_golds",8),("quality_cases",8)):
        rows = manifest.get(field)
        if not isinstance(rows, list) or len(rows) != count:
            raise EvidenceError(f"{field} inventory mismatch")
    # The manifest describes forbidden classes by name; scan runtime artifacts,
    # not this policy declaration itself.
    preflight = _load(RESULTS_DIR / "omen-preflight.json")
    verify_preflight(preflight)
    return {"deployed_turns":len(seeds),"gate_count":len(GATES),"result_shape_count":len(RESULTS)}

def verify_local_release(*, results_dir: Path, expected_commit: str, now: str | None = None) -> str:
    if not HEX40.fullmatch(expected_commit):
        raise EvidenceError("expected intended commit is invalid")
    payload = _load(results_dir / "local-verification.json")
    if payload.get("schema_version") != 1 or payload.get("artifact") != "local-verification" or payload.get("phase") != "09.1":
        raise EvidenceError("local verification schema mismatch")
    if payload.get("intended_commit") != expected_commit:
        raise EvidenceError("local verification intended commit mismatch")
    if payload.get("gates") != {gate: True for gate in sorted(GATES)}:
        raise EvidenceError("local verification gates incomplete")
    reference_now = _timestamp(now) if now else datetime.now(timezone.utc)
    age = (reference_now - _timestamp(payload.get("generated_at"))).total_seconds()
    if age < 0 or age > 86400:
        raise EvidenceError("local verification is stale")
    verify_shared_privacy(payload)
    return expected_commit

def verify_decision_ready(*, results_dir: Path, expected_commit: str, now: str | None = None) -> str:
    preflight = _load(results_dir / "omen-preflight.json")
    provider = verify_preflight(preflight, now=now)
    evidence = _load(results_dir / "omen-evidence.json")
    report = _load(results_dir / "decision-report.json")
    if evidence.get("artifact") != "omen-evidence" or report.get("artifact") != "decision-report":
        raise EvidenceError("decision artifact schema mismatch")
    if evidence.get("deployed_commit") != expected_commit or report.get("deployed_commit") != expected_commit:
        raise EvidenceError("deployed commit mismatch")
    if evidence.get("provider") != provider or report.get("model_id") != provider.get("model_id"):
        raise EvidenceError("provider identity mismatch")
    rows = evidence.get("generation_rows")
    traces = evidence.get("lifecycle_rows")
    if not isinstance(rows, list) or len(rows) != 36 or evidence.get("turn_count") != 36:
        raise EvidenceError("deployed matrix count mismatch")
    for row in rows:
        if not isinstance(row, dict) or any(row.get(key) != 0 for key in ("refusal_count","request_diff_count","persisted_rejected_count","false_retry_count")):
            raise EvidenceError("deployed matrix raw gate failed")
        if not isinstance(row.get("attempts"), int) or not 1 <= row["attempts"] <= 3:
            raise EvidenceError("deployed attempt gate failed")
    if not isinstance(traces, list) or len(traces) != 6:
        raise EvidenceError("lifecycle trace count mismatch")
    for trace in traces:
        immediate, final = trace.get("immediate"), trace.get("final")
        if not isinstance(immediate, dict) or not isinstance(final, dict):
            raise EvidenceError("lifecycle timing carrier mismatch")
        if set(immediate) - {"first_caption_ms","first_speech_ms","interrupt_ms"}:
            raise EvidenceError("immediate carrier contains final timing")
        if final.get("late_rejected_count") != 0 or final.get("whole_synthesis_fallback_count") != 0:
            raise EvidenceError("lifecycle late/fallback gate failed")
        if not (immediate.get("first_caption_ms", math.inf) < final.get("llm_complete_ms", -1) and immediate.get("first_speech_ms", math.inf) < final.get("llm_complete_ms", -1) and immediate.get("first_speech_ms", math.inf) < final.get("tts_complete_ms", -1)):
            raise EvidenceError("lifecycle early playback gate failed")
    recomputed_ready = len(rows) == 36 and len(traces) == 6
    if report.get("turn_count") != 36 or report.get("lifecycle_trace_count") != 6 or report.get("decision_ready") is not recomputed_ready or report.get("gate_results") != {gate: True for gate in sorted(GATES)}:
        raise EvidenceError("decision report does not match recomputation")
    verify_shared_privacy(evidence)
    verify_shared_privacy(report)
    return expected_commit

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 09.1 evidence")
    parser.add_argument("--contracts-only", action="store_true")
    parser.add_argument("--local-release", action="store_true")
    parser.add_argument("--decision-ready", action="store_true")
    parser.add_argument("--expected-commit")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    if sum((args.contracts_only, args.local_release, args.decision_ready)) != 1:
        parser.error("a verifier mode is required")
    try:
        if args.contracts_only:
            counts = verify_contracts_only()
            detail = f"contracts ({counts['deployed_turns']} deployed turns, {counts['gate_count']} critical gates)"
        elif args.local_release:
            verify_local_release(results_dir=args.results_dir, expected_commit=str(args.expected_commit or ""), now=args.now)
            detail = "local release"
        else:
            verify_decision_ready(results_dir=args.results_dir, expected_commit=str(args.expected_commit or ""), now=args.now)
            detail = "decision ready"
    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {detail}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
