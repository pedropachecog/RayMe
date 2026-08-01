from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import threading
import wave
from dataclasses import asdict, is_dataclass
from io import BytesIO
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


class RecordingQwenAdapter(ScriptedTtsAdapter):
    def __init__(self, events: list[str], *, prewarm_error: Exception | None = None) -> None:
        super().__init__("qwen3_1_7b", events)
        self.torch_reserved_mib = 5604.0
        self.prewarm_error = prewarm_error
        self.prewarm_calls: list[dict[str, Any]] = []

    def prewarm(self, **kwargs: Any) -> object:
        self.prewarm_calls.append(dict(kwargs))
        if self.prewarm_error is not None:
            raise self.prewarm_error
        return object()


class ScriptedAlignmentSttAdapter:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return {
            "status": "accepted",
            "transcript": self.transcript,
            "speech_detected": True,
        }


class SampleRateSensitiveAlignmentSttAdapter(ScriptedAlignmentSttAdapter):
    def __init__(self, transcript: str, *, expected_sample_count: int) -> None:
        super().__init__(transcript)
        self.expected_sample_count = expected_sample_count

    def transcribe(self, **kwargs: Any) -> dict[str, Any]:
        audio = kwargs["audio"]
        self.transcript = (
            "The Voice Lab transcript matches this uploaded sample."
            if len(audio) == self.expected_sample_count
            else "Completely unrelated words caused by wrong-speed audio."
        )
        return super().transcribe(**kwargs)


def _reference_wav_bytes(*, amplitude: int = 2048, sample_rate: int = 24000) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(
            amplitude.to_bytes(2, "little", signed=True) * (sample_rate // 5)
        )
    return buffer.getvalue()


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
    manager.stt_adapter = ScriptedAlignmentSttAdapter(
        "The exact reference transcript."
    )

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


def test_model_manager_health_exposes_only_resident_qwen_allocator_memory() -> None:
    manager, _, events = _build_manager()
    manager.startup()
    qwen = RecordingQwenAdapter(events)
    manager.tts_adapters["qwen3_1_7b"] = qwen

    assert manager.health()["tts_torch_reserved_mib"] is None

    manager.switch_tts_engine("qwen3_1_7b")

    assert manager.health()["tts_torch_reserved_mib"] == 5604.0


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
                reference_audio=_reference_wav_bytes(),
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
            reference_audio=_reference_wav_bytes(),
            reference_transcript="The exact reference transcript.",
        )
        assert repeated["prompt_state"] == "ready"
        assert len(qwen.prewarm_calls) == 1
        assert events.index("f5:unload") < events.index("qwen3_1_7b:load")

    asyncio.run(scenario())


def test_live_call_prompt_lease_rejects_competing_preview_and_preserves_stream() -> None:
    async def scenario() -> None:
        qwen_module = importlib.import_module("app.models.tts_qwen3")
        lease_error = _require_attr(qwen_module, "Qwen3PromptLeaseError")

        class CapacityOneQwenAdapter(RecordingQwenAdapter):
            def __init__(self, events: list[str]) -> None:
                super().__init__(events)
                self.selected_voice_key: str | None = None

            def prewarm(self, **kwargs: Any) -> object:
                self.selected_voice_key = str(kwargs["voice_key"])
                return super().prewarm(**kwargs)

            def stream(
                self,
                _request: object,
                *,
                request_id: str,
                voice_key: str,
            ) -> Any:
                assert request_id == "call-a-next-segment"
                assert voice_key == self.selected_voice_key
                yield voice_key

        manager, adapters, events = _build_manager()
        manager.startup()
        qwen = CapacityOneQwenAdapter(events)
        adapters["qwen3_1_7b"] = qwen
        manager.tts_adapters["qwen3_1_7b"] = qwen
        voice_a_audio = _reference_wav_bytes(amplitude=2048)
        voice_b_audio = _reference_wav_bytes(amplitude=1024)

        await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key="voice-a",
            reference_audio=voice_a_audio,
            reference_transcript="The exact reference transcript.",
            prompt_lease_owner="live-call-a",
        )

        with pytest.raises(lease_error) as rejected:
            await manager.prepare_tts_engine(
                "qwen3_1_7b",
                voice_key="voice-b",
                reference_audio=voice_b_audio,
                reference_transcript="A different approved transcript.",
            )
        assert rejected.value.code == "qwen3_prompt_leased"
        assert manager.is_tts_prompt_ready(
            "qwen3_1_7b",
            "voice-a",
            reference_audio=voice_a_audio,
            reference_transcript="The exact reference transcript.",
        )
        assert list(
            qwen.stream(
                object(),
                request_id="call-a-next-segment",
                voice_key="voice-a",
            )
        ) == ["voice-a"]
        assert [call["voice_key"] for call in qwen.prewarm_calls] == ["voice-a"]

        assert await manager.release_tts_prompt_lease("live-call-a") is True
        prepared_b = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key="voice-b",
            reference_audio=voice_b_audio,
            reference_transcript="A different approved transcript.",
        )
        assert prepared_b["voice_key"] == "voice-b"

    asyncio.run(scenario())


