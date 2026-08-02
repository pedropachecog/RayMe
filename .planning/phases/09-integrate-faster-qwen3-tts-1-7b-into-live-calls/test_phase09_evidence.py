from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

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


def test_manifest_keeps_native_ttfa_stretch_separate_from_live_hard_gates() -> None:
    thresholds = _manifest()["thresholds"]

    assert thresholds["native_hot_median_first_chunk_ms"] == 600.0
    assert thresholds["rayme_first_playback_ms"] == 1250.0
    assert thresholds["minimum_sample_rtfx"] == 1.05
    assert thresholds["minimum_median_rtfx"] == 1.25


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
    assert payload["critical_gates"] == ["speaker_stability"]
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


def test_hardware_tracer_fake_microphone_has_loop_safe_response_window(tmp_path: Path) -> None:
    tracer = _runner_module("phase09_runner_fake_microphone_silence").load_hardware_tracer()
    fixture = tmp_path / "fake-microphone.wav"
    sample_rate = 16_000
    voiced_frames = sample_rate
    with wave.open(str(fixture), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(b"\x01\x00" * voiced_frames)

    tracer._append_pcm_wav_silence(
        fixture,
        tracer.FAKE_MICROPHONE_TRAILING_SILENCE_MS,
    )

    with wave.open(str(fixture), "rb") as source:
        frames = source.readframes(source.getnframes())
        trailing_frames = int(
            sample_rate * tracer.FAKE_MICROPHONE_TRAILING_SILENCE_MS / 1000
        )
        assert source.getnframes() == voiced_frames + trailing_frames
    assert frames[-trailing_frames * 2 :] == b"\x00" * trailing_frames * 2
    # Chromium loops the finite fake-microphone WAV. The closing silence must
    # cover VAD turn close plus STT, LLM, early streaming, and short playout so
    # the next synthetic utterance cannot barge into every assistant reply.
    assert tracer.FAKE_MICROPHONE_TRAILING_SILENCE_MS >= 12_000


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


def test_hardware_tracer_collapses_packed_stereo_without_stretching_audio() -> None:
    import numpy as np

    tracer = _runner_module("phase09_runner_packed_stereo_capture").load_hardware_tracer()

    class Layout:
        channels = (object(), object())

    class Format:
        is_planar = False

    class Frame:
        layout = Layout()
        format = Format()

        def to_ndarray(self) -> object:
            # PyAV exposes packed stereo as one row of interleaved L/R samples.
            return np.asarray([[100, 300, -200, 200, 1000, 1000]], dtype=np.int16)

    actual = tracer._decoded_audio_frame_to_int16(Frame())

    assert actual.dtype == np.int16
    assert actual.tolist() == [200, 0, 1000]


def test_evidence_normalizes_numeric_ordinal_date_suffixes() -> None:
    runner = _runner_module("phase09_runner_numeric_ordinal_normalization")

    expected = "Pedro called on October 12."
    observed = "Pedro called on October 12th."

    assert runner._normalized_words(expected)[-1] == "12"
    assert runner._normalized_words(observed)[-1] == "12"
    assert runner._wer(expected, observed) == 0.0


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


def test_hardware_tracer_distinguishes_bounded_transport_drain_from_late_audio() -> None:
    import numpy as np

    tracer = _runner_module("phase09_runner_cancel_drain").load_hardware_tracer()
    acknowledged_at = 100.0
    audible = np.asarray([0, 256, -256], dtype=np.int16)
    silent = np.asarray([0, 0, 0], dtype=np.int16)
    frames = [
        (acknowledged_at - 0.001, audible),
        (acknowledged_at + 0.001, audible),
        (acknowledged_at + 0.250, audible),
        (acknowledged_at + 0.251, audible),
        (acknowledged_at + 0.300, silent),
    ]

    assert tracer._partition_interrupt_audio_frames(
        frames,
        acknowledged_at=acknowledged_at,
        receiver_drain_ms=250,
    ) == (2, 1)


def test_hardware_tracer_requires_measured_exact_zero_pending_track_metrics() -> None:
    tracer = _runner_module("phase09_runner_cancel_pending_metric").load_hardware_tracer()
    measured_zero = {
        "track_metrics_present": True,
        "track_admission_capacity_samples": 72_000,
        "track_pending_samples": 0,
        "track_pending_audio_ms": 0.0,
    }

    assert tracer._require_zero_track_pending_metrics(measured_zero) == measured_zero
    for invalid in (
        {},
        {**measured_zero, "track_metrics_present": False},
        {**measured_zero, "track_admission_capacity_samples": 0},
        {**measured_zero, "track_pending_samples": "0"},
        {**measured_zero, "track_pending_audio_ms": None},
        {**measured_zero, "track_pending_audio_ms": "0"},
    ):
        with pytest.raises(tracer.TracerFailure):
            tracer._require_zero_track_pending_metrics(invalid)
    with pytest.raises(tracer.TracerFailure, match="retained pending samples"):
        tracer._require_zero_track_pending_metrics(
            {
                **measured_zero,
                "track_pending_samples": 1,
                "track_pending_audio_ms": 0.0,
            }
        )
    with pytest.raises(tracer.TracerFailure, match="retained pending audio"):
        tracer._require_zero_track_pending_metrics(
            {**measured_zero, "track_pending_audio_ms": 0.1}
        )


def test_hardware_tracer_stored_result_rechecks_receiver_and_track_truth() -> None:
    import copy

    tracer = _runner_module("phase09_runner_stored_cancellation_truth").load_hardware_tracer()
    commit = "a" * 40
    digest = "b" * 64
    stream = {
        "event_order": ["ai_audio_started", "ai_done"],
        "pcm_sha256": digest,
        "wav_sha256": digest,
        "peak": 512,
        "immediate": {
            "streaming_used": True,
            "fallback_used": False,
            "whole_wav_fallback_used": False,
        },
        "final": {"bridge_queue_capacity": 2, "bridge_queue_high_water": 1},
    }
    payload = {
        "schema_version": tracer.SCHEMA_VERSION,
        "phase": "09",
        "plan": "04",
        "commit_sha": commit,
        "runtime_identity": {
            "runtime_version": tracer.RUNTIME_VERSION,
            "runtime_source_commit": tracer.RUNTIME_COMMIT,
            "model_id": tracer.MODEL_ID,
            "model_revision": tracer.MODEL_REVISION,
            "declared_model_revision": tracer.MODEL_REVISION,
            "torch_version": tracer.EXPECTED_TORCH,
            "torch_cuda_version": tracer.EXPECTED_CUDA,
            "cuda_available": True,
            "gpu_name": tracer.EXPECTED_GPU,
            "sample_rate": 24000,
            "deployed_commit": commit,
        },
        "reference_authorization": {
            "voice_data_steward": "steward-opaque",
            "authorization_basis": "generated_non_person_fixture",
            "use_scope": tracer.AUTHORIZED_SCOPE,
            "source": "generated_non_person_fixture",
            "opaque_voice_id": "voice-opaque",
            "opaque_asset_id": "asset-opaque",
            "reference_sha256": digest,
            "transcript_sha256": digest,
            "fake_microphone_sha256": digest,
            "temporary_reference_deleted_after_upload": True,
            "temporary_transcript_deleted_after_upload": True,
        },
        "readiness": {
            "observations": [
                {"loading_engine": tracer.ENGINE_ID, "prompt_state": "prewarming"},
                {"loading_engine": None, "prompt_state": "ready"},
            ],
            "prepared_model_state": "resident",
            "prepared_prompt_state": "ready",
            "resident_tts_engine": tracer.ENGINE_ID,
            "resident_tts_count": 1,
            "status_deployed_commit": commit,
        },
        "normal_streams": [
            {**stream, "bucket_id": "short"},
            {
                **stream,
                "bucket_id": "medium",
                "producer_running_at_audio_started": True,
                "producer_running_at_remote_playout": True,
                "first_before_completion": True,
                "remote_before_response": True,
            },
            {
                **stream,
                "bucket_id": "long",
                "producer_running_at_audio_started": True,
                "producer_running_at_remote_playout": True,
                "first_before_completion": True,
                "remote_before_response": True,
            },
        ],
        "cancellation": {
            "audio_started_count": 1,
            "normal_ai_done_count": 0,
            "post_cancel_nonzero_frames": 0,
            "worker_ack_upper_bound_ms": 10.0,
            "receiver_drain_ms": 250,
            "track_metrics_present": True,
            "track_admission_capacity_samples": 72_000,
            "track_pending_samples": 0,
            "track_pending_audio_ms": 0.0,
            "forced_termination_detected": False,
            "recovery": {"passed": True, "pcm_sha256": digest, "wav_sha256": digest},
        },
    }

    tracer._verify_payload(payload, expected_commit=commit)
    for field, value, message in (
        ("receiver_drain_ms", None, "receiver drain contract"),
        ("track_metrics_present", False, "no measured track telemetry"),
        ("track_admission_capacity_samples", 0, "admission capacity"),
        ("track_pending_samples", 1, "retained pending samples"),
        ("track_pending_audio_ms", 0.1, "retained pending audio"),
    ):
        invalid = copy.deepcopy(payload)
        invalid["cancellation"][field] = value
        with pytest.raises(tracer.TracerFailure, match=message):
            tracer._verify_payload(invalid, expected_commit=commit)


def test_hardware_tracer_observes_past_delayed_interrupt_event_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import numpy as np

    tracer = _runner_module("phase09_runner_delayed_interrupt_event").load_hardware_tracer()
    acknowledged_at = 100.01
    event_received_at = 100.60
    sleep_delays: list[float] = []

    class RecordingApi:
        ai_base_url = "https://ai.invalid"

        def post_json(
            self,
            _base_url: str,
            path: str,
            _payload: dict[str, object],
        ) -> object:
            if path.endswith("/interrupt"):
                return tracer.ApiResponse(
                    status=200,
                    payload={"receiver_drain_ms": 250},
                )
            return tracer.ApiResponse(status=409, payload={})

    class DelayedEventPeer:
        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []
            self.wait_count = 0
            self.capture_stopped = False

        def start_capture(self, captured_turn_id: str) -> None:
            assert captured_turn_id.startswith("trace-cancel-")
            self.events = [
                {"type": "ai_audio_started", "turn_id": captured_turn_id},
                {
                    "type": "interrupted",
                    "cancelled_turn_id": captured_turn_id,
                    "receiver_drain_ms": 250,
                    "_received_monotonic": event_received_at,
                    "tts_playback_final": {
                        "track_metrics_present": True,
                        "track_admission_capacity_samples": 72_000,
                        "track_pending_samples": 0,
                        "track_pending_audio_ms": 0.0,
                    },
                },
            ]

        async def wait_for_event(self, *_args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
            event = self.events[self.wait_count]
            self.wait_count += 1
            return self.wait_count - 1, event

        async def wait_for_nonzero_audio(self, *, timeout: float) -> float:
            assert timeout == 30.0
            return 99.9

        def stop_capture(self) -> tuple[list[tuple[float, object]], None]:
            self.capture_stopped = True
            audible = np.asarray([0, 256, -256], dtype=np.int16)
            return [(event_received_at + 0.01, audible)], None

    clock = iter((100.0, acknowledged_at, event_received_at + 0.01))
    monkeypatch.setattr(tracer.time, "perf_counter", lambda: next(clock))

    async def record_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(tracer.asyncio, "sleep", record_sleep)
    peer = DelayedEventPeer()

    with pytest.raises(
        tracer.TracerFailure,
        match="Audible Qwen frames arrived after the bounded receiver drain",
    ):
        asyncio.run(
            tracer._run_cancel_sample(
                RecordingApi(),
                peer,
                session_id="session-delayed-event",
                voice_id="voice-qwen",
                reference_audio=b"reference",
                transcript="authorized transcript",
            )
        )

    assert peer.capture_stopped is True
    assert sleep_delays == [pytest.approx(0.44)]


@pytest.mark.parametrize("received_at", [None, True, "100.0", math.nan, math.inf])
def test_hardware_tracer_rejects_invalid_interrupted_event_timestamp(
    received_at: object,
) -> None:
    tracer = _runner_module("phase09_runner_invalid_interrupt_timestamp").load_hardware_tracer()

    with pytest.raises(tracer.TracerFailure, match="event timestamp is invalid"):
        tracer._interrupt_capture_deadline(
            interrupt_acknowledged=100.0,
            interrupted_event={"_received_monotonic": received_at},
            receiver_drain_ms=250,
        )


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


def test_hardware_tracer_uses_upload_implied_authorization() -> None:
    import asyncio

    tracer = _runner_module("phase09_runner_saved_voice_contract").load_hardware_tracer()

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
        )
    )

    assert (voice_id, asset_id) == ("voice_phase09", "asset_phase09")
    assert api.saved_payload is not None
    assert api.saved_payload["metadata"] == {"source": "phase09_hardware_tracer"}
    assert not {
        "voice_data_steward",
        "authorization_basis",
        "use_scope",
    }.intersection(api.saved_payload)


