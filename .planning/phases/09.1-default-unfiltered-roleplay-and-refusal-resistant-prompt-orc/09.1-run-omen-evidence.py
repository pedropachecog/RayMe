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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run sanitized Phase 09.1 evidence probes")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.preflight:
        parser.error("exactly one runner mode is required")
    try:
        payload = collect_preflight(LiveReadOnlyProbe())
        write_json_atomic(args.output, payload)
    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: read-only provider preflight recorded sanitized evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
