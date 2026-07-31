from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import threading
from dataclasses import asdict, is_dataclass
from typing import Any

import pytest

EXPECTED_TTS_ENGINE_IDS = (
    "f5",
    "xtts_v2",
    "qwen3_1_7b",
    "luxtts",
    "chatterbox_turbo",
    "tada_1b",
    "voxcpm2",
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


class ScriptedTtsAdapter:
    def __init__(
        self,
        engine_id: str,
        events: list[str],
        *,
        fail_self_test: bool = False,
        fail_load: bool = False,
    ) -> None:
        self.engine_id = engine_id
        self.events = events
        self.fail_self_test = fail_self_test
        self.fail_load = fail_load
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
        if self.fail_load:
            raise RuntimeError(
                "Traceback: CUDA out of memory while loading C:\\secret\\model.bin"
            )
        self.loaded = True

    def unload(self) -> None:
        self.events.append(f"{self.engine_id}:unload")
        self.loaded = False


class FlakyLoadTtsAdapter(ScriptedTtsAdapter):
    def __init__(
        self,
        engine_id: str,
        events: list[str],
        *,
        failures_before_success: int,
    ) -> None:
        super().__init__(engine_id, events)
        self.failures_before_success = failures_before_success

    def load(self) -> None:
        self.events.append(f"{self.engine_id}:load")
        if self.failures_before_success > 0:
            self.failures_before_success -= 1
            raise RuntimeError(
                "Traceback: CUDA out of memory while loading C:\\secret\\model.bin"
            )
        self.loaded = True


class SlowPreparingQwenAdapter(ScriptedTtsAdapter):
    def __init__(self, events: list[str]) -> None:
        super().__init__("qwen3_1_7b", events)
        self.load_started = threading.Event()
        self.release_load = threading.Event()
        self.prewarm_started = threading.Event()
        self.release_prewarm = threading.Event()
        self.prewarm_calls: list[dict[str, Any]] = []

    def load(self) -> None:
        self.events.append("qwen3_1_7b:load")
        self.load_started.set()
        assert self.release_load.wait(1.0)
        self.loaded = True

    def prewarm(
        self,
        *,
        voice_key: str,
        reference_audio: bytes,
        reference_transcript: str,
    ) -> object:
        self.prewarm_calls.append(
            {
                "voice_key": voice_key,
                "reference_audio": reference_audio,
                "reference_transcript": reference_transcript,
            }
        )
        self.prewarm_started.set()
        assert self.release_prewarm.wait(1.0)
        return object()


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


def _build_manager(
    *,
    failing_engine: str | None = None,
    load_failing_engine: str | None = None,
) -> tuple[Any, dict[str, ScriptedTtsAdapter], list[str]]:
    config_module = importlib.import_module("app.config")
    manager_module = importlib.import_module("app.models.model_manager")

    AiBackendSettings = _require_attr(config_module, "AiBackendSettings")
    ModelManager = _require_attr(manager_module, "ModelManager")

    settings = AiBackendSettings(load_models_on_startup=False)
    events: list[str] = []
    adapters = {
        engine_id: ScriptedTtsAdapter(
            engine_id,
            events,
            fail_self_test=engine_id == failing_engine,
            fail_load=engine_id == load_failing_engine,
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


def test_prepare_qwen_keeps_status_responsive_and_separates_model_from_prompt() -> None:
    async def scenario() -> None:
        manager, adapters, events = _build_manager()
        manager.startup()
        qwen = SlowPreparingQwenAdapter(events)
        adapters["qwen3_1_7b"] = qwen
        manager.tts_adapters["qwen3_1_7b"] = qwen

        prepare = asyncio.create_task(
            manager.prepare_tts_engine(
                "qwen3_1_7b",
                voice_key="voice-key-1",
                reference_audio=b"contained-reference",
                reference_transcript="The exact reference transcript.",
            )
        )
        assert await asyncio.to_thread(qwen.load_started.wait, 1.0)

        loading = manager.health()
        loading_statuses = _engine_statuses(loading)
        assert loading["loading_engine"] == "qwen3_1_7b"
        assert loading_statuses["qwen3_1_7b"]["state"] == "loading"
        assert loading["resident_tts_engine"] is None
        assert _resident_engine_ids(loading_statuses) == []
        assert loading["selected_voice_prompt"] == {
            "engine_id": "qwen3_1_7b",
            "voice_key": "voice-key-1",
            "state": "none",
            "error_code": None,
        }

        qwen.release_load.set()
        assert await asyncio.to_thread(qwen.prewarm_started.wait, 1.0)
        prewarming = manager.health()
        prewarming_statuses = _engine_statuses(prewarming)
        assert prewarming["resident_tts_engine"] == "qwen3_1_7b"
        assert _resident_engine_ids(prewarming_statuses) == ["qwen3_1_7b"]
        assert prewarming["selected_voice_prompt"]["state"] == "prewarming"

        qwen.release_prewarm.set()
        prepared = await prepare
        assert prepared["model_state"] == "resident"
        assert prepared["prompt_state"] == "ready"
        assert manager.health()["selected_voice_prompt"]["state"] == "ready"

        repeated = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key="voice-key-1",
            reference_audio=b"contained-reference",
            reference_transcript="The exact reference transcript.",
        )
        assert repeated["prompt_state"] == "ready"
        assert len(qwen.prewarm_calls) == 1
        assert events.index("f5:unload") < events.index("qwen3_1_7b:load")

    asyncio.run(scenario())


def test_qwen_prompt_failure_is_voice_scoped_and_sanitized() -> None:
    class FailingPromptAdapter(ScriptedTtsAdapter):
        def prewarm(self, **_kwargs: Any) -> None:
            raise RuntimeError(
                "Traceback CUDA out of memory C:\\secret\\model.bin /models/private"
            )

    async def scenario() -> None:
        manager, _, events = _build_manager()
        manager.startup()
        adapter = FailingPromptAdapter("qwen3_1_7b", events)
        manager.tts_adapters["qwen3_1_7b"] = adapter

        with pytest.raises(RuntimeError):
            await manager.prepare_tts_engine(
                "qwen3_1_7b",
                voice_key="voice-key-failed",
                reference_audio=b"contained-reference",
                reference_transcript="The exact reference transcript.",
            )

        health = manager.health()
        statuses = _engine_statuses(health)
        assert health["resident_tts_engine"] == "qwen3_1_7b"
        assert statuses["qwen3_1_7b"]["available"] is True
        assert health["selected_voice_prompt"] == {
            "engine_id": "qwen3_1_7b",
            "voice_key": "voice-key-failed",
            "state": "failed",
            "error_code": "voice_prompt_preparation_failed",
        }
        _assert_no_raw_exception_text(health)

    asyncio.run(scenario())


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
    assert statuses["qwen3_1_7b"]["available"] is True
    _assert_no_raw_exception_text(statuses["xtts_v2"]["unavailable_reason"])
    _assert_no_raw_exception_text(health)


def test_startup_self_test_failure_remains_unavailable_without_retry() -> None:
    manager, _, events = _build_manager(failing_engine="xtts_v2")

    _complete(manager.startup())
    with pytest.raises(ValueError, match="TTS engine unavailable"):
        _complete(manager.switch_tts_engine("xtts_v2"))
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert statuses["xtts_v2"]["available"] is False
    assert statuses["xtts_v2"]["state"] == "unavailable"
    assert statuses["xtts_v2"]["unavailable_reason"] == "engine startup self-test failed"
    assert "xtts_v2:load" not in events


def test_voxcpm2_load_failure_degrades_only_voxcpm2() -> None:
    manager, _, events = _build_manager(load_failing_engine="voxcpm2")

    _complete(manager.startup())
    with pytest.raises(RuntimeError):
        _complete(manager.switch_tts_engine("voxcpm2"))
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["status"] == "degraded"
    assert health["resident_tts_engine"] is None
    assert health["loading_engine"] is None
    assert statuses["voxcpm2"]["available"] is False
    assert statuses["voxcpm2"]["resident"] is False
    assert statuses["voxcpm2"]["state"] == "unavailable"
    assert statuses["voxcpm2"]["unavailable_reason"] == "engine load failed"
    assert "voxcpm2:load" in events
    for engine_id in (
        "f5",
        "xtts_v2",
        "qwen3_1_7b",
        "luxtts",
        "chatterbox_turbo",
        "tada_1b",
    ):
        assert engine_id in statuses
        assert statuses[engine_id]["available"] is True
    _assert_no_raw_exception_text(statuses["voxcpm2"]["unavailable_reason"])
    _assert_no_raw_exception_text(health)


def test_transient_voxcpm2_load_failure_can_retry_on_later_switch() -> None:
    manager, adapters, events = _build_manager()
    adapters["voxcpm2"] = FlakyLoadTtsAdapter(
        "voxcpm2",
        events,
        failures_before_success=1,
    )
    manager.tts_adapters["voxcpm2"] = adapters["voxcpm2"]

    _complete(manager.startup())
    with pytest.raises(RuntimeError):
        _complete(manager.switch_tts_engine("voxcpm2"))

    failed_health = _health_mapping(manager)
    failed_statuses = _engine_statuses(failed_health)
    assert failed_statuses["voxcpm2"]["state"] == "unavailable"
    assert failed_statuses["voxcpm2"]["unavailable_reason"] == "engine load failed"

    _complete(manager.switch_tts_engine("voxcpm2"))
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["resident_tts_engine"] == "voxcpm2"
    assert statuses["voxcpm2"]["available"] is True
    assert statuses["voxcpm2"]["resident"] is True
    assert statuses["voxcpm2"]["state"] == "resident"
    assert statuses["voxcpm2"]["unavailable_reason"] is None
    assert events.count("voxcpm2:load") == 2


def test_default_engine_load_failure_degrades_health_without_blocking_startup() -> None:
    manager, _, events = _build_manager(load_failing_engine="f5")

    _complete(manager.startup())
    health = _health_mapping(manager)
    statuses = _engine_statuses(health)

    assert health["status"] == "degraded"
    assert health["resident_tts_engine"] is None
    assert health["loading_engine"] is None
    assert statuses["f5"]["available"] is False
    assert statuses["f5"]["resident"] is False
    assert statuses["f5"]["state"] == "unavailable"
    assert statuses["f5"]["unavailable_reason"] == "default engine load failed"
    assert "f5:load" in events
    _assert_no_raw_exception_text(health)
