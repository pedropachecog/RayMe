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
