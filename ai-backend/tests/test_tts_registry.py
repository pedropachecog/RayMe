from __future__ import annotations

import base64
import enum
import importlib
import math
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import create_app

EXPECTED_ENGINE_LABELS = {
    "f5": "F5-TTS",
    "xtts_v2": "XTTS v2",
    "qwen3_0_6b": "Qwen3-TTS 0.6B-Base",
    "luxtts": "LuxTTS",
    "chatterbox_turbo": "Chatterbox Turbo",
    "tada_1b": "TADA 1B",
    "voxcpm2": "VoxCPM2",
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
        "requires_transcript": False,
        "supports_streaming": True,
    },
    "qwen3_0_6b": {
        "model_license": "Apache-2.0",
        "requires_transcript": False,
        "supports_streaming": False,
    },
    "voxcpm2": {
        "code_license": "Apache-2.0",
        "model_license": "Apache-2.0",
        "requires_transcript": False,
        "supports_streaming": True,
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

    assert len(entries) == len(EXPECTED_ENGINE_LABELS)
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
    assert "Reference audio is sufficient" in by_id["xtts_v2"]["quality_notes"]
    assert "Native streaming inside safe chunks" in by_id["xtts_v2"]["quality_notes"]
    assert "Opt-in" in by_id["qwen3_0_6b"]["caveat_chips"]
    assert "0.6B-Base" in by_id["qwen3_0_6b"]["quality_notes"]
    assert "latency" in by_id["qwen3_0_6b"]["quality_notes"].lower()
    assert "accent" in by_id["qwen3_0_6b"]["quality_notes"].lower()
    assert by_id["luxtts"]["runtime_evidence"]
    assert by_id["chatterbox_turbo"]["runtime_evidence"]
    assert by_id["tada_1b"]["runtime_evidence"]


def test_registry_metadata_includes_voxcpm2_candidate_contract() -> None:
    registry_module, _, entries = _registry_and_entries()
    by_id = {entry.get("id") or entry.get("engine_id"): entry for entry in entries}

    assert "voxcpm2" in getattr(registry_module, "EXPECTED_ENGINE_IDS")
    assert by_id["voxcpm2"]["label"] == "VoxCPM2"
    assert by_id["voxcpm2"]["code_license"] == "Apache-2.0"
    assert by_id["voxcpm2"]["model_license"] == "Apache-2.0"
    assert by_id["voxcpm2"]["requires_transcript"] is False
    assert by_id["voxcpm2"]["supports_streaming"] is True
    assert "RTX 3060 gate pending" in by_id["voxcpm2"]["caveat_chips"]
    assert "optional" in by_id["voxcpm2"]["runtime_evidence"].lower()
    assert "openbmb/VoxCPM2" in by_id["voxcpm2"]["runtime_evidence"]
    assert "health" in by_id["voxcpm2"]["runtime_evidence"].lower()
    assert "48 kHz" in by_id["voxcpm2"]["quality_notes"]


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


class ScriptedSynthesisAdapter:
    def __init__(
        self,
        *,
        engine_id: str = "xtts_v2",
        should_fail: bool = False,
        warning_codes: list[str] | None = None,
    ) -> None:
        self.engine_id = engine_id
        self.should_fail = should_fail
        self.warning_codes = warning_codes or []
        self.last_request: Any = None

    def synthesize(self, request: Any) -> Any:
        self.last_request = request
        if self.should_fail:
            raise RuntimeError(
                "Traceback: /home/pmpg/.cache/openbmb/VoxCPM2 C:\\models\\secret\\CUDA out of memory"
            )
        registry_module = importlib.import_module("app.models.tts_registry")
        output_type = getattr(registry_module, "TtsSynthesisOutput")
        return output_type(
            engine_id=self.engine_id,
            wav_bytes=b"RIFFtest-wave",
            sample_rate=24000,
            duration_ms=125.0,
            warning_codes=self.warning_codes,
        )


class ScriptedSwitchingManager:
    def __init__(self, adapter: ScriptedSynthesisAdapter) -> None:
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
            "voxcpm2": adapter,
        }
        self._statuses = {engine_id: "idle" for engine_id in self.tts_adapters}
        self.switch_calls: list[str] = []
        self.unavailable_calls: list[tuple[str, str]] = []

    def switch_tts_engine(self, target_engine: str) -> None:
        if target_engine not in self.tts_adapters:
            raise ValueError(f"Unknown TTS engine: {target_engine}")
        self.loading_engine = target_engine
        self.switch_calls.append(target_engine)
        self.resident_tts_engine = target_engine
        self.loading_engine = None

    def _mark_unavailable(self, engine_id: str, reason: str) -> None:
        if engine_id not in self._statuses:
            raise KeyError(engine_id)
        self._statuses[engine_id] = "unavailable"
        self.unavailable_calls.append((engine_id, reason))


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
    adapter = ScriptedSynthesisAdapter()
    manager = ScriptedSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post("/tts/synthesize", json=_synthesis_payload())

    assert response.status_code == 200
    payload = response.json()
    assert manager.switch_calls == ["xtts_v2"]
    assert payload["engine_id"] == "xtts_v2"
    assert payload["content_type"] == "audio/wav"
    assert payload["audio_base64"] == base64.b64encode(b"RIFFtest-wave").decode("ascii")
    assert adapter.last_request.text == "Hello from RayMe."
    assert adapter.last_request.reference_audio == b"reference wav"
    assert adapter.last_request.reference_transcript == "Reference transcript."


