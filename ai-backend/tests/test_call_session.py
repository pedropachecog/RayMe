from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

import app.call.tracks as tracks_module
import app.call.session as session_module
from app.config import AiBackendSettings
from app.call.tracks import PcmAudioFrame, QueuedAudioOutputTrack, normalize_inbound_audio_frame
from app.call.session import (
    CALL_TTS_AUDIO_PREROLL_SECONDS,
    CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS,
    CallSession,
    CallSessionManager,
    PeerSwitchInProgressError,
    PeerOfferConfiguration,
    SpeechSegmentConflictError,
    SpeechSessionSelectionError,
    SpeechTurnTerminalError,
)
from app.models.tts_registry import TtsAudioChunk


def _scripted_wav_bytes(*, sample_count: int = 2880) -> bytes:
    buffer = BytesIO()
    samples = np.full(sample_count, 512 / np.iinfo(np.int16).max, dtype=np.float32)
    sf.write(buffer, samples, 24000, format="WAV")
    return buffer.getvalue()


SCRIPTED_WAV_BYTES = _scripted_wav_bytes()
QWEN_STREAM_CHUNK_WAV_BYTES = _scripted_wav_bytes(sample_count=7680)
LONG_QWEN_STREAM_CHUNK_WAV_BYTES = _scripted_wav_bytes(sample_count=96_000)


def _run(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return asyncio.run(value)
    return value


class ScriptedPeerConnection:
    def __init__(self) -> None:
        self.close_calls = 0
        self.connectionState = "new"

    async def close(self) -> None:
        self.close_calls += 1


class ScriptedAiTurn:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


class ScriptedDataChannel:
    def __init__(self, *, ready_state: str = "open") -> None:
        self.readyState = ready_state
        self.sent: list[str] = []

    def send(self, message: str) -> None:
        self.sent.append(message)


class ScriptedOutboundAudioTrack:
    def __init__(self, *, playout_wait_completed: bool = True) -> None:
        self.chunks: list[bytes] = []
        self.preroll_seconds: list[float] = []
        self.stop_calls = 0
        self.wait_calls: list[float | None] = []
        self.playout_wait_completed = playout_wait_completed

    async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
        self.chunks.append(chunk)
        self.preroll_seconds.append(preroll_seconds)
        self.last_enqueue_stats = {
            "duration_ms": int(120 + preroll_seconds * 1000),
            "samples": int(5760 + preroll_seconds * 48000),
            "rms": 512.0,
            "peak": 2048.0,
        }
        return float(self.last_enqueue_stats["duration_ms"]) / 1000.0

    async def stop_current(self) -> None:
        self.stop_calls += 1

    async def wait_until_idle(self, *, timeout: float | None = None) -> bool:
        self.wait_calls.append(timeout)
        return self.playout_wait_completed


class ObservableStreamingOutboundAudioTrack(ScriptedOutboundAudioTrack):
    def __init__(self) -> None:
        super().__init__()
        self.first_chunk_enqueued = asyncio.Event()

    async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
        result = await super().enqueue(chunk, preroll_seconds=preroll_seconds)
        if len(self.chunks) == 1:
            self.first_chunk_enqueued.set()
        return result


class BlockedIdleOutboundAudioTrack(ScriptedOutboundAudioTrack):
    def __init__(self) -> None:
        super().__init__()
        self.wait_started = asyncio.Event()
        self.release_idle = asyncio.Event()
        self.input_complete_calls = 0

    def mark_playout_input_complete(self) -> None:
        self.input_complete_calls += 1

    async def wait_until_idle(self, *, timeout: float | None = None) -> bool:
        self.wait_calls.append(timeout)
        self.wait_started.set()
        await self.release_idle.wait()
        return True


class ScriptedTtsAdapter:
    def __init__(self, *, delay: float = 0) -> None:
        self.delay = delay
        self.calls: list[dict[str, Any]] = []

    async def synthesize_call_text(
        self,
        *,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "turn_id": turn_id,
                "text": text,
                "voice_id": voice_id,
                "engine_id": engine_id,
            }
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        return {"wav_bytes": SCRIPTED_WAV_BYTES, "sample_rate": 24000, "duration_ms": 120}


class ScriptedGenericTtsAdapter:
    def __init__(self) -> None:
        self.reference_audio: bytes | None = None
        self.payload: Any | None = None

    def synthesize(self, payload: Any) -> dict[str, Any]:
        self.payload = payload
        self.reference_audio = payload.reference_audio
        return {"wav_bytes": SCRIPTED_WAV_BYTES, "sample_rate": 24000, "duration_ms": 120}


class ScriptedStreamingTtsAdapter:
    engine_id = "voxcpm2"

    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.first_chunk_yielded = threading.Event()
        self.release_second_chunk = threading.Event()
        self.stream_completed = threading.Event()

    def synthesize(self, payload: Any) -> dict[str, Any]:
        raise AssertionError("whole synthesis fallback was used")

    def stream(self, request: Any) -> Any:
        self.requests.append(request)
        self.first_chunk_yielded.set()
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=0,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=120,
            generated_at_ms=25.0,
        )
        self.release_second_chunk.wait()
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=1,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=120,
            generated_at_ms=75.0,
        )
        self.stream_completed.set()


class SlowStreamingTtsAdapter:
    engine_id = "voxcpm2"

    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.first_chunk_yielded = threading.Event()
        self.second_chunk_yielded = threading.Event()
        self.release_completion = threading.Event()
        self.stream_completed = threading.Event()

    def synthesize(self, payload: Any) -> dict[str, Any]:
        raise AssertionError("whole synthesis fallback was used")

    def stream(self, request: Any) -> Any:
        self.requests.append(request)
        self.first_chunk_yielded.set()
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=0,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=120,
            generated_at_ms=25.0,
        )
        self.second_chunk_yielded.set()
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=1,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=120,
            generated_at_ms=300.0,
        )
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=2,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=120,
            generated_at_ms=360.0,
        )
        self.release_completion.wait()
        self.stream_completed.set()


class SlowQwenStreamingTtsAdapter:
    engine_id = "qwen3_1_7b"

    def __init__(
        self,
        *,
        chunk_count: int = 3,
        wav_bytes: bytes = SCRIPTED_WAV_BYTES,
        duration_ms: float = 120.0,
    ) -> None:
        self.chunk_count = chunk_count
        self.wav_bytes = wav_bytes
        self.duration_ms = duration_ms
        self.requests: list[dict[str, Any]] = []
        self.second_chunk_yielded = threading.Event()
        self.release_completion = threading.Event()
        self.stream_completed = threading.Event()
        self.cancel_calls: list[str] = []

    def synthesize(self, _payload: Any) -> dict[str, Any]:
        raise AssertionError("whole synthesis fallback was used")

    def stream(
        self,
        request: Any,
        *,
        request_id: str,
        voice_key: str,
    ) -> Any:
        self.requests.append(
            {
                "request": request,
                "request_id": request_id,
                "voice_key": voice_key,
            }
        )
        for index in range(self.chunk_count):
            yield TtsAudioChunk(
                engine_id=self.engine_id,
                chunk_index=index,
                wav_bytes=self.wav_bytes,
                sample_rate=24000,
                duration_ms=self.duration_ms,
                generated_at_ms=25.0 + index * 60.0,
            )
            if index == 1:
                self.second_chunk_yielded.set()
        self.release_completion.wait()
        self.stream_completed.set()

    def cancel(self, request_id: str) -> bool:
        self.cancel_calls.append(request_id)
        self.release_completion.set()
        return True


class BackpressureQwenStreamingTtsAdapter(SlowQwenStreamingTtsAdapter):
    def __init__(self) -> None:
        super().__init__(chunk_count=6)
        self.yield_attempts = 0
        self.completed_yields = 0
        self.fourth_yield_attempted = threading.Event()

    def stream(
        self,
        request: Any,
        *,
        request_id: str,
        voice_key: str,
    ) -> Any:
        self.requests.append(
            {
                "request": request,
                "request_id": request_id,
                "voice_key": voice_key,
            }
        )
        for index in range(self.chunk_count):
            self.yield_attempts += 1
            if self.yield_attempts == 4:
                self.fourth_yield_attempted.set()
            yield TtsAudioChunk(
                engine_id=self.engine_id,
                chunk_index=index,
                wav_bytes=SCRIPTED_WAV_BYTES,
                sample_rate=24000,
                duration_ms=120,
                generated_at_ms=25.0 + index * 60.0,
            )
            self.completed_yields += 1
        self.stream_completed.set()


class CancellableQwenStreamingTtsAdapter:
    engine_id = "qwen3_1_7b"

    def __init__(self, *, yield_before_cancel: bool) -> None:
        self.yield_before_cancel = yield_before_cancel
        self.stream_started = threading.Event()
        self.release_stream = threading.Event()
        self.cancel_calls: list[str] = []
        self.synthesize_calls = 0

    def synthesize(self, _payload: Any) -> dict[str, Any]:
        self.synthesize_calls += 1
        raise AssertionError("whole synthesis fallback was used")

    def stream(
        self,
        request: Any,
        *,
        request_id: str,
        voice_key: str,
    ) -> Any:
        assert request.request_id == request_id
        assert request.voice_key == voice_key
        self.stream_started.set()
        if self.yield_before_cancel:
            yield TtsAudioChunk(
                engine_id=self.engine_id,
                chunk_index=0,
                wav_bytes=SCRIPTED_WAV_BYTES,
                sample_rate=24000,
                duration_ms=120,
                generated_at_ms=25.0,
            )
        self.release_stream.wait()

    def cancel(self, request_id: str) -> bool:
        self.cancel_calls.append(request_id)
        self.release_stream.set()
        return True


class BlockingFirstEnqueueTrack(ObservableStreamingOutboundAudioTrack):
    def __init__(self) -> None:
        super().__init__()
        self.first_enqueue_entered = asyncio.Event()
        self.release_first_enqueue = asyncio.Event()

    async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
        if not self.chunks:
            self.first_enqueue_entered.set()
            await self.release_first_enqueue.wait()
        return await super().enqueue(chunk, preroll_seconds=preroll_seconds)


class ScriptedInboundAudioFrame:
    def __init__(self, pcm: bytes) -> None:
        self.pcm = pcm
        self.sample_rate = 16000
        self.channels = 1


class ScriptedInboundAudioFrameSource:
    def __init__(self, *frames: bytes) -> None:
        self.frames = [ScriptedInboundAudioFrame(frame) for frame in frames]


class ScriptedAvAudioFrame:
    def __init__(self, samples: np.ndarray, *, sample_rate: int = 16000) -> None:
        self._samples = samples
        self.sample_rate = sample_rate

    def to_ndarray(self) -> np.ndarray:
        return self._samples


class ScriptedVadAdapter:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def accept_audio_frame(self, pcm: bytes) -> dict[str, bool]:
        self.frames.append(pcm)
        return {
            "speech_detected": True,
            "end_of_turn": len(self.frames) >= 2,
        }


class NeverEndingVadAdapter:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def accept_audio_frame(self, pcm: bytes) -> dict[str, bool]:
        self.frames.append(pcm)
        return {
            "speech_detected": True,
            "end_of_turn": False,
        }


class ScriptedSttAdapter:
    def __init__(self) -> None:
        self.calls: list[list[bytes]] = []

    def transcribe_pcm(self, pcm_frames: list[bytes], **_: Any) -> dict[str, Any]:
        self.calls.append(list(pcm_frames))
        return {
            "status": "accepted",
            "transcript": "hello from mic",
            "language": "en",
        }


class ScriptedManualFallbackSttAdapter:
    def __init__(self) -> None:
        self.calls: list[list[bytes]] = []

    def transcribe_pcm(self, pcm_frames: list[bytes], **_: Any) -> dict[str, Any]:
        self.calls.append(list(pcm_frames))
        return {
            "status": "needs_manual_transcript",
            "transcript": "",
            "language": "en",
            "speech_detected": True,
            "retry_allowed": True,
            "manual_transcript_allowed": True,
        }


def _new_session(
    *,
    session_id: str = "call-session-1",
    vad_adapter: Any | None = None,
    stt_adapter: Any | None = None,
    tts_adapter: Any | None = None,
    outbound_audio_track: Any | None = None,
    data_channel: Any | None = None,
    event_sink: Any | None = None,
    settings: AiBackendSettings | None = None,
) -> tuple[Any, ScriptedPeerConnection]:
    peer = ScriptedPeerConnection()
    session = CallSession(
        session_id=session_id,
        peer_connection=peer,
        vad_adapter=vad_adapter,
        stt_adapter=stt_adapter,
        tts_adapter=tts_adapter,
        outbound_audio_track=outbound_audio_track,
        data_channel=data_channel,
        event_sink=event_sink,
        settings=settings,
    )
    return session, peer


async def _wait_for_async_event_or_task(
    event: asyncio.Event,
    task: asyncio.Task[Any],
    *,
    label: str,
) -> None:
    event_task = asyncio.create_task(event.wait())
    done, pending = await asyncio.wait(
        {event_task, task},
        timeout=1.0,
        return_when=asyncio.FIRST_COMPLETED,
    )
    if event_task in done:
        return
    event_task.cancel()
    if pending and event_task in pending:
        try:
            await event_task
        except asyncio.CancelledError:
            pass
    if task in done:
        await task
    pytest.fail(f"Timed out waiting for {label}")


def test_create_session_returns_stable_session_id() -> None:
    manager = CallSessionManager()

    session = _run(manager.create_session(session_id="call-session-1"))

    assert session.session_id == "call-session-1"
    assert manager.get_session("call-session-1") is session
    assert session.stats()["session_id"] == "call-session-1"


def test_existing_session_reoffer_replaces_peer_connection_and_track() -> None:
    manager = CallSessionManager()
    first_peer = ScriptedPeerConnection()
    second_peer = ScriptedPeerConnection()
    first_track = ScriptedOutboundAudioTrack()
    second_track = ScriptedOutboundAudioTrack()

    session = _run(
        manager.create_session(
            session_id="call-session-reconnect",
            peer_connection=first_peer,
            outbound_audio_track=first_track,
        )
    )
    same_session = _run(
        manager.create_session(
            session_id="call-session-reconnect",
            peer_connection=second_peer,
            outbound_audio_track=second_track,
        )
    )

    assert same_session is session
    assert session.peer_connection is second_peer
    assert session.outbound_audio_track is second_track
    assert first_peer.close_calls == 1


def test_existing_session_reoffer_recovers_connection_failed_session() -> None:
    manager = CallSessionManager()
    first_peer = ScriptedPeerConnection()
    second_peer = ScriptedPeerConnection()

    session = _run(
        manager.create_session(
            session_id="call-session-reconnect-failed",
            peer_connection=first_peer,
        )
    )
    first_peer.connectionState = "failed"
    _run(session.handle_connection_state_change())

    same_session = _run(
        manager.create_session(
            session_id="call-session-reconnect-failed",
            peer_connection=second_peer,
        )
    )

    assert same_session is session
    assert session.peer_connection is second_peer
    assert session.state == "listening"
    assert session.end_reason is None
    assert session.ended_at is None


def test_existing_session_reoffer_marks_in_progress_turn_for_reconnect_grace() -> None:
    manager = CallSessionManager()
    first_peer = ScriptedPeerConnection()
    second_peer = ScriptedPeerConnection()
    session = _run(
        manager.create_session(
            session_id="call-session-reconnect-in-progress",
            peer_connection=first_peer,
        )
    )
    session._turn_frames.append(
        PcmAudioFrame(
            pcm=np.full(320, 2000, dtype=np.int16).tobytes(),
            sample_rate=16000,
            channels=1,
        )
    )
    session._speech_seen = True

    same_session = _run(
        manager.create_session(
            session_id="call-session-reconnect-in-progress",
            peer_connection=second_peer,
        )
    )

    assert same_session is session
    assert session._media_reconnect_grace_pending is True


def test_existing_failed_session_reoffer_marks_in_progress_turn_for_reconnect_grace() -> None:
    manager = CallSessionManager()
    first_peer = ScriptedPeerConnection()
    second_peer = ScriptedPeerConnection()
    session = _run(
        manager.create_session(
            session_id="call-session-reconnect-failed-in-progress",
            peer_connection=first_peer,
        )
    )
    session._turn_frames.append(
        PcmAudioFrame(
            pcm=np.full(320, 2000, dtype=np.int16).tobytes(),
            sample_rate=16000,
            channels=1,
        )
    )
    session._speech_seen = True
    first_peer.connectionState = "failed"
    _run(session.handle_connection_state_change())

    same_session = _run(
        manager.create_session(
            session_id="call-session-reconnect-failed-in-progress",
            peer_connection=second_peer,
        )
    )

    assert same_session is session
    assert session.state == "listening"
    assert session.end_reason is None
    assert session.ended_at is None
    assert session._media_reconnect_grace_pending is True


