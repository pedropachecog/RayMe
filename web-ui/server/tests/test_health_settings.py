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

from app.api.settings import get_ai_backend_probe, get_llm_probe, get_settings_session
from app.config import Settings
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
from app.storage.models import Base
from app.storage.session import create_engine

STATUS_VALUES = {CONNECTED, UNREACHABLE, UNAUTHORIZED, NOT_CONFIGURED}


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
        },
    )
    fetched = settings_client.get("/api/settings")

    assert updated.status_code == 200
    assert fetched.status_code == 200
    assert updated.json() == fetched.json()
    assert fetched.json() == {
        "web_url": "https://rayme.local:8443",
        "ai_backend_url": "https://ai.local:9443",
        "llm_base_url": "https://llm.local/v1",
        "llm_model": "configured-model",
        "llm_api_key_configured": True,
    }
    assert raw_llm_api_key not in json.dumps(fetched.json())
    assert "llm_api_key" not in fetched.json()


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
        },
    )

    seen = {settings_client.post("/api/settings/test/web").json()["status"]}
    for status in (CONNECTED, UNREACHABLE, UNAUTHORIZED):
        settings_client.app.dependency_overrides[get_ai_backend_probe] = _health_probe(status)
        response = settings_client.post("/api/settings/test/ai-backend")
        assert response.status_code == 200
        seen.add(response.json()["status"])

    settings_client.patch("/api/settings", json={"ai_backend_url": ""})
    settings_client.app.dependency_overrides[get_ai_backend_probe] = _health_probe(CONNECTED)
    seen.add(settings_client.post("/api/settings/test/ai-backend").json()["status"])

    assert seen == STATUS_VALUES


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
        },
    )

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


def _health_probe(status: ConnectionStatus):
    async def fake_probe(_base_url: str | None) -> ConnectionStatus:
        return status

    return lambda: fake_probe
