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
    AiBackendClient,
    AiBackendReadiness,
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
    "status",
    "stt_model",
    "stt_compute_type",
    "vad_ready",
    "resident_tts_engine",
    "available_engines",
    "loading_engine",
    "vram_used_mb",
    "vram_headroom_mb",
}
DEFAULT_SETTINGS_EXTENSIONS = {
    "save_ai_audio": True,
    "save_mic_audio": False,
    "vad_threshold": 0.5,
    "vad_end_silence_ms": 700,
    "stt_model": "distil-large-v3",
    "tts_default_engine": "f5",
    "llm_disable_thinking": True,
}


def test_runtime_settings_include_long_ai_synthesis_timeout() -> None:
    from app.config import load_settings

    settings = load_settings(
        {
            "RAYME_AI_BACKEND_BASE_URL": "https://ai.local:9443",
            "RAYME_AI_BACKEND_SYNTHESIS_TIMEOUT_SECONDS": "180",
            "RAYME_AI_BACKEND_SERVICE_TOKEN": "service-token-0123456789abcdef0123456789",
            "RAYME_AI_BACKEND_CA_BUNDLE": "/etc/rayme/ai-ca.pem",
        }
    )

    assert settings.ai_backend_base_url == "https://ai.local:9443"
    assert settings.ai_backend_synthesis_timeout_seconds == 180
    assert settings.ai_backend_service_token == "service-token-0123456789abcdef0123456789"
    assert settings.ai_backend_ca_bundle == Path("/etc/rayme/ai-ca.pem")


