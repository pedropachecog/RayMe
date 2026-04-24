"""Voice sample upload validation and blob storage helpers."""

from __future__ import annotations

import hashlib
import io
import wave
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath

from app.storage.blob_store import atomic_write_blob

MAX_VOICE_SAMPLE_UPLOAD_BYTES = 25 * 1024 * 1024
MIN_RECOMMENDED_DURATION_SECONDS = 6.0
MAX_RECOMMENDED_DURATION_SECONDS = 15.0

SUPPORTED_AUDIO_TYPES = {
    ".wav": {"audio/wav", "audio/x-wav"},
    ".mp3": {"audio/mpeg"},
    ".flac": {"audio/flac", "audio/x-flac"},
}


class VoiceSampleValidationError(ValueError):
    """Raised when an uploaded voice sample is unsafe or unsupported."""


@dataclass(frozen=True, slots=True)
class ValidatedVoiceSample:
    content: bytes
    content_type: str
    extension: str
    byte_size: int
    sha256: str
    duration_seconds: float | None
    sample_rate_hz: int | None
    channel_count: int | None
    warnings: list[str]


def validate_voice_sample_upload(
    filename: str,
    content_type: str | None,
    content: bytes,
) -> ValidatedVoiceSample:
    """Validate untrusted voice sample bytes before storage."""

    extension = _extension_from_filename(filename)
    normalized_content_type = (content_type or "").lower()
    if normalized_content_type not in SUPPORTED_AUDIO_TYPES[extension]:
        raise VoiceSampleValidationError("Voice sample content type does not match extension")
    if not content:
        raise VoiceSampleValidationError("Voice sample cannot be empty")
    if len(content) > MAX_VOICE_SAMPLE_UPLOAD_BYTES:
        raise VoiceSampleValidationError("Voice sample is over 25 MiB")

    duration_seconds, sample_rate_hz, channel_count = _audio_metadata(extension, content)
    warnings = _duration_warnings(duration_seconds)
    return ValidatedVoiceSample(
        content=content,
        content_type=normalized_content_type,
        extension=extension,
        byte_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        duration_seconds=duration_seconds,
        sample_rate_hz=sample_rate_hz,
        channel_count=channel_count,
        warnings=warnings,
    )


def write_voice_sample_blob(
    blob_dir: Path,
    asset_id: str,
    sample: ValidatedVoiceSample,
) -> Path:
    """Store a validated sample under a server-generated blob name."""

    return atomic_write_blob(blob_dir, f"{asset_id}{sample.extension}", sample.content)


def _extension_from_filename(filename: str) -> str:
    _validate_client_filename(filename)
    extension = PurePath(filename).suffix.lower()
    if extension not in SUPPORTED_AUDIO_TYPES:
        raise VoiceSampleValidationError("Voice sample must be WAV, MP3, or FLAC audio")
    return extension


def _validate_client_filename(filename: str) -> None:
    if not filename or filename in {".", ".."}:
        raise VoiceSampleValidationError("Voice sample filename is invalid")
    if "\x00" in filename or "/" in filename or "\\" in filename:
        raise VoiceSampleValidationError("Voice sample filename must not contain path separators")
    if PurePath(filename).is_absolute() or PureWindowsPath(filename).is_absolute():
        raise VoiceSampleValidationError("Voice sample filename must not be a path")
    if PurePath(filename).name != filename:
        raise VoiceSampleValidationError("Voice sample filename must not contain path components")


def _audio_metadata(extension: str, content: bytes) -> tuple[float | None, int | None, int | None]:
    if extension != ".wav":
        return None, None, None

    try:
        with wave.open(io.BytesIO(content), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            channel_count = wav_file.getnchannels()
    except (EOFError, wave.Error):
        return None, None, None

    if frame_rate <= 0:
        return None, None, channel_count
    return frame_count / frame_rate, frame_rate, channel_count


def _duration_warnings(duration_seconds: float | None) -> list[str]:
    if duration_seconds is None:
        return []
    if duration_seconds < MIN_RECOMMENDED_DURATION_SECONDS:
        return ["too_short"]
    if duration_seconds > MAX_RECOMMENDED_DURATION_SECONDS:
        return ["longer_than_recommended"]
    return []


__all__ = [
    "MAX_VOICE_SAMPLE_UPLOAD_BYTES",
    "SUPPORTED_AUDIO_TYPES",
    "ValidatedVoiceSample",
    "VoiceSampleValidationError",
    "validate_voice_sample_upload",
    "write_voice_sample_blob",
]
