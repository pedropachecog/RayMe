from __future__ import annotations

import importlib.util
import json
import math
import re
from pathlib import Path
from types import ModuleType

import pytest


PHASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = PHASE_DIR / "09-evidence-manifest.json"
SPEAKER_PATH = PHASE_DIR / "09-speaker-score.py"
VERIFIER_PATH = PHASE_DIR / "09-verify-evidence.py"

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


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_freezes_exact_twenty_ai_spec_scenarios() -> None:
    manifest = _manifest()
    scenarios = manifest["scenarios"]
    assert isinstance(scenarios, list)
    assert len(scenarios) == 20
    assert {scenario["scenario_id"] for scenario in scenarios} == EXPECTED_SCENARIOS
    assert all(scenario["expected_events"] for scenario in scenarios)
    assert all(scenario["criticality"] in {"critical", "high"} for scenario in scenarios)
    assert all("evidence_artifact" in scenario for scenario in scenarios)
    assert all("thresholds" in scenario for scenario in scenarios)


def test_manifest_pins_runtime_model_and_speaker_revisions() -> None:
    manifest = _manifest()
    assert manifest["runtime"] == {
        "engine_id": "qwen3_1_7b",
        "package": "faster-qwen3-tts==0.3.2",
        "source_commit": "a70afc0f81f7f5f8801c3227968f1102f43f211c",
        "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "model_revision": "fd4b254389122332181a7c3db7f27e918eec64e3",
        "torch_version": "2.10.0+cu126",
        "cuda_version": "12.6",
        "device": "cuda",
    }
    assert manifest["speaker_scorer"] == {
        "model_id": "microsoft/wavlm-base-plus-sv",
        "model_revision": "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e",
        "model_class": "WavLMForXVector",
        "transformers_version": "4.57.3",
        "sample_rate_hz": 16000,
        "device": "cuda",
        "maximum_late_drop": 0.05,
    }