@pytest.mark.parametrize("first_owner_released", ("call-a", "call-b"))
def test_same_prompt_calls_hold_lease_until_last_session_releases(
    first_owner_released: str,
) -> None:
    async def scenario() -> None:
        qwen_module = importlib.import_module("app.models.tts_qwen3")
        lease_error = _require_attr(qwen_module, "Qwen3PromptLeaseError")

        class SharedPromptQwenAdapter(RecordingQwenAdapter):
            def __init__(self, events: list[str]) -> None:
                super().__init__(events)
                self.selected_voice_key: str | None = None

            def prewarm(self, **kwargs: Any) -> object:
                self.selected_voice_key = str(kwargs["voice_key"])
                return super().prewarm(**kwargs)

            def stream(self, _request: object, **kwargs: Any) -> Any:
                assert kwargs["voice_key"] == self.selected_voice_key
                yield kwargs["voice_key"]

        manager, adapters, events = _build_manager()
        manager.startup()
        qwen = SharedPromptQwenAdapter(events)
        adapters["qwen3_1_7b"] = qwen
        manager.tts_adapters["qwen3_1_7b"] = qwen
        shared_audio = _reference_wav_bytes(amplitude=2048)
        replacement_audio = _reference_wav_bytes(amplitude=1024)
        shared_transcript = "The exact reference transcript."

        for owner in ("call-a", "call-b"):
            await manager.prepare_tts_engine(
                "qwen3_1_7b",
                voice_key="voice-shared",
                reference_audio=shared_audio,
                reference_transcript=shared_transcript,
                prompt_lease_owner=owner,
            )
        assert manager._qwen_prompt_lease_owners == {"call-a", "call-b"}
        assert len(qwen.prewarm_calls) == 1

        remaining_owner = ({"call-a", "call-b"} - {first_owner_released}).pop()
        assert await manager.release_tts_prompt_lease(first_owner_released) is True
        assert manager._qwen_prompt_lease_owners == {remaining_owner}
        with pytest.raises(lease_error):
            await manager.prepare_tts_engine(
                "qwen3_1_7b",
                voice_key="voice-replacement",
                reference_audio=replacement_audio,
                reference_transcript="A different approved transcript.",
            )
        with pytest.raises(lease_error):
            manager.switch_tts_engine("f5")
        assert list(
            qwen.stream(
                object(),
                request_id="remaining-call-segment",
                voice_key="voice-shared",
            )
        ) == ["voice-shared"]

        assert await manager.release_tts_prompt_lease(remaining_owner) is True
        assert not manager._qwen_prompt_lease_owners
        replacement = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key="voice-replacement",
            reference_audio=replacement_audio,
            reference_transcript="A different approved transcript.",
        )
        assert replacement["voice_key"] == "voice-replacement"

    asyncio.run(scenario())


