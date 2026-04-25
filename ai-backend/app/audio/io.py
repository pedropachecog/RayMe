from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from io import BytesIO

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class AudioBuffer:
    samples: np.ndarray
    sample_rate: int


@dataclass(frozen=True)
class TemporaryAudioFile:
    path: str

    def cleanup(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            return None


def decode_audio_bytes(audio_bytes: bytes, *, target_sample_rate: int = 16000) -> AudioBuffer:
    if not audio_bytes:
        raise ValueError("audio input is empty")
    try:
        samples, sample_rate = sf.read(
            BytesIO(audio_bytes),
            dtype="float32",
            always_2d=True,
        )
    except Exception as exc:
        raise ValueError("audio input is invalid") from exc

    mono = samples.mean(axis=1)
    if sample_rate != target_sample_rate:
        mono = _resample_linear(mono, source_rate=sample_rate, target_rate=target_sample_rate)
        sample_rate = target_sample_rate

    return AudioBuffer(samples=np.asarray(mono, dtype=np.float32), sample_rate=sample_rate)


def uploaded_bytes_to_temp_wav(
    audio_bytes: bytes,
    *,
    original_filename: str | None = None,
    target_sample_rate: int = 16000,
) -> TemporaryAudioFile:
    del original_filename
    decoded = decode_audio_bytes(audio_bytes, target_sample_rate=target_sample_rate)
    with tempfile.NamedTemporaryFile(prefix="rayme-stt-", suffix=".wav", delete=False) as handle:
        sf.write(handle.name, decoded.samples, decoded.sample_rate, format="WAV")
        return TemporaryAudioFile(path=handle.name)


def _resample_linear(samples: np.ndarray, *, source_rate: int, target_rate: int) -> np.ndarray:
    if len(samples) == 0:
        return samples
    duration = len(samples) / source_rate
    target_length = max(int(round(duration * target_rate)), 1)
    source_positions = np.linspace(0.0, duration, num=len(samples), endpoint=False)
    target_positions = np.linspace(0.0, duration, num=target_length, endpoint=False)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)
