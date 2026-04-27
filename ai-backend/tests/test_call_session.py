from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

import numpy as np
import soundfile as sf

import app.call.session as session_module
from app.call.tracks import QueuedAudioOutputTrack, normalize_inbound_audio_frame
from app.call.session import (
    CALL_TTS_AUDIO_PREROLL_SECONDS,
    CALL_TTS_REMOTE_PLAYOUT_HOLD_SECONDS,
    CallSession,
    CallSessionManager,
)


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

    def synthesize(self, payload: Any) -> dict[str, Any]:
        self.reference_audio = payload.reference_audio
        return {"wav_bytes": SCRIPTED_WAV_BYTES, "sample_rate": 24000, "duration_ms": 120}


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
    event_sink: Any | None = None,
) -> tuple[Any, ScriptedPeerConnection]:
    peer = ScriptedPeerConnection()
    session = CallSession(
        session_id=session_id,
        peer_connection=peer,
        vad_adapter=vad_adapter,
        stt_adapter=stt_adapter,
        tts_adapter=tts_adapter,
        outbound_audio_track=outbound_audio_track,
        event_sink=event_sink,
    )
    return session, peer


def test_create_session_returns_stable_session_id() -> None:
    manager = CallSessionManager()

    session = _run(manager.create_session(session_id="call-session-1"))

    assert session.session_id == "call-session-1"
    assert manager.get_session("call-session-1") is session
    assert session.stats()["session_id"] == "call-session-1"


def test_mute_stops_server_consumption() -> None:
    session, _ = _new_session()

    _run(session.set_muted(True))
    accepted = _run(session.handle_inbound_audio_frame(b"pcm-frame-1"))

    assert session.muted is True
    assert accepted is False
    assert session.stats()["incoming_audio_frames"] == 1
    assert session.stats()["dropped_audio_frames"] == 1
    assert session.stats()["muted"] is True


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
    session, _ = _new_session(vad_adapter=vad, stt_adapter=stt)

    end_silence_ms = int(session.settings.vad_end_silence_ms)
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
