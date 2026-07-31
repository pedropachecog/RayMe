from __future__ import annotations

import base64
import asyncio
import logging
import uuid
from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.config import AiBackendSettings
from app.models.model_manager import ModelManager
from app.models.tts_qwen3 import (
    Qwen3GenerationCeilingError,
    Qwen3PromptError,
    Qwen3ValidationError,
    Qwen3WorkerError,
)
from app.models.tts_registry import (
    MAX_REFERENCE_AUDIO_B64_LENGTH,
    MAX_REFERENCE_AUDIO_BYTES,
    TtsSynthesisInput,
    TtsSynthesisOutput,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class TtsSynthesizeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_id: str = Field(min_length=1, max_length=128)
    engine_id: str | None = Field(default=None, max_length=64)
    text: str = Field(min_length=1, max_length=5000)
    reference_audio_b64: str = Field(
        min_length=1,
        max_length=MAX_REFERENCE_AUDIO_B64_LENGTH,
        validation_alias=AliasChoices("reference_audio_b64", "reference_audio_base64"),
    )
    reference_transcript: str | None = Field(default=None, max_length=10000)
    reference_audio_content_type: str | None = Field(default=None, max_length=120)
    use_default_engine: bool = False
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)
    voxcpm2_cloning_mode: str = Field(default="auto", pattern="^(auto|reference_only|transcript_guided)$")
    voxcpm2_style_prompt: str | None = Field(default=None, max_length=300)
    voxcpm2_cfg_value: float = Field(default=2.0, ge=1.0, le=3.0)
    voxcpm2_inference_timesteps: int = Field(default=10, ge=4, le=30)
    voxcpm2_normalize: bool = True
    voxcpm2_denoise: bool = True


class QwenPromptInvalidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine_id: Literal["qwen3_1_7b"]
    voice_key: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )


@router.post("/tts/qwen3/prompts/invalidate")
async def invalidate_qwen_prompt(
    request: Request,
    payload: QwenPromptInvalidateRequest,
) -> dict[str, object]:
    manager = _manager_from_app(request)
    invalidate = getattr(manager, "invalidate_tts_prompt", None)
    if not callable(invalidate):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "qwen3_invalidate_failed",
                "message": "Voice prompt removal failed",
                "engine_id": payload.engine_id,
                "retryable": True,
            },
        )
    try:
        result = await invalidate(payload.engine_id, payload.voice_key)
    except Exception as exc:
        _mark_engine_unavailable(manager, payload.engine_id, failure=exc)
        logger.warning(
            "[rayme-tts] prompt.invalidate_failed engine=%s code=%s exc=%s",
            payload.engine_id,
            getattr(exc, "code", "qwen3_invalidate_failed"),
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "qwen3_invalidate_failed",
                "message": "Voice prompt removal failed",
                "engine_id": payload.engine_id,
                "retryable": True,
            },
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "qwen3_invalidate_failed",
                "message": "Voice prompt removal failed",
                "engine_id": payload.engine_id,
                "retryable": True,
            },
        )
    return result


@router.post("/tts/synthesize")
async def synthesize(request: Request, payload: TtsSynthesizeRequest) -> dict[str, Any]:
    target_engine = _target_engine(request, payload)
    reference_audio = _decode_reference_audio(payload.reference_audio_b64)
    manager = _manager_from_app(request)

    try:
        synthesis_input = TtsSynthesisInput(
            text=payload.text,
            reference_audio=reference_audio,
            reference_audio_content_type=payload.reference_audio_content_type,
            reference_transcript=payload.reference_transcript,
            speech_speed=payload.speech_speed,
            voxcpm2_cloning_mode=payload.voxcpm2_cloning_mode,
            voxcpm2_style_prompt=payload.voxcpm2_style_prompt,
            voxcpm2_cfg_value=payload.voxcpm2_cfg_value,
            voxcpm2_inference_timesteps=payload.voxcpm2_inference_timesteps,
            voxcpm2_normalize=payload.voxcpm2_normalize,
            voxcpm2_denoise=payload.voxcpm2_denoise,
        )
        if target_engine == "qwen3_1_7b":
            transcript = str(payload.reference_transcript or "")
            if not transcript.strip():
                raise Qwen3ValidationError(
                    "Qwen3 reference transcript is required",
                    code="qwen3_transcript_required",
                )
            prepare = getattr(manager, "prepare_tts_engine", None)
            if not callable(prepare):
                raise Qwen3PromptError(
                    "Qwen3 voice preparation is unavailable",
                    code="qwen3_prompt_failed",
                )
            await prepare(
                target_engine,
                voice_key=payload.voice_id,
                reference_audio=reference_audio,
                reference_transcript=transcript,
            )
            adapter = manager.tts_adapters[target_engine]
            result = await asyncio.to_thread(
                _collect_qwen_preview,
                adapter,
                synthesis_input,
                payload.voice_id,
            )
        else:
            await asyncio.to_thread(manager.switch_tts_engine, target_engine)
            adapter = manager.tts_adapters[target_engine]
            result = await asyncio.to_thread(adapter.synthesize, synthesis_input)
        if not result.wav_bytes:
            raise ValueError("synthesis returned empty audio")
    except HTTPException:
        raise
    except Qwen3WorkerError as exc:
        logger.warning(
            "[rayme-tts] synthesize.qwen_failed engine=%s code=%s",
            target_engine,
            exc.code,
        )
        _mark_engine_unavailable(manager, target_engine, failure=exc)
        raise HTTPException(
            status_code=_qwen_http_status(exc),
            detail=_qwen_error_detail(exc, target_engine),
        ) from exc
    except Exception as exc:
        logger.exception(
            "[rayme-tts] synthesize.failed engine=%s exc=%s",
            target_engine,
            exc.__class__.__name__,
        )
        _mark_engine_unavailable(manager, target_engine)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "tts_failed",
                "message": "Synthesis failed",
                "engine_id": target_engine,
            },
        ) from exc

    return {
        "engine_id": target_engine,
        "voice_id": payload.voice_id,
        "content_type": "audio/wav",
        "audio_base64": base64.b64encode(result.wav_bytes).decode("ascii"),
        "sample_rate": result.sample_rate,
        "duration_ms": result.duration_ms,
        "warnings": result.warning_codes or result.warnings,
    }