def test_tts_synthesize_accepts_web_ui_reference_audio_alias() -> None:
    adapter = ScriptedSynthesisAdapter()
    manager = ScriptedSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)
    payload = _synthesis_payload()
    payload["reference_audio_base64"] = payload.pop("reference_audio_b64")
    payload["speech_speed"] = 0.75

    response = client.post("/tts/synthesize", json=payload)

    assert response.status_code == 200
    assert adapter.last_request.reference_audio == b"reference wav"
    assert adapter.last_request.speech_speed == 0.75


def test_tts_synthesize_rejects_reference_audio_over_web_ui_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tts_module = importlib.import_module("app.api.tts")
    monkeypatch.setattr(tts_module, "MAX_REFERENCE_AUDIO_BYTES", len(b"reference wav") - 1)
    adapter = ScriptedSynthesisAdapter()
    manager = ScriptedSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post("/tts/synthesize", json=_synthesis_payload())

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "invalid_tts_request",
        "message": "reference audio is too large",
    }
    assert manager.switch_calls == []
    assert adapter.last_request is None


def test_tts_synthesize_accepts_bounded_voxcpm2_options() -> None:
    adapter = ScriptedSynthesisAdapter()
    manager = ScriptedSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post(
        "/tts/synthesize",
        json=_synthesis_payload(
            engine_id="voxcpm2",
            voxcpm2_cloning_mode="transcript_guided",
            voxcpm2_style_prompt="warm conversational phone audio",
            voxcpm2_cfg_value=2.25,
            voxcpm2_inference_timesteps=14,
            voxcpm2_normalize=True,
            voxcpm2_denoise=False,
        ),
    )

    assert response.status_code == 200
    assert manager.switch_calls == ["voxcpm2"]
    assert adapter.last_request.voxcpm2_cloning_mode == "transcript_guided"
    assert adapter.last_request.voxcpm2_style_prompt == "warm conversational phone audio"
    assert adapter.last_request.voxcpm2_cfg_value == 2.25
    assert adapter.last_request.voxcpm2_inference_timesteps == 14
    assert adapter.last_request.voxcpm2_normalize is True
    assert adapter.last_request.voxcpm2_denoise is False

    invalid_payloads = (
        {"voxcpm2_cloning_mode": "device_auto"},
        {"voxcpm2_style_prompt": "x" * 301},
        {"voxcpm2_cfg_value": 0.1},
        {"voxcpm2_inference_timesteps": 0},
    )
    for invalid in invalid_payloads:
        invalid_response = client.post(
            "/tts/synthesize",
            json=_synthesis_payload(engine_id="voxcpm2", **invalid),
        )
        assert invalid_response.status_code == 422


def test_tts_synthesize_returns_voxcpm2_warning_codes() -> None:
    adapter = ScriptedSynthesisAdapter(
        engine_id="voxcpm2",
        warning_codes=["voxcpm2_reference_only_without_transcript"],
    )
    manager = ScriptedSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post(
        "/tts/synthesize",
        json=_synthesis_payload(engine_id="voxcpm2", reference_transcript=""),
    )

    assert response.status_code == 200
    assert response.json()["warnings"] == ["voxcpm2_reference_only_without_transcript"]


def test_tts_synthesize_use_default_engine_switches_to_caller_default() -> None:
    adapter = ScriptedSynthesisAdapter()
    manager = ScriptedSwitchingManager(adapter)
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
    adapter = ScriptedSynthesisAdapter(should_fail=True)
    manager = ScriptedSwitchingManager(adapter)
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
    assert "/home/" not in rendered
    assert "openbmb/VoxCPM2" not in rendered


