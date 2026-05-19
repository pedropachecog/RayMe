"""Message action API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.llm_stream import ChatCompletionSettings
from app.domain.message_actions import (
    InvalidMessageActionError,
    MessageActionNotFoundError,
    SqlAlchemyMessageActionRepository,
    continue_ai_turn,
    create_swipe_alternate,
    edit_message_and_mark_stale,
    keep_stale_after_message,
    regenerate_ai_turn,
    select_message_alternate,
    truncate_stale_after_message,
)
from app.domain.settings_service import SettingsService
from app.domain.thread_service import ThreadNotFoundError
from app.storage.models import ThreadMessageShape
from app.storage.session import get_session

router = APIRouter(prefix="/api/messages", tags=["messages"])


class MessageEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def strip_non_empty_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "content is required"
            raise ValueError(msg)
        return stripped


class MessageSwipeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alternate_id: str | None = Field(default=None, min_length=1, max_length=64)


class MessageContinueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    composer_text: str = Field(default="", max_length=20000)

    @field_validator("composer_text")
    @classmethod
    def strip_composer_text(cls, value: str) -> str:
        return value.strip()


async def get_message_action_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_message_action_runtime_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_message_completion_client() -> object | None:
    return None


@router.post("/{message_id}/regenerate")
async def regenerate_message(
    message_id: str,
    session: AsyncSession = Depends(get_message_action_session),
    runtime_settings: Settings = Depends(get_message_action_runtime_settings),
    completion_client: object | None = Depends(get_message_completion_client),
) -> dict[str, Any]:
    repository = SqlAlchemyMessageActionRepository(session)
    try:
        message = await regenerate_ai_turn(
            message_id,
            repository=repository,
            settings=await _completion_settings(session, runtime_settings),
            completion_client=completion_client,
        )
    except (MessageActionNotFoundError, ThreadNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    except InvalidMessageActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _message_response(message)


@router.post("/{message_id}/swipes")
async def swipe_message(
    message_id: str,
    payload: MessageSwipeRequest | None = None,
    session: AsyncSession = Depends(get_message_action_session),
    runtime_settings: Settings = Depends(get_message_action_runtime_settings),
    completion_client: object | None = Depends(get_message_completion_client),
) -> dict[str, Any]:
    repository = SqlAlchemyMessageActionRepository(session)
    try:
        if payload is not None and payload.alternate_id is not None:
            message = await select_message_alternate(
                message_id,
                payload.alternate_id,
                repository=repository,
            )
        else:
            message = await create_swipe_alternate(
                message_id,
                repository=repository,
                settings=await _completion_settings(session, runtime_settings),
                completion_client=completion_client,
            )
    except (MessageActionNotFoundError, ThreadNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    except InvalidMessageActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _message_response(message)


@router.patch("/{message_id}")
async def edit_message(
    message_id: str,
    payload: MessageEditRequest,
    session: AsyncSession = Depends(get_message_action_session),
) -> dict[str, Any]:
    repository = SqlAlchemyMessageActionRepository(session)
    try:
        message = await edit_message_and_mark_stale(
            message_id,
            payload.content,
            repository=repository,
        )
    except (MessageActionNotFoundError, ThreadNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    return _message_response(message)


@router.post("/{message_id}/truncate-stale")
async def truncate_stale_messages(
    message_id: str,
    session: AsyncSession = Depends(get_message_action_session),
) -> dict[str, Any]:
    repository = SqlAlchemyMessageActionRepository(session)
    try:
        messages = await truncate_stale_after_message(message_id, repository=repository)
    except (MessageActionNotFoundError, ThreadNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    return {"messages": [_message_response(message) for message in messages]}


@router.post("/{message_id}/keep-stale")
async def keep_stale_messages(
    message_id: str,
    session: AsyncSession = Depends(get_message_action_session),
) -> dict[str, Any]:
    repository = SqlAlchemyMessageActionRepository(session)
    try:
        message = await keep_stale_after_message(message_id, repository=repository)
    except (MessageActionNotFoundError, ThreadNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    return _message_response(message)


@router.post("/{message_id}/continue")
async def continue_message(
    message_id: str,
    payload: MessageContinueRequest,
    session: AsyncSession = Depends(get_message_action_session),
    runtime_settings: Settings = Depends(get_message_action_runtime_settings),
    completion_client: object | None = Depends(get_message_completion_client),
) -> dict[str, Any]:
    repository = SqlAlchemyMessageActionRepository(session)
    try:
        message = await continue_ai_turn(
            message_id,
            payload.composer_text,
            repository=repository,
            settings=await _completion_settings(session, runtime_settings),
            completion_client=completion_client,
        )
    except (MessageActionNotFoundError, ThreadNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    except InvalidMessageActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _message_response(message)


async def _completion_settings(
    session: AsyncSession,
    runtime_settings: Settings,
) -> ChatCompletionSettings:
    endpoint_settings = await SettingsService(session, runtime_settings).read()
    return ChatCompletionSettings(
        base_url=endpoint_settings.llm_base_url,
        api_key=endpoint_settings.llm_api_key,
        model=endpoint_settings.llm_model,
        disable_thinking=endpoint_settings.llm_disable_thinking,
    )


def _message_response(message: ThreadMessageShape) -> dict[str, Any]:
    return message.to_dict()


__all__ = [
    "MessageContinueRequest",
    "MessageEditRequest",
    "MessageSwipeRequest",
    "get_message_action_runtime_settings",
    "get_message_action_session",
    "get_message_completion_client",
    "router",
]
