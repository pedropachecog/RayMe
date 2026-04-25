"""RED contracts for Web UI call bootstrap, controls, and durable writeback."""

from __future__ import annotations

import asyncio
import importlib
import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.characters import get_character_session
from app.api.chat import get_chat_session
from app.api.threads import get_thread_session
from app.api.voices import get_voice_session
from app.main import create_app
from app.storage.models import Base, Character, Message, Thread, Voice, VoiceAsset
from app.storage.session import create_engine


@dataclass(frozen=True, slots=True)
class CallFixture:
    client: TestClient
    sessionmaker: async_sessionmaker
    backend: "FakeCallBackend"
    completion: "FakeCompletionClient"
    voice_blob_dir: Path


_TEST_VOICE_BLOB_DIR: Path | None = None


class FakeCallBackend:
    def __init__(self, *, ready: bool = True, voice_available: bool = True) -> None:
        self.ready = ready
        self.voice_available = voice_available
        self.fail_end = False
        self.created_sessions: list[dict[str, Any]] = []
        self.speak_calls: list[dict[str, Any]] = []
        self.interrupt_calls: list[dict[str, Any]] = []

    async def readiness(self) -> dict[str, Any]:
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

    async def speak_call(
        self,
        base_url: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.speak_calls.append(
            {"base_url": base_url, "session_id": session_id, "payload": dict(payload)}
        )
        return {"session_id": session_id, "event": {"type": "ai_done"}}

    async def interrupt_call(self, base_url: str, session_id: str) -> dict[str, Any]:
        self.interrupt_calls.append({"base_url": base_url, "session_id": session_id})
        return {"session_id": session_id, "interrupted": True}

    async def end_call(self, base_url: str, session_id: str, reason: str) -> dict[str, Any]:
        if self.fail_end:
            from app.domain.ai_backend_client import AiBackendProcessingError

            raise AiBackendProcessingError(code="call_control_failed", message="Call control request failed")
        return {"session_id": session_id, "reason": reason}


class FakeCompletionClient:
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


class FakeCancelableTask:
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

    backend = FakeCallBackend()
    completion = FakeCompletionClient()
    app = create_app(static_client_dir=None)
    voice_blob_dir = tmp_path / "blobs" / "voices"
    global _TEST_VOICE_BLOB_DIR
    _TEST_VOICE_BLOB_DIR = voice_blob_dir
    _install_test_dependencies(app, sessionmaker, backend, completion, voice_blob_dir)

    with TestClient(app) as client:
        yield CallFixture(
            client=client,
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
        json={"session_id": "ai_session_foreign", "muted": True, "sdp": "fake-offer", "type": "offer"},
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
    assert [event["type"] for event in first_events] == ["ai_token", "ai_token", "ai_done"]
    assert [event["type"] for event in second_events] == ["ai_token", "ai_token", "ai_done"]
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
    assert all(call["session_id"] == started["session_id"] for call in call_fixture.backend.speak_calls)


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


def test_interrupt_cancels_server_generation_and_ai_backend_session(
    call_fixture: CallFixture,
) -> None:
    thread_id = asyncio.run(_insert_thread_with_character_and_voice(call_fixture.sessionmaker))
    started = call_fixture.client.post("/api/calls/start", json={"thread_id": thread_id}).json()
    calls_module = importlib.import_module("app.api.calls")
    fake_task = FakeCancelableTask()
    calls_module._ACTIVE_LLM_TURNS[started["call_id"]] = fake_task

    response = call_fixture.client.post(
        f"/api/calls/{started['call_id']}/interrupt",
        json={"session_id": started["session_id"]},
    )

    assert response.status_code == 200
    assert fake_task.cancel_calls == 1
    assert call_fixture.backend.interrupt_calls == [
        {"base_url": "https://127.0.0.1:9443", "session_id": started["session_id"]}
    ]


def _install_test_dependencies(
    app: FastAPI,
    sessionmaker: async_sessionmaker,
    backend: FakeCallBackend,
    completion: FakeCompletionClient,
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


async def _insert_character_with_voice(
    sessionmaker: async_sessionmaker,
    *,
    character_id: str = "char_call_ready",
    voice_deleted: bool = False,
) -> str:
    voice_id = f"voice_{character_id}"
    await _insert_voice(sessionmaker, voice_id=voice_id, deleted=voice_deleted)
    return await _insert_character(sessionmaker, character_id=character_id, default_voice_id=voice_id)


async def _insert_voice(sessionmaker: async_sessionmaker, *, voice_id: str, deleted: bool = False) -> None:
    if _TEST_VOICE_BLOB_DIR is not None:
        _TEST_VOICE_BLOB_DIR.mkdir(parents=True, exist_ok=True)
        (_TEST_VOICE_BLOB_DIR / f"voice_asset_{voice_id}.wav").write_bytes(b"voice sample bytes")
    async with sessionmaker() as session:
        voice = Voice(
            id=voice_id,
            name=f"Voice {voice_id}",
            default_engine="F5-TTS",
            reference_transcript="Reference transcript for the assigned voice.",
            metadata_json={},
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
                byte_size=256,
                sha256="0" * 64,
                duration_seconds=7.0,
                sample_rate_hz=24000,
                channel_count=1,
            )
        )
        await session.commit()


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


def _sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        if isinstance(payload, dict):
            events.append(payload)
    return events