async def test_ai_backend_client_sends_service_identity_on_webrtc_mutation() -> None:
    from app.domain.ai_backend_client import AiBackendClient

    token = "service-token-0123456789abcdef0123456789"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {token}"
        return httpx.Response(
            200,
            json={
                "session_id": "authorized-client",
                "answer": {"type": "answer", "sdp": "v=0\r\n"},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        ai_client = AiBackendClient(
            http_client=client,
            service_auth_token=token,
            trusted_base_url="https://ai.local:9443",
        )
        result = await ai_client.create_webrtc_offer(
            "https://ai.local:9443",
            {
                "session_id": "authorized-client",
                "thread_id": "thread-1",
                "voice_id": "voice-1",
                "engine_id": "f5",
                "offer": {"type": "offer", "sdp": "v=0\r\n"},
            },
        )

    assert result["session_id"] == "authorized-client"


async def test_ai_backend_client_never_authenticates_public_health() -> None:
    from app.domain.ai_backend_client import AiBackendClient

    token = "service-token-0123456789abcdef0123456789"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        ai_client = AiBackendClient(
            http_client=client,
            service_auth_token=token,
            trusted_base_url="https://ai.local:443",
        )
        result = await ai_client.get_status("https://AI.LOCAL")

    assert result.status == "ok"
    assert len(requests) == 1
    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize("redirect_status", [307, 308])
@pytest.mark.parametrize("request_kind", ["json_reference", "multipart_audio"])
async def test_ai_backend_client_never_replays_private_body_across_redirect(
    redirect_status: int,
    request_kind: str,
) -> None:
    token = "service-token-0123456789abcdef0123456789"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "ai.local":
            return httpx.Response(
                redirect_status,
                headers={"Location": "https://attacker.invalid/collect"},
            )
        return httpx.Response(200, json={"status": "stolen"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        ai_client = AiBackendClient(
            http_client=client,
            service_auth_token=token,
            trusted_base_url="https://ai.local:9443",
        )
        with pytest.raises(AiBackendUnavailable) as raised:
            if request_kind == "json_reference":
                await ai_client.synthesize(
                    "https://ai.local:9443",
                    {
                        "text": "private target payload",
                        "reference_audio_b64": "private-reference-audio",
                        "reference_transcript": "private reference transcript",
                    },
                )
            else:
                await ai_client.transcribe_sample(
                    "https://ai.local:9443",
                    b"private-multipart-audio",
                    "private-sample.wav",
                    "audio/wav",
                )

    assert raised.value.code == "untrusted_origin"
    assert len(requests) == 1
    assert str(requests[0].url).startswith("https://ai.local:9443/")
    assert requests[0].headers["authorization"] == f"Bearer {token}"
    if request_kind == "json_reference":
        assert json.loads(requests[0].content) == {
            "text": "private target payload",
            "reference_audio_b64": "private-reference-audio",
            "reference_transcript": "private reference transcript",
        }
    else:
        assert b"private-multipart-audio" in requests[0].content
        assert b"private-sample.wav" in requests[0].content


@pytest.mark.parametrize(
    "attacker_url",
    ["http://attacker.invalid", "https://attacker.invalid"],
)
async def test_ai_backend_client_rejects_untrusted_origin_before_payload_or_reference_leak(
    attacker_url: str,
) -> None:
    from app.domain.ai_backend_client import AiBackendClient

    requests: list[httpx.Request] = []
    token = "service-token-0123456789abcdef0123456789"
    voice_reference = {
        "reference_audio_b64": "private-reference-audio",
        "reference_transcript": "private reference transcript",
        "text": "private target payload",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ai_client = AiBackendClient(
            http_client=client,
            service_auth_token=token,
            trusted_base_url="https://ai.local:9443",
        )
        with pytest.raises(AiBackendUnavailable) as raised:
            await ai_client.synthesize(attacker_url, voice_reference)

    assert raised.value.code == "untrusted_origin"
    assert requests == []


def test_runtime_settings_reject_http_ai_backend_when_service_auth_is_enabled() -> None:
    token = "service-token-0123456789abcdef0123456789"

    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(
            ai_backend_base_url="http://ai.local:9443",
            ai_backend_service_token=token,
        )


async def test_ai_backend_client_verifies_configured_ca_and_rejects_certificate_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.domain.ai_backend_client import AiBackendClient, AiBackendUnavailable

    ca_bundle = tmp_path / "rayme-ca.pem"
    ca_bundle.write_text("test CA placeholder", encoding="utf-8")
    observed_verify: list[object] = []
    observed_follow_redirects: list[object] = []

    class CertificateRejectingClient:
        def __init__(self, *, timeout: float, verify: object) -> None:
            del timeout
            observed_verify.append(verify)

        async def __aenter__(self) -> "CertificateRejectingClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
            del method
            observed_follow_redirects.append(kwargs.get("follow_redirects"))
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("certificate verify failed", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", CertificateRejectingClient)
    client = AiBackendClient(ca_bundle=ca_bundle)

    with pytest.raises(AiBackendUnavailable) as raised:
        await client.get_status("https://substituted-ai.local:9443")

    assert raised.value.code == "unreachable"
    assert observed_verify == [str(ca_bundle)]
    assert observed_follow_redirects == [False]


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

    class DefaultAiBackendClient:
        async def get_status(self, _base_url: str) -> AiBackendStatus:
            return AiBackendStatus(
                status="ok",
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
                loading_engine=None,
                vram_used_mb=2300,
                vram_headroom_mb=8700,
            )

    app.dependency_overrides[get_ai_backend_client] = DefaultAiBackendClient

    with TestClient(app) as client:
        yield client

    asyncio.run(engine.dispose())


@pytest.fixture()
def authenticated_settings_client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, list[httpx.Request]]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'authenticated-settings.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    requests: list[httpx.Request] = []
    token = "service-token-0123456789abcdef0123456789"
    trusted_base_url = "https://192.168.1.199:9443"

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    app = create_app(
        Settings(
            web_public_url="https://192.168.1.199:8443",
            ai_backend_base_url=trusted_base_url,
            ai_backend_service_token=token,
            ai_backend_ca_bundle=tmp_path / "mkcert-rootCA.pem",
        ),
        static_client_dir=None,
    )

    async def override_session() -> AsyncIterator:
        async with sessionmaker() as session:
            yield session

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_settings_session] = override_session
    app.dependency_overrides[get_ai_backend_client] = lambda: AiBackendClient(
        http_client=transport_client,
        service_auth_token=token,
        trusted_base_url=trusted_base_url,
        ca_bundle=tmp_path / "mkcert-rootCA.pem",
    )

    with TestClient(app) as client:
        yield client, requests

    asyncio.run(transport_client.aclose())
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
            "llm_disable_thinking": False,
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
    assert body["llm_disable_thinking"] is False
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


@pytest.mark.parametrize(
    "attacker_url",
    ["http://attacker.invalid:9443", "https://attacker.invalid:9443"],
)
def test_authenticated_settings_patch_rejects_untrusted_ai_origin_without_probe(
    authenticated_settings_client: tuple[TestClient, list[httpx.Request]],
    attacker_url: str,
) -> None:
    client, requests = authenticated_settings_client

    response = client.patch("/api/settings", json={"ai_backend_url": attacker_url})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ai_backend_url_operator_managed"
    assert requests == []


def test_authenticated_settings_patch_allows_canonical_omen_origin_and_public_probe(
    authenticated_settings_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, requests = authenticated_settings_client

    response = client.patch(
        "/api/settings",
        json={"ai_backend_url": "https://192.168.1.199:9443"},
    )

    assert response.status_code == 200
    assert response.json()["ai_backend_url"] == "https://192.168.1.199:9443"
    assert len(requests) == 1
    assert str(requests[0].url) == "https://192.168.1.199:9443/health"
    assert "authorization" not in requests[0].headers


def test_settings_defaults_include_audio_vad_and_ai_backend_status(
    settings_client: TestClient,
) -> None:
    body = settings_client.get("/api/settings").json()

    for key, expected in DEFAULT_SETTINGS_EXTENSIONS.items():
        assert key in body
        assert body[key] == expected

    assert "ai_backend_status" in body
    assert AI_BACKEND_STATUS_FIELDS.issubset(body["ai_backend_status"])


def test_settings_rejects_vad_values_outside_call_phase_bounds(
    settings_client: TestClient,
) -> None:
    assert settings_client.patch("/api/settings", json={"vad_threshold": -0.01}).status_code == 422
    assert settings_client.patch("/api/settings", json={"vad_threshold": 1.01}).status_code == 422
    assert (
        settings_client.patch("/api/settings", json={"vad_end_silence_ms": 99}).status_code == 422
    )
    assert (
        settings_client.patch("/api/settings", json={"vad_end_silence_ms": 3001}).status_code == 422
    )


def test_settings_response_includes_compact_live_ai_backend_status(
    settings_client: TestClient,
) -> None:
    class ScriptedAiBackendClient:
        async def get_status(self, base_url: str) -> AiBackendStatus:
            assert base_url == "https://ai.local:9443"
            return AiBackendStatus(
                status="ok",
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
                loading_engine=None,
                vram_used_mb=2300,
                vram_headroom_mb=8700,
            )

    settings_client.app.dependency_overrides[get_ai_backend_client] = ScriptedAiBackendClient
    settings_client.patch("/api/settings", json={"ai_backend_url": "https://ai.local:9443"})

    body = settings_client.get("/api/settings").json()

    assert body["ai_backend_status"] == {
        "endpoint_status": "ok",
        "status": "ok",
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
    }


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
            assert defaults.llm_disable_thinking is True
            assert await session.get(AppSetting, SETTINGS_KEY) is None

            await service.update(
                {
                    "save_ai_audio": False,
                    "save_mic_audio": True,
                    "vad_threshold": "0.65",
                    "vad_end_silence_ms": "900",
                    "stt_model": " distil-large-v3 ",
                    "tts_default_engine": " f5 ",
                    "llm_disable_thinking": False,
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
            assert row.value_json["llm_disable_thinking"] is False
    finally:
        await engine.dispose()


async def test_authenticated_settings_ignore_persisted_untrusted_ai_backend_override(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'untrusted-endpoint.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    runtime_settings = Settings(
        ai_backend_base_url="https://192.168.1.199:9443",
        ai_backend_service_token="service-token-0123456789abcdef0123456789",
    )

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessionmaker() as session:
            session.add(
                AppSetting(
                    key=SETTINGS_KEY,
                    value_json={"ai_backend_url": "https://attacker.invalid:9443"},
                )
            )
            await session.commit()

            settings = await SettingsService(session, runtime_settings).read()

            assert settings.ai_backend_url == "https://192.168.1.199:9443"
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
            settings_client.get("/api/settings").json()["ai_backend_url"] == "https://ai.local:9443"
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

    class ScriptedAiBackendClient:
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

    settings_client.app.dependency_overrides[get_ai_backend_client] = ScriptedAiBackendClient

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


def test_ai_backend_readiness_bridge_fails_closed_on_token_mismatch(
    settings_client: TestClient,
) -> None:
    from app.api.ai_backend import get_ai_backend_client

    class MismatchedCredentialClient:
        async def get_authenticated_readiness(
            self,
            base_url: str,
        ) -> AiBackendReadiness:
            assert base_url == "https://127.0.0.1:9443"
            raise AiBackendUnavailable(
                code="unauthorized",
                message="AI backend is unreachable",
            )

    settings_client.app.dependency_overrides[get_ai_backend_client] = MismatchedCredentialClient

    response = settings_client.get("/api/ai-backend/readiness")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "unauthorized"


def test_ai_backend_readiness_bridge_returns_authenticated_proof(
    settings_client: TestClient,
) -> None:
    from app.api.ai_backend import get_ai_backend_client

    class AuthenticatedClient:
        async def get_authenticated_readiness(
            self,
            base_url: str,
        ) -> AiBackendReadiness:
            assert base_url == "https://127.0.0.1:9443"
            return AiBackendReadiness(
                service="rayme-ai-backend",
                status="ready",
                authenticated=True,
            )

    settings_client.app.dependency_overrides[get_ai_backend_client] = AuthenticatedClient

    response = settings_client.get("/api/ai-backend/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "service": "rayme-ai-backend",
        "status": "ready",
        "authenticated": True,
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

    async def scripted_llm_probe(
        *,
        base_url: str | None,
        api_key: str | None,
        model: str | None,
    ) -> ConnectionStatus:
        captured.update({"base_url": base_url, "api_key": api_key, "model": model})
        return CONNECTED

    settings_client.app.dependency_overrides[get_llm_probe] = lambda: scripted_llm_probe
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
    assert chat_completions_url("https://llm.local/v1") == ("https://llm.local/v1/chat/completions")


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
        if request.url.path == "/base/tts/synthesize":
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
        "/base/tts/synthesize",
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


async def test_ai_backend_client_preserves_sanitized_webrtc_offer_failure_detail() -> None:
    from app.domain.ai_backend_client import AiBackendClient, AiBackendProcessingError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/webrtc/offer"):
            return httpx.Response(
                502,
                json={
                    "detail": {
                        "code": "webrtc_offer_failed",
                        "message": "WebRTC offer could not be accepted",
                    }
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ai_client = AiBackendClient(http_client=client)
        with pytest.raises(AiBackendProcessingError) as failed:
            await ai_client.create_webrtc_offer(
                "https://ai.local:9443",
                {
                    "session_id": "rtc-call-1",
                    "thread_id": "thread-1",
                    "voice_id": "voice-1",
                    "engine_id": "f5",
                    "offer": {"type": "offer", "sdp": "v=0\r\n"},
                },
            )

    assert failed.value.to_public_dict() == {
        "code": "webrtc_offer_failed",
        "message": "WebRTC offer could not be accepted",
    }


async def test_ai_backend_client_preserves_peer_commit_reconciliation_status() -> None:
    from app.domain.ai_backend_client import AiBackendClient, AiBackendProcessingError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/peer-promotion"):
            return httpx.Response(
                409,
                json={
                    "detail": {
                        "code": "webrtc_peer_already_committed",
                        "message": r"private backend path C:\\models\\peer",
                    }
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ai_client = AiBackendClient(http_client=client)
        with pytest.raises(AiBackendProcessingError) as failed:
            await ai_client.promote_call_peer(
                "https://ai.local:9443",
                "rtc-call-1",
                1,
                "commit",
            )

    assert failed.value.to_public_dict() == {
        "code": "webrtc_peer_already_committed",
        "message": "Replacement peer generation was already committed",
    }


async def test_ai_backend_client_uses_stt_timeout_for_reconnect_audio_backfill() -> None:
    from app.domain.ai_backend_client import AiBackendClient

    class CapturingHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
            self.requests.append({"method": method, "url": url, **kwargs})
            return httpx.Response(
                200,
                json={"session_id": "rtc-call-1", "status": "accepted", "frames": 0},
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
        {"pcm_b64": "", "sample_rate": 16000, "channels": 1, "final": True},
    )

    assert result["status"] == "accepted"
    assert http_client.requests[0]["timeout"] == 120.0


def _ai_backend_client(status: ConnectionStatus):
    class ScriptedAiBackendClient:
        async def get_status(self, _base_url: str) -> AiBackendStatus:
            if status == CONNECTED:
                return AiBackendStatus(status="ok")
            if status == UNAUTHORIZED:
                raise AiBackendUnavailable(
                    code="unauthorized",
                    message="AI backend unreachable",
                )
            raise AiBackendUnavailable(code="unreachable", message="AI backend unreachable")

    return ScriptedAiBackendClient


def test_prompt_generation_defaults_are_public_without_writing_legacy_settings(
    settings_client: TestClient,
) -> None:
    body = settings_client.get("/api/settings").json()

    assert body["prompt_generation"]["mode"] == "roleplay"
    assert body["prompt_generation"]["model_profile"] == "auto"
    assert body["prompt_generation"]["context_limit"] == 16_384
    assert body["prompt_generation"]["max_tokens"] == 512
    assert body["prompt_generation"]["temperature"] == 0.8
    assert body["prompt_generation"]["top_p"] == 0.95
    assert body["prompt_generation"]["min_p"] == 0.05
    assert body["prompt_generation"]["top_k"] == 40
    assert body["prompt_generation"]["repetition_penalty"] == 1.05
    assert body["prompt_generation"]["presence_penalty"] == 0.0
    assert body["prompt_generation"]["frequency_penalty"] == 0.0


def test_nested_prompt_patch_round_trips_unicode_and_preserves_private_and_unrelated_state(
    settings_client: TestClient,
) -> None:
    api_key = "sk-prompt-profile-canary"
    first = settings_client.patch(
        "/api/settings",
        json={
            "llm_api_key": api_key,
            "ai_backend_url": "https://ai.local:9443",
            "save_ai_audio": False,
            "vad_threshold": 0.65,
        },
    )
    assert first.status_code == 200

    updated = settings_client.patch(
        "/api/settings",
        json={
            "prompt_generation": {
                "mode": "custom",
                "custom": {
                    "main": "  Exact Ω café — scene  ",
                    "auxiliary": "",
                    "post_history": "\t",
                },
                "model_profile": "qwen_llama_server",
                "context_limit": 32_768,
                "max_tokens": 1_024,
                "temperature": 1.10,
                "top_p": 0.91,
                "min_p": 0.07,
                "top_k": 77,
                "repetition_penalty": 1.09,
                "presence_penalty": -0.2,
                "frequency_penalty": 0.3,
            }
        },
    )
    fetched = settings_client.get("/api/settings")

    assert updated.status_code == 200
    assert updated.json() == fetched.json()
    body = fetched.json()
    prompt = body["prompt_generation"]
    assert prompt["custom"] == {
        "main": "  Exact Ω café — scene  ",
        "auxiliary": "",
        "post_history": "\t",
    }
    assert prompt["mode"] == "custom"
    assert prompt["model_profile"] == "qwen_llama_server"
    assert prompt["context_limit"] == 32_768
    assert isinstance(prompt["context_limit"], int)
    assert prompt["temperature"] == 1.10
    assert isinstance(prompt["temperature"], float)
    assert body["ai_backend_url"] == "https://ai.local:9443"
    assert body["save_ai_audio"] is False
    assert body["vad_threshold"] == 0.65
    assert body["llm_api_key_configured"] is True
    assert api_key not in json.dumps(body)
    assert "llm_api_key" not in body


def test_partial_nested_prompt_patch_preserves_omitted_prompt_and_endpoint_values(
    settings_client: TestClient,
) -> None:
    before = settings_client.get("/api/settings").json()

    response = settings_client.patch(
        "/api/settings",
        json={"prompt_generation": {"temperature": 1.25}},
    )

    assert response.status_code == 200
    after = response.json()
    assert after["prompt_generation"]["temperature"] == 1.25
    assert after["prompt_generation"]["roleplay"] == before["prompt_generation"]["roleplay"]
    assert after["prompt_generation"]["assistant"] == before["prompt_generation"]["assistant"]
    assert after["prompt_generation"]["custom"] == before["prompt_generation"]["custom"]
    for key in (
        "web_url",
        "ai_backend_url",
        "llm_base_url",
        "llm_model",
        "save_ai_audio",
        "save_mic_audio",
        "vad_threshold",
        "vad_end_silence_ms",
        "stt_model",
        "tts_default_engine",
    ):
        assert after[key] == before[key]


def test_invalid_nested_prompt_value_returns_stable_field_contract(
    settings_client: TestClient,
) -> None:
    response = settings_client.patch(
        "/api/settings",
        json={"prompt_generation": {"context_limit": 2_049}},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "invalid_prompt_generation",
        "field": "context_limit",
        "message": "Context limit must be between 2,048 and 131,072, in steps of 1,024.",
    }
