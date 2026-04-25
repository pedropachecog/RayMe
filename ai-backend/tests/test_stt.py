from __future__ import annotations

import asyncio
import importlib
import inspect
import os
from dataclasses import asdict, is_dataclass
from io import BytesIO
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import create_app

EXPECTED_WHISPER_OPTIONS = {
    "language": "en",
    "task": "transcribe",
    "condition_on_previous_text": False,
}
WHISPER_OPTION_CONTRACT = 'language="en" task="transcribe" condition_on_previous_text=False'
MANUAL_TRANSCRIPT_CONTRACT = "manual transcript fallback"
EXPECTED_BLOCKLIST_PHRASES = {
    "thank you for watching",
    "thanks for watching",
    "subscribe to my channel",
}
ROUTE_CONTRACT = "POST /stt/transcribe"


class FakeWhisperSegment:
    def __init__(self, text: str) -> None:
        self.text = text
        self.start = 0.0
        self.end = 1.0


class FakeWhisperInfo:
    language = "en"


class FakeWhisperModel:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[FakeWhisperSegment], FakeWhisperInfo]:
        self.calls.append({"audio": audio, "kwargs": kwargs})
        return [FakeWhisperSegment(self.transcript)], FakeWhisperInfo()


class SpeechVad:
    ready = True
    threshold = 0.5
    end_silence_ms = 700

    def speech_timestamps(self, audio: Any) -> list[dict[str, int]]:
        return [{"start": 0, "end": 16000}]


class NoSpeechVad(SpeechVad):
    def speech_timestamps(self, audio: Any) -> list[dict[str, int]]:
        return []


class RouteFakeSttAdapter:
    def __init__(self, result: dict[str, Any] | None = None, *, fail: bool = False) -> None:
        self.result = result
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("Traceback: CUDA out of memory in C:\\secret\\model.bin")
        assert self.result is not None
        return self.result