def test_mute_stops_server_consumption() -> None:
    session, _ = _new_session()

    _run(session.set_muted(True))
    accepted = _run(session.handle_inbound_audio_frame(b"pcm-frame-1"))

    assert session.muted is True
    assert accepted is False
    assert session.stats()["incoming_audio_frames"] == 1
    assert session.stats()["dropped_audio_frames"] == 1
    assert session.stats()["muted"] is True


def test_muted_raw_bytes_drop_returns_false_without_vad_or_stt() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    _run(session.set_muted(True))
    accepted = _run(session.handle_inbound_audio_frame(b"raw-muted-pcm"))

    assert accepted is False
    assert vad.frames == []
    assert stt.calls == []
    assert session.stats()["incoming_audio_frames"] == 1
    assert session.stats()["dropped_audio_frames"] == 1


def test_inbound_audio_emits_user_final_after_vad_end() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    source = ScriptedInboundAudioFrameSource(b"pcm-frame-1", b"pcm-frame-2")
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    first_event = _run(session.handle_inbound_audio_frame(source.frames[0]))
    final_event = _run(session.handle_inbound_audio_frame(source.frames[1]))

    assert first_event is None
    assert stt.calls == [[b"pcm-frame-1", b"pcm-frame-2"]]
    assert final_event == {
        "type": "user_final",
        "session_id": "call-session-1",
        "turn_id": "user-turn-1",
        "text": "hello from mic",
    }
    assert session.stats()["incoming_audio_frames"] == 2
    assert session.stats()["dropped_audio_frames"] == 0


def test_user_final_is_recoverable_when_data_channel_is_closed() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    channel = ScriptedDataChannel(ready_state="closed")
    source = ScriptedInboundAudioFrameSource(b"pcm-frame-1", b"pcm-frame-2")
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt, data_channel=channel)

    _run(session.handle_inbound_audio_frame(source.frames[0]))
    final_event = _run(session.handle_inbound_audio_frame(source.frames[1]))

    assert final_event["type"] == "user_final"
    assert channel.sent == []
    drained = session.drain_undelivered_events()
    assert len(drained) == 1
    assert drained[0]["type"] == "user_final"
    assert drained[0]["session_id"] == "call-session-1"
    assert drained[0]["turn_id"] == "user-turn-1"
    assert drained[0]["text"] == "hello from mic"
    assert drained[0]["started_at"]
    assert drained[0]["ended_at"]
    assert session.drain_undelivered_events() == []


def test_near_silent_finalized_turn_does_not_reach_stt() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    silent_pcm = np.zeros(320, dtype=np.int16).tobytes()
    source = ScriptedInboundAudioFrameSource(silent_pcm, silent_pcm)
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    first_event = _run(session.handle_inbound_audio_frame(source.frames[0]))
    second_event = _run(session.handle_inbound_audio_frame(source.frames[1]))

    assert first_event is None
    assert second_event is None
    assert stt.calls == []
    assert session.state == "listening"


def test_inbound_audio_emits_failed_event_when_stt_needs_manual_transcript() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedManualFallbackSttAdapter()
    source = ScriptedInboundAudioFrameSource(b"pcm-frame-1", b"pcm-frame-2")
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    first_event = _run(session.handle_inbound_audio_frame(source.frames[0]))
    failed_event = _run(session.handle_inbound_audio_frame(source.frames[1]))

    assert first_event is None
    assert stt.calls == [[b"pcm-frame-1", b"pcm-frame-2"]]
    assert failed_event == {
        "type": "failed",
        "session_id": "call-session-1",
        "turn_id": "user-turn-1",
        "code": "call_stt_failed",
        "message": "Speech transcription failed. Please try speaking again.",
        "retry_allowed": True,
    }


class ScriptedSileroVadAdapter:
    """Mimics SileroVadAdapter: exposes speech_timestamps + sampling_rate."""

    def __init__(
        self,
        *,
        sampling_rate: int = 16000,
        speech_end_sample: int | None = None,
        threshold: float = 0.5,
    ) -> None:
        self.sampling_rate = sampling_rate
        self.speech_end_sample = speech_end_sample
        self.threshold = threshold
        self.calls: list[int] = []

    def speech_timestamps(self, audio: Any) -> list[dict[str, int]]:
        total_samples = int(len(audio))
        self.calls.append(total_samples)
        if total_samples == 0:
            return []
        end = self.speech_end_sample if self.speech_end_sample is not None else total_samples
        return [{"start": 0, "end": min(end, total_samples)}]


class FlakySileroVadAdapter:
    """Mimics a brief Silero false-negative gap during continuous speech."""

    def __init__(
        self,
        *,
        false_silence_calls: set[int],
        sampling_rate: int = 16000,
        threshold: float = 0.5,
    ) -> None:
        self.false_silence_calls = false_silence_calls
        self.sampling_rate = sampling_rate
        self.threshold = threshold
        self.calls = 0

    def speech_timestamps(self, audio: Any) -> list[dict[str, int]]:
        self.calls += 1
        if self.calls in self.false_silence_calls:
            return []
        total_samples = int(len(audio))
        return [{"start": 0, "end": total_samples}]


def test_silero_silence_gap_finalizes_turn_even_with_loud_ambient_noise() -> None:
    """Regression: with browser AGC, raw RMS energy stays high every frame.
    Silero must drive end_of_turn from the gap between last speech and buffer end,
    not from a raw energy comparator."""
    sampling_rate = 16000
    frame_samples = 320  # 20 ms at 16 kHz
    loud_pcm = (np.full(frame_samples, 8000, dtype=np.int16)).tobytes()

    speech_frames_count = 5
    speech_end_sample = frame_samples * speech_frames_count
    vad = ScriptedSileroVadAdapter(
        sampling_rate=sampling_rate,
        speech_end_sample=speech_end_sample,
    )
    stt = ScriptedSttAdapter()
    settings = AiBackendSettings(call_vad_end_silence_ms=700)
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt, settings=settings)

    end_silence_ms = int(session.settings.call_vad_end_silence_ms)
    silence_frames_needed = (end_silence_ms // 20) + 1
    total_frames = speech_frames_count + silence_frames_needed

    final_event: dict[str, Any] | None = None
    for _ in range(total_frames):
        frame = ScriptedInboundAudioFrame(loud_pcm)
        result = _run(session.handle_inbound_audio_frame(frame))
        if isinstance(result, dict) and result.get("type") == "user_final":
            final_event = result
            break

    assert final_event is not None, (
        "Silero silence gap must finalize the turn; without this fix the "
        "energy fallback resets _silence_ms every frame so end_of_turn never fires"
    )
    assert final_event["type"] == "user_final"
    assert stt.calls, "STT must run after VAD end_of_turn"


def test_call_vad_tolerates_short_false_silero_silence_during_continuous_speech() -> None:
    frame_samples = 320  # 20 ms at 16 kHz
    speech_pcm = np.full(frame_samples, 2000, dtype=np.int16).tobytes()
    vad = FlakySileroVadAdapter(false_silence_calls=set(range(11, 46)))
    stt = ScriptedSttAdapter()
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    for _ in range(55):
        result = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))
        assert not (isinstance(result, dict) and result.get("type") == "user_final")

    assert stt.calls == []
    assert session.state == "listening"
    assert session._speech_seen is True
    assert session._silence_ms == 0


def test_call_vad_reconnect_grace_preserves_turn_until_speech_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    monkeypatch.setattr(session_module.time, "monotonic", lambda: now)

    frame_samples = 320  # 20 ms at 16 kHz
    speech_pcm = np.full(frame_samples, 2000, dtype=np.int16).tobytes()
    vad = FlakySileroVadAdapter(false_silence_calls=set(range(2, 42)))
    stt = ScriptedSttAdapter()
    settings = AiBackendSettings(
        call_vad_end_silence_ms=700,
        call_media_reconnect_grace_ms=5000,
    )
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt, settings=settings)

    first = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))
    assert first is None
    session.mark_media_reconnect_pending()
    session.start_media_reconnect_grace_if_pending()

    for _ in range(40):  # 800 ms: past the 700 ms silence threshold.
        result = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))
        assert not (isinstance(result, dict) and result.get("type") == "user_final")

    resumed = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))

    assert resumed is None
    assert stt.calls == []
    assert session.state == "listening"
    assert session._speech_seen is True
    assert session._silence_ms == 0


def test_reconnect_audio_backfill_is_inserted_before_replacement_track_frames() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    pre_pcm = np.full(320, 1000, dtype=np.int16).tobytes()
    gap_samples = np.concatenate(
        [
            np.full(320, 2000, dtype=np.int16),
            np.full(320, 3000, dtype=np.int16),
        ]
    )
    gap_pcm = gap_samples.tobytes()
    post_pcm = np.full(320, 4000, dtype=np.int16).tobytes()

    first = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(pre_pcm)))
    session.mark_media_reconnect_pending()
    backfill = _run(
        session.backfill_reconnect_audio(
            pcm=gap_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="gap-1",
            reason="failed",
            attempt=1,
            final=False,
        )
    )
    final = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(post_pcm)))

    assert first is None
    assert backfill["status"] == "accepted"
    assert backfill["frames"] == 2
    assert final["type"] == "user_final"
    assert stt.calls == [[
        pre_pcm,
        gap_samples[:320].tobytes(),
        gap_samples[320:].tobytes(),
        post_pcm,
    ]]


def test_final_reconnect_backfill_can_finalize_turn_without_replacement_frame() -> None:
    events: list[dict[str, Any]] = []
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    session, _ = _new_session(
        vad_adapter=vad,
        stt_adapter=stt,
        event_sink=events.append,
    )

    pre_pcm = np.full(320, 1000, dtype=np.int16).tobytes()
    gap_pcm = np.full(320, 2000, dtype=np.int16).tobytes()

    first = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(pre_pcm)))
    session.mark_media_reconnect_pending()
    backfill = _run(
        session.backfill_reconnect_audio(
            pcm=gap_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="gap-final",
            reason="failed",
            attempt=1,
            final=True,
        )
    )

    assert first is None
    assert backfill["status"] == "accepted"
    assert backfill["event"]["type"] == "user_final"
    assert backfill["event"]["text"] == "hello from mic"
    assert [event["type"] for event in events] == ["state", "user_final"]
    assert stt.calls == [[pre_pcm, gap_pcm]]
    assert session.state == "thinking"


def test_slow_reconnect_stt_defers_transport_terminal_and_returns_usable_user_final() -> None:
    import threading

    entered_stt = threading.Event()
    release_stt = threading.Event()

    class SlowSttAdapter:
        def transcribe(self, **_kwargs: Any) -> dict[str, Any]:
            entered_stt.set()
            assert release_stt.wait(timeout=2.0)
            return {
                "status": "accepted",
                "transcript": "recovered after slow transcription",
                "language": "en",
            }

    async def scenario() -> None:
        session, _ = _new_session(
            vad_adapter=ScriptedVadAdapter(),
            stt_adapter=SlowSttAdapter(),
        )
        session.voice_id = "voice-1"
        session.engine_id = "f5"
        peer = ScriptedPeerConnection()
        session.peer_connection = peer
        pre_pcm = np.full(320, 1000, dtype=np.int16).tobytes()
        gap_pcm = np.full(320, 2000, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pre_pcm)
        ) is None

        backfill_task = asyncio.create_task(
            session.backfill_reconnect_audio(
                pcm=gap_pcm,
                sample_rate=16000,
                channels=1,
                backfill_id="slow-stt-grace-expiry",
                final=True,
            )
        )
        assert await asyncio.to_thread(entered_stt.wait, 1.0)
        await session._begin_transport_reconnect(peer, "failed")
        epoch = session._peer_lifecycle.epoch
        assert await session.resolve_deferred_connection_state(
            epoch=epoch,
            peer_connection=peer,
        ) is False
        assert session.ended_at is None

        release_stt.set()
        result = await asyncio.wait_for(backfill_task, timeout=2.0)
        assert result["event"]["type"] == "user_final"
        assert result["event"]["text"] == "recovered after slow transcription"
        assert session._peer_lifecycle.phase == "reconnecting"
        await session.complete_transport_reconnect()
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-1",
            engine_id="f5",
        )
        assert reservation.epoch == session._peer_lifecycle.epoch
        assert session.state == "thinking"

    _run(scenario())


def test_terminal_session_rejects_late_reconnect_backfill_without_revival() -> None:
    session, _ = _new_session()
    terminal = _run(session.fail(reason="connection_failed"))

    result = _run(
        session.backfill_reconnect_audio(
            pcm=np.full(320, 2000, dtype=np.int16).tobytes(),
            backfill_id="late-terminal-backfill",
            final=True,
        )
    )

    assert terminal["type"] == "failed"
    assert result == {
        "status": "terminal",
        "frames": 0,
        "duration_ms": 0,
        "state": "failed",
        "reason": "connection_failed",
    }
    assert session._peer_lifecycle.phase == "terminal"
    assert session.ended_at is not None


def test_nonfinal_reconnect_backfill_with_extended_silence_finalizes_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    monkeypatch.setattr(session_module.time, "monotonic", lambda: now)

    stt = ScriptedSttAdapter()
    channel = ScriptedDataChannel(ready_state="closed")
    settings = AiBackendSettings(call_vad_end_silence_ms=700, call_media_reconnect_grace_ms=5000)
    session, _ = _new_session(stt_adapter=stt, data_channel=channel, settings=settings)

    speech_pcm = np.full(320, 2500, dtype=np.int16).tobytes()
    silence_pcm = np.zeros(320, dtype=np.int16).tobytes()

    assert _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm))) is None
    session.mark_media_reconnect_pending()
    session.start_media_reconnect_grace_if_pending()

    backfill = _run(
        session.backfill_reconnect_audio(
            pcm=b"".join([silence_pcm for _ in range(260)]),
            sample_rate=16000,
            channels=1,
            backfill_id="gap-nonfinal-extended-silence",
            reason="failed",
            attempt=1,
            final=False,
        )
    )

    assert backfill["event"]["type"] == "user_final"
    assert stt.calls, "STT must run when reconnect backfill already contains terminal silence"
    assert session.drain_undelivered_events()[0]["type"] == "user_final"


def test_final_reconnect_backfill_queues_recoverable_user_final_once() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    channel = ScriptedDataChannel(ready_state="closed")
    session, _ = _new_session(
        vad_adapter=vad,
        stt_adapter=stt,
        data_channel=channel,
    )

    pre_pcm = np.full(320, 1000, dtype=np.int16).tobytes()
    gap_pcm = np.full(320, 2000, dtype=np.int16).tobytes()

    assert _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(pre_pcm))) is None
    backfill = _run(
        session.backfill_reconnect_audio(
            pcm=gap_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="gap-final-drain",
            reason="connection_failed",
            attempt=1,
            final=True,
        )
    )

    assert backfill["event"]["type"] == "user_final"
    drained = session.drain_undelivered_events()
    assert [event["type"] for event in drained] == ["user_final"]
    assert drained[0]["text"] == "hello from mic"
    assert session.drain_undelivered_events() == []


def test_reconnect_audio_backfill_ignores_duplicate_ids() -> None:
    vad = ScriptedVadAdapter()
    session, _ = _new_session(vad_adapter=vad)
    gap_pcm = np.full(320, 2000, dtype=np.int16).tobytes()

    first = _run(
        session.backfill_reconnect_audio(
            pcm=gap_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="gap-duplicate",
        )
    )
    second = _run(
        session.backfill_reconnect_audio(
            pcm=gap_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="gap-duplicate",
        )
    )

    assert first["status"] == "accepted"
    assert second["status"] == "duplicate"
    assert len(session._turn_frames) == 1


