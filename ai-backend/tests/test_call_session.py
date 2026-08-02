from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import threading
import time
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
    TerminalCallSessionError,
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
THREAD_EVENT_RENDEZVOUS_TIMEOUT_SECONDS = 5.0


def _run(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return asyncio.run(value)
    return value


async def _wait_for_thread_event(
    event: threading.Event,
    *,
    label: str,
) -> None:
    ready = await asyncio.to_thread(
        event.wait,
        THREAD_EVENT_RENDEZVOUS_TIMEOUT_SECONDS,
    )
    assert ready, f"timed out waiting for {label}"


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

    muted_event = _run(session.set_muted(True))
    accepted = _run(session.handle_inbound_audio_frame(b"pcm-frame-1"))

    assert session.muted is True
    assert accepted is False
    assert session.stats()["incoming_audio_frames"] == 1
    assert session.stats()["dropped_audio_frames"] == 1
    assert session.stats()["muted"] is True
    assert muted_event["audio_input_epoch"] == 1
    assert muted_event["mute_revision"] == 1
    repeated_event = _run(session.set_muted(True))
    unmuted_event = _run(session.set_muted(False))
    assert repeated_event["audio_input_epoch"] == 1
    assert repeated_event["mute_revision"] == 2
    assert unmuted_event["audio_input_epoch"] == 1
    assert unmuted_event["mute_revision"] == 3


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


def test_mute_is_orthogonal_to_slow_stt_turn_ownership() -> None:
    entered_stt = threading.Event()
    release_stt = threading.Event()
    events: list[dict[str, Any]] = []

    class SlowSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            entered_stt.set()
            release_stt.wait()
            return {
                "status": "accepted",
                "transcript": "mute preserves this turn",
                "language": "en",
            }

    async def scenario() -> None:
        vad = NeverEndingVadAdapter()
        session, _ = _new_session(
            vad_adapter=vad,
            stt_adapter=SlowSttAdapter(),
            event_sink=events.append,
        )
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        finalized = asyncio.create_task(session.finalize_user_turn())
        try:
            await _wait_for_thread_event(entered_stt, label="mute STT admission")
            admission = next(iter(session._stt_admissions.values()))
            assert session.state == "understanding"

            await session.set_muted(True)
            assert session.muted is True
            assert session.state == "understanding"
            assert session._stt_admissions[admission.token] is admission
            dropped_before = session.dropped_audio_frames
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(pcm)
            ) is None
            assert session.dropped_audio_frames == dropped_before + 1
            assert session._turn_frames == []

            await session.set_muted(False)
            assert session.muted is False
            assert session.state == "understanding"
            assert session._stt_admissions[admission.token] is admission
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(pcm)
            ) is None
            assert session.dropped_audio_frames == dropped_before + 2
            assert session._turn_frames == []
            assert len(vad.frames) == 1
        finally:
            release_stt.set()

        result = await asyncio.wait_for(finalized, timeout=1.0)
        assert result is not None and result["type"] == "user_final"
        assert session._stt_admissions == {}
        assert session.state == "thinking"

    _run(scenario())

    assert [event["type"] for event in events] == [
        "state",
        "muted",
        "muted",
        "user_final",
    ]


def test_mute_is_orthogonal_to_active_streaming_tts_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(
        session_module,
        "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS",
        0.0,
    )
    events: list[dict[str, Any]] = []

    async def scenario() -> None:
        adapter = ScriptedStreamingTtsAdapter()
        track = ObservableStreamingOutboundAudioTrack()
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
        )
        turn_id = "turn-streaming-mute"
        speech = asyncio.create_task(
            session.speak_text(
                turn_id,
                "Playback stays live through mute controls.",
                "voice-1",
                "voxcpm2",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="Real VoxCPM2 reference text.",
                reference_audio_content_type="audio/wav",
            )
        )
        try:
            await _wait_for_async_event_or_task(
                track.first_chunk_enqueued,
                speech,
                label="first streaming playback before mute",
            )
            while session.state != "speaking" and not speech.done():
                await asyncio.sleep(0)
            assert session.state == "speaking"
            assert adapter.stream_completed.is_set() is False
            admission = session._speech_admission
            assert admission is not None
            request_id = session._active_tts_request_id
            assert session._active_tts_turn_id == turn_id

            await session.set_muted(True)
            assert session.muted is True
            assert session.state == "speaking"
            assert session._speech_admission is admission
            assert session._active_tts_request_id == request_id
            dropped_before = session.dropped_audio_frames
            pcm = np.full(320, 2200, dtype=np.int16).tobytes()
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(pcm)
            ) is None
            assert session.dropped_audio_frames == dropped_before + 1
            assert session._barge_in_frames == []
            assert session._turn_frames == []

            await session.set_muted(False)
            assert session.muted is False
            assert session.state == "speaking"
            assert session._speech_admission is admission
            assert session._active_tts_request_id == request_id
            silence = np.zeros(320, dtype=np.int16).tobytes()
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(silence)
            ) is None
            assert session._speech_admission is admission
            assert session._active_tts_turn_id == turn_id
            assert session._turn_frames == []
            assert speech.done() is False
        finally:
            adapter.release_second_chunk.set()

        terminal = await asyncio.wait_for(speech, timeout=1.0)
        assert terminal["type"] == "ai_done"
        assert session.state == "listening"
        assert session._speech_admission is None
        assert session._active_tts_turn_id is None

    _run(scenario())

    assert [event["type"] for event in events] == [
        "ai_audio_started",
        "muted",
        "muted",
        "ai_done",
    ]


def test_mute_discards_only_unconfirmed_ordinary_vad_onset() -> None:
    class NoSpeechVadAdapter:
        def accept_audio_frame(self, _pcm: bytes) -> dict[str, bool]:
            return {"speech_detected": False, "end_of_turn": False}

    pcm = np.full(320, 1800, dtype=np.int16).tobytes()
    partial, _ = _new_session(vad_adapter=NoSpeechVadAdapter())
    assert _run(
        partial.handle_inbound_audio_frame(ScriptedInboundAudioFrame(pcm))
    ) is None
    assert len(partial._turn_frames) == 1
    assert partial._speech_seen is False

    _run(partial.set_muted(True))

    assert partial._turn_frames == []
    assert partial._turn_started_at is None
    assert partial._speech_start_frame is None

    confirmed, _ = _new_session()
    confirmed_frame = normalize_inbound_audio_frame(
        ScriptedInboundAudioFrame(pcm)
    )
    confirmed._begin_barge_in_turn(
        [confirmed_frame],
        started_at="2026-08-02T00:00:00Z",
    )
    confirmed_frames = list(confirmed._turn_frames)

    _run(confirmed.set_muted(True))

    assert confirmed._speech_seen is True
    assert confirmed._turn_frames == confirmed_frames
    assert confirmed._turn_started_at == "2026-08-02T00:00:00Z"


@pytest.mark.parametrize(
    ("post_unmute_frames", "expect_interrupt"),
    [
        (1, False),
        (
            (session_module.CALL_BARGE_IN_MIN_SPEECH_MS + 19) // 20,
            True,
        ),
    ],
)
def test_mute_requires_full_fresh_barge_in_onset_after_unmute(
    monkeypatch: pytest.MonkeyPatch,
    post_unmute_frames: int,
    expect_interrupt: bool,
) -> None:
    monkeypatch.setattr(session_module, "CALL_TTS_STREAM_START_MIN_CHUNKS", 1)
    monkeypatch.setattr(
        session_module,
        "CALL_TTS_STREAM_START_MIN_AUDIO_SECONDS",
        0.0,
    )
    events: list[dict[str, Any]] = []

    async def scenario() -> None:
        adapter = ScriptedStreamingTtsAdapter()
        cancel_calls: list[str] = []

        def cancel(request_id: str) -> bool:
            cancel_calls.append(request_id)
            adapter.release_second_chunk.set()
            return True

        adapter.cancel = cancel
        track = ObservableStreamingOutboundAudioTrack()
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            tts_adapter=adapter,
            outbound_audio_track=track,
            event_sink=events.append,
        )
        turn_id = f"turn-mute-onset-{post_unmute_frames}"
        speech = asyncio.create_task(
            session.speak_text(
                turn_id,
                "Mute must split barge-in speech evidence.",
                "voice-1",
                "voxcpm2",
                final_chunk=True,
                reference_audio_b64="cmVhbC1zYW1wbGU=",
                reference_transcript="Real VoxCPM2 reference text.",
                reference_audio_content_type="audio/wav",
            )
        )
        try:
            await _wait_for_async_event_or_task(
                track.first_chunk_enqueued,
                speech,
                label="first streaming playback before barge-in mute",
            )
            while session.state != "speaking" and not speech.done():
                await asyncio.sleep(0)
            assert session.state == "speaking"
            assert adapter.stream_completed.is_set() is False
            admission = session._speech_admission
            request_id = session._active_tts_request_id
            assert admission is not None and request_id is not None

            pre_mute_pcm = np.full(320, 3000, dtype=np.int16).tobytes()
            onset_frame_count = (
                session_module.CALL_BARGE_IN_MIN_SPEECH_MS + 19
            ) // 20
            assert onset_frame_count == 6
            for _ in range(onset_frame_count - 1):
                assert await session.handle_inbound_audio_frame(
                    ScriptedInboundAudioFrame(pre_mute_pcm)
                ) is None
            assert session._barge_in_speech_ms == 100
            assert len(session._barge_in_frames) == 5
            assert cancel_calls == []

            await session.set_muted(True)
            assert session.state == "speaking"
            assert session._barge_in_frames == []
            assert session._barge_in_speech_ms == 0
            assert session._barge_in_speech_start_index is None
            assert session._barge_in_energy_start_index is None
            assert session._speech_admission is admission
            assert session._active_tts_request_id == request_id

            dropped_before = session.dropped_audio_frames
            muted_pcm = np.full(320, 3500, dtype=np.int16).tobytes()
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(muted_pcm)
            ) is None
            assert session.dropped_audio_frames == dropped_before + 1
            assert session._barge_in_frames == []

            await session.set_muted(False)
            fresh_pcm = np.full(320, 4000, dtype=np.int16).tobytes()
            interrupted: dict[str, Any] | None = None
            for frame_index in range(post_unmute_frames):
                result = await session.handle_inbound_audio_frame(
                    ScriptedInboundAudioFrame(fresh_pcm)
                )
                if frame_index < post_unmute_frames - 1:
                    assert result is None
                    assert cancel_calls == []
                else:
                    interrupted = result

            if expect_interrupt:
                assert interrupted is not None
                assert interrupted["type"] == "interrupted"
                assert interrupted["control_cause"] == "vad_barge_in"
                assert len(cancel_calls) == 1
                assert all(
                    frame.pcm == fresh_pcm for frame in session._turn_frames
                )
                assert len(session._turn_frames) == onset_frame_count
            else:
                assert interrupted is None
                assert cancel_calls == []
                assert session.state == "speaking"
                assert session._barge_in_speech_ms == 20
                assert session._speech_admission is admission
                assert session._active_tts_request_id == request_id
        finally:
            adapter.release_second_chunk.set()

        try:
            terminal = await asyncio.wait_for(speech, timeout=1.0)
        except asyncio.CancelledError:
            terminal = None
        if expect_interrupt:
            assert terminal is None or terminal.get("status") == "cancelled"
            assert "ai_done" not in [event["type"] for event in events]
        else:
            assert terminal is not None and terminal["type"] == "ai_done"

    _run(scenario())


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
    # VAD is sampled every 100 ms after its immediate initial decision. Keep a
    # 700-ms false-negative interval so this remains a time-based regression.
    vad = FlakySileroVadAdapter(false_silence_calls=set(range(3, 10)))
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
    # Eight 100-ms VAD decisions model the original 800-ms false-negative gap.
    vad = FlakySileroVadAdapter(false_silence_calls=set(range(2, 10)))
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

    # Replacement-track frames are held until the final backfill batch arrives.
    # Release 600 ms first so final backfill itself cannot finalize the turn.
    for _ in range(30):
        result = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))
        assert not (isinstance(result, dict) and result.get("type") == "user_final")

    assert vad.calls == 1
    assert len(session._reconnect_live_frame_hold_frames) == 30
    released = _run(
        session.backfill_reconnect_audio(
            pcm=b"",
            sample_rate=16000,
            channels=1,
            backfill_id="gap-final-empty-release",
            reason="connection_failed",
            attempt=1,
            final=True,
        )
    )

    assert released["status"] == "empty"
    assert "event" not in released
    assert vad.calls == 7
    assert session._silence_ms == 600
    assert session._reconnect_live_frame_hold_frames == []

    # Calls 8 and 9 carry the false-negative interval beyond the 700-ms end
    # threshold, but active reconnect grace must keep the turn listening.
    for _ in range(10):
        result = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))
        assert not (isinstance(result, dict) and result.get("type") == "user_final")

    assert vad.calls == 9
    assert session._silence_ms == 800
    assert session._in_media_reconnect_grace() is True
    assert stt.calls == []

    # Four frames remain below the next 100-ms analysis boundary. The fifth
    # reaches call 10, where speech resumes and clears accumulated silence.
    for _ in range(4):
        resumed = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))
        assert resumed is None
    assert vad.calls == 9
    assert session._silence_ms == 800

    resumed = _run(session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm)))

    assert resumed is None
    assert vad.calls == 10
    assert stt.calls == []
    assert session.state == "listening"
    assert session._speech_seen is True
    assert session._silence_ms == 0

    # Once grace expires, a fresh 700-ms false-negative interval can finalize.
    # STT must receive every pre-reconnect, held, grace, resumed, and final frame.
    now = 6.0
    vad.false_silence_calls.update(range(11, 18))
    final_event = None
    for _ in range(35):
        final_event = _run(
            session.handle_inbound_audio_frame(ScriptedInboundAudioFrame(speech_pcm))
        )

    assert final_event is not None
    assert final_event["type"] == "user_final"
    assert vad.calls == 17
    assert stt.calls == [[speech_pcm] * 81]


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
        try:
            await _wait_for_thread_event(
                entered_stt,
                label="slow reconnect STT admission",
            )
            await session._begin_transport_reconnect(peer, "failed")
            epoch = session._peer_lifecycle.epoch
            assert await session.resolve_deferred_connection_state(
                epoch=epoch,
                peer_connection=peer,
            ) is False
            assert session.ended_at is None
        finally:
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


