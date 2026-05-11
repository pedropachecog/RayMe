from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi.testclient import TestClient

from app.config import AiBackendSettings
from app.main import create_app
from app.models.engine_metadata import ENGINE_METADATA
from app.models.model_manager import ModelManager

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "scripts" / "run_https.py"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def load_runner_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ai_backend_run_https", RUNNER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScriptedTtsAdapter:
    def __init__(self, engine_id: str) -> None:
        self.engine_id = engine_id
        self.loaded = False

    def startup_self_test(self) -> None:
        return None

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False


def create_app_with_scripted_models() -> Any:
    app = create_app()
    app.state.model_manager = ModelManager(
        AiBackendSettings(load_models_on_startup=False),
        tts_adapters={engine.id: ScriptedTtsAdapter(engine.id) for engine in ENGINE_METADATA},
        vram_probe=lambda: {"used_mb": 2300, "headroom_mb": 8700},
    )
    return app


def run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_health_returns_phase_two_model_residency_contract() -> None:
    client = TestClient(create_app_with_scripted_models())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "rayme-ai-backend"
    assert payload["status"] in {"ok", "degraded", "starting", "error"}
    assert payload["phase"] == "02"
    assert payload["stt_model"] == "distil-large-v3"
    assert payload["stt_compute_type"] == "int8_float16"
    assert payload["vad_ready"] is True
    assert payload["resident_tts_engine"] == "f5"
    assert payload["loading_engine"] is None
    assert isinstance(payload["vram_used_mb"], int | float)
    assert isinstance(payload["vram_headroom_mb"], int | float)

    available_engines = payload["available_engines"]
    assert isinstance(available_engines, list)
    engine_ids = {
        engine.get("id") or engine.get("engine_id")
        for engine in available_engines
    }
    assert engine_ids == {
        "f5",
        "xtts_v2",
        "qwen3_0_6b",
        "luxtts",
        "chatterbox_turbo",
        "tada_1b",
        "voxcpm2",
    }
    resident_engines = [
        engine.get("id") or engine.get("engine_id")
        for engine in available_engines
        if engine.get("resident") is True
        or engine.get("state") == "resident"
        or engine.get("availability") == "resident"
    ]
    assert resident_engines == ["f5"]


def test_health_does_not_return_raw_exception_text_in_public_payload() -> None:
    client = TestClient(create_app_with_scripted_models())

    response = client.get("/health")

    assert response.status_code == 200
    rendered = response.text
    for forbidden in (
        "Traceback",
        "RuntimeError",
        "ValueError",
        "CUDA out of memory",
        "C:\\",
        "/models/",
    ):
        assert forbidden not in rendered

    for engine in response.json()["available_engines"]:
        if engine.get("available") is False:
            assert engine["unavailable_reason"]
            reason = str(engine["unavailable_reason"])
            assert "Traceback" not in reason
            assert "RuntimeError" not in reason


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


def test_build_log_config_attaches_handler_to_app_loggers() -> None:
    """Regression: uvicorn's default config silently discards `app.*` loggers.

    Without an explicit handler on the `app` logger, every `logger.info(...)`
    call from `app.api.webrtc` (the `[rayme-call]` instrumentation) is
    propagated to a handlerless root logger and dropped, leaving the OMEN
    log files devoid of post-offer call lifecycle evidence.
    """
    runner = load_runner_module()

    config = runner.build_log_config()

    assert config["version"] == 1
    assert config["disable_existing_loggers"] is False
    # uvicorn's own loggers must remain wired up.
    assert "uvicorn" in config["loggers"]
    assert "uvicorn.access" in config["loggers"]
    # `app.*` and `aiortc` module loggers must now have a stderr handler.
    app_logger = config["loggers"]["app"]
    assert app_logger["handlers"] == ["default"]
    assert app_logger["level"] == "INFO"
    assert app_logger["propagate"] is False
    aiortc_logger = config["loggers"]["aiortc"]
    assert aiortc_logger["handlers"] == ["default"]
    assert aiortc_logger["level"] == "INFO"
    # The handler the loggers reference must actually exist.
    assert "default" in config["handlers"]
