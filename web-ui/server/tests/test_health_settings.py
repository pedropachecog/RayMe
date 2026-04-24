"""Health and endpoint Settings contracts."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

STATUS_VALUES = ("Connected", "Unreachable", "Unauthorized", "Not configured")


def test_health_settings_status_values_are_connected_unreachable_unauthorized_not_configured() -> None:
    client = TestClient(create_app())

    web_health = client.get("/health")
    settings = client.get("/api/settings")

    assert web_health.status_code == 200
    assert web_health.json()["status"] in STATUS_VALUES

    payload = settings.json()
    assert payload["web_ui"]["status"] in STATUS_VALUES
    assert payload["ai_backend"]["status"] in STATUS_VALUES
    assert payload["ai_backend"]["health_path"] == "/health"
    assert payload["llm"]["status"] in STATUS_VALUES
    assert payload["llm"]["test_path"] == "/api/settings/test/llm"


def test_settings_never_return_raw_llm_api_key() -> None:
    client = TestClient(create_app())
    raw_llm_api_key = "sk-raw_llm_api_key-server-secret"

    save_response = client.put(
        "/api/settings",
        json={
            "llm": {
                "base_url": "https://api.openai-compatible.local/v1",
                "model": "configured-model",
                "api_key": raw_llm_api_key,
            }
        },
    )
    browser_payload = save_response.json()

    serialized = json.dumps(browser_payload)
    assert raw_llm_api_key not in serialized
    assert "api_key" not in browser_payload.get("llm", {})
    assert browser_payload["llm"]["api_key_masked"].startswith("sk-")
    assert browser_payload["llm"]["api_key_masked"].endswith("cret")


def test_llm_status_is_server_side_settings_probe_not_local_service() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/settings/test/llm",
        json={
            "base_url": "https://api.openai-compatible.local/v1",
            "model": "configured-model",
        },
    )

    payload = response.json()
    assert response.request.method == "POST"
    assert response.request.url.path == "/api/settings/test/llm"
    assert payload["status"] in STATUS_VALUES
    assert payload["probe"] == "openai_compatible_chat_completions"
    assert payload["target_base_url"] == "https://api.openai-compatible.local/v1"
    assert "/health" not in json.dumps(payload)
    assert not (Path(__file__).resolve().parents[2] / "llm" / "app").exists()
