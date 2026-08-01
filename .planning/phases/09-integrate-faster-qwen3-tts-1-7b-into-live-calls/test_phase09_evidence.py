from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


PHASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = PHASE_DIR / "09-evidence-manifest.json"
SPEAKER_PATH = PHASE_DIR / "09-speaker-score.py"
VERIFIER_PATH = PHASE_DIR / "09-verify-evidence.py"
RUNNER_PATH = PHASE_DIR / "09-run-omen-evidence.py"
FIDELITY_SWEEP_PATH = PHASE_DIR / "09-qwen-fidelity-sweep.py"

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

    stream_scenarios = [
        scenario
        for scenario in scenarios
        if scenario["scenario_id"].startswith(("clone-valid", "message-integrity"))
        or scenario["scenario_id"] == "slow-stream-backpressure"
    ]
    assert len(stream_scenarios) == 7
    assert all(str(scenario.get("target_text") or "").strip() for scenario in stream_scenarios)


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


EXPECTED_SELF_TESTS = {
    "false-overall-status",
    "stale-timestamp",
    "deployed-commit-mismatch",
    "whole-synthesis-fallback",
    "missing-critical-gate",
    "missing-scenario",
    "authorization-missing",
    "authorization-malformed",
    "authorization-wrong-reference-hash",
    "authorization-wrong-transcript-hash",
    "authorization-wrong-scope",
    "bridge-capacity-absent",
    "bridge-high-water-unbounded",
    "track-capacity-absent",
    "track-high-water-unbounded",
    "speaker-late-drop",
    "speaker-baseline-drop",
    "private-path-leak",
    "full-transcript-leak",
    "base64-audio-leak",
    "access-token-leak",
    "forbidden-audio-extension-leak",
    "cpu-substitution",
    "model-substitution",
    "non-natural-eos",
    "active-playout-underflow",
    "realtime-supply-failure",
    "late-audio-after-cancel",
    "ai-done-after-cancel",
    "persistence-after-cancel",
    "unbounded-prompt-cache",
    "unbounded-output-ceiling",
    "missing-human-pending-separation",
}


def test_verifier_contracts_only_checks_static_tools_and_schema() -> None:
    verifier = _load_module(VERIFIER_PATH, "phase09_verifier_contracts")
    manifest = verifier.verify_contracts_only()
    assert len(manifest["scenarios"]) == 20
    assert set(manifest["critical_gate_ids"]) == set(verifier.REQUIRED_CRITICAL_GATES)


def test_verifier_accepts_recomputed_synthetic_core_and_decision_bundle(tmp_path: Path) -> None:
    verifier = _load_module(VERIFIER_PATH, "phase09_verifier_valid")
    commit = "a" * 40
    verifier.write_synthetic_bundle(
        tmp_path,
        deployed_commit=commit,
        generated_at="2026-07-31T00:00:00Z",
    )
    assert verifier.verify_core_ready(
        results_dir=tmp_path,
        expected_commit=commit,
        now="2026-07-31T01:00:00Z",
    ) == commit
    assert verifier.verify_decision_ready(
        results_dir=tmp_path,
        expected_commit=commit,
        now="2026-07-31T01:00:00Z",
    ) == commit


def test_verifier_rejects_raw_failure_even_when_overall_status_is_true(tmp_path: Path) -> None:
    verifier = _load_module(VERIFIER_PATH, "phase09_verifier_false_status")
    commit = "a" * 40
    verifier.write_synthetic_bundle(tmp_path, deployed_commit=commit, generated_at="2026-07-31T00:00:00Z")
    soak_path = tmp_path / "qwen3-soak.json"
    soak = json.loads(soak_path.read_text(encoding="utf-8"))
    soak["overall_status"] = True
    soak["turns"][-1]["natural_eos"] = False
    soak_path.write_text(json.dumps(soak), encoding="utf-8")
    with pytest.raises(verifier.EvidenceError, match="natural EOS"):
        verifier.verify_core_ready(
            results_dir=tmp_path,
            expected_commit=commit,
            now="2026-07-31T01:00:00Z",
        )


