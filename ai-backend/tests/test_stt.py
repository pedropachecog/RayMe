from __future__ import annotations

import asyncio
import importlib
import inspect
from dataclasses import asdict, is_dataclass
from typing import Any

import pytest

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
