from __future__ import annotations

import base64
import enum
import importlib
from dataclasses import asdict, is_dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

EXPECTED_ENGINE_LABELS = {
    "f5": "F5-TTS",
    "xtts_v2": "XTTS v2",
    "qwen3_0_6b": "Qwen3-TTS 0.6B-Base",
    "luxtts": "LuxTTS",
    "chatterbox_turbo": "Chatterbox Turbo",
    "tada_1b": "TADA 1B",
}
REQUIRED_METADATA_FIELDS = {
    "id",
    "label",
    "code_license",
    "model_license",
    "caveat_chips",
    "runtime_evidence",
    "requires_transcript",
    "supports_streaming",
    "quality_notes",
    "is_default",
    "availability",
}
ENGINE_REQUIREMENTS = {
    "f5": {
        "model_license": "CC-BY-NC",
        "requires_transcript": True,
        "supports_streaming": False,
    },
    "xtts_v2": {
        "model_license": "CPML",
        "requires_transcript": True,
        "supports_streaming": True,
    },
    "qwen3_0_6b": {
        "model_license": "Apache-2.0",
        "requires_transcript": False,
        "supports_streaming": False,
    },
}
SWITCH_STATES = {"idle", "loading", "resident", "unavailable"}


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    pytest.fail(f"Expected dict-like registry metadata, got {type(value)!r}")


def _registry_and_entries() -> tuple[Any, Any, list[dict[str, Any]]]:
    registry_module = importlib.import_module("app.models.tts_registry")
    TtsEngineRegistry = getattr(registry_module, "TtsEngineRegistry")

    registry_attempts = (
        lambda: TtsEngineRegistry.default(),
        lambda: TtsEngineRegistry.from_defaults(),
        lambda: TtsEngineRegistry(),
    )
    registry = None
    errors: list[str] = []
    for attempt in registry_attempts:
        try:
            registry = attempt()
            break
        except (AttributeError, TypeError) as exc:
            errors.append(str(exc))
    if registry is None:
        pytest.fail(f"TtsEngineRegistry must expose default metadata: {errors}")

    raw_entries: Any
    if hasattr(registry, "list_engines"):
        raw_entries = registry.list_engines()
    elif hasattr(registry, "engines"):
        engines = registry.engines
        raw_entries = engines.values() if isinstance(engines, dict) else engines
    elif hasattr(registry_module, "TTS_ENGINE_METADATA"):
        metadata = registry_module.TTS_ENGINE_METADATA
        raw_entries = metadata.values() if isinstance(metadata, dict) else metadata
    else:
        pytest.fail("TTS registry must expose list_engines(), engines, or TTS_ENGINE_METADATA")

    entries = [_to_mapping(entry) for entry in raw_entries]
    return registry_module, registry, entries


def _availability_state(entry: dict[str, Any]) -> str:
    availability = entry["availability"]
    if isinstance(availability, str):
        return availability
    mapping = _to_mapping(availability)
    state = mapping.get("state") or mapping.get("status") or mapping.get("availability")
    assert isinstance(state, str)
    return state


def _module_switch_states(registry_module: Any) -> set[str]:
    for attr_name in ("SWITCH_STATES", "ENGINE_SWITCH_STATES", "EngineSwitchState"):
        value = getattr(registry_module, attr_name, None)
        if value is None:
            continue
        if isinstance(value, set | list | tuple):
            return {str(item) for item in value}
        if isinstance(value, type) and issubclass(value, enum.Enum):
            return {str(member.value) for member in value}
    pytest.fail("tts_registry must expose switch states idle|loading|resident|unavailable")


def test_registry_metadata_contains_full_six_engine_roster_registry_metadata() -> None:
    _, _, entries = _registry_and_entries()

    labels_by_id = {
        entry.get("id") or entry.get("engine_id"): entry["label"]
        for entry in entries
    }

    assert labels_by_id == EXPECTED_ENGINE_LABELS


def test_registry_metadata_rejects_three_engine_only_roster_registry_metadata() -> None:
    _, _, entries = _registry_and_entries()

    engine_ids = {entry.get("id") or entry.get("engine_id") for entry in entries}

    assert len(entries) == 6
    assert set(EXPECTED_ENGINE_LABELS) - engine_ids == set()


def test_registry_metadata_includes_license_runtime_and_availability_fields_registry_metadata() -> None:
    _, _, entries = _registry_and_entries()

    defaults = []
    for entry in entries:
        fields = set(entry)
        assert REQUIRED_METADATA_FIELDS <= fields
        engine_id = entry.get("id") or entry.get("engine_id")
        if entry["is_default"]:
            defaults.append(engine_id)
        assert entry["code_license"]
        assert entry["model_license"]
        assert isinstance(entry["caveat_chips"], list)
        assert entry["runtime_evidence"]
        assert _availability_state(entry) in SWITCH_STATES

    assert defaults == ["f5"]