@pytest.mark.parametrize("terminal_state", ["ended", "failed"])
def test_explicit_terminal_suppresses_admitted_slow_backfill_user_final(
    terminal_state: str,
) -> None:
    entered_stt = threading.Event()
    release_stt = threading.Event()
    events: list[dict[str, Any]] = []

    class SlowSttAdapter:
        def transcribe(self, **_kwargs: Any) -> dict[str, Any]:
            entered_stt.set()
            assert release_stt.wait(timeout=2.0)
            return {
                "status": "accepted",
                "transcript": "this terminal transcript must be suppressed",
                "language": "en",
            }

    async def scenario() -> None:
        session, _ = _new_session(
            vad_adapter=ScriptedVadAdapter(),
            stt_adapter=SlowSttAdapter(),
            event_sink=events.append,
        )
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
                backfill_id=f"slow-stt-explicit-{terminal_state}",
                final=True,
            )
        )
        await _wait_for_thread_event(
            entered_stt,
            label="explicit terminal backfill STT admission",
        )
        if terminal_state == "ended":
            terminal = await session.end(reason="explicit_hangup")
        else:
            terminal = await session.fail(reason="explicit_failure")

        release_stt.set()
        result = await asyncio.wait_for(backfill_task, timeout=2.0)
        assert result == {
            "status": "terminal",
            "frames": 0,
            "duration_ms": 0,
            "state": terminal_state,
            "reason": (
                "explicit_hangup"
                if terminal_state == "ended"
                else "explicit_failure"
            ),
        }
        assert terminal["type"] == terminal_state
        assert "user_final" not in [event["type"] for event in events]
        assert session.state == terminal_state

    _run(scenario())


@pytest.mark.parametrize("terminal_state", ["ended", "failed"])
@pytest.mark.parametrize("stt_result", ["accepted", "error"])
def test_explicit_terminal_suppresses_every_slow_ordinary_stt_outcome(
    monkeypatch: pytest.MonkeyPatch,
    terminal_state: str,
    stt_result: str,
) -> None:
    entered_stt = threading.Event()
    release_stt = threading.Event()
    events: list[dict[str, Any]] = []
    elapsed_seconds = 0.0
    monkeypatch.setattr(
        session_module.time,
        "perf_counter",
        lambda: elapsed_seconds,
    )

    class SlowOrdinarySttAdapter:
        def transcribe(self, **_kwargs: Any) -> dict[str, Any]:
            entered_stt.set()
            assert release_stt.wait(timeout=2.0)
            if stt_result == "error":
                raise RuntimeError("simulated slow STT failure")
            return {
                "status": "accepted",
                "transcript": "late ordinary transcript",
                "language": "en",
            }

    async def scenario() -> None:
        nonlocal elapsed_seconds
        session, _ = _new_session(
            vad_adapter=ScriptedVadAdapter(),
            stt_adapter=SlowOrdinarySttAdapter(),
            event_sink=events.append,
        )
        first_pcm = np.full(320, 1400, dtype=np.int16).tobytes()
        final_pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(first_pcm)
        ) is None
        finalized = asyncio.create_task(
            session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(final_pcm)
            )
        )
        await _wait_for_thread_event(
            entered_stt,
            label="explicit terminal ordinary STT admission",
        )

        if terminal_state == "ended":
            terminal = await session.end(reason="explicit_hangup")
        else:
            terminal = await session.fail(reason="explicit_failure")
        elapsed_seconds = 31.5
        release_stt.set()
        result = await asyncio.wait_for(finalized, timeout=2.0)

        assert result == {
            "status": "terminal",
            "frames": 0,
            "duration_ms": 0,
            "state": terminal_state,
            "reason": (
                "explicit_hangup"
                if terminal_state == "ended"
                else "explicit_failure"
            ),
        }
        assert terminal["type"] == terminal_state
        assert [event["type"] for event in events] == ["state", terminal_state]
        assert "user_final" not in [event["type"] for event in events]
        assert session._stt_admissions == {}
        assert elapsed_seconds > 30.0

    _run(scenario())


@pytest.mark.parametrize("stt_result", ["accepted", "empty", "error"])
def test_stt_event_commit_orders_async_delivery_before_terminal(
    stt_result: str,
) -> None:
    event_delivery_started = asyncio.Event()
    release_event_delivery = asyncio.Event()
    delivered_types: list[str] = []

    class OutcomeSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            if stt_result == "error":
                raise RuntimeError("simulated transcription failure")
            return {
                "status": "accepted" if stt_result == "accepted" else "empty",
                "transcript": "ordered transcript" if stt_result == "accepted" else "",
                "language": "en",
            }

    async def event_sink(event: dict[str, Any]) -> None:
        if event["type"] in {"user_final", "failed"}:
            event_delivery_started.set()
            await release_event_delivery.wait()
        delivered_types.append(event["type"])

    async def scenario() -> None:
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=OutcomeSttAdapter(),
            event_sink=event_sink,
        )
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        finalized = asyncio.create_task(session.finalize_user_turn())
        await event_delivery_started.wait()

        terminal = asyncio.create_task(session.end(reason="explicit_hangup"))
        while session.ended_at is None:
            await asyncio.sleep(0)
        assert not terminal.done()
        assert delivered_types == ["state"]

        release_event_delivery.set()
        result = await finalized
        ended = await terminal

        expected_stt_event = "user_final" if stt_result == "accepted" else "failed"
        assert result is not None and result["type"] == expected_stt_event
        assert ended["type"] == "ended"
        assert delivered_types == ["state", expected_stt_event, "ended"]
        assert session._event_outbox == []

    _run(scenario())


@pytest.mark.parametrize("stt_result", ["accepted", "empty", "error"])
def test_stt_event_sink_reentrant_session_action_does_not_deadlock(
    stt_result: str,
) -> None:
    delivered: list[tuple[str, str | None]] = []
    reentrant_results: list[dict[str, Any]] = []
    session: CallSession

    class OutcomeSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            if stt_result == "error":
                raise RuntimeError("simulated reentrant STT failure")
            return {
                "status": "accepted" if stt_result == "accepted" else "empty",
                "transcript": "reentrant transcript" if stt_result == "accepted" else "",
                "language": "en",
            }

    async def event_sink(event: dict[str, Any]) -> None:
        delivered.append((event["type"], event.get("code")))
        if stt_result == "accepted" and event["type"] == "user_final":
            reentrant_results.append(
                await session.end(reason="sink_hangup")
            )
        elif (
            stt_result == "empty"
            and event["type"] == "failed"
            and event.get("code") == "call_stt_failed"
        ):
            reentrant_results.append(
                await session.fail(reason="sink_failure")
            )
        elif (
            stt_result == "error"
            and event["type"] == "failed"
            and event.get("code") == "call_stt_failed"
        ):
            reentrant_results.append(
                await session.emit_event(
                    {
                        "type": "sink_followup",
                        "session_id": session.session_id,
                    }
                )
            )

    async def scenario() -> None:
        nonlocal session
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=OutcomeSttAdapter(),
            event_sink=event_sink,
        )
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        result = await asyncio.wait_for(
            session.finalize_user_turn(),
            timeout=2.0,
        )
        assert result is not None
        assert result["type"] == (
            "user_final" if stt_result == "accepted" else "failed"
        )

        if stt_result in {"accepted", "empty"}:
            outcome = session._terminal_outcome
            assert outcome is not None and outcome.transaction_task is not None
            await asyncio.wait_for(outcome.transaction_task, timeout=2.0)
            assert session.state == (
                "ended" if stt_result == "accepted" else "failed"
            )
        else:
            while session._event_outbox:
                await asyncio.sleep(0)
            assert session.state == "listening"

        assert len(reentrant_results) == 1
        if stt_result == "accepted":
            assert reentrant_results[0]["type"] == "ended"
            assert delivered == [
                ("state", None),
                ("user_final", None),
                ("ended", None),
            ]
        elif stt_result == "empty":
            assert reentrant_results[0]["type"] == "failed"
            assert delivered == [
                ("state", None),
                ("failed", "call_stt_failed"),
                ("failed", "sink_failure"),
            ]
        else:
            assert reentrant_results[0]["type"] == "sink_followup"
            assert delivered == [
                ("state", None),
                ("failed", "call_stt_failed"),
                ("sink_followup", None),
            ]

    _run(scenario())


