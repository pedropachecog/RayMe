"""Thread management API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.thread_service import (
    AlternateGreetingIndexError,
    CharacterUnavailableError,
    ThreadNotFoundError,
    ThreadService,
)
from app.storage.session import get_session

router = APIRouter(prefix="/api/threads", tags=["threads"])


class ThreadCreate(BaseModel):
    character_id: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=240)
    alternate_greeting_index: int | None = None


class ThreadRename(BaseModel):
    title: str = Field(min_length=1, max_length=240)


async def get_thread_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_thread_service(
    session: AsyncSession = Depends(get_thread_session),
) -> ThreadService:
    return ThreadService(session)


@router.get("")
async def list_threads(
    service: ThreadService = Depends(get_thread_service),
) -> dict[str, Any]:
    return {"items": await service.list_threads()}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadCreate,
    service: ThreadService = Depends(get_thread_service),
) -> dict[str, str]:
    try:
        return await service.create_thread(
            character_id=payload.character_id,
            title=payload.title,
            alternate_greeting_index=payload.alternate_greeting_index,
        )
    except CharacterUnavailableError as exc:
        raise HTTPException(status_code=404, detail="Character not found") from exc
    except AlternateGreetingIndexError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc


@router.get("/{thread_id}")
async def read_thread(
    thread_id: str,
    service: ThreadService = Depends(get_thread_service),
) -> dict[str, Any]:
    try:
        return await service.get_thread_detail(thread_id)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc


@router.patch("/{thread_id}")
async def rename_thread(
    thread_id: str,
    payload: ThreadRename,
    service: ThreadService = Depends(get_thread_service),
) -> dict[str, Any]:
    try:
        return await service.rename_thread(thread_id, payload.title)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str,
    service: ThreadService = Depends(get_thread_service),
) -> dict[str, Any]:
    try:
        return await service.delete_thread(thread_id)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc


__all__ = [
    "get_thread_service",
    "get_thread_session",
    "router",
]