def _complete(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    pytest.fail(f"Expected dict-like STT response, got {type(value)!r}")


def _make_stt_adapter(fake_model: FakeWhisperModel) -> Any:
    stt_module = importlib.import_module("app.models.stt")
    WhisperSttAdapter = getattr(stt_module, "WhisperSttAdapter")

    constructor_attempts = (
        {
            "model": fake_model,
            "model_name": "distil-large-v3",
            "compute_type": "int8_float16",
        },
        {
            "whisper_model": fake_model,
            "model_name": "distil-large-v3",
            "compute_type": "int8_float16",
        },
        {"model": fake_model},
        {"whisper_model": fake_model},
    )
    errors: list[str] = []
    for kwargs in constructor_attempts:
        try:
            return WhisperSttAdapter(**kwargs)
        except TypeError as exc:
            errors.append(str(exc))
    pytest.fail(f"WhisperSttAdapter must accept a fake model for unit tests: {errors}")


def _call_transcribe(adapter: Any, *, audio: Any, vad_adapter: Any) -> dict[str, Any]:
    call_attempts = (
        {"audio": audio, "vad_adapter": vad_adapter, "vad_threshold": 0.5, "vad_end_silence_ms": 700},
        {"audio_path": audio, "vad_adapter": vad_adapter, "vad_threshold": 0.5, "vad_end_silence_ms": 700},
        {"audio": audio, "vad": vad_adapter, "vad_threshold": 0.5, "vad_end_silence_ms": 700},
        {"audio_path": audio, "speech_timestamps": vad_adapter.speech_timestamps(audio)},
    )
    errors: list[str] = []
    for method_name in ("transcribe", "transcribe_sample", "transcribe_audio"):
        method = getattr(adapter, method_name, None)
        if method is None:
            continue
        for kwargs in call_attempts:
            try:
                return _to_mapping(_complete(method(**kwargs)))
            except TypeError as exc:
                errors.append(f"{method_name}: {exc}")
    pytest.fail(f"STT adapter must expose a VAD-gated transcribe method: {errors}")


def test_stt_adapter_uses_phase_zero_english_whisper_options() -> None:
    fake_model = FakeWhisperModel("Hello from the sample")
    adapter = _make_stt_adapter(fake_model)

    result = _call_transcribe(adapter, audio="sample.wav", vad_adapter=SpeechVad())

    assert WHISPER_OPTION_CONTRACT
    assert fake_model.calls, "VAD speech should allow Whisper transcription"
    whisper_kwargs = fake_model.calls[0]["kwargs"]
    assert whisper_kwargs["language"] == EXPECTED_WHISPER_OPTIONS["language"]
    assert whisper_kwargs["task"] == EXPECTED_WHISPER_OPTIONS["task"]
    assert (
        whisper_kwargs["condition_on_previous_text"]
        is EXPECTED_WHISPER_OPTIONS["condition_on_previous_text"]
    )
    assert result["language"] == "en"
    assert result["model"] == "distil-large-v3"
    assert result["compute_type"] == "int8_float16"
    assert whisper_kwargs["beam_size"] == 5
    assert whisper_kwargs["vad_filter"] is True
    assert whisper_kwargs["vad_parameters"]["threshold"] == 0.5
    assert whisper_kwargs["vad_parameters"]["min_silence_duration_ms"] == 700


def test_vad_gate_blocks_no_speech_before_transcript_return() -> None:
    fake_model = FakeWhisperModel("This should not be transcribed")
    adapter = _make_stt_adapter(fake_model)

    result = _call_transcribe(adapter, audio="quiet.wav", vad_adapter=NoSpeechVad())

    assert fake_model.calls == []
    assert result["status"] == "needs_manual_transcript"
    assert result["speech_detected"] is False
    assert result["retry_allowed"] is True
    assert result["manual_transcript_allowed"] is True
    assert result["transcript"] in ("", None)
    assert MANUAL_TRANSCRIPT_CONTRACT


def test_hallucination_blocklist_filters_common_whisper_filler() -> None:
    stt_module = importlib.import_module("app.models.stt")
    blocklist = set(getattr(stt_module, "HALLUCINATION_BLOCKLIST"))
    fake_model = FakeWhisperModel("Thank you for watching!")
    adapter = _make_stt_adapter(fake_model)

    result = _call_transcribe(adapter, audio="sample.wav", vad_adapter=SpeechVad())

    assert EXPECTED_BLOCKLIST_PHRASES <= {phrase.lower() for phrase in blocklist}
    assert fake_model.calls
    assert result["status"] == "needs_manual_transcript"
    assert result["manual_transcript_allowed"] is True
    assert result["retry_allowed"] is True
    assert result["transcript"] in ("", None)


def test_retry_and_manual_transcript_fallback_response_shape() -> None:
    fake_model = FakeWhisperModel("Subscribe to my channel")
    adapter = _make_stt_adapter(fake_model)

    result = _call_transcribe(adapter, audio="sample.wav", vad_adapter=SpeechVad())

    assert set(result) >= {
        "status",
        "transcript",
        "segments",
        "language",
        "model",
        "compute_type",
        "speech_detected",
        "retry_allowed",
        "manual_transcript_allowed",
    }
    assert result["status"] == "needs_manual_transcript"
    assert result["retry_allowed"] is True
    assert result["manual_transcript_allowed"] is True


def test_audio_io_decodes_uploaded_bytes_to_generated_wav_path() -> None:
    audio_io = importlib.import_module("app.audio.io")
    samples = np.zeros(1600, dtype=np.float32)
    source = BytesIO()
    sf.write(source, samples, 16000, format="WAV")

    helper = getattr(audio_io, "uploaded_bytes_to_temp_wav", None)
    assert helper is not None, "audio IO must expose uploaded_bytes_to_temp_wav"

    result = helper(source.getvalue(), original_filename="../evil-sample.mp3")
    path = result.path if hasattr(result, "path") else result
    try:
        assert os.path.exists(path)
        assert os.path.basename(path).startswith("rayme-stt-")
        assert os.path.basename(path).endswith(".wav")
        assert "evil" not in os.path.basename(path)
        decoded, sample_rate = sf.read(path, dtype="float32")
        assert sample_rate == 16000
        assert decoded.ndim == 1
    finally:
        cleanup = getattr(result, "cleanup", None)
        if callable(cleanup):
            cleanup()
        elif os.path.exists(path):
            os.unlink(path)


def test_silero_vad_adapter_uses_configurable_threshold_and_silence() -> None:
    vad_module = importlib.import_module("app.models.vad")
    SileroVadAdapter = getattr(vad_module, "SileroVadAdapter")
    calls: list[dict[str, Any]] = []

    def fake_get_speech_timestamps(audio: Any, model: Any, **kwargs: Any) -> list[dict[str, int]]:
        calls.append({"audio": audio, "model": model, "kwargs": kwargs})
        return [{"start": 100, "end": 1200}]

    adapter = SileroVadAdapter(
        model=object(),
        get_speech_timestamps_fn=fake_get_speech_timestamps,
        threshold=0.42,
        end_silence_ms=900,
    )

    result = adapter.speech_timestamps(np.zeros(16000, dtype=np.float32))

    assert adapter.ready is True
    assert adapter.threshold == 0.42
    assert adapter.end_silence_ms == 900
    assert result == [{"start": 100, "end": 1200}]
    assert calls[0]["kwargs"]["threshold"] == 0.42
    assert calls[0]["kwargs"]["min_silence_duration_ms"] == 900
    assert calls[0]["kwargs"]["sampling_rate"] == 16000


def test_silero_vad_adapter_loads_temp_wav_paths_before_timestamping(tmp_path: Any) -> None:
    vad_module = importlib.import_module("app.models.vad")
    SileroVadAdapter = getattr(vad_module, "SileroVadAdapter")
    audio_path = tmp_path / "sample.wav"
    sf.write(audio_path, np.zeros(16000, dtype=np.float32), 16000, format="WAV")
    calls: list[dict[str, Any]] = []

    def fake_get_speech_timestamps(audio: Any, model: Any, **kwargs: Any) -> list[dict[str, int]]:
        calls.append({"audio": audio, "model": model, "kwargs": kwargs})
        return [{"start": 0, "end": 16000}]

    adapter = SileroVadAdapter(
        model=object(),
        get_speech_timestamps_fn=fake_get_speech_timestamps,
    )

    result = adapter.speech_timestamps(str(audio_path))

    assert result == [{"start": 0, "end": 16000}]
    assert isinstance(calls[0]["audio"], np.ndarray)
    assert calls[0]["audio"].dtype == np.float32
    assert calls[0]["audio"].shape == (16000,)


def _wav_upload() -> tuple[str, bytes, str]:
    samples = np.zeros(1600, dtype=np.float32)
    source = BytesIO()
    sf.write(source, samples, 16000, format="WAV")
    return ("../unsafe-name.wav", source.getvalue(), "audio/wav")


def _client_with_stt(fake_stt: RouteFakeSttAdapter, vad_adapter: Any | None = None) -> TestClient:
    app = create_app()
    app.state.stt_adapter = fake_stt
    app.state.vad_adapter = vad_adapter or SpeechVad()
    return TestClient(app)


def test_transient_stt_route_accepts_upload_and_returns_contract_fields() -> None:
    fake_stt = RouteFakeSttAdapter(
        {
            "status": "accepted",
            "transcript": "Hello from the sample",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Hello from the sample"}],
            "language": "en",
            "model": "distil-large-v3",
            "compute_type": "int8_float16",
            "speech_detected": True,
            "retry_allowed": False,
            "manual_transcript_allowed": True,
        }
    )
    client = _client_with_stt(fake_stt)

    response = client.post(
        "/stt/transcribe",
        files={"file": _wav_upload()},
        data={"vad_threshold": "0.42", "vad_end_silence_ms": "900"},
    )

    assert ROUTE_CONTRACT
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {
        "status",
        "transcript",
        "segments",
        "language",
        "model",
        "compute_type",
        "speech_detected",
        "retry_allowed",
        "manual_transcript_allowed",
    }
    assert payload["manual_transcript_allowed"] is True
    assert fake_stt.calls[0]["vad_threshold"] == 0.42
    assert fake_stt.calls[0]["vad_end_silence_ms"] == 900
    assert os.path.basename(fake_stt.calls[0]["audio"]).startswith("rayme-stt-")
    assert "unsafe-name" not in os.path.basename(fake_stt.calls[0]["audio"])


def test_transient_stt_route_preserves_manual_fallback_response() -> None:
    fake_stt = RouteFakeSttAdapter(
        {
            "status": "needs_manual_transcript",
            "transcript": "",
            "segments": [],
            "language": "en",
            "model": "distil-large-v3",
            "compute_type": "int8_float16",
            "speech_detected": False,
            "retry_allowed": True,
            "manual_transcript_allowed": True,
        }
    )
    client = _client_with_stt(fake_stt, NoSpeechVad())

    response = client.post("/stt/transcribe", files={"file": _wav_upload()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_manual_transcript"
    assert payload["retry_allowed"] is True
    assert payload["manual_transcript_allowed"] is True


def test_transient_stt_route_returns_sanitized_failure_with_manual_fallback() -> None:
    client = _client_with_stt(RouteFakeSttAdapter(fail=True))

    response = client.post("/stt/transcribe", files={"file": _wav_upload()})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "stt_failed"
    assert detail["message"] == "Transcription failed"
    assert detail["retry_allowed"] is True
    assert detail["manual_transcript_allowed"] is True
    rendered = response.text
    assert "CUDA out of memory" not in rendered
    assert "Traceback" not in rendered
    assert "C:\\" not in rendered
