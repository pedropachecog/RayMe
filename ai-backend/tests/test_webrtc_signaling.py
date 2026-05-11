from __future__ import annotations

import base64
import asyncio
import math
from io import BytesIO
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

import app.api.webrtc as webrtc_module
from app.main import create_app
from app.models.tts_registry import TtsAudioChunk

MUTE_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/mute"
INTERRUPT_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/interrupt"
END_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/end"
SPEAK_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/speak"
RECONNECT_AUDIO_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/reconnect-audio"
EVENTS_DRAIN_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/events/drain"


def _scripted_wav_bytes() -> bytes:
    buffer = BytesIO()
    samples = np.full(2400, 0.25, dtype=np.float32)
    sf.write(buffer, samples, 24000, format="WAV")
    return buffer.getvalue()


SCRIPTED_WAV_BYTES = _scripted_wav_bytes()


class ScriptedTtsAdapter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def synthesize_call_text(
        self,
        *,
        turn_id: str,
        text: str,
        voice_id: str,
        engine_id: str,
        **options: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "turn_id": turn_id,
                "text": text,
                "voice_id": voice_id,
                "engine_id": engine_id,
                **options,
            }
        )
        if self.fail:
            raise RuntimeError(
                "raw model failure Traceback /home/pmpg/.cache/model-cache "
                r"C:\Users\pmpg\rayme\model-cache"
            )
        return {"wav_bytes": SCRIPTED_WAV_BYTES, "sample_rate": 24000, "duration_ms": 100}


class ScriptedStreamingTtsAdapter:
    engine_id = "voxcpm2"

    def __init__(self, *, fail: str | None = None) -> None:
        self.fail = fail
        self.calls: list[Any] = []

    def synthesize(self, _payload: Any) -> dict[str, Any]:
        raise AssertionError("whole synthesis fallback was used")

    def stream(self, request: Any) -> Any:
        self.calls.append(request)
        if self.fail == "before_first_audio":
            raise RuntimeError("Traceback /home/pmpg/.cache openbmb/VoxCPM2")
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=0,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=100,
            generated_at_ms=25.0,
        )
        if self.fail == "after_first_audio":
            raise RuntimeError("Traceback /home/pmpg/.cache openbmb/VoxCPM2")
        yield TtsAudioChunk(
            engine_id=self.engine_id,
            chunk_index=1,
            wav_bytes=SCRIPTED_WAV_BYTES,
            sample_rate=24000,
            duration_ms=100,
            generated_at_ms=60.0,
        )


class ScriptedModelManager:
    def __init__(
        self,
        adapter: Any | None = None,
        *,
        adapters: dict[str, Any] | None = None,
    ) -> None:
        self.switch_calls: list[str] = []
        self.tts_adapters = dict(adapters or {"f5": adapter or ScriptedTtsAdapter()})

    def switch_tts_engine(self, engine_id: str) -> None:
        self.switch_calls.append(engine_id)
        if engine_id not in self.tts_adapters:
            raise ValueError("unknown engine")


class StubPeerConnection:
    connectionState = "new"

    def __init__(self) -> None:
        self.tracks: list[Any] = []
        self.create_data_channel_calls = 0

    def addTrack(self, track: Any) -> None:
        self.tracks.append(track)

    def createDataChannel(self, label: str) -> Any:
        self.create_data_channel_calls += 1
        return type("StubDataChannel", (), {"label": label, "readyState": "open", "send": lambda self, data: None})()

    def on(self, _event_name: str) -> Any:
        def decorator(handler: Any) -> Any:
            return handler

        return decorator

    async def close(self) -> None:
        return None


@pytest.fixture
def stub_webrtc(monkeypatch: pytest.MonkeyPatch) -> None:
    def create_peer_connection(_offer: Any) -> StubPeerConnection:
        return StubPeerConnection()

    def attach_outbound_audio_track(peer_connection: StubPeerConnection) -> Any:
        track = type("StubAudioTrack", (), {"kind": "audio", "chunks": [], "enqueue": lambda self, chunk: self.chunks.append(chunk)})()
        peer_connection.addTrack(track)
        return track

    async def negotiate_answer(_peer_connection: Any, _offer: Any) -> dict[str, str]:
        return {
            "type": "answer",
            "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=RayMe test answer\r\nt=0 0\r\n",
        }

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", create_peer_connection)
    monkeypatch.setattr(webrtc_module, "_attach_outbound_audio_track", attach_outbound_audio_track)
    monkeypatch.setattr(webrtc_module, "_negotiate_answer", negotiate_answer)