@pytest.mark.parametrize("sink_outcome", ["exception", "cancelled"])
def test_accepted_stt_sink_failure_preserves_authoritative_delivery(
    sink_outcome: str,
) -> None:
    observed_types: list[str] = []
    channel = ScriptedDataChannel()
    track = ScriptedOutboundAudioTrack()

    class AcceptedSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            return {
                "status": "accepted",
                "transcript": "observer failure stays recoverable",
                "language": "en",
            }

    async def event_sink(event: dict[str, Any]) -> None:
        observed_types.append(event["type"])
        if event["type"] != "user_final":
            return
        if sink_outcome == "exception":
            raise RuntimeError("observer is offline")
        raise asyncio.CancelledError("observer callback cancelled")

    async def scenario() -> None:
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=AcceptedSttAdapter(),
            tts_adapter=ScriptedTtsAdapter(),
            outbound_audio_track=track,
            data_channel=channel,
            event_sink=event_sink,
        )
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None

        result = await asyncio.wait_for(
            session.finalize_user_turn(),
            timeout=1.0,
        )

        assert result is not None and result["type"] == "user_final"
        assert session._stt_admissions == {}
        assert session.state == "thinking"
        assert session._event_sink_failures == [
            {
                "event_type": "user_final",
                "error": (
                    "RuntimeError"
                    if sink_outcome == "exception"
                    else "CancelledError"
                ),
            }
        ]
        assert [json.loads(message)["type"] for message in channel.sent] == [
            "state",
            "user_final",
        ]
        assert session.drain_undelivered_events() == []

        # The authoritative recipient can continue the delivered turn even
        # though the optional observer failed.
        terminal = await session.speak_text(
            "ai-turn-after-observer-failure",
            "The call continues.",
            "voice-1",
            "f5",
            final_chunk=True,
        )
        assert terminal["type"] == "ai_done"
        assert session.state == "listening"

    _run(scenario())

    assert observed_types == [
        "state",
        "user_final",
        "ai_audio_started",
        "ai_done",
    ]


def test_failed_authoritative_stt_delivery_releases_thinking_ownership() -> None:
    class AcceptedSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            return {
                "status": "accepted",
                "transcript": "delivery cannot complete",
                "language": "en",
            }

    async def scenario() -> None:
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=AcceptedSttAdapter(),
        )
        deliver = session._deliver_event

        async def fail_user_final(event: dict[str, Any]) -> dict[str, Any]:
            if event["type"] == "user_final":
                raise RuntimeError("authoritative delivery failed")
            return await deliver(event)

        session._deliver_event = fail_user_final
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None

        with pytest.raises(RuntimeError, match="authoritative delivery failed"):
            await session.finalize_user_turn()

        assert session._stt_admissions == {}
        assert session.state == "listening"
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        assert len(session._turn_frames) == 1

    _run(scenario())


@pytest.mark.parametrize("stt_outcome", ["accepted", "empty", "error"])
def test_concurrent_turn_finalizers_share_one_stt_admission_and_outcome(
    stt_outcome: str,
) -> None:
    entered_stt = threading.Event()
    release_stt = threading.Event()
    events: list[dict[str, Any]] = []

    class BlockingSttAdapter:
        def __init__(self) -> None:
            self.calls: list[list[bytes]] = []

        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            self.calls.append(list(pcm_frames))
            entered_stt.set()
            assert release_stt.wait(timeout=2.0)
            if stt_outcome == "error":
                raise RuntimeError("shared transcription failed")
            return {
                "status": stt_outcome,
                "transcript": (
                    "one claimed turn" if stt_outcome == "accepted" else ""
                ),
                "language": "en",
            }

    async def scenario() -> None:
        stt = BlockingSttAdapter()
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=stt,
            event_sink=events.append,
        )
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None

        owner = asyncio.create_task(session.finalize_user_turn())
        await _wait_for_thread_event(
            entered_stt,
            label="shared STT finalization admission",
        )
        joiner = asyncio.create_task(session.finalize_user_turn())
        await asyncio.sleep(0)

        assert len(session._stt_admissions) == 1
        finalization = session._active_stt_finalization
        assert finalization is not None and finalization.task is not None
        assert finalization.admission.task is finalization.task
        assert finalization.task is not owner
        assert finalization.task is not joiner
        assert joiner.done() is False

        release_stt.set()
        owner_result, joined_result = await asyncio.gather(owner, joiner)

        assert joined_result == owner_result
        assert owner_result is not None
        expected_event = (
            "user_final" if stt_outcome == "accepted" else "failed"
        )
        assert owner_result["type"] == expected_event
        assert stt.calls == [[pcm]]
        assert session._stt_admissions == {}
        assert session._active_stt_finalization is None

    _run(scenario())

    expected_event = "user_final" if stt_outcome == "accepted" else "failed"
    assert [event["type"] for event in events] == ["state", expected_event]


@pytest.mark.parametrize("stt_outcome", ["accepted", "empty", "error"])
@pytest.mark.parametrize("cancelled_caller", ["first", "joiner"])
def test_caller_cancellation_cannot_cancel_owned_stt_finalization(
    stt_outcome: str,
    cancelled_caller: str,
) -> None:
    entered_stt = threading.Event()
    release_stt = threading.Event()
    events: list[dict[str, Any]] = []

    class ConcurrentTrackingSttAdapter:
        def __init__(self) -> None:
            self.calls: list[list[bytes]] = []
            self.active_calls = 0
            self.max_concurrent_calls = 0
            self.lock = threading.Lock()

        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            with self.lock:
                self.calls.append(list(pcm_frames))
                call_number = len(self.calls)
                self.active_calls += 1
                self.max_concurrent_calls = max(
                    self.max_concurrent_calls,
                    self.active_calls,
                )
            try:
                if call_number == 1:
                    entered_stt.set()
                    assert release_stt.wait(timeout=2.0)
                if stt_outcome == "error":
                    raise RuntimeError("owned transcription failed")
                return {
                    "status": stt_outcome,
                    "transcript": (
                        "durable shared turn"
                        if stt_outcome == "accepted"
                        else ""
                    ),
                    "language": "en",
                }
            finally:
                with self.lock:
                    self.active_calls -= 1

    async def scenario() -> None:
        stt = ConcurrentTrackingSttAdapter()
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=stt,
            event_sink=events.append,
        )
        first_pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        blocked_pcm = np.full(320, 2600, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(first_pcm)
        ) is None

        first = asyncio.create_task(session.finalize_user_turn())
        await _wait_for_thread_event(
            entered_stt,
            label="owned STT finalization admission",
        )
        joiner = asyncio.create_task(session.finalize_user_turn())
        await asyncio.sleep(0)
        finalization = session._active_stt_finalization
        assert finalization is not None and finalization.task is not None
        owned_task = finalization.task

        cancelled = first if cancelled_caller == "first" else joiner
        survivor = joiner if cancelled_caller == "first" else first
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled

        assert owned_task.done() is False
        assert owned_task.cancelled() is False
        assert session._active_stt_finalization is finalization
        assert len(session._stt_admissions) == 1
        assert session.state == "understanding"
        dropped_before = session.dropped_audio_frames
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(blocked_pcm)
        ) is None
        assert session.dropped_audio_frames == dropped_before + 1
        assert session._turn_frames == []

        release_stt.set()
        result = await asyncio.wait_for(survivor, timeout=1.0)
        expected_event = (
            "user_final" if stt_outcome == "accepted" else "failed"
        )
        assert result is not None and result["type"] == expected_event
        assert stt.calls == [[first_pcm]]
        assert stt.max_concurrent_calls == 1
        assert finalization.done.is_set()
        assert session._active_stt_finalization is None
        assert session._stt_admissions == {}

        if stt_outcome != "accepted":
            assert session.state == "listening"
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(blocked_pcm)
            ) is None
            second = await session.finalize_user_turn()
            assert second is not None and second["type"] == "failed"
            assert stt.calls == [[first_pcm], [blocked_pcm]]
            assert stt.max_concurrent_calls == 1

    _run(scenario())

    expected_event = "user_final" if stt_outcome == "accepted" else "failed"
    expected_types = ["state", expected_event]
    if stt_outcome != "accepted":
        expected_types.extend(["state", "failed"])
    assert [event["type"] for event in events] == expected_types


def test_overlapping_live_and_reconnect_finalizers_join_one_stt_outcome() -> None:
    events: list[dict[str, Any]] = []

    class EndingVadAdapter:
        def __init__(self) -> None:
            self.frames: list[bytes] = []

        def accept_audio_frame(self, pcm: bytes) -> dict[str, bool]:
            self.frames.append(pcm)
            return {"speech_detected": True, "end_of_turn": True}

    async def scenario() -> None:
        vad = EndingVadAdapter()
        stt = ScriptedSttAdapter()
        session, _ = _new_session(
            vad_adapter=vad,
            stt_adapter=stt,
            event_sink=events.append,
        )
        live_pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        reconnect_pcm = np.full(320, 3200, dtype=np.int16).tobytes()
        original_finalize = session.finalize_user_turn
        arrivals = 0
        both_finalizers_arrived = asyncio.Event()
        release_finalizers = asyncio.Event()

        async def overlap_finalize(
            *,
            backfill_admission: Any | None = None,
        ) -> dict[str, Any] | None:
            nonlocal arrivals
            arrivals += 1
            if arrivals == 2:
                both_finalizers_arrived.set()
            await release_finalizers.wait()
            return await original_finalize(
                backfill_admission=backfill_admission
            )

        session.finalize_user_turn = overlap_finalize
        live = asyncio.create_task(
            session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(live_pcm)
            )
        )
        await asyncio.sleep(0)
        reconnect = asyncio.create_task(
            session.backfill_reconnect_audio(
                pcm=reconnect_pcm,
                sample_rate=16000,
                channels=1,
                backfill_id="overlapping-finalizer",
                final=True,
            )
        )

        await asyncio.wait_for(both_finalizers_arrived.wait(), timeout=1.0)
        release_finalizers.set()
        live_result, reconnect_result = await asyncio.gather(live, reconnect)

        assert live_result is not None
        assert live_result["type"] == "user_final"
        assert reconnect_result["status"] == "accepted"
        assert reconnect_result["event"] == live_result
        assert stt.calls == [[live_pcm, reconnect_pcm]]
        assert session._stt_admissions == {}
        assert session._active_stt_finalization is None

    _run(scenario())

    assert [event["type"] for event in events] == ["state", "user_final"]


