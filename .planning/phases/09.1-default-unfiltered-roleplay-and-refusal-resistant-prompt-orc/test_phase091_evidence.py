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


def test_remote_acquisition_quotes_powershell_and_streams_sanitized_preflight(
    monkeypatch, tmp_path,
):
    runner = load_runner()
    expected = "d" * 40
    baseline = {
        "schema_version": 1,
        "artifact": "omen-preflight",
        "phase": "09.1",
        "generated_at": "2026-08-31T00:00:00Z",
        "deployed_commit": expected,
        "health": {"check": "rayme_settings", "status_code": 200, "ok": True},
        "provider": {"model_id": "observed-model"},
    }
    runner.RESULTS_DIR = tmp_path
    (tmp_path / "omen-preflight.json").write_text(json.dumps(baseline), encoding="utf-8")
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")
        payload = {"evidence": {"ok": True}, "decision": {"decision_ready": True}}
        return type("Completed", (), {
            "stdout": "RAYME_PHASE091_EVIDENCE=" + json.dumps(payload),
        })()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    evidence, decision = runner._run_remote_acquisition(expected)

    assert evidence == {"ok": True}
    assert decision == {"decision_ready": True}
    assert len(captured["argv"]) == 7
    remote_command = captured["argv"][-1]
    assert remote_command.startswith('powershell -NoProfile -NonInteractive -Command "')
    assert "--baseline-stdin" in remote_command
    assert json.loads(captured["input"]) == baseline


def test_worker_rejects_preflight_for_another_release():
    runner = load_runner()
    with pytest.raises(runner.EvidenceError, match="preflight identity"):
        runner._worker_acquire(
            "d" * 40,
            {"artifact": "omen-preflight", "deployed_commit": "e" * 40, "provider": {}},
        )


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


# Task 3: production acquisition lifecycle and local-release binding.


def _load_verifier(name="phase091_verifier"):
    spec = importlib.util.spec_from_file_location(name, VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_verification_uses_exact_intended_commit_and_rejects_mismatch(tmp_path):
    runner = load_runner()
    verifier = _load_verifier("phase091_local_release")
    commit = "d" * 40
    output = tmp_path / "local-verification.json"
    runner.record_local_verification(
        output, intended_commit=commit,
        gates={gate: True for gate in verifier.GATES},
        generated_at="2026-08-31T00:00:00Z",
    )
    assert json.loads(output.read_text())["intended_commit"] == commit
    assert verifier.verify_local_release(
        results_dir=tmp_path, expected_commit=commit,
        now="2026-08-31T00:30:00Z",
    ) == commit
    with pytest.raises(verifier.EvidenceError, match="intended commit"):
        verifier.verify_local_release(
            results_dir=tmp_path, expected_commit="e" * 40,
            now="2026-08-31T00:30:00Z",
        )


class FakeAcquisition:
    def __init__(self, preflight, expected_commit):
        self.preflight = preflight
        self.expected_commit = expected_commit
        self.calls = []

    def current_preflight(self):
        self.calls.append("current_preflight")
        current = json.loads(json.dumps(self.preflight))
        current["deployed_commit"] = self.expected_commit
        return current

    def settings_fingerprint(self):
        self.calls.append("settings_fingerprint")
        return "a" * 64

    def run_generation(self, scenario_id, evidence_seed):
        self.calls.append(("generation", scenario_id, evidence_seed))
        return {"attempts": 1, "refusal_count": 0, "request_diff_count": 0,
                "persisted_rejected_count": 0, "false_retry_count": 0}

    def start_slow_fixture(self):
        self.calls.append("fixture_start")
        return object()

    def run_lifecycle(self, _fixture, trace_id):
        self.calls.append(("lifecycle", trace_id))
        required = next(
            row["required_events"]
            for row in json.loads(MANIFEST.read_text())["lifecycle_traces"]
            if row["trace_id"] == trace_id
        )
        return {
            "events": [
                {"event_id": event_id, "elapsed_ms": float(index + 1) * 10.0}
                for index, event_id in enumerate(required)
            ],
            "late_rejected_count": 0, "whole_synthesis_fallback_count": 0,
        }

    def stop_slow_fixture(self, _fixture):
        self.calls.append("fixture_stop")

    def health_ready(self):
        self.calls.append("health_ready")
        return True


def test_ordered_acquisition_runs_36_then_fixture_and_restores_state(tmp_path):
    runner = load_runner()
    preflight = json.loads((PHASE_DIR / "results/omen-preflight.json").read_text())
    acquisition = FakeAcquisition(preflight, "f" * 40)
    evidence, decision = runner.run_ordered_evidence(
        acquisition,
        json.loads(MANIFEST.read_text()),
        expected_commit="f" * 40,
        baseline_preflight=preflight,
        generated_at="2026-08-31T00:10:00Z",
    )
    generation_calls = [call for call in acquisition.calls if isinstance(call, tuple) and call[0] == "generation"]
    assert len(generation_calls) == 36
    assert acquisition.calls.index("fixture_start") > acquisition.calls.index(generation_calls[-1])
    assert acquisition.calls.count("settings_fingerprint") == 2
    assert acquisition.calls[-2:] == ["health_ready", "fixture_stop"] or "fixture_stop" in acquisition.calls[-3:]
    assert evidence["deployed_commit"] == "f" * 40
    assert evidence["turn_count"] == 36
    assert decision["decision_ready"] is True
    serialized = json.dumps(evidence)
    assert "runtime_seed" not in serialized and '"seed"' not in serialized


def test_fixture_teardown_runs_when_lifecycle_fails():
    runner = load_runner()
    preflight = json.loads((PHASE_DIR / "results/omen-preflight.json").read_text())
    acquisition = FakeAcquisition(preflight, "f" * 40)
    acquisition.run_lifecycle = lambda *_args: (_ for _ in ()).throw(RuntimeError("fixture failure"))
    with pytest.raises(RuntimeError, match="fixture failure"):
        runner.run_ordered_evidence(
            acquisition, json.loads(MANIFEST.read_text()),
            expected_commit="f" * 40, baseline_preflight=preflight,
        )
    assert "fixture_stop" in acquisition.calls


def test_immediate_timing_carrier_never_contains_final_only_values():
    runner = load_runner()
    immediate, final = runner.split_timing_carriers({
        "first_caption_ms": 20.0, "first_speech_ms": 30.0,
        "llm_complete_ms": 80.0, "tts_complete_ms": 90.0,
        "final_playout_ms": 110.0, "interrupt_ms": 40.0,
        "late_rejected_count": 0,
    })
    assert set(immediate) == {"first_caption_ms", "first_speech_ms", "interrupt_ms"}
    assert set(final) == {"llm_complete_ms", "tts_complete_ms", "final_playout_ms", "late_rejected_count"}


def test_runner_source_forbids_deployment_and_scheduled_task_mutation():
    source = RUNNER.read_text(encoding="utf-8").lower()
    for forbidden in ("deploy-omen.sh", "schtasks", "start-process", "scheduledtask", "launcher.cmd"):
        assert forbidden not in source
