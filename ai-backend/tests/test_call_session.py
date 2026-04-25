from __future__ import annotations

import asyncio
from typing import Any

from app.call.session import CallSession, CallSessionManager


def _run(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return asyncio.run(value)
    return value


class FakePeerConnection:
    def __init__(self) -> None:
        self.close_calls = 0
        self.connectionState = "new"

    async def close(self) -> None:
        self.close_calls += 1


class FakeAiTurn:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


def _new_session(*, session_id: str = "call-session-1") -> tuple[Any, FakePeerConnection]:
    peer = FakePeerConnection()
    session = CallSession(session_id=session_id, peer_connection=peer)
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
    session, _ = _new_session()

    result = _run(session.handle_inbound_audio_frame(b"pcm-frame-1"))

    assert result is not None
    assert session.stats()["incoming_audio_frames"] == 1


def test_interrupt_cancels_active_ai_turn() -> None:
    session, _ = _new_session()
    active_turn = FakeAiTurn()
    session.active_ai_turn = active_turn

    event = _run(session.interrupt())

    assert session.interrupted is True
    assert active_turn.cancel_calls == 1
    assert event["type"] == "interrupted"
    assert event["session_id"] == "call-session-1"


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
