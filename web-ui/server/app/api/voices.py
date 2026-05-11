"""Voice Lab and Voice Library API routes."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.ai_backend_client import AiBackendClient, AiBackendClientError
from app.domain.voice_assets import VoiceSampleValidationError
from app.domain.voice_service import (
    VoiceAssetNotFoundError,
    VoiceMetadataValidationError,
    VoiceNotFoundError,
    VoiceReferencedError,
    VoiceService,
    VoiceSynthesisFailedError,
)
from app.storage.session import SERVER_ROOT, get_session

router = APIRouter(prefix="/api/voices", tags=["voices"])
DEFAULT_VOICE_BLOB_DIR = SERVER_ROOT / "data" / "blobs" / "voices"


class VoiceSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    default_engine: str = Field(min_length=1, max_length=80)
    reference_transcript: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_engine: str | None = Field(default=None, min_length=1, max_length=80)
    reference_transcript: str | None = None
    metadata: dict[str, Any] | None = None


class VoicePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    default_engine: str | None = Field(default=None, max_length=80)
    reference_transcript: str | None = None
    preview_text: str | None = None
    use_default_engine: bool = True
    engine: str | None = Field(default=None, max_length=80)
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceTestPlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    use_default_engine: bool = True
    engine: str | None = Field(default=None, max_length=80)
    speech_speed: float = Field(default=1.0, ge=0.5, le=1.5)


class AiBackendVoiceProcessor:
    def __init__(self, client: AiBackendClient, base_url: str) -> None:
        self.client = client
        self.base_url = base_url

    async def transcribe(
        self,
        *,
        asset_id: str,
        content: bytes,
        content_type: str | None,
    ) -> dict[str, Any]:
        result = await self.client.transcribe_sample(
            self.base_url,
            content,
            _processor_filename(asset_id, content_type),
            content_type or "application/octet-stream",
        )
        return result.model_dump()

    async def synthesize_preview(self, **payload: Any) -> dict[str, Any]:
        return await self._synthesize(kind="preview", **payload)

    async def test_play(self, **payload: Any) -> dict[str, Any]:
        return await self._synthesize(kind="test_play", **payload)

    async def _synthesize(self, *, kind: str, **payload: Any) -> dict[str, Any]:
        try:
            result = await self.client.synthesize(self.base_url, _synthesis_payload(kind, payload))
        except AiBackendClientError as exc:
            return {"status": "tts_failed", "error": exc.to_public_dict()}
        response = result.model_dump()
        response["status"] = "ok"
        return response


async def get_voice_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_voice_blob_dir() -> Path:
    return DEFAULT_VOICE_BLOB_DIR


def get_runtime_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_voice_processor(settings: Settings = Depends(get_runtime_settings)) -> object:
    return AiBackendVoiceProcessor(
        AiBackendClient(synthesis_timeout=settings.ai_backend_synthesis_timeout_seconds),
        settings.ai_backend_base_url,
    )


def get_voice_service(
    session: AsyncSession = Depends(get_voice_session),
    voice_blob_dir: Path = Depends(get_voice_blob_dir),
    processor: object = Depends(get_voice_processor),
) -> VoiceService:
    return VoiceService(session, voice_blob_dir, processor)


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def upload_voice_asset(
    file: UploadFile = File(...),
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    content = await file.read()
    try:
        return await service.upload_sample(
            filename=file.filename or "",
            content_type=file.content_type,
            content=content,
        )
    except VoiceSampleValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/sample")
async def read_voice_sample(asset_id: str, service: VoiceService = Depends(get_voice_service)):
    try:
        sample = await service.sample_blob(asset_id)
    except VoiceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice asset not found") from exc
    return FileResponse(
        sample.path,
        media_type=sample.content_type,
        filename=sample.storage_path,
    )


@router.post("/assets/{asset_id}/transcribe")
async def transcribe_voice_asset(
    asset_id: str,
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    try:
        return await service.transcribe_asset(asset_id)
    except VoiceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice asset not found") from exc
    except AiBackendClientError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "error": exc.to_public_dict(),
                "reference_transcript": "",
                "reference_transcript_editable": True,
                "retry_allowed": True,
                "manual_transcript_allowed": True,
            },
        )


@router.post("/preview")
async def preview_voice(
    payload: VoicePreview,
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    payload_state = payload.model_dump()
    if "metadata" not in payload.model_fields_set:
        payload_state.pop("metadata", None)
    try:
        return await service.preview_voice(payload_state)
    except VoiceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice asset not found") from exc
    except VoiceMetadataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        return JSONResponse(
            status_code=502,
            content={
                "error": {"code": "preview_failed", "message": "Preview synthesis failed"},
                "payload_state": payload_state,
            },
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def save_voice(
    payload: VoiceSave,
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    try:
        return await service.save_voice(payload.model_dump())
    except VoiceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice asset not found") from exc
    except VoiceMetadataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
async def list_voices(service: VoiceService = Depends(get_voice_service)) -> dict[str, Any]:
    return {"items": await service.list_voices()}


@router.get("/{voice_id}")
async def read_voice(voice_id: str, service: VoiceService = Depends(get_voice_service)) -> dict[str, Any]:
    try:
        return await service.get_voice(voice_id)
    except VoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc


@router.patch("/{voice_id}")
async def patch_voice(
    voice_id: str,
    payload: VoicePatch,
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    try:
        return await service.rename_voice(voice_id, payload.model_dump(exclude_unset=True))
    except VoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    except VoiceMetadataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{voice_id}")
async def delete_voice(
    voice_id: str,
    force: bool = Query(default=False),
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    try:
        return await service.delete_voice(voice_id, force=force)
    except VoiceReferencedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "Voice is referenced", "referents": exc.referents},
        ) from exc
    except VoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc


@router.post("/{voice_id}/test-play")
async def test_play_voice(
    voice_id: str,
    payload: VoiceTestPlay,
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    try:
        return await service.test_play_voice(voice_id, payload.model_dump())
    except VoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice not found") from exc
    except VoiceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice asset not found") from exc
    except VoiceMetadataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VoiceSynthesisFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "Voice test-play did not produce generated audio"},
        ) from exc


__all__ = [
    "AiBackendVoiceProcessor",
    "DEFAULT_VOICE_BLOB_DIR",
    "get_runtime_settings",
    "get_voice_blob_dir",
    "get_voice_processor",
    "get_voice_service",
    "get_voice_session",
    "router",
]


def _processor_filename(asset_id: str, content_type: str | None) -> str:
    extension_by_type = {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
    }
    return f"{asset_id}{extension_by_type.get(content_type or '', '.bin')}"


def _synthesis_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content")
    audio_base64 = base64.b64encode(content).decode("ascii") if isinstance(content, bytes) else None
    engine_id = payload.get("engine") or payload.get("default_engine")
    return {
        "kind": kind,
        "text": payload.get("text") or payload.get("preview_text") or "",
        "engine_id": engine_id,
        "use_default_engine": payload.get("use_default_engine", True),
        "reference_transcript": payload.get("reference_transcript"),
        "reference_audio_base64": audio_base64,
        "reference_audio_content_type": payload.get("content_type"),
        "voice_id": payload.get("voice_id") or payload.get("asset_id"),
        "asset_id": payload.get("asset_id"),
        "speech_speed": payload.get("speech_speed", 1.0),
    }
