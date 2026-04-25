"""Voice storage, Voice Lab, and Voice Library API contract tests."""

from __future__ import annotations

import asyncio
import io
import json
import wave
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import httpx
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
    return_tts_failed: bool = False
    calls: list[dict[str, Any]] | None = None

    async def transcribe(self, **_: Any) -> dict[str, str | float]:
        self._record("transcribe", _)
        return {
            "transcript": "This is the editable reference transcript.",
            "language": "en",
            "confidence": 0.98,
        }

    async def preview(self, **_: Any) -> dict[str, str]:
        self._record("preview", _)
        if self.fail_preview:
            raise RuntimeError("preview synthesis failed")
        if self.return_tts_failed:
            return {"status": "tts_failed", "error": "typed processing failure"}
        return {"preview_id": "preview-1", "preview_url": "/api/voices/previews/preview-1.wav"}

    async def synthesize_preview(self, **kwargs: Any) -> dict[str, str]:
        return await self.preview(**kwargs)

    async def test_play(self, **_: Any) -> dict[str, str]:
        self._record("test_play", _)
        if self.return_tts_failed:
            return {"status": "tts_failed", "error": "typed processing failure"}
        return {"audio_url": "/api/voices/test-play/test-play-1.wav"}

    def _record(self, operation: str, payload: dict[str, Any]) -> None:
        if self.calls is None:
            self.calls = []
        self.calls.append({"operation": operation, **payload})


@dataclass(frozen=True, slots=True)
class VoiceFixture:
    client: TestClient
    processor: FakeVoiceProcessor


@dataclass(frozen=True, slots=True)
class CreatedVoice:
    voice_id: str
    asset_id: str
    body: dict[str, Any]


def test_validate_voice_sample_upload_rejects_paths_and_unsupported_files() -> None:
    from app.domain.voice_assets import VoiceSampleValidationError, validate_voice_sample_upload

    with pytest.raises(VoiceSampleValidationError):
        validate_voice_sample_upload("../../sample.wav", "audio/wav", _pcm_wav_bytes(7.0))

    with pytest.raises(VoiceSampleValidationError):
        validate_voice_sample_upload("sample.txt", "text/plain", b"not audio")


def test_validate_voice_sample_upload_accepts_audio_and_reports_duration_warnings() -> None:
    from app.domain.voice_assets import validate_voice_sample_upload

    short_sample = validate_voice_sample_upload(
        "short.wav",
        "audio/wav",
        _pcm_wav_bytes(5.0),
    )
    recommended_sample = validate_voice_sample_upload(
        "recommended.wav",
        "audio/x-wav",
        _pcm_wav_bytes(6.0),
    )
    long_sample = validate_voice_sample_upload(
        "long.wav",
        "audio/wav",
        _pcm_wav_bytes(16.0),
    )

    assert short_sample.extension == ".wav"
    assert short_sample.content_type == "audio/wav"
    assert short_sample.byte_size == len(short_sample.content)
    assert short_sample.duration_seconds == pytest.approx(5.0)
    assert "too_short" in short_sample.warnings
    assert recommended_sample.warnings == []
    assert "longer_than_recommended" in long_sample.warnings


def test_write_voice_sample_blob_uses_asset_id_and_atomic_write(tmp_path: Path) -> None:
    from app.domain.voice_assets import validate_voice_sample_upload, write_voice_sample_blob

    sample = validate_voice_sample_upload(
        "owner-secret.wav",
        "audio/wav",
        _pcm_wav_bytes(7.0),
    )

    stored_path = write_voice_sample_blob(tmp_path, "voice_asset_test", sample)

    assert stored_path == tmp_path / "voice_asset_test.wav"
    assert stored_path.read_bytes() == sample.content
    assert stored_path.name != "owner-secret.wav"


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


def test_voice_asset_upload_rejects_unsupported_files_without_traceback(
    voice_fixture: VoiceFixture,
) -> None:
    response = voice_fixture.client.post(
        "/api/voices/assets",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )

    body = response.json()
    serialized = json.dumps(body).lower()
    assert response.status_code == 400
    assert "traceback" not in serialized
    assert "runtimeerror" not in serialized
    assert "valueerror" not in serialized


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
    assert voice_fixture.processor.calls
    call = voice_fixture.processor.calls[-1]
    assert call["operation"] == "transcribe"
    assert call["content"] == _wav_audio("transcribe-source.wav").content
    assert call["content_type"] == "audio/wav"


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