def test_reconnect_audio_backfill_releases_held_replacement_track_after_final_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    monkeypatch.setattr(session_module.time, "monotonic", lambda: now)

    vad = NeverEndingVadAdapter()
    settings = AiBackendSettings(call_media_reconnect_grace_ms=5000)
    session, _ = _new_session(vad_adapter=vad, settings=settings)

    pre_pcm = np.full(320, 1000, dtype=np.int16).tobytes()
    gap_one_pcm = np.full(320, 2000, dtype=np.int16).tobytes()
    gap_two_pcm = np.full(320, 3000, dtype=np.int16).tobytes()
    live_pcm = np.full(320, 4000, dtype=np.int16).tobytes()

    assert _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(pre_pcm))) is None
    session.mark_media_reconnect_pending()
    session.start_media_reconnect_grace_if_pending()

    assert _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(live_pcm))) is None
    assert [frame.pcm for frame in session._turn_frames] == [pre_pcm]
    assert [frame.pcm for frame in session._reconnect_live_frame_hold_frames] == [live_pcm]

    first_batch = _run(
        session.backfill_reconnect_audio(
            pcm=gap_one_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="gap-batch-1",
            batch_index=1,
            final=False,
        )
    )
    assert first_batch["status"] == "accepted"
    assert [frame.pcm for frame in session._turn_frames] == [pre_pcm, gap_one_pcm]
    assert [frame.pcm for frame in session._reconnect_live_frame_hold_frames] == [live_pcm]

    final_batch = _run(
        session.backfill_reconnect_audio(
            pcm=gap_two_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="gap-batch-2",
            batch_index=2,
            final=True,
        )
    )

    assert final_batch["status"] == "accepted"
    assert [frame.pcm for frame in session._turn_frames] == [
        pre_pcm,
        gap_one_pcm,
        gap_two_pcm,
        live_pcm,
    ]
    assert session._reconnect_live_frame_hold_frames == []


def test_reconnect_audio_backfill_trims_overlap_before_appending() -> None:
    vad = NeverEndingVadAdapter()
    session, _ = _new_session(vad_adapter=vad)

    live_prefix = [
        np.full(320, 1000 + index * 25, dtype=np.int16).tobytes()
        for index in range(40)
    ]
    overlap = [
        np.full(320, 2000 + index * 35, dtype=np.int16).tobytes()
        for index in range(35)
    ]
    gap = [
        np.full(320, 4200 + index * 40, dtype=np.int16).tobytes()
        for index in range(6)
    ]

    for pcm in live_prefix + overlap:
        assert _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(pcm))) is None

    backfill = _run(
        session.backfill_reconnect_audio(
            pcm=b"".join(overlap + gap),
            sample_rate=16000,
            channels=1,
            backfill_id="overlap-gap",
            reason="failed",
            attempt=1,
            final=False,
        )
    )

    assert backfill["status"] == "accepted"
    assert backfill["frames"] == len(gap)
    assert [frame.pcm for frame in session._turn_frames] == live_prefix + overlap + gap


def test_finalize_user_turn_trims_long_trailing_silence_before_stt() -> None:
    stt = ScriptedSttAdapter()
    session, _ = _new_session(stt_adapter=stt)
    speech = np.full(320, 2500, dtype=np.int16).tobytes()
    silence = np.zeros(320, dtype=np.int16).tobytes()

    session._turn_started_at = "2026-05-02T00:00:00Z"
    session._speech_seen = True
    session._turn_frames = [
        PcmAudioFrame(pcm=speech, sample_rate=16000, channels=1),
        *[
            PcmAudioFrame(pcm=silence, sample_rate=16000, channels=1)
            for _ in range(80)
        ],
    ]

    event = _run(session.finalize_user_turn())

    assert event["type"] == "user_final"
    assert len(stt.calls) == 1
    assert stt.calls[0].count(silence) == 20
    assert stt.calls[0][0] == speech


def test_inbound_audio_normalizer_scales_integer_channels_before_mixing() -> None:
    """Regression: PyAV-style channel arrays must not clip int16 PCM to +/-1."""

    samples = np.asarray([[0, 8192, -8192, 16384]], dtype=np.int16)
    frame = ScriptedAvAudioFrame(samples)

    normalized = normalize_inbound_audio_frame(frame)
    normalized_samples = np.frombuffer(normalized.pcm, dtype=np.int16)

    assert normalized.sample_rate == 16000
    assert normalized_samples.tolist() == [0, 8192, -8192, 16384]


def test_inbound_audio_normalizer_handles_channel_last_integer_audio() -> None:
    """Regression: PyAV may expose audio as samples x channels."""

    samples = np.asarray([[0, 8192], [-8192, 16384], [32767, -32767]], dtype=np.int16)
    frame = ScriptedAvAudioFrame(samples)

    normalized = normalize_inbound_audio_frame(frame)
    normalized_samples = np.frombuffer(normalized.pcm, dtype=np.int16)

    assert normalized.sample_rate == 16000
    assert normalized_samples.tolist() == [4096, 4096, 0]


def test_inbound_audio_normalizer_handles_packed_stereo_audio() -> None:
    """Regression: packed stereo audio should be deinterleaved before VAD."""

    from av import AudioFrame

    samples = np.arange(1920, dtype=np.int16).reshape(1, 1920)
    frame = AudioFrame.from_ndarray(samples, format="s16", layout="stereo")
    frame.sample_rate = 48000

    normalized = normalize_inbound_audio_frame(frame)

    assert normalized.sample_rate == 16000
    assert len(normalized.pcm) == 640


def test_muted_inbound_audio_counts_dropped_frames_without_stt() -> None:
    vad = ScriptedVadAdapter()
    stt = ScriptedSttAdapter()
    source = ScriptedInboundAudioFrameSource(b"muted-pcm-frame")
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    _run(session.set_muted(True))
    event = _run(session.handle_inbound_audio_frame(source.frames[0]))

    assert event is None
    assert stt.calls == []
    assert vad.frames == []
    assert session.stats()["incoming_audio_frames"] == 1
    assert session.stats()["dropped_audio_frames"] == 1
    assert session.stats()["muted"] is True


def test_interrupt_cancels_active_ai_turn() -> None:
    session, _ = _new_session()
    active_turn = ScriptedAiTurn()
    session.active_ai_turn = active_turn

    event = _run(session.interrupt())

    assert session.interrupted is True
    assert active_turn.cancel_calls == 1
    assert event["type"] == "interrupted"
    assert event["session_id"] == "call-session-1"
    assert event["receiver_drain_ms"] == session_module.CALL_INTERRUPT_RECEIVER_DRAIN_MS
    assert 100 < event["receiver_drain_ms"] <= 500


def test_speak_text_queues_audio_and_emits_done_for_final_chunk() -> None:
    events: list[dict[str, Any]] = []
    track = ScriptedOutboundAudioTrack()
    adapter = ScriptedTtsAdapter()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
        event_sink=events.append,
    )

    event = _run(
        session.speak_text(
            "ai-turn-1",
            "Hello from AI.",
            "voice-1",
            "f5",
            final_chunk=True,
        )
    )

    assert adapter.calls == [
        {
            "turn_id": "ai-turn-1",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": "f5",
        }
    ]
    assert track.chunks == [SCRIPTED_WAV_BYTES]
    assert track.preroll_seconds == [CALL_TTS_AUDIO_PREROLL_SECONDS]
    assert track.wait_calls
    assert [item["type"] for item in events] == ["ai_audio_started", "ai_done"]
    assert events[0]["audio"]["duration_ms"] == 120
    assert events[0]["audio"]["samples"] == 5760
    assert events[0]["audio"]["rms"] > 0
    assert events[0]["audio"]["peak"] > 0
    assert event["type"] == "ai_done"
    assert event["tts_playback_final"]["playout_wait_completed"] is True
    assert session.state == "listening"


def test_real_nonstreaming_terminal_crosses_web_playout_validation_boundary() -> None:
    contract_path = (
        Path(__file__).resolve().parents[2]
        / "web-ui/server/app/domain/speech_terminal.py"
    )
    spec = importlib.util.spec_from_file_location(
        "rayme_web_speech_terminal_contract",
        contract_path,
    )
    assert spec is not None and spec.loader is not None
    contract = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = contract
    spec.loader.exec_module(contract)

    async def produce(playout_wait_completed: bool) -> dict[str, Any]:
        session, _ = _new_session(
            tts_adapter=ScriptedTtsAdapter(),
            outbound_audio_track=ScriptedOutboundAudioTrack(
                playout_wait_completed=playout_wait_completed
            ),
        )
        return await session.speak_text(
            f"turn-{playout_wait_completed}",
            "Real non-streaming speech.",
            "voice-f5",
            "f5",
            final_chunk=True,
        )

    class EmptyAudioAdapter:
        async def synthesize_call_text(self, **_kwargs: Any) -> dict[str, Any]:
            return {"wav_bytes": b"", "sample_rate": 24000, "duration_ms": 0}

    async def produce_empty_audio() -> dict[str, Any]:
        session, _ = _new_session(
            tts_adapter=EmptyAudioAdapter(),
            outbound_audio_track=ScriptedOutboundAudioTrack(),
        )
        return await session.speak_text(
            "turn-empty",
            "Empty audio must fail closed.",
            "voice-f5",
            "f5",
            final_chunk=True,
        )

    completed_event = _run(produce(True))
    incomplete_event = _run(produce(False))
    empty_event = _run(produce_empty_audio())
    completed = contract._speech_terminal_from_response(
        {"event": completed_event},
        require_final=True,
    )
    incomplete = contract._speech_terminal_from_response(
        {"event": incomplete_event},
        require_final=True,
    )
    empty = contract._speech_terminal_from_response(
        {"event": empty_event},
        require_final=True,
    )

    assert completed_event["tts_playback_final"]["playout_wait_completed"] is True
    assert completed.status == "normal"
    assert completed.playout_completed is True
    assert incomplete_event["tts_playback_final"]["playout_wait_completed"] is False
    assert incomplete.status == "error"
    assert incomplete.playout_completed is False
    assert empty_event["tts_playback_final"]["playout_wait_completed"] is False
    assert empty.status == "error"


def test_speak_text_queues_audio_before_audio_started_event() -> None:
    order: list[str] = []

    class OrderedTrack(ScriptedOutboundAudioTrack):
        async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
            order.append("enqueue")
            return await super().enqueue(chunk, preroll_seconds=preroll_seconds)

        async def wait_until_idle(self, *, timeout: float | None = None) -> bool:
            order.append("wait_until_idle")
            return await super().wait_until_idle(timeout=timeout)

    def sink(event: dict[str, Any]) -> None:
        order.append(event["type"])

    track = OrderedTrack()
    adapter = ScriptedTtsAdapter()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
        event_sink=sink,
    )

    _run(
        session.speak_text(
            "ai-turn-order",
            "Hello from AI.",
            "voice-1",
            "f5",
            final_chunk=True,
        )
    )

    assert order.index("enqueue") < order.index("ai_audio_started")
    assert order.index("ai_audio_started") < order.index("wait_until_idle")
    assert track.preroll_seconds == [CALL_TTS_AUDIO_PREROLL_SECONDS]


def test_speak_text_holds_speaking_after_track_drains(monkeypatch: Any) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(session_module.asyncio, "sleep", fake_sleep)

    track = ScriptedOutboundAudioTrack()
    adapter = ScriptedTtsAdapter()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
    )

    _run(
        session.speak_text(
            "ai-turn-hold",
            "Hello from AI.",
            "voice-1",
            "f5",
            final_chunk=True,
        )
    )

    assert CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS in sleeps
    assert 0.08 not in sleeps


def test_voxcpm2_streaming_speak_buffers_bounded_startup_chunks_without_final_metrics() -> None:
    events: list[dict[str, Any]] = []

    async def scenario() -> dict[str, Any]:
        audio_started = asyncio.Event()

        def sink(event: dict[str, Any]) -> None:
            events.append(event)
            if event["type"] == "ai_audio_started":
                audio_started.set()

        track = ObservableStreamingOutboundAudioTrack()
        adapter = ScriptedStreamingTtsAdapter()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=sink,
        )
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-voxcpm2-stream-first",
                "Hello from streamed VoxCPM2.",
                "voice-voxcpm2",
                "voxcpm2",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="Real VoxCPM2 reference text.",
                reference_audio_content_type="audio/wav",
            )
        )
        try:
            assert await asyncio.to_thread(adapter.first_chunk_yielded.wait, 1.0)
            assert track.chunks == []
            adapter.release_second_chunk.set()

            await _wait_for_async_event_or_task(
                audio_started,
                speech,
                label="VoxCPM2 first streamed audio event",
            )

            assert len(track.chunks) == 2
            assert track.preroll_seconds == [CALL_TTS_AUDIO_PREROLL_SECONDS, 0.0]
            assert adapter.requests
            request = adapter.requests[0]
            assert request.voxcpm2_inference_timesteps == 4
            assert request.voxcpm2_normalize is False
            assert request.voxcpm2_denoise is False
            assert [event["type"] for event in events] == ["ai_audio_started"]

            playback = events[0]["tts_playback"]
            assert playback["streaming_used"] is True
            assert playback["fallback_used"] is False
            assert playback["whole_wav_fallback_used"] is False
            assert playback["chunk_count_at_start"] == 2
            assert playback["first_chunk_generated_ms"] == 25.0
            assert "buffered_until_complete" not in playback
            assert "total_generation_ms" not in playback
            assert "total_playback_ms" not in playback

            return await speech
        finally:
            adapter.release_second_chunk.set()
            if not speech.done():
                speech.cancel()

    event = _run(scenario())

    assert event["type"] == "ai_done"
    assert [item["type"] for item in events] == ["ai_audio_started", "ai_done"]


