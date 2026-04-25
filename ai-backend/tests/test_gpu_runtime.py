from __future__ import annotations

import importlib
import sys
import types
from typing import Any

import pytest


def test_cuda_device_guard_rejects_cpu_device_config() -> None:
    gpu_runtime = importlib.import_module("app.models.gpu_runtime")

    with pytest.raises(RuntimeError, match="requires CUDA device"):
        gpu_runtime.require_cuda_device_config(
            component="faster-whisper STT",
            device="cpu",
            compute_type="int8_float16",
        )


def test_cuda_device_guard_rejects_cpu_compute_type() -> None:
    gpu_runtime = importlib.import_module("app.models.gpu_runtime")

    with pytest.raises(RuntimeError, match="float16-capable"):
        gpu_runtime.require_cuda_device_config(
            component="faster-whisper STT",
            device="cuda",
            compute_type="int8",
        )


def test_torch_cuda_guard_rejects_cpu_only_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    gpu_runtime = importlib.import_module("app.models.gpu_runtime")
    fake_torch = types.SimpleNamespace(
        __version__="2.10.0+cpu",
        version=types.SimpleNamespace(cuda=None),
        cuda=types.SimpleNamespace(is_available=lambda: False),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    with pytest.raises(RuntimeError, match="CUDA-enabled PyTorch"):
        gpu_runtime.require_torch_cuda_runtime("F5-TTS")


def test_torch_cuda_guard_accepts_cuda_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    gpu_runtime = importlib.import_module("app.models.gpu_runtime")
    fake_cuda = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda _index: "NVIDIA GeForce RTX 3060",
    )
    fake_torch = types.SimpleNamespace(
        __version__="2.10.0+cu126",
        version=types.SimpleNamespace(cuda="12.6"),
        cuda=fake_cuda,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    info = gpu_runtime.require_torch_cuda_runtime("F5-TTS")

    assert info.torch_version == "2.10.0+cu126"
    assert info.torch_cuda_version == "12.6"
    assert info.device_name == "NVIDIA GeForce RTX 3060"


def test_stt_real_model_load_refuses_cpu_device_before_import() -> None:
    stt_module = importlib.import_module("app.models.stt")
    WhisperSttAdapter = getattr(stt_module, "WhisperSttAdapter")

    adapter = WhisperSttAdapter(
        model_name="distil-large-v3",
        compute_type="int8_float16",
        device="cpu",
    )

    with pytest.raises(RuntimeError, match="requires CUDA device"):
        adapter._ensure_model()


def test_stt_real_model_load_refuses_cpu_compute_type_before_import() -> None:
    stt_module = importlib.import_module("app.models.stt")
    WhisperSttAdapter = getattr(stt_module, "WhisperSttAdapter")

    adapter = WhisperSttAdapter(
        model_name="distil-large-v3",
        compute_type="int8",
        device="cuda",
    )

    with pytest.raises(RuntimeError, match="float16-capable"):
        adapter._ensure_model()


def test_f5_production_load_requires_torch_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    f5_module = importlib.import_module("app.models.tts_f5")
    F5TtsAdapter = getattr(f5_module, "F5TtsAdapter")

    def fake_available(self: Any) -> None:
        return None

    def fake_guard(component: str) -> None:
        raise RuntimeError(f"{component} requires a CUDA-enabled PyTorch runtime")

    monkeypatch.setattr(F5TtsAdapter, "_ensure_runtime_available", fake_available)
    monkeypatch.setattr(f5_module, "require_torch_cuda_runtime", fake_guard)

    with pytest.raises(RuntimeError, match="F5-TTS requires a CUDA-enabled PyTorch runtime"):
        F5TtsAdapter().load()