def test_qwen_prompt_invalidation_resets_matching_cache_and_preserves_unrelated_voice() -> None:
    async def scenario() -> None:
        qwen_module = importlib.import_module("app.models.tts_qwen3")

        class LifecycleQwenAdapter(RecordingQwenAdapter):
            def __init__(self, events: list[str]) -> None:
                super().__init__(events)
                self.selected_voice_key: str | None = None
                self.invalidate_calls: list[str] = []

            def prewarm(self, **kwargs: Any) -> object:
                self.selected_voice_key = str(kwargs["voice_key"])
                return super().prewarm(**kwargs)

            def invalidate(self, voice_key: str) -> Any:
                self.invalidate_calls.append(voice_key)
                matched = self.selected_voice_key == voice_key
                if matched:
                    self.selected_voice_key = None
                return qwen_module.QwenPromptInvalidationResult(
                    voice_key=voice_key,
                    matched=matched,
                    active_cancelled=False,
                )

        manager, _, events = _build_manager()
        manager.startup()
        adapter = LifecycleQwenAdapter(events)
        manager.tts_adapters["qwen3_1_7b"] = adapter
        manager.stt_adapter = ScriptedAlignmentSttAdapter("the exact reference transcript")
        first_owner = "a" * 64
        second_owner = "b" * 64

        prepared = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key=first_owner,
            reference_audio=_reference_wav_bytes(),
            reference_transcript="The exact reference transcript.",
        )
        assert prepared["prompt_state"] == "ready"
        assert manager._selected_prompt_cache_key is not None
        assert manager._qwen_alignment_cache is not None

        unrelated = await manager.invalidate_tts_prompt("qwen3_1_7b", second_owner)
        assert unrelated["status"] == "not_present"
        assert manager.is_tts_prompt_ready("qwen3_1_7b", first_owner) is True
        assert manager._selected_prompt_cache_key is not None
        assert manager._qwen_alignment_cache is not None

        matching = await manager.invalidate_tts_prompt("qwen3_1_7b", first_owner)
        assert matching["status"] == "invalidated"
        assert matching["matched"] is True
        assert manager.health()["selected_voice_prompt"] == {
            "engine_id": None,
            "voice_key": None,
            "state": "none",
            "error_code": None,
        }
        assert manager._selected_prompt_cache_key is None
        assert manager._qwen_alignment_cache is None

        repeated = await manager.invalidate_tts_prompt("qwen3_1_7b", first_owner)
        assert repeated["status"] == "not_present"

        manager.stt_adapter.transcript = "a second exact reference transcript"
        later = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key=second_owner,
            reference_audio=_reference_wav_bytes(amplitude=1024),
            reference_transcript="A second exact reference transcript.",
        )
        assert later["prompt_state"] == "ready"
        assert manager.is_tts_prompt_ready("qwen3_1_7b", second_owner) is True

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
                reference_audio=_reference_wav_bytes(),
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


@pytest.mark.parametrize(
    ("approved", "observed"),
    [
        ("Okay. Yeah, I RESENT you!", "okay yeah i resent you"),
        ("José says café timing is ready.", "jose says cafe timing is ready"),
    ],
)
def test_qwen_alignment_tolerates_punctuation_case_and_accent_variants(
    approved: str,
    observed: str,
) -> None:
    manager_module = importlib.import_module("app.models.model_manager")

    result = manager_module.evaluate_qwen_transcript_alignment(approved, observed)

    assert result.accepted is True
    assert result.token_coverage >= 0.45 or result.edit_similarity >= 0.50


def test_qwen_alignment_rejects_known_gross_mismatch() -> None:
    manager_module = importlib.import_module("app.models.model_manager")

    result = manager_module.evaluate_qwen_transcript_alignment(
        "Vulcan Science Academy validates a completely unrelated sentence.",
        "Okay yeah I resent you I love you but you blew it",
    )

    assert result.accepted is False
    assert result.token_coverage < 0.45
    assert result.edit_similarity < 0.50


@pytest.mark.parametrize(
    ("approved", "observed"),
    [
        (
            "Okay.",
            "Okay, the rest of this recording says entirely different words for several minutes.",
        ),
        (
            "The approved sentence contains enough meaningful reference words.",
            "The approved sentence contains enough meaningful reference words followed by "
            "totally unrelated speech that keeps going for a long time.",
        ),
        (
            "The approved sentence contains enough meaningful reference words for alignment.",
            "The approved sentence contains enough meaningful reference words",
        ),
        (
            "alpha beta gamma delta epsilon zeta",
            "zeta epsilon delta gamma beta alpha",
        ),
    ],
)
def test_qwen_alignment_rejects_short_prefix_tail_and_reordered_transcripts(
    approved: str,
    observed: str,
) -> None:
    manager_module = importlib.import_module("app.models.model_manager")

    result = manager_module.evaluate_qwen_transcript_alignment(approved, observed)

    assert result.accepted is False


def test_qwen_alignment_token_coverage_penalizes_observed_extra_speech() -> None:
    manager_module = importlib.import_module("app.models.model_manager")

    result = manager_module.evaluate_qwen_transcript_alignment(
        "one two three four five six",
        "one two three four five six unrelated extra speech continues",
    )

    assert result.token_coverage == 0.6


def test_qwen_alignment_resamples_uploaded_reference_like_voice_lab_transcription() -> None:
    async def scenario() -> None:
        manager, _, events = _build_manager()
        manager.startup()
        adapter = RecordingQwenAdapter(events)
        manager.tts_adapters["qwen3_1_7b"] = adapter
        alignment_stt = SampleRateSensitiveAlignmentSttAdapter(
            "",
            expected_sample_count=3200,
        )
        manager.stt_adapter = alignment_stt

        result = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key="voice-lab-48khz",
            reference_audio=_reference_wav_bytes(sample_rate=48000),
            reference_transcript=(
                "The Voice Lab transcript matches this uploaded sample."
            ),
        )

        assert result["prompt_state"] == "ready"
        assert len(alignment_stt.calls[0]["audio"]) == 3200
        assert len(adapter.prewarm_calls) == 1

    asyncio.run(scenario())