def test_streaming_metrics_do_not_fabricate_zeroes_without_track_provider() -> None:
    adapter = SlowQwenStreamingTtsAdapter(chunk_count=2)
    adapter.release_completion.set()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=ScriptedOutboundAudioTrack(),
    )

    event = _run(
        session.speak_text(
            "turn-missing-track-metrics",
            "Track telemetry must be measured, never invented.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=True,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )
    )

    final = event["tts_playback_final"]
    assert final["track_metrics_present"] is False
    assert "track_pending_samples" not in final
    assert "track_pending_audio_ms" not in final
    assert "track_admission_capacity_samples" not in final


def test_qwen_incremental_turn_carries_monotonic_segment_ordinals() -> None:
    adapter = SlowQwenStreamingTtsAdapter(chunk_count=2)
    adapter.release_completion.set()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=ScriptedOutboundAudioTrack(),
    )

    async def scenario() -> None:
        await session.speak_text(
            "turn-segment-entropy",
            "The first sentence keeps the prepared speaker.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=False,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )
        await session.speak_text(
            "turn-segment-entropy",
            "The second sentence gets a fresh deterministic trajectory.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=True,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )

    _run(scenario())

    requests = [item["request"] for item in adapter.requests]
    assert [request.turn_id for request in requests] == [
        "turn-segment-entropy",
        "turn-segment-entropy",
    ]
    assert [request.segment_ordinal for request in requests] == [0, 1]
    worker_request_ids = [item["request_id"] for item in adapter.requests]
    assert worker_request_ids[0] != worker_request_ids[1]
    assert all(value.startswith("tts-segment-") for value in worker_request_ids)
    assert [request.request_id for request in requests] == worker_request_ids
    assert session._tts_turn_ledgers["turn-segment-entropy"].state == "completed"


def test_qwen_nonfinal_segment_returns_before_playout_and_final_waits_turn_idle() -> None:
    adapter = SlowQwenStreamingTtsAdapter(chunk_count=2)
    adapter.release_completion.set()
    track = BlockedIdleOutboundAudioTrack()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
    )

    async def scenario() -> None:
        first = await asyncio.wait_for(
            session.speak_text(
                "turn-live-queued",
                "The first segment starts playing immediately.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=False,
                segment_id="turn-live-queued:0",
                segment_ordinal=0,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            ),
            timeout=1.0,
        )
        assert first["status"] == "queued"
        assert track.wait_calls == []
        assert track.input_complete_calls == 0
        assert len(track.chunks) == 2

        final_task = asyncio.create_task(
            session.speak_text(
                "turn-live-queued",
                "The final segment may generate while earlier audio is pending.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                segment_id="turn-live-queued:1",
                segment_ordinal=1,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        await asyncio.wait_for(track.wait_started.wait(), timeout=1.0)
        assert len(adapter.requests) == 2
        assert len(track.chunks) == 4
        assert not final_task.done()
        assert track.input_complete_calls == 1

        track.release_idle.set()
        final = await asyncio.wait_for(final_task, timeout=1.0)
        assert final["type"] == "ai_done"
        assert final["tts_playback_final"]["playout_wait_completed"] is True

    _run(scenario())


def test_qwen_final_marker_is_only_waiter_after_nonfinal_admission() -> None:
    adapter = SlowQwenStreamingTtsAdapter(chunk_count=2)
    adapter.release_completion.set()
    track = BlockedIdleOutboundAudioTrack()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
    )

    async def scenario() -> None:
        queued = await asyncio.wait_for(
            session.speak_text(
                "turn-live-final-marker",
                "This admitted segment must not wait for the speaker to drain.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=False,
                segment_id="turn-live-final-marker:0",
                segment_ordinal=0,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            ),
            timeout=1.0,
        )
        assert queued["status"] == "queued"
        assert track.wait_calls == []

        final_task = asyncio.create_task(
            session.complete_speech_turn(
                turn_id="turn-live-final-marker",
                voice_id="voice-qwen",
                engine_id="qwen3_1_7b",
                segment_id="turn-live-final-marker:1",
                segment_ordinal=1,
            )
        )
        await asyncio.wait_for(track.wait_started.wait(), timeout=1.0)
        assert not final_task.done()
        assert track.input_complete_calls == 1

        track.release_idle.set()
        final = await asyncio.wait_for(final_task, timeout=1.0)
        assert final["type"] == "ai_done"
        assert final["tts_playback_final"]["playout_wait_completed"] is True

    _run(scenario())


def test_web_turn_cancel_is_idempotent_and_does_not_poison_the_next_turn() -> None:
    adapter = SlowQwenStreamingTtsAdapter(chunk_count=2)
    adapter.release_completion.set()
    track = ScriptedOutboundAudioTrack()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
    )

    async def scenario() -> None:
        queued = await session.speak_text(
            "turn-web-cancel",
            "This audio is cancelled by its owning web turn.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=False,
            segment_id="turn-web-cancel:0",
            segment_ordinal=0,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )
        assert queued["status"] == "queued"

        first, retry = await asyncio.gather(
            session.cancel_speech_turn("turn-web-cancel"),
            session.cancel_speech_turn("turn-web-cancel"),
        )
        assert first == retry
        assert first["cancelled_turn_id"] == "turn-web-cancel"
        assert track.stop_calls == 1
        assert session.state == "listening"

        with pytest.raises(SpeechTurnTerminalError):
            await session.complete_speech_turn(
                turn_id="turn-web-cancel",
                voice_id="voice-qwen",
                engine_id="qwen3_1_7b",
                segment_id="turn-web-cancel:1",
                segment_ordinal=1,
            )

        recovered = await session.speak_text(
            "turn-after-web-cancel",
            "A subsequent turn still completes normally.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=True,
            segment_id="turn-after-web-cancel:0",
            segment_ordinal=0,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )
        assert recovered["type"] == "ai_done"

    _run(scenario())


def test_qwen_failed_segment_retries_keep_reserved_ordinal_until_success() -> None:
    class RetryQwenAdapter:
        engine_id = "qwen3_1_7b"

        def __init__(self) -> None:
            self.requests: list[Any] = []
            self.fail_calls = {0, 2}
            self.call_count = 0

        def synthesize(self, _request: Any) -> Any:
            raise AssertionError("whole synthesis fallback was used")

        def stream(
            self,
            request: Any,
            *,
            request_id: str,
            voice_key: str,
        ) -> Any:
            del request_id, voice_key
            call_index = self.call_count
            self.call_count += 1
            self.requests.append(request)
            if call_index in self.fail_calls:
                raise RuntimeError("retryable generation failure")
            for chunk_index in range(2):
                yield TtsAudioChunk(
                    engine_id=self.engine_id,
                    chunk_index=chunk_index,
                    wav_bytes=QWEN_STREAM_CHUNK_WAV_BYTES,
                    sample_rate=24_000,
                    duration_ms=100.0,
                    generated_at_ms=25.0 + chunk_index * 25.0,
                )

    adapter = RetryQwenAdapter()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=ScriptedOutboundAudioTrack(),
    )

    async def speak(text: str, *, final_chunk: bool, segment_ordinal: int) -> dict[str, Any]:
        return await session.speak_text(
            "turn-segment-retry",
            text,
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=final_chunk,
            segment_id=f"turn-segment-retry:{segment_ordinal}",
            segment_ordinal=segment_ordinal,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )

    async def scenario() -> None:
        first_failure = await speak(
            "The first segment is retried.",
            final_chunk=False,
            segment_ordinal=0,
        )
        first_retry = await speak(
            "The first segment is retried.",
            final_chunk=False,
            segment_ordinal=0,
        )
        final_failure = await speak(
            "The final segment is retried.",
            final_chunk=True,
            segment_ordinal=1,
        )
        final_retry = await speak(
            "The final segment is retried.",
            final_chunk=True,
            segment_ordinal=1,
        )

        assert first_failure["type"] == "failed"
        assert first_retry["status"] == "queued"
        assert final_failure["type"] == "failed"
        assert final_retry["type"] == "ai_done"

    _run(scenario())

    assert [request.segment_ordinal for request in adapter.requests] == [0, 0, 1, 1]
    worker_request_ids = [request.request_id for request in adapter.requests]
    assert len(set(worker_request_ids)) == 4
    assert all(value.startswith("tts-segment-") for value in worker_request_ids)
    assert session._tts_turn_ledgers["turn-segment-retry"].state == "completed"


def test_segment_ledger_rejects_collisions_and_replays_committed_response() -> None:
    class LedgerAdapter:
        engine_id = "qwen3_1_7b"

        def __init__(self) -> None:
            self.requests: list[Any] = []
            self.fail_next = False

        def synthesize(self, _request: Any) -> Any:
            raise AssertionError("whole synthesis fallback was used")

        def stream(
            self,
            request: Any,
            *,
            request_id: str,
            voice_key: str,
        ) -> Any:
            del request_id, voice_key
            self.requests.append(request)
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("retryable segment failure")
            for chunk_index in range(2):
                yield TtsAudioChunk(
                    engine_id=self.engine_id,
                    chunk_index=chunk_index,
                    wav_bytes=QWEN_STREAM_CHUNK_WAV_BYTES,
                    sample_rate=24_000,
                    duration_ms=320.0,
                    generated_at_ms=25.0 + chunk_index * 25.0,
                )

    adapter = LedgerAdapter()
    track = ScriptedOutboundAudioTrack()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
    )

    async def speak(
        turn_id: str,
        text: str,
        *,
        segment_id: str,
        ordinal: int,
        final_chunk: bool,
    ) -> dict[str, Any]:
        return await session.speak_text(
            turn_id,
            text,
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=final_chunk,
            segment_id=segment_id,
            segment_ordinal=ordinal,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )

    async def scenario() -> None:
        committed = await speak(
            "turn-ledger",
            "The first immutable segment.",
            segment_id="segment-0",
            ordinal=0,
            final_chunk=False,
        )
        request_count = len(adapter.requests)
        chunk_count = len(track.chunks)
        duplicate = await speak(
            "turn-ledger",
            "The first immutable segment.",
            segment_id="segment-0",
            ordinal=0,
            final_chunk=False,
        )
        assert duplicate == committed
        assert len(adapter.requests) == request_count
        assert len(track.chunks) == chunk_count

        with pytest.raises(SpeechSegmentConflictError):
            await speak(
                "turn-ledger",
                "Mutated content must be rejected.",
                segment_id="segment-0",
                ordinal=0,
                final_chunk=False,
            )
        with pytest.raises(SpeechSegmentConflictError):
            await speak(
                "turn-ledger",
                "A second identity cannot steal ordinal zero.",
                segment_id="segment-other",
                ordinal=0,
                final_chunk=False,
            )

        adapter.fail_next = True
        failed = await speak(
            "turn-ledger",
            "The final immutable segment.",
            segment_id="segment-1",
            ordinal=1,
            final_chunk=True,
        )
        assert failed["type"] == "failed"
        with pytest.raises(SpeechSegmentConflictError):
            await speak(
                "turn-ledger",
                "Changed final content.",
                segment_id="segment-1",
                ordinal=1,
                final_chunk=True,
            )
        final = await speak(
            "turn-ledger",
            "The final immutable segment.",
            segment_id="segment-1",
            ordinal=1,
            final_chunk=True,
        )
        final_request_count = len(adapter.requests)
        assert await speak(
            "turn-ledger",
            "The final immutable segment.",
            segment_id="segment-1",
            ordinal=1,
            final_chunk=True,
        ) == final
        assert len(adapter.requests) == final_request_count
        with pytest.raises(SpeechTurnTerminalError):
            await speak(
                "turn-ledger",
                "Nothing may follow completion.",
                segment_id="segment-2",
                ordinal=2,
                final_chunk=False,
            )

        await session._cancel_tts_turn("turn-cancelled-ledger")
        with pytest.raises(SpeechTurnTerminalError):
            await speak(
                "turn-cancelled-ledger",
                "Cancelled turns cannot revive.",
                segment_id="cancelled-0",
                ordinal=0,
                final_chunk=True,
            )

    _run(scenario())


def test_completed_final_marker_retry_returns_cached_ai_done() -> None:
    adapter = SlowQwenStreamingTtsAdapter(chunk_count=2)
    adapter.release_completion.set()
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=ScriptedOutboundAudioTrack(),
    )

    async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
        queued = await session.speak_text(
            "turn-final-marker-idempotent",
            "A non-final segment is admitted once.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=False,
            segment_id="turn-final-marker-idempotent:0",
            segment_ordinal=0,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )
        assert queued["status"] == "queued"
        first = await session.complete_speech_turn(
            turn_id="turn-final-marker-idempotent",
            voice_id="voice-qwen",
            engine_id="qwen3_1_7b",
            segment_id="turn-final-marker-idempotent:1",
            segment_ordinal=1,
        )
        retry = await session.complete_speech_turn(
            turn_id="turn-final-marker-idempotent",
            voice_id="voice-qwen",
            engine_id="qwen3_1_7b",
            segment_id="turn-final-marker-idempotent:1",
            segment_ordinal=1,
        )
        return first, retry

    first, retry = _run(scenario())

    assert first == retry
    assert first["type"] == "ai_done"
    assert len(adapter.requests) == 1


