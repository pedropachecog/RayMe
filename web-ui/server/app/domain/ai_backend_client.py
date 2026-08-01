"""Typed HTTP client for transient AI backend processing calls."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.domain.speech_terminal import (
    SpeechTurnTerminal,
    _speech_error_terminal,
    _speech_terminal_from_response,
)

UNREACHABLE_MESSAGE = "AI backend unreachable"
INVALID_RESPONSE_MESSAGE = "AI backend returned an invalid response"
TRANSCRIPTION_FAILED_MESSAGE = "Transcription failed"
SYNTHESIS_FAILED_MESSAGE = "Synthesis failed"
WEBRTC_FAILED_MESSAGE = "Call control request failed"
WEBRTC_OFFER_FAILED_MESSAGE = "WebRTC offer could not be accepted"
SPEECH_TURN_QUEUE_CAPACITY = 2
SAFE_PROCESSING_MESSAGES = {
    "qwen3_reference_audio_required": "Reference audio is required",
    "qwen3_reference_audio_invalid": "Reference audio is invalid",
    "qwen3_transcript_required": "Matching reference transcript is required",
    "qwen3_transcript_mismatch": "Reference audio and transcript do not match",
    "qwen3_alignment_failed": "Reference alignment could not be verified",
    "qwen3_prompt_failed": "Voice preparation failed",
    "qwen3_prompt_not_ready": "Selected voice is not ready",
    "qwen3_target_required": "Speech text is required",
    "qwen3_target_too_long": "Speech segment is too long",
    "qwen3_generation_ceiling": "Speech request exceeded its safety limit",
    "qwen3_no_audio": "Speech generation produced no audio",
    "qwen3_worker_protocol": "Qwen3-TTS runtime failed",
    "qwen3_worker_timeout": "Qwen3-TTS runtime timed out",
    "qwen3_worker_stopped": "Qwen3-TTS runtime stopped",
    "qwen3_invalidate_failed": "Voice prompt removal failed",
    "call_tts_prepare_mismatch": "Selected voice does not match the call",
    "call_tts_prepare_unavailable": "Voice preparation is unavailable",
    "call_tts_prepare_failed": "Voice preparation failed",
    "webrtc_offer_failed": WEBRTC_OFFER_FAILED_MESSAGE,
}


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


class QwenPromptInvalidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine_id: Literal["qwen3_1_7b"]
    voice_key: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    status: Literal["invalidated", "not_present"]
    matched: bool
    active_cancelled: bool

    @model_validator(mode="after")
    def validate_status(self) -> "QwenPromptInvalidationResult":
        if (self.status == "invalidated") != self.matched:
            raise ValueError("prompt invalidation status mismatch")
        return self


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


class SpeechTurnClosedError(AiBackendProcessingError):
    """A segment was offered after the turn reached a terminal state."""

    def __init__(self) -> None:
        super().__init__(code="call_tts_failed", message="Speech playback failed")


@dataclass(frozen=True, slots=True)
class _SpeechSubmission:
    text: str
    final_chunk: bool
    segment_id: str
    segment_ordinal: int


class SpeechTurn:
    """Bounded sequential scheduler over the existing WebRTC speak endpoint.

    `submit` returns once a natural segment has entered the capacity-two
    scheduler. One background worker owns calls to the backend, so one native
    Qwen generation runs at a time. `finalize` is the only terminal wait.
    """

    def __init__(
        self,
        *,
        backend: Any,
        base_url: str,
        session_id: str,
        turn_id: str,
        voice_id: str,
        engine_id: str,
        voice_reference: Mapping[str, Any],
        queue_capacity: int = SPEECH_TURN_QUEUE_CAPACITY,
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("speech turn queue capacity must be positive")
        self._backend = backend
        self._base_url = base_url
        self._session_id = session_id
        self._turn_id = turn_id
        self._common_payload = {
            "voice_id": voice_id,
            "engine_id": engine_id,
            **dict(voice_reference),
        }
        self._queue: asyncio.Queue[_SpeechSubmission] = asyncio.Queue(maxsize=queue_capacity)
        self._worker: asyncio.Task[None] | None = None
        self._closed = False
        self._terminal: SpeechTurnTerminal | None = None
        self._next_segment_ordinal = 0

    @property
    def terminal(self) -> SpeechTurnTerminal | None:
        return self._terminal

    async def submit(self, text: str) -> None:
        segment = text.strip()
        if not segment:
            return
        self._require_open()
        await self._queue.put(self._new_submission(segment, final_chunk=False))
        self._ensure_worker()
        if self._terminal is not None:
            raise SpeechTurnClosedError()

    async def finalize(self, tail: str | None = None) -> SpeechTurnTerminal:
        self._require_open()
        final_text = str(tail or "").strip()
        # Even when the incremental segmenter emitted the final sentence at a
        # natural boundary, the AI backend still owns the call state machine.
        # Send an explicit empty terminal marker instead of completing only in
        # this web process; the marker emits ai_done without replaying TTS.
        await self._queue.put(self._new_submission(final_text, final_chunk=True))
        self._closed = True
        self._ensure_worker()
        assert self._worker is not None
        await self._worker
        if self._terminal is None:
            self._terminal = _speech_error_terminal("call_tts_failed")
        return self._terminal

    async def cancel(self) -> SpeechTurnTerminal:
        self._closed = True
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
        if self._terminal is None or self._terminal.status == "normal":
            self._terminal = SpeechTurnTerminal(
                status="cancelled",
                playout_completed=False,
            )
        self._discard_pending()
        return self._terminal

    def _require_open(self) -> None:
        if self._closed or self._terminal is not None:
            raise SpeechTurnClosedError()

    def _ensure_worker(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    def _new_submission(self, text: str, *, final_chunk: bool) -> _SpeechSubmission:
        ordinal = self._next_segment_ordinal
        self._next_segment_ordinal += 1
        return _SpeechSubmission(
            text=text,
            final_chunk=final_chunk,
            segment_id=f"{self._turn_id}:{ordinal}",
            segment_ordinal=ordinal,
        )

    async def _run(self) -> None:
        try:
            while True:
                item = await self._queue.get()
                assert isinstance(item, _SpeechSubmission)
                if self._terminal is not None:
                    return
                try:
                    result = await self._speak(item)
                except AiBackendClientError as exc:
                    self._terminal = _speech_error_terminal(exc.code)
                    return
                except asyncio.CancelledError:
                    self._terminal = SpeechTurnTerminal(
                        status="cancelled",
                        playout_completed=False,
                    )
                    raise
                except Exception:
                    self._terminal = _speech_error_terminal("call_tts_failed")
                    return

                observed = _speech_terminal_from_response(
                    result,
                    require_final=item.final_chunk,
                )
                if observed.status != "normal" or item.final_chunk:
                    self._terminal = observed
                    return
        finally:
            self._discard_pending()

    async def _speak(self, item: _SpeechSubmission) -> dict[str, Any]:
        speak_call = getattr(self._backend, "speak_call", None)
        if not callable(speak_call):
            raise AiBackendUnavailable(
                code="call_backend_client_misconfigured",
                message="AI backend unreachable",
            )
        payload = {
            "turn_id": self._turn_id,
            "text": item.text,
            "final_chunk": item.final_chunk,
            "segment_id": item.segment_id,
            "segment_ordinal": item.segment_ordinal,
            **self._common_payload,
        }
        result = await speak_call(self._base_url, self._session_id, payload)
        if not isinstance(result, Mapping):
            raise AiBackendUnavailable(
                code="invalid_response",
                message=INVALID_RESPONSE_MESSAGE,
            )
        return dict(result)

    def _discard_pending(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return


class AiBackendClient:
    """Bounded httpx wrapper that maps backend details to safe public errors."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
        transcription_timeout: float = 120.0,
        synthesis_timeout: float = 120.0,
        webrtc_timeout: float = 30.0,
    ) -> None:
        self._http_client = http_client
        self._timeout = timeout
        self._transcription_timeout = transcription_timeout
        self._synthesis_timeout = synthesis_timeout
        self._webrtc_timeout = webrtc_timeout

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

    async def invalidate_qwen_prompt(
        self,
        base_url: str,
        voice_key: str,
    ) -> QwenPromptInvalidationResult:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, "/tts/qwen3/prompts/invalidate"),
            json={"engine_id": "qwen3_1_7b", "voice_key": voice_key},
            processing_message="Voice prompt removal failed",
            processing_code="qwen3_invalidate_failed",
            timeout=self._timeout,
        )
        payload = _json_payload(response)
        try:
            return QwenPromptInvalidationResult.model_validate(payload)
        except ValidationError as exc:
            raise _invalid_response() from exc

    async def get_webrtc_status(self, base_url: str) -> dict[str, Any]:
        response = await self._request("GET", _join_endpoint(base_url, "/webrtc/status"))
        payload = _json_payload(response)
        if not isinstance(payload, dict):
            raise _invalid_response()
        return dict(payload)

    async def get_tts_preparation_status(self, base_url: str) -> dict[str, Any]:
        payload = await self.get_webrtc_status(base_url)
        raw_model = payload.get("tts_model")
        model = raw_model if isinstance(raw_model, dict) else {}
        resident_engine = _safe_identifier(model.get("resident_engine"))
        loading_engine = _safe_identifier(model.get("loading_engine"))
        if loading_engine is not None:
            model_state = "loading"
            model_engine = loading_engine
        elif resident_engine is not None:
            model_state = "resident"
            model_engine = resident_engine
        else:
            model_state = "idle"
            model_engine = None

        raw_prompt = payload.get("selected_voice_prompt")
        prompt = raw_prompt if isinstance(raw_prompt, dict) else {}
        prompt_state = prompt.get("state")
        if prompt_state not in {"none", "prewarming", "ready", "failed"}:
            prompt_state = "none"
        return {
            "model": {"state": model_state, "engine_id": model_engine},
            "prompt": {
                "state": prompt_state,
                "voice_key": _safe_identifier(prompt.get("voice_key")),
                "error_code": _safe_identifier(prompt.get("error_code")),
            },
        }

    async def prepare_call_speech(
        self,
        base_url: str,
        session_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/prepare"),
            json=dict(payload),
            processing_message="Voice preparation failed",
            processing_code="call_tts_prepare_failed",
            timeout=self._synthesis_timeout,
        )
        response_payload = _json_payload(response)
        if not isinstance(response_payload, dict):
            raise _invalid_response()
        return dict(response_payload)

    async def create_webrtc_offer(
        self,
        base_url: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, "/webrtc/offer"),
            json=dict(payload),
            processing_message=WEBRTC_OFFER_FAILED_MESSAGE,
            processing_code="webrtc_offer_failed",
            timeout=self._webrtc_timeout,
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

    async def speak_call(
        self,
        base_url: str,
        session_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/speak"),
            json=dict(payload),
            processing_message=WEBRTC_FAILED_MESSAGE,
            processing_code="call_tts_failed",
            timeout=self._synthesis_timeout,
        )
        response_payload = _json_payload(response)
        if not isinstance(response_payload, dict):
            raise _invalid_response()
        return dict(response_payload)

    async def backfill_call_audio(
        self,
        base_url: str,
        session_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/reconnect-audio"),
            json=dict(payload),
            processing_message=WEBRTC_FAILED_MESSAGE,
            processing_code="call_reconnect_audio_failed",
            timeout=self._webrtc_timeout,
        )
        response_payload = _json_payload(response)
        if not isinstance(response_payload, dict):
            raise _invalid_response()
        return dict(response_payload)

    async def drain_call_events(self, base_url: str, session_id: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            _join_endpoint(base_url, f"/webrtc/sessions/{session_id}/events/drain"),
            processing_message=WEBRTC_FAILED_MESSAGE,
            processing_code="call_control_failed",
            timeout=self._timeout,
        )
        response_payload = _json_payload(response)
        if not isinstance(response_payload, dict):
            raise _invalid_response()
        return dict(response_payload)

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
            request_kwargs = dict(kwargs)
            if timeout is not None:
                request_kwargs["timeout"] = timeout
            if self._http_client is not None:
                response = await self._http_client.request(method, url, **request_kwargs)
            else:
                async with httpx.AsyncClient(timeout=self._timeout, verify=False) as client:
                    response = await client.request(method, url, **request_kwargs)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise AiBackendUnavailable(code="unreachable", message=UNREACHABLE_MESSAGE) from exc

        if response.status_code in {401, 403}:
            raise AiBackendUnavailable(code="unauthorized", message=UNREACHABLE_MESSAGE)
        if response.status_code >= 400 and processing_message and processing_code:
            raise _processing_error_from_response(response, processing_code, processing_message)
        if response.status_code >= 400:
            raise AiBackendUnavailable(code="unreachable", message=UNREACHABLE_MESSAGE)
        return response


def _join_endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _processing_error_from_response(
    response: httpx.Response,
    fallback_code: str,
    fallback_message: str,
) -> AiBackendProcessingError:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, dict):
        detail = payload if isinstance(payload, dict) else {}

    code = detail.get("code")
    if not isinstance(code, str) or not code:
        code = fallback_code
    message = SAFE_PROCESSING_MESSAGES.get(code, fallback_message)
    return AiBackendProcessingError(code=code, message=message)


def _safe_identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 160:
        return None
    if not all(character.isalnum() or character in "_.:-" for character in value):
        return None
    return value


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
    "QwenPromptInvalidationResult",
    "SPEECH_TURN_QUEUE_CAPACITY",
    "SpeechTurn",
    "SpeechTurnClosedError",
    "SpeechTurnTerminal",
    "SynthesisResult",
    "TranscriptionResult",
]