def test_core_runner_uses_current_saved_voice_helper_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    runner = _runner_module("phase09_runner_saved_voice_caller_contract")
    tracer = runner.load_hardware_tracer()
    selection = _fallback_selection(tmp_path / "selection")
    expected_commit = "a" * 40

    class SavedVoiceHelperReached(Exception):
        pass

    async def create_saved_voice(
        api: object,
        *,
        reference_audio: bytes,
        transcript: str,
    ) -> tuple[str, str]:
        assert api is not None
        assert reference_audio == selection.reference_path.read_bytes()
        assert transcript == selection.transcript_path.read_text(encoding="utf-8").strip()
        raise SavedVoiceHelperReached

    monkeypatch.setattr(tracer, "_runtime_identity", lambda commit: {})
    monkeypatch.setattr(tracer, "_create_saved_voice", create_saved_voice)
    production = runner.RayMeProductionPath(
        manifest=_manifest(),
        tracer=tracer,
        expected_commit=expected_commit,
        selection=selection,
        web_base_url="https://rayme.invalid",
        ai_base_url="https://ai.invalid",
        work_dir=tmp_path / "work",
        timeout=1.0,
    )

    with pytest.raises(SavedVoiceHelperReached):
        asyncio.run(production.open())


def test_core_runner_authenticates_canonical_captured_audio_stt_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    runner = _runner_module("phase09_runner_stt_canonical_service_auth")
    service_token = "p" * 32
    ssl_context = object()
    captured: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"accepted","transcript":"hello"}'

    class Opener:
        def open(self, request: object, *, timeout: float) -> Response:
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

    def capture_https_handler(*, context: object) -> object:
        captured["ssl_context"] = context
        return SimpleNamespace(context=context)

    def capture_opener(*handlers: object) -> Opener:
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(runner, "HTTPSHandler", capture_https_handler)
    monkeypatch.setattr(runner, "build_opener", capture_opener)
    production = runner.RayMeProductionPath(
        manifest=_manifest(),
        tracer=SimpleNamespace(),
        expected_commit="a" * 40,
        selection=SimpleNamespace(),
        web_base_url="https://rayme.invalid",
        ai_base_url="https://foreign-config.invalid",
        work_dir=tmp_path / "work",
        timeout=1.0,
    )
    production.api = SimpleNamespace(
        ai_base_url="https://ai.invalid",
        ssl_context=ssl_context,
        service_auth_token=service_token,
    )
    audio_path = tmp_path / "captured.wav"
    private_audio = b"RIFF captured production audio"
    audio_path.write_bytes(private_audio)

    result = asyncio.run(production._stt("captured-audio", "hello", audio_path))

    request = captured["request"]
    assert request.full_url == "https://ai.invalid/stt/transcribe"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == f"Bearer {service_token}"
    assert private_audio in request.data
    assert captured["ssl_context"] is ssl_context
    assert captured["timeout"] == 1.0
    assert any(isinstance(handler, runner._NoRedirectHandler) for handler in captured["handlers"])
    assert result == {"accepted": True, "wer": 0.0, "final_word_pass": True}