def test_engine_switch_silences_old_and_new_tracks_before_cancel_ack() -> None:
    class BlockedCancelAdapter:
        engine_id = "qwen3_1_7b"

        def __init__(self) -> None:
            self.stream_blocked = threading.Event()
            self.release_stream = threading.Event()
            self.stream_drained = threading.Event()
            self.cancel_entered = threading.Event()
            self.allow_cancel_ack = threading.Event()
            self.cancel_calls: list[str] = []

        def synthesize(self, _request: Any) -> Any:
            raise AssertionError("whole synthesis fallback was used")

        def stream(
            self,
            _request: Any,
            *,
            request_id: str,
            voice_key: str,
        ) -> Any:
            del voice_key
            try:
                for chunk_index in range(2):
                    yield TtsAudioChunk(
                        engine_id=self.engine_id,
                        chunk_index=chunk_index,
                        wav_bytes=QWEN_STREAM_CHUNK_WAV_BYTES,
                        sample_rate=24_000,
                        duration_ms=320.0,
                        generated_at_ms=25.0 + chunk_index * 25.0,
                    )
                self.stream_blocked.set()
                self.release_stream.wait()
            finally:
                self.stream_drained.set()

        def cancel(self, request_id: str) -> bool:
            self.cancel_calls.append(request_id)
            self.cancel_entered.set()
            self.allow_cancel_ack.wait(timeout=1.0)
            self.release_stream.set()
            return self.stream_drained.wait(timeout=1.0)

    async def scenario() -> tuple[
        BlockedCancelAdapter,
        ScriptedPeerConnection,
        ScriptedOutboundAudioTrack,
        ScriptedOutboundAudioTrack,
    ]:
        adapter = BlockedCancelAdapter()
        old_track = ScriptedOutboundAudioTrack()
        new_track = ScriptedOutboundAudioTrack()
        session, active_peer = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=old_track,
        )
        session.voice_id = "voice-before"
        session.engine_id = "qwen3_1_7b"
        candidate = ScriptedPeerConnection()
        speech = asyncio.create_task(
            session.speak_text(
                "turn-engine-switch-order",
                "The old voice must stop before acknowledgement.",
                "voice-before",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        assert await asyncio.to_thread(adapter.stream_blocked.wait, 1.0)
        old_chunk_count = len(old_track.chunks)
        assert old_chunk_count == 2

        generation = await session.mark_peer_connection_pending(
            candidate,
            outbound_audio_track=new_track,
            configuration=PeerOfferConfiguration(
                thread_id="thread-after",
                voice_id="voice-after",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=None,
                stt_adapter=None,
            ),
            timeout_seconds=60.0,
        )
        acceptance = asyncio.create_task(
            session.accept_pending_peer_connection(
                candidate,
                generation=generation,
            )
        )
        assert await asyncio.to_thread(adapter.cancel_entered.wait, 1.0)

        assert old_track.stop_calls == 1
        assert new_track.stop_calls == 1
        assert active_peer.close_calls == 1
        assert acceptance.done() is False
        assert len(old_track.chunks) == old_chunk_count
        assert session._peer_lifecycle.phase == "switching"
        assert session.voice_id == "voice-before"
        with pytest.raises(SpeechSessionSelectionError):
            await session.reserve_accepted_speech_configuration(
                voice_id="voice-after",
                engine_id="f5",
            )

        adapter.allow_cancel_ack.set()
        accepted, previous_peer = await acceptance
        assert accepted is True
        assert previous_peer is active_peer
        accepted_selection = await session.reserve_accepted_speech_configuration(
            voice_id="voice-after",
            engine_id="f5",
        )
        assert accepted_selection.epoch == session._peer_lifecycle.epoch
        try:
            await speech
        except asyncio.CancelledError:
            pass
        return adapter, active_peer, old_track, new_track

    adapter, active_peer, old_track, new_track = _run(scenario())

    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].startswith("tts-segment-")
    assert active_peer.close_calls == 1
    assert old_track.stop_calls == 1
    assert new_track.stop_calls == 1
    assert len(old_track.chunks) == 2


def test_reserved_speech_cannot_claim_after_engine_switch() -> None:
    async def scenario() -> None:
        adapter = SlowQwenStreamingTtsAdapter()
        track = ScriptedOutboundAudioTrack()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
        )
        session.voice_id = "voice-before"
        session.engine_id = "qwen3_1_7b"
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-before",
            engine_id="qwen3_1_7b",
        )

        admission_entered = asyncio.Event()
        resume_admission = asyncio.Event()
        original_admit = session._admit_tts_segment

        async def gated_admission(**kwargs: Any) -> Any:
            admission_entered.set()
            await resume_admission.wait()
            return await original_admit(**kwargs)

        session._admit_tts_segment = gated_admission  # type: ignore[method-assign]
        speech = asyncio.create_task(
            session.speak_text(
                "turn-pre-switch-reservation",
                "This stale voice must never start.",
                "voice-before",
                "qwen3_1_7b",
                final_chunk=True,
                accepted_configuration=reservation,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        await admission_entered.wait()

        candidate = ScriptedPeerConnection()
        generation = await session.mark_peer_connection_pending(
            candidate,
            configuration=PeerOfferConfiguration(
                thread_id="thread-after",
                voice_id="voice-after",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=None,
                stt_adapter=None,
            ),
            timeout_seconds=60.0,
        )
        accepted, _ = await session.accept_pending_peer_connection(
            candidate,
            generation=generation,
        )
        assert accepted is True

        resume_admission.set()
        with pytest.raises(SpeechSessionSelectionError):
            await speech
        assert adapter.requests == []
        assert track.chunks == []
        assert session._speech_admission is None

    _run(scenario())


def test_overlapping_engine_switch_rejects_and_closes_second_peer() -> None:
    class BlockingClosePeer(ScriptedPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_started = asyncio.Event()
            self.release_close = asyncio.Event()

        async def close(self) -> None:
            self.close_calls += 1
            self.close_started.set()
            await self.release_close.wait()

    async def scenario() -> None:
        session, _ = _new_session(
            outbound_audio_track=ScriptedOutboundAudioTrack()
        )
        old_peer = BlockingClosePeer()
        session.peer_connection = old_peer
        session.voice_id = "voice-before"
        session.engine_id = "qwen3_1_7b"

        first_peer = ScriptedPeerConnection()
        first_generation = await session.mark_peer_connection_pending(
            first_peer,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
            configuration=PeerOfferConfiguration(
                thread_id="thread-first",
                voice_id="voice-first",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=None,
                stt_adapter=None,
            ),
            timeout_seconds=60.0,
        )
        first_accept = asyncio.create_task(
            session.accept_pending_peer_connection(
                first_peer,
                generation=first_generation,
            )
        )
        await old_peer.close_started.wait()
        assert session._peer_lifecycle.phase == "switching"

        second_peer = ScriptedPeerConnection()
        with pytest.raises(PeerSwitchInProgressError):
            await session.mark_peer_connection_pending(
                second_peer,
                configuration=PeerOfferConfiguration(
                    thread_id="thread-second",
                    voice_id="voice-second",
                    engine_id="voxcpm2",
                    prompt_messages=(),
                    vad_adapter=None,
                    stt_adapter=None,
                ),
                timeout_seconds=60.0,
            )
        assert second_peer.close_calls == 1

        old_peer.release_close.set()
        accepted, previous_peer = await first_accept
        assert accepted is True
        assert previous_peer is old_peer
        assert session.peer_connection is first_peer
        assert session.thread_id == "thread-first"
        assert session.voice_id == "voice-first"
        assert session.engine_id == "f5"
        assert session._peer_lifecycle.phase == "stable"
        assert session._peer_lifecycle.switch_owner is None
        assert first_peer.close_calls == 0

    _run(scenario())


def test_switching_away_from_qwen_releases_prompt_for_another_session() -> None:
    lease_owner: str | None = "qwen-owner-one"
    releases: list[str] = []

    async def release_prompt(owner: str) -> bool:
        nonlocal lease_owner
        releases.append(owner)
        if lease_owner == owner:
            lease_owner = None
            return True
        return False

    async def scenario() -> None:
        nonlocal lease_owner
        first, _ = _new_session(session_id="qwen-owner-one")
        first.voice_id = "voice-qwen"
        first.engine_id = "qwen3_1_7b"
        assert await first.install_or_release_tts_prompt_lease(release_prompt)

        candidate = ScriptedPeerConnection()
        generation = await first.mark_peer_connection_pending(
            candidate,
            configuration=PeerOfferConfiguration(
                thread_id="thread-f5",
                voice_id="voice-f5",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=None,
                stt_adapter=None,
            ),
            timeout_seconds=60.0,
        )
        accepted, _ = await first.accept_pending_peer_connection(
            candidate,
            generation=generation,
        )

        assert accepted is True
        assert first.engine_id == "f5"
        assert first._tts_prompt_lease_releaser is None
        assert releases == ["qwen-owner-one"]
        assert lease_owner is None

        second, _ = _new_session(session_id="qwen-owner-two")
        if lease_owner is None:
            lease_owner = second.session_id
        assert lease_owner == "qwen-owner-two"
        assert await second.install_or_release_tts_prompt_lease(release_prompt)

    _run(scenario())


def test_qwen_long_turn_reconnect_barge_in_and_recovery_preserve_live_call(
    monkeypatch: Any,
) -> None:
    import app.api.webrtc as webrtc_module

    monkeypatch.setattr(session_module, "CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS", 0.0)
    events: list[dict[str, Any]] = []
    released_prompt_leases: list[str] = []

    class FakeAudioClock:
        def __init__(self) -> None:
            self.elapsed_seconds = 0.0
            self.advances: list[float] = []

        async def advance(self, seconds: float) -> None:
            self.elapsed_seconds += seconds
            self.advances.append(seconds)
            await asyncio.sleep(0)

    class FakeClockPacedOutboundAudioTrack(ScriptedOutboundAudioTrack):
        def __init__(self, clock: FakeAudioClock) -> None:
            super().__init__()
            self.clock = clock
            self.actual_audio_seconds = 0.0

        async def enqueue(
            self,
            chunk: bytes,
            *,
            preroll_seconds: float = 0.0,
        ) -> float:
            with sf.SoundFile(BytesIO(chunk)) as audio:
                duration_seconds = audio.frames / float(audio.samplerate)
            self.chunks.append(chunk)
            self.preroll_seconds.append(preroll_seconds)
            paced_seconds = duration_seconds + preroll_seconds
            self.actual_audio_seconds += duration_seconds
            await self.clock.advance(paced_seconds)
            return paced_seconds

    class CallbackPeer:
        def __init__(self) -> None:
            self.connectionState = "new"
            self.iceConnectionState = "new"
            self.handlers: dict[str, Any] = {}
            self.close_calls = 0

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

        async def close(self) -> None:
            self.close_calls += 1

    class IncidentQwenAdapter:
        engine_id = "qwen3_1_7b"

        def __init__(self) -> None:
            self.stream_count = 0
            self.active_request_id: str | None = None
            self.reconnect_pause = threading.Event()
            self.resume_after_reconnect = threading.Event()
            self.ready_for_barge_in = threading.Event()
            self.release_for_cancel = threading.Event()
            self.first_stream_drained = threading.Event()
            self.first_stream_completed = threading.Event()
            self.cancel_calls: list[str] = []
            self.synthesize_calls = 0

        def synthesize(self, _request: Any) -> Any:
            self.synthesize_calls += 1
            raise AssertionError("whole synthesis fallback was used")

        def stream(
            self,
            _request: Any,
            *,
            request_id: str,
            voice_key: str,
        ) -> Any:
            assert voice_key == "voice-qwen"
            stream_index = self.stream_count
            self.stream_count += 1
            self.active_request_id = request_id
            try:
                if stream_index == 0:
                    for chunk_index in range(12):
                        if chunk_index == 4:
                            self.reconnect_pause.set()
                            self.resume_after_reconnect.wait()
                        if chunk_index == 10:
                            self.ready_for_barge_in.set()
                            self.release_for_cancel.wait()
                        if self.release_for_cancel.is_set():
                            break
                        yield TtsAudioChunk(
                            engine_id=self.engine_id,
                            chunk_index=chunk_index,
                            wav_bytes=LONG_QWEN_STREAM_CHUNK_WAV_BYTES,
                            sample_rate=24_000,
                            duration_ms=4_000.0,
                            generated_at_ms=25.0 + chunk_index * 50.0,
                        )
                    if not self.release_for_cancel.is_set():
                        self.first_stream_completed.set()
                    return

                for chunk_index in range(2):
                    yield TtsAudioChunk(
                        engine_id=self.engine_id,
                        chunk_index=chunk_index,
                        wav_bytes=QWEN_STREAM_CHUNK_WAV_BYTES,
                        sample_rate=24_000,
                        duration_ms=320.0,
                        generated_at_ms=20.0 + chunk_index * 40.0,
                    )
            finally:
                self.active_request_id = None
                if stream_index == 0:
                    self.first_stream_drained.set()

        def cancel(self, request_id: str) -> bool:
            assert request_id == self.active_request_id
            self.cancel_calls.append(request_id)
            self.release_for_cancel.set()
            return self.first_stream_drained.wait(timeout=1.0)

    async def wait_thread_event(
        event: threading.Event,
        *,
        label: str,
    ) -> None:
        ready = await asyncio.to_thread(event.wait, 1.0)
        assert ready, f"timed out waiting for {label}"

    async def scenario() -> tuple[
        IncidentQwenAdapter,
        CallbackPeer,
        CallbackPeer,
        ScriptedOutboundAudioTrack,
        ScriptedOutboundAudioTrack,
        CallSession,
    ]:
        active_peer = CallbackPeer()
        replacement_peer = CallbackPeer()
        audio_clock = FakeAudioClock()
        active_track = FakeClockPacedOutboundAudioTrack(audio_clock)
        replacement_track = FakeClockPacedOutboundAudioTrack(audio_clock)
        adapter = IncidentQwenAdapter()
        session = CallSession(
            session_id="qwen-long-turn-reconnect-incident",
            peer_connection=active_peer,
            tts_adapter=adapter,
            outbound_audio_track=active_track,
            event_sink=events.append,
        )
        await session.install_or_release_tts_prompt_lease(
            lambda owner: released_prompt_leases.append(owner)
        )
        webrtc_module._attach_peer_handlers(active_peer, session)

        first_audio = asyncio.Event()

        def observe_first_audio(event: dict[str, Any]) -> None:
            events.append(event)
            if event.get("type") == "ai_audio_started":
                first_audio.set()

        session.event_sink = observe_first_audio
        long_speech = asyncio.create_task(
            session.speak_text(
                "turn-qwen-40s-paced",
                "A long streamed turn survives a media replacement before barge in.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        await asyncio.wait_for(first_audio.wait(), timeout=1.0)
        assert adapter.first_stream_completed.is_set() is False
        await wait_thread_event(adapter.reconnect_pause, label="reconnect pause")
        assert active_track.chunks

        generation = await session.mark_peer_connection_pending(
            replacement_peer,
            outbound_audio_track=replacement_track,
            timeout_seconds=60.0,
        )
        webrtc_module._attach_peer_handlers(
            replacement_peer,
            session,
            pending_generation=generation,
        )
        active_peer.connectionState = "closed"
        await active_peer.handlers["connectionstatechange"]()

        assert session.state == "reconnecting"
        assert session.ended_at is None
        assert released_prompt_leases == []

        replacement_peer.connectionState = "connected"
        replacement_peer.iceConnectionState = "connected"
        await replacement_peer.handlers["connectionstatechange"]()

        assert session.peer_connection is replacement_peer
        assert session.state == "speaking"
        assert active_peer.close_calls == 1
        assert replacement_peer.close_calls == 0
        assert released_prompt_leases == []

        adapter.resume_after_reconnect.set()
        await wait_thread_event(adapter.ready_for_barge_in, label="post-reconnect audio")
        for _ in range(100):
            if audio_clock.elapsed_seconds >= 40.0:
                break
            await asyncio.sleep(0)
        assert audio_clock.elapsed_seconds == pytest.approx(40.0)
        assert len(audio_clock.advances) == 10
        assert all(seconds == pytest.approx(4.0) for seconds in audio_clock.advances)
        assert replacement_track.chunks

        user_pcm = np.full(320, 4_000, dtype=np.int16).tobytes()
        onset_frames = (session_module.CALL_BARGE_IN_MIN_SPEECH_MS + 19) // 20
        interrupted = None
        for _ in range(onset_frames):
            interrupted = await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(user_pcm)
            )

        assert interrupted is not None
        assert interrupted["type"] == "interrupted"
        assert interrupted["control_cause"] == "vad_barge_in"
        try:
            await long_speech
        except asyncio.CancelledError:
            pass

        assert adapter.first_stream_completed.is_set() is False
        assert adapter.first_stream_drained.is_set()
        assert session.state == "listening"
        assert released_prompt_leases == []

        recovery = await session.speak_text(
            "turn-qwen-after-reconnect-barge",
            "The recovered live call completes exactly once.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=True,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )
        assert recovery["type"] == "ai_done"
        assert session.state == "listening"
        assert released_prompt_leases == []

        await session.end(reason="hangup")
        return (
            adapter,
            active_peer,
            replacement_peer,
            active_track,
            replacement_track,
            session,
        )

    (
        adapter,
        active_peer,
        replacement_peer,
        active_track,
        replacement_track,
        session,
    ) = _run(scenario())

    event_types = [event["type"] for event in events]
    assert event_types.count("ai_audio_started") == 2
    assert event_types.count("interrupted") == 1
    assert event_types.count("ai_done") == 1
    assert "failed" not in event_types
    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].startswith("tts-segment-")
    assert adapter.synthesize_calls == 0
    assert active_track.chunks
    assert replacement_track.chunks
    total_actual_audio_seconds = (
        active_track.actual_audio_seconds + replacement_track.actual_audio_seconds
    )
    assert 40.0 <= total_actual_audio_seconds < 60.0
    assert active_peer.close_calls == 1
    assert replacement_peer.close_calls == 1
    assert session.end_reason == "hangup"
    assert released_prompt_leases == ["qwen-long-turn-reconnect-incident"]


def test_voxcpm2_slow_stream_starts_playback_before_stream_completion(monkeypatch: Any) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS", 0.2)
    events: list[dict[str, Any]] = []

    async def scenario() -> tuple[dict[str, Any], ObservableStreamingOutboundAudioTrack]:
        audio_started = asyncio.Event()

        def sink(event: dict[str, Any]) -> None:
            events.append(event)
            if event["type"] == "ai_audio_started":
                audio_started.set()

        track = ObservableStreamingOutboundAudioTrack()
        adapter = SlowStreamingTtsAdapter()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=sink,
        )
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-voxcpm2-slow-stream",
                "Hello from slow streamed VoxCPM2.",
                "voice-voxcpm2",
                "voxcpm2",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="Real VoxCPM2 reference text.",
                reference_audio_content_type="audio/wav",
            )
        )
        try:
            assert await asyncio.to_thread(adapter.second_chunk_yielded.wait, 1.0)
            await _wait_for_async_event_or_task(
                audio_started,
                speech,
                label="VoxCPM2 slow stream starts before completion",
            )
            assert not adapter.stream_completed.is_set()
            assert track.chunks
            assert events and events[0]["type"] == "ai_audio_started"
            playback = events[0]["tts_playback"]
            assert "buffered_until_complete" not in playback
            assert playback["startup_buffered_chunks"] >= 2
            assert playback["chunk_count_at_start"] >= 2
            assert not speech.done()

            adapter.release_completion.set()
            return await speech, track
        finally:
            adapter.release_completion.set()
            if not speech.done():
                speech.cancel()

    event, track = _run(scenario())

    assert event["type"] == "ai_done"
    assert [item["type"] for item in events] == ["ai_audio_started", "ai_done"]
    assert track.chunks == [SCRIPTED_WAV_BYTES, SCRIPTED_WAV_BYTES, SCRIPTED_WAV_BYTES]
    assert track.preroll_seconds == [CALL_TTS_AUDIO_PREROLL_SECONDS, 0.0, 0.0]
    assert event["tts_playback_final"]["streaming_used"] is True
    assert event["tts_playback_final"]["chunk_count"] == 3
    assert event["tts_playback_final"]["inter_chunk_gaps_ms"] == [275.0, 60.0]
    assert event["tts_playback_final"]["under_realtime_generation"] is True
    assert event["tts_playback_final"]["realtime_generation_ratio"] < 1.05


def test_qwen_slow_stream_starts_playback_before_stream_completion() -> None:
    adapter = SlowQwenStreamingTtsAdapter(
        chunk_count=3,
        wav_bytes=QWEN_STREAM_CHUNK_WAV_BYTES,
        duration_ms=320.0,
    )
    events: list[dict[str, Any]] = []

    async def scenario() -> tuple[dict[str, Any], ObservableStreamingOutboundAudioTrack]:
        audio_started = asyncio.Event()

        def sink(event: dict[str, Any]) -> None:
            events.append(event)
            if event["type"] == "ai_audio_started":
                audio_started.set()

        track = ObservableStreamingOutboundAudioTrack()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=sink,
        )
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-qwen-slow-stream",
                "Hello from a slow native Qwen stream.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
                reference_audio_content_type="audio/wav",
            )
        )
        try:
            assert await asyncio.to_thread(adapter.second_chunk_yielded.wait, 1.0)
            await _wait_for_async_event_or_task(
                audio_started,
                speech,
                label="Qwen first playback before producer completion",
            )
            assert not adapter.stream_completed.is_set()
            assert track.chunks
            assert not speech.done()
            adapter.release_completion.set()
            return await speech, track
        finally:
            adapter.release_completion.set()
            if not speech.done():
                speech.cancel()

    event, track = _run(scenario())

    assert event["type"] == "ai_done"
    assert [item["type"] for item in events] == ["ai_audio_started", "ai_done"]
    assert event["ai_audio_started_event"]["tts_playback"]["streaming_used"] is True
    assert "total_generation_ms" not in event["ai_audio_started_event"]["tts_playback"]
    assert event["tts_playback_final"]["bridge_queue_capacity"] == 2
    assert event["tts_playback_final"]["bridge_queue_high_water"] <= 2
    assert event["ai_audio_started_event"]["tts_playback"]["startup_buffered_chunks"] == 2
    assert event["ai_audio_started_event"]["tts_playback"]["startup_buffered_audio_ms"] == 640.0
    assert event["ai_audio_started_event"]["tts_playback"]["startup_buffer_target_ms"] == 600.0
    assert track.preroll_seconds == [0.0, 0.0, 0.0]
    assert adapter.requests[0]["request_id"].startswith("tts-segment-")
    assert adapter.requests[0]["request"].turn_id == "ai-turn-qwen-slow-stream"
    assert adapter.requests[0]["voice_key"] == "voice-qwen"


def test_qwen_capacity_two_bridge_blocks_producer_without_dropping_chunks(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS", 0.0)

    async def scenario() -> dict[str, Any]:
        track = BlockingFirstEnqueueTrack()
        adapter = BackpressureQwenStreamingTtsAdapter()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
        )
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-qwen-backpressure",
                "This stream must stay bounded while playout is held.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        try:
            await _wait_for_async_event_or_task(
                track.first_enqueue_entered,
                speech,
                label="Qwen first enqueue enters slow playout",
            )
            assert await asyncio.to_thread(adapter.fourth_yield_attempted.wait, 1.0)
            await asyncio.sleep(0.05)
            assert adapter.completed_yields == 3
            assert not adapter.stream_completed.is_set()
            track.release_first_enqueue.set()
            return await speech
        finally:
            track.release_first_enqueue.set()
            if not speech.done():
                speech.cancel()

    event = _run(scenario())

    assert event["type"] == "ai_done"
    final = event["tts_playback_final"]
    assert final["track_metrics_present"] is False
    assert final["bridge_queue_capacity"] == 2
    assert final["bridge_queue_high_water"] == 2
    assert final["producer_block_time_ms"] > 0
    assert final["chunk_count"] == 6