def test_manifest_reference_is_hash_bound_and_privacy_local() -> None:
    manifest = _manifest()
    fixture = manifest["selected_fixture"]
    assert fixture["fixture_kind"] == "generated_non_person_fixture"
    assert fixture["use_scope"] == "rayme_lan_call_testing"
    assert fixture["voice_data_steward"]
    assert fixture["authorization_basis"] == "generated_non_person_fixture"
    assert re.fullmatch(r"[0-9a-f]{64}", fixture["reference_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", fixture["transcript_sha256"])
    assert "transcript" not in fixture
    assert manifest["evidence_policy"]["audio_storage"] == "local_only_uncommitted"
    assert manifest["evidence_policy"]["embedding_storage"] == "local_only_uncommitted"
    assert manifest["evidence_policy"]["committed_payload"] == "opaque_ids_hashes_and_scalars_only"
    assert manifest["evidence_policy"]["hosted_audio_judge_allowed"] is False
    assert manifest["evidence_policy"]["product_owner_direction_is_speaker_permission"] is False


def test_manifest_keeps_automated_and_human_acceptance_separate() -> None:
    status = _manifest()["acceptance_status"]
    assert status == {
        "autonomous_release_ready": "pending",
        "integrated_human_listening_status": "pending",
        "physical_call_status": "pending",
        "candidate_spike_listening_status": "accepted_separately",
    }


def test_speaker_cosine_and_resample_helpers_are_deterministic() -> None:
    speaker = _load_module(SPEAKER_PATH, "phase09_speaker")
    assert speaker.cosine_similarity([3.0, 4.0], [6.0, 8.0]) == pytest.approx(1.0)
    assert speaker.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    with pytest.raises(speaker.SpeakerScoreError, match="zero-norm"):
        speaker.cosine_similarity([0.0, 0.0], [1.0, 0.0])

    resampled = speaker.linear_resample([0.0, 1.0, 0.0], 3, 6)
    assert len(resampled) == 6
    assert all(math.isfinite(value) for value in resampled)
    assert resampled[0] == pytest.approx(0.0)
    assert resampled[-1] == pytest.approx(0.0)


def test_speaker_payload_recomputes_baseline_early_middle_late_gates() -> None:
    speaker = _load_module(SPEAKER_PATH, "phase09_speaker_payload")
    payload = speaker.build_score_payload(
        deployed_commit="a" * 40,
        reference_sha256="b" * 64,
        baseline_commit="a" * 40,
        baseline_scores=[("short", "1" * 64, 0.84), ("medium", "2" * 64, 0.82), ("long", "3" * 64, 0.80)],
        early_scores=[(turn, f"{turn:064x}", 0.82 - turn * 0.001) for turn in range(1, 6)],
        middle_scores=[(turn, f"{turn:064x}", 0.81 - turn * 0.0001) for turn in range(23, 28)],
        late_scores=[(turn, f"{turn:064x}", 0.79 - turn * 0.0001) for turn in range(46, 51)],
        runtime_metadata={
            "transformers_version": "4.57.3",
            "torch_version": "2.10.0+cu126",
            "torch_cuda_version": "12.6",
            "device": "cuda:0",
            "gpu_name": "NVIDIA GeForce RTX 3060",
        },
        generated_at="2026-07-31T00:00:00Z",
    )
    assert payload["integrated_baseline_median"] == pytest.approx(0.82)
    assert payload["early_median"] == pytest.approx(0.817)
    assert payload["middle_median"] == pytest.approx(0.8075)
    assert payload["late_median"] == pytest.approx(0.7852)
    assert payload["late_minus_early"] == pytest.approx(-0.0318)
    assert payload["late_minus_integrated_baseline"] == pytest.approx(-0.0348)
    assert payload["speaker_stability_gate"] is True
    assert payload["absolute_cosine_is_human_likeness_judgment"] is False
    assert payload["integrated_human_listening_status"] == "pending"
    assert payload["physical_call_status"] == "pending"
    assert all("embedding" not in sample for key in ("baseline_scores", "early_scores", "middle_scores", "late_scores") for sample in payload[key])


def test_speaker_payload_rejects_wrong_buckets_or_commit() -> None:
    speaker = _load_module(SPEAKER_PATH, "phase09_speaker_invalid")
    common = {
        "deployed_commit": "a" * 40,
        "reference_sha256": "b" * 64,
        "baseline_commit": "a" * 40,
        "baseline_scores": [("short", "1" * 64, 0.8), ("medium", "2" * 64, 0.8), ("long", "3" * 64, 0.8)],
        "early_scores": [(turn, f"{turn:064x}", 0.8) for turn in range(1, 6)],
        "middle_scores": [(turn, f"{turn:064x}", 0.8) for turn in range(23, 28)],
        "late_scores": [(turn, f"{turn:064x}", 0.8) for turn in range(46, 51)],
        "runtime_metadata": {
            "transformers_version": "4.57.3",
            "torch_version": "2.10.0+cu126",
            "torch_cuda_version": "12.6",
            "device": "cuda:0",
            "gpu_name": "NVIDIA GeForce RTX 3060",
        },
        "generated_at": "2026-07-31T00:00:00Z",
    }
    with pytest.raises(speaker.SpeakerScoreError, match="baseline commit"):
        speaker.build_score_payload(**{**common, "baseline_commit": "c" * 40})
    with pytest.raises(speaker.SpeakerScoreError, match="early turn ids"):
        speaker.build_score_payload(**{**common, "early_scores": common["early_scores"][:-1]})


def test_speaker_runtime_is_pinned_local_cuda_only() -> None:
    source = SPEAKER_PATH.read_text(encoding="utf-8")
    assert "microsoft/wavlm-base-plus-sv" in source
    assert "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e" in source
    assert "WavLMForXVector" in source
    assert "local_files_only=True" in source
    assert "transformers==4.57.3" in source
    assert "torch.cuda.is_available()" in source
    assert "http://" not in source and "https://" not in source


# Task 2 adds verifier-specific tests below this line.
