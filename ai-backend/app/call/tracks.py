from __future__ import annotations

import asyncio
import fractions
import os
import tempfile
from io import BytesIO
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import soundfile as sf
from aiortc import MediaStreamTrack


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


class QueuedAudioOutputTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, *, sample_rate: int = 48000, frame_ms: int = 20) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.frame_samples = max(int(sample_rate * frame_ms / 1000), 1)
        self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue()
        self._buffer = np.asarray([], dtype=np.int16)
        self._pts = 0

    async def recv(self) -> Any:
        from av import AudioFrame

        samples = await self._next_samples()
        frame = AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = self.sample_rate
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        self._pts += self.frame_samples
        return frame

    async def enqueue(self, wav_bytes: bytes) -> None:
        samples = _wav_bytes_to_int16(wav_bytes, target_sample_rate=self.sample_rate)
        if samples.size:
            await self._queue.put(samples)

    async def stop_current(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
        self._buffer = np.asarray([], dtype=np.int16)

    def stop(self) -> None:
        super().stop()
        self._queue.put_nowait(None)

    async def _next_samples(self) -> np.ndarray:
        while self._buffer.size < self.frame_samples and self.readyState != "ended":
            try:
                chunk = await asyncio.wait_for(
                    self._queue.get(), timeout=self.frame_samples / self.sample_rate
                )
            except asyncio.TimeoutError:
                break
            except asyncio.CancelledError:
                break
            if chunk is None:
                break
            self._buffer = np.concatenate([self._buffer, chunk])
            self._queue.task_done()

        if self._buffer.size >= self.frame_samples:
            samples = self._buffer[: self.frame_samples]
            self._buffer = self._buffer[self.frame_samples :]
            return samples

        samples = np.zeros(self.frame_samples, dtype=np.int16)
        if self._buffer.size:
            samples[: self._buffer.size] = self._buffer
            self._buffer = np.asarray([], dtype=np.int16)
        else:
            # Silence frame — add tiny jitter so Opus DTX does not suppress
            # the frame entirely. Without any packet flow during the
            # STT+LLM+TTS processing gap, ICE times out on the remote side
            # (especially Android Chrome) and the connection fails before
            # TTS audio arrives.
            samples[:] = np.random.randint(-4, 4, size=self.frame_samples, dtype=np.int16)
        return samples


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
        samples = _coerce_to_float32(array)
        if array.ndim > 1:
            layout = getattr(frame, "layout", None)
            format_ = getattr(frame, "format", None)
            channel_count = _frame_channel_count(layout, frame)
            is_planar = bool(getattr(format_, "is_planar", False))
            if is_planar and channel_count > 1 and array.shape[0] == channel_count:
                samples = samples.mean(axis=0)
            elif channel_count > 1:
                samples = samples.reshape(-1).reshape(-1, channel_count).mean(axis=1)
            elif array.shape[-1] <= 8 and array.shape[0] > array.shape[-1]:
                samples = samples.mean(axis=-1)
            else:
                samples = samples.reshape(-1)
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


def _wav_bytes_to_int16(wav_bytes: bytes, *, target_sample_rate: int) -> np.ndarray:
    samples, sample_rate = sf.read(BytesIO(wav_bytes), dtype="float32", always_2d=True)
    mono = np.asarray(samples, dtype=np.float32).mean(axis=1)
    if sample_rate != target_sample_rate:
        mono = _resample_linear(
            mono,
            source_rate=int(sample_rate),
            target_rate=target_sample_rate,
        )
    clipped = np.clip(mono, -1.0, 1.0)
    return (clipped * np.iinfo(np.int16).max).astype(np.int16)


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


def _frame_channel_count(layout: Any, frame: Any) -> int:
    channels = getattr(layout, "channels", None)
    if channels is not None:
        try:
            count = len(channels)
            if count > 0:
                return count
        except TypeError:
            pass
    count = int(getattr(frame, "channels", 1) or 1)
    return max(count, 1)


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