def test_qwen_fast_producer_is_bounded_by_paced_track_consumption(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_TTS_AUDIO_PREROLL_SECONDS", 0.0)
    events: list[dict[str, Any]] = []
    stream_completed_at_start: list[bool] = []

    async def scenario() -> tuple[dict[str, Any], QueuedAudioOutputTrack, list[int]]:
        track = QueuedAudioOutputTrack(
            sample_rate=48000,
            frame_ms=20,
            max_pending_audio_seconds=0.24,
        )
        adapter = BackpressureQwenStreamingTtsAdapter()
        played_peaks: list[int] = []

        def sink(event: dict[str, Any]) -> None:
            events.append(event)
            if event["type"] == "ai_audio_started":
                stream_completed_at_start.append(adapter.stream_completed.is_set())

        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=sink,
        )
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-qwen-paced-credit",
                "Fast generation must stay bounded by real paced playout.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )

        async def consume() -> None:
            while not speech.done() or track.pending_samples > 0:
                frame = await track.recv()
                played_peaks.append(int(np.max(np.abs(frame.to_ndarray()))))

        consumer = asyncio.create_task(consume())
        try:
            result = await asyncio.wait_for(speech, timeout=5.0)
            await asyncio.wait_for(consumer, timeout=1.0)
            return result, track, played_peaks
        finally:
            if not consumer.done():
                consumer.cancel()

    event, track, played_peaks = _run(scenario())

    assert event["type"] == "ai_done"
    assert stream_completed_at_start == [False]
    assert any(peak > 0 for peak in played_peaks)
    immediate = event["ai_audio_started_event"]["tts_playback"]
    assert "total_generation_ms" not in immediate
    assert "total_playback_ms" not in immediate
    assert "generation_complete_ms" not in immediate
    assert "playout_complete_ms" not in immediate
    assert "track_pending_audio_high_water_ms" not in immediate
    final = event["tts_playback_final"]
    assert final["track_metrics_present"] is True
    assert final["bridge_queue_capacity"] == 2
    assert final["bridge_queue_high_water"] <= 2
    assert final["bridge_producer_block_count"] > 0
    assert final["track_admission_capacity_ms"] == 240.0
    assert final["track_pending_audio_high_water_ms"] <= 240.0
    assert final["track_admission_block_count"] > 0
    assert final["track_admission_block_time_ms"] > 0
    assert final["track_underflow_frames"] == 0
    assert final["track_order_violation_count"] == 0
    assert final["track_discarded_samples"] == 0
    assert final["track_playout_debt_ms"] == 0.0
    assert final["playout_wait_completed"] is True
    assert final["playout_complete_ms"] >= final["generation_complete_ms"]
    assert final["native_generation_ms"] == 325.0
    assert final["realtime_generation_ratio"] == pytest.approx(720.0 / 325.0, abs=0.001)
    assert track.pending_samples == 0


def test_queued_audio_output_track_credit_wakes_and_discards_on_stop() -> None:
    async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
        track = QueuedAudioOutputTrack(
            sample_rate=16000,
            frame_ms=20,
            max_pending_audio_seconds=0.04,
        )
        samples = np.full(3200, 0.25, dtype=np.float32)
        buffer = BytesIO()
        sf.write(buffer, samples, 16000, format="WAV")

        enqueue = asyncio.create_task(track.enqueue(buffer.getvalue()))
        await asyncio.sleep(0)
        assert track.pending_samples <= 640
        assert not enqueue.done()
        before = track.playout_metrics()
        await track.stop_current()
        await asyncio.wait_for(enqueue, timeout=0.5)
        after = track.playout_metrics()
        return before, after

    before, after = _run(scenario())

    assert before["pending_samples"] <= before["admission_capacity_samples"]
    assert before["admission_block_count"] > 0
    assert after["pending_samples"] == 0
    assert after["playout_debt_ms"] == 0.0
    assert after["discarded_samples"] > 0
    assert after["discarded_chunks"] > 0


@pytest.mark.parametrize("yield_before_cancel", [False, True])
@pytest.mark.parametrize("termination", ["interrupt", "hangup"])
def test_qwen_termination_cancels_exact_request_and_rejects_normal_completion(
    monkeypatch: Any,
    yield_before_cancel: bool,
    termination: str,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    events: list[dict[str, Any]] = []

    async def scenario() -> tuple[ObservableStreamingOutboundAudioTrack, str]:
        track = ObservableStreamingOutboundAudioTrack()
        adapter = CancellableQwenStreamingTtsAdapter(
            yield_before_cancel=yield_before_cancel
        )
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
        )
        turn_id = (
            f"ai-turn-qwen-{termination}-after"
            if yield_before_cancel
            else f"ai-turn-qwen-{termination}-before"
        )
        speech = asyncio.create_task(
            session.speak_text(
                turn_id,
                "This Qwen speech must stop immediately.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        try:
            assert await asyncio.to_thread(adapter.stream_started.wait, 1.0)
            if yield_before_cancel:
                await _wait_for_async_event_or_task(
                    track.first_chunk_enqueued,
                    speech,
                    label="Qwen first audio before interruption",
                )
            if termination == "interrupt":
                await session.interrupt()
            else:
                await session.end(reason="hangup")
            try:
                await speech
            except asyncio.CancelledError:
                pass
                assert len(adapter.cancel_calls) == 1
                assert adapter.cancel_calls[0].startswith("tts-segment-")
            assert adapter.synthesize_calls == 0
            assert session.state == (
                "listening" if termination == "interrupt" else "ended"
            )
            return track, turn_id
        finally:
            adapter.release_stream.set()
            if not speech.done():
                speech.cancel()

    track, _turn_id = _run(scenario())

    assert len(track.chunks) == (1 if yield_before_cancel else 0)
    assert track.stop_calls == 1
    assert "ai_done" not in [item["type"] for item in events]
    assert [item["type"] for item in events][-1] == (
        "interrupted" if termination == "interrupt" else "ended"
    )


def test_qwen_cancel_preserves_adapter_ownership_until_terminal_then_recovers(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    events: list[dict[str, Any]] = []

    class OwnershipRaceAdapter:
        engine_id = "qwen3_1_7b"

        def __init__(self) -> None:
            self.session: CallSession | None = None
            self.requests = 0
            self.active_request_id: str | None = None
            self.first_chunk_yielded = threading.Event()
            self.release_generation = threading.Event()
            self.matching_terminal_consumed = threading.Event()
            self.cancel_calls: list[str] = []
            self.cancel_observed_published_flag: bool | None = None
            self.synthesize_calls = 0

        def synthesize(self, _payload: Any) -> dict[str, Any]:
            self.synthesize_calls += 1
            raise AssertionError("whole synthesis fallback was used")

        def stream(
            self,
            request: Any,
            *,
            request_id: str,
            voice_key: str,
        ) -> Any:
            del request, voice_key
            self.requests += 1
            self.active_request_id = request_id
            try:
                yield TtsAudioChunk(
                    engine_id=self.engine_id,
                    chunk_index=0,
                    wav_bytes=SCRIPTED_WAV_BYTES,
                    sample_rate=24000,
                    duration_ms=120,
                    generated_at_ms=25.0,
                )
                self.first_chunk_yielded.set()
                if self.requests == 1:
                    self.release_generation.wait()
            finally:
                self.active_request_id = None
                self.matching_terminal_consumed.set()

        def cancel(self, request_id: str) -> bool:
            assert self.session is not None
            self.cancel_calls.append(request_id)
            self.cancel_observed_published_flag = (
                request_id in self.session._cancelled_ai_turns
            )
            if self.active_request_id != request_id:
                return False
            self.release_generation.set()
            return self.matching_terminal_consumed.wait(timeout=1.0)

    async def scenario() -> tuple[OwnershipRaceAdapter, dict[str, Any]]:
        track = ObservableStreamingOutboundAudioTrack()
        adapter = OwnershipRaceAdapter()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
        )
        adapter.session = session
        interrupted_turn = "turn-qwen-ownership-race"
        speech = asyncio.create_task(
            session.speak_text(
                interrupted_turn,
                "Start early, then cancel the owned worker request.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        await _wait_for_async_event_or_task(
            track.first_chunk_enqueued,
            speech,
            label="Qwen first playback before ownership cancellation",
        )
        await session.interrupt()
        try:
            await speech
        except asyncio.CancelledError:
            pass

        recovery = await session.speak_text(
            "turn-qwen-ownership-recovery",
            "A subsequent native stream succeeds.",
            "voice-qwen",
            "qwen3_1_7b",
            final_chunk=True,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="The exact reference transcript.",
        )
        return adapter, recovery

    adapter, recovery = _run(scenario())

    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].startswith("tts-segment-")
    assert adapter.cancel_observed_published_flag is False
    assert adapter.matching_terminal_consumed.is_set()
    assert adapter.active_request_id is None
    assert adapter.synthesize_calls == 0
    assert recovery["type"] == "ai_done"
    assert not any(
        event.get("type") == "ai_done"
        and event.get("turn_id") == "turn-qwen-ownership-race"
        for event in events
    )


def test_qwen_spoken_vad_barge_in_preserves_mic_turn_and_silences_real_playout(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_TTS_AUDIO_PREROLL_SECONDS", 0.0)
    events: list[dict[str, Any]] = []

    class EnergySileroVadAdapter:
        def __init__(self) -> None:
            self.sampling_rate = 16000
            self.threshold = 0.5
            self.calls: list[int] = []

        def speech_timestamps(self, audio: Any) -> list[dict[str, int]]:
            samples = np.asarray(audio, dtype=np.float32)
            self.calls.append(len(samples))
            speech = np.flatnonzero(np.abs(samples) >= (1000 / np.iinfo(np.int16).max))
            if not speech.size:
                return []
            return [{"start": int(speech[0]), "end": int(speech[-1]) + 1}]

    class DelayedCancelAckAdapter:
        engine_id = "qwen3_1_7b"

        def __init__(self, track: QueuedAudioOutputTrack) -> None:
            self.track = track
            self.requests = 0
            self.active_request_id: str | None = None
            self.cancel_started = threading.Event()
            self.release_cancel_ack = threading.Event()
            self.release_first_stream = threading.Event()
            self.first_stream_drained = threading.Event()
            self.cancel_calls: list[str] = []
            self.synthesize_calls = 0

        def synthesize(self, _payload: Any) -> dict[str, Any]:
            self.synthesize_calls += 1
            raise AssertionError("whole synthesis fallback was used")

        def stream(
            self,
            request: Any,
            *,
            request_id: str,
            voice_key: str,
        ) -> Any:
            del request, voice_key
            self.requests += 1
            self.active_request_id = request_id
            try:
                yield TtsAudioChunk(
                    engine_id=self.engine_id,
                    chunk_index=0,
                    wav_bytes=QWEN_STREAM_CHUNK_WAV_BYTES,
                    sample_rate=24000,
                    duration_ms=320,
                    generated_at_ms=25.0,
                )
                if self.requests == 1:
                    self.release_first_stream.wait()
            finally:
                self.active_request_id = None
                if self.requests == 1:
                    self.first_stream_drained.set()

        def cancel(self, request_id: str) -> bool:
            self.cancel_calls.append(request_id)
            assert self.active_request_id == request_id
            self.cancel_started.set()
            self.release_first_stream.set()
            assert self.release_cancel_ack.wait(timeout=1.0)
            return self.first_stream_drained.wait(timeout=1.0)

    async def scenario() -> tuple[
        DelayedCancelAckAdapter,
        dict[str, Any],
        np.ndarray,
        dict[str, Any],
        ScriptedSttAdapter,
    ]:
        track = QueuedAudioOutputTrack(
            sample_rate=16000,
            frame_ms=20,
            max_pending_audio_seconds=0.5,
        )
        adapter = DelayedCancelAckAdapter(track)
        vad = EnergySileroVadAdapter()
        stt = ScriptedSttAdapter()
        session, _ = _new_session(
            vad_adapter=vad,
            stt_adapter=stt,
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
            settings=AiBackendSettings(call_vad_end_silence_ms=500),
        )
        interrupted_turn = "turn-qwen-delayed-cancel"
        speech = asyncio.create_task(
            session.speak_text(
                interrupted_turn,
                "Queued speech must become silent before cancellation acknowledgement.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        barge_in: asyncio.Task[Any] | None = None
        try:
            while track.pending_samples == 0:
                if speech.done():
                    await speech
                await asyncio.sleep(0)
            first_frame = await track.recv()
            assert np.max(np.abs(first_frame.to_ndarray())) > 0
            assert track.pending_samples > 0

            low_pcm = np.full(320, 80, dtype=np.int16).tobytes()
            transient_pcm = np.full(320, 8000, dtype=np.int16).tobytes()
            user_pcm = np.full(320, 4000, dtype=np.int16).tobytes()
            silence_pcm = np.zeros(320, dtype=np.int16).tobytes()

            # Residual room noise stays bounded, and one loud transient cannot
            # self-barge or leak into the confirmed user onset.
            noise_frame_count = (
                session_module.CALL_BARGE_IN_MAX_ONSET_BUFFER_MS // 20
            ) + 5
            for _ in range(noise_frame_count):
                assert await session.handle_inbound_audio_frame(
                    ScriptedInboundAudioFrame(low_pcm)
                ) is None
            assert (
                session._barge_in_buffered_ms
                <= session_module.CALL_BARGE_IN_MAX_ONSET_BUFFER_MS
            )
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(transient_pcm)
            ) is None
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(low_pcm)
            ) is None
            assert adapter.cancel_calls == []
            assert session.state == "speaking"

            onset_frame_count = (
                session_module.CALL_BARGE_IN_MIN_SPEECH_MS + 19
            ) // 20
            for _ in range(onset_frame_count - 1):
                assert await session.handle_inbound_audio_frame(
                    ScriptedInboundAudioFrame(user_pcm)
                ) is None
                assert adapter.cancel_calls == []

            # The final real PCM frame confirms the production VAD onset. The
            # handler itself invokes interrupt; the test never does so directly.
            assert track.pending_samples > 0
            barge_in = asyncio.create_task(
                session.handle_inbound_audio_frame(
                    ScriptedInboundAudioFrame(user_pcm)
                )
            )
            assert await asyncio.to_thread(adapter.cancel_started.wait, 1.0)
            while track.pending_samples > 0:
                await asyncio.sleep(0)
            assert not barge_in.done()

            # Mic frames delivered while the worker acknowledgement is delayed
            # remain part of the interrupted user's utterance.
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(user_pcm)
            ) is None
            silent_during_ack_delay = await track.recv()
            assert np.max(np.abs(silent_during_ack_delay.to_ndarray())) == 0
            assert track.pending_samples == 0

            # The speech task is allowed to settle and clear its active fields
            # before the worker acknowledges cancellation. The request-scoped
            # metrics callback captured by cancel_ai_turn must remain usable.
            await asyncio.wait_for(asyncio.shield(speech), timeout=1.0)
            assert speech.done()
            assert not barge_in.done()
            assert session._active_tts_metrics_snapshot is None

            adapter.release_cancel_ack.set()
            interrupted = await asyncio.wait_for(barge_in, timeout=1.0)
            assert interrupted["type"] == "interrupted"
            assert interrupted["control_cause"] == "vad_barge_in"
            playback_final = interrupted["tts_playback_final"]
            assert playback_final["track_metrics_present"] is True
            assert playback_final["track_admission_capacity_samples"] > 0
            assert playback_final["track_pending_samples"] == 0
            assert playback_final["track_pending_audio_ms"] == 0.0
            assert adapter.first_stream_drained.is_set()
            assert session._active_tts_adapter is None
            assert session._active_tts_request_id is None
            assert session.state == "listening"

            user_final = None
            for _ in range(25):
                user_final = await session.handle_inbound_audio_frame(
                    ScriptedInboundAudioFrame(silence_pcm)
                )
            assert user_final is not None
            assert user_final["type"] == "user_final"
            assert user_final["text"] == "hello from mic"
            assert stt.calls
            assert transient_pcm not in stt.calls[0]
            assert stt.calls[0].count(user_pcm) >= onset_frame_count + 1

            recovery_speech = asyncio.create_task(
                session.speak_text(
                    "turn-qwen-after-delayed-cancel",
                    "The next native streaming turn recovers normally.",
                    "voice-qwen",
                    "qwen3_1_7b",
                    final_chunk=True,
                    reference_audio_b64="cmVhbC1zYW1wbGU=",
                    reference_transcript="The exact reference transcript.",
                )
            )
            recovery_peaks: list[int] = []
            while not recovery_speech.done() or track.pending_samples > 0:
                frame = await track.recv()
                recovery_peaks.append(int(np.max(np.abs(frame.to_ndarray()))))
            recovery = await recovery_speech
            assert any(peak > 0 for peak in recovery_peaks)
            return (
                adapter,
                recovery,
                silent_during_ack_delay.to_ndarray(),
                user_final,
                stt,
            )
        finally:
            adapter.release_cancel_ack.set()
            adapter.release_first_stream.set()
            if barge_in is not None and not barge_in.done():
                barge_in.cancel()
            if not speech.done():
                speech.cancel()

    adapter, recovery, silence, user_final, stt = _run(scenario())

    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].startswith("tts-segment-")
    assert adapter.synthesize_calls == 0
    assert recovery["type"] == "ai_done"
    assert user_final["type"] == "user_final"
    assert stt.calls
    assert np.max(np.abs(silence)) == 0
    assert not any(
        event.get("type") == "ai_done"
        and event.get("turn_id") == "turn-qwen-delayed-cancel"
        for event in events
    )


@pytest.mark.parametrize(
    ("control_cause", "expected_state", "expected_terminal"),
    [
        ("button_interrupt", "listening", "interrupted"),
        ("vad_barge_in", "listening", "interrupted"),
        ("hangup", "ended", "ended"),
        ("engine_switch", "listening", None),
        ("connection_failure", "failed", "failed"),
        ("session_close", "ended", "ended"),
    ],
)
def test_qwen_control_causes_are_request_scoped_terminal_safe_and_recoverable(
    monkeypatch: Any,
    control_cause: str,
    expected_state: str,
    expected_terminal: str | None,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    monkeypatch.setattr(session_module, "CALL_QWEN3_STREAM_START_MIN_AUDIO_SECONDS", 0.0)
    events: list[dict[str, Any]] = []

    async def scenario() -> tuple[
        CancellableQwenStreamingTtsAdapter,
        ObservableStreamingOutboundAudioTrack,
        CallSession,
        dict[str, Any] | None,
        dict[str, Any],
    ]:
        manager = CallSessionManager()
        track = ObservableStreamingOutboundAudioTrack()
        adapter = CancellableQwenStreamingTtsAdapter(yield_before_cancel=True)
        session = await manager.create_session(
            session_id=f"call-{control_cause}",
            voice_id="voice-qwen",
            engine_id="qwen3_1_7b",
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
        )
        turn_id = f"turn-{control_cause}"
        speech = asyncio.create_task(
            session.speak_text(
                turn_id,
                "This active Qwen request must stop at the matching control.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
        )
        terminal: dict[str, Any] | None = None
        try:
            await _wait_for_async_event_or_task(
                track.first_chunk_enqueued,
                speech,
                label=f"Qwen audio before {control_cause}",
            )
            if control_cause in {"button_interrupt", "vad_barge_in"}:
                terminal = await session.interrupt(cause=control_cause)
            elif control_cause == "hangup":
                terminal = await session.end(reason="hangup")
            elif control_cause == "engine_switch":
                await session.update_call_selection(
                    voice_id="voice-f5",
                    engine_id="f5",
                )
            elif control_cause == "connection_failure":
                terminal = await session.fail(reason="connection_failed")
            else:
                await manager.remove_session(session.session_id)
                terminal = events[-1]

            try:
                await speech
            except asyncio.CancelledError:
                pass

            recovery_adapter = SlowQwenStreamingTtsAdapter(chunk_count=2)
            recovery_adapter.release_completion.set()
            recovery_track = ObservableStreamingOutboundAudioTrack()
            recovery_session = await manager.create_session(
                session_id=f"recovery-{control_cause}",
                voice_id="voice-qwen",
                engine_id="qwen3_1_7b",
                tts_adapter=recovery_adapter,
                outbound_audio_track=recovery_track,
            )
            recovery = await recovery_session.speak_text(
                f"recovery-turn-{control_cause}",
                "A clean later call still succeeds.",
                "voice-qwen",
                "qwen3_1_7b",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="The exact reference transcript.",
            )
            return adapter, track, session, terminal, recovery
        finally:
            adapter.release_stream.set()
            if not speech.done():
                speech.cancel()

    adapter, track, session, terminal, recovery = _run(scenario())

    turn_id = f"turn-{control_cause}"
    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].startswith("tts-segment-")
    assert adapter.synthesize_calls == 0
    assert track.stop_calls == 1
    assert session.state == expected_state
    assert recovery["type"] == "ai_done"
    assert "ai_done" not in [item["type"] for item in events]
    if expected_terminal is not None:
        assert terminal is not None
        assert terminal["type"] == expected_terminal
        assert terminal["control_cause"] == control_cause
        assert terminal["cancelled_turn_id"] == turn_id
        assert terminal["cancelled_request_id"] == adapter.cancel_calls[0]
        final = terminal["tts_playback_final"]
        assert final["natural_eos"] is False
        assert final["track_metrics_present"] is False
        assert "track_discarded_samples" not in final


def test_cancelled_turn_rejects_late_audio_and_normal_terminal_events() -> None:
    events: list[dict[str, Any]] = []
    session, _ = _new_session(event_sink=events.append)
    session._cancelled_ai_turns.add("cancelled-turn")

    audio = _run(
        session.emit_event(
            {
                "type": "ai_audio_started",
                "session_id": session.session_id,
                "turn_id": "cancelled-turn",
            }
        )
    )
    done = _run(
        session.emit_event(
            {
                "type": "ai_done",
                "session_id": session.session_id,
                "turn_id": "cancelled-turn",
            }
        )
    )

    assert audio == {"status": "discarded", "turn_id": "cancelled-turn"}
    assert done == {"status": "discarded", "turn_id": "cancelled-turn"}
    assert events == []


def test_voxcpm2_streaming_speak_returns_one_done_event_for_final_turn() -> None:
    events: list[dict[str, Any]] = []

    async def scenario() -> tuple[dict[str, Any], ObservableStreamingOutboundAudioTrack]:
        track = ObservableStreamingOutboundAudioTrack()
        adapter = ScriptedStreamingTtsAdapter()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
        )
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-voxcpm2-stream-done",
                "Hello from streamed VoxCPM2.",
                "voice-voxcpm2",
                "voxcpm2",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="Real VoxCPM2 reference text.",
                reference_audio_content_type="audio/wav",
            )
        )
        try:
            adapter.release_second_chunk.set()
            await _wait_for_async_event_or_task(
                track.first_chunk_enqueued,
                speech,
                label="VoxCPM2 first streamed chunk enqueue",
            )
            return await speech, track
        finally:
            adapter.release_second_chunk.set()
            if not speech.done():
                speech.cancel()

    event, track = _run(scenario())

    assert [item["type"] for item in events].count("ai_done") == 1
    assert [item["type"] for item in events] == ["ai_audio_started", "ai_done"]
    assert track.chunks == [SCRIPTED_WAV_BYTES, SCRIPTED_WAV_BYTES]
    assert track.preroll_seconds == [CALL_TTS_AUDIO_PREROLL_SECONDS, 0.0]
    assert event["type"] == "ai_done"
    assert event["ai_audio_started_event"]["tts_playback"]["streaming_used"] is True
    assert event["ai_audio_started_event"]["tts_playback"]["chunk_count_at_start"] == 2
    assert "buffered_until_complete" not in event["ai_audio_started_event"]["tts_playback"]
    final_playback = event["tts_playback_final"]
    assert final_playback["streaming_used"] is True
    assert final_playback["fallback_used"] is False
    assert final_playback["whole_wav_fallback_used"] is False
    assert final_playback["chunk_count"] == 2
    assert final_playback["total_generation_ms"] >= 75.0
    assert final_playback["total_playback_ms"] > 0
    assert "realtime_generation_ratio" in final_playback
    assert "under_realtime_generation" in final_playback
    assert final_playback["inter_chunk_gaps_ms"] == [50.0]