@pytest.mark.parametrize("redirect_status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("foreign_scheme", ["https", "http"])
def test_core_runner_rejects_stt_redirect_without_foreign_header_or_body(
    monkeypatch: pytest.MonkeyPatch,
    redirect_status: int,
    foreign_scheme: str,
) -> None:
    runner = _runner_module(
        f"phase09_runner_stt_redirect_{foreign_scheme}_{redirect_status}"
    )
    service_token = "redirect-secret-" + "x" * 32
    private_audio = b"RIFF private redirect payload"
    ssl_context = object()
    trusted_requests: list[object] = []
    foreign_requests: list[object] = []
    foreign_url = f"{foreign_scheme}://attacker.invalid/collect"

    class Opener:
        def __init__(self, handlers: tuple[object, ...]) -> None:
            self.handlers = handlers

        def open(self, request: object, *, timeout: float) -> object:
            assert timeout == 2.0
            trusted_requests.append(request)
            redirect_handler = next(
                handler
                for handler in self.handlers
                if isinstance(handler, runner._NoRedirectHandler)
            )
            try:
                redirected = redirect_handler.redirect_request(
                    request,
                    None,
                    redirect_status,
                    "private redirect response",
                    {"Location": foreign_url},
                    foreign_url,
                )
            except runner.HTTPError:
                raise
            foreign_requests.append(redirected)
            raise AssertionError("the authenticated request was replayed")

    monkeypatch.setattr(
        runner,
        "HTTPSHandler",
        lambda *, context: SimpleNamespace(context=context),
    )
    monkeypatch.setattr(runner, "build_opener", lambda *handlers: Opener(handlers))

    with pytest.raises(runner.EvidenceRunnerError) as raised:
        runner._multipart_audio_request(
            url="https://ai.invalid/stt/transcribe",
            trusted_ai_base_url="https://ai.invalid",
            audio=private_audio,
            service_auth_token=service_token,
            timeout=2.0,
            ssl_context=ssl_context,
        )

    assert str(raised.value) == (
        f"RayMe STT rejected captured production audio (status {redirect_status})"
    )
    assert len(trusted_requests) == 1
    trusted_request = trusted_requests[0]
    assert trusted_request.full_url == "https://ai.invalid/stt/transcribe"
    assert trusted_request.get_header("Authorization") == f"Bearer {service_token}"
    assert private_audio in trusted_request.data
    assert foreign_requests == []
    assert service_token not in str(raised.value)
    assert private_audio.decode() not in str(raised.value)


@pytest.mark.parametrize(
    ("url", "trusted_ai_base_url"),
    [
        ("http://ai.invalid/stt/transcribe", "https://ai.invalid"),
        ("https://attacker.invalid/stt/transcribe", "https://ai.invalid"),
        ("https://ai.invalid/stt/transcribe", "http://ai.invalid"),
    ],
)
def test_core_runner_rejects_untrusted_initial_stt_destination_before_io(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    trusted_ai_base_url: str,
) -> None:
    runner = _runner_module("phase09_runner_stt_untrusted_initial_destination")

    def unexpected_opener(*_handlers: object) -> object:
        raise AssertionError("an untrusted STT destination must fail before I/O")

    monkeypatch.setattr(runner, "build_opener", unexpected_opener)
    with pytest.raises(
        runner.EvidenceRunnerError,
        match=r"^RayMe STT destination is not trusted$",
    ):
        runner._multipart_audio_request(
            url=url,
            trusted_ai_base_url=trusted_ai_base_url,
            audio=b"RIFF private initial payload",
            service_auth_token="t" * 32,
            timeout=1.0,
            ssl_context=object(),
        )


@pytest.mark.parametrize("service_token", ["", "   ", "x" * 31, f" {'x' * 31} "])
def test_core_runner_rejects_missing_or_short_stt_identity_before_io(
    monkeypatch: pytest.MonkeyPatch,
    service_token: str,
) -> None:
    runner = _runner_module("phase09_runner_stt_missing_or_short_identity")

    def unexpected_opener(*_handlers: object) -> object:
        raise AssertionError("an invalid service identity must fail before I/O")

    monkeypatch.setattr(runner, "build_opener", unexpected_opener)
    with pytest.raises(
        runner.EvidenceRunnerError,
        match=r"^RayMe AI service identity is not configured$",
    ) as raised:
        runner._multipart_audio_request(
            url="https://ai.invalid/stt/transcribe",
            trusted_ai_base_url="https://ai.invalid",
            audio=b"RIFF private token payload",
            service_auth_token=service_token,
            timeout=1.0,
            ssl_context=object(),
        )
    if service_token.strip():
        assert service_token.strip() not in str(raised.value)


@pytest.mark.parametrize("status", [401, 403, 500])
def test_core_runner_sanitizes_stt_auth_and_server_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: int,
) -> None:
    runner = _runner_module(f"phase09_runner_stt_sanitized_{status}")
    incorrect_token = "incorrect-token-" + "x" * 32
    private_response = "private transcript and reference response"

    class PrivateResponse:
        def read(self) -> bytes:
            raise AssertionError("a rejected private response must not be read")

        def close(self) -> None:
            return None

    class Opener:
        def open(self, request: object, *, timeout: float) -> object:
            assert request.get_header("Authorization") == f"Bearer {incorrect_token}"
            assert timeout == 1.0
            raise runner.HTTPError(
                request.full_url,
                status,
                f"{private_response} {incorrect_token}",
                {},
                PrivateResponse(),
            )

    monkeypatch.setattr(
        runner,
        "HTTPSHandler",
        lambda *, context: SimpleNamespace(context=context),
    )
    monkeypatch.setattr(runner, "build_opener", lambda *_handlers: Opener())

    with pytest.raises(runner.EvidenceRunnerError) as raised:
        runner._multipart_audio_request(
            url="https://ai.invalid/stt/transcribe",
            trusted_ai_base_url="https://ai.invalid",
            audio=b"RIFF private rejected payload",
            service_auth_token=incorrect_token,
            timeout=1.0,
            ssl_context=object(),
        )

    assert str(raised.value) == (
        f"RayMe STT rejected captured production audio (status {status})"
    )
    assert raised.value.__cause__ is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert incorrect_token not in str(raised.value)
    assert private_response not in str(raised.value)
    assert list(tmp_path.iterdir()) == []


