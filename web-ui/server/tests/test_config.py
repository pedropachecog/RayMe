"""Web host configuration and security middleware tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, load_settings
from app.main import create_app
from app.security import CSP_HEADER, configure_cors


def test_default_web_host_is_localhost() -> None:
    settings = load_settings({})

    assert settings.web_bind_host == "127.0.0.1"
    assert settings.host == "127.0.0.1"
    assert settings.web_port == 8443
    assert settings.allowed_origins == ["https://127.0.0.1:8443"]


def test_rayme_web_bind_host_rejects_wildcard() -> None:
    with pytest.raises(ValidationError, match="RAYME_WEB_BIND_HOST"):
        load_settings({"RAYME_WEB_BIND_HOST": "0.0.0.0"})


def test_rayme_allowed_origins_rejects_wildcard() -> None:
    with pytest.raises(ValidationError, match="RAYME_ALLOWED_ORIGINS"):
        load_settings({"RAYME_ALLOWED_ORIGINS": "*"})


def test_allowed_origins_are_comma_separated_explicit_values() -> None:
    settings = load_settings(
        {
            "RAYME_ALLOWED_ORIGINS": (
                "https://192.168.1.199:8443, https://rayme.local:8443"
            )
        }
    )

    assert settings.allowed_origins == [
        "https://192.168.1.199:8443",
        "https://rayme.local:8443",
    ]


def test_configure_cors_allows_only_configured_origin() -> None:
    app = create_app(
        Settings(
            allowed_origins=["https://192.168.1.199:8443"],
            web_bind_host="127.0.0.1",
        ),
        static_client_dir=None,
    )
    client = TestClient(app)

    response = client.options(
        "/api/settings",
        headers={
            "Origin": "https://192.168.1.199:8443",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://192.168.1.199:8443"
    assert "access-control-allow-credentials" not in response.headers


def test_configure_cors_rejects_wildcard_origins() -> None:
    app = create_app(static_client_dir=None)

    with pytest.raises(ValueError, match="wildcards"):
        configure_cors(app, ["*"])


def test_csp_contains_default_src_self() -> None:
    app = create_app(static_client_dir=None)
    client = TestClient(app)

    response = client.get("/")

    assert "default-src 'self'" in CSP_HEADER
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_static_client_mount_is_conditional_on_build_output(tmp_path: Path) -> None:
    missing_build = tmp_path / "missing"
    app_without_build = create_app(static_client_dir=missing_build)
    assert not any(route.name == "client" for route in app_without_build.routes)

    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "200.html").write_text("<main>RayMe</main>", encoding="utf-8")
    app_with_build = create_app(static_client_dir=build_dir)
    assert any(route.name == "client" for route in app_with_build.routes)

    response = TestClient(app_with_build).get("/chat/example-thread")
    assert response.status_code == 200
    assert response.text == "<main>RayMe</main>"