def test_interrupt_after_first_voxcpm2_stream_chunk_discards_late_chunks() -> None:
    events: list[dict[str, Any]] = []

    async def scenario() -> ObservableStreamingOutboundAudioTrack:
        track = ObservableStreamingOutboundAudioTrack()
        adapter = ScriptedStreamingTtsAdapter()
        session, _ = _new_session(
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
        )
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-voxcpm2-stream-cancel",
                "This streamed VoxCPM2 speech should stop.",
                "voice-voxcpm2",
                "voxcpm2",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="Real VoxCPM2 reference text.",
                reference_audio_content_type="audio/wav",
            )
        )
        try:
            adapter.release_second_chunk.set()
            await _wait_for_async_event_or_task(
                track.first_chunk_enqueued,
                speech,
                label="VoxCPM2 first streamed chunk enqueue",
            )
            await session.interrupt()
            try:
                await speech
            except asyncio.CancelledError:
                pass
            return track
        finally:
            adapter.release_second_chunk.set()
            if not speech.done():
                speech.cancel()

    track = _run(scenario())

    assert track.chunks == [SCRIPTED_WAV_BYTES, SCRIPTED_WAV_BYTES]
    assert track.preroll_seconds == [CALL_TTS_AUDIO_PREROLL_SECONDS, 0.0]
    assert track.stop_calls == 1
    assert [item["type"] for item in events] == ["ai_audio_started", "interrupted"]
    assert "ai_done" not in [item["type"] for item in events]


def test_queued_audio_output_track_returns_tts_audio_frames() -> None:
    async def scenario() -> Any:
        track = QueuedAudioOutputTrack(sample_rate=16000, frame_ms=20)
        samples = np.full(1600, 0.25, dtype=np.float32)
        buffer = BytesIO()
        sf.write(buffer, samples, 16000, format="WAV")

        await track.enqueue(buffer.getvalue())
        frame = await track.recv()

        return frame

    frame = _run(scenario())

    assert frame.sample_rate == 16000
    assert frame.samples == 320
    assert np.max(np.abs(frame.to_ndarray())) > 0


def test_queued_audio_output_track_preroll_sends_silence_before_tts() -> None:
    async def scenario() -> Any:
        track = QueuedAudioOutputTrack(sample_rate=16000, frame_ms=20)
        samples = np.full(1600, 0.25, dtype=np.float32)
        buffer = BytesIO()
        sf.write(buffer, samples, 16000, format="WAV")

        duration = await track.enqueue(buffer.getvalue(), preroll_seconds=0.04)
        first = await track.recv()
        second = await track.recv()
        third = await track.recv()

        return duration, first, second, third

    duration, first, second, third = _run(scenario())

    assert abs(duration - 0.14) < 0.001
    assert np.max(np.abs(first.to_ndarray())) == 0
    assert np.max(np.abs(second.to_ndarray())) == 0
    assert np.max(np.abs(third.to_ndarray())) > 0


def test_queued_audio_output_track_natural_partial_tail_is_not_underflow() -> None:
    async def scenario() -> dict[str, Any]:
        track = QueuedAudioOutputTrack(sample_rate=16000, frame_ms=20)
        samples = np.full(330, 0.25, dtype=np.float32)
        buffer = BytesIO()
        sf.write(buffer, samples, 16000, format="WAV")

        await track.enqueue(buffer.getvalue())
        track.mark_playout_input_complete()
        await track.recv()
        await track.recv()
        return track.playout_metrics()

    metrics = _run(scenario())

    assert metrics["played_samples"] == 330
    assert metrics["underflow_frames"] == 0


def test_queued_audio_output_track_idle_frames_emit_silent_keepalive() -> None:
    async def scenario() -> Any:
        track = QueuedAudioOutputTrack(sample_rate=16000, frame_ms=20)
        return await track.recv()

    frame = _run(scenario())

    assert frame.sample_rate == 16000
    assert frame.samples == 320
    assert np.max(np.abs(frame.to_ndarray())) == 0


def test_queued_audio_output_track_paces_tts_frames_in_realtime(monkeypatch: Any) -> None:
    now = 1000.0
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return now

    async def fake_sleep(delay: float) -> None:
        nonlocal now
        sleeps.append(delay)
        now += max(delay, 0.0)

    monkeypatch.setattr(tracks_module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(tracks_module.asyncio, "sleep", fake_sleep)

    async def scenario() -> None:
        track = QueuedAudioOutputTrack(sample_rate=16000, frame_ms=20)
        samples = np.full(1600, 0.25, dtype=np.float32)
        buffer = BytesIO()
        sf.write(buffer, samples, 16000, format="WAV")

        await track.enqueue(buffer.getvalue())
        for _ in range(5):
            await track.recv()

    _run(scenario())

    assert len(sleeps) == 4
    assert sum(sleeps) == pytest.approx(0.08, abs=0.005)


def test_default_vad_max_turn_does_not_force_end_at_five_seconds() -> None:
    settings = AiBackendSettings()
    session = CallSession(session_id="vad-default", settings=settings)
    pcm = np.full(320, 2000, dtype=np.int16).tobytes()
    result: dict[str, bool] = {"end_of_turn": False}

    for _ in range(250):
        frame = PcmAudioFrame(pcm=pcm, sample_rate=16000, channels=1)
        session._turn_frames.append(frame)
        result = session._accept_vad_frame(frame)

    assert settings.vad_max_turn_ms > 5000
    assert result["end_of_turn"] is False


def test_default_call_vad_max_turn_allows_continuous_speech_beyond_thirty_seconds() -> None:
    settings = AiBackendSettings()
    vad = ScriptedSileroVadAdapter(sampling_rate=16000)
    session = CallSession(
        session_id="call-vad-long-turn",
        settings=settings,
        vad_adapter=vad,
    )
    pcm = np.full(320, 2000, dtype=np.int16).tobytes()
    result: dict[str, bool] = {"end_of_turn": False}

    for _ in range(1600):  # 32 seconds at 20 ms/frame.
        frame = PcmAudioFrame(pcm=pcm, sample_rate=16000, channels=1)
        session._turn_frames.append(frame)
        result = session._accept_vad_frame(frame)

    assert settings.call_vad_max_turn_ms > 30000
    assert result["end_of_turn"] is False


def test_silero_vad_analysis_window_stays_bounded_after_five_seconds() -> None:
    settings = AiBackendSettings(vad_end_silence_ms=700, vad_max_turn_ms=30000)
    vad = ScriptedSileroVadAdapter(sampling_rate=16000)
    session = CallSession(session_id="vad-window", settings=settings, vad_adapter=vad)
    pcm = np.full(320, 2000, dtype=np.int16).tobytes()

    for _ in range(300):  # 6 seconds at 20 ms/frame.
        frame = PcmAudioFrame(pcm=pcm, sample_rate=16000, channels=1)
        session._turn_frames.append(frame)
        result = session._accept_vad_frame(frame)
        assert result["end_of_turn"] is False

    assert len(session._turn_frames) == 300, "STT still needs the full turn buffer"
    assert vad.calls
    assert max(vad.calls) <= 16000 * 3


def test_speak_text_generic_adapter_uses_real_reference_audio() -> None:
    adapter = ScriptedGenericTtsAdapter()
    session, _ = _new_session(tts_adapter=adapter)

    _run(
        session.speak_text(
            "ai-turn-reference",
            "Hello from AI.",
            "voice-1",
            "f5",
            final_chunk=True,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="Real reference text.",
            reference_audio_content_type="audio/wav",
        )
    )

    assert adapter.reference_audio == b"real-sample"


def test_speak_text_generic_adapter_passes_voxcpm2_options() -> None:
    adapter = ScriptedGenericTtsAdapter()
    session, _ = _new_session(tts_adapter=adapter)

    _run(
        session.speak_text(
            "ai-turn-voxcpm2-options",
            "Hello from VoxCPM2.",
            "voice-voxcpm2",
            "voxcpm2",
            final_chunk=True,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
            reference_transcript="Real VoxCPM2 reference text.",
            reference_audio_content_type="audio/wav",
            voxcpm2_cloning_mode="transcript_guided",
            voxcpm2_style_prompt="warm phone call voice",
            voxcpm2_cfg_value=2.4,
            voxcpm2_inference_timesteps=12,
            voxcpm2_normalize=True,
            voxcpm2_denoise=False,
        )
    )

    assert adapter.payload is not None
    assert adapter.payload.voxcpm2_cloning_mode == "transcript_guided"
    assert adapter.payload.voxcpm2_style_prompt == "warm phone call voice"
    assert adapter.payload.voxcpm2_cfg_value == 2.4
    assert adapter.payload.voxcpm2_inference_timesteps == 12
    assert adapter.payload.voxcpm2_normalize is True
    assert adapter.payload.voxcpm2_denoise is False


def test_interrupt_cancels_active_speech_before_ai_done() -> None:
    events: list[dict[str, Any]] = []
    track = ScriptedOutboundAudioTrack()
    adapter = ScriptedTtsAdapter(delay=1)
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
        event_sink=events.append,
    )

    async def scenario() -> None:
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-cancel",
                "This should stop.",
                "voice-1",
                "f5",
                final_chunk=True,
            )
        )
        await asyncio.sleep(0)
        await session.interrupt()
        try:
            await speech
        except asyncio.CancelledError:
            pass

    _run(scenario())

    assert track.chunks == []
    assert track.stop_calls == 1
    assert "ai_audio_started" not in [item["type"] for item in events]
    assert "ai_done" not in [item["type"] for item in events]


