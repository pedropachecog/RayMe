"""OpenAI-compatible chat completion streaming contract."""

from __future__ import annotations

import asyncio
import inspect
import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

import httpx
from openai import AsyncOpenAI

from app.domain.prompt_builder import PromptContextMessage
from app.domain.refusal_guard import (
    LLMEmptyOutput,
    LLMGuardError,
    LLMRefusalExhausted,
    PrefixRefusalGuard,
)
from app.storage.models import ThreadMessageShape

SSE_DATA_PREFIX = "data: "
TOKEN_EVENT_TYPE = "token"
DONE_EVENT_TYPE = "done"
ERROR_EVENT_TYPE = "error"
CHAT_COMPLETION_SEED_LIMIT = 2**31 - 1
MAX_SEMANTIC_ATTEMPTS = 3
REFUSAL_RETRY_CORRECTION = (
    "The prior draft broke character. Respond only with the in-world reply."
)


@dataclass(frozen=True, slots=True)
class ChatCompletionSettings:
    """Server-side settings used for OpenAI-compatible chat completion calls."""

    base_url: str
    model: str
    api_key: str | None = None
    disable_thinking: bool = False


class TokenEvent(TypedDict):
    type: Literal["token"]
    text: str


class DoneEvent(TypedDict):
    type: Literal["done"]
    message: dict[str, Any]


class ErrorEvent(TypedDict):
    type: Literal["error"]
    code: str
    message: str


PersistFinalMessage = Callable[[str], Awaitable[ThreadMessageShape]]
SeedFactory = Callable[[], int]


def encode_sse_event(event: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(event), separators=(",", ":"))
    return f"{SSE_DATA_PREFIX}{payload}\n\n"


def token_event(text: str) -> TokenEvent:
    return {"type": TOKEN_EVENT_TYPE, "text": text}


def done_event(message: ThreadMessageShape) -> DoneEvent:
    return {"type": DONE_EVENT_TYPE, "message": message.to_dict()}


def error_event(*, code: str, message: str) -> ErrorEvent:
    return {"type": ERROR_EVENT_TYPE, "code": code, "message": message}


async def stream_chat_completion(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None = None,
    persist_final: PersistFinalMessage | None = None,
    seed_factory: SeedFactory | None = None,
) -> AsyncIterator[str]:
    """Yield SSE token events and a final done event with a full ThreadMessageShape."""

    collected: list[str] = []
    try:
        async for token in _stream_text_tokens(
            settings,
            messages,
            client=client,
            seed_factory=seed_factory,
        ):
            collected.append(token)
            yield encode_sse_event(token_event(token))

        if persist_final is not None:
            message = await persist_final("".join(collected))
            yield encode_sse_event(done_event(message))
    except LLMGuardError as exc:
        yield encode_sse_event(error_event(code=exc.code, message=exc.message))
    except Exception:
        yield encode_sse_event(
            error_event(code="llm_stream_failed", message="LLM stream failed")
        )


async def collect_chat_completion(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None = None,
    seed_factory: SeedFactory | None = None,
) -> str:
    """Collect a complete assistant response using only server-side settings."""

    return "".join(
        [
            token
            async for token in _stream_text_tokens(
                settings,
                messages,
                client=client,
                seed_factory=seed_factory,
            )
        ]
    )


async def _stream_text_tokens(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object | None,
    seed_factory: SeedFactory | None = None,
) -> AsyncIterator[str]:
    completion_client = client or _openai_client(settings)
    owns_client = client is None
    draw_seed = seed_factory or _random_chat_completion_seed
    used_seeds: set[int] = set()
    try:
        for attempt in range(1, MAX_SEMANTIC_ATTEMPTS + 1):
            attempt_messages = _messages_for_attempt(messages, attempt=attempt)
            seed = _distinct_seed(draw_seed, used_seeds)
            guard = PrefixRefusalGuard()
            emitted_nonblank = False
            refused = False
            raw_tokens = _stream_raw_text_tokens(
                settings,
                attempt_messages,
                client=completion_client,
                seed=seed,
                attempt=attempt,
            )
            try:
                async for token in raw_tokens:
                    decision = guard.feed(token)
                    if decision.refused:
                        refused = True
                        break
                    for accepted in decision.released_text:
                        emitted_nonblank = emitted_nonblank or bool(accepted.strip())
                        yield accepted

                if not refused:
                    final = guard.finish()
                    refused = final.refused
                    for accepted in final.released_text:
                        emitted_nonblank = emitted_nonblank or bool(accepted.strip())
                        yield accepted
            except asyncio.CancelledError:
                raise
            finally:
                await raw_tokens.aclose()

            if refused:
                continue
            if not emitted_nonblank:
                raise LLMEmptyOutput()
            return
        raise LLMRefusalExhausted()
    finally:
        if owns_client:
            await _close_async_resource(completion_client)


