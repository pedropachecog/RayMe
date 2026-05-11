from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import math
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest


FORBIDDEN_PUBLIC_ERROR_TEXT = (
    "Traceback",
    "C:\\",
    "/home/",
    "openbmb/VoxCPM2",
)


def _voxcpm2_module() -> Any:
    return importlib.import_module("app.models.tts_voxcpm2")


def _registry_module() -> Any:
    return importlib.import_module("app.models.tts_registry")


def _request(**overrides: Any) -> Any:
    TtsSynthesisInput = getattr(_registry_module(), "TtsSynthesisInput")
    payload = {
        "text": "RayMe should sound natural.",
        "reference_audio": b"reference wav bytes",
        "reference_audio_content_type": "audio/wav",
        "reference_transcript": "Reference prompt text.",
    }
    payload.update(overrides)
    return TtsSynthesisInput(**payload)


def _tone(sample_rate: int = 48_000, seconds: float = 0.025) -> np.ndarray:
    samples = int(sample_rate * seconds)
    t = np.linspace(0, seconds, samples, endpoint=False)
    return (0.1 * np.sin(2 * math.pi * 220 * t)).astype(np.float32)


class ScriptedVoxCpmRuntime:
    sample_rate = 48_000
    allowed_generate_kwargs = {
        "text",
        "cfg_value",
        "inference_timesteps",
        "normalize",
        "denoise",
        "prompt_wav_path",
        "prompt_text",
        "reference_wav_path",
    }

    def __init__(
        self,
        audio: np.ndarray | None = None,
        streaming_chunks: list[Any] | None = None,
    ) -> None:
        self.audio = _tone() if audio is None else audio
        self.streaming_chunks = (
            [self.audio] if streaming_chunks is None else streaming_chunks
        )
        self.calls: list[dict[str, Any]] = []
        self.streaming_calls: list[dict[str, Any]] = []

    def parameters(self) -> list[Any]:
        return [types.SimpleNamespace(device=types.SimpleNamespace(type="cuda"))]

    def generate(self, **kwargs: Any) -> tuple[np.ndarray, int]:
        unknown_kwargs = set(kwargs) - self.allowed_generate_kwargs
        if unknown_kwargs:
            raise TypeError(f"unexpected generate kwargs: {sorted(unknown_kwargs)}")
        self.calls.append(kwargs)
        return self.audio, self.sample_rate

    def generate_streaming(self, **kwargs: Any) -> Any:
        unknown_kwargs = set(kwargs) - self.allowed_generate_kwargs
        if unknown_kwargs:
            raise TypeError(f"unexpected generate_streaming kwargs: {sorted(unknown_kwargs)}")
        self.streaming_calls.append(kwargs)
        yield from self.streaming_chunks


def test_voxcpm2_adapter_uses_cuda_guard_and_runtime_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    voxcpm2_module = _voxcpm2_module()
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    cuda_guard_calls: list[str] = []

    class ScriptedVoxCPM:
        @classmethod
        def from_pretrained(cls, *args: Any, **kwargs: Any) -> ScriptedVoxCpmRuntime:
            assert "device" not in kwargs
            calls.append((args, kwargs))
            return ScriptedVoxCpmRuntime()

    fake_voxcpm = types.ModuleType("voxcpm")
    fake_voxcpm.VoxCPM = ScriptedVoxCPM
    monkeypatch.setitem(sys.modules, "voxcpm", fake_voxcpm)
    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "voxcpm":
            return importlib.machinery.ModuleSpec("voxcpm", loader=None)
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(
        voxcpm2_module,
        "require_torch_cuda_runtime",
        lambda component: cuda_guard_calls.append(component),
    )

    adapter = voxcpm2_module.VoxCpm2TtsAdapter()
    adapter.load()

    assert adapter.required_modules == ("voxcpm",)
    assert voxcpm2_module.REQUIRED_PACKAGE == "voxcpm==2.0.2"
    assert voxcpm2_module.MODEL_ID == "openbmb/VoxCPM2"
    assert cuda_guard_calls == ["VoxCPM2", "VoxCPM2"]
    assert calls
    assert calls[0][0] == ("openbmb/VoxCPM2",)
    assert calls[0][1]["load_denoiser"] is False


