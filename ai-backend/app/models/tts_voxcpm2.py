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

        return VoxCPM.from_pretrained("openbmb/VoxCPM2", device="cuda")


def _build_generate_kwargs(
    *,
    request: TtsSynthesisInput,
    reference_path: Path,
    reference_transcript: str,
    warning_codes: list[str],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "text": request.text,
        "cfg_value": request.voxcpm2_cfg_value,
        "inference_timesteps": request.voxcpm2_inference_timesteps,
        "normalize": request.voxcpm2_normalize,
        "denoise": request.voxcpm2_denoise,
    }
    style_prompt = (request.voxcpm2_style_prompt or "").strip()
    if style_prompt:
        kwargs["style_prompt"] = style_prompt

    if request.voxcpm2_cloning_mode == "transcript_guided" and reference_transcript:
        kwargs["prompt_wav_path"] = str(reference_path)
        kwargs["prompt_text"] = reference_transcript
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


def _audio_suffix(content_type: str | None) -> str:
    return {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
    }.get((content_type or "").lower(), ".wav")
