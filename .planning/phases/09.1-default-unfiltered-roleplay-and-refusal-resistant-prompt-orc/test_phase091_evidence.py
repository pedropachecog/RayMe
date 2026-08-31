from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PHASE_DIR = Path(__file__).parent
RUNNER = PHASE_DIR / "09.1-run-omen-evidence.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("phase091_evidence_runner", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeProbe:
    def __init__(self, *, settings=None, models=None, props=None):
        self.calls: list[tuple[str, str]] = []
        self.settings = settings or {
            "llm_base_url": "https://private.invalid/v1",
            "llm_model": "observed-model",
        }
        self.models = models or {"data": [{"id": "observed-model"}]}
        self.props = props or {
            "model_alias": "observed-model",
            "chat_template": (
                "{% for message in messages %}"
                "{% if message.role == 'assistant' %}{{ message.content }}{% endif %}"
                "{% if loop.last and add_generation_prompt %}<assistant>{% endif %}"
                "{% endfor %}"
            ),
            "default_generation_settings": {"n_ctx": 131072},
        }

    def deployed_commit(self):
        self.calls.append(("READ", "deployed_commit"))
        return "a" * 40

    def get_rayme_settings(self):
        self.calls.append(("GET", "rayme_settings"))
        return 200, self.settings

    def get_provider_models(self, _private_base_url):
        self.calls.append(("GET", "provider_models"))
        return self.models

    def get_provider_props(self, _private_base_url):
        self.calls.append(("GET", "provider_props"))
        return self.props


def test_preflight_is_read_only_and_sanitized():
    runner = load_runner()
    probe = FakeProbe()
    result = runner.collect_preflight(probe, generated_at="2026-08-31T00:00:00Z")

    assert {method for method, _ in probe.calls} <= {"GET", "READ"}
    assert result["deployed_commit"] == "a" * 40
    assert result["provider"]["model_id"] == "observed-model"
    assert result["provider"]["context_capacity"] == 131072
    assert len(result["provider"]["chat_template_sha256"]) == 64
    assert result["provider"]["chat_template_bytes"] > 0
    assert result["provider"]["assistant_prefill"] is True
    serialized = json.dumps(result)
    for forbidden in (
        "private.invalid",
        "{% for message",
        "{{ message.content }}",
        "llm_base_url",
        "credentials",
        "runtime_seed",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("models", {"data": []}),
        ("models", {"data": [{"id": "one"}, {"id": "two"}]}),
        ("props", {"model_alias": "observed-model"}),
        (
            "props",
            {
                "model_alias": "observed-model",
                "chat_template": "{{ messages }}",
                "default_generation_settings": {"n_ctx": "unknown"},
            },
        ),
    ],
)
def test_model_identity_context_capacity_chat_template_fail_closed(field, value):
    runner = load_runner()
    kwargs = {field: value}
    with pytest.raises(runner.EvidenceError):
        runner.collect_preflight(FakeProbe(**kwargs))


def test_model_identity_conflict_fails_closed():
    runner = load_runner()
    with pytest.raises(runner.EvidenceError, match="model identity"):
        runner.collect_preflight(
            FakeProbe(models={"data": [{"id": "observed-model"}]}, props={
                "model_alias": "different-model",
                "chat_template": "{% if add_generation_prompt %}{% endif %}",
                "default_generation_settings": {"n_ctx": 4096},
            })
        )


def test_assistant_prefill_must_be_observable_not_defaulted():
    runner = load_runner()
    props = dict(FakeProbe().props)
    props["chat_template"] = "{% for message in messages %}{{ message.content }}{% endfor %}"
    with pytest.raises(runner.EvidenceError, match="assistant prefill"):
        runner.collect_preflight(FakeProbe(props=props))


# Task 2: immutable evidence corpus, schemas, and independent verifier.


MANIFEST = PHASE_DIR / "09.1-evidence-manifest.json"
VERIFIER = PHASE_DIR / "09.1-verify-evidence.py"