def test_runner_main_sanitizes_unexpected_exceptions_without_private_detail(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _runner_module("phase09_runner_unexpected_failure")
    private_detail = r"C:\private\voice.wav secret transcript"
    args = SimpleNamespace(
        expected_commit="a" * 40,
        dry_run=True,
        core_only=False,
        finish_acoustic_leak=False,
    )

    def fail_manifest_load() -> dict[str, object]:
        raise TypeError(private_detail)

    monkeypatch.setattr(runner, "_parse_args", lambda argv: args)
    monkeypatch.setattr(runner, "load_manifest", fail_manifest_load)

    assert runner.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL: Unexpected evidence runner failure (TypeError)\n"
    assert private_detail not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("failure_type", (OSError, RuntimeError, ValueError))
def test_runner_main_sanitizes_expected_builtin_exception_messages(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_type: type[Exception],
) -> None:
    runner = _runner_module(f"phase09_runner_{failure_type.__name__.lower()}_failure")
    private_detail = r"C:\private\voice.wav exact secret transcript"
    args = SimpleNamespace(
        expected_commit="a" * 40,
        dry_run=True,
        core_only=False,
        finish_acoustic_leak=False,
    )

    def fail_manifest_load() -> dict[str, object]:
        raise failure_type(private_detail)

    monkeypatch.setattr(runner, "_parse_args", lambda argv: args)
    monkeypatch.setattr(runner, "load_manifest", fail_manifest_load)

    assert runner.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"FAIL: Unexpected evidence runner failure ({failure_type.__name__})\n"
    )
    assert private_detail not in captured.err
    assert "voice.wav" not in captured.err
    assert "secret transcript" not in captured.err
    assert "Traceback" not in captured.err