def test_verifier_recomputes_speaker_medians_instead_of_trusting_gate(tmp_path: Path) -> None:
    verifier = _load_module(VERIFIER_PATH, "phase09_verifier_speaker")
    commit = "a" * 40
    verifier.write_synthetic_bundle(tmp_path, deployed_commit=commit, generated_at="2026-07-31T00:00:00Z")
    speaker_path = tmp_path / "qwen3-speaker.json"
    speaker = json.loads(speaker_path.read_text(encoding="utf-8"))
    speaker["speaker_stability_gate"] = True
    speaker["late_scores"] = [
        {**row, "cosine": 0.70} for row in speaker["late_scores"]
    ]
    speaker_path.write_text(json.dumps(speaker), encoding="utf-8")
    with pytest.raises(verifier.EvidenceError, match="late speaker median"):
        verifier.verify_decision_ready(
            results_dir=tmp_path,
            expected_commit=commit,
            now="2026-07-31T01:00:00Z",
        )


@pytest.mark.parametrize(
    "payload,pattern",
    [
        ({"safe": "C:\\Users\\private\\voice"}, "private path"),
        ({"reference_transcript": "the complete private transcript sentinel"}, "transcript"),
        ({"wav_b64": "A" * 1024}, "base64"),
        ({"authorization": "Bearer rayme_secret_access_token_1234567890"}, "token"),
        ({"sample": "results/private-reference.wav"}, "audio extension"),
        ({"/home/private/reference": "safe"}, "private path"),
    ],
)
def test_verifier_leak_scan_covers_keys_and_values(payload: dict[str, str], pattern: str) -> None:
    verifier = _load_module(VERIFIER_PATH, f"phase09_verifier_leak_{pattern.replace(' ', '_')}")
    with pytest.raises(verifier.EvidenceError, match=pattern):
        verifier.verify_no_private_leaks(payload, label="test payload")


def test_verifier_named_self_tests_cover_every_false_readiness_mutation() -> None:
    verifier = _load_module(VERIFIER_PATH, "phase09_verifier_selftest")
    passed = verifier.run_self_tests()
    assert set(passed) == EXPECTED_SELF_TESTS
    assert len(passed) == len(EXPECTED_SELF_TESTS)


