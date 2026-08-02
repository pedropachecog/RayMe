"""RED contracts for Web UI call bootstrap, controls, and durable writeback."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import json
import logging
import threading
import time
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.characters import get_character_session
from app.api.chat import get_chat_session
from app.api.threads import get_thread_session
from app.api.voices import get_voice_session
from app.domain.ai_backend_client import (
    AiBackendProcessingError,
    SpeechTurn,
    SpeechTurnClosedError,
    SpeechTurnTerminal,
)
from app.main import create_app
from app.domain.call_service import CallService
from app.storage.models import (
    Base,
    CallTurn,
    Character,
    Message,
    Thread,
    Voice,
    VoiceAsset,
    utc_now,
)
from app.storage.session import create_engine


@dataclass(frozen=True, slots=True)
class CallFixture:
    client: TestClient
    app: FastAPI
    sessionmaker: async_sessionmaker
    backend: "ScriptedCallBackend"
    completion: "ScriptedCompletionClient"
    voice_blob_dir: Path


_TEST_VOICE_BLOB_DIR: Path | None = None
UNSAFE_CALL_ROUTE_SUFFIXES = [
    "/offer",
    "/peer-promotion",
    "/mute",
    "/interrupt",
    "/turns",
    "/reconnect-audio",
    "/events/recover",
    "/end",
    "/_debug/event",
]


class ScriptedCallBackend:
    def __init__(self, *, ready: bool = True, voice_available: bool = True) -> None:
        self.ready = ready
        self.voice_available = voice_available
        self.fail_end = False
        self.fail_offer = False
        self.readiness_calls = 0
        self.created_sessions: list[dict[str, Any]] = []
        self.offer_calls: list[dict[str, Any]] = []
        self.offer_peer_generation: int | None = None
        self.peer_promotion_calls: list[dict[str, Any]] = []
        self.peer_promotion_error_code: str | None = None
        self.peer_promotion_status: str | None = None
        self.prepare_calls: list[dict[str, Any]] = []
        self.preparation_status_calls = 0
        self.preparation_result: dict[str, Any] | None = None
        self.preparation_statuses: list[dict[str, Any]] = []
        self.backfill_calls: list[dict[str, Any]] = []
        self.drained_events: list[dict[str, Any]] = []
        self.speak_calls: list[dict[str, Any]] = []
        self.cancel_turn_calls: list[dict[str, Any]] = []
        self.interrupt_calls: list[dict[str, Any]] = []
        self.interrupt_result: dict[str, Any] | None = None
        self.mute_calls: list[dict[str, Any]] = []
        self.muted = False
        self.audio_input_epoch = 0
        self.mute_revision = 0

    async def readiness(self) -> dict[str, Any]:
        self.readiness_calls += 1
        if not self.ready:
            return {
                "ready": False,
                "code": "call_backend_not_ready",
                "message": "AI backend is not ready for calls.",
            }
        return {"ready": True}

    async def start_call_session(self, **payload: Any) -> dict[str, str]:
        self.created_sessions.append(dict(payload))
        if not self.ready:
            return {"status": "not_ready", "code": "call_backend_not_ready"}
        if not self.voice_available:
            return {"status": "voice_unavailable", "code": "call_voice_unavailable"}
        return {"session_id": f"ai_session_{len(self.created_sessions):032d}"}

    async def create_webrtc_offer(self, base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.offer_calls.append({"base_url": base_url, "payload": dict(payload)})
        if self.fail_offer:
            from app.domain.ai_backend_client import AiBackendProcessingError

            raise AiBackendProcessingError(
                code="webrtc_offer_failed",
                message="WebRTC offer could not be accepted",
            )
        return {
            "session_id": payload["session_id"],
            "answer": {"type": "answer", "sdp": "v=0\r\n"},
            "peer_generation": self.offer_peer_generation,
            "peer_commit_timeout_ms": 11000,
        }

    async def promote_call_peer(
        self,
        base_url: str,
        session_id: str,
        generation: int,
        action: str,
    ) -> dict[str, Any]:
        self.peer_promotion_calls.append(
            {
                "base_url": base_url,
                "session_id": session_id,
                "generation": generation,
                "action": action,
            }
        )
        if self.peer_promotion_error_code is not None:
            raise AiBackendProcessingError(
                code=self.peer_promotion_error_code,
                message="Replacement peer generation was already committed",
            )
        return {
            "session_id": session_id,
            "generation": generation,
            "status": self.peer_promotion_status
            or ("committed" if action == "commit" else "rejected"),
        }

    async def prepare_call_speech(
        self,
        base_url: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.prepare_calls.append(
            {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
        )
        return dict(
            self.preparation_result
            or {
                "engine_id": "qwen3_1_7b",
                "model_state": "resident",
                "prompt_state": "ready",
                "voice_key": payload["voice_id"],
                "error_code": None,
            }
        )

    async def get_tts_preparation_status(self, base_url: str) -> dict[str, Any]:
        self.preparation_status_calls += 1
        if self.preparation_statuses:
            return dict(self.preparation_statuses.pop(0))
        voice_key = self.prepare_calls[-1]["payload"]["voice_id"]
        return {
            "model": {"state": "resident", "engine_id": "qwen3_1_7b"},
            "prompt": {"state": "ready", "voice_key": voice_key, "error_code": None},
        }

    async def speak_call(
        self,
        base_url: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.speak_calls.append(
            {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
        )
        return {
            "session_id": session_id,
            "event": {
                "type": "ai_done",
                "tts_playback_final": {"playout_wait_completed": True},
            },
        }

    async def backfill_call_audio(
        self,
        base_url: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.backfill_calls.append(
            {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
        )
        return {"session_id": session_id, "status": "accepted", "frames": 2}

    async def cancel_call_turn(
        self,
        base_url: str,
        session_id: str,
        turn_id: str,
    ) -> dict[str, Any]:
        self.cancel_turn_calls.append(
            {"base_url": base_url, "session_id": session_id, "turn_id": turn_id}
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "state": "listening",
            "status": "cancelled",
        }

    async def drain_call_events(self, base_url: str, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "events": list(self.drained_events)}

    async def interrupt_call(self, base_url: str, session_id: str) -> dict[str, Any]:
        self.interrupt_calls.append({"base_url": base_url, "session_id": session_id})
        return dict(
            self.interrupt_result
            or {
                "session_id": session_id,
                "interrupted": True,
                "cancelled_turn_id": "turn-interrupted-01",
                "receiver_drain_ms": 250,
            }
        )

    async def mute_call(
        self,
        base_url: str,
        session_id: str,
        muted: bool,
    ) -> dict[str, Any]:
        self.mute_calls.append(
            {"base_url": base_url, "session_id": session_id, "muted": muted}
        )
        if muted and not self.muted:
            self.audio_input_epoch += 1
        self.muted = muted
        self.mute_revision += 1
        return {
            "session_id": session_id,
            "muted": self.muted,
            "audio_input_epoch": self.audio_input_epoch,
            "mute_revision": self.mute_revision,
        }

    async def end_call(self, base_url: str, session_id: str, reason: str) -> dict[str, Any]:
        if self.fail_end:
            from app.domain.ai_backend_client import AiBackendProcessingError

            raise AiBackendProcessingError(code="call_control_failed", message="Call control request failed")
        return {"session_id": session_id, "reason": reason}


class ScriptedCompletionClient:
    def __init__(self) -> None:
        self.token_sequences: list[list[str]] = [["AI reply."]]
        self.requests: list[dict[str, Any]] = []
        self.fail_next = False

    async def stream_chat_completion_tokens(self, settings: Any, messages: Any) -> AsyncIterator[str]:
        self.requests.append({"settings": settings, "messages": list(messages)})
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("raw LLM failure")
        tokens = self.token_sequences.pop(0) if self.token_sequences else ["AI reply."]
        for token in tokens:
            yield token


class ScriptedCancelableTask:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


@pytest.fixture()
def call_fixture(tmp_path: Path) -> Iterator[CallFixture]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-calls.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    backend = ScriptedCallBackend()
    completion = ScriptedCompletionClient()
    app = create_app(static_client_dir=None)
    voice_blob_dir = tmp_path / "blobs" / "voices"
    global _TEST_VOICE_BLOB_DIR
    _TEST_VOICE_BLOB_DIR = voice_blob_dir
    _install_test_dependencies(app, sessionmaker, backend, completion, voice_blob_dir)

    with TestClient(app) as client:
        yield CallFixture(
            client=client,
            app=app,
            sessionmaker=sessionmaker,
            backend=backend,
            completion=completion,
            voice_blob_dir=voice_blob_dir,
        )

    _TEST_VOICE_BLOB_DIR = None
    asyncio.run(engine.dispose())


def test_start_from_thread_returns_server_owned_call_and_session_ids(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))

    response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})

    assert response.status_code == 201
    body = response.json()
    assert body["thread_id"] == thread_id
    assert body["call_id"]
    assert body["session_id"]
    assert body["call_id"] != body["session_id"]
    assert body["call_id"] != thread_id
    assert len(body["call_id"]) >= 32
    assert len(body["session_id"]) >= 32


def test_start_from_character_card_creates_or_selects_thread_before_call(
    call_fixture: CallFixture,
) -> None:
    character_id = asyncio.run(
        _insert_character_with_voice(call_fixture.sessionmaker, character_id="char_card_call")
    )

    response = call_fixture.client.post("/api/calls/start", json={"character_id": character_id})

    assert response.status_code == 201
    body = response.json()
    assert body["call_id"]
    assert body["session_id"]
    assert body["thread_id"].startswith("thread_")
    assert asyncio.run(_thread_character_id(call_fixture.sessionmaker, body["thread_id"])) == character_id


@pytest.mark.parametrize("control_route", ["/offer", "/mute", "/interrupt", "/end"])
def test_controls_reject_unknown_or_mismatched_call_session_pairs(
    call_fixture: CallFixture,
    control_route: str,
) -> None:
    response = call_fixture.client.post(
        f"/api/calls/call_unknown{control_route}",
        json={"session_id": "ai_session_foreign", "muted": True, "sdp": "scripted-offer", "type": "offer"},
    )

    assert response.status_code == 404
    assert _public_error_code(response) == "call_session_not_found"


def test_turns_reject_mismatched_session_for_existing_call(call_fixture: CallFixture) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    start_response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})
    assert start_response.status_code == 201
    started = start_response.json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": "ai_session_not_owned_by_this_call",
            "turn_id": "user-turn-1",
            "text": "Hello",
            "source": "user_final",
        },
    )

    assert response.status_code == 404
    assert _public_error_code(response) == "call_session_not_found"


def test_reconnect_audio_backfill_forwards_to_backend_without_persistence(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/reconnect-audio",
        json={
            "session_id": started["session_id"],
            "pcm_b64": "AAECAw==",
            "sample_rate": 16000,
            "channels": 1,
            "backfill_id": "gap-1",
            "audio_input_epoch": 4,
            "reason": "failed",
            "attempt": 1,
            "duration_ms": 40,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert call_fixture.backend.backfill_calls == [
        {
            "base_url": "https://127.0.0.1:9443",
            "session_id": started["session_id"],
            "payload": {
                "pcm_b64": "AAECAw==",
                "sample_rate": 16000,
                "channels": 1,
                "backfill_id": "gap-1",
                "audio_input_epoch": 4,
                "reason": "failed",
                "attempt": 1,
                "duration_ms": 40,
                "batch_index": None,
                "final": True,
            },
        }
    ]
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert rows[-1] == ("call_start", "event", "Call started")
    assert not any(row[0] in {"user_speech", "ai_speech"} for row in rows)


def test_post_unmute_pcm_marker_crosses_web_proxy_without_relabeling(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()
    post_unmute_pcm = (3333).to_bytes(2, "little", signed=True) * 320
    encoded = base64.b64encode(post_unmute_pcm).decode("ascii")

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/reconnect-audio",
        json={
            "session_id": started["session_id"],
            "pcm_b64": encoded,
            "sample_rate": 16000,
            "channels": 1,
            "backfill_id": "post-unmute-marker",
            "audio_input_epoch": 1,
            "final": True,
        },
    )

    assert response.status_code == 200
    forwarded = call_fixture.backend.backfill_calls[-1]["payload"]
    assert forwarded["pcm_b64"] == encoded
    assert forwarded["audio_input_epoch"] == 1
    assert set(
        int.from_bytes(post_unmute_pcm[offset : offset + 2], "little", signed=True)
        for offset in range(0, len(post_unmute_pcm), 2)
    ) == {3333}


@pytest.mark.parametrize(
    "requests",
    [
        [
            {"backfill_id": "stale-first", "audio_input_epoch": 0, "attempt": 1},
            {"backfill_id": "stale-first", "audio_input_epoch": 0, "attempt": 2},
        ],
        [
            {"backfill_id": "retry-first", "audio_input_epoch": 0, "attempt": 2},
            {"backfill_id": "retry-first", "audio_input_epoch": 0, "attempt": 1},
        ],
        [{"audio_input_epoch": 0, "attempt": 1}],
    ],
    ids=["stale-first", "retry-first", "anonymous"],
)
def test_reconnect_audio_epoch_identity_survives_web_proxy_ordering(
    call_fixture: CallFixture,
    requests: list[dict[str, Any]],
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()

    for request_payload in requests:
        response = call_fixture.client.post(
            f"/api/calls/{started['call_id']}/reconnect-audio",
            json={
                "session_id": started["session_id"],
                "pcm_b64": "AAECAw==",
                "sample_rate": 16000,
                "channels": 1,
                **request_payload,
            },
        )
        assert response.status_code == 200

    forwarded = [
        {
            "backfill_id": item["payload"]["backfill_id"],
            "audio_input_epoch": item["payload"]["audio_input_epoch"],
            "attempt": item["payload"]["attempt"],
        }
        for item in call_fixture.backend.backfill_calls
    ]
    assert forwarded == [
        {
            "backfill_id": item.get("backfill_id"),
            "audio_input_epoch": item["audio_input_epoch"],
            "attempt": item["attempt"],
        }
        for item in requests
    ]


def test_recover_call_events_forwards_undelivered_user_final(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    call_fixture.backend.drained_events = [
        {
            "type": "user_final",
            "session_id": started["session_id"],
            "turn_id": "user-turn-recovered",
            "text": "Recovered speech.",
        }
    ]

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/events/recover",
        json={"session_id": started["session_id"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "call_id": started["call_id"],
        "session_id": started["session_id"],
        "events": call_fixture.backend.drained_events,
    }


def test_mute_interrupt_and_end_reject_mismatched_session_for_existing_call(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    start_response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})
    assert start_response.status_code == 201
    started = start_response.json()

    for route in ("/mute", "/interrupt", "/end"):
        response = call_fixture.client.post(
            f"/api/calls/{started['call_id']}{route}",
            json={"session_id": "ai_session_not_owned_by_this_call", "muted": True},
        )
        assert response.status_code == 404
        assert _public_error_code(response) == "call_session_not_found"


def test_mute_response_preserves_backend_authoritative_audio_epoch(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()
    route = f"/api/calls/{started['call_id']}/mute"
    payload = {"session_id": started["session_id"], "muted": True}

    muted = call_fixture.client.post(route, json=payload)
    repeated = call_fixture.client.post(route, json=payload)
    unmuted = call_fixture.client.post(
        route,
        json={"session_id": started["session_id"], "muted": False},
    )

    assert muted.status_code == 200
    assert muted.json()["muted"] is True
    assert muted.json()["audio_input_epoch"] == 1
    assert muted.json()["mute_revision"] == 1
    assert repeated.json()["audio_input_epoch"] == 1
    assert repeated.json()["mute_revision"] == 2
    assert unmuted.json()["muted"] is False
    assert unmuted.json()["audio_input_epoch"] == 1
    assert unmuted.json()["mute_revision"] == 3


def test_start_requires_assigned_voice_with_recovery_message(call_fixture: CallFixture) -> None:
    character_id = asyncio.run(
        _insert_character(call_fixture.sessionmaker, character_id="char_no_voice", default_voice_id=None)
    )
    thread_id = asyncio.run(
        _insert_thread(call_fixture.sessionmaker, character_id=character_id, thread_id="thread_no_voice")
    )

    response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})

    assert response.status_code == 409
    assert _public_error_code(response) == "call_voice_required"
    assert _public_error_message(response) == "Assign a voice before calling this character."


def test_start_rejects_unavailable_assigned_voice(call_fixture: CallFixture) -> None:
    character_id = asyncio.run(
        _insert_character_with_voice(
            call_fixture.sessionmaker,
            character_id="char_deleted_voice",
            voice_deleted=True,
        )
    )
    thread_id = asyncio.run(
        _insert_thread(call_fixture.sessionmaker, character_id=character_id, thread_id="thread_deleted_voice")
    )

    response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})

    assert response.status_code == 409
    assert _public_error_code(response) == "call_voice_unavailable"


def test_start_rejects_backend_not_ready_with_sanitized_public_code(
    call_fixture: CallFixture,
) -> None:
    call_fixture.backend.ready = False
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))

    response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})

    assert response.status_code == 503
    assert _public_error_code(response) == "call_backend_not_ready"
    assert "traceback" not in str(response.json()).lower()
    assert "runtimeerror" not in str(response.json()).lower()


def test_foreign_origin_rejected_for_unsafe_call_controls(call_fixture: CallFixture) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))

    response = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
        headers={"Origin": "https://attacker.invalid"},
    )

    assert response.status_code == 403
    assert _public_error_code(response) == "call_origin_not_allowed"


@pytest.mark.parametrize("route_suffix", UNSAFE_CALL_ROUTE_SUFFIXES)
def test_foreign_origin_rejected_for_every_unsafe_call_route(
    call_fixture: CallFixture,
    route_suffix: str,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}{route_suffix}",
        json=_unsafe_call_payload(route_suffix, started["session_id"]),
        headers={"Origin": "https://attacker.invalid"},
    )

    assert response.status_code == 403
    assert _public_error_code(response) == "call_origin_not_allowed"


def test_foreign_origin_rejected_for_start_route(call_fixture: CallFixture) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))

    response = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
        headers={"Origin": "https://attacker.invalid"},
    )

    assert response.status_code == 403
    assert _public_error_code(response) == "call_origin_not_allowed"


def test_debug_event_truncates_detail_and_is_behavior_neutral(
    call_fixture: CallFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    before_rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    before_backend_calls = _backend_call_snapshot(call_fixture.backend)
    long_debug_value = "debug-detail-" * 80

    with caplog.at_level(logging.INFO, logger="app.api.calls"):
        response = call_fixture.client.post(
            f"/api/calls/{started['call_id']}/_debug/event",
            json={
                "event": "pc.connectionstatechange",
                "session_id": started["session_id"],
                "detail": {"phase": "failed", "raw": long_debug_value},
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id)) == before_rows
    assert _backend_call_snapshot(call_fixture.backend) == before_backend_calls
    detail_logs = [
        record.args[3]
        for record in caplog.records
        if record.name == "app.api.calls" and record.getMessage().startswith("[browser-call]")
    ]
    assert detail_logs
    assert len(str(detail_logs[-1])) <= 800
    assert "truncated" in str(detail_logs[-1])
    assert long_debug_value not in str(detail_logs[-1])


async def test_ai_backend_client_backfill_uses_stt_sized_timeout_path() -> None:
    from app.domain.ai_backend_client import AiBackendClient

    class CapturingHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
            self.requests.append({"method": method, "url": url, **kwargs})
            return httpx.Response(
                200,
                json={"session_id": "rtc-call-1", "status": "accepted", "frames": 2},
            )

    http_client = CapturingHttpClient()
    ai_client = AiBackendClient(
        http_client=http_client,  # type: ignore[arg-type]
        timeout=5.0,
        transcription_timeout=120.0,
        webrtc_timeout=30.0,
    )

    result = await ai_client.backfill_call_audio(
        "https://ai.local:9443",
        "rtc-call-1",
        {"pcm_b64": "AA==", "sample_rate": 16000, "channels": 1, "final": True},
    )

    assert result["status"] == "accepted"
    assert http_client.requests[0]["timeout"] == 120.0


async def test_ordinary_and_reconnect_stt_survive_simulated_delay_over_thirty_seconds() -> None:
    from app.domain.ai_backend_client import AiBackendClient

    class SimulatedDelayedSttClient:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
            del method
            timeout = float(kwargs["timeout"])
            self.timeouts.append(timeout)
            simulated_elapsed_seconds = 45.0
            if timeout <= simulated_elapsed_seconds:
                raise httpx.ReadTimeout("simulated STT exceeded caller timeout")
            if url.endswith("/stt/transcribe"):
                return httpx.Response(
                    200,
                    json={"status": "ok", "transcript": "ordinary delayed speech"},
                )
            return httpx.Response(
                200,
                json={
                    "session_id": "rtc-delayed-stt",
                    "status": "accepted",
                    "event": {
                        "type": "user_final",
                        "turn_id": "user-turn-delayed",
                        "text": "reconnected delayed speech",
                    },
                },
            )

    http_client = SimulatedDelayedSttClient()
    ai_client = AiBackendClient(
        http_client=http_client,  # type: ignore[arg-type]
        webrtc_timeout=30.0,
        transcription_timeout=120.0,
    )

    ordinary = await ai_client.transcribe_sample(
        "https://ai.local:9443",
        b"wav",
        "turn.wav",
        "audio/wav",
    )
    reconnect = await ai_client.backfill_call_audio(
        "https://ai.local:9443",
        "rtc-delayed-stt",
        {"pcm_b64": "AA==", "sample_rate": 16000, "channels": 1, "final": True},
    )

    assert ordinary.transcript == "ordinary delayed speech"
    assert reconnect["event"]["type"] == "user_final"
    assert [reconnect["event"]["type"]].count("user_final") == 1
    assert http_client.timeouts == [120.0, 120.0]


def test_offer_failure_returns_backend_public_detail(call_fixture: CallFixture) -> None:
    call_fixture.backend.fail_offer = True
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json={
            "session_id": started["session_id"],
            "offer": {"type": "offer", "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"},
        },
    )

    assert response.status_code == 502
    assert _public_error_code(response) == "webrtc_offer_failed"
    assert _public_error_message(response) == "WebRTC offer could not be accepted"


@pytest.mark.parametrize("action", ["commit", "reject"])
def test_peer_promotion_preserves_offer_generation_and_forwards_authenticated_action(
    call_fixture: CallFixture,
    action: str,
) -> None:
    call_fixture.backend.offer_peer_generation = 7
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    offered = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json={
            "session_id": started["session_id"],
            "offer": {"type": "offer", "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"},
        },
    )
    promoted = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/peer-promotion",
        json={
            "session_id": started["session_id"],
            "generation": 7,
            "action": action,
        },
    )

    assert offered.status_code == 200
    assert offered.json()["peer_generation"] == 7
    assert offered.json()["peer_commit_timeout_ms"] == 11000
    assert promoted.status_code == 200
    assert promoted.json()["status"] == (
        "committed" if action == "commit" else "rejected"
    )
    assert call_fixture.backend.peer_promotion_calls == [
        {
            "base_url": "https://127.0.0.1:9443",
            "session_id": started["session_id"],
            "generation": 7,
            "action": action,
        }
    ]


def test_peer_promotion_preserves_structured_already_committed_status(
    call_fixture: CallFixture,
) -> None:
    call_fixture.backend.offer_peer_generation = 7
    call_fixture.backend.peer_promotion_error_code = "webrtc_peer_already_committed"
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json={
            "session_id": started["session_id"],
            "offer": {"type": "offer", "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"},
        },
    )

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/peer-promotion",
        json={
            "session_id": started["session_id"],
            "generation": 7,
            "action": "commit",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "webrtc_peer_already_committed",
        "message": "Replacement peer generation was already committed",
    }


@pytest.mark.parametrize("action", ["commit", "reject"])
def test_peer_promotion_preserves_switch_in_progress_status(
    call_fixture: CallFixture,
    action: str,
) -> None:
    call_fixture.backend.offer_peer_generation = 7
    call_fixture.backend.peer_promotion_status = "in_progress"
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json={
            "session_id": started["session_id"],
            "offer": {"type": "offer", "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"},
        },
    )

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/peer-promotion",
        json={
            "session_id": started["session_id"],
            "generation": 7,
            "action": action,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "call_id": started["call_id"],
        "session_id": started["session_id"],
        "generation": 7,
        "status": "in_progress",
    }


@pytest.mark.parametrize(
    "invalid_reference",
    [
        "changed_reference",
        "unsafe_path",
        "missing_file",
    ],
)
def test_qwen_call_start_rejects_tampered_or_uncontained_reference_before_backend_work(
    call_fixture: CallFixture,
    invalid_reference: str,
) -> None:
    thread_id, voice_id = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(
            call_fixture.sessionmaker,
            invalid_reference=invalid_reference,
        )
    )
    if invalid_reference == "changed_reference":
        (call_fixture.voice_blob_dir / f"voice_asset_{voice_id}.wav").write_bytes(
            b"changed voice sample bytes"
        )
    elif invalid_reference == "missing_file":
        (call_fixture.voice_blob_dir / f"voice_asset_{voice_id}.wav").unlink()

    response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})

    assert response.status_code == 409
    assert _public_error_code(response) == "call_voice_unavailable"
    assert _public_error_message(response) == (
        "The assigned voice is unavailable. Choose another voice before calling."
    )
    assert call_fixture.backend.readiness_calls == 0
    assert call_fixture.backend.offer_calls == []
    public_body = response.text
    assert "Reference transcript for Qwen call preparation" not in public_body
    assert str(call_fixture.voice_blob_dir) not in public_body
    assert "private.wav" not in public_body


def test_qwen_offer_prepares_exact_uploaded_reference_and_turn_uses_opaque_key(
    call_fixture: CallFixture,
) -> None:
    call_fixture.completion.token_sequences = [["Prepared Qwen call reply."]]
    thread_id, saved_voice_id = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started_response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})
    assert started_response.status_code == 201
    started = started_response.json()

    offer_response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json={
            "session_id": started["session_id"],
            "offer": {"type": "offer", "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"},
        },
    )

    assert offer_response.status_code == 200
    assert started["engine_id"] == "qwen3_1_7b"
    assert len(call_fixture.backend.prepare_calls) == 1
    prepare_payload = call_fixture.backend.prepare_calls[0]["payload"]
    assert prepare_payload["voice_id"] == _qwen_test_voice_key(saved_voice_id)
    assert prepare_payload["voice_id"] != started["voice_id"]
    assert prepare_payload["engine_id"] == "qwen3_1_7b"
    assert base64.b64decode(prepare_payload["reference_audio_base64"], validate=True) == (
        b"voice sample bytes"
    )
    assert prepare_payload["reference_transcript"] == "Reference transcript for Qwen call preparation."
    assert call_fixture.backend.offer_calls[0]["payload"]["voice_id"] == prepare_payload["voice_id"]
    assert not {
        "voice_data_steward",
        "authorization_basis",
        "use_scope",
        "reference_sha256",
        "transcript_sha256",
    }.intersection(prepare_payload)
    assert offer_response.json()["preparation"] == {
        "model": {"state": "resident", "engine_id": "qwen3_1_7b"},
        "prompt": {
            "state": "ready",
            "voice_key": prepare_payload["voice_id"],
            "error_code": None,
        },
    }

    turn_response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-qwen-prepared",
            "text": "Use the prepared saved voice.",
            "source": "user_final",
        },
    )

    assert turn_response.status_code == 200
    speak_payload = call_fixture.backend.speak_calls[-1]["payload"]
    assert speak_payload["voice_id"] == prepare_payload["voice_id"]
    assert speak_payload["reference_transcript"] == prepare_payload["reference_transcript"]


def test_qwen_slow_llm_submits_first_safe_segment_before_stream_completion(
    call_fixture: CallFixture,
) -> None:
    first_submission = threading.Event()
    release_llm = threading.Event()
    response_holder: list[Any] = []

    class HeldOpenCompletionClient:
        async def stream_chat_completion_tokens(
            self,
            settings: Any,
            messages: Any,
        ) -> AsyncIterator[str]:
            del settings, messages
            yield "This is the first safe sentence."
            while not release_llm.is_set():
                await asyncio.sleep(0.01)
            yield " A final tail remains"

    class EarlyAcceptanceBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            if not payload["final_chunk"]:
                first_submission.set()
                return {
                    "session_id": session_id,
                    "event": {
                        "status": "queued",
                        "turn_id": payload["turn_id"],
                        "tts_playback_final": {"playout_wait_completed": True},
                    },
                }
            return {
                "session_id": session_id,
                "event": {
                    "type": "ai_done",
                    "turn_id": payload["turn_id"],
                    "tts_playback_final": {"playout_wait_completed": True},
                },
            }

    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend = EarlyAcceptanceBackend()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: backend
    call_fixture.app.dependency_overrides[calls_module.get_call_completion_client] = (
        HeldOpenCompletionClient
    )

    def request_turn() -> None:
        response_holder.append(
            call_fixture.client.post(
                f"/api/calls/{started['call_id']}/turns",
                json={
                    "session_id": started["session_id"],
                    "turn_id": "turn-qwen-slow-llm",
                    "text": "Keep the LLM stream open.",
                    "source": "user_final",
                },
            )
        )

    request_thread = threading.Thread(target=request_turn, daemon=True)
    request_thread.start()
    try:
        assert first_submission.wait(timeout=2.0), (
            "Qwen speech was not submitted while the LLM stream remained open"
        )
        assert request_thread.is_alive()
        assert backend.speak_calls[0]["payload"]["text"] == (
            "This is the first safe sentence."
        )
        assert backend.speak_calls[0]["payload"]["final_chunk"] is False
        assert backend.speak_calls[0]["payload"]["engine_id"] == "qwen3_1_7b"
    finally:
        release_llm.set()
        request_thread.join(timeout=3.0)

    assert not request_thread.is_alive()
    assert response_holder[0].status_code == 200
    assert [call["payload"]["text"] for call in backend.speak_calls] == [
        "This is the first safe sentence.",
        "A final tail remains",
    ]
    assert backend.speak_calls[-1]["payload"]["final_chunk"] is True


def test_qwen_offer_polls_shared_readiness_without_repeating_preparation(
    call_fixture: CallFixture,
) -> None:
    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    voice_key = _qwen_test_voice_key()
    call_fixture.backend.preparation_result = {
        "engine_id": "qwen3_1_7b",
        "model_state": "loading",
        "prompt_state": "prewarming",
        "voice_key": voice_key,
        "error_code": None,
    }
    call_fixture.backend.preparation_statuses = [
        {
            "model": {"state": "resident", "engine_id": "qwen3_1_7b"},
            "prompt": {
                "state": "prewarming",
                "voice_key": voice_key,
                "error_code": None,
            },
        },
        {
            "model": {"state": "resident", "engine_id": "qwen3_1_7b"},
            "prompt": {"state": "ready", "voice_key": voice_key, "error_code": None},
        },
    ]

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json={
            "session_id": started["session_id"],
            "offer": {"type": "offer", "sdp": "v=0\r\n"},
        },
    )

    assert response.status_code == 200
    assert len(call_fixture.backend.prepare_calls) == 1
    assert call_fixture.backend.preparation_status_calls == 2
    assert response.json()["preparation"]["prompt"]["state"] == "ready"


def test_qwen_failed_preparation_is_safe_and_a_later_retry_remains_usable(
    call_fixture: CallFixture,
) -> None:
    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    call_fixture.backend.preparation_result = {
        "engine_id": "qwen3_1_7b",
        "model_state": "resident",
        "prompt_state": "failed",
        "voice_key": _qwen_test_voice_key(),
        "error_code": "qwen3_prompt_failed",
        "diagnostic": r"C:\\private\\model secret transcript",
    }
    offer_payload = {
        "session_id": started["session_id"],
        "offer": {"type": "offer", "sdp": "v=0\r\n"},
    }

    failed = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json=offer_payload,
    )

    assert failed.status_code == 502
    assert _public_error_code(failed) == "qwen3_prompt_failed"
    assert _public_error_message(failed) == "Voice preparation failed"
    assert "private" not in failed.text
    assert "secret transcript" not in failed.text

    call_fixture.backend.preparation_result = None
    recovered = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json=offer_payload,
    )

    assert recovered.status_code == 200
    assert recovered.json()["preparation"]["prompt"]["state"] == "ready"
    assert len(call_fixture.backend.prepare_calls) == 2


def test_offer_rejects_missing_backend_method_instead_of_returning_empty_answer(
    call_fixture: CallFixture,
) -> None:
    class IncompleteCallBackend:
        pass

    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = IncompleteCallBackend

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/offer",
        json={
            "session_id": started["session_id"],
            "offer": {"type": "offer", "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"},
        },
    )

    assert response.status_code == 502
    assert _public_error_code(response) == "call_backend_client_misconfigured"
    assert "create_webrtc_offer" in _public_error_message(response)


@pytest.mark.parametrize(
    ("helper_name", "args", "missing_method"),
    [
        ("_promote_call_peer", ("session_live", 1, "commit"), "promote_call_peer"),
        ("_mute_call", ("session_live", True), "mute_call"),
        ("_interrupt_call", ("session_live",), "interrupt_call"),
        ("_end_call", ("session_live", "hangup"), "end_call"),
        ("_speak_call", ("session_live", {"turn_id": "turn_1", "text": "Hi"}), "speak_call"),
        (
            "_backfill_call_audio",
            ("session_live", {"pcm_b64": "AA==", "sample_rate": 16000, "channels": 1}),
            "backfill_call_audio",
        ),
    ],
)
def test_call_control_helpers_reject_missing_backend_methods_instead_of_local_success(
    helper_name: str,
    args: tuple[Any, ...],
    missing_method: str,
) -> None:
    calls_module = importlib.import_module("app.api.calls")
    helper = getattr(calls_module, helper_name)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(helper(object(), "https://127.0.0.1:9443", *args))

    assert getattr(exc_info.value, "code") == "call_backend_client_misconfigured"
    assert missing_method in getattr(exc_info.value, "message")


def test_start_and_end_write_chronological_call_boundary_rows(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    start_response = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id})
    assert start_response.status_code == 201
    started = start_response.json()

    end_response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/end",
        json={"session_id": started["session_id"]},
    )

    assert end_response.status_code == 200
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert rows[-2:] == [
        ("call_start", "event", "Call started"),
        ("call_end", "event", "Call ended"),
    ]


def test_end_writes_local_boundary_even_when_backend_session_control_fails(
    call_fixture: CallFixture,
) -> None:
    call_fixture.backend.fail_end = True
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/end",
        json={"session_id": started["session_id"]},
    )

    assert response.status_code == 200
    assert response.json()["reason"] == "hangup"
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert rows[-1] == ("call_end", "event", "Call ended")


def test_end_rejects_missing_backend_method_instead_of_pretending_backend_ended(
    call_fixture: CallFixture,
) -> None:
    class IncompleteCallBackend:
        pass

    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = IncompleteCallBackend

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/end",
        json={"session_id": started["session_id"]},
    )

    assert response.status_code == 502
    assert _public_error_code(response) == "call_backend_client_misconfigured"
    assert "end_call" in _public_error_message(response)
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert rows[-1] == ("call_start", "event", "Call started")


def test_two_turns_stream_tokens_and_write_exact_speech_rows_before_call_end(
    call_fixture: CallFixture,
) -> None:
    call_fixture.completion.token_sequences = [
        ["First ", "AI answer."],
        ["Second ", "AI answer."],
    ]
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    first = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-1",
            "text": "First user turn.",
            "source": "user_final",
        },
    )
    second = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-2",
            "text": "Second user turn.",
            "source": "user_final",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_events = _sse_events(first.text)
    second_events = _sse_events(second.text)
    assert [event["type"] for event in first_events] == ["ai_token", "ai_token", "state", "ai_done"]
    assert [event["type"] for event in second_events] == ["ai_token", "ai_token", "state", "ai_done"]
    assert first_events[2] == {"type": "state", "turn_id": "turn-1", "state": "rehearsing"}
    assert second_events[2] == {"type": "state", "turn_id": "turn-2", "state": "rehearsing"}
    assert "".join(event.get("text", "") for event in first_events) == "First AI answer."
    assert "".join(event.get("text", "") for event in second_events) == "Second AI answer."

    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    speech_rows = [row for row in rows if row[0] in {"user_speech", "ai_speech"}]
    assert speech_rows == [
        ("user_speech", "user", "First user turn."),
        ("ai_speech", "assistant", "First AI answer."),
        ("user_speech", "user", "Second user turn."),
        ("ai_speech", "assistant", "Second AI answer."),
    ]
    assert [call["payload"]["text"] for call in call_fixture.backend.speak_calls] == [
        "First AI answer.",
        "Second AI answer.",
    ]
    assert all(call["payload"]["reference_audio_base64"] for call in call_fixture.backend.speak_calls)
    assert all(
        call["payload"]["reference_transcript"] == "Reference transcript for the assigned voice."
        for call in call_fixture.backend.speak_calls
    )
    assert all(
        not any(key.startswith("voxcpm2_") for key in call["payload"])
        for call in call_fixture.backend.speak_calls
    )
    assert all(call["session_id"] == started["session_id"] for call in call_fixture.backend.speak_calls)


def test_qwen_normal_multi_segment_turn_persists_once_after_one_normal_terminal(
    call_fixture: CallFixture,
) -> None:
    class SegmentAwareBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            event: dict[str, Any] = {
                "turn_id": payload["turn_id"],
                "tts_playback_final": {"playout_wait_completed": True},
            }
            if payload["final_chunk"]:
                event["type"] = "ai_done"
            else:
                event["status"] = "queued"
            return {"session_id": session_id, "event": event}

    visible_text = (
        "This is the first natural sentence."
        " This is the second natural sentence."
        " A final tail remains"
    )
    call_fixture.completion.token_sequences = [
        [
            "This is the first natural sentence.",
            " This is the second natural sentence.",
            " A final tail remains",
        ]
    ]
    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend = SegmentAwareBackend()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: backend

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-qwen-multi-segment",
            "text": "Speak a longer answer.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    assert [call["payload"]["final_chunk"] for call in backend.speak_calls] == [
        False,
        False,
        True,
    ]
    assert [call["payload"]["segment_ordinal"] for call in backend.speak_calls] == [
        0,
        1,
        2,
    ]
    assert [call["payload"]["segment_id"] for call in backend.speak_calls] == [
        "turn-qwen-multi-segment:0",
        "turn-qwen-multi-segment:1",
        "turn-qwen-multi-segment:2",
    ]
    events = _sse_events(response.text)
    assert sum(event.get("type") == "ai_done" for event in events) == 1
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert [row for row in rows if row[0] == "ai_speech"] == [
        ("ai_speech", "assistant", visible_text)
    ]


def test_concurrent_duplicate_completed_turn_is_reserved_and_persisted_once(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()

    async def scenario() -> None:
        async with call_fixture.sessionmaker() as session:
            service = CallService(session)
            reservation = await service.reserve_call_turn(
                started["call_id"],
                turn_id="turn-duplicate",
                text="User request.",
                task=None,
            )
            assert reservation.created is True
            assert await service.record_reserved_user_speech(
                started["call_id"],
                turn_id="turn-duplicate",
                text="User request.",
            ) is not None
            original_stage = service._stage_message
            stage_entered = asyncio.Event()
            release_stage = asyncio.Event()

            async def delayed_stage(
                thread_id: str,
                content_text: str,
                **kwargs: Any,
            ) -> dict[str, Any]:
                stage_entered.set()
                await release_stage.wait()
                return await original_stage(thread_id, content_text, **kwargs)

            service._stage_message = delayed_stage  # type: ignore[method-assign]
            terminal = SpeechTurnTerminal(status="normal", playout_completed=True)
            first = asyncio.create_task(
                service.record_completed_ai_speech(
                    started["call_id"],
                    turn_id="turn-duplicate",
                    text="Persist exactly once.",
                    terminal=terminal,
                )
            )
            await stage_entered.wait()
            duplicate = await service.record_completed_ai_speech(
                started["call_id"],
                turn_id="turn-duplicate",
                text="Duplicate must not persist.",
                terminal=terminal,
            )
            release_stage.set()
            persisted = await first

            assert persisted is not None
            assert duplicate is None

        async with call_fixture.sessionmaker() as verification_session:
            rows = (
                await verification_session.execute(
                    select(Message).where(
                        Message.call_id == started["call_id"],
                        Message.call_turn_id == "turn-duplicate",
                    )
                )
            ).scalars().all()
            assert [row.content_text for row in rows] == ["Persist exactly once."]

    asyncio.run(scenario())


def test_hangup_marked_during_assistant_append_rolls_back_uncommitted_turn(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()

    async def scenario() -> None:
        async with call_fixture.sessionmaker() as session:
            service = CallService(session)
            reservation = await service.reserve_call_turn(
                started["call_id"],
                turn_id="turn-hangup-race",
                text="User request before hangup.",
                task=None,
            )
            assert reservation.created is True
            assert await service.record_reserved_user_speech(
                started["call_id"],
                turn_id="turn-hangup-race",
                text="User request before hangup.",
            ) is not None
            original_stage = service._stage_message
            stage_entered = asyncio.Event()
            release_stage = asyncio.Event()

            async def delayed_stage(
                thread_id: str,
                content_text: str,
                **kwargs: Any,
            ) -> dict[str, Any]:
                stage_entered.set()
                await release_stage.wait()
                return await original_stage(thread_id, content_text, **kwargs)

            service._stage_message = delayed_stage  # type: ignore[method-assign]
            persistence = asyncio.create_task(
                service.record_completed_ai_speech(
                    started["call_id"],
                    turn_id="turn-hangup-race",
                    text="Never durable after hangup.",
                    terminal=SpeechTurnTerminal(
                        status="normal",
                        playout_completed=True,
                    ),
                )
            )
            await stage_entered.wait()
            ended = await service.begin_end(started["call_id"])
            late_turn = ScriptedCancelableTask()
            release_stage.set()

            assert ended["ended_at"] is not None
            assert await service.register_active_turn(
                started["call_id"],
                late_turn,
            ) is False
            assert late_turn.cancel_calls == 0
            assert await persistence is None

        async with call_fixture.sessionmaker() as verification_session:
            persisted = await verification_session.scalar(
                select(Message.id).where(
                    Message.call_id == started["call_id"],
                    Message.call_turn_id == "turn-hangup-race",
                )
            )
            assert persisted is None

    asyncio.run(scenario())


def test_concurrent_duplicate_turn_endpoint_reuses_reservation_without_replay(
    call_fixture: CallFixture,
) -> None:
    class BlockingCompletion(ScriptedCompletionClient):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()

        async def stream_chat_completion_tokens(
            self,
            settings: Any,
            messages: Any,
        ) -> AsyncIterator[str]:
            self.requests.append({"settings": settings, "messages": list(messages)})
            self.started.set()
            assert await asyncio.to_thread(self.release.wait, 2.0)
            yield "One endpoint execution only."

    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started_call = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()
    calls_module = importlib.import_module("app.api.calls")
    completion = BlockingCompletion()
    call_fixture.app.dependency_overrides[
        calls_module.get_call_completion_client
    ] = lambda: completion
    payload = {
        "session_id": started_call["session_id"],
        "turn_id": "turn-endpoint-duplicate",
        "text": "Run this live turn exactly once.",
        "source": "user_final",
    }
    route = f"/api/calls/{started_call['call_id']}/turns"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(call_fixture.client.post, route, json=payload)
        assert completion.started.wait(2.0)
        duplicate_future = executor.submit(
            call_fixture.client.post,
            route,
            json=payload,
        )
        time.sleep(0.1)
        assert not duplicate_future.done()
        completion.release.set()
        first = first_future.result(timeout=5.0)
        duplicate = duplicate_future.result(timeout=5.0)

    completed_retry = call_fixture.client.post(route, json=payload)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    duplicate_events = _sse_events(duplicate.text)
    assert duplicate_events[0] == {
        "type": "turn_existing",
        "turn_id": "turn-endpoint-duplicate",
        "state": "running",
        "recoverable": False,
    }
    assert duplicate_events[1]["type"] == "ai_done"
    assert duplicate_events[1]["turn_id"] == "turn-endpoint-duplicate"
    assert duplicate_events[1]["existing"] is True
    assert duplicate_events[1]["message"]["content_text"] == (
        "One endpoint execution only."
    )
    assert completed_retry.status_code == 200
    completed_events = _sse_events(completed_retry.text)
    assert len(completed_events) == 1
    assert completed_events[0]["type"] == "ai_done"
    assert completed_events[0]["existing"] is True
    assert completed_events[0]["message"] == duplicate_events[1]["message"]
    assert len(completion.requests) == 1
    assert len(call_fixture.backend.speak_calls) == 1

    async def persisted() -> tuple[list[Message], list[CallTurn]]:
        async with call_fixture.sessionmaker() as session:
            messages = (
                await session.execute(
                    select(Message).where(
                        Message.thread_id == thread_id,
                        Message.message_kind.in_(("user_speech", "ai_speech")),
                    )
                )
            ).scalars().all()
            turns = (
                await session.execute(
                    select(CallTurn).where(
                        CallTurn.call_id == started_call["call_id"],
                        CallTurn.turn_id == "turn-endpoint-duplicate",
                    )
                )
            ).scalars().all()
            return messages, turns

    messages, turns = asyncio.run(persisted())
    assert [(row.message_kind, row.content_text) for row in messages] == [
        ("user_speech", "Run this live turn exactly once."),
        ("ai_speech", "One endpoint execution only."),
    ]
    assert len(turns) == 1
    assert turns[0].state == "completed"
    assert turns[0].user_message_id == messages[0].id
    assert turns[0].assistant_message_id == messages[1].id


def test_reservation_commit_that_persists_then_cancels_is_terminalized_by_owner(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()

    async def scenario() -> tuple[CallTurn, bool, str, int]:
        owner_task = object()
        async with call_fixture.sessionmaker() as session:
            service = CallService(session)
            original_commit = session.commit

            async def commit_then_cancel() -> None:
                await original_commit()
                raise asyncio.CancelledError()

            session.commit = commit_then_cancel  # type: ignore[method-assign]
            with pytest.raises(asyncio.CancelledError):
                await service.reserve_call_turn(
                    started["call_id"],
                    turn_id="turn-reservation-cancelled-after-commit",
                    text="Persist the reservation, then cancel the waiter.",
                    task=owner_task,
                )
            call = service._active_call(started["call_id"])
            owner_removed = (
                "turn-reservation-cancelled-after-commit" not in call.turn_owners
                and owner_task not in call.active_turn_tasks
            )

        async with call_fixture.sessionmaker() as verification_session:
            turn = await verification_session.scalar(
                select(CallTurn).where(
                    CallTurn.call_id == started["call_id"],
                    CallTurn.turn_id == "turn-reservation-cancelled-after-commit",
                )
            )
            assert turn is not None
            retry = await CallService(verification_session).reserve_call_turn(
                started["call_id"],
                turn_id="turn-reservation-cancelled-after-commit",
                text="Persist the reservation, then cancel the waiter.",
                task=None,
            )
            message_count = int(
                await verification_session.scalar(
                    select(func.count(Message.id)).where(
                        Message.thread_id == thread_id,
                        Message.message_kind.in_(("user_speech", "ai_speech")),
                    )
                )
                or 0
            )
            return turn, owner_removed, retry.state, message_count

    turn, owner_removed, retry_state, message_count = asyncio.run(scenario())

    assert turn.state == "cancelled"
    assert turn.owner_token is None
    assert turn.lease_expires_at is None
    assert owner_removed is True
    assert retry_state == "cancelled"
    assert message_count == 0


def test_expired_restart_style_turn_is_failed_without_llm_or_tts_replay(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()
    turn_id = "turn-expired-after-restart"
    text = "Do not replay this abandoned turn."

    async def abandon_owner() -> str:
        async with call_fixture.sessionmaker() as session:
            service = CallService(session)
            reservation = await service.reserve_call_turn(
                started["call_id"],
                turn_id=turn_id,
                text=text,
                task=object(),
            )
            assert reservation.owner_token is not None
            assert await service.record_reserved_user_speech(
                started["call_id"],
                turn_id=turn_id,
                text=text,
                owner_token=reservation.owner_token,
            ) is not None
            await session.execute(
                update(CallTurn)
                .where(
                    CallTurn.call_id == started["call_id"],
                    CallTurn.turn_id == turn_id,
                )
                .values(lease_expires_at=utc_now() - timedelta(seconds=1))
            )
            await session.commit()
            call = service._active_call(started["call_id"])
            call.turn_owners.clear()
            call.turn_owner_tasks.clear()
            call.active_turn_tasks.clear()

        async with call_fixture.sessionmaker() as restart_session:
            assert await CallService(restart_session).reconcile_stale_call_turns() == 1
        return reservation.owner_token

    expired_owner = asyncio.run(abandon_owner())

    route = f"/api/calls/{started['call_id']}/turns"
    payload = {
        "session_id": started["session_id"],
        "turn_id": turn_id,
        "text": text,
        "source": "user_final",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        retries = [
            executor.submit(call_fixture.client.post, route, json=payload)
            for _ in range(2)
        ]
        responses = [retry.result(timeout=5.0) for retry in retries]

    for response in responses:
        assert response.status_code == 200
        assert _sse_events(response.text) == [
            {
                "type": "turn_existing",
                "turn_id": turn_id,
                "state": "failed",
                "recoverable": True,
            }
        ]
    assert call_fixture.completion.requests == []
    assert call_fixture.backend.speak_calls == []

    async def persisted() -> tuple[CallTurn, list[Message], dict[str, Any] | None]:
        async with call_fixture.sessionmaker() as session:
            late_owner_write = await CallService(session).record_completed_ai_speech(
                started["call_id"],
                turn_id=turn_id,
                text="A stale owner must not publish this answer.",
                terminal=SpeechTurnTerminal(
                    status="normal",
                    playout_completed=True,
                ),
                owner_token=expired_owner,
            )
            turn = await session.scalar(
                select(CallTurn).where(
                    CallTurn.call_id == started["call_id"],
                    CallTurn.turn_id == turn_id,
                )
            )
            assert turn is not None
            messages = (
                await session.execute(
                    select(Message).where(
                        Message.thread_id == thread_id,
                        Message.message_kind.in_(("user_speech", "ai_speech")),
                    )
                )
            ).scalars().all()
            return turn, messages, late_owner_write

    turn, messages, late_owner_write = asyncio.run(persisted())
    assert turn.state == "failed"
    assert turn.owner_token is None
    assert turn.lease_expires_at is None
    assert late_owner_write is None
    assert [(message.message_kind, message.content_text) for message in messages] == [
        ("user_speech", text)
    ]


def test_post_hangup_turn_endpoint_rejects_before_history_llm_or_tts(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()
    ended = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/end",
        json={"session_id": started["session_id"], "reason": "hangup"},
    )
    assert ended.status_code == 200
    completion_calls = len(call_fixture.completion.requests)
    speech_calls = len(call_fixture.backend.speak_calls)

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-after-hangup",
            "text": "This must have no durable or model side effect.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    assert _sse_events(response.text) == [
        {
            "type": "error",
            "turn_id": "turn-after-hangup",
            "code": "call_session_not_found",
            "message": "Call session was not found",
        }
    ]
    assert len(call_fixture.completion.requests) == completion_calls
    assert len(call_fixture.backend.speak_calls) == speech_calls

    async def side_effects() -> tuple[int, int]:
        async with call_fixture.sessionmaker() as session:
            message_count = await session.scalar(
                select(func.count(Message.id)).where(
                    Message.thread_id == thread_id,
                    Message.message_kind == "user_speech",
                )
            )
            turn_count = await session.scalar(
                select(func.count(CallTurn.id)).where(
                    CallTurn.call_id == started["call_id"],
                    CallTurn.turn_id == "turn-after-hangup",
                )
            )
            return int(message_count or 0), int(turn_count or 0)

    assert asyncio.run(side_effects()) == (0, 0)


@pytest.mark.parametrize(
    ("terminal_event", "expected_status"),
    [
        pytest.param({"type": "ai_done"}, "error", id="absent"),
        pytest.param(
            {"type": "ai_done", "tts_playback_final": {}},
            "error",
            id="empty",
        ),
        pytest.param(
            {"type": "ai_done", "tts_playback_final": None},
            "error",
            id="null",
        ),
        pytest.param(
            {
                "type": "ai_done",
                "tts_playback_final": {"playout_wait_completed": False},
            },
            "error",
            id="false",
        ),
        pytest.param(
            {
                "type": "ai_done",
                "tts_playback_final": {"playout_wait_completed": 1},
            },
            "error",
            id="integer",
        ),
        pytest.param(
            {
                "type": "ai_done",
                "tts_playback_final": {"playout_wait_completed": "true"},
            },
            "error",
            id="string",
        ),
        pytest.param(
            {
                "type": "ai_done",
                "tts_playback_final": {"playout_wait_completed": True},
            },
            "normal",
            id="literal-true",
        ),
    ],
)
def test_speech_turn_accepts_only_literal_true_final_playout_proof(
    terminal_event: dict[str, Any],
    expected_status: str,
) -> None:
    class TerminalBackend:
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            del base_url, payload
            return {"session_id": session_id, "event": terminal_event}

    async def run_turn() -> Any:
        turn = SpeechTurn(
            backend=TerminalBackend(),
            base_url="https://127.0.0.1:9443",
            session_id="session-playout-proof",
            turn_id="turn-playout-proof",
            voice_id="voice-playout-proof",
            engine_id="qwen3_1_7b",
            voice_reference={},
        )
        return await turn.finalize("Audible only with proof.")

    terminal = asyncio.run(run_turn())

    assert terminal.status == expected_status
    assert terminal.playout_completed is (expected_status == "normal")


def test_qwen_boundary_terminated_turn_still_submits_one_backend_terminal(
    call_fixture: CallFixture,
) -> None:
    class BoundaryAwareBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            event: dict[str, Any] = {
                "turn_id": payload["turn_id"],
                "tts_playback_final": {"playout_wait_completed": True},
            }
            if payload["final_chunk"]:
                event["type"] = "ai_done"
            else:
                event["status"] = "queued"
            return {"session_id": session_id, "event": event}

    visible_text = "This complete Qwen reply ends at its sentence boundary."
    call_fixture.completion.token_sequences = [[visible_text]]
    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend = BoundaryAwareBackend()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: backend

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-qwen-boundary-terminal",
            "text": "Finish this live turn normally.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    assert [call["payload"]["final_chunk"] for call in backend.speak_calls] == [
        False,
        True,
    ]
    assert [call["payload"]["text"] for call in backend.speak_calls] == [
        visible_text,
        "",
    ]
    events = _sse_events(response.text)
    assert sum(event.get("type") == "ai_done" for event in events) == 1
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert [row for row in rows if row[0] == "ai_speech"] == [
        ("ai_speech", "assistant", visible_text)
    ]


@pytest.mark.parametrize("after_audio", [False, True])
def test_cancelled_qwen_turn_never_persists_complete_speech_or_normal_done(
    call_fixture: CallFixture,
    after_audio: bool,
) -> None:
    class CancelledBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            event: dict[str, Any] = {
                "status": "cancelled",
                "turn_id": payload["turn_id"],
            }
            if after_audio:
                event["ai_audio_started_event"] = {
                    "type": "ai_audio_started",
                    "turn_id": payload["turn_id"],
                    "session_id": session_id,
                }
            return {"session_id": session_id, "event": event}

    call_fixture.completion.token_sequences = [["This Qwen answer is cancelled"]]
    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend = CancelledBackend()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: backend

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": f"turn-qwen-cancel-{after_audio}",
            "text": "Cancel this speech.",
            "source": "user_final",
        },
    )

    events = _sse_events(response.text)
    assert any(event.get("type") == "ai_token" for event in events)
    assert not any(event.get("type") == "ai_done" for event in events)
    assert any(event.get("type") == "ai_audio_started" for event in events) is after_audio
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert not any(row[0] == "ai_speech" for row in rows)


def test_qwen_worker_error_is_sanitized_and_does_not_persist_or_emit_normal_done(
    call_fixture: CallFixture,
) -> None:
    class FailingQwenBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            raise AiBackendProcessingError(
                code="qwen3_generation_ceiling",
                message=r"private transcript C:\\Users\\pmpg\\model-cache",
            )

    call_fixture.completion.token_sequences = [["This Qwen answer reaches a ceiling"]]
    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend = FailingQwenBackend()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: backend

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-qwen-ceiling",
            "text": "Trigger the safe ceiling.",
            "source": "user_final",
        },
    )

    events = _sse_events(response.text)
    assert events[-1] == {
        "type": "error",
        "turn_id": "turn-qwen-ceiling",
        "code": "call_tts_failed",
        "message": "Speech playback failed",
    }
    assert not any(event.get("type") == "ai_done" for event in events)
    assert "private transcript" not in response.text
    assert r"C:\\Users" not in response.text
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert not any(row[0] == "ai_speech" for row in rows)


def test_llm_failure_after_first_speech_admission_cancels_backend_turn_once(
    call_fixture: CallFixture,
) -> None:
    speech_admitted = asyncio.Event()

    class FailsAfterSpeechAdmission:
        async def stream_chat_completion_tokens(
            self,
            settings: Any,
            messages: Any,
        ) -> AsyncIterator[str]:
            del settings, messages
            yield "The first spoken sentence is already live."
            while not speech_admitted.is_set():
                await asyncio.sleep(0)
            raise RuntimeError("LLM stream failed after speech admission")

    class AdmissionBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            speech_admitted.set()
            return {
                "session_id": session_id,
                "event": {
                    "status": "queued",
                    "turn_id": payload["turn_id"],
                    "ai_audio_started_event": {
                        "type": "ai_audio_started",
                        "turn_id": payload["turn_id"],
                    },
                },
            }

    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend = AdmissionBackend()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: backend
    call_fixture.app.dependency_overrides[calls_module.get_call_completion_client] = (
        FailsAfterSpeechAdmission
    )

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-llm-fails-after-audio",
            "text": "Start speaking, then fail generation.",
            "source": "user_final",
        },
    )

    events = _sse_events(response.text)
    assert any(event.get("type") == "error" for event in events)
    assert not any(event.get("type") == "ai_done" for event in events)
    assert backend.cancel_turn_calls == [
        {
            "base_url": "https://127.0.0.1:9443",
            "session_id": started["session_id"],
            "turn_id": "turn-llm-fails-after-audio",
        }
    ]


def test_sse_cancellation_after_audio_keeps_one_backend_cancel_alive() -> None:
    class CancelAwareBackend:
        def __init__(self) -> None:
            self.speak_started = asyncio.Event()
            self.cancel_started = asyncio.Event()
            self.release_cancel = asyncio.Event()
            self.cancel_calls: list[str] = []

        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            del base_url, session_id, payload
            self.speak_started.set()
            await asyncio.Future()
            raise AssertionError("unreachable")

        async def cancel_call_turn(
            self,
            base_url: str,
            session_id: str,
            turn_id: str,
        ) -> dict[str, Any]:
            del base_url, session_id
            self.cancel_calls.append(turn_id)
            self.cancel_started.set()
            await self.release_cancel.wait()
            return {"status": "cancelled", "turn_id": turn_id}

    async def scenario() -> None:
        backend = CancelAwareBackend()
        turn = SpeechTurn(
            backend=backend,
            base_url="https://127.0.0.1:9443",
            session_id="session-sse-cancel",
            turn_id="turn-sse-cancel",
            voice_id="voice-qwen",
            engine_id="qwen3_1_7b",
            voice_reference={},
        )
        await turn.submit("Audio began before the SSE connection closed.")
        await backend.speak_started.wait()

        cancelled_request = asyncio.create_task(turn.cancel())
        await backend.cancel_started.wait()
        cancelled_request.cancel()
        terminal = await cancelled_request
        assert terminal.status == "cancelled"
        assert backend.cancel_calls == ["turn-sse-cancel"]

        backend.release_cancel.set()
        retry = await turn.cancel()
        assert retry.status == "cancelled"
        assert backend.cancel_calls == ["turn-sse-cancel"]

    asyncio.run(scenario())


def test_blank_assistant_output_creates_no_speech_request_state_or_persistence(
    call_fixture: CallFixture,
) -> None:
    call_fixture.completion.token_sequences = [["   "]]
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-blank-assistant",
            "text": "Return no spoken text.",
            "source": "user_final",
        },
    )

    events = _sse_events(response.text)
    assert call_fixture.backend.speak_calls == []
    assert not any(event.get("type") == "state" for event in events)
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert not any(row[0] == "ai_speech" for row in rows)


@pytest.mark.parametrize("control_route", ["interrupt", "end"])
def test_terminal_call_control_during_incremental_qwen_turn_writes_no_complete_speech(
    call_fixture: CallFixture,
    control_route: str,
) -> None:
    speech_started = threading.Event()
    release_llm = threading.Event()
    control_received = threading.Event()
    response_holder: list[Any] = []

    class HeldOpenCompletionClient:
        async def stream_chat_completion_tokens(
            self,
            settings: Any,
            messages: Any,
        ) -> AsyncIterator[str]:
            del settings, messages
            yield "This is an early Qwen sentence."
            while not release_llm.is_set():
                await asyncio.sleep(0.01)
            yield " This tail must never persist"

    class ControlledBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            speech_started.set()
            while not control_received.is_set():
                await asyncio.sleep(0.01)
            return {
                "session_id": session_id,
                "event": {"status": "cancelled", "turn_id": payload["turn_id"]},
            }

        async def interrupt_call(self, base_url: str, session_id: str) -> dict[str, Any]:
            control_received.set()
            return await super().interrupt_call(base_url, session_id)

        async def end_call(self, base_url: str, session_id: str, reason: str) -> dict[str, Any]:
            control_received.set()
            return {"session_id": session_id, "reason": reason}

    thread_id, _ = asyncio.run(
        _insert_qwen_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend = ControlledBackend()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: backend
    call_fixture.app.dependency_overrides[calls_module.get_call_completion_client] = (
        HeldOpenCompletionClient
    )

    def request_turn() -> None:
        response_holder.append(
            call_fixture.client.post(
                f"/api/calls/{started['call_id']}/turns",
                json={
                    "session_id": started["session_id"],
                    "turn_id": f"turn-qwen-{control_route}",
                    "text": "Stop this incremental turn.",
                    "source": "user_final",
                },
            )
        )

    request_thread = threading.Thread(target=request_turn, daemon=True)
    request_thread.start()
    try:
        assert speech_started.wait(timeout=2.0)
        control_payload = {"session_id": started["session_id"]}
        if control_route == "end":
            control_payload["reason"] = "hangup"
        control_response = call_fixture.client.post(
            f"/api/calls/{started['call_id']}/{control_route}",
            json=control_payload,
        )
        assert control_response.status_code == 200
    finally:
        release_llm.set()
        control_received.set()
        request_thread.join(timeout=3.0)

    assert not request_thread.is_alive()
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert not any(row[0] == "ai_speech" for row in rows)
    if response_holder:
        assert not any(
            event.get("type") == "ai_done"
            for event in _sse_events(response_holder[0].text)
        )


def test_speech_turn_rejects_post_cancel_submission_and_a_later_turn_can_finish() -> None:
    class RecoverableBackend:
        def __init__(self) -> None:
            self.calls = 0

        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            del base_url, session_id
            self.calls += 1
            if self.calls == 1:
                return {"event": {"status": "cancelled", "turn_id": payload["turn_id"]}}
            return {
                "event": {
                    "type": "ai_done",
                    "turn_id": payload["turn_id"],
                    "tts_playback_final": {"playout_wait_completed": True},
                }
            }

    async def scenario() -> None:
        backend = RecoverableBackend()
        first = SpeechTurn(
            backend=backend,
            base_url="https://127.0.0.1:9443",
            session_id="session-one",
            turn_id="turn-cancelled",
            voice_id="voice-one",
            engine_id="qwen3_1_7b",
            voice_reference={},
        )
        cancelled = await first.finalize("Cancel this sentence")
        assert cancelled.status == "cancelled"
        assert cancelled.playout_completed is False
        with pytest.raises(SpeechTurnClosedError):
            await first.submit("late private segment")

        second = SpeechTurn(
            backend=backend,
            base_url="https://127.0.0.1:9443",
            session_id="session-two",
            turn_id="turn-normal",
            voice_id="voice-two",
            engine_id="qwen3_1_7b",
            voice_reference={},
        )
        normal = await second.finalize("A later turn succeeds")
        assert normal.status == "normal"
        assert normal.playout_completed is True

    asyncio.run(scenario())


def test_voxcpm2_call_voice_reference_forwards_mode_and_style(
    call_fixture: CallFixture,
) -> None:
    call_fixture.completion.token_sequences = [["VoxCPM2 call reply."]]
    thread_id = asyncio.run(_insert_voxcpm2_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    expected_voxcpm2_fields = {
        "voxcpm2_cloning_mode": "transcript_guided",
        "voxcpm2_style_prompt": "warm phone call voice",
        "voxcpm2_cfg_value": 2.4,
        "voxcpm2_inference_timesteps": 12,
        "voxcpm2_normalize": True,
        "voxcpm2_denoise": False,
    }

    voice_reference = asyncio.run(
        _voice_reference_for_started_call(
            call_fixture.sessionmaker,
            started["call_id"],
            call_fixture.voice_blob_dir,
        )
    )

    assert voice_reference["reference_audio_base64"]
    assert voice_reference["reference_transcript"] == "Saved VoxCPM2 transcript."

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-voxcpm2",
            "text": "Use the saved VoxCPM2 voice.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    assert call_fixture.backend.speak_calls
    speak_payload = call_fixture.backend.speak_calls[-1]["payload"]
    assert speak_payload["voice_id"] == started["voice_id"]
    assert speak_payload["engine_id"] == "voxcpm2"
    assert not any("voxcpm2" in getattr(route, "path", "") for route in call_fixture.app.routes)
    assert (
        {key: voice_reference.get(key) for key in expected_voxcpm2_fields},
        {key: speak_payload.get(key) for key in expected_voxcpm2_fields},
    ) == (expected_voxcpm2_fields, expected_voxcpm2_fields)


def test_f5_call_turn_uses_standard_turns_route_without_engine_route(
    call_fixture: CallFixture,
) -> None:
    call_fixture.completion.token_sequences = [["F5 call reply."]]
    thread_id = asyncio.run(_insert_f5_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-f5",
            "text": "Use the saved F5 voice.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    assert call_fixture.backend.speak_calls[-1]["payload"]["engine_id"] == "f5"
    assert not any("voxcpm2" in getattr(route, "path", "") for route in call_fixture.app.routes)


def test_voxcpm2_call_tts_failure_is_sanitized_and_truthful(
    call_fixture: CallFixture,
) -> None:
    class FailingVoxCpm2CallBackend(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            from app.domain.ai_backend_client import AiBackendProcessingError

            raise AiBackendProcessingError(
                code="call_tts_failed",
                message=(
                    "Traceback in /home/pmpg/.cache/huggingface/openbmb/VoxCPM2 "
                    r"C:\Users\pmpg\rayme\model-cache"
                ),
            )

    call_fixture.completion.token_sequences = [["Audio will fail after text."]]
    failing_backend = FailingVoxCpm2CallBackend()
    calls_module = importlib.import_module("app.api.calls")
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = lambda: failing_backend
    thread_id = asyncio.run(_insert_voxcpm2_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-voxcpm2-failure",
            "text": "Persist this exact VoxCPM2 user speech.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert {
        "type": "error",
        "turn_id": "turn-voxcpm2-failure",
        "code": "call_tts_failed",
        "message": "Speech playback failed",
    } in events
    public_body = json.dumps(events)
    assert "Traceback" not in public_body
    assert "/home/" not in public_body
    assert r"C:\\" not in public_body
    assert "openbmb/VoxCPM2" not in public_body
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert ("user_speech", "user", "Persist this exact VoxCPM2 user speech.") in rows
    assert not any(row[0] == "ai_speech" for row in rows)
    assert failing_backend.speak_calls[-1]["payload"]["engine_id"] == "voxcpm2"


def test_turn_generation_failure_preserves_user_speech_and_returns_fixed_code(
    call_fixture: CallFixture,
) -> None:
    call_fixture.completion.fail_next = True
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-fail",
            "text": "Persist this user speech.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert events == [
        {
            "type": "error",
            "turn_id": "turn-fail",
            "code": "call_generation_failed",
            "message": "AI generation failed",
        }
    ]
    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    assert ("user_speech", "user", "Persist this user speech.") in rows
    assert not any(row[0] == "ai_speech" for row in rows)


def test_turn_yields_ai_audio_started_event_when_nested_inside_speak_result_event(
    call_fixture: CallFixture,
) -> None:
    """ai_audio_started SSE event must be emitted when ai_audio_started_event is
    nested inside speak_result["event"], not at the speak_result top level.

    Regression for: _speak_call returns {"session_id":…, "turn_id":…, "state":…,
    "event": {"type":"ai_done", …, "ai_audio_started_event": {…}}}. The old code
    checked speak_result.get("ai_audio_started_event") which always returned None
    because the key is inside speak_result["event"]. The SSE ai_audio_started event
    was therefore never sent to the browser, so the client never knew audio was
    playing.
    """

    class BackendWithNestedAudioStarted(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            return {
                "session_id": session_id,
                "turn_id": payload.get("turn_id"),
                "state": "speaking",
                "event": {
                    "type": "ai_done",
                    "turn_id": payload.get("turn_id"),
                    "ai_audio_started_event": {
                        "type": "ai_audio_started",
                        "turn_id": payload.get("turn_id"),
                        "session_id": session_id,
                    },
                },
            }

    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()

    calls_module = importlib.import_module("app.api.calls")
    backend_with_audio = BackendWithNestedAudioStarted()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = (
        lambda: backend_with_audio
    )

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-audio-started",
            "text": "Say something.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    event_types = [e["type"] for e in events]
    assert "ai_audio_started" in event_types, (
        f"Expected ai_audio_started SSE event but got: {event_types}. "
        "ai_audio_started_event nested inside speak_result['event'] was not surfaced."
    )
    audio_started_events = [e for e in events if e["type"] == "ai_audio_started"]
    assert audio_started_events[0]["turn_id"] == "turn-audio-started"


def test_turn_forwards_streaming_audio_started_metrics_without_extra_speech_rows(
    call_fixture: CallFixture,
) -> None:
    class BackendWithStreamingAudioMetrics(ScriptedCallBackend):
        async def speak_call(
            self,
            base_url: str,
            session_id: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.speak_calls.append(
                {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
            )
            return {
                "session_id": session_id,
                "event": {
                    "type": "ai_done",
                    "ai_audio_started_event": {
                        "type": "ai_audio_started",
                        "tts_playback": {
                            "streaming_used": True,
                            "fallback_used": False,
                            "whole_wav_fallback_used": False,
                            "chunk_count_at_start": 1,
                            "first_chunk_generated_ms": 390.0,
                            "first_chunk_enqueued_ms": 410.0,
                            "ai_audio_started_ms": 412.0,
                            "inter_chunk_gaps_ms": [],
                        },
                    },
                    "tts_playback_final": {
                        "streaming_used": True,
                        "fallback_used": False,
                        "whole_wav_fallback_used": False,
                        "playout_wait_completed": True,
                        "chunk_count": 3,
                        "total_generation_ms": 1800.0,
                        "total_playback_ms": 1700.0,
                        "inter_chunk_gaps_ms": [22.0, 31.0],
                    },
                },
            }

    call_fixture.completion.token_sequences = [["Streaming ", "AI reply."]]
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    backend_with_metrics = BackendWithStreamingAudioMetrics()
    call_fixture.app.dependency_overrides[calls_module.get_call_backend_client] = (
        lambda: backend_with_metrics
    )

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/turns",
        json={
            "session_id": started["session_id"],
            "turn_id": "turn-streaming-audio-metrics",
            "text": "Speak with streaming audio metrics.",
            "source": "user_final",
        },
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    audio_started_events = [event for event in events if event["type"] == "ai_audio_started"]
    assert len(audio_started_events) == 1
    tts_playback = audio_started_events[0]["tts_playback"]
    assert tts_playback["chunk_count_at_start"] == 1
    assert "total_generation_ms" not in tts_playback
    assert "total_playback_ms" not in tts_playback

    rows = asyncio.run(_message_kinds(call_fixture.sessionmaker, thread_id))
    speech_rows = [row for row in rows if row[0] == "ai_speech"]
    assert speech_rows == [("ai_speech", "assistant", "Streaming AI reply.")]


def test_interrupt_cancels_server_generation_and_ai_backend_session(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    scripted_task = ScriptedCancelableTask()

    async def register_task() -> None:
        async with call_fixture.sessionmaker() as session:
            registered = await CallService(session).register_active_turn(
                started["call_id"],
                scripted_task,
            )
            assert registered is True

    asyncio.run(register_task())

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/interrupt",
        json={"session_id": started["session_id"]},
    )

    assert response.status_code == 200
    assert scripted_task.cancel_calls == 1
    assert call_fixture.backend.interrupt_calls == [
        {"base_url": "https://127.0.0.1:9443", "session_id": started["session_id"]}
    ]
    assert response.json()["receiver_drain_ms"] == 250
    assert response.json()["cancelled_turn_id"] == "turn-interrupted-01"


@pytest.mark.parametrize(
    "backend_payload",
    [
        {"receiver_drain_ms": 0.1},
        {"receiver_drain_ms": True},
        {"receiver_drain_ms": "250"},
        {"receiver_drain_ms": -1},
        {},
        {"receiver_drain_ms": 501},
    ],
)
def test_interrupt_uses_safe_default_for_invalid_backend_drain_contract(
    call_fixture: CallFixture,
    backend_payload: dict[str, Any],
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()
    call_fixture.backend.interrupt_result = {
        "session_id": started["session_id"],
        "interrupted": True,
        **backend_payload,
    }

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/interrupt",
        json={"session_id": started["session_id"]},
    )

    assert response.status_code == 200
    assert response.json()["receiver_drain_ms"] == 250


def test_call_control_cancels_and_awaits_every_active_turn_task(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(
        _insert_thread_with_character_and_voice(call_fixture.sessionmaker)
    )
    started = call_fixture.client.post(
        "/api/calls/start",
        json={"thread_id": thread_id},
    ).json()

    async def scenario() -> None:
        stopped: list[str] = []

        async def active_turn(name: str) -> None:
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                stopped.append(name)

        tasks = {
            asyncio.create_task(active_turn("first")),
            asyncio.create_task(active_turn("second")),
        }
        async with call_fixture.sessionmaker() as session:
            service = CallService(session)
            for task in tasks:
                assert await service.register_active_turn(started["call_id"], task)
            await asyncio.sleep(0)

            await service.cancel_active_turns(started["call_id"])

            assert all(task.done() for task in tasks)
            assert sorted(stopped) == ["first", "second"]
            assert service._active_call(started["call_id"]).active_turn_tasks == set()

    asyncio.run(scenario())


def _install_test_dependencies(
    app: FastAPI,
    sessionmaker: async_sessionmaker,
    backend: ScriptedCallBackend,
    completion: ScriptedCompletionClient,
    voice_blob_dir: Path,
) -> None:
    async def override_session() -> AsyncIterator[Any]:
        async with sessionmaker() as session:
            yield session

    for dependency in (
        get_character_session,
        get_chat_session,
        get_thread_session,
        get_voice_session,
    ):
        app.dependency_overrides[dependency] = override_session

    try:
        calls_module = importlib.import_module("app.api.calls")
    except ModuleNotFoundError:
        return

    for name in ("get_call_session", "get_calls_session"):
        dependency = getattr(calls_module, name, None)
        if dependency is not None:
            app.dependency_overrides[dependency] = override_session

    for name in ("get_call_backend", "get_call_backend_client", "get_ai_backend_call_client"):
        dependency = getattr(calls_module, name, None)
        if dependency is not None:
            app.dependency_overrides[dependency] = lambda: backend

    completion_dependency = getattr(calls_module, "get_call_completion_client", None)
    if completion_dependency is not None:
        app.dependency_overrides[completion_dependency] = lambda: completion

    voice_blob_dependency = getattr(calls_module, "get_call_voice_blob_dir", None)
    if voice_blob_dependency is not None:
        app.dependency_overrides[voice_blob_dependency] = lambda: voice_blob_dir


async def _insert_thread_with_character_and_voice(sessionmaker: async_sessionmaker) -> str:
    character_id = await _insert_character_with_voice(sessionmaker)
    return await _insert_thread(sessionmaker, character_id=character_id)


async def _insert_voxcpm2_thread_with_character_and_voice(sessionmaker: async_sessionmaker) -> str:
    character_id = "char_voxcpm2_call_ready"
    voice_id = f"voice_{character_id}"
    await _insert_voice(
        sessionmaker,
        voice_id=voice_id,
        default_engine="voxcpm2",
        reference_transcript="Saved VoxCPM2 transcript.",
        metadata={
            "engine_settings": {
                "voxcpm2": {
                    "cloning_mode": "transcript_guided",
                    "style_prompt": "warm phone call voice",
                    "cfg_value": 2.4,
                    "inference_timesteps": 12,
                    "normalize": True,
                    "denoise": False,
                }
            }
        },
    )
    await _insert_character(sessionmaker, character_id=character_id, default_voice_id=voice_id)
    return await _insert_thread(
        sessionmaker,
        character_id=character_id,
        thread_id="thread_voxcpm2_call_ready",
    )


async def _insert_qwen_thread_with_character_and_voice(
    sessionmaker: async_sessionmaker,
    *,
    invalid_reference: str | None = None,
) -> tuple[str, str]:
    character_id = "char_qwen_call_ready"
    voice_id = f"voice_{character_id}"
    reference_bytes = b"voice sample bytes"
    reference_transcript = "Reference transcript for Qwen call preparation."
    await _insert_voice(
        sessionmaker,
        voice_id=voice_id,
        default_engine="qwen3_1_7b",
        reference_transcript=reference_transcript,
        metadata={},
    )
    if invalid_reference == "unsafe_path":
        async with sessionmaker() as session:
            asset = await session.scalar(
                select(VoiceAsset).where(VoiceAsset.voice_id == voice_id)
            )
            assert asset is not None
            asset.storage_path = "../private.wav"
            await session.commit()
    await _insert_character(sessionmaker, character_id=character_id, default_voice_id=voice_id)
    thread_id = await _insert_thread(
        sessionmaker,
        character_id=character_id,
        thread_id="thread_qwen_call_ready",
    )
    return thread_id, voice_id


def _qwen_test_voice_key(
    saved_voice_id: str = "voice_char_qwen_call_ready",
) -> str:
    return hashlib.sha256(
        f"rayme:qwen3_1_7b:{saved_voice_id}".encode("utf-8")
    ).hexdigest()


async def _insert_f5_thread_with_character_and_voice(sessionmaker: async_sessionmaker) -> str:
    character_id = "char_f5_call_ready"
    voice_id = f"voice_{character_id}"
    await _insert_voice(
        sessionmaker,
        voice_id=voice_id,
        default_engine="f5",
        reference_transcript="Saved F5 transcript.",
    )
    await _insert_character(sessionmaker, character_id=character_id, default_voice_id=voice_id)
    return await _insert_thread(
        sessionmaker,
        character_id=character_id,
        thread_id="thread_f5_call_ready",
    )


async def _insert_character_with_voice(
    sessionmaker: async_sessionmaker,
    *,
    character_id: str = "char_call_ready",
    voice_deleted: bool = False,
) -> str:
    voice_id = f"voice_{character_id}"
    await _insert_voice(sessionmaker, voice_id=voice_id, deleted=voice_deleted)
    return await _insert_character(sessionmaker, character_id=character_id, default_voice_id=voice_id)


async def _insert_voice(
    sessionmaker: async_sessionmaker,
    *,
    voice_id: str,
    deleted: bool = False,
    default_engine: str = "F5-TTS",
    reference_transcript: str = "Reference transcript for the assigned voice.",
    metadata: dict[str, Any] | None = None,
) -> None:
    sample_bytes = b"voice sample bytes"
    if _TEST_VOICE_BLOB_DIR is not None:
        _TEST_VOICE_BLOB_DIR.mkdir(parents=True, exist_ok=True)
        (_TEST_VOICE_BLOB_DIR / f"voice_asset_{voice_id}.wav").write_bytes(sample_bytes)
    async with sessionmaker() as session:
        voice = Voice(
            id=voice_id,
            name=f"Voice {voice_id}",
            default_engine=default_engine,
            reference_transcript=reference_transcript,
            metadata_json=dict(metadata or {}),
        )
        if deleted:
            from app.storage.models import utc_now

            voice.deleted_at = utc_now()
        session.add(voice)
        session.add(
            VoiceAsset(
                id=f"voice_asset_{voice_id}",
                voice_id=voice_id,
                asset_kind="sample",
                storage_path=f"voice_asset_{voice_id}.wav",
                content_type="audio/wav",
                byte_size=len(sample_bytes),
                sha256=hashlib.sha256(sample_bytes).hexdigest(),
                duration_seconds=7.0,
                sample_rate_hz=24000,
                channel_count=1,
            )
        )
        await session.commit()


async def _voice_reference_for_started_call(
    sessionmaker: async_sessionmaker,
    call_id: str,
    voice_blob_dir: Path,
) -> dict[str, Any]:
    async with sessionmaker() as session:
        return await CallService(session).voice_reference_for_call(call_id, voice_blob_dir)


async def _insert_character(
    sessionmaker: async_sessionmaker,
    *,
    character_id: str,
    default_voice_id: str | None,
) -> str:
    async with sessionmaker() as session:
        session.add(
            Character(
                id=character_id,
                name=f"Character {character_id}",
                description="description",
                personality="personality",
                scenario="scenario",
                first_mes="Opening from card.",
                system_prompt="system",
                default_voice_id=default_voice_id,
                raw_source_json={"spec": "chara_card_v3"},
            )
        )
        await session.commit()
        return character_id


async def _insert_thread(
    sessionmaker: async_sessionmaker,
    *,
    character_id: str,
    thread_id: str = "thread_call_ready",
) -> str:
    async with sessionmaker() as session:
        thread = Thread(
            id=thread_id,
            character_id=character_id,
            title="Call Thread",
            character_snapshot_name="Call Character",
            character_snapshot_description="description",
            character_snapshot_personality="personality",
            character_snapshot_scenario="scenario",
            character_snapshot_first_mes="Opening from card.",
            character_snapshot_system_prompt="system",
            character_snapshot_raw_source_json={"spec": "chara_card_v3"},
        )
        session.add(thread)
        await session.flush()
        session.add(
            Message(
                id=f"msg_opening_{thread_id}",
                thread_id=thread_id,
                message_kind="ai_text",
                role="assistant",
                sequence=0,
                content_text="Opening from card.",
            )
        )
        await session.commit()
        return thread_id


async def _thread_character_id(sessionmaker: async_sessionmaker, thread_id: str) -> str | None:
    async with sessionmaker() as session:
        result = await session.execute(select(Thread.character_id).where(Thread.id == thread_id))
        return result.scalar_one_or_none()


async def _message_kinds(sessionmaker: async_sessionmaker, thread_id: str) -> list[tuple[str, str, str | None]]:
    async with sessionmaker() as session:
        result = await session.execute(
            select(Message.message_kind, Message.role, Message.content_text)
            .where(Message.thread_id == thread_id)
            .order_by(Message.sequence)
        )
        return [(kind, role, content) for kind, role, content in result.all()]


def _public_error_code(response: Any) -> str | None:
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("code")
    return None


def _public_error_message(response: Any) -> str | None:
    detail = response.json().get("detail")
    if isinstance(detail, dict):
        return detail.get("message")
    return None


def _unsafe_call_payload(route_suffix: str, session_id: str) -> dict[str, Any]:
    if route_suffix == "/offer":
        return {
            "session_id": session_id,
            "offer": {"type": "offer", "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"},
        }
    if route_suffix == "/peer-promotion":
        return {
            "session_id": session_id,
            "generation": 1,
            "action": "commit",
        }
    if route_suffix == "/mute":
        return {"session_id": session_id, "muted": True}
    if route_suffix == "/interrupt":
        return {"session_id": session_id, "reason": "button"}
    if route_suffix == "/turns":
        return {
            "session_id": session_id,
            "turn_id": "turn-origin-check",
            "text": "This should be rejected before call state changes.",
            "source": "user_final",
        }
    if route_suffix == "/reconnect-audio":
        return {
            "session_id": session_id,
            "pcm_b64": "AA==",
            "sample_rate": 16000,
            "channels": 1,
            "backfill_id": "origin-check",
        }
    if route_suffix == "/events/recover":
        return {"session_id": session_id}
    if route_suffix == "/end":
        return {"session_id": session_id, "reason": "hangup"}
    if route_suffix == "/_debug/event":
        return {
            "event": "origin-check",
            "session_id": session_id,
            "detail": {"route": route_suffix},
        }
    raise AssertionError(f"Unhandled unsafe call route suffix: {route_suffix}")


def _backend_call_snapshot(backend: ScriptedCallBackend) -> dict[str, list[dict[str, Any]]]:
    return {
        "created_sessions": [dict(item) for item in backend.created_sessions],
        "offer_calls": [dict(item) for item in backend.offer_calls],
        "backfill_calls": [dict(item) for item in backend.backfill_calls],
        "speak_calls": [dict(item) for item in backend.speak_calls],
        "interrupt_calls": [dict(item) for item in backend.interrupt_calls],
    }


def _sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        if isinstance(payload, dict):
            events.append(payload)
    return events
