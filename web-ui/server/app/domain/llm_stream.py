"""OpenAI-compatible chat completion streaming contract."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.domain.prompt_builder import PromptContextMessage
from app.storage.models import ThreadMessageShape

SSE_DATA_PREFIX = "data: "
TOKEN_EVENT_TYPE = "token"
DONE_EVENT_TYPE = "done"
ERROR_EVENT_TYPE = "error"


@dataclass(frozen=True, slots=True)
class ChatCompletionSettings:
    """Server-side settings used for OpenAI-compatible chat completion calls."""

    base_url: str
    model: str
    api_key: str | None = None


class TokenEvent(TypedDict):
    type: Literal["token"]
    text: str


class DoneEvent(TypedDict):
    type: Literal["done"]
    message: dict[str, Any]


class ErrorEvent(TypedDict):
    type: Literal["error"]
    message: str


PersistFinalMessage = Callable[[str], Awaitable[ThreadMessageShape]]


def encode_sse_event(event: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(event), separators=(",", ":"))
    return f"{SSE_DATA_PREFIX}{payload}\n\n"


def token_event(text: str) -> TokenEvent:
    return {"type": TOKEN_EVENT_TYPE, "text": text}


def done_event(message: ThreadMessageShape) -> DoneEvent:
    return {"type": DONE_EVENT_TYPE, "message": message.to_dict()}


def error_event(message: str) -> ErrorEvent:
    return {"type": ERROR_EVENT_TYPE, "message": message}


async def stream_chat_completion(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None = None,
    persist_final: PersistFinalMessage | None = None,
) -> AsyncIterator[str]:
    """Yield SSE token events and a final done event with a full ThreadMessageShape."""

    raise NotImplementedError


async def collect_chat_completion(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None = None,
) -> str:
    """Collect a complete assistant response using only server-side settings."""

    raise NotImplementedError


__all__ = [
    "ChatCompletionSettings",
    "DONE_EVENT_TYPE",
    "DoneEvent",
    "ERROR_EVENT_TYPE",
    "ErrorEvent",
    "PersistFinalMessage",
    "SSE_DATA_PREFIX",
    "TOKEN_EVENT_TYPE",
    "ThreadMessageShape",
    "TokenEvent",
    "collect_chat_completion",
    "done_event",
    "encode_sse_event",
    "error_event",
    "stream_chat_completion",
    "token_event",
]
