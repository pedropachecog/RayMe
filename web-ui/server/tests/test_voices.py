"""Voice storage, Voice Lab, and Voice Library API contract tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.characters import get_character_session, get_portrait_blob_dir
from app.main import create_app
from app.storage.models import Base
from app.storage.session import create_engine

SUPPORTED_TTS_ENGINES = (
    "F5-TTS",
    "XTTS v2",
    "Qwen3-TTS 0.6B-Base",
    "LuxTTS",
    "Chatterbox Turbo",
    "TADA 1B",
)


@dataclass(frozen=True, slots=True)
class UploadedAudio:
    filename: str
    content_type: str
    content: bytes


@dataclass(slots=True)
class FakeVoiceProcessor:
    fail_preview: bool = False

    async def transcribe(self, **_: Any) -> dict[str, str | float]:
        return {
            "transcript": "This is the editable reference transcript.",
            "language": "en",
            "confidence": 0.98,
        }

    async def preview(self, **_: Any) -> dict[str, str]:
        if self.fail_preview:
            raise RuntimeError("preview synthesis failed")
        return {"preview_id": "preview-1", "preview_url": "/api/voices/previews/preview-1.wav"}

    async def synthesize_preview(self, **kwargs: Any) -> dict[str, str]:
        return await self.preview(**kwargs)

    async def test_play(self, **_: Any) -> dict[str, str]:
        return {"audio_url": "/api/voices/test-play/test-play-1.wav"}


@dataclass(frozen=True, slots=True)
class VoiceFixture:
    client: TestClient
    processor: FakeVoiceProcessor


@dataclass(frozen=True, slots=True)
class CreatedVoice:
    voice_id: str
    asset_id: str
    body: dict[str, Any]


@pytest.fixture()
def voice_fixture(tmp_path: Path) -> Iterator[VoiceFixture]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-voices.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    app = create_app(static_client_dir=None)
    processor = FakeVoiceProcessor()
    _install_test_dependencies(app, sessionmaker, tmp_path / "blobs", processor)

    with TestClient(app) as client:
        yield VoiceFixture(client=client, processor=processor)

    asyncio.run(engine.dispose())


def test_voice_asset_upload_accepts_wav_mp3_flac_and_rejects_txt(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client

    for audio in _accepted_audio_files():
        response = _upload_voice_asset(client, audio)

        assert response.status_code == 201
        body = response.json()
        assert body["asset_id"]
        assert body["content_type"] == audio.content_type
        assert body["byte_size"] == len(audio.content)
        assert body["storage_path"] != audio.filename
        assert "owner-secret" not in body["storage_path"]
        assert "/" not in body["storage_path"].strip("/")

    rejected = client.post(
        "/api/voices/assets",
        files={"file": ("owner-secret.txt", b"not audio", "text/plain")},
    )

    assert rejected.status_code == 400
    assert "audio" in rejected.json()["detail"].lower()


def test_voice_asset_transcribe_returns_editable_reference_transcript(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    uploaded = _upload_voice_asset(client, _wav_audio("transcribe-source.wav"))
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["asset_id"]

    response = client.post(f"/api/voices/assets/{asset_id}/transcribe")

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == asset_id
    assert body["reference_transcript"] == "This is the editable reference transcript."
    assert body["reference_transcript_editable"] is True


def test_voice_save_without_preview_covers_full_engine_roster(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client

    # Contract: save without preview must not require preview_id, preview_url, or synthesis success.
    for engine_name in SUPPORTED_TTS_ENGINES:
        uploaded = _upload_voice_asset(client, _wav_audio(f"{engine_name}.wav"))
        assert uploaded.status_code == 201
        asset_id = uploaded.json()["asset_id"]
        response = client.post(
            "/api/voices",
            json=_voice_payload(
                asset_id=asset_id,
                name=f"{engine_name} reference voice",
                default_engine=engine_name,
                reference_transcript=f"Editable transcript for {engine_name}.",
            ),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["voice_id"]
        assert body["asset_id"] == asset_id
        assert body["name"] == f"{engine_name} reference voice"
        assert body["default_engine"] == engine_name
        assert body["reference_transcript"] == f"Editable transcript for {engine_name}."
        assert "preview_id" not in body
        assert "preview_url" not in body


def test_voice_id_is_stable_across_rename_and_character_reference(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    voice = _create_voice(client, name="Original display name")
    character = _create_character(client)

    assigned = client.put(
        f"/api/characters/{character['id']}",
        json={
            **_character_payload(name="Character with default voice"),
            "default_voice_id": voice.voice_id,
        },
    )
    renamed = client.patch(
        f"/api/voices/{voice.voice_id}",
        json={
            "name": "Renamed display name",
            "default_engine": "XTTS v2",
            "reference_transcript": "Updated editable transcript.",
        },
    )
    character_after_rename = client.get(f"/api/characters/{character['id']}")

    assert assigned.status_code == 200
    assert assigned.json()["default_voice"]["voice_id"] == voice.voice_id
    assert renamed.status_code == 200
    assert renamed.json()["voice_id"] == voice.voice_id
    assert renamed.json()["name"] == "Renamed display name"
    assert renamed.json()["default_engine"] == "XTTS v2"
    assert renamed.json()["reference_transcript"] == "Updated editable transcript."
    assert character_after_rename.status_code == 200
    assert character_after_rename.json()["default_voice"]["voice_id"] == voice.voice_id
    assert character_after_rename.json()["default_voice"]["name"] == "Renamed display name"


def test_preview_failure_preserves_unsaved_voice_payload_state(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    voice_fixture.processor.fail_preview = True
    uploaded = _upload_voice_asset(client, _flac_audio("preview-input.flac"))
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["asset_id"]
    payload = {
        "asset_id": asset_id,
        "name": "Preview can fail but state survives",
        "default_engine": "F5-TTS",
        "reference_transcript": "Preview failure keeps this transcript editable.",
        "preview_text": "This preview text should still be visible after failure.",
        "use_default_engine": False,
        "engine": "LuxTTS",
    }

    response = client.post("/api/voices/preview", json=payload)

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "preview_failed"
    assert body["payload_state"] == payload
    assert "preview_url" not in body


def test_force_delete_tombstones_voice_and_characters_show_unavailable_state(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    voice = _create_voice(client, name="Referenced voice")
    character = _create_character(client)
    assigned = client.put(
        f"/api/characters/{character['id']}",
        json={**_character_payload(name="Character with voice"), "default_voice_id": voice.voice_id},
    )
    assert assigned.status_code == 200

    deleted = client.delete(f"/api/voices/{voice.voice_id}?force=true")
    voice_detail = client.get(f"/api/voices/{voice.voice_id}")
    character_detail = client.get(f"/api/characters/{character['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["voice_id"] == voice.voice_id
    assert deleted.json()["deleted_at"] is not None
    assert deleted.json()["tombstone"]["name"] == "Referenced voice"
    assert voice_detail.status_code == 200
    assert voice_detail.json()["status"] == "deleted"
    assert voice_detail.json()["unavailable_label"] == "Voice unavailable"
    assert character_detail.status_code == 200
    assert character_detail.json()["default_voice"] == {
        "voice_id": voice.voice_id,
        "name": "Referenced voice",
        "status": "unavailable",
        "label": "Voice unavailable",
    }


def test_voice_library_detail_and_test_play_routes(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    voice = _create_voice(client, name="Library voice")

    listing = client.get("/api/voices")
    detail = client.get(f"/api/voices/{voice.voice_id}")
    test_play = client.post(
        f"/api/voices/{voice.voice_id}/test-play",
        json={"text": "This is a stock test phrase.", "use_default_engine": True},
    )

    assert listing.status_code == 200
    assert [item["voice_id"] for item in listing.json()["items"]] == [voice.voice_id]
    assert detail.status_code == 200
    assert detail.json()["voice_id"] == voice.voice_id
    assert detail.json()["name"] == "Library voice"
    assert test_play.status_code == 200
    assert test_play.json()["voice_id"] == voice.voice_id
    assert test_play.json()["engine"] == voice.body["default_engine"]
    assert test_play.json()["audio_url"]


def _install_test_dependencies(
    app: FastAPI,
    sessionmaker: async_sessionmaker,
    blob_dir: Path,
    processor: FakeVoiceProcessor,
) -> None:
    async def override_session() -> AsyncIterator:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_character_session] = override_session
    app.dependency_overrides[get_portrait_blob_dir] = lambda: blob_dir / "portraits"

    try:
        from app.api import voices as voices_api
    except ImportError:
        return

    _override_if_present(app, voices_api, "get_voice_session", override_session)
    _override_if_present(app, voices_api, "get_voice_blob_dir", lambda: blob_dir / "voices")
    _override_if_present(app, voices_api, "get_voice_processor", lambda: processor)


def _override_if_present(
    app: FastAPI,
    module: object,
    dependency_name: str,
    replacement: object,
) -> None:
    dependency = getattr(module, dependency_name, None)
    if dependency is not None:
        app.dependency_overrides[dependency] = replacement


def _accepted_audio_files() -> tuple[UploadedAudio, ...]:
    return (
        _wav_audio("owner-secret.wav"),
        UploadedAudio("owner-secret.mp3", "audio/mpeg", b"ID3\x04\x00\x00\x00\x00\x00\x21mp3"),
        _flac_audio("owner-secret.flac"),
    )


def _wav_audio(filename: str) -> UploadedAudio:
    return UploadedAudio(
        filename=filename,
        content_type="audio/wav",
        content=b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00",
    )


def _flac_audio(filename: str) -> UploadedAudio:
    return UploadedAudio(filename=filename, content_type="audio/flac", content=b"fLaC\x00\x00\x00")


def _upload_voice_asset(client: TestClient, audio: UploadedAudio):
    return client.post(
        "/api/voices/assets",
        files={"file": (audio.filename, audio.content, audio.content_type)},
    )


def _create_voice(client: TestClient, *, name: str = "Saved voice") -> CreatedVoice:
    asset_response = _upload_voice_asset(client, _wav_audio(f"{name}.wav"))
    assert asset_response.status_code == 201
    asset_id = asset_response.json()["asset_id"]
    response = client.post(
        "/api/voices",
        json=_voice_payload(
            asset_id=asset_id,
            name=name,
            default_engine="F5-TTS",
            reference_transcript="Editable transcript for saved voice.",
        ),
    )
    assert response.status_code == 201
    body = response.json()
    return CreatedVoice(voice_id=body["voice_id"], asset_id=asset_id, body=body)


def _voice_payload(
    *,
    asset_id: str,
    name: str,
    default_engine: str,
    reference_transcript: str,
) -> dict[str, str]:
    payload = {
        "asset_id": asset_id,
        "name": name,
        "default_engine": default_engine,
        "reference_transcript": reference_transcript,
    }
    assert "preview_id" not in payload
    assert "preview_url" not in payload
    assert "successful_synthesis_result" not in payload
    return payload


def _character_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Voice Test Character",
        "description": "description",
        "personality": "personality",
        "scenario": "scenario",
        "first_mes": "first",
        "mes_example": "<START>\n{{char}}: example",
        "system_prompt": "system",
        "creator_notes": "creator notes",
        "character_notes": "character notes",
        "tags": ["voice"],
        "alternate_greetings": [],
        "post_history_instructions": "post history",
        "creator": "RayMe",
        "character_version": "1.0",
    }
    payload.update(overrides)
    return payload


def _create_character(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/characters", json=_character_payload())
    assert response.status_code == 201, json.dumps(response.json())
    return response.json()
