from __future__ import annotations

from collections.abc import Callable
from os import PathLike
from typing import Any

import numpy as np
import soundfile as sf

GetSpeechTimestamps = Callable[..., list[dict[str, int | float]]]


class SileroVadAdapter:
    def __init__(
        self,
        *,
        model: Any | None = None,
        get_speech_timestamps_fn: GetSpeechTimestamps | None = None,
        threshold: float = 0.5,
        end_silence_ms: int = 700,
        sampling_rate: int = 16000,
    ) -> None:
        self.model = model
        self._get_speech_timestamps = get_speech_timestamps_fn
        self.threshold = threshold
        self.end_silence_ms = end_silence_ms
        self.sampling_rate = sampling_rate

    @property
    def ready(self) -> bool:
        return self.model is not None or self._get_speech_timestamps is not None

    def speech_timestamps(self, audio: Any) -> list[dict[str, int | float]]:
        self._ensure_model()
        if self.model is None or self._get_speech_timestamps is None:
            raise RuntimeError("Silero VAD model is not loaded")
        return list(
            self._get_speech_timestamps(
                self._coerce_audio(audio),
                self.model,
                threshold=self.threshold,
                sampling_rate=self.sampling_rate,
                min_silence_duration_ms=self.end_silence_ms,
            )
        )

    def _ensure_model(self) -> None:
        if self.model is not None and self._get_speech_timestamps is not None:
            return
        try:
            from silero_vad import get_speech_timestamps, load_silero_vad
        except Exception as exc:
            raise RuntimeError("Silero VAD is not available") from exc

        self.model = self.model or load_silero_vad()
        self._get_speech_timestamps = self._get_speech_timestamps or get_speech_timestamps

    def _coerce_audio(self, audio: Any) -> Any:
        if isinstance(audio, np.ndarray):
            return audio.astype(np.float32, copy=False)
        if isinstance(audio, (str, PathLike)):
            samples, sample_rate = sf.read(audio, dtype="float32", always_2d=True)
            mono = np.asarray(samples, dtype=np.float32).mean(axis=1)
            if int(sample_rate) != self.sampling_rate:
                raise RuntimeError("Silero VAD audio sample rate mismatch")
            return mono
        return audio
