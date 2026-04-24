"""Thread creation, hydration, list, rename, and delete route tests."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.threads import get_thread_session
from app.main import create_app
from app.storage.models import Base, Character, CharacterAsset, Message, MessageAlternate, Thread
from app.storage.session import create_engine


@pytest.fixture()
def thread_client(tmp_path: Path) -> Iterator[tuple[TestClient, async_sessionmaker]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-test.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    app = create_app(static_client_dir=None)

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_thread_session] = override_session

    with TestClient(app) as client:
        yield client, sessionmaker

    asyncio.run(engine.dispose())


def test_thread_creation_inserts_first_message_before_any_user_message(
    thread_client: tuple[TestClient, async_sessionmaker],
) -> None:
    client, sessionmaker = thread_client
    character_id = asyncio.run(_insert_character(sessionmaker, first_mes="Default opening."))

    create_response = client.post("/api/threads", json={"character_id": character_id})

    assert create_response.status_code == 201
    thread_id = create_response.json()["thread_id"]
    detail = client.get(f"/api/threads/{thread_id}").json()
    messages = detail["messages"]
    assert [message["sequence"] for message in messages] == [0]
    assert messages[0]["message_kind"] == "ai_text"
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content_text"] == "Default opening."
    assert messages[0]["selected_alternate_id"] == messages[0]["alternates"][0]["id"]
    assert messages[0]["alternates"][0]["source_action"] == "first_mes"


def test_thread_creation_persists_selected_alternate_greeting_index_as_opening_message(
    thread_client: tuple[TestClient, async_sessionmaker],
) -> None:
    client, sessionmaker = thread_client
    character_id = asyncio.run(
        _insert_character(
            sessionmaker,
            first_mes="Fallback opening.",
            alternate_greetings=["Alternate zero.", "Alternate one."],
        )
    )

    create_response = client.post(
        "/api/threads",
        json={"character_id": character_id, "alternate_greeting_index": 1},
    )

    assert create_response.status_code == 201
    thread_id = create_response.json()["thread_id"]
    opening = client.get(f"/api/threads/{thread_id}").json()["messages"][0]
    assert opening["content_text"] == "Alternate one."
    assert opening["selected_alternate_id"] == opening["alternates"][0]["id"]
    assert opening["alternates"][0]["alternate_index"] == 1
    assert opening["alternates"][0]["content_text"] == "Alternate one."
    assert opening["alternates"][0]["source_action"] == "first_mes"


def test_thread_creation_rejects_out_of_range_alternate_greeting_index(
    thread_client: tuple[TestClient, async_sessionmaker],
) -> None:
    client, sessionmaker = thread_client
    character_id = asyncio.run(
        _insert_character(sessionmaker, alternate_greetings=["Only alternate."])
    )

    response = client.post(
        "/api/threads",
        json={"character_id": character_id, "alternate_greeting_index": 3},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "alternate_greeting_index_out_of_range"
    assert response.json()["detail"]["alternate_greeting_count"] == 1


def test_post_threads_returns_thread_id_for_client_navigation(
    thread_client: tuple[TestClient, async_sessionmaker],
) -> None:
    client, sessionmaker = thread_client
    character_id = asyncio.run(_insert_character(sessionmaker))

    response = client.post("/api/threads", json={"character_id": character_id})

    assert response.status_code == 201
    assert set(response.json()) == {"thread_id"}
    assert response.json()["thread_id"].startswith("thread_")


def test_thread_detail_hydrates_metadata_chronological_messages_alternates_and_stale_flags(
    thread_client: tuple[TestClient, async_sessionmaker],
) -> None:
    client, sessionmaker = thread_client
    character_id = asyncio.run(_insert_character(sessionmaker, first_mes="Hello from card."))
    thread_id = client.post(
        "/api/threads",
        json={"character_id": character_id, "title": "Hydration Thread"},
    ).json()["thread_id"]
    asyncio.run(_insert_branch_messages(sessionmaker, thread_id))

    response = client.get(f"/api/threads/{thread_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Hydration Thread"
    assert body["character_id"] == character_id
    assert body["character_name"] == "Test Character"
    assert body["character_snapshot"]["first_mes"] == "Hello from card."
    assert [message["sequence"] for message in body["messages"]] == [0, 1, 2]
    selected_ai = body["messages"][2]
    assert selected_ai["content_text"] == "Selected swipe branch."
    assert selected_ai["selected_alternate_id"] == "alt-selected"
    assert [alternate["alternate_index"] for alternate in selected_ai["alternates"]] == [0, 1]
    assert selected_ai["stale_after_edit"] is True


def test_threads_list_sorts_by_activity_with_character_snapshot_and_last_snippet(
    thread_client: tuple[TestClient, async_sessionmaker],
) -> None:
    client, sessionmaker = thread_client
    older_character_id = asyncio.run(_insert_character(sessionmaker, character_id="char_older"))
    newer_character_id = asyncio.run(_insert_character(sessionmaker, character_id="char_newer"))
    asyncio.run(_insert_portrait(sessionmaker, newer_character_id))
    older_thread_id = client.post(
        "/api/threads",
        json={"character_id": older_character_id, "title": "Older"},
    ).json()["thread_id"]
    newer_thread_id = client.post(
        "/api/threads",
        json={"character_id": newer_character_id, "title": "Newer"},
    ).json()["thread_id"]
    asyncio.run(_set_thread_activity(sessionmaker, older_thread_id, minutes_ago=20))
    asyncio.run(
        _set_thread_activity(
            sessionmaker,
            newer_thread_id,
            minutes_ago=1,
            last_message="A recent selected answer for the Home list.",
        )
    )

    response = client.get("/api/threads")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [newer_thread_id, older_thread_id]
    assert items[0]["character_name"] == "Test Character"
    assert items[0]["character_portrait_asset_id"] == "asset_newer"
    assert items[0]["last_message_snippet"] == "A recent selected answer for the Home list."


def test_thread_rename_and_delete_scope_to_selected_thread(
    thread_client: tuple[TestClient, async_sessionmaker],
) -> None:
    client, sessionmaker = thread_client
    first_character_id = asyncio.run(_insert_character(sessionmaker, character_id="char_one"))
    second_character_id = asyncio.run(_insert_character(sessionmaker, character_id="char_two"))
    first_thread_id = client.post(
        "/api/threads",
        json={"character_id": first_character_id, "title": "First"},
    ).json()["thread_id"]
    second_thread_id = client.post(
        "/api/threads",
        json={"character_id": second_character_id, "title": "Second"},
    ).json()["thread_id"]

    rename_response = client.patch(
        f"/api/threads/{first_thread_id}",
        json={"title": "Renamed thread"},
    )
    delete_response = client.delete(f"/api/threads/{first_thread_id}")

    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "Renamed thread"
    assert delete_response.status_code == 200
    assert client.get(f"/api/threads/{first_thread_id}").status_code == 404
    assert client.get(f"/api/threads/{second_thread_id}").status_code == 200
    counts = asyncio.run(_message_counts_by_thread(sessionmaker))
    assert counts == {second_thread_id: 1}


async def _insert_character(
    sessionmaker: async_sessionmaker,
    *,
    character_id: str = "char_test",
    first_mes: str = "Hello from the character.",
    alternate_greetings: list[str] | None = None,
) -> str:
    async with sessionmaker() as session:
        session.add(
            Character(
                id=character_id,
                name="Test Character",
                description="description",
                personality="personality",
                scenario="scenario",
                first_mes=first_mes,
                system_prompt="system",
                alternate_greetings_json=list(alternate_greetings or []),
                raw_source_json={"spec": "chara_card_v3"},
            )
        )
        await session.commit()
        return character_id


async def _insert_portrait(sessionmaker: async_sessionmaker, character_id: str) -> None:
    async with sessionmaker() as session:
        session.add(
            CharacterAsset(
                id="asset_newer",
                character_id=character_id,
                asset_kind="portrait",
                storage_path="asset_newer.png",
                content_type="image/png",
                byte_size=123,
                sha256="0" * 64,
            )
        )
        await session.commit()


async def _insert_branch_messages(sessionmaker: async_sessionmaker, thread_id: str) -> None:
    async with sessionmaker() as session:
        session.add(
            Message(
                id="user-message",
                thread_id=thread_id,
                message_kind="user_text",
                role="user",
                sequence=1,
                content_text="User asks a question.",
            )
        )
        await session.commit()
        session.add(
            Message(
                id="ai-message",
                thread_id=thread_id,
                message_kind="ai_text",
                role="assistant",
                sequence=2,
                content_text="Original AI branch.",
                selected_alternate_id="alt-selected",
                stale_after_edit=True,
            )
        )
        await session.commit()
        session.add_all(
            [
                MessageAlternate(
                    id="alt-original",
                    message_id="ai-message",
                    alternate_index=0,
                    content_text="Original AI branch.",
                    source_action="swipe",
                ),
                MessageAlternate(
                    id="alt-selected",
                    message_id="ai-message",
                    alternate_index=1,
                    content_text="Selected swipe branch.",
                    source_action="swipe",
                ),
            ]
        )
        await session.commit()


async def _set_thread_activity(
    sessionmaker: async_sessionmaker,
    thread_id: str,
    *,
    minutes_ago: int,
    last_message: str | None = None,
) -> None:
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    async with sessionmaker() as session:
        thread = (await session.execute(select(Thread).where(Thread.id == thread_id))).scalar_one()
        thread.last_message_at = timestamp
        thread.updated_at = timestamp
        if last_message is not None:
            message = (
                await session.execute(
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .order_by(Message.sequence.desc())
                )
            ).scalars().first()
            assert message is not None
            message.content_text = last_message
            message.updated_at = timestamp
            if message.selected_alternate_id is not None:
                alternate = (
                    await session.execute(
                        select(MessageAlternate).where(
                            MessageAlternate.id == message.selected_alternate_id
                        )
                    )
                ).scalar_one()
                alternate.content_text = last_message
                alternate.updated_at = timestamp
        await session.commit()


async def _message_counts_by_thread(sessionmaker: async_sessionmaker) -> dict[str, int]:
    async with sessionmaker() as session:
        result = await session.execute(
            select(Message.thread_id, func.count(Message.id)).group_by(Message.thread_id)
        )
        return {thread_id: count for thread_id, count in result.all()}
