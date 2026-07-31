from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError


def _protocol_module():
    from app.models import tts_qwen3_protocol

    return tts_qwen3_protocol


def _audio_b64(payload: bytes = b"RIFF-valid-wav-chunk") -> str:
    return base64.b64encode(payload).decode("ascii")


@pytest.mark.parametrize(
    ("payload", "model_name"),
    [
        (
            {"schema_version": 1, "op": "load", "request_id": "load-1"},
            "QwenLoadCommand",
        ),
        (
            {
                "schema_version": 1,
                "op": "prewarm",
                "request_id": "prewarm-1",
                "voice_key": "voice_0123456789abcdef",
                "reference_audio_b64": _audio_b64(),
                "reference_transcript": "The exact spoken reference.",
            },
            "QwenPrewarmCommand",
        ),
        (
            {
                "schema_version": 1,
                "op": "generate",
                "request_id": "turn-1",
                "voice_key": "voice_0123456789abcdef",
                "text": "This audio must stream.",
                "max_new_tokens": 48,
                "hard_audio_seconds": 6.0,
            },
            "QwenGenerateCommand",
        ),
        (
            {"schema_version": 1, "op": "cancel", "request_id": "turn-1"},
            "QwenCancelCommand",
        ),
        (
            {
                "schema_version": 1,
                "op": "invalidate",
                "request_id": "invalidate-1",
                "voice_key": "voice_0123456789abcdef",
            },
            "QwenInvalidateCommand",
        ),
        (
            {"schema_version": 1, "op": "unload", "request_id": "unload-1"},
            "QwenUnloadCommand",
        ),
    ],
)
def test_qwen_protocol_command_schema_is_versioned_and_discriminated(
    payload: dict[str, object], model_name: str
) -> None:
    protocol = _protocol_module()

    command = protocol.parse_command(payload)

    assert type(command).__name__ == model_name
    assert command.schema_version == 1
    assert command.request_id == payload["request_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2, "op": "load", "request_id": "load-1"},
        {"schema_version": 1, "op": "load", "request_id": "x" * 129},
        {"schema_version": 1, "op": "load", "request_id": "unsafe request"},
        {"schema_version": 1, "op": "unknown", "request_id": "load-1"},
        {
            "schema_version": 1,
            "op": "prewarm",
            "request_id": "prewarm-1",
            "voice_key": "voice_0123456789abcdef",
            "reference_audio_b64": "not-base64!!!",
            "reference_transcript": "Spoken words.",
        },
        {
            "schema_version": 1,
            "op": "prewarm",
            "request_id": "prewarm-1",
            "voice_key": "voice_0123456789abcdef",
            "reference_audio_b64": base64.b64encode(b"x" * 65).decode("ascii"),
            "reference_transcript": "Spoken words.",
        },
    ],
)
def test_qwen_protocol_command_schema_rejects_wrong_or_oversized_data(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    protocol = _protocol_module()
    monkeypatch.setattr(protocol, "MAX_REFERENCE_AUDIO_BYTES", 64)

    with pytest.raises(ValidationError):
        protocol.parse_command(payload)


@pytest.mark.parametrize(
    ("payload", "model_name"),
    [
        (
            {
                "schema_version": 1,
                "event": "loaded",
                "request_id": "load-1",
                "engine_id": "qwen3_1_7b",
                "runtime_version": "0.3.2",
                "model_revision": "fd4b254389122332181a7c3db7f27e918eec64e3",
                "device": "cuda",
                "sample_rate": 24000,
                "warmup_prefill": 100,
            },
            "QwenLoadedEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "prompt_ready",
                "request_id": "prewarm-1",
                "voice_key": "voice_0123456789abcdef",
            },
            "QwenPromptReadyEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "prompt_failed",
                "request_id": "prewarm-1",
                "voice_key": "voice_0123456789abcdef",
                "error_code": "qwen3_prompt_failed",
            },
            "QwenPromptFailedEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "invalidated",
                "request_id": "invalidate-1",
                "voice_key": "voice_0123456789abcdef",
            },
            "QwenInvalidatedEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "chunk",
                "request_id": "turn-1",
                "chunk_index": 0,
                "wav_b64": _audio_b64(),
                "sample_rate": 24000,
                "duration_ms": 320.0,
                "generated_at_ms": 369.0,
                "total_steps_so_far": 4,
            },
            "QwenChunkEvent",
        ),
        (
            {
                "schema_version": 1,
                "event": "done",
                "request_id": "turn-1",
                "chunk_count": 1,
                "natural_eos": True,
            },
            "QwenTerminalEvent",
        ),
    ],
)
def test_qwen_protocol_event_schema_is_versioned_and_bounded(
    payload: dict[str, object], model_name: str
) -> None:
    protocol = _protocol_module()

    event = protocol.parse_event(payload)

    assert type(event).__name__ == model_name
    assert event.schema_version == 1


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": 2,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 369.0,
            "total_steps_so_far": 4,
        },
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": "%%%%",
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 369.0,
            "total_steps_so_far": 4,
        },
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 48000,
            "duration_ms": 320.0,
            "generated_at_ms": 369.0,
            "total_steps_so_far": 4,
        },
        {
            "schema_version": 1,
            "event": "error",
            "request_id": "turn-1",
            "chunk_count": 0,
            "natural_eos": True,
            "error_code": "qwen3_worker_failed",
        },
    ],
)
def test_qwen_protocol_event_schema_rejects_malformed_data(payload: dict[str, object]) -> None:
    protocol = _protocol_module()

    with pytest.raises(ValidationError):
        protocol.parse_event(payload)


def test_qwen_event_sequence_rejects_wrong_request_non_monotonic_and_late_events() -> None:
    protocol = _protocol_module()
    state = protocol.QwenStreamEventValidator(request_id="turn-1")
    first = protocol.parse_event(
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 400.0,
            "total_steps_so_far": 4,
        }
    )
    state.accept(first)

    for bad_payload in (
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "other-turn",
            "chunk_index": 1,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 700.0,
            "total_steps_so_far": 8,
        },
        {
            "schema_version": 1,
            "event": "chunk",
            "request_id": "turn-1",
            "chunk_index": 0,
            "wav_b64": _audio_b64(),
            "sample_rate": 24000,
            "duration_ms": 320.0,
            "generated_at_ms": 300.0,
            "total_steps_so_far": 4,
        },
    ):
        with pytest.raises(protocol.QwenProtocolError):
            state.accept(protocol.parse_event(bad_payload))

    terminal = protocol.parse_event(
        {
            "schema_version": 1,
            "event": "done",
            "request_id": "turn-1",
            "chunk_count": 1,
            "natural_eos": True,
        }
    )
    state.accept(terminal)
    assert state.terminal is terminal

    with pytest.raises(protocol.QwenProtocolError):
        state.accept(terminal)
    with pytest.raises(protocol.QwenProtocolError):
        state.accept(first)


def test_qwen_invalidate_acknowledgement_contains_only_opaque_identity() -> None:
    protocol = _protocol_module()

    event = protocol.parse_event(
        {
            "schema_version": 1,
            "event": "invalidated",
            "request_id": "invalidate-1",
            "voice_key": "voice_0123456789abcdef",
        }
    )

    dumped = event.model_dump()
    assert dumped["voice_key"] == "voice_0123456789abcdef"
    assert "reference_audio" not in dumped
    assert "reference_transcript" not in dumped
    assert "model_path" not in dumped
