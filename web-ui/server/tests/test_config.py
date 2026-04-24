"""Web host configuration and security middleware tests."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, load_settings
from app.main import create_app
from app.security import CSP_HEADER, configure_cors

RUNNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_dev_https.py"


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_dev_https", RUNNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    assert "script-src 'self' 'unsafe-inline'" in CSP_HEADER
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert (
        "script-src 'self' 'unsafe-inline'"
        in response.headers["content-security-policy"]
    )


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


def test_https_runner_help_contains_direct_ip_browser_url(capsys: pytest.CaptureFixture[str]) -> None:
    runner = load_runner()

    with pytest.raises(SystemExit) as exc_info:
        runner.main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "RAYME_WEB_BIND_HOST=192.168.1.199" in output
    assert "RAYME_WEB_PORT=8443" in output
    assert "https://192.168.1.199:8443" in output


def test_https_runner_check_config_accepts_explicit_localhost(tmp_path: Path) -> None:
    runner = load_runner()
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")

    result = runner.main(
        [
            "--check-config",
            "--host",
            "127.0.0.1",
            "--port",
            "8443",
            "--cert",
            str(cert_path),
            "--key",
            str(key_path),
        ]
    )

    assert result == 0


def test_https_runner_check_config_rejects_wildcard_host(tmp_path: Path) -> None:
    runner = load_runner()
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        runner.main(
            [
                "--check-config",
                "--host",
                "0.0.0.0",
                "--port",
                "8443",
                "--cert",
                str(cert_path),
                "--key",
                str(key_path),
            ]
        )

    assert exc_info.value.code != 0


def test_https_runner_passes_tls_files_to_uvicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = load_runner()
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(runner.uvicorn, "run", fake_run)

    result = runner.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "8443",
            "--cert",
            str(cert_path),
            "--key",
            str(key_path),
        ]
    )

    assert result == 0
    assert captured["app"] == "app.main:create_app"
    assert captured["factory"] is True
    assert captured["ssl_certfile"] == str(cert_path)
    assert captured["ssl_keyfile"] == str(key_path)
