"""Phase 1 vertical-slice API acceptance."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.characters import get_character_session, get_portrait_blob_dir
from app.api.chat import get_chat_completion_client, get_chat_session
from app.api.messages import get_message_action_session, get_message_completion_client
from app.api.threads import get_thread_session
from app.config import Settings
from app.domain.llm_stream import ChatCompletionSettings
from app.main import create_app
from app.storage.models import Base
from app.storage.session import create_engine

CARD_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cards"


class ScriptedCompletionClient:
    def __init__(self) -> None:
        self.responses = [
            ["Streamed ", "backend reply"],
            ["Regenerated backend response"],
            ["Swipe backend alternate"],
            ["Continue backend extension"],
            ["Reload follow-up response"],
        ]
        self.requests: list[dict[str, object]] = []

    async def stream_chat_completion_tokens(
        self,
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ):
        self.requests.append({"settings": settings, "messages": list(messages)})
        for token in self.responses.pop(0):
            yield token


@pytest.fixture()
def phase1_client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, async_sessionmaker, ScriptedCompletionClient]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-phase1.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    scripted_client = ScriptedCompletionClient()
    app = create_app(
        Settings(
            web_public_url="https://192.168.1.199:8443",
            ai_backend_base_url="https://192.168.1.199:9443",
            llm_base_url="http://server-llm.local/v1",
            llm_model="server-model",
            llm_api_key="server-secret",
        ),
        static_client_dir=None,
    )

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_character_session] = override_session
    app.dependency_overrides[get_thread_session] = override_session
    app.dependency_overrides[get_chat_session] = override_session
    app.dependency_overrides[get_message_action_session] = override_session
    app.dependency_overrides[get_chat_completion_client] = lambda: scripted_client
    app.dependency_overrides[get_message_completion_client] = lambda: scripted_client
    app.dependency_overrides[get_portrait_blob_dir] = lambda: tmp_path / "portraits"

    with TestClient(app) as client:
        yield client, sessionmaker, scripted_client

    asyncio.run(engine.dispose())


def test_phase1_import_chat_actions_reload_and_continue(
    phase1_client: tuple[TestClient, async_sessionmaker, ScriptedCompletionClient],
) -> None:
    client, _sessionmaker, scripted_client = phase1_client
    fixture = CARD_FIXTURE_DIR / "v3_card.json"

    import_response = client.post(
        "/api/characters/import",
        files={"file": (fixture.name, fixture.read_bytes(), "application/json")},
    )

    assert import_response.status_code == 201
    imported = import_response.json()
    assert imported["name"] == "RayMe Fixture V3"
    assert imported["character"]["id"] == imported["id"]
    assert imported["lorebook_present"] is True
    assert "Lorebook present - not used in v1" in imported["warnings"]

    character_id = imported["id"]
    patch_response = client.patch(
        f"/api/characters/{character_id}",
        json=_character_payload(imported, description="Saved review description."),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["description"] == "Saved review description."

    create_thread_response = client.post(
        "/api/threads",
        json={"character_id": character_id, "alternate_greeting_index": 1},
    )

    assert create_thread_response.status_code == 201
    thread_id = create_thread_response.json()["thread_id"]
    opening = client.get(f"/api/threads/{thread_id}").json()["messages"][0]
    assert opening["content_text"] == "V3 Alternate greeting two."
    assert opening["alternates"][0]["alternate_index"] == 1
    assert opening["alternates"][0]["source_action"] == "first_mes"

    send_response = client.post(f"/api/chat/{thread_id}/send", json={"content": "First turn"})
    assert send_response.status_code == 200
    send_events = _sse_events(send_response.text)
    assert send_events[0] == {"type": "token", "text": "Streamed "}
    assert send_events[1] == {"type": "token", "text": "backend reply"}
    first_ai_message = send_events[-1]["message"]
    assert first_ai_message["content_text"] == "Streamed backend reply"

    regenerated = client.post(f"/api/messages/{first_ai_message['id']}/regenerate").json()
    assert regenerated["id"] == first_ai_message["id"]
    assert regenerated["content_text"] == "Regenerated backend response"
    assert regenerated["alternates"][-1]["source_action"] == "regenerate"
    assert regenerated["selected_alternate_id"] == regenerated["alternates"][-1]["id"]

    swiped = client.post(f"/api/messages/{first_ai_message['id']}/swipes").json()
    assert swiped["selected_alternate_id"] == swiped["alternates"][-1]["id"]
    assert swiped["alternates"][-1]["source_action"] == "swipe"
    assert swiped["content_text"] == "Swipe backend alternate"

    continued = client.post(
        f"/api/messages/{first_ai_message['id']}/continue",
        json={"composer_text": "extend this branch"},
    ).json()
    assert continued["selected_alternate_id"] == continued["alternates"][-1]["id"]
    assert continued["alternates"][-1]["source_action"] == "continue"
    assert continued["content_text"] == "Continue backend extension"

    reloaded = client.get(f"/api/threads/{thread_id}").json()
    selected_ai_turn = next(message for message in reloaded["messages"] if message["id"] == first_ai_message["id"])
    assert selected_ai_turn["content_text"] == "Continue backend extension"

    second_send = client.post(
        f"/api/chat/{thread_id}/send",
        json={"content": "Continue after reload"},
    )
    assert second_send.status_code == 200
    second_events = _sse_events(second_send.text)
    assert second_events[-1]["message"]["content_text"] == "Reload follow-up response"
    final_detail = client.get(f"/api/threads/{thread_id}").json()
    assert final_detail["id"] == thread_id
    assert final_detail["messages"][-1]["content_text"] == "Reload follow-up response"
    assert len(scripted_client.requests) == 5
    assert all(
        request["settings"]
        == ChatCompletionSettings(
            base_url="http://server-llm.local/v1",
            model="server-model",
            api_key="server-secret",
            disable_thinking=True,
        )
        for request in scripted_client.requests
    )
    prompt_text = "\n".join(
        message["content"] for message in scripted_client.requests[-1]["messages"]  # type: ignore[index]
    )
    assert "Continue backend extension" in prompt_text
    assert "server-secret" not in prompt_text


def _character_payload(source: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": source["name"],
        "description": source.get("description"),
        "personality": source.get("personality"),
        "scenario": source.get("scenario"),
        "first_mes": source.get("first_mes"),
        "mes_example": source.get("mes_example"),
        "system_prompt": source.get("system_prompt"),
        "creator_notes": source.get("creator_notes"),
        "character_notes": source.get("character_notes"),
        "tags": source.get("tags") or [],
        "alternate_greetings": source.get("alternate_greetings") or [],
        "post_history_instructions": source.get("post_history_instructions"),
        "creator": source.get("creator"),
        "character_version": source.get("character_version"),
    }
    payload.update(overrides)
    return payload


def _sse_events(body: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
