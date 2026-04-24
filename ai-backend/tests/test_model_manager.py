from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from dataclasses import asdict, is_dataclass
from typing import Any

import pytest

EXPECTED_TTS_ENGINE_IDS = (
    "f5",
    "xtts_v2",
    "qwen3_0_6b",
    "luxtts",
    "chatterbox_turbo",
    "tada_1b",
)
EXPECTED_STATUS_VALUES = {"ok", "degraded", "starting", "error"}
EXPECTED_SWITCH_STATES = {"idle", "loading", "resident", "unavailable"}
FORBIDDEN_PUBLIC_ERROR_TEXT = (
    "Traceback",
    "RuntimeError",
    "CUDA out of memory",
    "C:\\",
    "/models/",
)


class FakeTtsAdapter:
    def __init__(
        self,
        engine_id: str,
        events: list[str],
        *,
        fail_self_test: bool = False,
    ) -> None:
        self.engine_id = engine_id
        self.events = events
        self.fail_self_test = fail_self_test
        self.loaded = False

    def startup_self_test(self) -> None:
        self.events.append(f"{self.engine_id}:self_test")
        if self.fail_self_test:
            raise RuntimeError(
                "Traceback: CUDA out of memory while loading C:\\secret\\model.bin"
            )

    def self_test(self) -> None:
        self.startup_self_test()

    def load(self) -> None:
        self.events.append(f"{self.engine_id}:load")
        self.loaded = True

    def unload(self) -> None:
        self.events.append(f"{self.engine_id}:unload")
        self.loaded = False


def _require_attr(module: object, attr: str) -> Any:
    try:
        return getattr(module, attr)
    except AttributeError:
        pytest.fail(f"{module!r} must expose {attr}")


def _complete(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    pytest.fail(f"Expected dict-like contract object, got {type(value)!r}")


def _health_mapping(manager: Any) -> dict[str, Any]:
    return _to_mapping(_complete(manager.health()))


def _engine_statuses(health: dict[str, Any]) -> dict[str, dict[str, Any]]:
    engines = health.get("available_engines")
    assert isinstance(engines, list), "available_engines must be a list of engine status objects"

    statuses: dict[str, dict[str, Any]] = {}
    for engine in engines:
        mapping = _to_mapping(engine)
        engine_id = mapping.get("id") or mapping.get("engine_id")
        assert engine_id in EXPECTED_TTS_ENGINE_IDS
        statuses[str(engine_id)] = mapping
    return statuses


def _resident_engine_ids(statuses: dict[str, dict[str, Any]]) -> list[str]:
    residents: list[str] = []
    for engine_id, status in statuses.items():
        state = status.get("state") or status.get("availability") or status.get("status")
        if status.get("resident") is True or state == "resident":
            residents.append(engine_id)
    return residents


def _assert_no_raw_exception_text(payload: Any) -> None:
    rendered = json.dumps(payload, sort_keys=True)
    for forbidden in FORBIDDEN_PUBLIC_ERROR_TEXT:
        assert forbidden not in rendered


def _build_manager(*, failing_engine: str | None = None) -> tuple[Any, dict[str, FakeTtsAdapter], list[str]]:
    config_module = importlib.import_module("app.config")
    manager_module = importlib.import_module("app.models.model_manager")

    AiBackendSettings = _require_attr(config_module, "AiBackendSettings")
    ModelManager = _require_attr(manager_module, "ModelManager")

    settings = AiBackendSettings(load_models_on_startup=False)
    events: list[str] = []
    adapters = {
        engine_id: FakeTtsAdapter(
            engine_id,
            events,
            fail_self_test=engine_id == failing_engine,
        )
        for engine_id in EXPECTED_TTS_ENGINE_IDS
    }

    constructor_attempts = (
        {
            "settings": settings,
            "tts_adapters": adapters,
            "vram_probe": lambda: {"used_mb": 2300, "headroom_mb": 8700},
        },
        {
            "settings": settings,
            "adapters": adapters,
            "vram_probe": lambda: {"used_mb": 2300, "headroom_mb": 8700},
        },
        {"settings": settings, "tts_adapters": adapters},
        {"settings": settings, "adapters": adapters},
        {"settings": settings},
    )
    for kwargs in constructor_attempts:
        try:
            manager = ModelManager(**kwargs)
            break
        except TypeError:
            continue
    else:
        manager = ModelManager(settings)

    if not hasattr(manager, "tts_adapters"):
        setattr(manager, "tts_adapters", adapters)
    if not hasattr(manager, "vram_probe"):
        setattr(manager, "vram_probe", lambda: {"used_mb": 2300, "headroom_mb": 8700})

    return manager, adapters, events


def test_model_manager_defaults_match_phase_zero_decisions() -> None:
    config_module = importlib.import_module("app.config")
    AiBackendSettings = _require_attr(config_module, "AiBackendSettings")

    settings = AiBackendSettings(load_models_on_startup=False)

    assert settings.stt_model == "distil-large-v3"
    assert settings.stt_compute_type == "int8_float16"
    assert settings.stt_language == "en"
    assert settings.default_tts_engine == "f5"
    assert settings.vram_budget_mb == 11000


def test_model_manager_health_reports_one_hot_residency_and_vram_headroom() -> None:
    manager, _, _ = _build_manager()

    _complete(manager.startup())
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["status"] in EXPECTED_STATUS_VALUES
    assert health["stt_model"] == "distil-large-v3"
    assert health["stt_compute_type"] == "int8_float16"
    assert health["vad_ready"] is True
    assert health["resident_tts_engine"] == "f5"
    assert health["loading_engine"] is None
    assert isinstance(health["vram_used_mb"], int | float)
    assert isinstance(health["vram_headroom_mb"], int | float)
    assert set(statuses) == set(EXPECTED_TTS_ENGINE_IDS)
    assert _resident_engine_ids(statuses) == ["f5"]


def test_switch_tts_engine_unloads_previous_resident_before_loading_target() -> None:
    manager, _, events = _build_manager()

    _complete(manager.startup())
    _complete(manager.switch_tts_engine("xtts_v2"))
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["resident_tts_engine"] == "xtts_v2"
    assert health["loading_engine"] is None
    assert _resident_engine_ids(statuses) == ["xtts_v2"]
    assert events.index("f5:unload") < events.index("xtts_v2:load")


def test_failed_engine_self_test_degrades_only_that_engine_with_typed_reason() -> None:
    manager, _, _ = _build_manager(failing_engine="xtts_v2")

    _complete(manager.startup())
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["status"] == "degraded"
    assert health["resident_tts_engine"] == "f5"
    assert statuses["xtts_v2"]["available"] is False
    assert statuses["xtts_v2"]["unavailable_reason"]
    assert statuses["xtts_v2"].get("state") in EXPECTED_SWITCH_STATES
    assert statuses["f5"]["available"] is True
    assert statuses["qwen3_0_6b"]["available"] is True
    _assert_no_raw_exception_text(statuses["xtts_v2"]["unavailable_reason"])
    _assert_no_raw_exception_text(health)