@pytest.mark.parametrize(
    ("stt_outcome", "delivery_outcome"),
    [
        ("accepted", "success"),
        ("empty", "success"),
        ("accepted", "failure"),
    ],
)
def test_cancelled_finalizer_leaves_stt_settlement_owned_by_outbox(
    stt_outcome: str,
    delivery_outcome: str,
) -> None:
    delivery_started = asyncio.Event()
    release_delivery = asyncio.Event()
    channel = ScriptedDataChannel()

    class OutcomeSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            return {
                "status": stt_outcome,
                "transcript": (
                    "durably settled transcript"
                    if stt_outcome == "accepted"
                    else ""
                ),
                "language": "en",
            }

    async def scenario() -> None:
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=OutcomeSttAdapter(),
            data_channel=channel,
        )
        deliver = session._deliver_event
        expected_event = (
            "user_final" if stt_outcome == "accepted" else "failed"
        )

        async def blocked_delivery(event: dict[str, Any]) -> dict[str, Any]:
            if event["type"] == expected_event:
                delivery_started.set()
                await release_delivery.wait()
                if delivery_outcome == "failure":
                    raise RuntimeError("authoritative delivery failed")
            return await deliver(event)

        session._deliver_event = blocked_delivery
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        finalized = asyncio.create_task(session.finalize_user_turn())
        await asyncio.wait_for(delivery_started.wait(), timeout=1.0)

        settlement = session._stt_state_settlement
        assert settlement is not None and settlement.task is not None
        finalization = session._active_stt_finalization
        assert finalization is not None and finalization.task is not None
        expected_pending_state = (
            "thinking" if stt_outcome == "accepted" else "understanding"
        )
        assert session.state == expected_pending_state

        finalized.cancel()
        with pytest.raises(asyncio.CancelledError):
            await finalized
        assert len(session._stt_admissions) == 1
        assert session._active_stt_finalization is finalization
        assert finalization.task.done() is False
        assert session._stt_state_settlement is settlement
        assert settlement.task.done() is False
        assert session.state == expected_pending_state

        dropped_before = session.dropped_audio_frames
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        assert session.dropped_audio_frames == dropped_before + 1
        assert session._turn_frames == []

        release_delivery.set()
        if delivery_outcome == "success":
            delivered = await asyncio.wait_for(
                asyncio.shield(settlement.task),
                timeout=1.0,
            )
            assert delivered["type"] == expected_event
        else:
            with pytest.raises(
                RuntimeError,
                match="authoritative delivery failed",
            ):
                await asyncio.wait_for(
                    asyncio.shield(settlement.task),
                    timeout=1.0,
                )
        await asyncio.sleep(0)
        await asyncio.wait_for(finalization.done.wait(), timeout=1.0)

        expected_final_state = (
            "thinking"
            if stt_outcome == "accepted" and delivery_outcome == "success"
            else "listening"
        )
        assert session.state == expected_final_state
        assert settlement.settled is True
        assert session._stt_admissions == {}
        assert session._active_stt_finalization is None
        assert session._stt_state_settlement is None
        assert session._owned_stt_event_settlement_tasks == set()
        assert session._event_outbox == []
        channel_event_types = [
            json.loads(message)["type"] for message in channel.sent
        ]
        assert channel_event_types == (
            ["state", expected_event]
            if delivery_outcome == "success"
            else ["state"]
        )

        if expected_final_state == "listening":
            assert await session.handle_inbound_audio_frame(
                ScriptedInboundAudioFrame(pcm)
            ) is None
            assert len(session._turn_frames) == 1

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


def test_mute_discards_reconnect_hold_and_rejects_stale_backfill_epoch() -> None:
    async def scenario() -> None:
        vad = NeverEndingVadAdapter()
        stt = ScriptedSttAdapter()
        settings = AiBackendSettings(call_media_reconnect_grace_ms=5000)
        session, _ = _new_session(
            vad_adapter=vad,
            stt_adapter=stt,
            settings=settings,
        )
        pre_mute_live_pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        pre_mute_backfill_pcm = np.full(320, 2600, dtype=np.int16).tobytes()
        post_unmute_pcm = np.full(320, 3400, dtype=np.int16).tobytes()

        session._media_reconnect_grace_pending = True
        session.start_media_reconnect_grace_if_pending()
        grace_until = session._media_reconnect_grace_until
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pre_mute_live_pcm)
        ) is None
        assert vad.frames == []
        assert [
            frame.pcm for frame in session._reconnect_live_frame_hold_frames
        ] == [pre_mute_live_pcm]

        backfill_admitted = asyncio.Event()
        release_backfill = asyncio.Event()
        original_backfill = session._backfill_reconnect_audio_admitted

        async def delay_admitted_backfill(**kwargs: Any) -> dict[str, Any]:
            backfill_admitted.set()
            await release_backfill.wait()
            return await original_backfill(**kwargs)

        session._backfill_reconnect_audio_admitted = delay_admitted_backfill
        delayed = asyncio.create_task(
            session.backfill_reconnect_audio(
                pcm=pre_mute_backfill_pcm,
                sample_rate=16000,
                channels=1,
                backfill_id="pre-mute-delayed-backfill",
                final=True,
            )
        )
        await asyncio.wait_for(backfill_admitted.wait(), timeout=1.0)
        stale_admission = next(
            iter(session._reconnect_backfill_admissions.values())
        )
        assert session._reconnect_audio_backfill_epochs[
            "pre-mute-delayed-backfill"
        ] == stale_admission.audio_input_epoch

        await session.set_muted(True)

        assert stale_admission.audio_input_epoch < session._audio_input_epoch
        assert session._reconnect_live_frame_hold_frames == []
        assert session._reconnect_live_frame_hold_until == 0.0
        assert session._reconnect_live_frame_hold_logged is False
        assert session._media_reconnect_grace_audio_diag_count == 0
        assert session._media_reconnect_grace_until == grace_until

        await session.set_muted(False)
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(post_unmute_pcm)
        ) is None
        assert vad.frames == [post_unmute_pcm]

        release_backfill.set()
        stale = await asyncio.wait_for(delayed, timeout=1.0)
        assert stale["status"] == "skipped"
        duplicate = await session.backfill_reconnect_audio(
            pcm=pre_mute_backfill_pcm,
            sample_rate=16000,
            channels=1,
            backfill_id="pre-mute-delayed-backfill",
            final=True,
        )
        assert duplicate["status"] == "skipped"
        assert vad.frames == [post_unmute_pcm]

        result = await session.finalize_user_turn()
        assert result is not None and result["type"] == "user_final"
        assert stt.calls == [[post_unmute_pcm]]

    _run(scenario())


def test_retry_before_stale_backfill_uses_reserved_pre_mute_epoch() -> None:
    async def scenario() -> None:
        vad = NeverEndingVadAdapter()
        stt = ScriptedSttAdapter()
        session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)
        pre_mute_pcm = np.full(320, 2400, dtype=np.int16).tobytes()
        post_unmute_pcm = np.full(320, 3600, dtype=np.int16).tobytes()
        original_backfill = session._backfill_reconnect_audio_admitted
        first_admitted = asyncio.Event()
        release_first = asyncio.Event()
        admission_count = 0

        async def delay_first_admission(**kwargs: Any) -> dict[str, Any]:
            nonlocal admission_count
            admission_count += 1
            if admission_count == 1:
                first_admitted.set()
                await release_first.wait()
            return await original_backfill(**kwargs)

        session._backfill_reconnect_audio_admitted = delay_first_admission
        original = asyncio.create_task(
            session.backfill_reconnect_audio(
                pcm=pre_mute_pcm,
                backfill_id="retry-before-stale-original",
                audio_input_epoch=0,
                final=True,
            )
        )
        await asyncio.wait_for(first_admitted.wait(), timeout=1.0)
        assert session._reconnect_audio_backfill_epochs == {
            "retry-before-stale-original": 0
        }

        await session.set_muted(True)
        await session.set_muted(False)
        assert session._audio_input_epoch == 1

        retry = await session.backfill_reconnect_audio(
            pcm=pre_mute_pcm,
            backfill_id="retry-before-stale-original",
            audio_input_epoch=1,
            attempt=2,
            final=True,
        )
        assert retry["status"] == "skipped"
        assert session._reconnect_audio_backfill_epochs == {
            "retry-before-stale-original": 0
        }
        assert vad.frames == []

        retry_without_epoch = await session.backfill_reconnect_audio(
            pcm=pre_mute_pcm,
            backfill_id="retry-before-stale-original",
            attempt=3,
            final=True,
        )
        assert retry_without_epoch["status"] == "skipped"
        assert session._reconnect_audio_backfill_epochs == {
            "retry-before-stale-original": 0
        }
        assert vad.frames == []

        release_first.set()
        stale_original = await asyncio.wait_for(original, timeout=1.0)
        assert stale_original["status"] == "skipped"
        assert vad.frames == []

        anonymous = await session.backfill_reconnect_audio(
            pcm=pre_mute_pcm,
            final=True,
        )
        assert anonymous == {
            "status": "skipped",
            "frames": 0,
            "duration_ms": 0,
            "state": "listening",
            "reason": "audio_input_epoch_required",
        }
        unidentified_epochless = await session.backfill_reconnect_audio(
            pcm=pre_mute_pcm,
            backfill_id="unseen-after-mute",
            final=True,
        )
        assert unidentified_epochless == {
            "status": "skipped",
            "frames": 0,
            "duration_ms": 0,
            "state": "listening",
            "reason": "audio_input_epoch_required",
        }
        assert "unseen-after-mute" not in session._reconnect_audio_backfill_epochs
        stale_anonymous = await session.backfill_reconnect_audio(
            pcm=pre_mute_pcm,
            audio_input_epoch=0,
            final=True,
        )
        assert stale_anonymous["status"] == "skipped"
        assert vad.frames == []

        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(post_unmute_pcm)
        ) is None
        result = await session.finalize_user_turn()
        assert result is not None and result["type"] == "user_final"
        assert vad.frames == [post_unmute_pcm]
        assert stt.calls == [[post_unmute_pcm]]

    _run(scenario())


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
            await _wait_for_thread_event(
                adapter.first_chunk_yielded,
                label="first streaming TTS chunk",
            )
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
        await _wait_for_thread_event(
            adapter.stream_blocked,
            label="blocked replacement TTS stream",
        )
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
        await _wait_for_thread_event(
            adapter.cancel_entered,
            label="replacement TTS cancellation",
        )

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