def _target_engine(request: Request, payload: TtsSynthesizeRequest) -> str:
    if payload.use_default_engine:
        return payload.engine_id or _settings_from_app(request).default_tts_engine
    if not payload.engine_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_tts_request", "message": "engine_id is required"},
        )
    return payload.engine_id


def _decode_reference_audio(reference_audio_b64: str) -> bytes:
    try:
        decoded = base64.b64decode(reference_audio_b64, validate=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_tts_request",
                "message": "reference_audio_b64 must be valid base64",
            },
        ) from exc
    if not decoded:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_tts_request",
                "message": "reference_audio_b64 must not be empty",
            },
        )
    if len(decoded) > MAX_REFERENCE_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "invalid_tts_request",
                "message": "reference audio is too large",
            },
        )
    return decoded


def _settings_from_app(request: Request) -> AiBackendSettings:
    manager = getattr(request.app.state, "model_manager", None)
    settings = getattr(manager, "settings", None)
    if isinstance(settings, AiBackendSettings):
        return settings
    return AiBackendSettings()


def _manager_from_app(request: Request) -> Any:
    manager = getattr(request.app.state, "model_manager", None)
    if manager is None:
        manager = ModelManager(AiBackendSettings())
        manager.startup()
        request.app.state.model_manager = manager
    return manager


def _mark_engine_unavailable(
    manager: Any,
    engine_id: str,
    *,
    failure: Exception | None = None,
) -> None:
    if failure is not None and not bool(
        getattr(failure, "marks_engine_unavailable", False)
    ):
        return
    contain = getattr(manager, "_contain_qwen_runtime_failure", None)
    if engine_id == "qwen3_1_7b" and callable(contain):
        contain(engine_id)
        return
    statuses = getattr(manager, "_statuses", {})
    if isinstance(statuses, dict) and engine_id not in statuses:
        return
    marker = getattr(manager, "_mark_unavailable", None)
    if callable(marker):
        try:
            marker(engine_id, "engine synthesis failed")
        except Exception:
            logger.warning(
                "[rayme-tts] mark_unavailable.failed engine=%s",
                engine_id,
                exc_info=True,
            )


def _qwen_http_status(error: Qwen3WorkerError) -> int:
    if isinstance(error, (Qwen3ValidationError, Qwen3PromptError)):
        return 422
    if isinstance(error, Qwen3GenerationCeilingError):
        return 422
    return 502


def _qwen_error_detail(
    error: Qwen3WorkerError,
    engine_id: str,
) -> dict[str, str]:
    messages = {
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
        "qwen3_worker_unavailable": "Qwen3-TTS runtime is unavailable",
        "qwen3_generation_failed": "Qwen3-TTS runtime failed",
        "qwen3_load_failed": "Qwen3-TTS runtime failed to load",
    }
    return {
        "code": error.code,
        "message": messages.get(error.code, "Qwen3-TTS request failed"),
        "engine_id": engine_id,
    }


def _collect_qwen_preview(
    adapter: Any,
    synthesis_input: TtsSynthesisInput,
    voice_key: str,
) -> TtsSynthesisOutput:
    import numpy as np
    import soundfile as sf

    chunks = list(
        adapter.stream(
            synthesis_input,
            request_id=f"preview-{uuid.uuid4().hex}",
            voice_key=voice_key,
        )
    )
    if not chunks:
        raise Qwen3PromptError(
            "Qwen3 preview produced no audio",
            code="qwen3_no_audio",
        )
    arrays: list[Any] = []
    for chunk in chunks:
        audio, sample_rate = sf.read(
            BytesIO(bytes(chunk.wav_bytes)),
            dtype="float32",
            always_2d=False,
        )
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if int(sample_rate) != 24000 or samples.size == 0:
            raise Qwen3PromptError(
                "Qwen3 preview audio is invalid",
                code="qwen3_no_audio",
            )
        arrays.append(samples)
    combined = np.concatenate(arrays)
    output = BytesIO()
    sf.write(output, combined, 24000, format="WAV")
    return TtsSynthesisOutput(
        engine_id="qwen3_1_7b",
        wav_bytes=output.getvalue(),
        sample_rate=24000,
        duration_ms=round(combined.size * 1000.0 / 24000, 3),
    )
