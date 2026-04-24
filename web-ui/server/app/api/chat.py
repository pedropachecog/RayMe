"""Streaming text chat API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.llm_stream import ChatCompletionSettings, stream_chat_completion
from app.domain.prompt_builder import SqlAlchemyPromptRepository, build_prompt_context
from app.domain.settings_service import SettingsService
from app.domain.thread_service import ThreadNotFoundError, ThreadService, new_message_id
from app.storage.models import Message, MessageAlternateShape, Thread, ThreadMessageShape, utc_now
from app.storage.session import get_session

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatSendRequest(BaseModel):
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


async def get_chat_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_chat_runtime_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_chat_completion_client() -> object | None:
    return None


@router.post("/{thread_id}/send")
async def send_chat_message(
    thread_id: str,
    payload: ChatSendRequest,
    session: AsyncSession = Depends(get_chat_session),
    runtime_settings: Settings = Depends(get_chat_runtime_settings),
    completion_client: object | None = Depends(get_chat_completion_client),
) -> StreamingResponse:
    repository = ChatRepository(session)
    try:
        await repository.append_user_message(thread_id, payload.content)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc

    endpoint_settings = await SettingsService(session, runtime_settings).read()
    completion_settings = ChatCompletionSettings(
        base_url=endpoint_settings.llm_base_url,
        api_key=endpoint_settings.llm_api_key,
        model=endpoint_settings.llm_model,
    )
    prompt_messages = await build_prompt_context(
        thread_id,
        repository=SqlAlchemyPromptRepository(session),
        action="send",
    )

    async def events() -> AsyncIterator[str]:
        async for event in stream_chat_completion(
            completion_settings,
            prompt_messages,
            client=completion_client,
            persist_final=lambda text: repository.append_ai_message(thread_id, text),
        ):
            yield event

    return StreamingResponse(events(), media_type="text/event-stream")


class ChatRepository:
    """Durable message writes used by the streaming chat endpoint."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append_user_message(self, thread_id: str, content_text: str) -> ThreadMessageShape:
        return await self._append_message(
            thread_id,
            content_text,
            message_kind="user_text",
            role="user",
        )

    async def append_ai_message(self, thread_id: str, content_text: str) -> ThreadMessageShape:
        return await self._append_message(
            thread_id,
            content_text,
            message_kind="ai_text",
            role="assistant",
        )

    async def _append_message(
        self,
        thread_id: str,
        content_text: str,
        *,
        message_kind: str,
        role: str,
    ) -> ThreadMessageShape:
        thread = await self._get_thread(thread_id)
        now = utc_now()
        message = Message(
            id=new_message_id(),
            thread_id=thread_id,
            message_kind=message_kind,
            role=role,
            sequence=await self._next_sequence(thread_id),
            content_text=content_text,
            created_at=now,
            updated_at=now,
        )
        self.session.add(message)
        thread.last_message_at = now
        thread.updated_at = now
        await self.session.commit()
        return await self._hydrate_message(thread_id, message.id)

    async def _get_thread(self, thread_id: str) -> Thread:
        result = await self.session.execute(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.deleted_at.is_(None),
            )
        )
        thread = result.scalar_one_or_none()
        if thread is None:
            raise ThreadNotFoundError(thread_id)
        return thread

    async def _next_sequence(self, thread_id: str) -> int:
        result = await self.session.execute(
            select(func.max(Message.sequence)).where(Message.thread_id == thread_id)
        )
        max_sequence = result.scalar_one_or_none()
        return (max_sequence if max_sequence is not None else -1) + 1

    async def _hydrate_message(self, thread_id: str, message_id: str) -> ThreadMessageShape:
        detail = await ThreadService(self.session).get_thread_detail(thread_id)
        for message in detail["messages"]:
            if message["id"] == message_id:
                return _shape_from_thread_message_dict(message)
        raise ThreadNotFoundError(thread_id)


def _shape_from_thread_message_dict(message: dict[str, Any]) -> ThreadMessageShape:
    return ThreadMessageShape(
        id=message["id"],
        thread_id=message["thread_id"],
        message_kind=message["message_kind"],
        role=message["role"],
        sequence=message["sequence"],
        content_text=message["content_text"],
        selected_alternate_id=message["selected_alternate_id"],
        alternates=[
            MessageAlternateShape(
                id=alternate["id"],
                message_id=alternate["message_id"],
                alternate_index=alternate["alternate_index"],
                content_text=alternate["content_text"],
                source_action=alternate["source_action"],
                created_at=alternate["created_at"],
            )
            for alternate in message["alternates"]
        ],
        stale_after_edit=message["stale_after_edit"],
        created_at=message["created_at"],
        updated_at=message["updated_at"],
    )


__all__ = [
    "ChatRepository",
    "ChatSendRequest",
    "get_chat_completion_client",
    "get_chat_runtime_settings",
    "get_chat_session",
    "router",
]
