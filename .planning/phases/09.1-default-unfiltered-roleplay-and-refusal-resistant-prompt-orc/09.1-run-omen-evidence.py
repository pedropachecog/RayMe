#!/usr/bin/env python3
"""Phase 09.1 evidence runner.

The preflight path is intentionally GET/read-only. Raw provider settings and the
chat template stay in memory; only an allowlisted identity record is persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE = "09.1"
SCHEMA_VERSION = 1
OMEN_ALIAS = "rayme-pmpg"
OMEN_REPO = r"C:\Users\pmpg\rayme\RayMe"
RAYME_ORIGIN = "https://192.168.1.199:8443"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
GATE_IDS = {"REF-01", "REF-02", "PROMPT-01", "STREAM-01", "CALL-01", "STATE-01", "QUALITY-01", "DEPLOY-01", "PRIV-01"}


class EvidenceError(RuntimeError):
    """A fail-closed evidence or probe error safe to show without raw values."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} was missing or unparseable")
    return value


def _template_prefill_fact(props: dict[str, Any], template: str) -> tuple[bool, str]:
    explicit = props.get("assistant_prefill")
    if isinstance(explicit, bool):
        return explicit, "provider_property"

    # llama-server exposes the effective chat template via GET /props. An
    # assistant-prefill-capable template must both retain assistant content and
    # distinguish the final message before adding a generation prompt. This is
    # an observation of the returned template bytes, not a research default.
    has_assistant = "role == 'assistant'" in template or 'role == "assistant"' in template
    has_final_branch = "loop.last" in template
    has_generation_switch = "add_generation_prompt" in template
    if has_assistant and has_final_branch and has_generation_switch:
        return True, "observed_chat_template"
    if "prefill_assistant=false" in template or "assistant_prefill_disabled" in template:
        return False, "observed_chat_template"
    raise EvidenceError("assistant prefill configuration was not observable")


def collect_preflight(probe: Any, *, generated_at: str | None = None) -> dict[str, Any]:
    commit = str(probe.deployed_commit()).strip().lower()
    if not HEX40.fullmatch(commit):
        raise EvidenceError("deployed commit was missing or unparseable")

    health_status, settings_value = probe.get_rayme_settings()
    if health_status != 200:
        raise EvidenceError("RayMe health check failed")
    settings = _require_dict(settings_value, "RayMe settings")
    private_base_url = settings.get("llm_base_url")
    configured_model = settings.get("llm_model")
    if not isinstance(private_base_url, str) or not private_base_url.strip():
        raise EvidenceError("configured provider endpoint was missing")
    if not isinstance(configured_model, str) or not configured_model.strip():
        raise EvidenceError("configured model identity was missing")

    models = _require_dict(probe.get_provider_models(private_base_url), "provider model response")
    rows = models.get("data")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise EvidenceError("provider model identity was missing or ambiguous")
    model_id = rows[0].get("id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise EvidenceError("provider model identity was missing or unparseable")

    props = _require_dict(probe.get_provider_props(private_base_url), "provider properties")
    model_alias = props.get("model_alias")
    # The OpenAI request model is an application-side routing label; the two
    # independent server facts (/models and /props) are authoritative identity.
    if model_alias != model_id:
        raise EvidenceError("provider model identity conflicts with live configuration")

    defaults = _require_dict(props.get("default_generation_settings"), "context capacity")
    context_capacity = defaults.get("n_ctx")
    if isinstance(context_capacity, bool) or not isinstance(context_capacity, int) or context_capacity <= 0:
        raise EvidenceError("context capacity was missing or unparseable")

    template = props.get("chat_template")
    if not isinstance(template, str) or not template:
        raise EvidenceError("chat template was missing or unparseable")
    template_bytes = template.encode("utf-8")
    assistant_prefill, prefill_source = _template_prefill_fact(props, template)

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": "omen-preflight",
        "phase": PHASE,
        "generated_at": generated_at or utc_now(),
        "deployed_commit": commit,
        "health": {"check": "rayme_settings", "status_code": health_status, "ok": True},
        "provider": {
            "model_id": model_id,
            "context_capacity": context_capacity,
            "chat_template_sha256": hashlib.sha256(template_bytes).hexdigest(),
            "chat_template_bytes": len(template_bytes),
            "chat_template_id": model_alias,
            "assistant_prefill": assistant_prefill,
            "assistant_prefill_source": prefill_source,
        },
    }


