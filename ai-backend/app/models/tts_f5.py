from __future__ import annotations

import importlib.machinery
import sys
import tempfile
import types
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.models.tts_registry import (
    ImportGatedTtsAdapter,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)


class F5TtsAdapter(ImportGatedTtsAdapter):
    engine_id = "f5"
    required_modules = ("f5_tts",)

    def __init__(self, runtime_factory: Callable[[], Any] | None = None) -> None:
        super().__init__()
        self._runtime_factory = runtime_factory
        self._runtime: Any | None = None

    def load(self) -> None:
        self._ensure_runtime_available()
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def synthesize(self, request: TtsSynthesisInput) -> TtsSynthesisOutput:
        if not self.loaded:
            self.load()
        runtime = self._runtime or self._build_runtime()
        self._runtime = runtime
        reference_transcript = (request.reference_transcript or "").strip()
        if not reference_transcript:
            raise ValueError("F5 synthesis requires a reference transcript")

        with tempfile.TemporaryDirectory(prefix="rayme-f5-") as tmp_dir:
            reference_path = Path(tmp_dir) / f"reference{_audio_suffix(request.reference_audio_content_type)}"
            reference_path.write_bytes(request.reference_audio)
            wav, sample_rate, _ = runtime.infer(
                str(reference_path),
                reference_transcript,
                request.text,
                show_info=lambda *_args, **_kwargs: None,
                progress=None,
                nfe_step=7,
            )

        wav_array = np.asarray(wav, dtype=np.float32).flatten()
        if wav_array.size == 0:
            raise ValueError("F5 synthesis returned empty audio")
        buffer = BytesIO()
        sf.write(buffer, wav_array, int(sample_rate), format="WAV")
        wav_bytes = buffer.getvalue()
        return TtsSynthesisOutput(
            engine_id=self.engine_id,
            wav_bytes=wav_bytes,
            sample_rate=int(sample_rate),
            duration_ms=round((wav_array.size / float(sample_rate)) * 1000, 1),
        )

    def _build_runtime(self) -> Any:
        if self._runtime_factory is not None:
            return self._runtime_factory()
        _install_f5_runtime_shims()
        from f5_tts.api import F5TTS

        return F5TTS()


def _install_f5_runtime_shims() -> None:
    """Avoid F5 import crashes from training deps and librosa/numba."""
    import torchaudio.functional as audio_functional

    def mel_filter(
        *,
        sr: int,
        n_fft: int,
        n_mels: int,
        fmin: float = 0,
        fmax: float | None = None,
        **_: Any,
    ) -> np.ndarray:
        filter_bank = audio_functional.melscale_fbanks(
            n_freqs=(int(n_fft) // 2) + 1,
            f_min=float(fmin or 0),
            f_max=float((sr / 2) if fmax is None else fmax),
            n_mels=int(n_mels),
            sample_rate=int(sr),
            norm="slaney",
            mel_scale="slaney",
        )
        return filter_bank.transpose(0, 1).cpu().numpy().astype(np.float32)

    librosa_mod = types.ModuleType("librosa")
    librosa_mod.__path__ = []
    librosa_mod.__spec__ = importlib.machinery.ModuleSpec(
        "librosa",
        loader=None,
        is_package=True,
    )
    filters_mod = types.ModuleType("librosa.filters")
    filters_mod.__spec__ = importlib.machinery.ModuleSpec(
        "librosa.filters",
        loader=None,
        is_package=False,
    )
    filters_mod.mel = mel_filter
    librosa_mod.filters = filters_mod
    sys.modules["librosa"] = librosa_mod
    sys.modules["librosa.filters"] = filters_mod

    trainer_mod = types.ModuleType("f5_tts.model.trainer")
    trainer_mod.__spec__ = importlib.machinery.ModuleSpec(
        "f5_tts.model.trainer",
        loader=None,
        is_package=False,
    )

    class Trainer:  # pragma: no cover - runtime shim only
        pass

    trainer_mod.Trainer = Trainer
    sys.modules["f5_tts.model.trainer"] = trainer_mod


def _audio_suffix(content_type: str | None) -> str:
    return {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
    }.get((content_type or "").lower(), ".wav")