def test_voxcpm2_cuda_guard_rejects_missing_device_evidence() -> None:
    voxcpm2_module = _voxcpm2_module()

    with pytest.raises(RuntimeError, match="did not expose CUDA-loaded parameters"):
        voxcpm2_module._assert_runtime_uses_cuda(object())


def test_voxcpm2_reference_only_mode_when_transcript_missing() -> None:
    runtime = ScriptedVoxCpmRuntime()
    adapter = _voxcpm2_module().VoxCpm2TtsAdapter(runtime_factory=lambda: runtime)

    result = adapter.synthesize(
        _request(
            reference_transcript="",
            voxcpm2_cloning_mode="auto",
            voxcpm2_style_prompt="warm phone-call voice",
            voxcpm2_cfg_value=2.0,
            voxcpm2_inference_timesteps=12,
            voxcpm2_normalize=True,
            voxcpm2_denoise=False,
        )
    )

    assert runtime.calls
    call = runtime.calls[0]
    assert call["text"] == "(warm phone-call voice)RayMe should sound natural."
    assert "reference_wav_path" in call
    assert Path(call["reference_wav_path"]).suffix == ".wav"
    assert call.get("prompt_wav_path") is None
    assert call.get("prompt_text") is None
    assert "style_prompt" not in call
    assert call["cfg_value"] == 2.0
    assert call["inference_timesteps"] == 12
    assert call["normalize"] is True
    assert call["denoise"] is False
    assert result.engine_id == "voxcpm2"
    assert result.sample_rate == 48_000
    assert "voxcpm2_reference_only_without_transcript" in result.warning_codes


def test_voxcpm2_transcript_guided_mode_passes_prompt_text() -> None:
    runtime = ScriptedVoxCpmRuntime()
    adapter = _voxcpm2_module().VoxCpm2TtsAdapter(runtime_factory=lambda: runtime)

    result = adapter.synthesize(
        _request(
            reference_transcript="A clean reference transcript.",
            voxcpm2_cloning_mode="transcript_guided",
        )
    )

    assert runtime.calls
    call = runtime.calls[0]
    assert call["prompt_text"] == "A clean reference transcript."
    assert "prompt_wav_path" in call
    assert Path(call["prompt_wav_path"]).suffix == ".wav"
    assert "reference_wav_path" in call
    assert call["reference_wav_path"] == call["prompt_wav_path"]
    assert result.warning_codes == []


def test_voxcpm2_returns_runtime_sample_rate_48000() -> None:
    runtime = ScriptedVoxCpmRuntime()
    adapter = _voxcpm2_module().VoxCpm2TtsAdapter(runtime_factory=lambda: runtime)

    result = adapter.synthesize(_request())

    assert result.engine_id == "voxcpm2"
    assert result.sample_rate == 48_000
    assert result.duration_ms and result.duration_ms > 0
    assert result.wav_bytes.startswith(b"RIFF")


def test_voxcpm2_installs_soundfile_librosa_load_shim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import soundfile as sf

    voxcpm2_module = _voxcpm2_module()
    fake_librosa = types.ModuleType("librosa")
    monkeypatch.setitem(sys.modules, "librosa", fake_librosa)
    input_path = tmp_path / "input.wav"
    sf.write(input_path, np.column_stack([_tone(), _tone()]), 48_000)

    voxcpm2_module._ensure_librosa_load()

    assert callable(fake_librosa.load)
    audio, sample_rate = fake_librosa.load(str(input_path), sr=24_000, mono=True)
    assert sample_rate == 24_000
    assert audio.ndim == 1
    assert audio.dtype == np.float32
    assert audio.size > 0


