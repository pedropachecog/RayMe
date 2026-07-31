from __future__ import annotations

import base64
import binascii
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


SCHEMA_VERSION = 1
ENGINE_ID = "qwen3_1_7b"
SAMPLE_RATE = 24_000
MAX_REFERENCE_AUDIO_BYTES = 25 * 1024 * 1024
MAX_REFERENCE_AUDIO_B64_LENGTH = 36 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_CHUNK_B64_LENGTH = 12 * 1024 * 1024
MAX_REFERENCE_TRANSCRIPT_LENGTH = 20_000
MAX_TARGET_TEXT_LENGTH = 8_000
MAX_ERROR_CODE_LENGTH = 96
RELEASE_EVIDENCE_MODE = "phase09_release_evidence"
MAX_RELEASE_EVIDENCE_SEED = 4_294_967_295
REQUEST_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
VOICE_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class QwenProtocolError(ValueError):
    """The worker crossed a request or event-sequence trust boundary."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _CommandBase(_StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=REQUEST_ID_PATTERN,
    )


class QwenLoadCommand(_CommandBase):
    op: Literal["load"]


class QwenPrewarmCommand(_CommandBase):
    op: Literal["prewarm"]
    voice_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=VOICE_KEY_PATTERN,
    )
    reference_audio_b64: str = Field(
        min_length=1,
        max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
    )
    reference_transcript: str = Field(
        min_length=1,
        max_length=MAX_REFERENCE_TRANSCRIPT_LENGTH,
    )

    @field_validator("reference_audio_b64")
    @classmethod
    def validate_reference_audio_b64(cls, value: str) -> str:
        _decode_bounded_base64(
            value,
            max_bytes=MAX_REFERENCE_AUDIO_BYTES,
            label="reference audio",
        )
        return value

    @field_validator("reference_transcript")
    @classmethod
    def validate_reference_transcript(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reference transcript is required")
        return value

    def reference_audio_bytes(self) -> bytes:
        return _decode_bounded_base64(
            self.reference_audio_b64,
            max_bytes=MAX_REFERENCE_AUDIO_BYTES,
            label="reference audio",
        )


class QwenGenerateCommand(_CommandBase):
    op: Literal["generate"]
    voice_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=VOICE_KEY_PATTERN,
    )
    text: str = Field(min_length=1, max_length=MAX_TARGET_TEXT_LENGTH)
    max_new_tokens: int = Field(ge=4, le=384, multiple_of=4)
    hard_audio_seconds: float = Field(ge=0.1, le=32.0)
    release_evidence_mode: Literal["phase09_release_evidence"] | None = None
    release_evidence_seed: int | None = Field(
        default=None,
        ge=0,
        le=MAX_RELEASE_EVIDENCE_SEED,
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target text is required")
        return value

    @model_validator(mode="after")
    def require_paired_release_evidence_fields(self) -> "QwenGenerateCommand":
        if (self.release_evidence_mode is None) != (self.release_evidence_seed is None):
            raise ValueError("release evidence mode and seed must be provided together")
        return self


class QwenCancelCommand(_CommandBase):
    op: Literal["cancel"]


class QwenInvalidateCommand(_CommandBase):
    op: Literal["invalidate"]
    voice_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=VOICE_KEY_PATTERN,
    )


class QwenUnloadCommand(_CommandBase):
    op: Literal["unload"]


QwenWorkerCommand: TypeAlias = Annotated[
    QwenLoadCommand
    | QwenPrewarmCommand
    | QwenGenerateCommand
    | QwenCancelCommand
    | QwenInvalidateCommand
    | QwenUnloadCommand,
    Field(discriminator="op"),
]
_COMMAND_ADAPTER = TypeAdapter(QwenWorkerCommand)


class _EventBase(_StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=REQUEST_ID_PATTERN,
    )


class QwenLoadedEvent(_EventBase):
    event: Literal["loaded"]
    engine_id: Literal["qwen3_1_7b"] = ENGINE_ID
    runtime_version: Literal["0.3.2"]
    model_revision: Literal["fd4b254389122332181a7c3db7f27e918eec64e3"]
    device: Literal["cuda"]
    sample_rate: Literal[24000] = SAMPLE_RATE
    warmup_prefill: Literal[100]


class QwenPromptReadyEvent(_EventBase):
    event: Literal["prompt_ready"]
    voice_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=VOICE_KEY_PATTERN,
    )


class QwenPromptFailedEvent(_EventBase):
    event: Literal["prompt_failed"]
    voice_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=VOICE_KEY_PATTERN,
    )
    error_code: str = Field(
        min_length=1,
        max_length=MAX_ERROR_CODE_LENGTH,
        pattern=r"^[a-z0-9_]+$",
    )


class QwenInvalidatedEvent(_EventBase):
    event: Literal["invalidated"]
    voice_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=VOICE_KEY_PATTERN,
    )
    matched: bool


class QwenChunkEvent(_EventBase):
    event: Literal["chunk"]
    chunk_index: int = Field(ge=0, le=4095)
    wav_b64: str = Field(min_length=1, max_length=MAX_CHUNK_B64_LENGTH)
    sample_rate: Literal[24000] = SAMPLE_RATE
    duration_ms: float = Field(gt=0, le=2000)
    generated_at_ms: float = Field(ge=0, le=3_600_000)
    total_steps_so_far: int = Field(ge=1, le=384)

    @field_validator("wav_b64")
    @classmethod
    def validate_wav_b64(cls, value: str) -> str:
        _decode_bounded_base64(value, max_bytes=MAX_CHUNK_BYTES, label="audio chunk")
        return value

    def wav_bytes(self) -> bytes:
        return _decode_bounded_base64(
            self.wav_b64,
            max_bytes=MAX_CHUNK_BYTES,
            label="audio chunk",
        )


class QwenTerminalEvent(_EventBase):
    event: Literal["done", "cancelled", "error"]
    chunk_count: int = Field(ge=0, le=4096)
    natural_eos: bool = False
    error_code: str | None = Field(
        default=None,
        max_length=MAX_ERROR_CODE_LENGTH,
        pattern=r"^[a-z0-9_]+$",
    )

    @model_validator(mode="after")
    def validate_terminal_semantics(self) -> "QwenTerminalEvent":
        if self.event == "done":
            if not self.natural_eos or self.error_code is not None:
                raise ValueError("done terminal requires natural EOS and no error")
        elif self.event == "cancelled":
            if self.natural_eos or self.error_code is not None:
                raise ValueError("cancelled terminal cannot claim EOS or an error")
        elif self.natural_eos or not self.error_code:
            raise ValueError("error terminal requires an error code and no natural EOS")
        return self


QwenWorkerEvent: TypeAlias = Annotated[
    QwenLoadedEvent
    | QwenPromptReadyEvent
    | QwenPromptFailedEvent
    | QwenInvalidatedEvent
    | QwenChunkEvent
    | QwenTerminalEvent,
    Field(discriminator="event"),
]
_EVENT_ADAPTER = TypeAdapter(QwenWorkerEvent)


def parse_command(payload: object) -> QwenWorkerCommand:
    return _COMMAND_ADAPTER.validate_python(payload)


def parse_event(payload: object) -> QwenWorkerEvent:
    return _EVENT_ADAPTER.validate_python(payload)


class QwenStreamEventValidator:
    """Request-scoped state machine for chunk and terminal worker events."""

    def __init__(
        self,
        *,
        request_id: str,
        max_cumulative_duration_ms: float = 32_000.0,
    ) -> None:
        _CommandBase.model_validate(
            {"schema_version": SCHEMA_VERSION, "request_id": request_id}
        )
        self.request_id = request_id
        if max_cumulative_duration_ms <= 0 or max_cumulative_duration_ms > 32_000:
            raise ValueError("invalid cumulative audio ceiling")
        self.max_cumulative_duration_ms = max_cumulative_duration_ms
        self.next_chunk_index = 0
        self.last_generated_at_ms = -1.0
        self.last_total_steps = 0
        self.cumulative_duration_ms = 0.0
        self.terminal: QwenTerminalEvent | None = None

    def accept(self, event: QwenWorkerEvent) -> None:
        if self.terminal is not None:
            raise QwenProtocolError("worker event arrived after terminal")
        if event.request_id != self.request_id:
            raise QwenProtocolError("worker event request mismatch")
        if isinstance(event, QwenChunkEvent):
            if event.chunk_index != self.next_chunk_index:
                raise QwenProtocolError("worker chunk index is not monotonic")
            if event.generated_at_ms < self.last_generated_at_ms:
                raise QwenProtocolError("worker generated time is not monotonic")
            if event.total_steps_so_far <= self.last_total_steps:
                raise QwenProtocolError("worker generation steps are not monotonic")
            next_duration_ms = self.cumulative_duration_ms + event.duration_ms
            if next_duration_ms > self.max_cumulative_duration_ms:
                raise QwenProtocolError("worker audio exceeded request ceiling")
            self.next_chunk_index += 1
            self.last_generated_at_ms = event.generated_at_ms
            self.last_total_steps = event.total_steps_so_far
            self.cumulative_duration_ms = next_duration_ms
            return
        if not isinstance(event, QwenTerminalEvent):
            raise QwenProtocolError("non-stream worker event in stream")
        if event.chunk_count != self.next_chunk_index:
            raise QwenProtocolError("worker terminal chunk count mismatch")
        self.terminal = event


def _decode_bounded_base64(value: str, *, max_bytes: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not decoded:
        raise ValueError(f"empty {label}")
    if len(decoded) > max_bytes:
        raise ValueError(f"oversized {label}")
    return decoded
