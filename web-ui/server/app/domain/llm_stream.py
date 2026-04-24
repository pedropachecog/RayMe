"""OpenAI-compatible chat completion streaming contract."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from openai import AsyncOpenAI

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

    collected: list[str] = []
    try:
        async for token in _stream_text_tokens(settings, messages, client=client):
            collected.append(token)
            yield encode_sse_event(token_event(token))

        if persist_final is not None:
            message = await persist_final("".join(collected))
            yield encode_sse_event(done_event(message))
    except Exception:
        yield encode_sse_event(error_event("LLM stream failed"))


async def collect_chat_completion(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None = None,
) -> str:
    """Collect a complete assistant response using only server-side settings."""

    return "".join(
        [
            token
            async for token in _stream_text_tokens(
                settings,
                messages,
                client=client,
            )
        ]
    )


async def _stream_text_tokens(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None,
) -> AsyncIterator[str]:
    completion_client = client or _openai_client(settings)

    custom_stream = getattr(completion_client, "stream_chat_completion_tokens", None)
    if callable(custom_stream):
        async for token in custom_stream(settings, messages):
            if token:
                yield str(token)
        return

    fake_tokens = getattr(completion_client, "tokens", None)
    if fake_tokens is not None:
        requests = getattr(completion_client, "requests", None)
        if isinstance(requests, list):
            requests.append({"settings": settings, "messages": list(messages)})
        for token in fake_tokens:
            if token:
                yield str(token)
        return

    create = completion_client.chat.completions.create
    stream = await create(
        model=settings.model,
        messages=[dict(message) for message in messages],
        stream=True,
    )
    async for chunk in stream:
        token = _chunk_delta_text(chunk)
        if token:
            yield token


def _openai_client(settings: ChatCompletionSettings) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key or "",
    )


def _chunk_delta_text(chunk: object) -> str | None:
    choices = _field(chunk, "choices")
    if not choices:
        return None

    first_choice = choices[0]
    delta = _field(first_choice, "delta")
    if delta is None:
        return None

    content = _field(delta, "content")
    return content if isinstance(content, str) else None


def _field(source: object, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


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