def test_runner_main_preserves_curated_domain_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _runner_module("phase09_runner_curated_domain_failure")
    args = SimpleNamespace(
        expected_commit="a" * 40,
        dry_run=True,
        core_only=False,
        finish_acoustic_leak=False,
    )

    def fail_manifest_load() -> dict[str, object]:
        raise runner.EvidenceRunnerError("Evidence manifest is invalid")

    monkeypatch.setattr(runner, "_parse_args", lambda argv: args)
    monkeypatch.setattr(runner, "load_manifest", fail_manifest_load)

    assert runner.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL: Evidence manifest is invalid\n"


def test_runner_main_success_remains_visible(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _runner_module("phase09_runner_success")
    args = SimpleNamespace(
        expected_commit="a" * 40,
        dry_run=True,
        core_only=False,
        finish_acoustic_leak=False,
    )

    monkeypatch.setattr(runner, "_parse_args", lambda argv: args)
    monkeypatch.setattr(runner, "load_manifest", lambda: {})

    assert runner.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == "PASS\n"
    assert captured.err == ""


@pytest.mark.parametrize("failure", (KeyboardInterrupt(), SystemExit(7)))
def test_runner_main_does_not_swallow_base_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException,
) -> None:
    runner = _runner_module(
        f"phase09_runner_{failure.__class__.__name__.lower()}_failure"
    )
    args = SimpleNamespace(
        expected_commit="a" * 40,
        dry_run=True,
        core_only=False,
        finish_acoustic_leak=False,
    )

    def fail_manifest_load() -> dict[str, object]:
        raise failure

    monkeypatch.setattr(runner, "_parse_args", lambda argv: args)
    monkeypatch.setattr(runner, "load_manifest", fail_manifest_load)

    with pytest.raises(failure.__class__) as raised:
        runner.main([])
    if isinstance(failure, SystemExit):
        assert raised.value.code == 7
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


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
        if self.fail_at == "prewarm":
            raise RuntimeError("prewarm failed")

    async def assert_qwen_ready(self) -> dict[str, object]:
        self.events.append("assert_qwen_ready")
        return {"model_state": "resident", "prompt_state": "ready"}

    async def close(self) -> None:
        self.events.append("close")


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
        "close",
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