def _client(*, model_manager: Any | None = None) -> TestClient:
    app = create_app()
    if model_manager is not None:
        app.state.model_manager = model_manager
    return TestClient(app)


def _offer_payload(*, session_id: str = "call-session-1") -> dict[str, Any]:
    return {
        "session_id": session_id,
        "thread_id": "thread-1",
        "voice_id": "voice-1",
        "engine_id": "f5",
        "prompt_messages": [
            {"role": "system", "content": "Stay in character."},
            {"role": "user", "content": "Hello before the call."},
        ],
        "offer": {
            "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n",
            "type": "offer",
        },
    }


def test_webrtc_status_exposes_live_call_readiness_and_session_counts() -> None:
    response = _client().get("/webrtc/status")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {
        "status",
        "live_call_ready",
        "media_transport_ready",
        "active_sessions",
    }
    assert isinstance(payload["live_call_ready"], bool)
    assert isinstance(payload["media_transport_ready"], bool)
    assert isinstance(payload["active_sessions"], int)
    assert payload["status"] in {"starting", "ready", "degraded", "unavailable"}


def test_webrtc_offer_creates_session_answer_and_events_channel(stub_webrtc: None) -> None:
    client = _client()
    response = client.post("/webrtc/offer", json=_offer_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "call-session-1"
    assert payload["answer"]["type"] == "answer"
    assert isinstance(payload["answer"]["sdp"], str)
    assert payload["answer"]["sdp"].startswith("v=0")
    assert payload["data_channel"]["label"] == "rayme-events"
    session = client.app.state.call_session_manager.get_session("call-session-1")
    assert session.peer_connection.create_data_channel_calls == 0
    assert session.outbound_audio_track is not None
    assert session.outbound_audio_track.kind == "audio"


def test_failed_reconnect_offer_preserves_existing_session_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peers: list[Any] = []
    tracks: list[Any] = []

    class TrackingPeerConnection(StubPeerConnection):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    class TrackingAudioTrack:
        kind = "audio"

        def __init__(self) -> None:
            self.chunks: list[bytes] = []

        async def enqueue(self, chunk: bytes, *, preroll_seconds: float = 0.0) -> float:
            self.chunks.append(chunk)
            return 0.1

    def create_peer_connection(_offer: Any) -> TrackingPeerConnection:
        peer = TrackingPeerConnection()
        peers.append(peer)
        return peer

    def attach_outbound_audio_track(peer_connection: TrackingPeerConnection) -> TrackingAudioTrack:
        track = TrackingAudioTrack()
        tracks.append(track)
        peer_connection.addTrack(track)
        return track

    negotiate_calls = 0

    async def negotiate_answer(_peer_connection: Any, _offer: Any) -> dict[str, str]:
        nonlocal negotiate_calls
        negotiate_calls += 1
        if negotiate_calls == 2:
            raise RuntimeError("simulated reconnect negotiation failure")
        return {
            "type": "answer",
            "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=RayMe test answer\r\nt=0 0\r\n",
        }

    monkeypatch.setattr(webrtc_module, "_create_peer_connection", create_peer_connection)
    monkeypatch.setattr(webrtc_module, "_attach_outbound_audio_track", attach_outbound_audio_track)
    monkeypatch.setattr(webrtc_module, "_negotiate_answer", negotiate_answer)

    client = _client()
    session_id = "reconnect-preserve-session"
    first = client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    assert first.status_code == 200
    session = client.app.state.call_session_manager.get_session(session_id)
    original_peer = session.peer_connection
    original_track = session.outbound_audio_track

    second = client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    assert second.status_code == 502
    assert len(peers) == 2
    assert len(tracks) == 2
    assert session.peer_connection is original_peer
    assert session.outbound_audio_track is original_track
    assert original_peer.close_calls == 0


def test_webrtc_mute_control_returns_session_state(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(
        MUTE_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"muted": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["state"] in {"listening", "muted"}
    assert payload["muted"] is True


def test_webrtc_interrupt_control_returns_session_state(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(INTERRUPT_ROUTE_TEMPLATE.format(session_id=session_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["state"] in {"listening", "interrupted"}


def test_webrtc_speak_synthesizes_with_exact_engine_and_emits_done(stub_webrtc: None) -> None:
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapter)
    client = _client(model_manager=manager)
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-1",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": "f5",
            "final_chunk": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert manager.switch_calls == ["f5"]
    assert adapter.calls == [
        {
            "turn_id": "ai-turn-1",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": "f5",
        }
    ]
    assert payload["event"]["type"] == "ai_done"
    assert payload["event"]["turn_id"] == "ai-turn-1"


def test_webrtc_speak_accepts_bounded_voxcpm2_options(stub_webrtc: None) -> None:
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-options"
    client.post(
        "/webrtc/offer",
        json={**_offer_payload(session_id=session_id), "engine_id": "voxcpm2"},
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "final_chunk": True,
            "reference_audio_base64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "Real VoxCPM2 reference text.",
            "reference_audio_content_type": "audio/wav",
            "voxcpm2_cloning_mode": "transcript_guided",
            "voxcpm2_style_prompt": "warm phone call voice",
            "voxcpm2_cfg_value": 2.4,
            "voxcpm2_inference_timesteps": 12,
            "voxcpm2_normalize": True,
            "voxcpm2_denoise": False,
        },
    )

    assert response.status_code == 200
    assert manager.switch_calls == ["voxcpm2"]
    assert adapter.calls == [
        {
            "turn_id": "ai-turn-voxcpm2",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "voxcpm2_cloning_mode": "transcript_guided",
            "voxcpm2_style_prompt": "warm phone call voice",
            "voxcpm2_cfg_value": 2.4,
            "voxcpm2_inference_timesteps": 12,
            "voxcpm2_normalize": True,
            "voxcpm2_denoise": False,
        }
    ]


def test_webrtc_speak_returns_streaming_tts_playback_metrics_for_voxcpm2(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedStreamingTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-streaming"
    client.post(
        "/webrtc/offer",
        json={**_offer_payload(session_id=session_id), "engine_id": "voxcpm2"},
    )

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2-streaming",
            "text": "Hello from VoxCPM2 streaming.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "final_chunk": True,
            "reference_audio_base64": "cmVhbC1zYW1wbGU=",
            "reference_transcript": "Real VoxCPM2 reference text.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert manager.switch_calls == ["voxcpm2"]
    assert len(adapter.calls) == 1
    assert payload["event"]["type"] == "ai_done"

    started_event = payload["event"]["ai_audio_started_event"]
    assert started_event["type"] == "ai_audio_started"
    started_playback = started_event["tts_playback"]
    assert started_playback["streaming_used"] is True
    assert started_playback["chunk_count_at_start"] == 1
    assert "total_generation_ms" not in started_playback
    assert "total_playback_ms" not in started_playback

    final_playback = payload["event"]["tts_playback_final"]
    assert final_playback["streaming_used"] is True
    assert final_playback["chunk_count"] >= 1
    assert math.isfinite(final_playback["total_generation_ms"])
    assert math.isfinite(final_playback["total_playback_ms"])
    assert isinstance(final_playback["inter_chunk_gaps_ms"], list)


def test_webrtc_speak_streaming_failure_keeps_fixed_public_error(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedStreamingTtsAdapter(fail="before_first_audio")
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-streaming-fail"
    client.post("/webrtc/offer", json={**_offer_payload(session_id=session_id), "engine_id": "voxcpm2"})

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2-streaming-fail",
            "text": "Hello from a failing VoxCPM2 stream.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "final_chunk": True,
            "reference_audio_base64": "cmVhbC1zYW1wbGU=",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "call_tts_failed",
        "message": "Speech playback failed",
        "engine_id": "voxcpm2",
    }
    assert "Traceback" not in response.text
    assert "/home/" not in response.text
    assert ".cache" not in response.text
    assert "openbmb/VoxCPM2" not in response.text

    late_failure_adapter = ScriptedStreamingTtsAdapter(fail="after_first_audio")
    late_session_id = "call-session-voxcpm2-streaming-late-fail"
    client.post(
        "/webrtc/offer",
        json={**_offer_payload(session_id=late_session_id), "engine_id": "voxcpm2"},
    )
    session = client.app.state.call_session_manager.get_session(late_session_id)
    event = asyncio.run(
        session.speak_text(
            "ai-turn-voxcpm2-streaming-late-fail",
            "Hello from a late failing VoxCPM2 stream.",
            "voice-voxcpm2",
            "voxcpm2",
            final_chunk=True,
            tts_adapter=late_failure_adapter,
            reference_audio_b64="cmVhbC1zYW1wbGU=",
        )
    )

    assert event["type"] == "failed"
    assert event["code"] == "call_tts_failed"
    assert event["ai_audio_started_event"]["tts_playback"]["streaming_used"] is True
    assert event["ai_audio_started_event"]["tts_playback"]["chunk_count_at_start"] == 1
    assert event["tts_playback_final"]["streaming_used"] is True
    assert event["tts_playback_final"]["chunk_count"] == 1


def test_webrtc_speak_rejects_reference_audio_over_web_ui_limit(
    monkeypatch: pytest.MonkeyPatch,
    stub_webrtc: None,
) -> None:
    monkeypatch.setattr(webrtc_module, "MAX_REFERENCE_AUDIO_BYTES", len(b"real-sample") - 1)
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-reference-too-large"
    client.post("/webrtc/offer", json={**_offer_payload(session_id=session_id), "engine_id": "voxcpm2"})

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-reference-too-large",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "reference_audio_base64": base64.b64encode(b"real-sample").decode("ascii"),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "call_tts_reference_audio_too_large",
        "message": "Reference audio is too large",
    }
    assert adapter.calls == []


def test_webrtc_speak_rejects_unbounded_voxcpm2_options_with_sanitized_422(
    stub_webrtc: None,
) -> None:
    adapter = ScriptedTtsAdapter()
    manager = ScriptedModelManager(adapters={"voxcpm2": adapter})
    client = _client(model_manager=manager)
    session_id = "call-session-voxcpm2-invalid"
    client.post("/webrtc/offer", json={**_offer_payload(session_id=session_id), "engine_id": "voxcpm2"})

    invalid = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-voxcpm2-invalid",
            "text": "Hello from VoxCPM2.",
            "voice_id": "voice-voxcpm2",
            "engine_id": "voxcpm2",
            "voxcpm2_cloning_mode": "invalid",
            "voxcpm2_style_prompt": (
                "Traceback /home/pmpg/.cache/model-cache "
                r"C:\Users\pmpg\rayme\model-cache "
            )
            * 30,
            "voxcpm2_cfg_value": 99,
            "voxcpm2_inference_timesteps": 500,
        },
    )

    assert invalid.status_code == 422
    assert "Traceback" not in invalid.text
    assert "/home/" not in invalid.text
    assert r"C:\\" not in invalid.text
    assert "model-cache" not in invalid.text


def test_webrtc_speak_failure_returns_fixed_call_tts_failed_code(stub_webrtc: None) -> None:
    client = _client(model_manager=ScriptedModelManager(ScriptedTtsAdapter(fail=True)))
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(
        SPEAK_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "turn_id": "ai-turn-fail",
            "text": "Hello from AI.",
            "voice_id": "voice-1",
            "engine_id": "f5",
            "final_chunk": True,
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "call_tts_failed",
        "message": "Speech playback failed",
        "engine_id": "f5",
    }
    assert "raw model failure" not in response.text
    assert "Traceback" not in response.text
    assert "/home/" not in response.text
    assert r"C:\\" not in response.text
    assert "model-cache" not in response.text


def test_webrtc_end_control_returns_session_state(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))

    response = client.post(
        END_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"reason": "hangup"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["state"] == "ended"
    assert payload["reason"] == "hangup"


def test_webrtc_reconnect_audio_backfill_appends_to_call_session(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    pcm = np.full(640, 2000, dtype=np.int16).tobytes()

    response = client.post(
        RECONNECT_AUDIO_ROUTE_TEMPLATE.format(session_id=session_id),
        json={
            "pcm_b64": base64.b64encode(pcm).decode("ascii"),
            "sample_rate": 16000,
            "channels": 1,
            "backfill_id": "gap-route-1",
            "reason": "failed",
            "attempt": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["status"] == "accepted"
    assert payload["frames"] == 2
    session = client.app.state.call_session_manager.get_session(session_id)
    assert len(session._turn_frames) == 2


def test_webrtc_events_drain_returns_undelivered_user_final(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-1"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    session = client.app.state.call_session_manager.get_session(session_id)
    session.data_channel = type(
        "ClosedDataChannel",
        (),
        {"readyState": "closed", "send": lambda self, data: None},
    )()

    import asyncio

    asyncio.run(
        session.emit_event(
            {
                "type": "user_final",
                "session_id": session_id,
                "turn_id": "user-turn-1",
                "text": "Recovered text",
            }
        )
    )

    response = client.post(EVENTS_DRAIN_ROUTE_TEMPLATE.format(session_id=session_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["events"] == [
        {
            "type": "user_final",
            "session_id": session_id,
            "turn_id": "user-turn-1",
            "text": "Recovered text",
        }
    ]
    assert client.post(EVENTS_DRAIN_ROUTE_TEMPLATE.format(session_id=session_id)).json()["events"] == []


def test_webrtc_events_drain_returns_late_user_final_after_end(stub_webrtc: None) -> None:
    client = _client()
    session_id = "call-session-late-end"
    client.post("/webrtc/offer", json=_offer_payload(session_id=session_id))
    session = client.app.state.call_session_manager.get_session(session_id)
    session.data_channel = type(
        "ClosedDataChannel",
        (),
        {"readyState": "closed", "send": lambda self, data: None},
    )()

    end_response = client.post(
        END_ROUTE_TEMPLATE.format(session_id=session_id),
        json={"reason": "connection_failed"},
    )
    assert end_response.status_code == 200
    assert client.app.state.call_session_manager.stats()["active_sessions"] == 0

    import asyncio

    asyncio.run(
        session.emit_event(
            {
                "type": "user_final",
                "session_id": session_id,
                "turn_id": "user-turn-after-end",
                "text": "Recovered text after end",
            }
        )
    )

    response = client.post(EVENTS_DRAIN_ROUTE_TEMPLATE.format(session_id=session_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["events"] == [
        {
            "type": "user_final",
            "session_id": session_id,
            "turn_id": "user-turn-after-end",
            "text": "Recovered text after end",
        }
    ]


def test_webrtc_offer_malformed_payload_returns_sanitized_validation_error() -> None:
    response = _client().post(
        "/webrtc/offer",
        json={
            "session_id": "call-session-1",
            "offer": {"type": "offer"},
        },
    )

    assert response.status_code in {400, 422}
    assert "Traceback" not in response.text
    assert "File " not in response.text


def test_webrtc_offer_rejects_non_media_offer_instead_of_inventing_answer() -> None:
    response = _client().post("/webrtc/offer", json=_offer_payload())

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "webrtc_offer_failed",
        "message": "WebRTC offer could not be accepted",
    }
    assert "RayMe test answer" not in response.text


def test_receive_audio_track_media_stream_error_with_live_ice_does_not_fail_session() -> None:
    """MediaStreamError raised while ICE=completed/connected must NOT call session.fail().

    Regression for: Android Chrome stops sending audio frames after the user
    finishes speaking; aiortc raises MediaStreamError; the old fallthrough
    called session.fail() which destroyed the outbound audio track and prevented
    in-flight TTS from being delivered.
    """
    import asyncio

    from app.call.session import CallSessionManager
    from app.call.tracks import QueuedAudioOutputTrack
    from app.config import AiBackendSettings

    class MediaStreamError(Exception):
        pass

    class ScriptedInboundTrack:
        kind = "audio"
        id = "inbound-1"
        calls = 0

        async def recv(self) -> Any:
            self.calls += 1
            # Raise immediately — the error path is what we are testing, not
            # frame processing.  ICE and conn states are still "alive" so the
            # fallthrough must NOT call session.fail().
            raise MediaStreamError("end of stream")

    class LivePeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"
        close_calls: int = 0

        async def close(self) -> None:
            self.close_calls += 1

    async def _run_test() -> tuple[int, str, int]:
        settings = AiBackendSettings()
        manager = CallSessionManager(settings=settings)
        pc = LivePeerConnection()
        outbound_track = QueuedAudioOutputTrack()
        session = await manager.create_session(
            session_id="test-media-stream-error",
            thread_id="thread-1",
            voice_id="voice-1",
            engine_id="f5",
            prompt_messages=[],
            peer_connection=pc,
            vad_adapter=None,
            stt_adapter=None,
            outbound_audio_track=outbound_track,
        )
        track = ScriptedInboundTrack()
        task = asyncio.create_task(webrtc_module._receive_audio_track(session, track))
        await asyncio.sleep(0.25)
        session.state = "ended"
        await task
        return pc.close_calls, session.state, track.calls

    close_calls, state, recv_calls = asyncio.run(_run_test())

    assert close_calls == 0, (
        "peer_connection.close() must NOT be called when MediaStreamError fires "
        "while ICE/conn are still alive (ice=completed conn=connected)"
    )
    assert state not in {"failed"}, (
        f"session.fail() must NOT be called; got state={state!r}"
    )
    assert recv_calls > 1


def test_receive_audio_track_recovers_from_transient_live_ice_recv_errors() -> None:
    """Transient recv errors while ICE is live must not permanently kill input."""
    import asyncio

    from app.call.session import CallSession
    from app.call.tracks import PcmAudioFrame

    class TransientRecvError(Exception):
        pass

    class ResumingInboundTrack:
        kind = "audio"
        id = "inbound-resumes"

        def __init__(self) -> None:
            self.calls = 0

        async def recv(self) -> Any:
            self.calls += 1
            if self.calls <= 3:
                raise TransientRecvError("temporary RTP read gap")
            await asyncio.sleep(0.005)
            return PcmAudioFrame(
                pcm=(b"\x00\x20" * 320),
                sample_rate=16000,
                channels=1,
            )

    class LivePeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"

    class EndingCallSession(CallSession):
        async def handle_inbound_audio_frame(self, frame: Any) -> Any:
            result = await super().handle_inbound_audio_frame(frame)
            self.state = "ended"
            return result

    async def _run_test() -> tuple[int, int, str]:
        session = EndingCallSession(
            session_id="test-transient-recv-error",
            peer_connection=LivePeerConnection(),
            vad_adapter=None,
            stt_adapter=None,
        )
        track = ResumingInboundTrack()
        await webrtc_module._receive_audio_track(session, track)
        return track.calls, session.incoming_audio_frames, session.state

    recv_calls, incoming_frames, state = asyncio.run(_run_test())

    assert recv_calls >= 4
    assert incoming_frames == 1
    assert state == "ended"


def test_receive_audio_track_exits_when_peer_connection_is_superseded() -> None:
    """Old receive loops must stop after a media reconnect installs a new peer."""
    import asyncio

    from app.call.session import CallSession
    from app.call.tracks import PcmAudioFrame

    class EndlessInboundTrack:
        kind = "audio"
        id = "old-inbound"

        def __init__(self) -> None:
            self.calls = 0

        async def recv(self) -> Any:
            self.calls += 1
            await asyncio.sleep(0.005)
            return PcmAudioFrame(
                pcm=(b"\x00\x20" * 320),
                sample_rate=16000,
                channels=1,
            )

    class LivePeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"

    async def _run_test() -> tuple[int, int, str]:
        old_peer = LivePeerConnection()
        new_peer = LivePeerConnection()
        session = CallSession(
            session_id="test-superseded-peer",
            peer_connection=old_peer,
            vad_adapter=None,
            stt_adapter=None,
        )
        track = EndlessInboundTrack()
        task = asyncio.create_task(webrtc_module._receive_audio_track(session, track, old_peer))
        await asyncio.sleep(0.02)
        session.peer_connection = new_peer
        await asyncio.wait_for(task, timeout=0.5)
        return track.calls, session.incoming_audio_frames, session.state

    recv_calls, incoming_frames, state = asyncio.run(_run_test())

    assert recv_calls >= 1
    assert incoming_frames >= 1
    assert state == "listening"


def test_data_channel_keepalive_starts_when_browser_channel_already_open() -> None:
    """Browser-created channels can arrive at aiortc already open.

    Regression for Android Chrome live calls: if the backend only starts
    keepalive from a future "open" event, this already-open path never sends
    pings during long listening/user-speaking spans.
    """
    import asyncio

    from app.call.session import CallSession

    class ScriptedDataChannel:
        label = webrtc_module.RAYME_EVENTS_CHANNEL

        def __init__(self) -> None:
            self.readyState = "open"
            self.sent: list[str] = []
            self.handlers: dict[str, Any] = {}

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

        def send(self, data: str) -> None:
            self.sent.append(data)

        def close(self) -> None:
            self.readyState = "closed"
            close_handler = self.handlers.get("close")
            if close_handler is not None:
                close_handler()

    class ScriptedPeerConnection:
        connectionState = "connected"
        iceConnectionState = "completed"

        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}

        def on(self, event_name: str) -> Any:
            def decorator(handler: Any) -> Any:
                self.handlers[event_name] = handler
                return handler

            return decorator

    async def _run_test() -> list[str]:
        peer = ScriptedPeerConnection()
        session = CallSession(session_id="test-already-open-datachannel", peer_connection=peer)
        webrtc_module._attach_peer_handlers(peer, session)
        channel = ScriptedDataChannel()

        peer.handlers["datachannel"](channel)
        await asyncio.sleep(0)
        channel.close()
        await asyncio.sleep(0)
        return channel.sent

    sent = asyncio.run(_run_test())

    assert sent[:1] == ['{"type":"ping"}']
