from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.audio.filters import HALLUCINATION_BLOCKLIST, is_blocklisted_transcript
from app.config import AiBackendSettings


@dataclass(frozen=True)
class TranscriptionSegment:
    start: float
    end: float
    text: str


class WhisperSttAdapter:
    def __init__(
        self,
        *,
        model: Any | None = None,
        whisper_model: Any | None = None,
        settings: AiBackendSettings | None = None,
        model_name: str | None = None,
        compute_type: str | None = None,
        device: str = "cuda",
        model_factory: Callable[[str, str, str], Any] | None = None,
    ) -> None:
        self.settings = settings or AiBackendSettings()
        self.model_name = model_name or self.settings.stt_model
        self.compute_type = compute_type or self.settings.stt_compute_type
        self.language = self.settings.stt_language
        self.device = device
        self.model = model or whisper_model
        self._model_factory = model_factory

    def transcribe(
        self,
        *,
        audio: Any,
        vad_adapter: Any | None = None,
        vad_threshold: float | None = None,
        vad_end_silence_ms: int | None = None,
    ) -> dict[str, Any]:
        threshold = self.settings.vad_threshold if vad_threshold is None else vad_threshold
        end_silence_ms = (
            self.settings.vad_end_silence_ms
            if vad_end_silence_ms is None
            else vad_end_silence_ms
        )
        speech_detected = self._speech_detected(audio, vad_adapter)
        if not speech_detected:
            return self._manual_response(speech_detected=False)

        model = self._ensure_model()
        try:
            segments_iter, info = self._transcribe_with_model(
                model,
                audio,
                threshold=threshold,
                end_silence_ms=end_silence_ms,
            )
            segments = [self._segment_to_mapping(segment) for segment in list(segments_iter)]
        except RuntimeError as exc:
            if not self._can_retry_on_cpu(exc):
                raise
            self.device = "cpu"
            self.compute_type = "int8"
            self.model = None
            model = self._ensure_model()
            segments_iter, info = self._transcribe_with_model(
                model,
                audio,
                threshold=threshold,
                end_silence_ms=end_silence_ms,
            )
            segments = [self._segment_to_mapping(segment) for segment in list(segments_iter)]
        transcript = " ".join(segment["text"].strip() for segment in segments).strip()

        if not transcript or is_blocklisted_transcript(transcript):
            return self._manual_response(speech_detected=True, segments=segments)

        return {
            "status": "accepted",
            "transcript": transcript,
            "segments": segments,
            "language": getattr(info, "language", self.language),
            "model": self.model_name,
            "compute_type": self.compute_type,
            "speech_detected": True,
            "retry_allowed": False,
            "manual_transcript_allowed": True,
        }

    def transcribe_sample(self, **kwargs: Any) -> dict[str, Any]:
        return self.transcribe(**kwargs)

    def transcribe_audio(self, **kwargs: Any) -> dict[str, Any]:
        return self.transcribe(**kwargs)

    def _ensure_model(self) -> Any:
        if self.model is None:
            self.model = self._build_model()
        return self.model

    def _build_model(self) -> Any:
        if self._model_factory is not None:
            return self._model_factory(self.model_name, self.device, self.compute_type)
        from faster_whisper import WhisperModel

        return WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )

    def _transcribe_with_model(
        self,
        model: Any,
        audio: Any,
        *,
        threshold: float,
        end_silence_ms: int,
    ) -> Any:
        return model.transcribe(
            audio,
            language="en",
            task="transcribe",
            condition_on_previous_text=False,
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "threshold": threshold,
                "min_silence_duration_ms": end_silence_ms,
            },
        )

    def _can_retry_on_cpu(self, exc: RuntimeError) -> bool:
        if self.device == "cpu":
            return False
        message = str(exc).lower()
        return "cuda" in message or "cublas" in message or "cudnn" in message

    def _speech_detected(self, audio: Any, vad_adapter: Any | None) -> bool:
        if vad_adapter is None:
            return True
        timestamps = vad_adapter.speech_timestamps(audio)
        return bool(timestamps)

    def _segment_to_mapping(self, segment: Any) -> dict[str, Any]:
        return {
            "start": float(getattr(segment, "start", 0.0)),
            "end": float(getattr(segment, "end", 0.0)),
            "text": str(getattr(segment, "text", "")),
        }

    def _manual_response(
        self,
        *,
        speech_detected: bool,
        segments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "needs_manual_transcript",
            "transcript": "",
            "segments": segments or [],
            "language": self.language,
            "model": self.model_name,
            "compute_type": self.compute_type,
            "speech_detected": speech_detected,
            "retry_allowed": True,
            "manual_transcript_allowed": True,
        }
