"""Character CRUD, import/export, delete, and portrait route tests."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.characters import get_character_session, get_portrait_blob_dir
from app.domain.cards import (
    CharacterDeleteResult,
    delete_character_preserving_thread_snapshots,
)
from app.domain.character_service import ACTIVE_PORTRAIT_KIND
from app.main import create_app
from app.storage.models import Base, CharacterAsset, Message, Thread, Voice, utc_now
from app.storage.session import create_engine

CARD_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cards"


class FakeCharacterRepository:
    def __init__(self) -> None:
        self.thread_snapshot = {
            "thread_id": "thread-1",
            "character_id": "character-1",
            "character_snapshot": {
                "name": "Historical Character",
                "first_mes": "This opening line must survive deletion.",
            },
        }

    async def delete_character_preserving_thread_snapshots(
        self,
        character_id: str,
    ) -> CharacterDeleteResult:
        assert character_id == "character-1"
        return CharacterDeleteResult(
            character_id=character_id,
            deleted_at="2026-04-24T00:00:00Z",
            preserved_thread_ids=(self.thread_snapshot["thread_id"],),
            strategy="soft_delete",
        )


@pytest.fixture()
def character_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path, async_sessionmaker]]:
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

    portrait_dir = tmp_path / "portraits"
    app.dependency_overrides[get_character_session] = override_session
    app.dependency_overrides[get_portrait_blob_dir] = lambda: portrait_dir

    with TestClient(app) as client:
        yield client, portrait_dir, sessionmaker

    asyncio.run(engine.dispose())


async def test_character_delete_preserves_existing_thread_snapshot() -> None:
    repository = FakeCharacterRepository()

    result = await delete_character_preserving_thread_snapshots(
        "character-1",
        repository=repository,
    )

    assert result.deleted_at is not None
    assert result.strategy in {"soft_delete", "detach_threads"}
    assert result.preserved_thread_ids == ("thread-1",)
    assert repository.thread_snapshot["character_snapshot"]["name"] == "Historical Character"
    assert (
        repository.thread_snapshot["character_snapshot"]["first_mes"]
        == "This opening line must survive deletion."
    )


def test_character_crud_routes_persist_editor_fields(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, _ = character_client
    created = _create_character(client)
    character_id = created["id"]

    listing = client.get("/api/characters")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [character_id]

    detail = client.get(f"/api/characters/{character_id}")
    assert detail.status_code == 200
    assert detail.json()["alternate_greetings"] == ["Alt one", "Alt two"]

    updated_payload = _character_payload(
        name="Updated Character",
        description="updated description",
        personality="updated personality",
        scenario="updated scenario",
        first_mes="updated first",
        mes_example="<START>\n{{char}}: updated",
        system_prompt="updated system",
        creator_notes="updated creator notes",
        character_notes="updated character notes",
        tags=["updated", "tag"],
        alternate_greetings=["Updated alt"],
        post_history_instructions="updated post history",
        creator="Updated Creator",
        character_version="2.0",
    )
    updated = client.put(f"/api/characters/{character_id}", json=updated_payload)
    assert updated.status_code == 200
    body = updated.json()
    for key, value in updated_payload.items():
        assert body[key] == value

    deleted = client.delete(f"/api/characters/{character_id}")
    assert deleted.status_code == 200
    assert deleted.json()["strategy"] == "soft_delete"
    assert client.get("/api/characters").json()["items"] == []


def test_character_default_voice_id_persists_across_writes_and_reads(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, sessionmaker = character_client
    first_voice_id = "voice_default_first"
    second_voice_id = "voice_default_second"
    asyncio.run(_insert_voice(sessionmaker, first_voice_id, name="First assigned voice"))
    asyncio.run(_insert_voice(sessionmaker, second_voice_id, name="Second assigned voice"))

    created = client.post(
        "/api/characters",
        json=_character_payload(default_voice_id=first_voice_id),
    )
    character_id = created.json()["id"]
    updated = client.put(
        f"/api/characters/{character_id}",
        json=_character_payload(
            name="Updated Character",
            default_voice_id=second_voice_id,
        ),
    )
    detail = client.get(f"/api/characters/{character_id}")
    listing = client.get("/api/characters")

    assert created.status_code == 201
    assert created.json()["default_voice_id"] == first_voice_id
    assert updated.status_code == 200
    assert updated.json()["default_voice_id"] == second_voice_id
    assert detail.status_code == 200
    assert detail.json()["default_voice_id"] == second_voice_id
    assert listing.status_code == 200
    assert listing.json()["items"][0]["default_voice_id"] == second_voice_id


def test_character_default_voice_id_rejects_missing_or_deleted_voice(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, sessionmaker = character_client
    deleted_voice_id = "voice_deleted_default"
    asyncio.run(_insert_voice(sessionmaker, deleted_voice_id, name="Deleted default voice"))
    asyncio.run(_soft_delete_voice(sessionmaker, deleted_voice_id))

    missing = client.post(
        "/api/characters",
        json=_character_payload(default_voice_id="voice_missing_default"),
    )
    deleted = client.post(
        "/api/characters",
        json=_character_payload(default_voice_id=deleted_voice_id),
    )
    no_voice = client.post(
        "/api/characters",
        json=_character_payload(default_voice_id=""),
    )

    assert missing.status_code == 400
    assert missing.json()["detail"] == "Default voice not found"
    assert deleted.status_code == 400
    assert deleted.json()["detail"] == "Default voice not found"
    assert no_voice.status_code == 201
    assert no_voice.json()["default_voice_id"] is None


def test_character_delete_keeps_threads_and_messages_queryable(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, sessionmaker = character_client
    character_id = _create_character(client)["id"]
    asyncio.run(_insert_thread_with_message(sessionmaker, character_id))

    response = client.delete(f"/api/characters/{character_id}")

    assert response.status_code == 200
    assert response.json()["preserved_thread_ids"] == ["thread-1"]
    thread, message = asyncio.run(_load_thread_and_message(sessionmaker))
    assert thread.character_snapshot_name == "Historical Character"
    assert message.content_text == "Historical message"


def test_import_route_reports_lorebook_present_not_used(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, _ = character_client
    fixture = CARD_FIXTURE_DIR / "v3_card.json"

    response = client.post(
        "/api/characters/import",
        files={"file": (fixture.name, fixture.read_bytes(), "application/json")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "RayMe Fixture V3"
    assert body["lorebook_present"] is True
    assert "Lorebook present - not used in v1" in body["warnings"]


def test_import_png_card_creates_active_portrait_asset(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, portrait_dir, sessionmaker = character_client
    fixture = CARD_FIXTURE_DIR / "v3_card.png"

    response = client.post(
        "/api/characters/import",
        files={"file": (fixture.name, fixture.read_bytes(), "image/png")},
    )

    assert response.status_code == 201
    body = response.json()
    character_id = body["id"]
    assert body["portrait_asset_id"] is not None
    assert body["portrait_url"] == (
        f"/api/characters/{character_id}/portrait?asset_id={body['portrait_asset_id']}"
    )
    assert body["portrait_storage_path"] is not None
    assert (portrait_dir / body["portrait_storage_path"]).is_file()
    assert body["character"]["portrait_asset_id"] == body["portrait_asset_id"]
    assert body["character"]["portrait_url"] == body["portrait_url"]
    assets = asyncio.run(_load_assets(sessionmaker, character_id))
    assert len(assets) == 1
    assert assets[0].asset_kind == ACTIVE_PORTRAIT_KIND
    assert assets[0].content_type == "image/png"


def test_export_v2_route_returns_json_only(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, _ = character_client
    character_id = _create_character(client)["id"]

    response = client.get(f"/api/characters/{character_id}/export-v2")

    assert response.status_code == 200
    body = response.json()
    assert body["spec"] == "chara_card_v2"
    assert body["data"]["name"] == "Test Character"
    assert "ccv3" not in response.text
    assert "png" not in response.text.lower()


def test_portrait_rejects_path_like_filename_and_svg(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, _ = character_client
    character_id = _create_character(client)["id"]

    path_response = client.put(
        f"/api/characters/{character_id}/portrait",
        files={"file": ("../portrait.png", _png_bytes(), "image/png")},
    )
    svg_response = client.put(
        f"/api/characters/{character_id}/portrait",
        files={"file": ("portrait.svg", b"<svg></svg>", "image/svg+xml")},
    )

    assert path_response.status_code == 400
    assert svg_response.status_code == 400


def test_valid_portrait_creates_asset_record_and_blob(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, portrait_dir, sessionmaker = character_client
    character_id = _create_character(client)["id"]

    response = client.put(
        f"/api/characters/{character_id}/portrait",
        files={"file": ("portrait.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["portrait_asset_id"] is not None
    assert body["portrait_url"] == (
        f"/api/characters/{character_id}/portrait?asset_id={body['portrait_asset_id']}"
    )
    assert body["portrait_storage_path"] != "portrait.png"
    assert (portrait_dir / body["portrait_storage_path"]).is_file()
    blob_response = client.get(body["portrait_url"])
    assert blob_response.status_code == 200
    assert blob_response.headers["content-type"] == "image/png"
    assert blob_response.content == _png_bytes()
    assets = asyncio.run(_load_assets(sessionmaker, character_id))
    assert len(assets) == 1
    assert assets[0].asset_kind == ACTIVE_PORTRAIT_KIND


def test_portrait_replace_and_delete_manage_active_reference(
    character_client: tuple[TestClient, Path, async_sessionmaker],
) -> None:
    client, _, sessionmaker = character_client
    character_id = _create_character(client)["id"]

    first = client.put(
        f"/api/characters/{character_id}/portrait",
        files={"file": ("first.png", _png_bytes(color=(255, 0, 0, 255)), "image/png")},
    ).json()
    second = client.put(
        f"/api/characters/{character_id}/portrait",
        files={"file": ("second.png", _png_bytes(color=(0, 255, 0, 255)), "image/png")},
    ).json()

    assert second["portrait_asset_id"] != first["portrait_asset_id"]
    assets_after_replace = asyncio.run(_load_assets(sessionmaker, character_id))
    assert len(assets_after_replace) == 2
    assert sum(asset.asset_kind == ACTIVE_PORTRAIT_KIND for asset in assets_after_replace) == 1

    deleted = client.delete(f"/api/characters/{character_id}/portrait")
    assert deleted.status_code == 200
    assert deleted.json()["portrait_asset_id"] is None
    assert deleted.json()["portrait_url"] is None
    assets_after_delete = asyncio.run(_load_assets(sessionmaker, character_id))
    assert len(assets_after_delete) == 2
    assert sum(asset.asset_kind == ACTIVE_PORTRAIT_KIND for asset in assets_after_delete) == 0


def _character_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Test Character",
        "description": "description",
        "personality": "personality",
        "scenario": "scenario",
        "first_mes": "first",
        "mes_example": "<START>\n{{char}}: example",
        "system_prompt": "system",
        "creator_notes": "creator notes",
        "character_notes": "character notes",
        "tags": ["tag-one", "tag-two"],
        "alternate_greetings": ["Alt one", "Alt two"],
        "post_history_instructions": "post history",
        "creator": "RayMe",
        "character_version": "1.0",
    }
    payload.update(overrides)
    return payload


def _create_character(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/characters", json=_character_payload())
    assert response.status_code == 201
    return response.json()


def _png_bytes(*, color: tuple[int, int, int, int] = (0, 0, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (2, 2), color).save(buffer, format="PNG")
    return buffer.getvalue()


async def _insert_thread_with_message(
    sessionmaker: async_sessionmaker,
    character_id: str,
) -> None:
    async with sessionmaker() as session:
        session.add(
            Thread(
                id="thread-1",
                character_id=character_id,
                title="History",
                character_snapshot_name="Historical Character",
                character_snapshot_first_mes="Opening snapshot",
            )
        )
        await session.commit()
        session.add(
            Message(
                id="message-1",
                thread_id="thread-1",
                message_kind="ai_text",
                role="assistant",
                sequence=1,
                content_text="Historical message",
            )
        )
        await session.commit()


async def _load_thread_and_message(sessionmaker: async_sessionmaker) -> tuple[Thread, Message]:
    async with sessionmaker() as session:
        thread = (
            await session.execute(select(Thread).where(Thread.id == "thread-1"))
        ).scalar_one()
        message = (
            await session.execute(select(Message).where(Message.id == "message-1"))
        ).scalar_one()
        return thread, message


async def _load_assets(
    sessionmaker: async_sessionmaker,
    character_id: str,
) -> list[CharacterAsset]:
    async with sessionmaker() as session:
        result = await session.execute(
            select(CharacterAsset).where(CharacterAsset.character_id == character_id)
        )
        return list(result.scalars())


async def _insert_voice(
    sessionmaker: async_sessionmaker,
    voice_id: str,
    *,
    name: str,
) -> None:
    async with sessionmaker() as session:
        session.add(
            Voice(
                id=voice_id,
                name=name,
                default_engine="F5-TTS",
                reference_transcript="A saved reference transcript.",
                metadata_json={"source": "test"},
            )
        )
        await session.commit()


async def _soft_delete_voice(sessionmaker: async_sessionmaker, voice_id: str) -> None:
    async with sessionmaker() as session:
        voice = await session.get(Voice, voice_id)
        assert voice is not None
        voice.deleted_at = utc_now()
        await session.commit()
