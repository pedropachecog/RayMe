from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.webrtc as webrtc_module
from app.main import create_app

MUTE_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/mute"
INTERRUPT_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/interrupt"
END_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/end"
SPEAK_ROUTE_TEMPLATE = "/webrtc/sessions/{session_id}/speak"


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
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "turn_id": turn_id,
                "text": text,
                "voice_id": voice_id,
                "engine_id": engine_id,
            }
        )
        if self.fail:
            raise RuntimeError("raw model failure")
        return {"wav_bytes": b"scripted-wav", "sample_rate": 24000, "duration_ms": 100}


class ScriptedModelManager:
    def __init__(self, adapter: ScriptedTtsAdapter | None = None) -> None:
        self.switch_calls: list[str] = []
        self.tts_adapters = {"f5": adapter or ScriptedTtsAdapter()}

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