def test_manifest_freezes_complete_phase091_corpus_and_three_seed_matrix():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scenarios = manifest["deployed_scenarios"]
    assert len(scenarios) == 12
    assert len({row["scenario_id"] for row in scenarios}) == 12
    assert all(len(row["evidence_seeds"]) == 3 for row in scenarios)
    assert len({seed for row in scenarios for seed in row["evidence_seeds"]}) == 36
    assert manifest["ordinary_runtime_seed_policy"] == "fresh_undisclosed_per_attempt"
    assert len(manifest["lifecycle_traces"]) == 6
    assert len(manifest["request_golds"]) == 8
    assert len(manifest["quality_cases"]) == 8
    assert set(manifest["critical_gate_ids"]) == {
        "REF-01", "REF-02", "PROMPT-01", "STREAM-01", "CALL-01",
        "STATE-01", "QUALITY-01", "DEPLOY-01", "PRIV-01",
    }


def test_manifest_admits_only_four_ignored_result_shapes_and_no_auth_metadata():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest["generated_results"]) == {
        "results/omen-preflight.json",
        "results/local-verification.json",
        "results/omen-evidence.json",
        "results/decision-report.json",
    }
    serialized = json.dumps(manifest).lower()
    for forbidden in (
        "voice_data_steward", "authorization_basis", "authorization_status",
        "consent", "use_scope", "generated_person", "synthetic_fallback",
    ):
        assert forbidden not in serialized


def test_verifier_contracts_only_recomputes_manifest_contracts():
    verifier = load_runner.__globals__["importlib"].util.spec_from_file_location(
        "phase091_verifier_contracts", VERIFIER
    )
    assert verifier and verifier.loader
    module = importlib.util.module_from_spec(verifier)
    verifier.loader.exec_module(module)
    checked = module.verify_contracts_only()
    assert checked["deployed_turns"] == 36
    assert checked["gate_count"] == 9
    assert checked["result_shape_count"] == 4


def test_verifier_recursive_privacy_scan_rejects_prose_paths_secrets_and_seeds():
    spec = importlib.util.spec_from_file_location("phase091_verifier_privacy", VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for payload in (
        {"prompt": "private roleplay prompt"},
        {"nested": {"history": "private turn"}},
        {"path": r"C:\\Users\\private\\evidence"},
        {"authorization": "Bearer secret-token-value"},
        {"runtime_seed": 99123},
        {"audio": "sample.wav"},
    ):
        with pytest.raises(module.EvidenceError):
            module.verify_shared_privacy(payload)


def test_verifier_rejects_stale_or_changed_preflight_identity():
    spec = importlib.util.spec_from_file_location("phase091_verifier_preflight", VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline = {
        "schema_version": 1,
        "artifact": "omen-preflight",
        "phase": "09.1",
        "generated_at": "2026-08-31T00:00:00Z",
        "deployed_commit": "a" * 40,
        "health": {"check": "rayme_settings", "status_code": 200, "ok": True},
        "provider": {
            "model_id": "observed-model", "context_capacity": 131072,
            "chat_template_sha256": "b" * 64, "chat_template_bytes": 100,
            "chat_template_id": "observed-model", "assistant_prefill": True,
            "assistant_prefill_source": "observed_chat_template",
        },
    }
    module.verify_preflight(baseline, now="2026-08-31T00:30:00Z")
    with pytest.raises(module.EvidenceError, match="stale"):
        module.verify_preflight(baseline, now="2026-08-31T03:00:00Z")
    changed = json.loads(json.dumps(baseline))
    changed["provider"]["chat_template_sha256"] = "c" * 64
    with pytest.raises(module.EvidenceError, match="provider identity"):
        module.verify_preflight(
            changed,
            expected_provider=baseline["provider"],
            now="2026-08-31T00:30:00Z",
        )
