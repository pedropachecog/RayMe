from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.audio.filters import HALLUCINATION_BLOCKLIST, is_blocklisted_transcript
from app.config import AiBackendSettings
from app.models.gpu_runtime import require_cuda_device_config


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
    ) -> None:
        self.settings = settings or AiBackendSettings()
        self.model_name = model_name or self.settings.stt_model
        self.compute_type = compute_type or self.settings.stt_compute_type
        self.language = self.settings.stt_language
        self.device = device
        self.model = model or whisper_model

    def transcribe(
        self,
        *,
        audio: Any,
        vad_adapter: Any | None = None,
        vad_threshold: float | None = None,
        vad_end_silence_ms: int | None = None,
        apply_vad_filter: bool = True,
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
        segments_iter, info = self._transcribe_with_model(
            model,
            audio,
            threshold=threshold,
            end_silence_ms=end_silence_ms,
            apply_vad_filter=apply_vad_filter,
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

    def warmup(self) -> None:
        self._ensure_model()

    def _ensure_model(self) -> Any:
        if self.model is None:
            require_cuda_device_config(
                component="faster-whisper STT",
                device=self.device,
                compute_type=self.compute_type,
            )
            from faster_whisper import WhisperModel

            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self.model

    def _transcribe_with_model(
        self,
        model: Any,
        audio: Any,
        *,
        threshold: float,
        end_silence_ms: int,
        apply_vad_filter: bool,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "language": "en",
            "task": "transcribe",
            "condition_on_previous_text": False,
            "beam_size": 5,
            "vad_filter": apply_vad_filter,
        }
        if apply_vad_filter:
            kwargs["vad_parameters"] = {
                "threshold": threshold,
                "min_silence_duration_ms": end_silence_ms,
            }
        return model.transcribe(
            audio,
            **kwargs,
        )

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