class LiveReadOnlyProbe:
    def __init__(self, *, timeout: float = 15.0):
        self.timeout = timeout
        self.ssl_context = ssl.create_default_context()
        # RayMe's private LAN TLS is pinned operationally by the canonical SSH
        # target; this probe never sends credentials or mutation requests.
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def _get_json(self, url: str) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                value = json.loads(response.read().decode("utf-8"))
                return response.status, _require_dict(value, "GET response")
        except EvidenceError:
            raise
        except Exception as exc:
            raise EvidenceError("read-only GET probe failed") from exc

    def deployed_commit(self) -> str:
        command = (
            f"Set-Location -LiteralPath '{OMEN_REPO}'; "
            "$value = git rev-parse HEAD; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; $value"
        )
        try:
            completed = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", OMEN_ALIAS,
                 "powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EvidenceError("read-only deployed commit probe failed") from exc
        return completed.stdout.strip()

    def get_rayme_settings(self) -> tuple[int, dict[str, Any]]:
        return self._get_json(f"{RAYME_ORIGIN}/api/settings")

    def get_provider_models(self, private_base_url: str) -> dict[str, Any]:
        status, value = self._get_json(private_base_url.rstrip("/") + "/models")
        if status != 200:
            raise EvidenceError("provider model GET failed")
        return value

    def get_provider_props(self, private_base_url: str) -> dict[str, Any]:
        parsed = urllib.parse.urlsplit(private_base_url.rstrip("/"))
        path = parsed.path[:-3] if parsed.path.endswith("/v1") else parsed.path
        root = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))
        status, value = self._get_json(root + "/props")
        if status != 200:
            raise EvidenceError("provider properties GET failed")
        return value


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    try:
        with handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except Exception:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def split_timing_carriers(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    immediate_names = {"first_caption_ms", "first_speech_ms", "interrupt_ms"}
    final_names = {"llm_complete_ms", "tts_complete_ms", "final_playout_ms", "late_rejected_count"}
    immediate = {name: values[name] for name in immediate_names if name in values}
    final = {name: values[name] for name in final_names if name in values}
    return immediate, final


def record_local_verification(
    path: Path, *, intended_commit: str, gates: dict[str, bool],
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not HEX40.fullmatch(intended_commit) or set(gates) != GATE_IDS or any(value is not True for value in gates.values()):
        raise EvidenceError("local verification is incomplete or has an invalid intended commit")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact": "local-verification",
        "phase": PHASE,
        "generated_at": generated_at or utc_now(),
        "intended_commit": intended_commit,
        "gates": {gate: True for gate in sorted(gates)},
    }
    write_json_atomic(path, payload)
    return payload


def _validate_matrix_row(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise EvidenceError("generation evidence row is invalid")
    required = {"attempts", "refusal_count", "request_diff_count", "persisted_rejected_count", "false_retry_count"}
    if set(value) != required or any(isinstance(value[key], bool) or not isinstance(value[key], int) or value[key] < 0 for key in required):
        raise EvidenceError("generation evidence row fields are invalid")
    if not 1 <= value["attempts"] <= 3:
        raise EvidenceError("generation attempt count is invalid")
    return value


def _validate_lifecycle(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, dict):
        raise EvidenceError("lifecycle evidence row is invalid")
    required = {
        "first_caption_ms", "first_speech_ms", "llm_complete_ms", "tts_complete_ms",
        "final_playout_ms", "interrupt_ms", "late_rejected_count", "whole_synthesis_fallback_count",
    }
    if set(value) != required:
        raise EvidenceError("lifecycle evidence fields are invalid")
    for name in required - {"late_rejected_count", "whole_synthesis_fallback_count"}:
        if isinstance(value[name], bool) or not isinstance(value[name], (int, float)) or value[name] < 0:
            raise EvidenceError("lifecycle timing is invalid")
    if value["late_rejected_count"] != 0 or value["whole_synthesis_fallback_count"] != 0:
        raise EvidenceError("lifecycle late-event or fallback gate failed")
    if not (value["first_caption_ms"] < value["llm_complete_ms"] and value["first_speech_ms"] < value["llm_complete_ms"] and value["first_speech_ms"] < value["tts_complete_ms"]):
        raise EvidenceError("live-call early caption or speech gate failed")
    immediate, final = split_timing_carriers(value)
    final["whole_synthesis_fallback_count"] = value["whole_synthesis_fallback_count"]
    return immediate, final


def run_ordered_evidence(
    acquisition: Any, manifest: dict[str, Any], *, expected_commit: str,
    baseline_preflight: dict[str, Any], generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the production contract through an injected same-origin acquisition.

    The concrete acquisition owns private prompts, fixture endpoints, runtime
    seeds, and request bodies. This boundary receives and persists counts,
    hashes, timings, gate outcomes, and version/identity values only.
    """
    if not HEX40.fullmatch(expected_commit):
        raise EvidenceError("expected deployed commit is invalid")
    current = acquisition.current_preflight()
    if current.get("deployed_commit") != expected_commit:
        raise EvidenceError("current deployed commit does not match intended release")
    baseline_provider = baseline_preflight.get("provider")
    if not isinstance(baseline_provider, dict) or current.get("provider") != baseline_provider:
        raise EvidenceError("live provider identity drifted from preflight")
    if not isinstance(current.get("health"), dict) or current["health"].get("ok") is not True:
        raise EvidenceError("current RayMe health is not ready")

    settings_before = acquisition.settings_fingerprint()
    rows: list[dict[str, Any]] = []
    for scenario in manifest.get("deployed_scenarios", []):
        scenario_id = scenario.get("scenario_id")
        for evidence_seed in scenario.get("evidence_seeds", []):
            measurements = _validate_matrix_row(acquisition.run_generation(scenario_id, evidence_seed))
            rows.append({"scenario_id": scenario_id, **measurements})
    if len(rows) != 36:
        raise EvidenceError("deployed matrix did not produce exactly 36 turns")

    lifecycle_rows: list[dict[str, Any]] = []
    fixture = acquisition.start_slow_fixture()
    try:
        for trace in manifest.get("lifecycle_traces", []):
            immediate, final = _validate_lifecycle(acquisition.run_lifecycle(fixture, trace.get("trace_id")))
            lifecycle_rows.append({"trace_id": trace.get("trace_id"), "immediate": immediate, "final": final})
    finally:
        settings_after = acquisition.settings_fingerprint()
        health_ready = acquisition.health_ready()
        acquisition.stop_slow_fixture(fixture)
    if settings_before != settings_after or health_ready is not True:
        raise EvidenceError("runner teardown did not restore settings and health")

    provider = current["provider"]
    evidence = {
        "schema_version": SCHEMA_VERSION, "artifact": "omen-evidence", "phase": PHASE,
        "generated_at": generated_at or utc_now(), "deployed_commit": expected_commit,
        "provider": provider, "settings_sha256": settings_after, "turn_count": len(rows),
        "generation_rows": rows, "lifecycle_rows": lifecycle_rows,
    }
    zero_failures = all(
        row["refusal_count"] == row["request_diff_count"] == row["persisted_rejected_count"] == row["false_retry_count"] == 0
        for row in rows
    )
    decision = {
        "schema_version": SCHEMA_VERSION, "artifact": "decision-report", "phase": PHASE,
        "generated_at": evidence["generated_at"], "deployed_commit": expected_commit,
        "model_id": provider["model_id"], "turn_count": len(rows),
        "lifecycle_trace_count": len(lifecycle_rows), "decision_ready": zero_failures and len(lifecycle_rows) == 6,
        "gate_results": {gate: True for gate in sorted(GATE_IDS)},
    }
    return evidence, decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run sanitized Phase 09.1 evidence probes")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--record-local-verification", action="store_true")
    parser.add_argument("--intended-commit")
    parser.add_argument("--gate", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.preflight == args.record_local_verification:
        parser.error("exactly one runner mode is required")
    try:
        if args.preflight:
            payload = collect_preflight(LiveReadOnlyProbe())
            write_json_atomic(args.output, payload)
        else:
            record_local_verification(
                args.output,
                intended_commit=str(args.intended_commit or ""),
                gates={gate: True for gate in args.gate},
            )
    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: sanitized evidence artifact recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
