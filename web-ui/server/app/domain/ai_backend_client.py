"""Typed HTTP client for transient AI backend processing calls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

UNREACHABLE_MESSAGE = "AI backend unreachable"
INVALID_RESPONSE_MESSAGE = "AI backend returned an invalid response"
TRANSCRIPTION_FAILED_MESSAGE = "Transcription failed"
SYNTHESIS_FAILED_MESSAGE = "Synthesis failed"
WEBRTC_FAILED_MESSAGE = "Call control request failed"


class EngineStatus(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(alias="engine_id")
    label: str | None = None
    available: bool = True
    state: str | None = None
    resident: bool | None = None
    unavailable_reason: str | None = None


class AiBackendStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["ok", "degraded", "starting", "error"]
    stt_model: str | None = None
    stt_compute_type: str | None = None
    vad_ready: bool = False
    resident_tts_engine: str | None = None
    available_engines: list[EngineStatus] = Field(default_factory=list)
    loading_engine: str | None = None
    vram_used_mb: float | None = None
    vram_headroom_mb: float | None = None


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    transcript: str | None = None
    language: str | None = None
    model: str | None = None
    compute_type: str | None = None
    segments: list[dict[str, Any]] = Field(default_factory=list)
    speech_detected: bool = False
    retry_allowed: bool = True
    manual_transcript_allowed: bool = True


class SynthesisResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    engine_id: str
    content_type: str
    audio_base64: str | None = None
    duration_ms: int | float | None = None


class AiBackendClientError(Exception):
    """Public-safe AI backend client error."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_public_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class AiBackendUnavailable(AiBackendClientError):
    """The backend could not be reached or returned malformed status data."""


class AiBackendProcessingError(AiBackendClientError):
    """The backend reached a processing path but could not complete it."""


class AiBackendClient:
    """Bounded httpx wrapper that maps backend details to safe public errors."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
        transcription_timeout: float = 120.0,
        synthesis_timeout: float = 120.0,
    ) -> None:
        self._http_client = http_client
        self._timeout = timeout
        self._transcription_timeout = transcription_timeout
        self._synthesis_timeout = synthesis_timeout

    async def get_status(self, base_url: str) -> AiBackendStatus:
        response = await self._request("GET", _join_endpoint(base_url, "/health"))
        payload = _json_payload(response)
        try:
            return AiBackendStatus.model_validate(payload)
        except ValidationError as exc:
            raise _invalid_response() from exc

    async def transcribe_sample(
        self,
        base_url: str,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> TranscriptionResult:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, "/stt/transcribe"),
            files={"file": (filename, audio_bytes, content_type)},
            processing_message=TRANSCRIPTION_FAILED_MESSAGE,
            processing_code="transcription_failed",
            timeout=self._transcription_timeout,
        )
        payload = _json_payload(response)
        try:
            return TranscriptionResult.model_validate(payload)
        except ValidationError as exc:
            raise _invalid_response() from exc

    async def synthesize(self, base_url: str, payload: Mapping[str, Any]) -> SynthesisResult:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, "/tts/synthesize"),
            json=dict(payload),
            processing_message=SYNTHESIS_FAILED_MESSAGE,
            processing_code="synthesis_failed",
            timeout=self._synthesis_timeout,
        )
        response_payload = _json_payload(response)
        try:
            return SynthesisResult.model_validate(response_payload)
        except ValidationError as exc:
            raise _invalid_response() from exc

    async def get_webrtc_status(self, base_url: str) -> dict[str, Any]:
        response = await self._request("GET", _join_endpoint(base_url, "/webrtc/status"))
        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise _invalid_response()
        return dict(payload)

    async def create_webrtc_offer(
        self,
        base_url: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, "/webrtc/offer"),
            json=dict(payload),
            processing_message=WEBRTC_FAILED_MESSAGE,
            processing_code="webrtc_offer_failed",
            timeout=self._timeout,
        )
        response_payload = _json_payload(response)
        if not isinstance(response_payload, dict):
            raise _invalid_response()
        return dict(response_payload)

    async def mute_call(self, base_url: str, session_id: str, muted: bool) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/mute"),
            json={"muted": muted},
            processing_message=WEBRTC_FAILED_MESSAGE,
            processing_code="call_control_failed",
            timeout=self._timeout,
        )
        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise _invalid_response()
        return dict(payload)

    async def interrupt_call(self, base_url: str, session_id: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/interrupt"),
            processing_message=WEBRTC_FAILED_MESSAGE,
            processing_code="call_control_failed",
            timeout=self._timeout,
        )
        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise _invalid_response()
        return dict(payload)

    async def end_call(self, base_url: str, session_id: str, reason: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/end"),
            json={"reason": reason},
            processing_message=WEBRTC_FAILED_MESSAGE,
            processing_code="call_control_failed",
            timeout=self._timeout,
        )
        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise _invalid_response()
        return dict(payload)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        processing_message: str | None = None,
        processing_code: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            if self._http_client is not None:
                response = await self._http_client.request(method, url, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=timeout or self._timeout, verify=False) as client:
                    response = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise AiBackendUnavailable(code="unreachable", message=UNREACHABLE_MESSAGE) from exc

        if response.status_code >= 500 and processing_message and processing_code:
            raise AiBackendProcessingError(code=processing_code, message=processing_message)
        if response.status_code in {401, 403}:
            raise AiBackendUnavailable(code="unauthorized", message=UNREACHABLE_MESSAGE)
        if response.status_code >= 400:
            raise AiBackendUnavailable(code="unreachable", message=UNREACHABLE_MESSAGE)
        return response


def _join_endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _json_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise _invalid_response() from exc


def _invalid_response() -> AiBackendUnavailable:
    return AiBackendUnavailable(code="invalid_response", message=INVALID_RESPONSE_MESSAGE)


__all__ = [
    "AiBackendClient",
    "AiBackendClientError",
    "AiBackendProcessingError",
    "AiBackendStatus",
    "AiBackendUnavailable",
    "EngineStatus",
    "SynthesisResult",
    "TranscriptionResult",
]
