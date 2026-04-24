"""Voice Lab and Voice Library API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.voice_assets import VoiceSampleValidationError
from app.domain.voice_service import (
    VoiceAssetNotFoundError,
    VoiceNotFoundError,
    VoiceReferencedError,
    VoiceService,
)
from app.storage.session import SERVER_ROOT, get_session

router = APIRouter(prefix="/api/voices", tags=["voices"])
DEFAULT_VOICE_BLOB_DIR = SERVER_ROOT / "data" / "blobs" / "voices"


class VoiceSave(BaseModel):
    asset_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    default_engine: str = Field(min_length=1, max_length=80)
    reference_transcript: str | None = None


class VoicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_engine: str | None = Field(default=None, min_length=1, max_length=80)
    reference_transcript: str | None = None


class VoicePreview(BaseModel):
    asset_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    default_engine: str | None = Field(default=None, max_length=80)
    reference_transcript: str | None = None
    preview_text: str | None = None
    use_default_engine: bool = True
    engine: str | None = Field(default=None, max_length=80)


class VoiceTestPlay(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    use_default_engine: bool = True
    engine: str | None = Field(default=None, max_length=80)


class PassthroughVoiceProcessor:
    async def transcribe(self, **_: Any) -> dict[str, str | float]:
        return {"transcript": "", "language": "en", "confidence": 0.0}

    async def synthesize_preview(self, **_: Any) -> dict[str, str]:
        return {"preview_id": "", "preview_url": ""}

    async def test_play(self, **_: Any) -> dict[str, str]:
        return {"audio_url": ""}


async def get_voice_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_voice_blob_dir() -> Path:
    return DEFAULT_VOICE_BLOB_DIR


def get_voice_processor() -> object:
    return PassthroughVoiceProcessor()


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


@router.post("/preview")
async def preview_voice(
    payload: VoicePreview,
    service: VoiceService = Depends(get_voice_service),
) -> dict[str, Any]:
    payload_state = payload.model_dump()
    try:
        return await service.preview_voice(payload_state)
    except VoiceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice asset not found") from exc
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


__all__ = [
    "DEFAULT_VOICE_BLOB_DIR",
    "get_voice_blob_dir",
    "get_voice_processor",
    "get_voice_service",
    "get_voice_session",
    "router",
]