def test_interrupt_cancels_voxcpm2_active_speech_before_ai_done() -> None:
    events: list[dict[str, Any]] = []
    track = ScriptedOutboundAudioTrack()
    adapter = ScriptedTtsAdapter(delay=1)
    session, _ = _new_session(
        tts_adapter=adapter,
        outbound_audio_track=track,
        event_sink=events.append,
    )

    async def scenario() -> None:
        speech = asyncio.create_task(
            session.speak_text(
                "ai-turn-voxcpm2-cancel",
                "This VoxCPM2 speech should stop.",
                "voice-voxcpm2",
                "voxcpm2",
                final_chunk=True,
            )
        )
        await asyncio.sleep(0)
        await session.interrupt()
        try:
            await speech
        except asyncio.CancelledError:
            pass

    _run(scenario())

    assert track.chunks == []
    assert track.stop_calls == 1
    assert [item["type"] for item in events] == ["interrupted"]
    assert "ai_audio_started" not in [item["type"] for item in events]
    assert "ai_done" not in [item["type"] for item in events]


def test_end_closes_peer_once() -> None:
    session, peer = _new_session()

    first_event = _run(session.end(reason="hangup"))
    second_event = _run(session.end(reason="hangup"))

    assert peer.close_calls == 1
    assert first_event["reason"] == "hangup"
    assert second_event["reason"] == "hangup"
    assert session.state == "ended"
    assert session.end_reason == "hangup"


@pytest.mark.parametrize(
    "failed_step",
    ["cancel", "active_peer", "candidate_peer", "prompt_lease"],
)
def test_terminal_cleanup_ledger_retries_only_failed_resources(
    failed_step: str,
) -> None:
    class FailOncePeer(ScriptedPeerConnection):
        def __init__(self, step: str) -> None:
            super().__init__()
            self.step = step
            self.successful_closes = 0

        async def close(self) -> None:
            self.close_calls += 1
            if failed_step == self.step and self.close_calls == 1:
                raise RuntimeError(f"injected {self.step} close failure")
            self.successful_closes += 1

    class CleanupSession(CallSession):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.cancel_attempts = 0
            self.cancel_successes = 0

        async def cancel_ai_turn(
            self,
            turn_id: str | None = None,
            *,
            cause: str = "interrupt",
        ) -> dict[str, Any]:
            del turn_id
            self.cancel_attempts += 1
            if failed_step == "cancel" and self.cancel_attempts == 1:
                raise RuntimeError("injected cancellation failure")
            self.cancel_successes += 1
            self.active_turn_task = None
            return {"control_cause": cause}

    active_peer = FailOncePeer("active_peer")
    candidate_peer = FailOncePeer("candidate_peer")
    prompt_attempts = 0
    prompt_successes = 0

    async def release_prompt(_owner: str) -> bool:
        nonlocal prompt_attempts, prompt_successes
        prompt_attempts += 1
        if failed_step == "prompt_lease" and prompt_attempts == 1:
            raise RuntimeError("injected prompt release failure")
        prompt_successes += 1
        return True

    async def scenario() -> CleanupSession:
        session = CleanupSession(
            session_id=f"terminal-cleanup-{failed_step}",
            peer_connection=active_peer,
        )
        session.active_turn_task = object()
        await session.install_or_release_tts_prompt_lease(release_prompt)
        await session.mark_peer_connection_pending(
            candidate_peer,
            timeout_seconds=60.0,
        )

        await session.end(reason="hangup")

        # Later cleanup steps still run even when an earlier owner raises.
        if failed_step != "candidate_peer":
            assert candidate_peer.successful_closes == 1
        if failed_step != "prompt_lease":
            assert prompt_successes == 1

        await session.end(reason="hangup")
        return session

    session = _run(scenario())

    assert session.cancel_successes == 1
    assert active_peer.successful_closes == 1
    assert candidate_peer.successful_closes == 1
    assert prompt_successes == 1
    assert session.cancel_attempts == (2 if failed_step == "cancel" else 1)
    assert active_peer.close_calls == (2 if failed_step == "active_peer" else 1)
    assert candidate_peer.close_calls == (2 if failed_step == "candidate_peer" else 1)
    assert prompt_attempts == (2 if failed_step == "prompt_lease" else 1)


@pytest.mark.parametrize("first_terminal", ["end", "fail"])
def test_terminal_race_emits_only_the_winning_outcome(first_terminal: str) -> None:
    events: list[dict[str, Any]] = []
    session, peer = _new_session(event_sink=events.append)

    async def scenario() -> list[dict[str, Any]]:
        await session._lifecycle_lock.acquire()
        try:
            if first_terminal == "end":
                first = asyncio.create_task(session.end(reason="hangup"))
                await asyncio.sleep(0)
                second = asyncio.create_task(session.fail(reason="connection_failed"))
            else:
                first = asyncio.create_task(session.fail(reason="connection_failed"))
                await asyncio.sleep(0)
                second = asyncio.create_task(session.end(reason="hangup"))
        finally:
            session._lifecycle_lock.release()
        results = list(await asyncio.gather(first, second))
        results.append(await session.end(reason="repeated"))
        results.append(await session.fail(reason="repeated_failure"))
        return results

    results = _run(scenario())
    terminal_events = [
        event for event in events if event["type"] in {"ended", "failed"}
    ]

    assert len(terminal_events) == 1
    expected_type = "ended" if first_terminal == "end" else "failed"
    assert terminal_events[0]["type"] == expected_type
    assert [result["type"] for result in results] == [expected_type] * 4
    assert peer.close_calls == 1
    assert session.state == expected_type


@pytest.mark.parametrize("blocked_step", ["active_peer", "prompt_lease", "event_sink"])
def test_cancelled_terminal_caller_does_not_cancel_shared_transaction(
    blocked_step: str,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    events: list[dict[str, Any]] = []

    class BlockingPeer(ScriptedPeerConnection):
        async def close(self) -> None:
            self.close_calls += 1
            if blocked_step == "active_peer":
                entered.set()
                await release.wait()

    async def release_prompt(_owner: str) -> bool:
        if blocked_step == "prompt_lease":
            entered.set()
            await release.wait()
        return True

    async def event_sink(event: dict[str, Any]) -> None:
        if blocked_step == "event_sink":
            entered.set()
            await release.wait()
        events.append(event)

    async def scenario() -> tuple[dict[str, Any], CallSession, BlockingPeer]:
        peer = BlockingPeer()
        session = CallSession(
            session_id=f"cancelled-terminal-{blocked_step}",
            peer_connection=peer,
            event_sink=event_sink,
        )
        assert await session.install_or_release_tts_prompt_lease(release_prompt)
        first = asyncio.create_task(session.end(reason="hangup"))
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        follower = asyncio.create_task(session.fail(reason="connection_failed"))
        release.set()
        result = await asyncio.wait_for(follower, timeout=1.0)
        assert session._terminal_outcome is not None
        assert session._terminal_outcome.ready.is_set()
        return result, session, peer

    result, session, peer = _run(scenario())

    assert result["type"] == "ended"
    assert [event["type"] for event in events] == ["ended"]
    assert peer.close_calls == 1
    assert session.state == "ended"


def test_failed_connection_records_connection_failed_reason() -> None:
    session, peer = _new_session()
    peer.connectionState = "failed"

    _run(session.handle_connection_state_change())

    assert session.state == "reconnecting"
    assert session.end_reason is None
    assert peer.close_calls == 0

    _run(session.resolve_deferred_connection_state())

    assert session.state == "failed"
    assert session.end_reason == "connection_failed"
    assert peer.close_calls == 1


def test_closed_connection_ends_session_and_releases_prompt_lease() -> None:
    session, peer = _new_session(session_id="call-session-remote-closed")
    released_owners: list[str] = []

    async def scenario() -> None:
        installed = await session.install_or_release_tts_prompt_lease(
            lambda owner: released_owners.append(owner)
        )
        assert installed is True
        peer.connectionState = "closed"
        await session.handle_connection_state_change()

        assert session.state == "reconnecting"
        assert session.end_reason is None
        assert released_owners == []

        await session.resolve_deferred_connection_state()

    _run(scenario())

    assert session.state == "ended"
    assert session.end_reason == "connection_closed"
    assert peer.close_calls == 1
    assert released_owners == ["call-session-remote-closed"]


def test_connected_replacement_keeps_prompt_lease_owned_through_reconnect() -> None:
    session, peer = _new_session(session_id="call-session-reconnect-lease")
    replacement_peer = ScriptedPeerConnection()
    released_owners: list[str] = []

    async def scenario() -> None:
        installed = await session.install_or_release_tts_prompt_lease(
            lambda owner: released_owners.append(owner)
        )
        assert installed is True
        generation = await session.mark_peer_connection_pending(replacement_peer)
        peer.connectionState = "closed"
        await session.handle_connection_state_change()

        assert session.state == "reconnecting"
        assert session.ended_at is None
        assert released_owners == []

        accepted, previous_peer = await session.accept_pending_peer_connection(
            replacement_peer,
            generation=generation,
        )

        assert accepted is True
        assert previous_peer is peer
        assert session.peer_connection is replacement_peer
        assert session.state == "listening"
        assert session.ended_at is None
        assert released_owners == []

        await session.end(reason="hangup")

    _run(scenario())

    assert released_owners == ["call-session-reconnect-lease"]


def test_speech_reservation_rejects_configuration_epoch_changed_by_acceptance() -> None:
    session, _ = _new_session()
    session.voice_id = "voice-before"
    session.engine_id = "f5"
    candidate = ScriptedPeerConnection()

    async def scenario() -> None:
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-before",
            engine_id="f5",
        )
        generation = await session.mark_peer_connection_pending(
            candidate,
            configuration=PeerOfferConfiguration(
                thread_id="thread-after",
                voice_id="voice-after",
                engine_id="voxcpm2",
                prompt_messages=(),
                vad_adapter=None,
                stt_adapter=None,
            ),
            timeout_seconds=60.0,
        )
        accepted, _ = await session.accept_pending_peer_connection(
            candidate,
            generation=generation,
        )
        assert accepted is True

        with pytest.raises(SpeechSessionSelectionError):
            await session.speak_text(
                "turn-stale-selection",
                "This stale selection must never synthesize.",
                "voice-before",
                "f5",
                final_chunk=True,
                accepted_configuration=reservation,
            )

    _run(scenario())


@pytest.mark.parametrize("acceptance_wins", [True, False])
def test_reconnect_acceptance_and_grace_expiry_make_one_atomic_decision(
    acceptance_wins: bool,
) -> None:
    session, active_peer = _new_session(
        session_id=f"reconnect-decision-{acceptance_wins}"
    )
    candidate = ScriptedPeerConnection()

    async def scenario() -> tuple[bool, bool]:
        generation = await session.mark_peer_connection_pending(
            candidate,
            timeout_seconds=60.0,
        )
        active_peer.connectionState = "closed"
        await session.handle_connection_state_change()
        reconnect_epoch = session._peer_lifecycle.epoch

        await session._lifecycle_lock.acquire()
        try:
            if acceptance_wins:
                accept_task = asyncio.create_task(
                    session.accept_pending_peer_connection(
                        candidate,
                        generation=generation,
                    )
                )
                await asyncio.sleep(0)
                resolve_task = asyncio.create_task(
                    session.resolve_deferred_connection_state(
                        epoch=reconnect_epoch,
                        peer_connection=active_peer,
                    )
                )
            else:
                resolve_task = asyncio.create_task(
                    session.resolve_deferred_connection_state(
                        epoch=reconnect_epoch,
                        peer_connection=active_peer,
                    )
                )
                await asyncio.sleep(0)
                accept_task = asyncio.create_task(
                    session.accept_pending_peer_connection(
                        candidate,
                        generation=generation,
                    )
                )
        finally:
            session._lifecycle_lock.release()

        accepted, _ = await accept_task
        resolved = await resolve_task
        return accepted, resolved

    accepted, resolved = _run(scenario())

    assert (accepted, resolved) == (
        (True, False) if acceptance_wins else (False, True)
    )
    if acceptance_wins:
        assert session.peer_connection is candidate
        assert session.state == "listening"
        assert candidate.close_calls == 0
    else:
        assert session.state == "ended"
        assert session.end_reason == "connection_closed"
        assert candidate.close_calls == 1


def test_reconnect_candidate_supersession_is_ordered_and_closes_stale_peer() -> None:
    session, active_peer = _new_session(session_id="call-session-reconnect-order")
    first_candidate = ScriptedPeerConnection()
    second_candidate = ScriptedPeerConnection()

    async def scenario() -> None:
        first_generation = await session.mark_peer_connection_pending(
            first_candidate,
            timeout_seconds=60.0,
        )
        second_generation = await session.mark_peer_connection_pending(
            second_candidate,
            timeout_seconds=60.0,
        )

        assert first_candidate.close_calls == 1
        assert session._pending_peer_connections == [second_candidate]
        assert session.is_peer_connection_pending(
            first_candidate,
            first_generation,
        ) is False

        stale_accepted, stale_previous = await session.accept_pending_peer_connection(
            first_candidate,
            generation=first_generation,
        )
        accepted, previous_peer = await session.accept_pending_peer_connection(
            second_candidate,
            generation=second_generation,
        )

        assert stale_accepted is False
        assert stale_previous is None
        assert accepted is True
        assert previous_peer is active_peer
        assert session.peer_connection is second_candidate

    _run(scenario())


def test_reconnect_candidate_timeout_leaves_terminalization_to_reconnect_grace() -> None:
    session, active_peer = _new_session(session_id="call-session-reconnect-timeout")
    candidate = ScriptedPeerConnection()
    released_owners: list[str] = []

    async def scenario() -> None:
        await session.install_or_release_tts_prompt_lease(
            lambda owner: released_owners.append(owner)
        )
        await session.mark_peer_connection_pending(
            candidate,
            timeout_seconds=0.01,
        )
        active_peer.connectionState = "closed"
        await session.handle_connection_state_change()

        assert session.state == "reconnecting"
        assert released_owners == []

        await asyncio.sleep(0.03)

        assert candidate.close_calls == 1
        assert session._pending_peer_connections == []
        assert session.state == "reconnecting"
        assert session.end_reason is None
        assert released_owners == []

        await session.resolve_deferred_connection_state()

    _run(scenario())

    assert candidate.close_calls == 1
    assert session._pending_peer_connections == []
    assert session.state == "ended"
    assert session.end_reason == "connection_closed"
    assert released_owners == ["call-session-reconnect-timeout"]


def test_old_candidate_rejection_cannot_terminalize_newer_generation() -> None:
    session, active_peer = _new_session(session_id="candidate-reject-generation-race")
    close_started = asyncio.Event()
    allow_close = asyncio.Event()

    class SlowClosingPeer(ScriptedPeerConnection):
        async def close(self) -> None:
            self.close_calls += 1
            close_started.set()
            await allow_close.wait()

    first_candidate = SlowClosingPeer()
    second_candidate = ScriptedPeerConnection()

    async def scenario() -> None:
        first_generation = await session.mark_peer_connection_pending(
            first_candidate,
            timeout_seconds=60.0,
        )
        active_peer.connectionState = "closed"
        await session.handle_connection_state_change()

        rejecting = asyncio.create_task(
            session.reject_pending_peer_connection(
                first_candidate,
                generation=first_generation,
            )
        )
        await close_started.wait()
        second_generation = await session.mark_peer_connection_pending(
            second_candidate,
            timeout_seconds=60.0,
        )
        allow_close.set()
        assert await rejecting is True

        assert session.state == "reconnecting"
        assert session.ended_at is None
        assert session.is_peer_connection_pending(
            second_candidate,
            second_generation,
        )
        assert second_candidate.close_calls == 0

    _run(scenario())


def test_stats_returns_session_state_and_audio_counters() -> None:
    session, _ = _new_session(session_id="call-session-stats")

    _run(session.handle_inbound_audio_frame(b"pcm-frame-1"))
    _run(session.set_muted(True))
    _run(session.handle_inbound_audio_frame(b"pcm-frame-2"))
    stats = session.stats()

    assert stats == {
        "session_id": "call-session-stats",
        "state": session.state,
        "muted": True,
        "incoming_audio_frames": 2,
        "dropped_audio_frames": 1,
        "late_tts_event_discard_count": 0,
    }