def test_tts_synthesize_unknown_engine_keeps_public_error_sanitized() -> None:
    adapter = ScriptedSynthesisAdapter()
    manager = ScriptedSwitchingManager(adapter)
    app = create_app()
    app.state.model_manager = manager
    client = TestClient(app)

    response = client.post("/tts/synthesize", json=_synthesis_payload(engine_id="missing_engine"))

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "tts_failed",
        "message": "Synthesis failed",
        "engine_id": "missing_engine",
    }
    assert manager.unavailable_calls == []
    rendered = response.text
    assert "KeyError" not in rendered
    assert "ValueError" not in rendered
    assert "Unknown TTS engine" not in rendered


def test_f5_adapter_uses_runtime_infer_and_returns_wav_bytes() -> None:
    f5_module = importlib.import_module("app.models.tts_f5")
    registry_module = importlib.import_module("app.models.tts_registry")
    F5TtsAdapter = getattr(f5_module, "F5TtsAdapter")
    TtsSynthesisInput = getattr(registry_module, "TtsSynthesisInput")

    class ScriptedF5Runtime:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def infer(self, ref_file: str, ref_text: str, gen_text: str, **_: Any) -> tuple[Any, int, None]:
            self.calls.append((ref_file, ref_text, gen_text, _))
            sample_rate = 24_000
            t = np.linspace(0, 0.05, int(sample_rate * 0.05), endpoint=False)
            return (0.1 * np.sin(2 * math.pi * 440 * t), sample_rate, None)

    runtime = ScriptedF5Runtime()
    adapter = F5TtsAdapter(runtime_factory=lambda: runtime)

    result = adapter.synthesize(
        TtsSynthesisInput(
            text="Generated RayMe audio.",
            reference_audio=b"scripted-reference-wav",
            reference_transcript="Reference transcript.",
            speech_speed=0.75,
        )
    )

    assert runtime.calls
    assert runtime.calls[0][1] == "Reference transcript."
    assert runtime.calls[0][2] == "Generated RayMe audio."
    assert runtime.calls[0][3]["speed"] == 0.75
    assert result.engine_id == "f5"
    assert result.sample_rate == 24_000
    assert result.duration_ms and result.duration_ms > 0
    assert result.wav_bytes.startswith(b"RIFF")


def test_f5_adapter_restores_pythonhashseed_after_infer(monkeypatch: pytest.MonkeyPatch) -> None:
    f5_module = importlib.import_module("app.models.tts_f5")
    registry_module = importlib.import_module("app.models.tts_registry")
    F5TtsAdapter = getattr(f5_module, "F5TtsAdapter")
    TtsSynthesisInput = getattr(registry_module, "TtsSynthesisInput")

    class HashSeedMutatingRuntime:
        def infer(self, *_args: Any, **_kwargs: Any) -> tuple[Any, int, None]:
            os.environ["PYTHONHASHSEED"] = str(2**63 - 1)
            sample_rate = 24_000
            t = np.linspace(0, 0.02, int(sample_rate * 0.02), endpoint=False)
            return (0.1 * np.sin(2 * math.pi * 440 * t), sample_rate, None)

    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    adapter = F5TtsAdapter(runtime_factory=HashSeedMutatingRuntime)

    adapter.synthesize(
        TtsSynthesisInput(
            text="Generated RayMe audio.",
            reference_audio=b"scripted-reference-wav",
            reference_transcript="Reference transcript.",
        )
    )

    assert "PYTHONHASHSEED" not in os.environ


def test_f5_adapter_load_builds_runtime_before_first_synthesis() -> None:
    f5_module = importlib.import_module("app.models.tts_f5")
    F5TtsAdapter = getattr(f5_module, "F5TtsAdapter")

    runtime = object()
    builds = 0

    def runtime_factory() -> object:
        nonlocal builds
        builds += 1
        return runtime

    adapter = F5TtsAdapter(runtime_factory=runtime_factory)

    adapter.load()

    assert adapter.loaded is True
    assert adapter._runtime is runtime
    assert builds == 1


def test_f5_runtime_audio_loader_avoids_torchcodec_dependency(tmp_path: Path) -> None:
    f5_module = importlib.import_module("app.models.tts_f5")
    load_audio = getattr(f5_module, "_load_audio_with_soundfile")
    sample_path = tmp_path / "reference.wav"
    sample_rate = 16_000
    tone = np.zeros((sample_rate // 10, 1), dtype=np.float32)
    sf.write(sample_path, tone, sample_rate, format="WAV")

    audio, actual_sample_rate = load_audio(sample_path)

    assert actual_sample_rate == sample_rate
    assert tuple(audio.shape) == (1, sample_rate // 10)
    assert str(audio.device) == "cpu"


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
