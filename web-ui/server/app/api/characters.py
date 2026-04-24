"""Character CRUD, import/export, and portrait API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.character_service import CharacterNotFoundError, CharacterService
from app.domain.portraits import PortraitValidationError
from app.storage.session import SERVER_ROOT, get_session

router = APIRouter(prefix="/api/characters", tags=["characters"])
DEFAULT_PORTRAIT_BLOB_DIR = SERVER_ROOT / "data" / "blobs" / "portraits"


class CharacterWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_mes: str | None = None
    mes_example: str | None = None
    system_prompt: str | None = None
    creator_notes: str | None = None
    character_notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    alternate_greetings: list[str] = Field(default_factory=list)
    post_history_instructions: str | None = None
    creator: str | None = None
    character_version: str | None = None
    raw_source_json: dict[str, Any] | None = None
    lorebook_json: dict[str, Any] | list[Any] | None = None


async def get_character_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_portrait_blob_dir() -> Path:
    return DEFAULT_PORTRAIT_BLOB_DIR


def get_character_service(
    session: AsyncSession = Depends(get_character_session),
    portrait_blob_dir: Path = Depends(get_portrait_blob_dir),
) -> CharacterService:
    return CharacterService(session, portrait_blob_dir)


@router.get("")
async def list_characters(
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    return {"items": await service.list_characters()}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_character(
    payload: CharacterWrite,
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    return await service.create_character(payload.model_dump())


@router.get("/{character_id}")
async def read_character(
    character_id: str,
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    try:
        return await service.get_character_response(character_id)
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc


@router.put("/{character_id}")
async def update_character(
    character_id: str,
    payload: CharacterWrite,
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    try:
        return await service.update_character(character_id, payload.model_dump())
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc


@router.patch("/{character_id}")
async def patch_character(
    character_id: str,
    payload: CharacterWrite,
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    return await update_character(character_id, payload, service)


@router.delete("/{character_id}")
async def delete_character(
    character_id: str,
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    try:
        result = await service.delete_character(character_id)
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc
    return {
        "character_id": result.character_id,
        "deleted_at": result.deleted_at,
        "preserved_thread_ids": list(result.preserved_thread_ids),
        "strategy": result.strategy,
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_character(
    file: UploadFile = File(...),
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    content = await file.read()
    try:
        return await service.import_character(
            filename=file.filename or "",
            content=content,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{character_id}/export-v2")
async def export_character_v2(
    character_id: str,
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    try:
        return await service.export_character_v2(character_id)
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc


@router.put("/{character_id}/portrait")
async def replace_portrait(
    character_id: str,
    file: UploadFile = File(...),
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    content = await file.read()
    try:
        return await service.replace_portrait(
            character_id,
            filename=file.filename or "",
            content=content,
        )
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc
    except PortraitValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{character_id}/portrait")
async def delete_portrait(
    character_id: str,
    service: CharacterService = Depends(get_character_service),
) -> dict[str, Any]:
    try:
        return await service.delete_portrait(character_id)
    except CharacterNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc


__all__ = [
    "DEFAULT_PORTRAIT_BLOB_DIR",
    "get_character_service",
    "get_character_session",
    "get_portrait_blob_dir",
    "router",
]