def test_verifier_cli_self_test_lists_named_mutations() -> None:
    completed = subprocess.run(
        [sys.executable, str(VERIFIER_PATH), "--self-test"],
        cwd=PHASE_DIR.parents[3],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    for name in EXPECTED_SELF_TESTS:
        assert f"PASS self-test: {name}" in completed.stdout
    assert completed.stdout.rstrip().endswith("PASS")


def test_print_deployed_commit_emits_only_validated_sha(tmp_path: Path) -> None:
    verifier = _load_module(VERIFIER_PATH, "phase09_verifier_print")
    commit = "d" * 40
    verifier.write_synthetic_bundle(tmp_path, deployed_commit=commit, generated_at="2026-07-31T00:00:00Z")
    completed = subprocess.run(
        [
            sys.executable,
            str(VERIFIER_PATH),
            "--print-deployed-commit",
            "--results-dir",
            str(tmp_path),
            "--now",
            "2026-07-31T01:00:00Z",
        ],
        cwd=PHASE_DIR.parents[3],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == f"{commit}\n"


# Plan 09-13 Task 1: production-path acquisition contracts.


class _FakeReferenceSelection:
    def __init__(
        self,
        *,
        reference_path: Path,
        transcript_path: Path,
        source: str,
        reference_sha256: str,
        transcript_sha256: str,
    ) -> None:
        self.reference_path = reference_path
        self.transcript_path = transcript_path
        self.steward_id = "generated_non_person_fixture"
        self.authorization_basis = "generated_non_person_fixture"
        self.use_scope = "rayme_lan_call_testing"
        self.reference_sha256 = reference_sha256
        self.transcript_sha256 = transcript_sha256
        self.source = source


def _runner_module(name: str = "phase09_omen_runner") -> ModuleType:
    return _load_module(RUNNER_PATH, name)


def test_hardware_tracer_preserves_planar_int16_pcm_scale() -> None:
    import numpy as np

    tracer = _runner_module("phase09_runner_int16_capture").load_hardware_tracer()

    class Frame:
        def to_ndarray(self) -> object:
            return np.asarray([[-2048, -128, 0, 128, 2048]], dtype=np.int16)

    actual = tracer._decoded_audio_frame_to_int16(Frame())

    assert actual.dtype == np.int16
    assert actual.tolist() == [-2048, -128, 0, 128, 2048]


def test_hardware_tracer_scales_normalized_float_pcm_once() -> None:
    import numpy as np

    tracer = _runner_module("phase09_runner_float_capture").load_hardware_tracer()

    class Frame:
        def to_ndarray(self) -> object:
            return np.asarray([[-1.0, -0.5, 0.0, 0.5, 1.0]], dtype=np.float32)

    actual = tracer._decoded_audio_frame_to_int16(Frame())

    assert actual.dtype == np.int16
    assert actual.tolist() == [-32767, -16384, 0, 16384, 32767]


def test_hardware_tracer_consumer_records_and_detects_int16_audio() -> None:
    import asyncio
    import numpy as np

    tracer = _runner_module("phase09_runner_capture_consumer").load_hardware_tracer()

    class Frame:
        def to_ndarray(self) -> object:
            return np.asarray([[0, 64, 256, -512]], dtype=np.int16)

    class Track:
        def __init__(self) -> None:
            self.calls = 0

        async def recv(self) -> object:
            self.calls += 1
            if self.calls == 1:
                return Frame()
            raise RuntimeError("capture complete")

    async def scenario() -> tuple[list[tuple[float, object]], float | None]:
        capture = tracer.WebRtcCapture()
        capture.start_capture("turn-int16")
        await capture._consume_audio(Track())
        return capture.stop_capture()

    frames, first_nonzero = asyncio.run(scenario())

    assert first_nonzero is not None
    assert len(frames) == 1
    assert frames[0][1].tolist() == [0, 64, 256, -512]


def test_fidelity_sweep_compares_upstream_and_bounded_fidelity_profiles() -> None:
    sweep = _load_module(FIDELITY_SWEEP_PATH, "phase09_fidelity_sweep_contract")

    assert sweep.REPO_ROOT == PHASE_DIR.parents[2]
    assert sweep.PROFILES["upstream-default"] == {
        "temperature": 0.9,
        "top_k": 50,
        "top_p": 1.0,
        "do_sample": True,
        "repetition_penalty": 1.05,
    }
    assert sweep.PROFILES["fidelity-060"]["temperature"] == 0.60
    assert sweep.PROFILES["fidelity-060"]["repetition_penalty"] == 1.10
    assert sweep.PROFILES["greedy"]["do_sample"] is False
    assert set(sweep.TARGETS) == {
        "names-numbers",
        "negation-abbreviations",
        "punctuation-final-word",
    }
    assert sweep.TARGET_SEEDS["names-numbers"] == (91004, 92100, 93100)
    assert sweep.TARGET_SEEDS["negation-abbreviations"] == (91005, 92101, 93101)
    assert sweep.TARGET_SEEDS["punctuation-final-word"] == (91006, 92102, 93102)
    assert sweep._wer("No, version 2.4.", "No version 2.4") == 0.0


def _hash_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _fallback_selection(tmp_path: Path) -> _FakeReferenceSelection:
    tmp_path.mkdir(parents=True, exist_ok=True)
    reference = tmp_path / "generated-reference.bin"
    transcript = tmp_path / "generated-transcript.bin"
    reference_bytes = b"RIFF-generated-non-person-fixture"
    transcript_bytes = b"Generated non person fixture.\n"
    reference.write_bytes(reference_bytes)
    transcript.write_bytes(transcript_bytes)
    return _FakeReferenceSelection(
        reference_path=reference,
        transcript_path=transcript,
        source="generated_non_person_fixture",
        reference_sha256=_hash_bytes(reference_bytes),
        transcript_sha256=_hash_bytes(transcript_bytes),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "malformed",
        "wrong-reference-hash",
        "wrong-transcript-hash",
        "wrong-scope",
    ],
)
def test_runner_invalid_phase005_sidecars_select_fallback_before_product_use(
    tmp_path: Path,
    mutation: str,
) -> None:
    runner = _runner_module(f"phase09_runner_sidecar_{mutation}")
    reference = tmp_path / "phase005-reference.bin"
    transcript = tmp_path / "phase005-transcript.bin"
    sidecar = tmp_path / "phase005.authorization.json"
    reference_bytes = b"RIFF-phase005-private-reference"
    transcript_bytes = b"Exact Phase 005 transcript.\n"
    reference.write_bytes(reference_bytes)
    transcript.write_bytes(transcript_bytes)
    metadata = {
        "voice_data_steward": "opaque-steward",
        "authorization_basis": "speaker-provided local test",
        "use_scope": "rayme_lan_call_testing",
        "reference_sha256": _hash_bytes(reference_bytes),
        "transcript_sha256": _hash_bytes(transcript_bytes),
    }
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    if mutation == "missing":
        sidecar.unlink()
    elif mutation == "malformed":
        sidecar.write_text("{", encoding="utf-8")
    elif mutation == "wrong-reference-hash":
        sidecar.write_text(json.dumps({**metadata, "reference_sha256": "0" * 64}), encoding="utf-8")
    elif mutation == "wrong-transcript-hash":
        sidecar.write_text(json.dumps({**metadata, "transcript_sha256": "f" * 64}), encoding="utf-8")
    else:
        sidecar.write_text(json.dumps({**metadata, "use_scope": "outside-rayme"}), encoding="utf-8")

    fallback = _fallback_selection(tmp_path / "fallback")
    used_paths: list[Path] = []
    selected = runner.resolve_evidence_reference(
        reference_path=reference,
        transcript_path=transcript,
        sidecar_path=sidecar,
        fallback_factory=lambda: fallback,
    )
    runner.consume_selected_reference(selected, lambda path: used_paths.append(path))

    assert selected.source == "generated_non_person_fixture"
    assert used_paths == [fallback.reference_path, fallback.transcript_path]
    assert reference not in used_paths and transcript not in used_paths


def test_runner_loads_tracer_canonical_authorization_contract() -> None:
    runner = _runner_module("phase09_runner_canonical_authorization")
    tracer = runner.load_hardware_tracer()
    assert runner.CANONICAL_REFERENCE_RESOLVER == "_resolve_authorized_reference"
    assert runner.canonical_reference_resolver(tracer) is tracer._resolve_authorized_reference
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "09-run-hardware-tracer.py" in source
    assert "_resolve_authorized_reference" in source


def test_hardware_tracer_sends_canonical_top_level_voice_authorization(tmp_path: Path) -> None:
    import asyncio

    tracer = _runner_module("phase09_runner_saved_voice_contract").load_hardware_tracer()
    selection = _fallback_selection(tmp_path / "selection")

    class CapturingApi:
        web_base_url = "https://rayme.invalid"

        def __init__(self) -> None:
            self.saved_payload: dict[str, object] | None = None

        def post_wav(self, path: str, *, filename: str, content: bytes):
            assert path == "/api/voices/assets"
            assert filename == "rayme-phase09-reference.wav"
            assert content == b"RIFF-reference"
            return tracer.ApiResponse(status=201, payload={"asset_id": "asset_phase09"})

        def post_json(
            self,
            base_url: str,
            path: str,
            payload: dict[str, object],
        ):
            assert base_url == self.web_base_url
            assert path == "/api/voices"
            self.saved_payload = payload
            return tracer.ApiResponse(status=201, payload={"voice_id": "voice_phase09"})

    api = CapturingApi()
    voice_id, asset_id = asyncio.run(
        tracer._create_saved_voice(
            api,
            reference_audio=b"RIFF-reference",
            transcript="Generated non person fixture.",
            selection=selection,
        )
    )

    assert (voice_id, asset_id) == ("voice_phase09", "asset_phase09")
    assert api.saved_payload is not None
    assert api.saved_payload["voice_data_steward"] == selection.steward_id
    assert api.saved_payload["authorization_basis"] == selection.authorization_basis
    assert api.saved_payload["use_scope"] == selection.use_scope
    assert api.saved_payload["metadata"] == {
        "source": "phase09_hardware_tracer",
        "authorization": tracer._voice_provenance(selection),
    }


def test_runner_writes_generated_non_person_fixture_sidecar_without_private_content(
    tmp_path: Path,
) -> None:
    runner = _runner_module("phase09_runner_fixture_bundle")
    selection = _fallback_selection(tmp_path / "source")
    manifest = _manifest()
    manifest["selected_fixture"] = {
        **manifest["selected_fixture"],
        "reference_sha256": selection.reference_sha256,
        "transcript_sha256": selection.transcript_sha256,
    }
    paths = runner.write_permitted_fixture_bundle(
        selection=selection,
        manifest=manifest,
        local_dir=tmp_path / "results" / ".local",
    )
    provenance = json.loads(paths["provenance"].read_text(encoding="utf-8"))
    assert provenance == {
        **manifest["selected_fixture"],
        "authorization_basis": "generated_non_person_fixture",
        "use_scope": "rayme_lan_call_testing",
    }
    assert paths["reference"].read_bytes() == selection.reference_path.read_bytes()
    assert paths["transcript"].read_bytes() == selection.transcript_path.read_bytes()
    assert "transcript" not in provenance
    assert "path" not in json.dumps(provenance).lower()


class _DryProductionPath:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def collect_runtime(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("runtime", str(scenario["scenario_id"])))
        return {"attested": True}

    async def collect_stream(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("stream", str(scenario["scenario_id"])))
        return {"streaming_used": True}

    async def collect_alignment(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("alignment", str(scenario["scenario_id"])))
        return {"alignment_observed": True}

    async def collect_ceiling(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("ceiling", str(scenario["scenario_id"])))
        return {"ceiling_triggered": True}

    async def collect_control(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("control", str(scenario["scenario_id"])))
        return {"cancelled": True}

    async def collect_worker_failure(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("worker_failure", str(scenario["scenario_id"])))
        return {"backend_healthy": True}

    async def collect_soak(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("soak", str(scenario["scenario_id"])))
        return {"turn_count": 50}

    async def collect_canonical_call(self, scenario: dict[str, object]) -> dict[str, object]:
        self.calls.append(("canonical_call", str(scenario["scenario_id"])))
        return {"canonical_public_api": True}


def test_runner_dispatches_all_manifest_scenarios_through_named_production_paths() -> None:
    import asyncio

    runner = _runner_module("phase09_runner_dispatch")
    manifest = _manifest()
    production = _DryProductionPath()
    rows = asyncio.run(runner.run_manifest_scenarios(manifest, production))
    assert [row["scenario_id"] for row in rows] == [
        scenario["scenario_id"] for scenario in manifest["scenarios"]
    ]
    assert len(production.calls) == 20
    assert {kind for kind, _ in production.calls} == {
        "runtime",
        "stream",
        "alignment",
        "ceiling",
        "control",
        "worker_failure",
        "soak",
        "canonical_call",
    }
    assert all(row["observed_events"] for row in rows)
    assert all("measurements" in row for row in rows)
    assert [row["seed"] for row in rows] == [
        scenario["seed"] for scenario in manifest["scenarios"]
    ]


def test_runner_anchor_hashes_are_bound_to_each_actual_wav_and_mismatch_fails() -> None:
    runner = _runner_module("phase09_runner_actual_anchor_hashes")
    shared = "a" * 64
    rows = [
        {
            "turn": turn,
            "audio_sha256": f"{turn:064x}",
            "source_audio_sha256": shared,
        }
        for turn in (1, 10, 20, 30, 40, 50)
    ]

    runner.bind_and_validate_actual_anchor_hashes(
        rows,
        anchor_turns=[1, 10, 20, 30, 40, 50],
    )
    assert [row["anchor_sha256"] for row in rows] == [shared] * 6

    rows[-1]["source_audio_sha256"] = "b" * 64
    with pytest.raises(runner.EvidenceRunnerError, match="bit-identical"):
        runner.bind_and_validate_actual_anchor_hashes(
            rows,
            anchor_turns=[1, 10, 20, 30, 40, 50],
        )


def test_soak_reset_seed_anchors_use_identical_text_while_other_turns_stay_mixed() -> None:
    runner = _runner_module("phase09_runner_anchor_inputs")
    anchors = {1, 10, 20, 30, 40, 50}

    anchor_texts = {
        runner._soak_target_text(turn, anchor_turns=anchors) for turn in anchors
    }
    non_anchor_texts = {
        runner._soak_target_text(turn, anchor_turns=anchors)
        for turn in range(1, 10)
        if turn not in anchors
    }

    assert anchor_texts == {runner.SOAK_ANCHOR_TARGET_TEXT}
    assert non_anchor_texts == set(runner.SOAK_TARGET_TEXTS)


def test_runner_source_owns_production_routes_and_forbids_direct_generation_imports() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "/api/voices" in source
    assert "/webrtc/sessions/" in source
    assert "/api/calls" in source
    assert "/stt/transcribe" in source
    assert "from faster_qwen3_tts" not in source
    assert "import faster_qwen3_tts" not in source
    assert "generate_voice_clone(" not in source
    assert "generate_voice_clone_streaming(" not in source


# Plan 09-13 Task 2: core/finish lifecycle and sanitized bundle contracts.


class _CoreAcquisition:
    def __init__(self, payloads: dict[str, dict[str, object]]) -> None:
        self.payloads = payloads
        self.ready_checks = 0

    async def collect_core(self) -> dict[str, dict[str, object]]:
        return self.payloads

    async def assert_qwen_ready(self) -> dict[str, object]:
        self.ready_checks += 1
        return {
            "model_state": "resident",
            "prompt_state": "ready",
            "resident_engine": "qwen3_1_7b",
        }

    def private_state(self) -> dict[str, object]:
        return {
            "selected_voice_id": "voice_opaque_test",
            "reference_authorization": _manifest()["selected_fixture"],
            "baseline_audio": {"short": "private-short", "medium": "private-medium", "long": "private-long"},
            "soak_audio": {str(turn): f"private-turn-{turn}" for turn in [1, 2, 3, 4, 5, 23, 24, 25, 26, 27, 46, 47, 48, 49, 50]},
        }


def _synthetic_payloads(tmp_path: Path, commit: str) -> dict[str, dict[str, object]]:
    verifier = _load_module(VERIFIER_PATH, f"phase09_runner_bundle_{tmp_path.name}")
    source = tmp_path / "source"
    verifier.write_synthetic_bundle(
        source,
        deployed_commit=commit,
        generated_at="2026-07-31T00:00:00Z",
    )
    return {
        key: json.loads((source / filename).read_text(encoding="utf-8"))
        for key, filename in verifier.CORE_FILES.items()
    }


def test_runner_core_only_writes_exact_verifiable_core_and_private_state(tmp_path: Path) -> None:
    import asyncio

    commit = "a" * 40
    runner = _runner_module("phase09_runner_core_split")
    verifier = _load_module(VERIFIER_PATH, "phase09_runner_core_verify")
    acquisition = _CoreAcquisition(_synthetic_payloads(tmp_path, commit))
    output_dir = tmp_path / "results"
    local_dir = output_dir / ".local"

    asyncio.run(
        runner.run_core_only(
            expected_commit=commit,
            output_dir=output_dir,
            local_dir=local_dir,
            acquisition=acquisition,
        )
    )

    assert acquisition.ready_checks == 1
    assert {path.name for path in output_dir.glob("qwen3-*.json")} == set(verifier.CORE_FILES.values())
    assert verifier.verify_core_ready(
        results_dir=output_dir,
        expected_commit=commit,
        now="2026-07-31T01:00:00Z",
    ) == commit
    state = json.loads((local_dir / "qwen3-runner-state.json").read_text(encoding="utf-8"))
    assert state["expected_commit"] == commit
    assert state["mode"] == "core_complete"
    assert state["qwen_ready"] is True
    assert state["selected_voice_id"] == "voice_opaque_test"
    assert not (output_dir / "qwen3-speaker.json").exists()
    assert not (output_dir / "qwen3-log-leak-scan.json").exists()


class _FinishLifecycle:
    def __init__(
        self,
        *,
        speaker: dict[str, object],
        leak_scan: dict[str, object],
        fail_at: str | None = None,
    ) -> None:
        self.speaker = speaker
        self.leak_scan = leak_scan
        self.fail_at = fail_at
        self.events: list[str] = []

    async def assert_core_binding(self, expected_commit: str, state: dict[str, object]) -> None:
        self.events.append("assert_core_binding")
        assert state["expected_commit"] == expected_commit

    async def unload_qwen(self) -> None:
        self.events.append("unload_qwen")

    async def run_cuda_speaker_scorer(self) -> dict[str, object]:
        self.events.append("run_cuda_speaker_scorer")
        if self.fail_at == "scorer":
            raise RuntimeError("scorer failed")
        return self.speaker

    async def scan_same_commit_logs(self) -> dict[str, object]:
        self.events.append("scan_same_commit_logs")
        return self.leak_scan

    async def reload_qwen(self) -> None:
        self.events.append("reload_qwen")
        if self.fail_at == "reload":
            raise RuntimeError("reload failed")

    async def prewarm_selected_voice(self) -> None:
        self.events.append("prewarm_selected_voice")

    async def assert_qwen_ready(self) -> dict[str, object]:
        self.events.append("assert_qwen_ready")
        return {"model_state": "resident", "prompt_state": "ready"}


def _prepare_core_state(tmp_path: Path, commit: str) -> tuple[Path, Path, dict[str, dict[str, object]]]:
    import asyncio

    runner = _runner_module(f"phase09_runner_prepare_{tmp_path.name}")
    output_dir = tmp_path / "results"
    local_dir = output_dir / ".local"
    payloads = _synthetic_payloads(tmp_path, commit)
    asyncio.run(
        runner.run_core_only(
            expected_commit=commit,
            output_dir=output_dir,
            local_dir=local_dir,
            acquisition=_CoreAcquisition(payloads),
        )
    )
    return output_dir, local_dir, payloads


def test_runner_finish_unloads_scores_on_cuda_restores_and_leaves_browser_placeholder(
    tmp_path: Path,
) -> None:
    import asyncio

    commit = "b" * 40
    runner = _runner_module("phase09_runner_finish_split")
    verifier = _load_module(VERIFIER_PATH, "phase09_runner_finish_payload")
    output_dir, local_dir, _ = _prepare_core_state(tmp_path, commit)
    decision_source = tmp_path / "decision-source"
    verifier.write_synthetic_bundle(
        decision_source,
        deployed_commit=commit,
        generated_at="2026-07-31T00:00:00Z",
    )
    speaker = json.loads((decision_source / "qwen3-speaker.json").read_text(encoding="utf-8"))
    leak_scan = json.loads((decision_source / "qwen3-log-leak-scan.json").read_text(encoding="utf-8"))
    lifecycle = _FinishLifecycle(speaker=speaker, leak_scan=leak_scan)

    asyncio.run(
        runner.run_finish_acoustic_leak(
            expected_commit=commit,
            output_dir=output_dir,
            local_dir=local_dir,
            lifecycle=lifecycle,
            generated_at="2026-07-31T00:00:00Z",
        )
    )

    assert lifecycle.events == [
        "assert_core_binding",
        "unload_qwen",
        "run_cuda_speaker_scorer",
        "scan_same_commit_logs",
        "reload_qwen",
        "prewarm_selected_voice",
        "assert_qwen_ready",
    ]
    assert json.loads((output_dir / "qwen3-speaker.json").read_text(encoding="utf-8")) == speaker
    assert json.loads((output_dir / "qwen3-log-leak-scan.json").read_text(encoding="utf-8")) == leak_scan
    browser = json.loads((output_dir / "qwen3-browser.json").read_text(encoding="utf-8"))
    assert browser["deployed_commit"] == commit
    assert browser["evidence_state"] == "awaiting_real_live_e2e"
    assert browser["mocked"] is False
    assert browser["live_e2e_enabled"] is False
    with pytest.raises(verifier.EvidenceError, match="real qwen3_1_7b live E2E"):
        verifier.verify_decision_ready(
            results_dir=output_dir,
            expected_commit=commit,
            now="2026-07-31T01:00:00Z",
        )
    state = json.loads((local_dir / "qwen3-runner-state.json").read_text(encoding="utf-8"))
    assert state["mode"] == "finish_complete"
    assert state["qwen_ready"] is True


@pytest.mark.parametrize("fail_at", ["scorer", "reload"])
def test_runner_finish_failure_never_claims_qwen_ready_or_uses_fallback(
    tmp_path: Path,
    fail_at: str,
) -> None:
    import asyncio

    commit = "c" * 40
    runner = _runner_module(f"phase09_runner_finish_failure_{fail_at}")
    verifier = _load_module(VERIFIER_PATH, f"phase09_runner_finish_failure_payload_{fail_at}")
    output_dir, local_dir, _ = _prepare_core_state(tmp_path, commit)
    decision_source = tmp_path / "decision-source"
    verifier.write_synthetic_bundle(
        decision_source,
        deployed_commit=commit,
        generated_at="2026-07-31T00:00:00Z",
    )
    lifecycle = _FinishLifecycle(
        speaker=json.loads((decision_source / "qwen3-speaker.json").read_text(encoding="utf-8")),
        leak_scan=json.loads((decision_source / "qwen3-log-leak-scan.json").read_text(encoding="utf-8")),
        fail_at=fail_at,
    )

    with pytest.raises(RuntimeError, match="failed"):
        asyncio.run(
            runner.run_finish_acoustic_leak(
                expected_commit=commit,
                output_dir=output_dir,
                local_dir=local_dir,
                lifecycle=lifecycle,
            )
        )

    state = json.loads((local_dir / "qwen3-runner-state.json").read_text(encoding="utf-8"))
    assert state["mode"] == "finish_failed"
    assert state["qwen_ready"] is False
    assert state["failure_stage"] == fail_at
    assert "cpu" not in " ".join(lifecycle.events).lower()
    assert "remote" not in " ".join(lifecycle.events).lower()


def test_runner_finish_source_pins_local_cuda_scorer_and_never_self_certifies() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "09-speaker-score.py" in source
    assert "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e" in source
    assert "--finish-acoustic-leak" in source
    assert "--core-only" in source
    assert '\"device\": \"cpu\"' not in source
    assert "remote_audio_judge" not in source
    assert "overall_status" not in source


def test_runner_accepts_only_positive_numeric_worker_allocator_memory() -> None:
    runner = _runner_module("phase09_runner_worker_memory")

    assert runner._qwen_torch_reserved_mib(
        {"tts_model": {"torch_reserved_mib": 5604.0}}
    ) == 5604.0
    for payload in (
        {},
        {"tts_model": {}},
        {"tts_model": {"torch_reserved_mib": None}},
        {"tts_model": {"torch_reserved_mib": "5604"}},
        {"tts_model": {"torch_reserved_mib": 0}},
        {"tts_model": {"torch_reserved_mib": math.nan}},
    ):
        with pytest.raises(runner.EvidenceRunnerError):
            runner._qwen_torch_reserved_mib(payload)


def test_canonical_deploy_owns_final_qwen_core_evidence_and_copyback() -> None:
    deploy_path = PHASE_DIR.parents[2] / "scripts" / "deploy-omen.sh"
    source = deploy_path.read_text(encoding="utf-8")

    assert 'RAYME_OMEN_VERIFY_QWEN3="${RAYME_OMEN_VERIFY_QWEN3:-0}"' in source
    assert "$env:RAYME_OMEN_VERIFY_QWEN3" in source
    assert "$verifyQwen3" in source
    assert "microsoft/wavlm-base-plus-sv" in source
    assert "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e" in source
    assert "snapshot_download" in source
    assert "09-run-omen-evidence.py" in source
    assert "--core-only" in source
    assert "09-verify-evidence.py" in source
    assert "--core-ready" in source
    assert "tts_model.torch_reserved_mib" in source
    assert "Qwen worker Torch reserved memory could not be measured" in source
    assert "Qwen worker Torch reserved memory exceeds the 5888 MiB release limit" in source
    assert "--query-compute-apps=used_memory" not in source
    assert "RAYME_QWEN3_TORCH_RESERVED_MIB" not in source

    for filename in (
        "qwen3-runtime.json",
        "qwen3-webrtc-status.json",
        "qwen3-call-flow.json",
        "qwen3-soak.json",
        "qwen3-stt.json",
        "qwen3-permitted-reference.wav",
        "qwen3-permitted-reference.txt",
        "qwen3-permitted-provenance.json",
        "qwen3-fake-mic.wav",
    ):
        assert filename in source

    assert "__RAYME_QWEN3_CORE_READY__" in source
    assert "09-speaker-score.py" not in source