def test_overlapping_switch_rejection_owns_slow_peer_cleanup() -> None:
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

        rejected_peer = BlockingClosePeer()
        with pytest.raises(PeerSwitchInProgressError):
            await asyncio.wait_for(
                session.mark_peer_connection_pending(
                    rejected_peer,
                    configuration=PeerOfferConfiguration(
                        thread_id="thread-rejected",
                        voice_id="voice-rejected",
                        engine_id="voxcpm2",
                        prompt_messages=(),
                        vad_adapter=None,
                        stt_adapter=None,
                    ),
                    timeout_seconds=60.0,
                ),
                timeout=0.2,
            )
        await rejected_peer.close_started.wait()
        cleanup_tasks = tuple(session._owned_peer_cleanup_tasks)
        assert cleanup_tasks
        assert any(not task.done() for task in cleanup_tasks)
        assert rejected_peer.close_calls == 1

        rejected_peer.release_close.set()
        await asyncio.gather(*cleanup_tasks)
        assert session._owned_peer_cleanup_failures == []

        old_peer.release_close.set()
        accepted, previous_peer = await first_accept
        assert accepted is True
        assert previous_peer is old_peer
        assert session.peer_connection is first_peer
        assert session._peer_lifecycle.phase == "stable"

    _run(scenario())


def test_lost_switch_ownership_closes_candidate_without_orphan_state() -> None:
    class BlockingRetiringPeer(ScriptedPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_started = asyncio.Event()
            self.release_close = asyncio.Event()

        async def close(self) -> None:
            self.close_calls += 1
            self.close_started.set()
            await self.release_close.wait()

    async def scenario() -> None:
        old_track = ScriptedOutboundAudioTrack()
        new_track = ScriptedOutboundAudioTrack()
        session, _ = _new_session(outbound_audio_track=old_track)
        retiring_peer = BlockingRetiringPeer()
        candidate_peer = ScriptedPeerConnection()
        session.peer_connection = retiring_peer
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        generation = await session.mark_peer_connection_pending(
            candidate_peer,
            outbound_audio_track=new_track,
            configuration=PeerOfferConfiguration(
                thread_id="thread-new",
                voice_id="voice-new",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=None,
                stt_adapter=None,
            ),
            timeout_seconds=60.0,
        )
        acceptance = asyncio.create_task(
            session.accept_pending_peer_connection(
                candidate_peer,
                generation=generation,
            )
        )
        await retiring_peer.close_started.wait()

        async with session._lifecycle_lock:
            session._peer_lifecycle.phase = "reconnecting"
            session._peer_lifecycle.epoch += 1
        retiring_peer.release_close.set()

        accepted, previous_peer = await acceptance
        cleanup_tasks = tuple(session._owned_peer_cleanup_tasks)
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks)
        assert accepted is False
        assert previous_peer is retiring_peer
        assert session.peer_connection is retiring_peer
        assert candidate_peer.close_calls == 1
        assert new_track.stop_calls == 1
        assert session._peer_lifecycle.phase == "reconnecting"
        assert session._peer_lifecycle.switch_owner is None
        assert session._peer_lifecycle.switch_task is None
        assert session._peer_lifecycle.retiring_peer is None
        assert session._owned_peer_cleanup_failures == []

    _run(scenario())


@pytest.mark.parametrize("terminal_action", ["end", "fail"])
def test_explicit_terminal_adopts_private_switch_candidate_resources(
    terminal_action: str,
) -> None:
    class BlockingRetiringPeer(ScriptedPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_started = asyncio.Event()
            self.release_close = asyncio.Event()

        async def close(self) -> None:
            self.close_calls += 1
            self.close_started.set()
            await self.release_close.wait()

    async def scenario() -> None:
        old_track = ScriptedOutboundAudioTrack()
        new_track = ScriptedOutboundAudioTrack()
        session, _ = _new_session(outbound_audio_track=old_track)
        retiring_peer = BlockingRetiringPeer()
        candidate_peer = ScriptedPeerConnection()
        session.peer_connection = retiring_peer
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        generation = await session.mark_peer_connection_pending(
            candidate_peer,
            outbound_audio_track=new_track,
            configuration=PeerOfferConfiguration(
                thread_id="thread-new",
                voice_id="voice-new",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=None,
                stt_adapter=None,
            ),
            timeout_seconds=60.0,
        )
        acceptance = asyncio.create_task(
            session.accept_pending_peer_connection(
                candidate_peer,
                generation=generation,
            )
        )
        await retiring_peer.close_started.wait()
        terminal = asyncio.create_task(
            session.end(reason="explicit_hangup")
            if terminal_action == "end"
            else session.fail(reason="explicit_failure")
        )
        while session.ended_at is None:
            await asyncio.sleep(0)

        cleanup = session._terminal_cleanup
        assert cleanup is not None
        assert any(peer is candidate_peer for peer in cleanup.extra_peers_pending)
        assert any(track is old_track for track in cleanup.extra_tracks_pending)
        assert any(track is new_track for track in cleanup.extra_tracks_pending)
        assert session._peer_lifecycle.switch_transaction is None

        retiring_peer.release_close.set()
        terminal_event = await terminal
        accepted, previous_peer = await acceptance

        assert terminal_event["type"] == (
            "ended" if terminal_action == "end" else "failed"
        )
        assert accepted is False
        assert previous_peer is retiring_peer
        assert session.peer_connection is retiring_peer
        assert candidate_peer.close_calls == 1
        assert old_track.stop_calls >= 1
        assert new_track.stop_calls >= 1
        assert session._terminal_cleanup_pending(cleanup) is False
        assert session._owned_peer_cleanup_failures == []

    _run(scenario())


def test_switch_preserves_slow_stt_and_thinking_frame_drop_states() -> None:
    entered_stt = threading.Event()
    release_stt = threading.Event()

    class SlowSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            entered_stt.set()
            assert release_stt.wait(timeout=2.0)
            return {
                "status": "accepted",
                "transcript": "the original turn remains ordered",
                "language": "en",
            }

    async def scenario() -> None:
        session, _ = _new_session(
            vad_adapter=NeverEndingVadAdapter(),
            stt_adapter=SlowSttAdapter(),
            outbound_audio_track=ScriptedOutboundAudioTrack(),
        )
        retiring_peer = ScriptedPeerConnection()
        candidate_peer = ScriptedPeerConnection()
        session.peer_connection = retiring_peer
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        transcription = asyncio.create_task(session.finalize_user_turn())
        await _wait_for_thread_event(
            entered_stt,
            label="peer replacement STT admission",
        )
        assert session.state == "understanding"

        generation = await session.mark_peer_connection_pending(
            candidate_peer,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
            configuration=PeerOfferConfiguration(
                thread_id="thread-new",
                voice_id="voice-new",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=NeverEndingVadAdapter(),
                stt_adapter=SlowSttAdapter(),
            ),
            timeout_seconds=60.0,
        )
        accepted, _ = await session.accept_pending_peer_connection(
            candidate_peer,
            generation=generation,
        )
        assert accepted is True
        assert session.state == "understanding"
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        assert session._turn_frames == []

        release_stt.set()
        result = await transcription
        assert result is not None and result["type"] == "user_final"
        assert session.state == "thinking"
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        assert session._turn_frames == []
        assert session.dropped_audio_frames == 2

    _run(scenario())


@pytest.mark.parametrize("stt_result", ["accepted", "empty", "error"])
def test_admitted_stt_finishes_while_configuration_switch_is_blocked(
    stt_result: str,
) -> None:
    entered_stt = threading.Event()
    release_stt = threading.Event()
    events: list[dict[str, Any]] = []

    class BlockingRetiringPeer(ScriptedPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_started = asyncio.Event()
            self.release_close = asyncio.Event()

        async def close(self) -> None:
            self.close_calls += 1
            self.close_started.set()
            await self.release_close.wait()

    class SlowOutcomeSttAdapter:
        def transcribe_pcm(
            self,
            pcm_frames: list[bytes],
            **_kwargs: Any,
        ) -> dict[str, Any]:
            assert pcm_frames
            entered_stt.set()
            assert release_stt.wait(timeout=2.0)
            if stt_result == "error":
                raise RuntimeError("simulated STT failure during switch")
            return {
                "status": "accepted" if stt_result == "accepted" else "empty",
                "transcript": "owned STT completes" if stt_result == "accepted" else "",
                "language": "en",
            }

    async def scenario() -> None:
        old_vad = NeverEndingVadAdapter()
        new_vad = NeverEndingVadAdapter()
        stt = SlowOutcomeSttAdapter()
        session, _ = _new_session(
            vad_adapter=old_vad,
            stt_adapter=stt,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
            event_sink=events.append,
        )
        retiring_peer = BlockingRetiringPeer()
        candidate_peer = ScriptedPeerConnection()
        session.peer_connection = retiring_peer
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        pcm = np.full(320, 1800, dtype=np.int16).tobytes()
        assert await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        ) is None
        finalized = asyncio.create_task(session.finalize_user_turn())
        await _wait_for_thread_event(
            entered_stt,
            label="cancel-shielded STT admission",
        )
        admission = next(iter(session._stt_admissions.values()))
        finalization = session._active_stt_finalization
        assert finalization is not None and finalization.task is not None
        assert admission.task is finalization.task
        assert admission.task is not finalized
        assert session.state == "understanding"

        generation = await session.mark_peer_connection_pending(
            candidate_peer,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
            configuration=PeerOfferConfiguration(
                thread_id="thread-new",
                voice_id="voice-new",
                engine_id="f5",
                prompt_messages=(),
                vad_adapter=new_vad,
                stt_adapter=stt,
            ),
            timeout_seconds=60.0,
        )
        switching = asyncio.create_task(
            session.accept_pending_peer_connection(
                candidate_peer,
                generation=generation,
            )
        )
        await retiring_peer.close_started.wait()
        transaction = session._peer_lifecycle.switch_transaction
        assert transaction is not None
        assert admission.token in transaction.stt_admission_tokens

        release_stt.set()
        stt_event = await asyncio.wait_for(finalized, timeout=2.0)
        assert stt_event is not None
        assert stt_event["type"] == (
            "user_final" if stt_result == "accepted" else "failed"
        )
        assert session._stt_admissions == {}
        expected_state = "thinking" if stt_result == "accepted" else "listening"
        assert session.state == expected_state

        retiring_peer.release_close.set()
        accepted, _ = await switching
        assert accepted is True
        assert session.state == expected_state

        buffered_before = len(session._turn_frames)
        result = await session.handle_inbound_audio_frame(
            ScriptedInboundAudioFrame(pcm)
        )
        if stt_result == "accepted":
            assert result is None
            assert len(session._turn_frames) == buffered_before
        else:
            assert result is None
            assert len(session._turn_frames) == buffered_before + 1
        assert [event["type"] for event in events] == [
            "state",
            "user_final" if stt_result == "accepted" else "failed",
        ]

    _run(scenario())


def test_stale_prompt_lease_cleanup_retries_transient_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS",
        0.0,
    )

    async def scenario() -> None:
        session, _ = _new_session()
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-old",
            engine_id="qwen3_1_7b",
        )
        async with session._lifecycle_lock:
            session._peer_lifecycle.epoch += 1
            session.voice_id = "voice-new"
            session.engine_id = "f5"
        owners = {session.session_id}
        attempts = 0

        async def release(owner: str) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient release failure")
            owners.discard(owner)

        with pytest.raises(SpeechSessionSelectionError):
            await session.install_or_release_tts_prompt_lease(
                release,
                accepted_configuration=reservation,
            )
        cleanup = session._owned_prompt_lease_cleanups[-1]
        assert attempts == 2
        assert owners == set()
        assert cleanup.released is True
        assert cleanup.failure_state is None
        assert session._owned_prompt_lease_cleanup_failures == []

    _run(scenario())


