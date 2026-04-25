from __future__ import annotations

import enum
import importlib
from dataclasses import asdict, is_dataclass
from typing import Any

import pytest

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
