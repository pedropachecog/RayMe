from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class PcmAudioFrame:
    pcm: bytes
    sample_rate: int = 16000
    channels: int = 1


@dataclass
class InboundAudioFrameNormalizer:
    target_sample_rate: int = 16000
    incoming_frames: int = 0

    def normalize(self, frame: Any) -> PcmAudioFrame:
        self.incoming_frames += 1
        return normalize_inbound_audio_frame(
            frame,
            target_sample_rate=self.target_sample_rate,
        )


@dataclass
class OutboundAudioBuffer:
    chunks: list[bytes] = field(default_factory=list)

    def append(self, chunk: bytes) -> None:
        if chunk:
            self.chunks.append(chunk)

    def drain(self) -> list[bytes]:
        chunks = list(self.chunks)
        self.chunks.clear()
        return chunks


@dataclass(frozen=True)
class TemporaryWavFile:
    path: str

    def cleanup(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            return None


def normalize_inbound_audio_frame(
    frame: Any,
    *,
    target_sample_rate: int = 16000,
) -> PcmAudioFrame:
    if isinstance(frame, bytes):
        return PcmAudioFrame(pcm=frame, sample_rate=target_sample_rate, channels=1)

    pcm = getattr(frame, "pcm", None)
    if isinstance(pcm, bytes):
        return PcmAudioFrame(
            pcm=pcm,
            sample_rate=int(getattr(frame, "sample_rate", target_sample_rate)),
            channels=int(getattr(frame, "channels", 1)),
        )

    to_ndarray = getattr(frame, "to_ndarray", None)
    if callable(to_ndarray):
        array = np.asarray(to_ndarray())
        if array.ndim > 1:
            array = array.mean(axis=0)
        samples = _coerce_to_float32(array)
        source_rate = int(getattr(frame, "sample_rate", target_sample_rate))
        if source_rate != target_sample_rate:
            samples = _resample_linear(
                samples,
                source_rate=source_rate,
                target_rate=target_sample_rate,
            )
        int16 = np.clip(samples, -1.0, 1.0)
        return PcmAudioFrame(
            pcm=(int16 * np.iinfo(np.int16).max).astype(np.int16).tobytes(),
            sample_rate=target_sample_rate,
            channels=1,
        )

    raise TypeError("unsupported inbound audio frame")


def write_pcm_frames_to_temp_wav(
    frames: list[PcmAudioFrame],
    *,
    target_sample_rate: int = 16000,
) -> TemporaryWavFile:
    samples = [_pcm_to_float32(frame, target_sample_rate=target_sample_rate) for frame in frames]
    combined = np.concatenate(samples) if samples else np.asarray([], dtype=np.float32)
    with tempfile.NamedTemporaryFile(prefix="rayme-call-stt-", suffix=".wav", delete=False) as handle:
        sf.write(handle.name, combined, target_sample_rate, format="WAV")
        return TemporaryWavFile(path=handle.name)


def _pcm_to_float32(frame: PcmAudioFrame, *, target_sample_rate: int) -> np.ndarray:
    if not frame.pcm:
        return np.asarray([], dtype=np.float32)
    samples = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32)
    samples = samples / float(np.iinfo(np.int16).max)
    if frame.channels > 1:
        samples = samples.reshape(-1, frame.channels).mean(axis=1)
    if frame.sample_rate != target_sample_rate:
        samples = _resample_linear(
            samples,
            source_rate=frame.sample_rate,
            target_rate=target_sample_rate,
        )
    return samples.astype(np.float32, copy=False)


def _coerce_to_float32(array: np.ndarray) -> np.ndarray:
    if np.issubdtype(array.dtype, np.integer):
        max_value = float(np.iinfo(array.dtype).max)
        return (array.astype(np.float32) / max_value).astype(np.float32, copy=False)
    return array.astype(np.float32, copy=False)


def _resample_linear(
    samples: np.ndarray,
    *,
    source_rate: int,
    target_rate: int,
) -> np.ndarray:
    if len(samples) == 0:
        return samples.astype(np.float32, copy=False)
    duration = len(samples) / source_rate
    target_length = max(int(round(duration * target_rate)), 1)
    source_positions = np.linspace(0.0, duration, num=len(samples), endpoint=False)
    target_positions = np.linspace(0.0, duration, num=target_length, endpoint=False)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)
