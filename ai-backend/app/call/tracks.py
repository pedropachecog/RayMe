from __future__ import annotations

import asyncio
import fractions
import logging
import os
import tempfile
import time
from io import BytesIO
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import soundfile as sf
from aiortc import MediaStreamTrack

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        *,
        sample_rate: int = 48000,
        frame_ms: int = 20,
        max_pending_audio_seconds: float = 1.5,
    ) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.frame_samples = max(int(sample_rate * frame_ms / 1000), 1)
        self.max_pending_samples = max(
            int(sample_rate * max(max_pending_audio_seconds, frame_ms / 1000)),
            self.frame_samples,
        )
        # Queue entry count is deliberately not the bound: native TTS chunks have
        # different durations. Admission credit below bounds the actual audio
        # debt held by both this queue and the internal frame buffer.
        self._queue: asyncio.Queue[tuple[int, np.ndarray] | None] = asyncio.Queue()
        self._buffer = np.asarray([], dtype=np.int16)
        self._pending_condition = asyncio.Condition()
        self._pending_samples = 0
        self._pending_samples_high_water = 0
        self._playout_epoch = 0
        self._next_sequence = 0
        self._last_consumed_sequence: int | None = None
        self._admission_block_count = 0
        self._admission_block_time_ms = 0.0
        self._underflow_frames = 0
        self._enqueued_chunks = 0
        self._played_samples = 0
        self._discarded_chunks = 0
        self._discarded_samples = 0
        self._join_count = 0
        self._order_violation_count = 0
        self._idle_wait_completed_count = 0
        self._idle_wait_timeout_count = 0
        self._playout_measurement_active = False
        self._pts = 0
        self._recv_count = 0
        self._idle_frame_count = 0
        self._next_frame_at: float | None = None
        self.last_enqueue_stats: dict[str, float | int] = {
            "duration_ms": 0,
            "samples": 0,
            "rms": 0.0,
            "peak": 0.0,
        }
        self._nonzero_send_logged = False

    @property
    def pending_samples(self) -> int:
        return self._pending_samples

    def reset_playout_metrics(self) -> None:
        """Start one turn's measurement without changing queued audio."""
        self._pending_samples_high_water = self._pending_samples
        self._admission_block_count = 0
        self._admission_block_time_ms = 0.0
        self._underflow_frames = 0
        self._enqueued_chunks = 0
        self._played_samples = 0
        self._discarded_chunks = 0
        self._discarded_samples = 0
        self._join_count = 0
        self._order_violation_count = 0
        self._idle_wait_completed_count = 0
        self._idle_wait_timeout_count = 0
        self._playout_measurement_active = False

    def playout_metrics(self) -> dict[str, float | int | bool]:
        pending_ms = self._samples_to_ms(self._pending_samples)
        high_water_ms = self._samples_to_ms(self._pending_samples_high_water)
        return {
            "admission_capacity_samples": self.max_pending_samples,
            "admission_capacity_ms": self._samples_to_ms(self.max_pending_samples),
            "pending_samples": self._pending_samples,
            "pending_audio_ms": pending_ms,
            "pending_samples_high_water": self._pending_samples_high_water,
            "pending_audio_high_water_ms": high_water_ms,
            "admission_block_count": self._admission_block_count,
            "admission_block_time_ms": round(self._admission_block_time_ms, 1),
            "underflow_frames": self._underflow_frames,
            "playout_debt_ms": pending_ms,
            "playout_debt_high_water_ms": high_water_ms,
            "enqueued_chunks": self._enqueued_chunks,
            "played_samples": self._played_samples,
            "discarded_chunks": self._discarded_chunks,
            "discarded_samples": self._discarded_samples,
            "join_count": self._join_count,
            "order_violation_count": self._order_violation_count,
            "idle_wait_completed_count": self._idle_wait_completed_count,
            "idle_wait_timeout_count": self._idle_wait_timeout_count,
        }

    async def recv(self) -> Any:
        from av import AudioFrame

        await self._pace_realtime()
        self._recv_count += 1
        samples = await self._next_samples()
        frame = AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = self.sample_rate
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        self._pts += self.frame_samples
        # Log periodically for diagnostics
        if self._recv_count % 50 == 0:
            logger.info(
                "[rayme-call] track.send.progress recv_count=%d idle_frames=%d "
                "queue_size=%d buffer_size=%d",
                self._recv_count,
                self._idle_frame_count,
                self._queue.qsize(),
                self._buffer.size,
            )
        return frame

    async def enqueue(self, wav_bytes: bytes, *, preroll_seconds: float = 0.0) -> float:
        samples = _wav_bytes_to_int16(wav_bytes, target_sample_rate=self.sample_rate)
        preroll_samples = int(self.sample_rate * max(preroll_seconds, 0.0))
        if preroll_samples > 0:
            samples = np.concatenate([np.zeros(preroll_samples, dtype=np.int16), samples])
        self.last_enqueue_stats = audio_stats_for_int16_samples(
            samples,
            sample_rate=self.sample_rate,
        )
        duration_seconds = float(self.last_enqueue_stats["duration_ms"]) / 1000.0
        logger.info(
            "[rayme-call] track.enqueue stats samples=%d duration_ms=%d "
            "preroll_ms=%d rms=%.1f peak=%.1f",
            self.last_enqueue_stats["samples"],
            self.last_enqueue_stats["duration_ms"],
            int(preroll_samples * 1000 / self.sample_rate) if self.sample_rate else 0,
            self.last_enqueue_stats["rms"],
            self.last_enqueue_stats["peak"],
        )
        if samples.size:
            await self._admit_samples(samples)
        return duration_seconds

    async def wait_until_idle(self, *, timeout: float | None = None) -> bool:
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + max(timeout, 0.0)
        async with self._pending_condition:
            while self.readyState != "ended" and self._pending_samples > 0:
                if deadline is None:
                    await self._pending_condition.wait()
                    continue
                remaining = deadline - loop.time()
                if remaining <= 0:
                    self._idle_wait_timeout_count += 1
                    logger.info(
                        "[rayme-call] track.wait_until_idle.timeout recv_count=%d "
                        "queue_size=%d buffer_size=%d pending_samples=%d",
                        self._recv_count,
                        self._queue.qsize(),
                        self._buffer.size,
                        self._pending_samples,
                    )
                    return False
                try:
                    await asyncio.wait_for(
                        self._pending_condition.wait(),
                        timeout=remaining,
                    )
                except asyncio.TimeoutError:
                    self._idle_wait_timeout_count += 1
                    return False
            completed = self.readyState != "ended" and self._pending_samples == 0
            if completed:
                self._idle_wait_completed_count += 1
                self._playout_measurement_active = False
            return completed

    async def stop_current(self) -> None:
        async with self._pending_condition:
            self._playout_epoch += 1
            discarded_entries = 0
            while not self._queue.empty():
                item = self._queue.get_nowait()
                self._queue.task_done()
                if item is not None:
                    discarded_entries += 1
            if self._buffer.size:
                discarded_entries += 1
            if self._pending_samples:
                self._discarded_samples += self._pending_samples
            self._discarded_chunks += discarded_entries
            self._pending_samples = 0
            self._buffer = np.asarray([], dtype=np.int16)
            self._last_consumed_sequence = None
            self._playout_measurement_active = False
            self._pending_condition.notify_all()

    def stop(self) -> None:
        self._discard_pending_now()
        super().stop()
        self._queue.put_nowait(None)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._notify_pending_waiters())

    async def _next_samples(self) -> np.ndarray:
        while self._buffer.size < self.frame_samples and self.readyState != "ended":
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            except asyncio.CancelledError:
                break
            if item is None:
                break
            sequence, chunk = item
            if (
                self._last_consumed_sequence is not None
                and sequence <= self._last_consumed_sequence
            ):
                self._order_violation_count += 1
            self._last_consumed_sequence = sequence
            self._buffer = np.concatenate([self._buffer, chunk])
            self._queue.task_done()

        consumed_samples = min(self._buffer.size, self.frame_samples)
        if consumed_samples >= self.frame_samples:
            samples = self._buffer[: self.frame_samples]
            self._buffer = self._buffer[self.frame_samples :]
            await self._release_pending_samples(consumed_samples)
            peak = float(np.max(np.abs(samples.astype(np.float32))))
            if not self._nonzero_send_logged and peak >= 128:
                self._nonzero_send_logged = True
                logger.info(
                    "[rayme-call] track.send.first_nonzero recv_count=%d rms=%.1f peak=%.1f",
                    self._recv_count,
                    float(np.sqrt(np.mean(np.square(samples.astype(np.float32))))),
                    peak,
                )
            return samples

        samples = np.zeros(self.frame_samples, dtype=np.int16)
        if consumed_samples:
            samples[:consumed_samples] = self._buffer[:consumed_samples]
            self._buffer = np.asarray([], dtype=np.int16)
            await self._release_pending_samples(consumed_samples)
            peak = float(np.max(np.abs(samples.astype(np.float32))))
            if not self._nonzero_send_logged and peak >= 128:
                self._nonzero_send_logged = True
                logger.info(
                    "[rayme-call] track.send.first_nonzero recv_count=%d rms=%.1f peak=%.1f",
                    self._recv_count,
                    float(np.sqrt(np.mean(np.square(samples.astype(np.float32))))),
                    peak,
                )
        if consumed_samples < self.frame_samples and self._playout_measurement_active:
            self._underflow_frames += 1
        if not consumed_samples:
            # Emit silence while no AI audio is queued so recv() continues to
            # produce RTP frames during STT/LLM/TTS gaps. The browser can keep
            # the remote media element audible without leaking a carrier tone.
            self._idle_frame_count += 1
        return samples

    async def _admit_samples(self, samples: np.ndarray) -> None:
        epoch = self._playout_epoch
        offset = 0
        self._enqueued_chunks += 1
        if self._pending_samples > 0:
            self._join_count += 1

        while offset < samples.size:
            blocked_at: float | None = None
            async with self._pending_condition:
                while (
                    epoch == self._playout_epoch
                    and self.readyState != "ended"
                    and self._pending_samples >= self.max_pending_samples
                ):
                    if blocked_at is None:
                        blocked_at = time.perf_counter()
                        self._admission_block_count += 1
                    await self._pending_condition.wait()
                if blocked_at is not None:
                    self._admission_block_time_ms += (
                        time.perf_counter() - blocked_at
                    ) * 1000
                if epoch != self._playout_epoch or self.readyState == "ended":
                    self._discarded_samples += int(samples.size - offset)
                    self._discarded_chunks += 1
                    return

                available = self.max_pending_samples - self._pending_samples
                admitted = min(available, int(samples.size - offset))
                if admitted <= 0:
                    continue
                sequence = self._next_sequence
                self._next_sequence += 1
                chunk = np.asarray(samples[offset : offset + admitted], dtype=np.int16).copy()
                self._queue.put_nowait((sequence, chunk))
                offset += admitted
                self._pending_samples += admitted
                self._playout_measurement_active = True
                self._pending_samples_high_water = max(
                    self._pending_samples_high_water,
                    self._pending_samples,
                )

    async def _release_pending_samples(self, sample_count: int) -> None:
        async with self._pending_condition:
            released = min(max(int(sample_count), 0), self._pending_samples)
            self._pending_samples -= released
            self._played_samples += released
            self._pending_condition.notify_all()

    def _discard_pending_now(self) -> None:
        self._playout_epoch += 1
        discarded_entries = 0
        while not self._queue.empty():
            item = self._queue.get_nowait()
            self._queue.task_done()
            if item is not None:
                discarded_entries += 1
        if self._buffer.size:
            discarded_entries += 1
        self._discarded_samples += self._pending_samples
        self._discarded_chunks += discarded_entries
        self._pending_samples = 0
        self._buffer = np.asarray([], dtype=np.int16)
        self._last_consumed_sequence = None
        self._playout_measurement_active = False

    async def _notify_pending_waiters(self) -> None:
        async with self._pending_condition:
            self._pending_condition.notify_all()

    def _samples_to_ms(self, sample_count: int) -> float:
        return round(float(sample_count) * 1000.0 / max(self.sample_rate, 1), 1)

    async def _pace_realtime(self) -> None:
        frame_duration = self.frame_samples / max(self.sample_rate, 1)
        now = time.monotonic()
        if self._next_frame_at is None:
            self._next_frame_at = now

        wait_seconds = self._next_frame_at - now
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
            now = time.monotonic()

        if self._next_frame_at < now - frame_duration:
            self._next_frame_at = now + frame_duration
        else:
            self._next_frame_at += frame_duration


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


def audio_stats_for_wav_bytes(
    wav_bytes: bytes,
    *,
    target_sample_rate: int,
) -> dict[str, float | int]:
    return audio_stats_for_int16_samples(
        _wav_bytes_to_int16(wav_bytes, target_sample_rate=target_sample_rate),
        sample_rate=target_sample_rate,
    )


def audio_stats_for_int16_samples(
    samples: np.ndarray,
    *,
    sample_rate: int,
) -> dict[str, float | int]:
    float_samples = samples.astype(np.float32)
    return {
        "duration_ms": int(samples.size * 1000 / sample_rate) if samples.size else 0,
        "samples": int(samples.size),
        "rms": float(np.sqrt(np.mean(np.square(float_samples)))) if samples.size else 0.0,
        "peak": float(np.max(np.abs(float_samples))) if samples.size else 0.0,
    }


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