def test_stale_prompt_lease_permanent_failure_remains_terminal_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "CALL_PROMPT_LEASE_CLEANUP_RETRY_LIMIT", 3)
    monkeypatch.setattr(session_module, "CALL_TERMINAL_CLEANUP_RETRY_LIMIT", 2)
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS",
        0.0,
    )

    async def scenario() -> None:
        session, _ = _new_session()
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-old",
            engine_id="qwen3_1_7b",
        )
        async with session._lifecycle_lock:
            session._peer_lifecycle.epoch += 1
            session.voice_id = "voice-new"
            session.engine_id = "f5"
        attempts = 0

        async def release(_owner: str) -> None:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("permanent release failure")

        with pytest.raises(SpeechSessionSelectionError):
            await session.install_or_release_tts_prompt_lease(
                release,
                accepted_configuration=reservation,
            )
        owned = session._owned_prompt_lease_cleanups[-1]
        assert attempts == 3
        assert owned.released is False
        assert owned.failure_state == {
            "status": "retry_exhausted",
            "reason": "stale_prepare_selection",
            "attempts": 3,
            "error": "RuntimeError",
        }

        await session.end(reason="explicit_hangup")
        terminal_task = session._terminal_cleanup_task
        if terminal_task is not None:
            await terminal_task
        cleanup = session._terminal_cleanup
        assert cleanup is not None
        assert cleanup.owned_prompt_cleanups_pending == [owned]
        assert session._terminal_cleanup_failure_state is not None
        assert "owned_prompt_lease:1" in session._terminal_cleanup_failure_state[
            "pending_steps"
        ]

    _run(scenario())


def test_stale_prompt_lease_blocking_release_is_bounded_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "CALL_PROMPT_LEASE_CLEANUP_RETRY_LIMIT", 2)
    monkeypatch.setattr(
        session_module,
        "CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS",
        0.0,
    )

    async def scenario() -> None:
        session, _ = _new_session()
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-old",
            engine_id="qwen3_1_7b",
        )
        async with session._lifecycle_lock:
            session._peer_lifecycle.epoch += 1
            session.voice_id = "voice-new"
            session.engine_id = "f5"
        attempts = 0

        async def release(_owner: str) -> None:
            nonlocal attempts
            attempts += 1
            await asyncio.Event().wait()

        with pytest.raises(SpeechSessionSelectionError):
            await asyncio.wait_for(
                session.install_or_release_tts_prompt_lease(
                    release,
                    accepted_configuration=reservation,
                ),
                timeout=0.2,
            )
        owned = session._owned_prompt_lease_cleanups[-1]
        assert attempts == 2
        assert owned.released is False
        assert owned.failure_state is not None
        assert owned.failure_state["error"] == "TimeoutError"

    _run(scenario())


def test_stale_prompt_lease_caller_cancellation_cannot_cancel_owned_release() -> None:
    async def scenario() -> None:
        session, _ = _new_session()
        session.voice_id = "voice-old"
        session.engine_id = "qwen3_1_7b"
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-old",
            engine_id="qwen3_1_7b",
        )
        async with session._lifecycle_lock:
            session._peer_lifecycle.epoch += 1
            session.voice_id = "voice-new"
            session.engine_id = "f5"
        release_started = asyncio.Event()
        allow_release = asyncio.Event()
        owners = {session.session_id}

        async def release(owner: str) -> None:
            release_started.set()
            await allow_release.wait()
            owners.discard(owner)

        caller = asyncio.create_task(
            session.install_or_release_tts_prompt_lease(
                release,
                accepted_configuration=reservation,
            )
        )
        await release_started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        owned = session._owned_prompt_lease_cleanups[-1]
        assert owned.task is not None and not owned.task.done()
        assert owners == {session.session_id}

        terminal = asyncio.create_task(session.end(reason="explicit_hangup"))
        while session.ended_at is None:
            await asyncio.sleep(0)
        cleanup = session._terminal_cleanup
        assert cleanup is not None
        assert cleanup.owned_prompt_cleanups_pending == [owned]

        allow_release.set()
        await owned.task
        await terminal
        assert owned.released is True
        assert owners == set()
        assert cleanup.owned_prompt_cleanups_pending == []
        assert session._owned_prompt_lease_cleanup_failures == []

    _run(scenario())


@pytest.mark.parametrize(
    "release_outcome",
    ["transient", "permanent", "blocking"],
)
def test_terminal_adopts_prompt_handoff_without_suppressing_terminal_event(
    monkeypatch: pytest.MonkeyPatch,
    release_outcome: str,
) -> None:
    monkeypatch.setattr(session_module, "CALL_PROMPT_LEASE_CLEANUP_RETRY_LIMIT", 2)
    monkeypatch.setattr(session_module, "CALL_TERMINAL_CLEANUP_RETRY_LIMIT", 3)
    monkeypatch.setattr(
        session_module,
        "CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS",
        0.0,
    )
    events: list[dict[str, Any]] = []

    async def scenario() -> None:
        session, _ = _new_session(
            session_id=f"terminal-handoff-{release_outcome}",
            event_sink=events.append,
        )
        attempts = 0

        async def release(_owner: str) -> None:
            nonlocal attempts
            attempts += 1
            if release_outcome == "transient" and attempts == 1:
                raise RuntimeError("transient release failure")
            if release_outcome == "permanent":
                raise RuntimeError("permanent release failure")
            if release_outcome == "blocking":
                await asyncio.Event().wait()

        async with session._lifecycle_lock:
            ending = asyncio.create_task(session.end(reason="explicit_hangup"))
            await asyncio.sleep(0)
            handoff = session.start_prompt_lease_handoff(release)
            await asyncio.sleep(0)
            assert session.ended_at is None

        while session.ended_at is None:
            await asyncio.sleep(0)
        terminal_cleanup = session._terminal_cleanup
        assert terminal_cleanup is not None
        assert handoff in terminal_cleanup.owned_prompt_handoffs_pending

        terminal = await asyncio.wait_for(ending, timeout=1.0)
        assert terminal["type"] == "ended"
        assert session._terminal_outcome is not None
        assert session._terminal_outcome.event == terminal
        assert session._terminal_outcome.error is None

        assert handoff.task is not None
        assert await asyncio.wait_for(
            asyncio.shield(handoff.task),
            timeout=1.0,
        ) is False
        release_cleanup = handoff.release_cleanup
        assert release_cleanup is not None
        terminal_retry = session._terminal_cleanup_task
        if terminal_retry is not None:
            await asyncio.wait_for(terminal_retry, timeout=1.0)

        assert attempts == 2
        if release_outcome == "transient":
            assert release_cleanup.released is True
            assert terminal_cleanup.owned_prompt_handoffs_pending == []
            assert terminal_cleanup.owned_prompt_cleanups_pending == []
        else:
            assert release_cleanup.released is False
            assert (
                handoff in terminal_cleanup.owned_prompt_handoffs_pending
                or release_cleanup
                in terminal_cleanup.owned_prompt_cleanups_pending
            )
            assert session._terminal_cleanup_failure_state is not None

    _run(scenario())

    assert [event["type"] for event in events] == ["ended"]