@pytest.mark.parametrize("fail_at", ["scorer", "reload", "prewarm"])
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
    assert lifecycle.events[-1] == "close"
    assert "cpu" not in " ".join(lifecycle.events).lower()
    assert "remote" not in " ".join(lifecycle.events).lower()


def test_omen_finish_cleanup_ends_ai_session_before_closing_peer() -> None:
    import asyncio

    runner = _runner_module("phase09_runner_finish_cleanup")
    events: list[str] = []

    class RecordingApi:
        ai_base_url = "https://ai.invalid"

        def post_json(self, base_url: str, path: str, payload: dict[str, object]) -> object:
            events.append(f"end:{base_url}{path}:{payload['reason']}")
            return SimpleNamespace(status=200, payload={"state": "ended"})

    class RecordingPeer:
        async def close(self) -> None:
            events.append("peer.close")

    lifecycle = runner.OmenFinishLifecycle.__new__(runner.OmenFinishLifecycle)
    lifecycle.api = RecordingApi()
    lifecycle.tracer = SimpleNamespace(
        _require_ok=lambda response, label: events.append(f"ok:{label}") or response.payload
    )
    lifecycle.session_id = "phase09-finish-regression"
    lifecycle.peer = RecordingPeer()

    asyncio.run(lifecycle.close())

    assert events == [
        "end:https://ai.invalid/webrtc/sessions/phase09-finish-regression/end:phase09_finish_complete",
        "ok:finish Qwen session end",
        "peer.close",
    ]
    assert lifecycle.session_id == ""
    assert lifecycle.peer is None


def test_runner_finish_source_pins_local_cuda_scorer_and_never_self_certifies() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "09-speaker-score.py" in source
    assert "feb593a6c23c1cc3d9510425c29b0a14d2b07b1e" in source
    assert "--finish-acoustic-leak" in source
    assert "--core-only" in source
    assert '\"device\": \"cpu\"' not in source
    assert "remote_audio_judge" not in source
    assert "overall_status" not in source
    assert '\"reference_transcript\": PUBLIC_SCORER_SWITCH_TRANSCRIPT' in source


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
    assert "Protect-Phase09QwenLogs" in source
    assert "<redacted:phase09-private-reference>" in source
    assert source.index("Protect-Phase09QwenLogs") < source.index(
        "Start-ScheduledTask -TaskName RayMePhase1AI"
    )

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
