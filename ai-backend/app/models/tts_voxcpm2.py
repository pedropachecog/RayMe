from __future__ import annotations

import tempfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.models.gpu_runtime import require_torch_cuda_runtime
from app.models.tts_registry import (
    ImportGatedTtsAdapter,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)


REQUIRED_PACKAGE = "voxcpm==2.0.2"
MODEL_ID = "openbmb/VoxCPM2"


class VoxCpm2TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "voxcpm2"
    required_modules = ("voxcpm",)
    synthesis_enabled = True

    def __init__(self, runtime_factory: Callable[[], Any] | None = None) -> None:
        super().__init__()
        self._runtime_factory = runtime_factory
        self._runtime: Any | None = None

    def startup_self_test(self) -> None:
        self._ensure_runtime_available()

    def load(self) -> None:
        if self._runtime_factory is None:
            self._ensure_runtime_available()
            require_torch_cuda_runtime("VoxCPM2")
        if self._runtime is None:
            self._runtime = self._build_runtime()
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False
        self._runtime = None

    def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
        if not self.loaded:
            self.load()
        runtime = self._runtime or self._build_runtime()
        self._runtime = runtime
        reference_transcript = (request.reference_transcript or "").strip()
        warning_codes: list[str] = []

        with tempfile.TemporaryDirectory(prefix="rayme-voxcpm2-") as tmp_dir:
            reference_path = Path(tmp_dir) / f"reference{_audio_suffix(request.reference_audio_content_type)}"
            reference_path.write_bytes(request.reference_audio)
            generate_kwargs = _build_generate_kwargs(
                request=request,
                reference_path=reference_path,
                reference_transcript=reference_transcript,
                warning_codes=warning_codes,
            )
            _ensure_librosa_load()
            generated = runtime.generate(**generate_kwargs)

        wav, sample_rate = _split_generate_result(generated, runtime)
        wav_array = np.asarray(wav, dtype=np.float32).flatten()
        if wav_array.size == 0:
            raise ValueError("VoxCPM2 synthesis failed")
        sample_rate = int(sample_rate)
        buffer = BytesIO()
        sf.write(buffer, wav_array, sample_rate, format="WAV")
        return TtsSynthesisOutput(
            engine_id=self.engine_id,
            wav_bytes=buffer.getvalue(),
            sample_rate=sample_rate,
            duration_ms=round((wav_array.size / float(sample_rate)) * 1000, 1),
            warning_codes=warning_codes,
            warnings=warning_codes,
        )

    def _build_runtime(self) -> Any:
        if self._runtime_factory is not None:
            return self._runtime_factory()
        require_torch_cuda_runtime("VoxCPM2")
        from voxcpm import VoxCPM

        runtime = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)
        _assert_runtime_uses_cuda(runtime)
        return runtime


def _assert_runtime_uses_cuda(runtime: Any) -> None:
    device_types: set[str] = set()
    for candidate in (runtime, getattr(runtime, "tts_model", None), getattr(runtime, "model", None)):
        if candidate is None or not hasattr(candidate, "parameters"):
            continue
        try:
            for parameter in candidate.parameters():
                device = getattr(parameter, "device", None)
                if device is not None:
                    device_types.add(str(getattr(device, "type", device)))
                break
        except Exception:
            continue
    if "cuda" not in device_types:
        raise RuntimeError("VoxCPM2 runtime did not expose CUDA-loaded parameters")


def _build_generate_kwargs(
    *,
    request: TtsSynthesisInput,
    reference_path: Path,
    reference_transcript: str,
    warning_codes: list[str],
) -> dict[str, Any]:
    style_prompt = (request.voxcpm2_style_prompt or "").strip()
    text = request.text
    if style_prompt and request.voxcpm2_cloning_mode != "transcript_guided":
        text = f"({style_prompt}){text}"

    kwargs: dict[str, Any] = {
        "text": text,
        "cfg_value": request.voxcpm2_cfg_value,
        "inference_timesteps": request.voxcpm2_inference_timesteps,
        "normalize": request.voxcpm2_normalize,
        "denoise": request.voxcpm2_denoise,
    }

    if request.voxcpm2_cloning_mode == "transcript_guided" and reference_transcript:
        kwargs["prompt_wav_path"] = str(reference_path)
        kwargs["prompt_text"] = reference_transcript
        kwargs["reference_wav_path"] = str(reference_path)
    else:
        kwargs["reference_wav_path"] = str(reference_path)
        if request.voxcpm2_cloning_mode != "reference_only" and not reference_transcript:
            warning_codes.append("voxcpm2_reference_only_without_transcript")
    return kwargs


def _split_generate_result(generated: Any, runtime: Any) -> tuple[Any, int]:
    if isinstance(generated, tuple) and len(generated) >= 2:
        return generated[0], int(generated[1])
    sample_rate = int(getattr(runtime, "sample_rate", 48_000))
    return generated, sample_rate


def _ensure_librosa_load() -> None:
    try:
        import librosa  # type: ignore[import]
    except Exception:
        return
    if callable(getattr(librosa, "load", None)):
        return

    def _soundfile_load(
        path: str,
        *,
        sr: int | None = 22050,
        mono: bool = True,
        dtype: str = "float32",
        **_: Any,
    ) -> tuple[np.ndarray, int]:
        audio, source_sr = sf.read(path, dtype=dtype, always_2d=False)
        audio_array = np.asarray(audio, dtype=np.float32)
        if mono and audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)
        elif not mono and audio_array.ndim == 1:
            audio_array = audio_array.reshape(-1, 1)
        target_sr = int(sr) if sr else int(source_sr)
        if target_sr != int(source_sr):
            audio_array = _resample_linear(audio_array, int(source_sr), target_sr)
        return audio_array, target_sr

    librosa.load = _soundfile_load  # type: ignore[attr-defined]


def _resample_linear(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr <= 0 or target_sr <= 0 or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    if audio.ndim == 1:
        sample_count = max(int(round(audio.shape[0] * target_sr / source_sr)), 1)
        source_x = np.linspace(0.0, 1.0, num=audio.shape[0], endpoint=False)
        target_x = np.linspace(0.0, 1.0, num=sample_count, endpoint=False)
        return np.interp(target_x, source_x, audio).astype(np.float32)
    channels = [
        _resample_linear(audio[:, channel], source_sr, target_sr)
        for channel in range(audio.shape[1])
    ]
    return np.stack(channels, axis=1).astype(np.float32)


def _audio_suffix(content_type: str | None) -> str:
    return {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
    }.get((content_type or "").lower(), ".wav")
