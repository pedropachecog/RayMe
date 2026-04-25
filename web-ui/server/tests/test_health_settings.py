"""Health and endpoint Settings API tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.settings import get_ai_backend_client, get_llm_probe, get_settings_session
from app.config import Settings
from app.domain.ai_backend_client import (
    AiBackendStatus,
    AiBackendUnavailable,
    EngineStatus,
)
from app.domain.settings_service import SETTINGS_KEY, SettingsService
from app.domain.llm_probe import (
    CONNECTED,
    NOT_CONFIGURED,
    UNAUTHORIZED,
    UNREACHABLE,
    ConnectionStatus,
    chat_completions_url,
    health_url,
    probe_http_health,
    probe_openai_compatible_llm,
)
from app.main import create_app
from app.storage.models import AppSetting, Base
from app.storage.session import create_engine

STATUS_VALUES = {CONNECTED, UNREACHABLE, UNAUTHORIZED, NOT_CONFIGURED}
AI_BACKEND_STATUS_FIELDS = {
    "endpoint_status",
    "stt_model",
    "vad_ready",
    "resident_tts_engine",
    "available_tts_engines",
    "loading_state",
    "vram_mb",
    "vram_headroom_mb",
}
DEFAULT_SETTINGS_EXTENSIONS = {
    "save_ai_audio": True,
    "save_mic_audio": False,
    "vad_threshold": 0.5,
    "vad_end_silence_ms": 700,
    "stt_model": "distil-large-v3",
    "tts_default_engine": "f5",
}


@pytest.fixture()
def settings_client(tmp_path: Path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-settings.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    app = create_app(
        Settings(
            web_public_url="https://127.0.0.1:8443",
            ai_backend_base_url="https://127.0.0.1:9443",
            llm_base_url="https://api.openai.com/v1",
            llm_model="gpt-test-default",
        ),
        static_client_dir=None,
    )

    async def override_session() -> AsyncIterator:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_settings_session] = override_session

    with TestClient(app) as client:
        yield client

    asyncio.run(engine.dispose())


def test_health_returns_exact_web_ui_payload(settings_client: TestClient) -> None:
    response = settings_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "rayme-web-ui", "status": "ok", "phase": "01"}


def test_get_and_patch_settings_persist_values_without_echoing_raw_key(
    settings_client: TestClient,
) -> None:
    raw_llm_api_key = "sk-raw_llm_api_key-server-secret"

    updated = settings_client.patch(
        "/api/settings",
        json={
            "web_url": "https://rayme.local:8443",
            "ai_backend_url": "https://ai.local:9443",
            "llm_base_url": "https://llm.local/v1",
            "llm_model": "configured-model",
            "llm_api_key": raw_llm_api_key,
            "save_ai_audio": False,
            "save_mic_audio": True,
            "vad_threshold": 0.65,
            "vad_end_silence_ms": 900,
        },
    )
    fetched = settings_client.get("/api/settings")

    assert updated.status_code == 200
    assert fetched.status_code == 200
    assert updated.json() == fetched.json()
    body = fetched.json()
    assert body["web_url"] == "https://rayme.local:8443"
    assert body["ai_backend_url"] == "https://ai.local:9443"
    assert body["llm_base_url"] == "https://llm.local/v1"
    assert body["llm_model"] == "configured-model"
    assert body["llm_api_key_configured"] is True
    assert "save_ai_audio" in body
    assert "save_mic_audio" in body
    assert "vad_threshold" in body
    assert "vad_end_silence_ms" in body
    assert body["save_ai_audio"] is False
    assert body["save_mic_audio"] is True
    assert body["vad_threshold"] == 0.65
    assert body["vad_end_silence_ms"] == 900
    assert "ai_backend_status" in body
    assert AI_BACKEND_STATUS_FIELDS.issubset(body["ai_backend_status"])
    assert raw_llm_api_key not in json.dumps(fetched.json())
    assert "llm_api_key" not in fetched.json()


def test_settings_defaults_include_audio_vad_and_ai_backend_status(
    settings_client: TestClient,
) -> None:
    body = settings_client.get("/api/settings").json()

    for key, expected in DEFAULT_SETTINGS_EXTENSIONS.items():
        assert key in body
        assert body[key] == expected

    assert "ai_backend_status" in body
    assert AI_BACKEND_STATUS_FIELDS.issubset(body["ai_backend_status"])


async def test_settings_service_persists_phase2_defaults_with_json_types(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'typed-settings.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    runtime_settings = Settings(
        web_public_url="https://127.0.0.1:8443",
        ai_backend_base_url="https://127.0.0.1:9443",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-test-default",
    )

    try:
        async with sessionmaker() as session:
            service = SettingsService(session, runtime_settings)
            defaults = await service.read()

            assert defaults.save_ai_audio is True
            assert defaults.save_mic_audio is False
            assert defaults.vad_threshold == 0.5
            assert defaults.vad_end_silence_ms == 700
            assert defaults.stt_model == "distil-large-v3"
            assert defaults.tts_default_engine == "f5"
            assert await session.get(AppSetting, SETTINGS_KEY) is None

            await service.update(
                {
                    "save_ai_audio": False,
                    "save_mic_audio": True,
                    "vad_threshold": "0.65",
                    "vad_end_silence_ms": "900",
                    "stt_model": " distil-large-v3 ",
                    "tts_default_engine": " f5 ",
                }
            )

            row = await session.get(AppSetting, SETTINGS_KEY)
            assert row is not None
            assert row.value_json["save_ai_audio"] is False
            assert row.value_json["save_mic_audio"] is True
            assert row.value_json["vad_threshold"] == 0.65
            assert isinstance(row.value_json["vad_threshold"], float)
            assert row.value_json["vad_end_silence_ms"] == 900
            assert isinstance(row.value_json["vad_end_silence_ms"], int)
            assert row.value_json["stt_model"] == "distil-large-v3"
            assert row.value_json["tts_default_engine"] == "f5"
    finally:
        await engine.dispose()


def test_connection_test_routes_return_only_allowed_status_values(
    settings_client: TestClient,
) -> None:
    settings_client.patch(
        "/api/settings",
        json={
            "web_url": "https://rayme.local:8443",
            "ai_backend_url": "https://ai.local:9443",
            "llm_base_url": "https://llm.local/v1",
            "llm_model": "configured-model",
            "save_ai_audio": True,
            "save_mic_audio": False,
            "vad_threshold": 0.5,
            "vad_end_silence_ms": 700,
        },
    )

    assert settings_client.get("/api/settings").json()["web_url"] == "https://rayme.local:8443"
    seen = {settings_client.post("/api/settings/test/web").json()["status"]}
    for status in (CONNECTED, UNREACHABLE, UNAUTHORIZED):
        settings_client.app.dependency_overrides[get_ai_backend_client] = _ai_backend_client(status)
        assert (
            settings_client.get("/api/settings").json()["ai_backend_url"]
            == "https://ai.local:9443"
        )
        response = settings_client.post("/api/settings/test/ai-backend")
        assert response.status_code == 200
        seen.add(response.json()["status"])

    settings_client.patch("/api/settings", json={"ai_backend_url": ""})
    settings_client.app.dependency_overrides[get_ai_backend_client] = _ai_backend_client(CONNECTED)
    seen.add(settings_client.post("/api/settings/test/ai-backend").json()["status"])

    assert seen == STATUS_VALUES


def test_ai_backend_status_bridge_returns_compact_backend_status(
    settings_client: TestClient,
) -> None:
    from app.api.ai_backend import get_ai_backend_client

    class FakeAiBackendClient:
        async def get_status(self, base_url: str) -> AiBackendStatus:
            assert base_url == "https://127.0.0.1:9443"
            return AiBackendStatus(
                status="degraded",
                stt_model="distil-large-v3",
                stt_compute_type="int8_float16",
                vad_ready=True,
                resident_tts_engine="f5",
                available_engines=[
                    EngineStatus(
                        id="f5",
                        label="F5-TTS",
                        available=True,
                        state="resident",
                    )
                ],
                loading_engine="xtts_v2",
                vram_used_mb=2300,
                vram_headroom_mb=8700,
            )

    settings_client.app.dependency_overrides[get_ai_backend_client] = FakeAiBackendClient

    response = settings_client.get("/api/ai-backend/status")

    assert response.status_code == 200
    assert response.json() == {
        "endpoint_status": "degraded",
        "status": "degraded",
        "stt_model": "distil-large-v3",
        "stt_compute_type": "int8_float16",
        "vad_ready": True,
        "resident_tts_engine": "f5",
        "available_engines": [
            {"id": "f5", "label": "F5-TTS", "available": True, "state": "resident"}
        ],
        "loading_engine": "xtts_v2",
        "vram_used_mb": 2300,
        "vram_headroom_mb": 8700,
    }


def test_ai_backend_settings_probe_uses_typed_client_and_treats_degraded_as_connected(
    settings_client: TestClient,
) -> None:
    from app.api.settings import get_ai_backend_client

    class DegradedAiBackendClient:
        async def get_status(self, base_url: str) -> AiBackendStatus:
            assert base_url == "https://ai.local:9443"
            return AiBackendStatus(
                status="degraded",
                stt_model="distil-large-v3",
                stt_compute_type="int8_float16",
                vad_ready=False,
                resident_tts_engine=None,
                available_engines=[],
                loading_engine=None,
                vram_used_mb=None,
                vram_headroom_mb=None,
            )

    settings_client.patch("/api/settings", json={"ai_backend_url": "https://ai.local:9443"})
    settings_client.app.dependency_overrides[get_ai_backend_client] = DegradedAiBackendClient

    response = settings_client.post("/api/settings/test/ai-backend")

    assert response.status_code == 200
    assert response.json() == {"status": CONNECTED}


def test_ai_backend_settings_probe_preserves_unreachable_unauthorized_and_not_configured(
    settings_client: TestClient,
) -> None:
    from app.api.settings import get_ai_backend_client

    class UnauthorizedAiBackendClient:
        async def get_status(self, _base_url: str) -> AiBackendStatus:
            raise AiBackendUnavailable(code="unauthorized", message="AI backend unreachable")

    class UnreachableAiBackendClient:
        async def get_status(self, _base_url: str) -> AiBackendStatus:
            raise AiBackendUnavailable(code="unreachable", message="AI backend unreachable")

    settings_client.patch("/api/settings", json={"ai_backend_url": "https://ai.local:9443"})
    settings_client.app.dependency_overrides[get_ai_backend_client] = UnauthorizedAiBackendClient
    assert settings_client.post("/api/settings/test/ai-backend").json() == {"status": UNAUTHORIZED}

    settings_client.app.dependency_overrides[get_ai_backend_client] = UnreachableAiBackendClient
    assert settings_client.post("/api/settings/test/ai-backend").json() == {"status": UNREACHABLE}

    settings_client.patch("/api/settings", json={"ai_backend_url": ""})
    assert settings_client.post("/api/settings/test/ai-backend").json() == {
        "status": NOT_CONFIGURED
    }


def test_llm_test_uses_server_side_settings_and_never_returns_api_key(
    settings_client: TestClient,
) -> None:
    captured: dict[str, str | None] = {}
    raw_llm_api_key = "sk-secret-value"

    async def fake_llm_probe(
        *,
        base_url: str | None,
        api_key: str | None,
        model: str | None,
    ) -> ConnectionStatus:
        captured.update({"base_url": base_url, "api_key": api_key, "model": model})
        return CONNECTED

    settings_client.app.dependency_overrides[get_llm_probe] = lambda: fake_llm_probe
    settings_client.patch(
        "/api/settings",
        json={
            "llm_base_url": "https://llm.local/v1",
            "llm_api_key": raw_llm_api_key,
            "llm_model": "configured-model",
            "save_ai_audio": True,
            "save_mic_audio": False,
        },
    )

    assert settings_client.get("/api/settings").json()["llm_base_url"] == "https://llm.local/v1"
    response = settings_client.post(
        "/api/settings/test/llm",
        json={
            "llm_base_url": "https://attacker.invalid/v1",
            "llm_api_key": "sk-browser-supplied",
            "llm_model": "attacker-model",
        },
    )

    assert response.status_code == 200
    assert response.request.url.path == "/api/settings/test/llm"
    assert response.json() == {"status": CONNECTED}
    assert captured == {
        "base_url": "https://llm.local/v1",
        "api_key": raw_llm_api_key,
        "model": "configured-model",
    }
    assert raw_llm_api_key not in json.dumps(response.json())
    assert "sk-browser-supplied" not in json.dumps(response.json())


def test_llm_health_is_settings_probe_not_local_llm_service(settings_client: TestClient) -> None:
    response = settings_client.post("/api/settings/test/llm")

    assert response.request.method == "POST"
    assert response.request.url.path == "/api/settings/test/llm"
    assert response.json()["status"] in STATUS_VALUES
    assert not (Path(__file__).resolve().parents[3] / "llm" / "app").exists()


async def test_ai_backend_probe_targets_configured_health_path() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        status = await probe_http_health("https://ai.local:9443/base", http_client=client)

    assert status == CONNECTED
    assert str(requests[0].url) == "https://ai.local:9443/base/health"
    assert health_url("https://ai.local:9443/base") == "https://ai.local:9443/base/health"


async def test_llm_probe_posts_openai_compatible_chat_completions_without_leaking_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        status = await probe_openai_compatible_llm(
            base_url="https://llm.local/v1",
            api_key="sk-server-secret",
            model="configured-model",
            http_client=client,
        )

    body = json.loads(requests[0].content)
    assert status == CONNECTED
    assert str(requests[0].url) == "https://llm.local/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer sk-server-secret"
    assert body["model"] == "configured-model"
    assert body["messages"] == [{"role": "user", "content": "ping"}]
    assert chat_completions_url("https://llm.local/v1") == (
        "https://llm.local/v1/chat/completions"
    )


async def test_probes_map_unauthorized_unreachable_and_not_configured() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(401))
    ) as unauthorized_client:
        llm_unauthorized = await probe_openai_compatible_llm(
            base_url="https://llm.local/v1",
            api_key="bad-key",
            model="configured-model",
            http_client=unauthorized_client,
        )

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)) as failing_client:
        ai_unreachable = await probe_http_health(
            "https://ai.local:9443",
            http_client=failing_client,
        )

    llm_not_configured = await probe_openai_compatible_llm(
        base_url="",
        api_key=None,
        model="configured-model",
    )

    assert llm_unauthorized == UNAUTHORIZED
    assert ai_unreachable == UNREACHABLE
    assert llm_not_configured == NOT_CONFIGURED


async def test_ai_backend_client_maps_status_transcription_and_synthesis_shapes() -> None:
    from app.domain.ai_backend_client import (
        AiBackendClient,
        AiBackendStatus,
        EngineStatus,
        SynthesisResult,
        TranscriptionResult,
    )

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/base/health":
            return httpx.Response(
                200,
                json={
                    "status": "degraded",
                    "stt_model": "distil-large-v3",
                    "stt_compute_type": "int8_float16",
                    "vad_ready": True,
                    "resident_tts_engine": "f5",
                    "available_engines": [
                        {"id": "f5", "label": "F5-TTS", "available": True, "state": "resident"}
                    ],
                    "loading_engine": None,
                    "vram_used_mb": 2300,
                    "vram_headroom_mb": 8700,
                },
            )
        if request.url.path == "/base/stt/transcribe":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "transcript": "Hello from the sample",
                    "language": "en",
                    "model": "distil-large-v3",
                    "compute_type": "int8_float16",
                    "segments": [{"start": 0.0, "end": 1.0, "text": "Hello from the sample"}],
                    "speech_detected": True,
                    "retry_allowed": False,
                    "manual_transcript_allowed": False,
                },
            )
        if request.url.path == "/base/synthesize":
            return httpx.Response(
                200,
                json={
                    "engine_id": "f5",
                    "content_type": "audio/wav",
                    "audio_base64": "UklGRg==",
                    "duration_ms": 420,
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ai_client = AiBackendClient(http_client=client)
        status = await ai_client.get_status("https://ai.local:9443/base")
        transcription = await ai_client.transcribe_sample(
            "https://ai.local:9443/base",
            b"sample-audio",
            "sample.wav",
            "audio/wav",
        )
        synthesis = await ai_client.synthesize(
            "https://ai.local:9443/base",
            {"text": "Hello", "engine_id": "f5"},
        )

    assert isinstance(status, AiBackendStatus)
    assert isinstance(status.available_engines[0], EngineStatus)
    assert status.status == "degraded"
    assert status.stt_model == "distil-large-v3"
    assert status.stt_compute_type == "int8_float16"
    assert status.vad_ready is True
    assert status.resident_tts_engine == "f5"
    assert status.vram_headroom_mb == 8700
    assert isinstance(transcription, TranscriptionResult)
    assert transcription.transcript == "Hello from the sample"
    assert transcription.manual_transcript_allowed is False
    assert isinstance(synthesis, SynthesisResult)
    assert synthesis.engine_id == "f5"
    assert synthesis.content_type == "audio/wav"
    assert [request.url.path for request in requests] == [
        "/base/health",
        "/base/stt/transcribe",
        "/base/synthesize",
    ]


async def test_ai_backend_client_sanitizes_public_error_payloads() -> None:
    from app.domain.ai_backend_client import (
        AiBackendClient,
        AiBackendProcessingError,
        AiBackendUnavailable,
    )

    def traceback_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            raise httpx.ConnectError(
                'Traceback RuntimeError File "C:\\secret\\adapter.py"',
                request=request,
            )
        if request.url.path.endswith("/transcribe"):
            return httpx.Response(500, text='Traceback RuntimeError File "/models/private.py"')
        if request.url.path.endswith("/synthesize"):
            return httpx.Response(200, text='Traceback RuntimeError File "/models/private.py"')
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(traceback_handler)) as client:
        ai_client = AiBackendClient(http_client=client)
        with pytest.raises(AiBackendUnavailable) as unreachable:
            await ai_client.get_status("https://ai.local:9443")
        with pytest.raises(AiBackendProcessingError) as transcription_failed:
            await ai_client.transcribe_sample(
                "https://ai.local:9443",
                b"sample-audio",
                "sample.wav",
                "audio/wav",
            )
        with pytest.raises(AiBackendUnavailable) as invalid_response:
            await ai_client.synthesize("https://ai.local:9443", {"text": "Hello"})

    public_errors = [
        unreachable.value.to_public_dict(),
        transcription_failed.value.to_public_dict(),
        invalid_response.value.to_public_dict(),
    ]
    assert public_errors == [
        {"code": "unreachable", "message": "AI backend unreachable"},
        {"code": "transcription_failed", "message": "Transcription failed"},
        {"code": "invalid_response", "message": "AI backend returned an invalid response"},
    ]
    rendered = json.dumps(public_errors)
    for forbidden in ("Traceback", 'File "', "RuntimeError", "C:\\", "/models/"):
        assert forbidden not in rendered


def _ai_backend_client(status: ConnectionStatus):
    class FakeAiBackendClient:
        async def get_status(self, _base_url: str) -> AiBackendStatus:
            if status == CONNECTED:
                return AiBackendStatus(status="ok")
            if status == UNAUTHORIZED:
                raise AiBackendUnavailable(
                    code="unauthorized",
                    message="AI backend unreachable",
                )
            raise AiBackendUnavailable(code="unreachable", message="AI backend unreachable")

    return FakeAiBackendClient