def test_registry_metadata_captures_engine_specific_contracts_registry_metadata() -> None:
    _, _, entries = _registry_and_entries()
    by_id = {entry.get("id") or entry.get("engine_id"): entry for entry in entries}

    for engine_id, required in ENGINE_REQUIREMENTS.items():
        entry = by_id[engine_id]
        for field, expected in required.items():
            assert entry[field] == expected

    assert "Default" in by_id["f5"]["caveat_chips"]
    assert "Requires transcript" in by_id["f5"]["caveat_chips"]
    assert "Transcript stored for portability" in by_id["xtts_v2"]["quality_notes"]
    assert "Native streaming inside safe chunks" in by_id["xtts_v2"]["quality_notes"]
    assert "Opt-in" in by_id["qwen3_0_6b"]["caveat_chips"]
    assert "0.6B-Base" in by_id["qwen3_0_6b"]["quality_notes"]
    assert "latency" in by_id["qwen3_0_6b"]["quality_notes"].lower()
    assert "accent" in by_id["qwen3_0_6b"]["quality_notes"].lower()
    assert by_id["luxtts"]["runtime_evidence"]
    assert by_id["chatterbox_turbo"]["runtime_evidence"]
    assert by_id["tada_1b"]["runtime_evidence"]


def test_registry_metadata_rejects_missing_engine_registry_metadata() -> None:
    registry_module, _, entries = _registry_and_entries()
    TtsEngineRegistry = getattr(registry_module, "TtsEngineRegistry")

    incomplete_entries = [
        entry for entry in entries if (entry.get("id") or entry.get("engine_id")) != "tada_1b"
    ]

    with pytest.raises(ValueError, match="missing.*tada_1b"):
        TtsEngineRegistry(engines=incomplete_entries)


def test_registry_switch_state_contract_is_idle_loading_resident_unavailable_registry_metadata() -> None:
    registry_module, _, _ = _registry_and_entries()

    assert _module_switch_states(registry_module) == SWITCH_STATES


class FakeSynthesisAdapter:
    engine_id = "xtts_v2"

    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.last_request: Any = None

    def synthesize(self, request: Any) -> Any:
        self.last_request = request
        if self.should_fail:
            raise RuntimeError("C:\\models\\secret\\traceback CUDA out of memory")
        registry_module = importlib.import_module("app.models.tts_registry")
        output_type = getattr(registry_module, "TtsSynthesisOutput")
        return output_type(
            engine_id=self.engine_id,
            wav_bytes=b"RIFFfake-wave",
            sample_rate=24000,
            duration_ms=125.0,
        )


class FakeSwitchingManager:
    def __init__(self, adapter: FakeSynthesisAdapter) -> None:
        self.settings = type("Settings", (), {"default_tts_engine": "f5"})()
        self.loading_engine = None
        self.resident_tts_engine = "f5"
        self.tts_adapters = {
            "f5": adapter,
            "xtts_v2": adapter,
            "qwen3_0_6b": adapter,
            "luxtts": adapter,
            "chatterbox_turbo": adapter,
            "tada_1b": adapter,
        }
        self.switch_calls: list[str] = []

    def switch_tts_engine(self, target_engine: str) -> None:
        self.loading_engine = target_engine
        self.switch_calls.append(target_engine)
        self.resident_tts_engine = target_engine
        self.loading_engine = None


def _synthesis_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "voice_id": "voice_test",
        "engine_id": "xtts_v2",
        "text": "Hello from RayMe.",
        "reference_audio_b64": base64.b64encode(b"reference wav").decode("ascii"),
        "reference_transcript": "Reference transcript.",
        "use_default_engine": False,
    }
    payload.update(overrides)
    return payload


def test_tts_synthesize_switches_engine_and_returns_transient_json() -> None:
    adapter = FakeSynthesisAdapter()
    manager = FakeSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post("/tts/synthesize", json=_synthesis_payload())

    assert response.status_code == 200
    payload = response.json()
    assert manager.switch_calls == ["xtts_v2"]
    assert payload["engine_id"] == "xtts_v2"
    assert payload["content_type"] == "audio/wav"
    assert payload["audio_base64"] == base64.b64encode(b"RIFFfake-wave").decode("ascii")
    assert adapter.last_request.text == "Hello from RayMe."
    assert adapter.last_request.reference_audio == b"reference wav"
    assert adapter.last_request.reference_transcript == "Reference transcript."


def test_tts_synthesize_use_default_engine_switches_to_caller_default() -> None:
    adapter = FakeSynthesisAdapter()
    manager = FakeSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post(
        "/tts/synthesize",
        json=_synthesis_payload(engine_id="f5", use_default_engine=True),
    )

    assert response.status_code == 200
    assert manager.switch_calls == ["f5"]
    assert response.json()["engine_id"] == "f5"


def test_tts_synthesize_failure_returns_fixed_public_error() -> None:
    adapter = FakeSynthesisAdapter(should_fail=True)
    manager = FakeSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post("/tts/synthesize", json=_synthesis_payload())

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "tts_failed",
        "message": "Synthesis failed",
        "engine_id": "xtts_v2",
    }
    rendered = response.text
    assert "Traceback" not in rendered
    assert "RuntimeError" not in rendered
    assert "CUDA out of memory" not in rendered
    assert "C:\\" not in rendered


def test_create_app_includes_tts_router_without_voice_library_persistence_routes() -> None:
    app = create_app()
    routes = {
        f"{','.join(sorted(route.methods or []))} {route.path}"
        for route in app.routes
        if hasattr(route, "methods")
    }

    assert "POST /tts/synthesize" in routes
    assert not any("/tts/voices" in route for route in routes)
    assert not any("/tts/library" in route for route in routes)
    assert not any(route.endswith(" /voices") for route in routes)