def test_voice_save_succeeds_after_preview_returns_tts_failed(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    voice_fixture.processor.return_tts_failed = True
    uploaded = _upload_voice_asset(client, _wav_audio("tts-failed-preview.wav"))
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["asset_id"]

    preview = client.post(
        "/api/voices/preview",
        json={
            "asset_id": asset_id,
            "name": "Preview failure can still save",
            "default_engine": "F5-TTS",
            "reference_transcript": "Save does not require successful synthesis.",
            "preview_text": "Preview can fail.",
        },
    )
    saved = client.post(
        "/api/voices",
        json={
            **_voice_payload(
                asset_id=asset_id,
                name="Preview failure can still save",
                default_engine="F5-TTS",
                reference_transcript="Save does not require successful synthesis.",
            ),
            "metadata": {"source": "voice_lab", "preview_status": "tts_failed"},
        },
    )

    assert preview.status_code == 200
    assert preview.json()["status"] == "tts_failed"
    assert saved.status_code == 201
    assert saved.json()["metadata"]["sample_asset_id"] == asset_id
    assert saved.json()["metadata"]["source"] == "voice_lab"
    assert saved.json()["metadata"]["preview_status"] == "tts_failed"


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
    assert assigned.json()["default_voice"]["id"] == voice.voice_id
    assert renamed.status_code == 200
    assert renamed.json()["voice_id"] == voice.voice_id
    assert renamed.json()["name"] == "Renamed display name"
    assert renamed.json()["default_engine"] == "F5-TTS"
    assert renamed.json()["reference_transcript"] == "Editable transcript for saved voice."
    assert character_after_rename.status_code == 200
    assert character_after_rename.json()["default_voice"]["id"] == voice.voice_id
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
    assert character_detail.json()["default_voice_id"] == voice.voice_id
    assert character_detail.json()["default_voice_state"] == "unavailable"
    assert character_detail.json()["default_voice_label"] == "Voice unavailable"
    assert character_detail.json()["default_voice"]["id"] == voice.voice_id
    assert character_detail.json()["default_voice"]["deleted_name"] == "Referenced voice"


def test_delete_referenced_voice_requires_force_and_returns_readable_referents(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    voice = _create_voice(client, name="Still referenced voice")
    character = _create_character(client)
    assigned = client.put(
        f"/api/characters/{character['id']}",
        json={**_character_payload(name="Readable referent"), "default_voice_id": voice.voice_id},
    )
    assert assigned.status_code == 200

    blocked = client.delete(f"/api/voices/{voice.voice_id}")
    detail = blocked.json()["detail"]

    assert blocked.status_code == 409
    assert detail["message"] == "Voice is referenced"
    assert detail["referents"] == [
        {"kind": "character", "id": character["id"], "name": "Readable referent"}
    ]


def test_ai_backend_voice_processor_uses_stt_route_and_stored_sample_bytes() -> None:
    from app.api.voices import AiBackendVoiceProcessor
    from app.domain.ai_backend_client import AiBackendClient

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/base/stt/transcribe":
            assert b"stored-sample-bytes" in request.content
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "transcript": "Transcript from stored sample",
                    "language": "en",
                    "model": "distil-large-v3",
                    "compute_type": "int8_float16",
                    "segments": [],
                    "speech_detected": True,
                    "retry_allowed": False,
                    "manual_transcript_allowed": False,
                },
            )
        return httpx.Response(404)

    async def exercise() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            processor = AiBackendVoiceProcessor(
                AiBackendClient(http_client=http_client),
                "https://ai.local:9443/base",
            )
            return await processor.transcribe(
                asset_id="voice_asset_route_test",
                content=b"stored-sample-bytes",
                content_type="audio/wav",
            )

    result = asyncio.run(exercise())

    assert result["transcript"] == "Transcript from stored sample"
    assert [request.url.path for request in requests] == ["/base/stt/transcribe"]


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


def test_voice_test_play_returns_bad_gateway_when_synthesis_produces_no_audio(
    voice_fixture: VoiceFixture,
) -> None:
    client = voice_fixture.client
    voice_fixture.processor.return_tts_failed = True
    voice = _create_voice(client, name="Library voice with failing test play")

    test_play = client.post(
        f"/api/voices/{voice.voice_id}/test-play",
        json={"text": "This should fail without audio.", "use_default_engine": True},
    )

    assert test_play.status_code == 502
    assert test_play.json()["detail"]["message"] == "Voice test-play did not produce generated audio"


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


def _pcm_wav_bytes(duration_seconds: float, *, sample_rate_hz: int = 8000) -> bytes:
    buffer = io.BytesIO()
    frame_count = int(duration_seconds * sample_rate_hz)
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


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