def test_qwen_alignment_is_cached_by_content_and_blocks_before_load_or_prompt() -> None:
    async def scenario() -> None:
        qwen = importlib.import_module("app.models.tts_qwen3")
        manager, _, events = _build_manager()
        manager.startup()
        adapter = RecordingQwenAdapter(events)
        manager.tts_adapters["qwen3_1_7b"] = adapter
        stt = ScriptedAlignmentSttAdapter(
            "Okay yeah I resent you I love you but you blew it"
        )
        manager.stt_adapter = stt
        reference = _reference_wav_bytes()
        approved = "Vulcan Science Academy validates a completely unrelated sentence."

        for _ in range(2):
            with pytest.raises(qwen.Qwen3ValidationError) as raised:
                await manager.prepare_tts_engine(
                    "qwen3_1_7b",
                    voice_key="voice-mismatch",
                    reference_audio=reference,
                    reference_transcript=approved,
                )
            assert raised.value.code == "qwen3_transcript_mismatch"

        health = manager.health()
        assert len(stt.calls) == 1
        assert adapter.prewarm_calls == []
        assert "qwen3_1_7b:load" not in events
        assert health["resident_tts_engine"] == "f5"
        assert health["selected_voice_prompt"]["state"] == "failed"
        assert health["selected_voice_prompt"]["error_code"] == (
            "qwen3_transcript_mismatch"
        )
        _assert_no_raw_exception_text(health)

        # A rejected voice is scoped to that immutable prompt identity. A later
        # aligned voice must still be able to load Qwen and become ready.
        stt.transcript = approved
        valid_result = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key="voice-aligned-after-mismatch",
            reference_audio=_reference_wav_bytes(amplitude=1024),
            reference_transcript=approved,
        )

        assert valid_result["prompt_state"] == "ready"
        assert len(stt.calls) == 2
        assert len(adapter.prewarm_calls) == 1
        assert adapter.prewarm_calls[0]["reference_transcript"] == approved

    asyncio.run(scenario())


def test_qwen_alignment_never_replaces_exact_approved_transcript_entering_prompt() -> None:
    async def scenario() -> None:
        manager, _, events = _build_manager()
        manager.startup()
        adapter = RecordingQwenAdapter(events)
        manager.tts_adapters["qwen3_1_7b"] = adapter
        stt = ScriptedAlignmentSttAdapter("jose says cafe timing is ready")
        manager.stt_adapter = stt
        exact = "  José says café timing is ready.  "

        result = await manager.prepare_tts_engine(
            "qwen3_1_7b",
            voice_key="voice-aligned",
            reference_audio=_reference_wav_bytes(),
            reference_transcript=exact,
        )

        assert result["prompt_state"] == "ready"
        assert adapter.prewarm_calls[0]["reference_transcript"] == exact
        assert len(stt.calls) == 1

    asyncio.run(scenario())


def test_qwen_runtime_failure_marks_only_qwen_unavailable_and_preserves_stt_and_other_tts() -> None:
    async def scenario() -> None:
        qwen = importlib.import_module("app.models.tts_qwen3")
        manager, _, events = _build_manager()
        manager.startup()
        adapter = RecordingQwenAdapter(
            events,
            prewarm_error=qwen.Qwen3WorkerProtocolError(
                "Traceback C:\\private\\model.bin",
            ),
        )
        manager.tts_adapters["qwen3_1_7b"] = adapter
        stt = ScriptedAlignmentSttAdapter("the exact approved transcript")
        manager.stt_adapter = stt
        manager.stt_ready = True

        with pytest.raises(qwen.Qwen3WorkerProtocolError):
            await manager.prepare_tts_engine(
                "qwen3_1_7b",
                voice_key="voice-runtime-failed",
                reference_audio=_reference_wav_bytes(),
                reference_transcript="The exact approved transcript.",
            )

        failed = manager.health()
        failed_statuses = _engine_statuses(failed)
        assert failed_statuses["qwen3_1_7b"]["available"] is False
        assert failed_statuses["f5"]["available"] is True
        assert failed_statuses["xtts_v2"]["available"] is True
        assert failed["stt_ready"] is True
        assert manager.stt_adapter is stt
        manager.switch_tts_engine("xtts_v2")
        assert manager.health()["resident_tts_engine"] == "xtts_v2"
        _assert_no_raw_exception_text(failed)

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
