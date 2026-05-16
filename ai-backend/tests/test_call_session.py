from __future__ import annotations

import asyncio
import threading
from io import BytesIO
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
)
from app.models.tts_registry import TtsAudioChunk


def _scripted_wav_bytes() -> bytes:
    buffer = BytesIO()
    samples = np.full(2880, 512 / np.iinfo(np.int16).max, dtype=np.float32)
    sf.write(buffer, samples, 24000, format="WAV")
    return buffer.getvalue()


SCRIPTED_WAV_BYTES = _scripted_wav_bytes()


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
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.preroll_seconds: list[float] = []
        self.stop_calls = 0
        self.wait_calls: list[float | None] = []

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
        return True


class ObservableStreamingOutboundAudioTrack(ScriptedOutboundAudioTrack):
    def __init__(self) -> None:
        super().__init__()
        self.first_chunk_enqueued = asyncio.Event()

    async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
        result = await super().enqueue(chunk, preroll_seconds=preroll_seconds)
        if len(self.chunks) == 1:
            self.first_chunk_enqueued.set()
        return result


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
    assert session.state == "listening"


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


def test_failed_connection_records_connection_failed_reason() -> None:
    session, peer = _new_session()
    peer.connectionState = "failed"

    _run(session.handle_connection_state_change())

    assert session.state == "failed"
    assert session.end_reason == "connection_failed"
    assert peer.close_calls == 1


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
    }