@pytest.mark.parametrize(
    "failed_step",
    ["stop", "old_peer_close", "cancel", "prompt_lease"],
)
def test_engine_switch_cleanup_failure_never_leaves_switching(
    failed_step: str,
) -> None:
    class FailingStopTrack(ScriptedOutboundAudioTrack):
        async def stop_current(self) -> None:
            self.stop_calls += 1
            raise RuntimeError("injected stop failure")

    class FailingClosePeer(ScriptedPeerConnection):
        async def close(self) -> None:
            self.close_calls += 1
            raise RuntimeError("injected close failure")

    async def scenario() -> None:
        old_track: ScriptedOutboundAudioTrack = (
            FailingStopTrack()
            if failed_step == "stop"
            else ScriptedOutboundAudioTrack()
        )
        session, original_peer = _new_session(outbound_audio_track=old_track)
        if failed_step == "old_peer_close":
            session.peer_connection = FailingClosePeer()
        else:
            session.peer_connection = original_peer
        session.voice_id = "voice-before"
        session.engine_id = "qwen3_1_7b"

        if failed_step == "cancel":
            session.active_turn_task = ScriptedAiTurn()

            async def fail_cancel(*_: Any, **__: Any) -> dict[str, Any]:
                raise RuntimeError("injected cancellation failure")

            session.cancel_ai_turn = fail_cancel  # type: ignore[method-assign]

        if failed_step == "prompt_lease":
            async def fail_release(_: str) -> bool:
                raise RuntimeError("injected lease failure")

            assert await session.install_or_release_tts_prompt_lease(fail_release)

        candidate = ScriptedPeerConnection()
        generation = await session.mark_peer_connection_pending(
            candidate,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
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

        assert accepted is False
        assert session._peer_lifecycle.phase == "terminal"
        assert session._peer_lifecycle.phase != "switching"
        assert session._peer_lifecycle.switch_owner is None
        assert session.state == "failed"
        assert await session.commit_pending_peer_generation(generation) == "failed"
        assert await session.reject_pending_peer_generation(generation) == "failed"
        if failed_step == "prompt_lease":
            cleanup = session._terminal_cleanup
            assert cleanup is not None
            assert cleanup.prompt_lease_releaser is not None
            assert cleanup.prompt_lease_pending is True

    _run(scenario())


@pytest.mark.parametrize("blocked_step", ["old_peer", "prompt_lease"])
def test_generation_decisions_join_owned_selection_switch_cleanup(
    blocked_step: str,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    released_prompt_leases: list[str] = []

    class BlockingRetiringPeer(ScriptedPeerConnection):
        async def close(self) -> None:
            self.close_calls += 1
            if blocked_step == "old_peer":
                entered.set()
                await release.wait()

    async def release_prompt_lease(owner: str) -> bool:
        released_prompt_leases.append(owner)
        if blocked_step == "prompt_lease":
            entered.set()
            await release.wait()
        return True

    async def scenario() -> None:
        old_peer = BlockingRetiringPeer()
        candidate = ScriptedPeerConnection()
        candidate.connectionState = "connected"
        session = CallSession(
            session_id=f"switch-generation-decision-{blocked_step}",
            thread_id="thread-before",
            voice_id="voice-before",
            engine_id="qwen3_1_7b",
            peer_connection=old_peer,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
        )
        assert await session.install_or_release_tts_prompt_lease(
            release_prompt_lease
        )
        generation = await session.mark_peer_connection_pending(
            candidate,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
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

        first_commit = asyncio.create_task(
            session.commit_pending_peer_generation(generation)
        )
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        transaction = session._peer_lifecycle.switch_transaction
        switch_task = session._peer_lifecycle.switch_task
        assert transaction is not None
        assert transaction.candidate_generation == generation
        assert switch_task is not None and switch_task.done() is False
        assert session._peer_lifecycle.phase == "switching"
        assert session._peer_lifecycle.candidate is None
        assert session._peer_lifecycle.active_generation == 0
        assert session.voice_id == "voice-before"
        assert session.engine_id == "qwen3_1_7b"

        first_commit.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first_commit
        assert switch_task.done() is False
        assert await session.commit_pending_peer_generation(generation) == "in_progress"
        assert await session.reject_pending_peer_generation(generation) == "in_progress"
        assert switch_task.done() is False
        assert candidate.close_calls == 0

        release.set()
        accepted, previous_peer = await asyncio.wait_for(
            asyncio.shield(switch_task),
            timeout=1.0,
        )
        assert accepted is True
        assert previous_peer is old_peer
        assert await session.commit_pending_peer_generation(generation) == "committed"
        assert await session.reject_pending_peer_generation(generation) == "committed"
        assert session.peer_connection is candidate
        assert session.thread_id == "thread-after"
        assert session.voice_id == "voice-after"
        assert session.engine_id == "f5"
        assert session._tts_prompt_lease_releaser is None
        assert session._peer_lifecycle.active_generation == generation
        assert session._peer_lifecycle.last_switch_candidate_generation == generation
        assert session._peer_lifecycle.last_switch_outcome == "committed"
        assert old_peer.close_calls == 1
        assert candidate.close_calls == 0

    _run(scenario())

    assert released_prompt_leases == [f"switch-generation-decision-{blocked_step}"]


@pytest.mark.parametrize(
    "blocked_step",
    ["stop", "old_peer_close", "cancel", "prompt_lease"],
)
def test_cancelled_switch_initiator_cannot_strand_owned_transaction(
    blocked_step: str,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class BlockingStopTrack(ScriptedOutboundAudioTrack):
        async def stop_current(self) -> None:
            self.stop_calls += 1
            if blocked_step == "stop":
                entered.set()
                await release.wait()

    class BlockingClosePeer(ScriptedPeerConnection):
        async def close(self) -> None:
            self.close_calls += 1
            if blocked_step == "old_peer_close":
                entered.set()
                await release.wait()

    async def scenario() -> None:
        old_peer = BlockingClosePeer()
        session = CallSession(
            session_id=f"cancelled-switch-{blocked_step}",
            peer_connection=old_peer,
            outbound_audio_track=BlockingStopTrack(),
        )
        session.voice_id = "voice-before"
        session.engine_id = "qwen3_1_7b"

        if blocked_step == "cancel":
            session.active_turn_task = ScriptedAiTurn()

            async def block_cancel(*_: Any, **__: Any) -> dict[str, Any]:
                entered.set()
                await release.wait()
                session.active_turn_task = None
                return {"control_cause": "engine_switch"}

            session.cancel_ai_turn = block_cancel  # type: ignore[method-assign]

        if blocked_step == "prompt_lease":
            async def block_release(_: str) -> bool:
                entered.set()
                await release.wait()
                return True

            assert await session.install_or_release_tts_prompt_lease(block_release)

        candidate = ScriptedPeerConnection()
        generation = await session.mark_peer_connection_pending(
            candidate,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
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
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        owned_switch = session._peer_lifecycle.switch_task
        assert owned_switch is not None
        assert owned_switch.done() is False

        acceptance.cancel()
        with pytest.raises(asyncio.CancelledError):
            await acceptance
        assert session._peer_lifecycle.phase == "switching"
        assert owned_switch.done() is False

        release.set()
        accepted, previous_peer = await asyncio.wait_for(
            asyncio.shield(owned_switch),
            timeout=1.0,
        )
        assert accepted is True
        assert previous_peer is old_peer
        assert session._peer_lifecycle.phase == "stable"
        assert session._peer_lifecycle.switch_owner is None
        assert session._peer_lifecycle.switch_task is None
        reservation = await session.reserve_accepted_speech_configuration(
            voice_id="voice-after",
            engine_id="f5",
        )
        assert reservation.engine_id == "f5"

    _run(scenario())


@pytest.mark.parametrize("failed_resource", ["old_peer", "old_track"])
def test_failed_switch_resource_transfers_to_terminal_cleanup_retry(
    failed_resource: str,
) -> None:
    class FailOncePeer(ScriptedPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.successful_closes = 0

        async def close(self) -> None:
            self.close_calls += 1
            if failed_resource == "old_peer" and self.close_calls == 1:
                raise RuntimeError("injected old peer close failure")
            self.successful_closes += 1

    class FailOnceTrack(ScriptedOutboundAudioTrack):
        def __init__(self) -> None:
            super().__init__()
            self.successful_stops = 0

        async def stop_current(self) -> None:
            self.stop_calls += 1
            if failed_resource == "old_track" and self.stop_calls == 1:
                raise RuntimeError("injected old track stop failure")
            self.successful_stops += 1

    async def scenario() -> None:
        old_peer = FailOncePeer()
        old_track = FailOnceTrack()
        session = CallSession(
            session_id=f"switch-resource-transfer-{failed_resource}",
            peer_connection=old_peer,
            outbound_audio_track=old_track,
            voice_id="voice-before",
            engine_id="qwen3_1_7b",
        )
        candidate = ScriptedPeerConnection()
        generation = await session.mark_peer_connection_pending(
            candidate,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
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
        assert accepted is False
        assert session.state == "failed"
        cleanup = session._terminal_cleanup
        assert cleanup is not None
        assert cleanup.extra_peers_pending == []
        assert cleanup.extra_tracks_pending == []
        assert session._terminal_cleanup_failure_state is None
        if failed_resource == "old_peer":
            assert old_peer.close_calls == 2
            assert old_peer.successful_closes == 1
        else:
            assert old_track.stop_calls == 2
            assert old_track.successful_stops == 1

    _run(scenario())


def test_permanently_blocked_old_peer_remains_in_terminal_failure_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "CALL_SWITCH_CLEANUP_STEP_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(session_module, "CALL_TERMINAL_CLEANUP_RETRY_LIMIT", 2)
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS",
        0.0,
    )

    class PermanentlyBlockingPeer(ScriptedPeerConnection):
        async def close(self) -> None:
            self.close_calls += 1
            await asyncio.Event().wait()

    async def scenario() -> None:
        old_peer = PermanentlyBlockingPeer()
        session = CallSession(
            session_id="permanent-old-peer-cleanup",
            peer_connection=old_peer,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
            voice_id="voice-before",
            engine_id="qwen3_1_7b",
        )
        candidate = ScriptedPeerConnection()
        generation = await session.mark_peer_connection_pending(
            candidate,
            outbound_audio_track=ScriptedOutboundAudioTrack(),
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
        assert accepted is False
        cleanup_task = session._terminal_cleanup_task
        assert cleanup_task is not None
        await asyncio.wait_for(cleanup_task, timeout=0.5)
        cleanup = session._terminal_cleanup
        assert cleanup is not None
        assert cleanup.extra_peers_pending == [old_peer]
        assert session._terminal_cleanup_failure_state == {
            "status": "retry_exhausted",
            "attempts": 2,
            "pending_steps": ["extra_peer:1"],
        }
        assert old_peer.close_calls == 3

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


@pytest.mark.parametrize(
    "force_reconnect_rendezvous_failure",
    [False, True],
    ids=["complete-workflow", "forced-rendezvous-failure"],
)
def test_qwen_long_turn_reconnect_barge_in_and_recovery_preserve_live_call(
    monkeypatch: Any,
    force_reconnect_rendezvous_failure: bool,
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
            self.producer_thread: threading.Thread | None = None
            self.producer_exited = threading.Event()

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
            self.producer_thread = threading.current_thread()
            try:
                if stream_index == 0:
                    for chunk_index in range(12):
                        if chunk_index == 4:
                            self.reconnect_pause.set()
                            assert self.resume_after_reconnect.wait(
                                timeout=THREAD_EVENT_RENDEZVOUS_TIMEOUT_SECONDS
                            ), "timed out waiting to resume after reconnect"
                        if chunk_index == 10:
                            self.ready_for_barge_in.set()
                            assert self.release_for_cancel.wait(
                                timeout=THREAD_EVENT_RENDEZVOUS_TIMEOUT_SECONDS
                            ), "timed out waiting for barge-in cancellation"
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
                    self.producer_exited.set()

        def cancel(self, request_id: str) -> bool:
            assert request_id == self.active_request_id
            self.cancel_calls.append(request_id)
            self.release_for_cancel.set()
            return self.first_stream_drained.wait(timeout=1.0)

    async def scenario() -> tuple[
        IncidentQwenAdapter,
        CallbackPeer,
        CallbackPeer,
        ScriptedOutboundAudioTrack,
        ScriptedOutboundAudioTrack,
        CallSession,
    ]:
        nonlocal incident_adapter
        active_peer = CallbackPeer()
        replacement_peer = CallbackPeer()
        audio_clock = FakeAudioClock()
        active_track = FakeClockPacedOutboundAudioTrack(audio_clock)
        replacement_track = FakeClockPacedOutboundAudioTrack(audio_clock)
        adapter = IncidentQwenAdapter()
        incident_adapter = adapter
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
        try:
            await asyncio.wait_for(first_audio.wait(), timeout=1.0)
            assert adapter.first_stream_completed.is_set() is False
            await _wait_for_thread_event(
                adapter.reconnect_pause,
                label="reconnect pause",
            )
            if force_reconnect_rendezvous_failure:
                raise AssertionError("forced reconnect rendezvous failure")
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

            assert session.peer_connection is active_peer
            assert active_peer.close_calls == 0
            assert await session.commit_pending_peer_generation(generation) == "committed"
            assert session.peer_connection is replacement_peer
            assert session.state == "speaking"
            assert active_peer.close_calls == 1
            assert replacement_peer.close_calls == 0
            assert released_prompt_leases == []

            adapter.resume_after_reconnect.set()
            await _wait_for_thread_event(
                adapter.ready_for_barge_in,
                label="post-reconnect audio",
            )
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
        finally:
            adapter.resume_after_reconnect.set()
            adapter.release_for_cancel.set()
            if not long_speech.done():
                long_speech.cancel()
            settled, pending = await asyncio.wait(
                {long_speech},
                timeout=THREAD_EVENT_RENDEZVOUS_TIMEOUT_SECONDS,
            )
            assert pending == set(), "timed out settling long Qwen speech task"
            assert settled == {long_speech}
            try:
                await long_speech
            except asyncio.CancelledError:
                pass

    incident_adapter: IncidentQwenAdapter | None = None
    if force_reconnect_rendezvous_failure:
        started_at = time.perf_counter()
        with pytest.raises(AssertionError, match="forced reconnect rendezvous failure"):
            _run(scenario())
        assert time.perf_counter() - started_at < THREAD_EVENT_RENDEZVOUS_TIMEOUT_SECONDS
        assert incident_adapter is not None
        assert incident_adapter.producer_exited.is_set()
        assert incident_adapter.producer_thread is not None
        assert incident_adapter.producer_thread.is_alive() is False
        return

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
            await _wait_for_thread_event(
                adapter.second_chunk_yielded,
                label="second VoxCPM2 streaming chunk",
            )
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
            await _wait_for_thread_event(
                adapter.second_chunk_yielded,
                label="second Qwen streaming chunk",
            )
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
            await _wait_for_thread_event(
                adapter.fourth_yield_attempted,
                label="fourth Qwen streaming yield attempt",
            )
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
            await _wait_for_thread_event(
                adapter.stream_started,
                label="cancellable Qwen stream start",
            )
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
            await _wait_for_thread_event(
                adapter.cancel_started,
                label="Qwen barge-in cancellation",
            )
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
            # The bounded VAD scheduler may make the end decision up to one
            # 100-ms analysis cadence after the 500-ms silence threshold.
            for _ in range(30):
                result = await session.handle_inbound_audio_frame(
                    ScriptedInboundAudioFrame(silence_pcm)
                )
                if result is not None:
                    user_final = result
                    break
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


def test_silero_vad_analysis_is_cadenced_for_a_long_live_turn() -> None:
    """A live 20-ms input stream must not synchronously invoke Silero 50 times/s."""
    settings = AiBackendSettings(vad_end_silence_ms=700, vad_max_turn_ms=30000)
    vad = ScriptedSileroVadAdapter(sampling_rate=16000)
    session = CallSession(session_id="vad-cadence", settings=settings, vad_adapter=vad)
    pcm = np.full(320, 2000, dtype=np.int16).tobytes()

    for _ in range(1600):  # 32 seconds at 20 ms/frame.
        frame = PcmAudioFrame(pcm=pcm, sample_rate=16000, channels=1)
        session._turn_frames.append(frame)
        result = session._accept_vad_frame(frame)
        assert result["end_of_turn"] is False

    assert len(session._turn_frames) == 1600, "STT must retain the full user turn"
    assert vad.calls
    assert max(vad.calls) <= 16000 * 3
    assert len(vad.calls) <= 321, "Silero analysis must be no more frequent than every 100 ms"
    assert session._vad_recent_sample_count <= 16000 * 3


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


@pytest.mark.parametrize("blocked_step", ["active_peer", "prompt_lease"])
def test_blocking_terminal_cleanup_publishes_once_and_retries_in_background(
    monkeypatch: pytest.MonkeyPatch,
    blocked_step: str,
) -> None:
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_STEP_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_MAX_SECONDS",
        0.01,
    )
    release = asyncio.Event()
    events: list[dict[str, Any]] = []
    successful_closes = 0
    successful_releases = 0

    class BlockingPeer(ScriptedPeerConnection):
        async def close(self) -> None:
            nonlocal successful_closes
            self.close_calls += 1
            if blocked_step == "active_peer" and not release.is_set():
                await release.wait()
            successful_closes += 1

    async def release_prompt(_: str) -> bool:
        nonlocal successful_releases
        if blocked_step == "prompt_lease" and not release.is_set():
            await release.wait()
        successful_releases += 1
        return True

    async def scenario() -> None:
        peer = BlockingPeer()
        session = CallSession(
            session_id=f"blocking-terminal-{blocked_step}",
            peer_connection=peer,
            event_sink=events.append,
        )
        assert await session.install_or_release_tts_prompt_lease(release_prompt)

        winner = asyncio.create_task(session.end(reason="hangup"))
        follower = asyncio.create_task(session.fail(reason="connection_failed"))
        winner_result, follower_result = await asyncio.wait_for(
            asyncio.gather(winner, follower),
            timeout=0.5,
        )
        assert winner_result == follower_result
        assert winner_result["type"] == "ended"
        assert [event["type"] for event in events] == ["ended"]
        cleanup_task = session._terminal_cleanup_task
        assert cleanup_task is not None
        assert cleanup_task.done() is False

        release.set()
        await asyncio.wait_for(cleanup_task, timeout=0.5)
        cleanup = session._terminal_cleanup
        assert cleanup is not None
        assert session._terminal_cleanup_pending(cleanup) is False
        assert session._terminal_cleanup_failure_state is None

    _run(scenario())
    assert successful_closes == 1
    assert successful_releases == 1
    assert [event["type"] for event in events] == ["ended"]


def test_terminal_cleanup_retries_beyond_three_until_qwen_lease_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_BASE_SECONDS",
        0.0,
    )
    monkeypatch.setattr(
        session_module,
        "CALL_TERMINAL_CLEANUP_RETRY_MAX_SECONDS",
        0.0,
    )
    release_attempts = 0
    successful_releases = 0
    events: list[dict[str, Any]] = []

    async def release_prompt(_: str) -> bool:
        nonlocal release_attempts, successful_releases
        release_attempts += 1
        if release_attempts <= 5:
            raise RuntimeError("injected transient lease release failure")
        successful_releases += 1
        return True

    async def scenario() -> None:
        session, _ = _new_session(event_sink=events.append)
        session.engine_id = "qwen3_1_7b"
        assert await session.install_or_release_tts_prompt_lease(release_prompt)

        winner, follower = await asyncio.gather(
            session.end(reason="hangup"),
            session.fail(reason="connection_failed"),
        )
        assert winner == follower
        assert winner["type"] == "ended"
        cleanup_task = session._terminal_cleanup_task
        assert cleanup_task is not None
        await asyncio.wait_for(cleanup_task, timeout=0.5)
        cleanup = session._terminal_cleanup
        assert cleanup is not None
        assert cleanup.prompt_lease_pending is False
        assert session._terminal_cleanup_failure_state is None

    _run(scenario())
    assert release_attempts == 6
    assert successful_releases == 1
    assert [event["type"] for event in events] == ["ended"]


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
        assert session.peer_connection is active_peer
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


@pytest.mark.parametrize(
    ("action", "expected_admission", "expected_owner"),
    [
        ("commit", True, "candidate"),
        ("reject", False, "active"),
    ],
)
def test_candidate_inbound_media_waits_for_generation_bound_browser_decision(
    action: str,
    expected_admission: bool,
    expected_owner: str,
) -> None:
    session, active_peer = _new_session(
        session_id=f"candidate-media-browser-{action}"
    )
    candidate = ScriptedPeerConnection()

    async def scenario() -> bool:
        generation = await session.mark_peer_connection_pending(
            candidate,
            timeout_seconds=60.0,
        )
        admission = asyncio.create_task(
            session.wait_for_peer_media_admission(
                candidate,
                generation=generation,
            )
        )
        await asyncio.sleep(0)
        assert admission.done() is False

        if action == "commit":
            candidate.connectionState = "connected"
            assert await session.commit_pending_peer_generation(generation) == "committed"
        else:
            assert await session.reject_pending_peer_generation(generation) == "rejected"
        return await admission

    admitted = _run(scenario())

    assert admitted is expected_admission
    assert session.peer_connection is (
        candidate if expected_owner == "candidate" else active_peer
    )
    assert active_peer.close_calls == (1 if action == "commit" else 0)
    assert candidate.close_calls == (0 if action == "commit" else 1)


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


def test_terminal_controls_and_audio_stay_closed_before_and_after_delivery() -> None:
    terminal_delivery_started = asyncio.Event()
    allow_terminal_delivery = asyncio.Event()
    delivered_events: list[dict[str, Any]] = []

    async def event_sink(event: dict[str, Any]) -> None:
        if event["type"] == "ended":
            terminal_delivery_started.set()
            await allow_terminal_delivery.wait()
        delivered_events.append(event)

    session, _ = _new_session(
        session_id="call-session-terminal-controls",
        event_sink=event_sink,
    )

    async def assert_controls_rejected() -> None:
        for muted in (True, False):
            with pytest.raises(TerminalCallSessionError):
                await session.set_muted(muted)
        with pytest.raises(TerminalCallSessionError):
            await session.interrupt()
        with pytest.raises(TerminalCallSessionError):
            await session.update_call_selection(
                voice_id="late-voice",
                engine_id="late-engine",
            )
        with pytest.raises(TerminalCallSessionError):
            await session.cancel_speech_turn("late-turn")

    async def scenario() -> None:
        ending = asyncio.create_task(session.end(reason="hangup"))
        await asyncio.wait_for(terminal_delivery_started.wait(), timeout=1.0)

        assert session.ended_at is not None
        assert session._peer_lifecycle.phase == "terminal"
        assert session.state == "ended"
        await assert_controls_rejected()
        assert session.muted is False
        assert session.interrupted is False
        assert (session.voice_id, session.engine_id) == (None, None)

        # Media admission uses terminal ownership, not the display state. This
        # remains fail closed even if some unrelated bug corrupts that label.
        session.state = "listening"
        assert await session.handle_inbound_audio_frame(b"late-pcm") is False
        assert session.dropped_audio_frames == 1
        assert session._turn_frames == []
        session.state = "ended"

        allow_terminal_delivery.set()
        terminal = await asyncio.wait_for(ending, timeout=1.0)
        assert terminal["type"] == "ended"

        await assert_controls_rejected()
        assert await session.handle_inbound_audio_frame(b"later-pcm") is False

    _run(scenario())

    assert [event["type"] for event in delivered_events] == ["ended"]
    assert session.state == "ended"
    assert session.muted is False
    assert session.interrupted is False
    assert session.dropped_audio_frames == 2
