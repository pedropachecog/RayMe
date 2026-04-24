from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "scripts" / "run_https.py"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_health_returns_exact_phase_one_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "rayme-ai-backend",
        "status": "ok",
        "phase": "01",
        "capabilities": ["health"],
    }


def test_https_runner_check_config_accepts_explicit_host() -> None:
    result = run_runner(
        "--check-config",
        "--host",
        "127.0.0.1",
        "--port",
        "9443",
        "--cert",
        str(PYPROJECT),
        "--key",
        str(PYPROJECT),
    )

    assert result.returncode == 0, result.stderr


def test_https_runner_rejects_wildcard_host_in_check_mode() -> None:
    result = run_runner(
        "--check-config",
        "--host",
        "0.0.0.0",
        "--port",
        "9443",
        "--cert",
        str(PYPROJECT),
        "--key",
        str(PYPROJECT),
    )

    assert result.returncode != 0
    assert "0.0.0.0" in result.stderr


def test_https_runner_requires_cert_and_key_paths() -> None:
    result = run_runner("--check-config", "--host", "127.0.0.1")

    assert result.returncode != 0
    assert "--cert" in result.stderr
    assert "--key" in result.stderr


def test_https_runner_help_documents_direct_ip_health_url() -> None:
    result = run_runner("--help")
    output = result.stdout + result.stderr

    assert result.returncode == 0
    assert "https://192.168.1.199:9443/health" in output
    assert "--cert" in output
    assert "--key" in output
    assert "9443" in output