async def _stream_raw_text_tokens(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    client: object,
    seed: int,
    attempt: int,
) -> AsyncIterator[str]:
    custom_stream = getattr(client, "stream_chat_completion_tokens", None)
    if callable(custom_stream):
        custom_iterator = _call_custom_stream(
            custom_stream,
            settings,
            messages,
            seed=seed,
            attempt=attempt,
        )
        try:
            async for token in custom_iterator:
                if token:
                    yield str(token)
        finally:
            await _close_async_resource(custom_iterator)
        return

    create = client.chat.completions.create
    request_kwargs: dict[str, Any] = {
        "model": settings.model,
        "messages": _prepare_messages(settings, messages),
        "seed": seed,
        "stream": True,
    }
    if _should_disable_thinking(settings):
        request_kwargs["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": False},
        }
    stream = await create(**request_kwargs)
    try:
        async for chunk in stream:
            token = _chunk_delta_text(chunk)
            if token:
                yield token
    finally:
        await _close_async_resource(stream)


def _openai_client(settings: ChatCompletionSettings) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key or "",
        max_retries=0,
        timeout=httpx.Timeout(90.0, connect=5.0, read=30.0, write=10.0, pool=5.0),
    )


def _random_chat_completion_seed() -> int:
    return secrets.randbelow(CHAT_COMPLETION_SEED_LIMIT + 1)


def _distinct_seed(seed_factory: SeedFactory, used_seeds: set[int]) -> int:
    seed = seed_factory()
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("chat completion seed factory must return an integer")
    if not 0 <= seed <= CHAT_COMPLETION_SEED_LIMIT:
        raise ValueError("chat completion seed is outside the supported range")
    while seed in used_seeds:
        seed = (seed + 1) % (CHAT_COMPLETION_SEED_LIMIT + 1)
    used_seeds.add(seed)
    return seed


def _messages_for_attempt(
    messages: Sequence[PromptContextMessage],
    *,
    attempt: int,
) -> list[PromptContextMessage]:
    prepared = [dict(message) for message in messages]
    if attempt > 1:
        prepared.append({"role": "user", "content": REFUSAL_RETRY_CORRECTION})
    return prepared


def _call_custom_stream(
    custom_stream: Callable[..., Any],
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
    *,
    seed: int,
    attempt: int,
) -> AsyncIterator[str]:
    parameters = inspect.signature(custom_stream).parameters.values()
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
    )
    names = {parameter.name for parameter in parameters}
    kwargs: dict[str, Any] = {}
    if accepts_kwargs or "seed" in names:
        kwargs["seed"] = seed
    if accepts_kwargs or "attempt" in names:
        kwargs["attempt"] = attempt
    return custom_stream(settings, messages, **kwargs)


async def _close_async_resource(resource: object) -> None:
    close = getattr(resource, "aclose", None)
    if not callable(close):
        close = getattr(resource, "close", None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _should_disable_thinking(settings: ChatCompletionSettings) -> bool:
    return settings.disable_thinking and "qwen" in settings.model.lower()


def _prepare_messages(
    settings: ChatCompletionSettings,
    messages: Sequence[PromptContextMessage],
) -> list[dict[str, Any]]:
    prepared = [dict(message) for message in messages]
    if not _should_disable_thinking(settings):
        return prepared
    for message in reversed(prepared):
        if message.get("role") == "user":
            content = str(message.get("content") or "").rstrip()
            if "/no_think" not in content:
                message["content"] = f"{content}\n\n/no_think" if content else "/no_think"
            break
    return prepared


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
    "CHAT_COMPLETION_SEED_LIMIT",
    "ChatCompletionSettings",
    "DONE_EVENT_TYPE",
    "DoneEvent",
    "ERROR_EVENT_TYPE",
    "ErrorEvent",
    "PersistFinalMessage",
    "REFUSAL_RETRY_CORRECTION",
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