def test_voxcpm2_style_and_control_fields_are_bounded() -> None:
    TtsSynthesisInput = getattr(_registry_module(), "TtsSynthesisInput")

    valid = _request(
        voxcpm2_cloning_mode="reference_only",
        voxcpm2_style_prompt="calm, close-mic conversational style",
        voxcpm2_cfg_value=1.5,
        voxcpm2_inference_timesteps=16,
        voxcpm2_normalize=True,
        voxcpm2_denoise=True,
    )

    assert valid.voxcpm2_cloning_mode == "reference_only"
    assert valid.voxcpm2_style_prompt == "calm, close-mic conversational style"
    assert valid.voxcpm2_cfg_value == 1.5
    assert valid.voxcpm2_inference_timesteps == 16
    assert valid.voxcpm2_normalize is True
    assert valid.voxcpm2_denoise is True
    with pytest.raises(ValueError):
        TtsSynthesisInput(**{**valid.model_dump(), "voxcpm2_cloning_mode": "device_auto"})
    with pytest.raises(ValueError):
        TtsSynthesisInput(**{**valid.model_dump(), "voxcpm2_style_prompt": "x" * 601})
    with pytest.raises(ValueError):
        TtsSynthesisInput(**{**valid.model_dump(), "voxcpm2_cfg_value": 0.1})
    with pytest.raises(ValueError):
        TtsSynthesisInput(**{**valid.model_dump(), "voxcpm2_inference_timesteps": 0})


def test_voxcpm2_empty_audio_raises_sanitized_synthesis_failure() -> None:
    runtime = ScriptedVoxCpmRuntime(audio=np.asarray([], dtype=np.float32))
    adapter = _voxcpm2_module().VoxCpm2TtsAdapter(runtime_factory=lambda: runtime)

    with pytest.raises(ValueError) as exc_info:
        adapter.synthesize(_request())

    rendered = str(exc_info.value)
    assert "synthesis failed" in rendered.lower()
    for forbidden in FORBIDDEN_PUBLIC_ERROR_TEXT:
        assert forbidden not in rendered


def test_tts_streaming_contract_exports_chunk_types() -> None:
    registry = _registry_module()

    assert "TtsAudioChunk" in registry.__all__
    assert "TtsStreamingAdapter" in registry.__all__

    chunk = registry.TtsAudioChunk(
        engine_id="voxcpm2",
        chunk_index=0,
        wav_bytes=b"RIFF....WAVE",
        sample_rate=48_000,
        duration_ms=12.5,
        generated_at_ms=3.2,
    )

    assert chunk.engine_id == "voxcpm2"
    assert chunk.chunk_index == 0
    assert chunk.sample_rate == 48_000
    assert chunk.warning_codes == []
    assert hasattr(registry.TtsStreamingAdapter, "stream")


def test_voxcpm2_stream_yields_wav_chunks_with_timing() -> None:
    registry = _registry_module()
    runtime = ScriptedVoxCpmRuntime(
        streaming_chunks=[
            (_tone(sample_rate=24_000, seconds=0.02), 24_000),
            _tone(sample_rate=48_000, seconds=0.01),
        ]
    )
    adapter = _voxcpm2_module().VoxCpm2TtsAdapter(runtime_factory=lambda: runtime)

    chunks = list(
        adapter.stream(
            _request(
                reference_transcript="",
                voxcpm2_cloning_mode="auto",
            )
        )
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert all(isinstance(chunk, registry.TtsAudioChunk) for chunk in chunks)
    assert all(chunk.engine_id == "voxcpm2" for chunk in chunks)
    assert chunks[0].sample_rate == 24_000
    assert chunks[1].sample_rate == 48_000
    assert all(chunk.wav_bytes.startswith(b"RIFF") for chunk in chunks)
    assert all(chunk.duration_ms > 0 for chunk in chunks)
    assert all(chunk.generated_at_ms >= 0 for chunk in chunks)
    assert all(
        "voxcpm2_reference_only_without_transcript" in chunk.warning_codes
        for chunk in chunks
    )
    assert runtime.streaming_calls
    assert runtime.calls == []


def test_voxcpm2_stream_rejects_empty_chunks_without_generate_fallback() -> None:
    runtime = ScriptedVoxCpmRuntime(
        audio=_tone(),
        streaming_chunks=[
            np.asarray([], dtype=np.float32),
            (np.asarray([], dtype=np.float32), 48_000),
        ],
    )
    adapter = _voxcpm2_module().VoxCpm2TtsAdapter(runtime_factory=lambda: runtime)

    with pytest.raises(ValueError, match="VoxCPM2 streaming synthesis failed"):
        list(adapter.stream(_request()))

    assert runtime.streaming_calls
    assert runtime.calls == []
