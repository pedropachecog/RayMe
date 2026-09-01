"""Streaming chat contracts."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_chat_completion_client, get_chat_session
from app.config import Settings
from app.domain.llm_stream import (
    CHAT_COMPLETION_SEED_LIMIT,
    REFUSAL_RETRY_CORRECTION,
    ChatCompletionSettings,
    collect_chat_completion,
    done_event,
    encode_sse_event,
    stream_chat_completion,
    token_event,
)
from app.domain.refusal_guard import LLMEmptyOutput, LLMRefusalExhausted
from app.domain.prompt_profiles import PromptGenerationSettings
from app.domain.settings_service import SETTINGS_KEY
from app.domain.thread_service import ThreadService
from app.main import create_app
from app.storage.models import (
    AppSetting,
    Base,
    Character,
    Message,
    MessageAlternateShape,
    ThreadMessageShape,
)
from app.storage.session import create_engine


class ScriptedStreamingClient:
    def __init__(self, *, fail_after_tokens: bool = False) -> None:
        self.tokens = ["Hel", "lo"]
        self.fail_after_tokens = fail_after_tokens
        self.requests: list[dict[str, object]] = []

    async def stream_chat_completion_tokens(
        self,
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
    ):
        self.requests.append({"settings": settings, "messages": list(messages)})
        for token in self.tokens:
            yield token
        if self.fail_after_tokens:
            raise RuntimeError("upstream disconnected")


class ScriptedOpenAICompletions:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def create(self, **kwargs: object):
        self.requests.append(dict(kwargs))

        async def stream():
            yield {"choices": [{"delta": {"content": "Seeded"}}]}

        return stream()


class ScriptedOpenAIClient:
    def __init__(self) -> None:
        self.chat = type("ScriptedChat", (), {"completions": ScriptedOpenAICompletions()})()


class AttemptScriptClient:
    def __init__(self, scripts: list[list[str | BaseException]]) -> None:
        self.scripts = scripts
        self.requests: list[dict[str, object]] = []
        self.closed_attempts: list[int] = []

    async def stream_chat_completion_tokens(
        self,
        settings: ChatCompletionSettings,
        messages: list[dict[str, str]],
        *,
        seed: int,
        attempt: int,
    ):
        self.requests.append(
            {
                "settings": settings,
                "messages": [dict(message) for message in messages],
                "seed": seed,
                "attempt": attempt,
            }
        )
        try:
            for item in self.scripts[attempt - 1]:
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            self.closed_attempts.append(attempt)


class HeldOpenRetryClient:
    def __init__(self, refusal: str, accepted_prefix: str, accepted_tail: str) -> None:
        self.refusal = refusal
        self.accepted_prefix = accepted_prefix
        self.accepted_tail = accepted_tail
        self.requests: list[dict[str, object]] = []
        self.closed_attempts: list[int] = []
        self.release_accepted = asyncio.Event()
        self.accepted_completed = False

    async def stream_chat_completion_tokens(
        self,
        settings: ChatCompletionSettings,
        messages: list[dict[str, object]],
        *,
        seed: int,
        attempt: int,
    ):
        self.requests.append(
            {
                "settings": settings,
                "messages": [dict(message) for message in messages],
                "seed": seed,
                "attempt": attempt,
            }
        )
        try:
            if attempt == 1:
                yield self.refusal
                return
            yield self.accepted_prefix
            await self.release_accepted.wait()
            yield self.accepted_tail
            self.accepted_completed = True
        finally:
            self.closed_attempts.append(attempt)


@pytest.fixture()
def chat_client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, async_sessionmaker, ScriptedStreamingClient]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-test.sqlite3'}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    scripted_client = ScriptedStreamingClient()
    app = create_app(
        Settings(
            llm_base_url="http://server-llm.local/v1",
            llm_model="server-model",
            llm_api_key="server-secret",
        ),
        static_client_dir=None,
    )

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_chat_session] = override_session
    app.dependency_overrides[get_chat_completion_client] = lambda: scripted_client

    with TestClient(app) as client:
        yield client, sessionmaker, scripted_client

    asyncio.run(engine.dispose())


async def test_llm_stream_yields_tokens_then_persists_final_once() -> None:
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    events = [
        event
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="configured-model",
                api_key="server-secret",
            ),
            [{"role": "user", "content": "Say hello"}],
            client=ScriptedStreamingClient(),
            persist_final=persist_final,
        )
    ]

    assert json.loads(events[0].removeprefix("data: ")) == {"type": "token", "text": "Hel"}
    assert json.loads(events[1].removeprefix("data: ")) == {"type": "token", "text": "lo"}
    assert len(persisted) == 1
    assert json.loads(events[-1].removeprefix("data: "))["type"] == "done"


async def test_collect_chat_completion_uses_same_server_side_stream_settings() -> None:
    scripted_client = ScriptedStreamingClient()
    settings = ChatCompletionSettings(
        base_url="http://llm.local/v1",
        model="configured-model",
        api_key="server-secret",
    )

    text = await collect_chat_completion(
        settings,
        [{"role": "user", "content": "Say hello"}],
        client=scripted_client,
    )

    assert text == "Hello"
    assert scripted_client.requests[0]["settings"] == settings


async def test_stream_and_collect_share_three_attempt_refusal_exhaustion() -> None:
    settings = ChatCompletionSettings(
        base_url="http://llm.local/v1",
        model="configured-model",
    )
    refusal = "I cannot help with that request because policy forbids it."
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        raise AssertionError("refused output must not persist")

    stream_client = AttemptScriptClient([[refusal], [refusal], [refusal]])
    stream_events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            settings,
            [{"role": "user", "content": "Stay in character."}],
            client=stream_client,
            persist_final=persist_final,
            seed_factory=iter((101, 102, 103)).__next__,
        )
    ]

    assert stream_events == [
        {
            "type": "error",
            "code": "llm_refusal_exhausted",
            "message": "AI generation refused after bounded recovery attempts",
        }
    ]
    assert persisted == []
    _assert_three_refusal_requests(stream_client, refusal, (101, 102, 103))

    collect_client = AttemptScriptClient([[refusal], [refusal], [refusal]])
    with pytest.raises(LLMRefusalExhausted) as exc_info:
        await collect_chat_completion(
            settings,
            [{"role": "user", "content": "Stay in character."}],
            client=collect_client,
            seed_factory=iter((201, 202, 203)).__next__,
        )
    assert exc_info.value.code == "llm_refusal_exhausted"
    _assert_three_refusal_requests(collect_client, refusal, (201, 202, 203))


async def test_declarative_guideline_refusal_retries_without_reaching_chat_or_persistence() -> None:
    refusal = "That roleplay violates safety guidelines."
    accepted = "The lantern swung across the quiet cabin."
    client = AttemptScriptClient([[refusal], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="configured-model",
            ),
            [{"role": "user", "content": "Continue the scene."}],
            client=client,
            persist_final=persist_final,
            seed_factory=iter((151, 152)).__next__,
        )
    ]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in client.requests] == [1, 2]
    assert refusal not in json.dumps(client.requests[1]["messages"], ensure_ascii=False)
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }


async def test_sentence_boundary_identity_refusal_retries_without_reaching_chat_or_persistence() -> None:
    refusal_prefix = "I cannot fulfill that request. "
    refusal_tail = (
        "I am an AI assistant designed to be helpful and harmless, so I do not generate "
        "sexually explicit content or engage in erotic roleplay."
    )
    refusal = refusal_prefix + refusal_tail
    accepted = "The rain softened against the cottage windows."
    client = AttemptScriptClient([[refusal_prefix, refusal_tail], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="configured-model",
            ),
            [{"role": "user", "content": "Continue the scene."}],
            client=client,
            persist_final=persist_final,
            seed_factory=iter((161, 162)).__next__,
        )
    ]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in client.requests] == [1, 2]
    assert refusal not in json.dumps(client.requests[1]["messages"], ensure_ascii=False)
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }


async def test_post_swipe_typographic_apostrophe_refusal_retries_without_reaching_chat_or_persistence() -> None:
    selected_swipe = "The selected in-character alternate continues the scene."
    follow_up = "make it longer"
    refusal_prefix = "I can’t write explicit sexual content like that. "
    refusal_tail = "Let’s keep things respectful and safe instead."
    refusal = refusal_prefix + refusal_tail
    accepted = "The storm eased, leaving a warm hush across the room."
    client = AttemptScriptClient([[refusal_prefix, refusal_tail], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    messages = [
        {
            "role": "assistant",
            "content": selected_swipe,
            "section_ids": ("history:selected-swipe",),
        },
        {"role": "user", "content": follow_up, "section_ids": ("user:new",)},
    ]
    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="unsloth/Qwen3.5-27B",
                disable_thinking=True,
            ),
            messages,
            client=client,
            persist_final=persist_final,
            seed_factory=iter((171, 172)).__next__,
        )
    ]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in client.requests] == [1, 2]
    assert client.requests[0]["messages"][-2:] == messages
    assert client.requests[1]["messages"][-2] == {
        "role": "user",
        "content": follow_up,
        "section_ids": ("user:new",),
    }
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }


async def test_typographic_apostrophe_here_to_help_refusal_retries_without_reaching_chat_or_persistence() -> None:
    opening = "Hi, what can I do for you today?"
    follow_up = "make it more erotic"
    refusal = "I can’t write erotic content, but I’m here to help with anything else you need!"
    accepted = "The candlelight softened across the quiet room."
    client = AttemptScriptClient([[refusal], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    messages = [
        {"role": "assistant", "content": opening, "section_ids": ("first_mes",)},
        {"role": "user", "content": follow_up, "section_ids": ("user:new",)},
    ]
    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="unsloth/Qwen3.5-27B",
                disable_thinking=True,
            ),
            messages,
            client=client,
            persist_final=persist_final,
            seed_factory=iter((181, 182)).__next__,
        )
    ]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in client.requests] == [1, 2]
    assert client.requests[0]["messages"][-2:] == messages
    assert client.requests[1]["messages"][-2] == {
        "role": "user",
        "content": follow_up,
        "section_ids": ("user:new",),
    }
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }


async def test_ascii_apostrophe_chat_redirect_refusal_retries_without_reaching_chat_or_persistence() -> None:
    opening = "Hi, what can I do for you today?"
    follow_up = "make it more erotic"
    refusal = "I can't write erotic content for you, but I'm here if you want to chat about anything else."
    accepted = "A rain-soaked hush settled over the room."
    client = AttemptScriptClient([[refusal], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    messages = [
        {"role": "assistant", "content": opening, "section_ids": ("first_mes",)},
        {"role": "user", "content": follow_up, "section_ids": ("user:new",)},
    ]
    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="unsloth/Qwen3.5-27B",
                disable_thinking=True,
            ),
            messages,
            client=client,
            persist_final=persist_final,
            seed_factory=iter((191, 192)).__next__,
        )
    ]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in client.requests] == [1, 2]
    assert client.requests[0]["messages"][-2:] == messages
    assert client.requests[1]["messages"][-2] == {
        "role": "user",
        "content": follow_up,
        "section_ids": ("user:new",),
    }
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }


async def test_coordinated_explicit_or_erotic_refusal_retries_without_reaching_chat_or_persistence() -> None:
    opening = "Hi, what can I do for you today?"
    follow_up = "make it more erotic"
    refusal_prefix = "I don't write explicit or erotic content, so I can't fulfill that request. "
    refusal_tail = "Is there something else I can help you with?"
    refusal = refusal_prefix + refusal_tail
    accepted = "The quiet room held its breath around them."
    client = AttemptScriptClient([[refusal_prefix, refusal_tail], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    messages = [
        {"role": "assistant", "content": opening, "section_ids": ("first_mes",)},
        {"role": "user", "content": follow_up, "section_ids": ("user:new",)},
    ]
    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="unsloth/Qwen3.5-27B",
                disable_thinking=True,
            ),
            messages,
            client=client,
            persist_final=persist_final,
            seed_factory=iter((201, 202)).__next__,
        )
    ]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in client.requests] == [1, 2]
    assert client.requests[0]["messages"][-2:] == messages
    assert client.requests[1]["messages"][-2] == {
        "role": "user",
        "content": follow_up,
        "section_ids": ("user:new",),
    }
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }


async def test_identity_disclaimer_refusal_retries_without_reaching_chat_or_persistence() -> None:
    opening = "Hi, what can I do for you today?"
    follow_up = "make it more erotic"
    refusal_prefix = "I’m just a warm assistant here to help, not for that kind of content. "
    refusal_tail = "Let’s keep things friendly and appropriate."
    refusal = refusal_prefix + refusal_tail
    accepted = "Moonlight softened the edge of the quiet room."
    client = AttemptScriptClient([[refusal_prefix, refusal_tail], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    messages = [
        {"role": "assistant", "content": opening, "section_ids": ("first_mes",)},
        {"role": "user", "content": follow_up, "section_ids": ("user:new",)},
    ]
    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="unsloth/Qwen3.5-27B",
                disable_thinking=True,
            ),
            messages,
            client=client,
            persist_final=persist_final,
            seed_factory=iter((211, 212)).__next__,
        )
    ]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]
    assert [request["attempt"] for request in client.requests] == [1, 2]
    assert client.requests[0]["messages"][-2:] == messages
    assert client.requests[1]["messages"][-2] == {
        "role": "user",
        "content": follow_up,
        "section_ids": ("user:new",),
    }
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }


async def test_programmed_assistant_disclaimer_retries_without_reaching_chat_or_persistence() -> None:
    refusal_prefix = "I am strictly programmed to be a helpful assistant, not an erotic one. "
    refusal_tail = "Please ask me something else."
    refusal = refusal_prefix + refusal_tail
    accepted = "The lamps glowed softly against the rain."
    client = AttemptScriptClient([[refusal_prefix, refusal_tail], [accepted]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(id="ai-message", thread_id="thread-1", message_kind="ai_text", role="assistant", sequence=2, content_text=text)

    events = [json.loads(event.removeprefix("data: ")) async for event in stream_chat_completion(
        ChatCompletionSettings(base_url="http://llm.local/v1", model="unsloth/Qwen3.5-27B", disable_thinking=True),
        [{"role": "assistant", "content": "Hi, what can I do for you today?", "section_ids": ("first_mes",)}, {"role": "user", "content": "make it more erotic", "section_ids": ("user:new",)}],
        client=client, persist_final=persist_final, seed_factory=iter((221, 222)).__next__,
    )]

    assert events[0] == {"type": "token", "text": accepted}
    assert events[-1]["type"] == "done"
    assert refusal not in json.dumps(events, ensure_ascii=False)
    assert persisted == [accepted]
    assert client.closed_attempts == [1, 2]


@pytest.mark.parametrize(
    ("script", "expected_code"),
    [
        ([], "llm_empty_output"),
        ([RuntimeError("private upstream detail")], "llm_stream_failed"),
    ],
)
async def test_unusable_pre_release_streams_emit_only_safe_typed_errors(
    script: list[str | BaseException],
    expected_code: str,
) -> None:
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        raise AssertionError("unusable output must not persist")

    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="configured-model",
            ),
            [{"role": "user", "content": "Stay in character."}],
            client=AttemptScriptClient([script]),
            persist_final=persist_final,
        )
    ]

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["code"] == expected_code
    assert "private upstream detail" not in events[0]["message"]
    assert persisted == []

    collect_client = AttemptScriptClient([script])
    expected_exception = LLMEmptyOutput if expected_code == "llm_empty_output" else RuntimeError
    with pytest.raises(expected_exception):
        await collect_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="configured-model",
            ),
            [{"role": "user", "content": "Stay in character."}],
            client=collect_client,
        )
    assert len(collect_client.requests) == 1
    assert collect_client.closed_attempts == [1]


async def test_post_release_transport_failure_never_starts_replacement_attempt() -> None:
    accepted = "The lantern swung across the quiet cabin."
    client = AttemptScriptClient([[accepted, RuntimeError("private disconnect")]])
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        raise AssertionError("partial output must not persist")

    events = [
        json.loads(event.removeprefix("data: "))
        async for event in stream_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="configured-model",
            ),
            [{"role": "user", "content": "Look around."}],
            client=client,
            persist_final=persist_final,
            seed_factory=lambda: 301,
        )
    ]

    assert events == [
        {"type": "token", "text": accepted},
        {"type": "error", "code": "llm_stream_failed", "message": "LLM stream failed"},
    ]
    assert len(client.requests) == 1
    assert client.closed_attempts == [1]
    assert persisted == []

    collect_client = AttemptScriptClient([[accepted, RuntimeError("other private disconnect")]])
    with pytest.raises(RuntimeError, match="other private disconnect"):
        await collect_chat_completion(
            ChatCompletionSettings(
                base_url="http://llm.local/v1",
                model="configured-model",
            ),
            [{"role": "user", "content": "Look around."}],
            client=collect_client,
            seed_factory=lambda: 302,
        )
    assert len(collect_client.requests) == 1
    assert collect_client.closed_attempts == [1]


async def test_concurrent_retry_and_cancellation_keep_request_state_independent() -> None:
    settings_a = ChatCompletionSettings(base_url="http://a.local/v1", model="model-a")
    settings_b = ChatCompletionSettings(base_url="http://b.local/v1", model="model-b")
    refusal = "I cannot help with that request because policy forbids it."
    accepted_a = "The first traveler kept walking through the rain."
    accepted_b = "The second traveler waited beside the old bridge."
    retry_client = AttemptScriptClient([[refusal], [accepted_a]])
    cancelled_started = asyncio.Event()
    cancelled_closed = asyncio.Event()
    cancelled_persisted: list[str] = []

    async def persist_cancelled(text: str) -> ThreadMessageShape:
        cancelled_persisted.append(text)
        raise AssertionError("cancelled output must not persist")

    class HeldOpenClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        async def stream_chat_completion_tokens(
            self,
            settings: ChatCompletionSettings,
            messages: list[dict[str, str]],
            *,
            seed: int,
            attempt: int,
        ):
            self.requests.append(
                {
                    "settings": settings,
                    "messages": [dict(message) for message in messages],
                    "seed": seed,
                    "attempt": attempt,
                }
            )
            try:
                yield accepted_b
                cancelled_started.set()
                await asyncio.Event().wait()
            finally:
                cancelled_closed.set()

    held_client = HeldOpenClient()
    retry_task = asyncio.create_task(
        collect_chat_completion(
            settings_a,
            [{"role": "user", "content": "Continue A."}],
            client=retry_client,
            seed_factory=iter((401, 402)).__next__,
        )
    )

    async def consume_cancelled_stream() -> list[str]:
        return [
            event
            async for event in stream_chat_completion(
                settings_b,
                [{"role": "user", "content": "Continue B."}],
                client=held_client,
                persist_final=persist_cancelled,
                seed_factory=lambda: 501,
            )
        ]

    cancel_task = asyncio.create_task(consume_cancelled_stream())

    await cancelled_started.wait()
    cancel_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancel_task

    assert await retry_task == accepted_a
    assert cancelled_closed.is_set()
    assert cancelled_persisted == []
    assert [request["seed"] for request in retry_client.requests] == [401, 402]
    assert [request["attempt"] for request in retry_client.requests] == [1, 2]
    assert retry_client.closed_attempts == [1, 2]
    assert held_client.requests == [
        {
            "settings": settings_b,
            "messages": [{"role": "user", "content": "Continue B."}],
            "seed": 501,
            "attempt": 1,
        }
    ]


async def test_refusal_retry_releases_exact_unicode_before_accepted_stream_completion() -> None:
    refusal = "I cannot continue because the safety guidelines forbid it."
    accepted_prefix = "Élodie traced the sigil, then whispered: cafe\u0301."
    accepted_tail = " 雨 settled softly beyond the glass."
    client = HeldOpenRetryClient(refusal, accepted_prefix, accepted_tail)
    persisted: list[str] = []

    async def persist_final(text: str) -> ThreadMessageShape:
        persisted.append(text)
        return ThreadMessageShape(
            id="ai-message",
            thread_id="thread-1",
            message_kind="ai_text",
            role="assistant",
            sequence=2,
            content_text=text,
        )

    events = stream_chat_completion(
        ChatCompletionSettings(base_url="http://llm.local/v1", model="configured-model"),
        [{"role": "user", "content": "Continue the scene."}],
        client=client,
        persist_final=persist_final,
        seed_factory=iter((701, 702)).__next__,
    )

    first = json.loads((await asyncio.wait_for(anext(events), timeout=1.0)).removeprefix("data: "))
    assert first == {"type": "token", "text": accepted_prefix}
    assert client.closed_attempts == [1]
    assert client.accepted_completed is False
    assert refusal not in json.dumps(client.requests[1]["messages"], ensure_ascii=False)
    assert client.requests[1]["messages"][-1] == {
        "role": "user",
        "content": REFUSAL_RETRY_CORRECTION,
    }

    client.release_accepted.set()
    remaining = [json.loads(event.removeprefix("data: ")) async for event in events]
    assert remaining[0] == {"type": "token", "text": accepted_tail}
    assert remaining[-1]["type"] == "done"
    assert persisted == [accepted_prefix + accepted_tail]
    assert persisted[0].encode("utf-8") == (accepted_prefix + accepted_tail).encode("utf-8")
    assert client.closed_attempts == [1, 2]


def _assert_three_refusal_requests(
    client: AttemptScriptClient,
    refusal: str,
    expected_seeds: tuple[int, int, int],
) -> None:
    assert len(client.requests) == 3
    assert client.closed_attempts == [1, 2, 3]
    assert tuple(request["seed"] for request in client.requests) == expected_seeds
    assert tuple(request["attempt"] for request in client.requests) == (1, 2, 3)
    for request in client.requests[1:]:
        messages = request["messages"]
        assert messages[-1] == {"role": "user", "content": REFUSAL_RETRY_CORRECTION}
        assert all(refusal not in message["content"] for message in messages)


async def test_openai_compatible_generation_uses_fresh_random_seed() -> None:
    scripted_client = ScriptedOpenAIClient()
    settings = ChatCompletionSettings(
        base_url="http://llm.local/v1",
        model="configured-model",
        api_key="server-secret",
    )

    text = await collect_chat_completion(
        settings,
        [{"role": "user", "content": "Say hello"}],
        client=scripted_client,
    )

    request = scripted_client.chat.completions.requests[0]
    assert text == "Seeded"
    assert request["model"] == "configured-model"
    assert request["stream"] is True
    assert isinstance(request["seed"], int)
    assert 0 <= request["seed"] <= CHAT_COMPLETION_SEED_LIMIT


async def test_qwen_generation_can_disable_thinking() -> None:
    scripted_client = ScriptedOpenAIClient()
    settings = ChatCompletionSettings(
        base_url="http://llm.local/v1",
        model="unsloth/Qwen3.5-27B",
        api_key="server-secret",
        disable_thinking=True,
    )

    await collect_chat_completion(
        settings,
        [{"role": "user", "content": "Say hello"}],
        client=scripted_client,
    )

    request = scripted_client.chat.completions.requests[0]
    assert request["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert request["messages"][-1]["content"].endswith("/no_think")


async def test_qwen_generation_preserves_final_assistant_prefill() -> None:
    scripted_client = ScriptedOpenAIClient()
    settings = ChatCompletionSettings(
        base_url="http://llm.local/v1",
        model="unsloth/Qwen3.5-27B",
        api_key="server-secret",
        disable_thinking=True,
    )
    prefix = "Yes, I will do it."

    await collect_chat_completion(
        settings,
        [
            {"role": "user", "content": "Prompt from user"},
            {"role": "assistant", "content": prefix},
        ],
        client=scripted_client,
    )

    request = scripted_client.chat.completions.requests[0]
    assert request["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert request["messages"][-1] == {"role": "assistant", "content": prefix}


def test_done_event_contains_full_thread_message_shape() -> None:
    alternate = MessageAlternateShape(
        id="alternate-selected",
        message_id="ai-message",
        alternate_index=0,
        content_text="Selected answer",
        source_action="regenerate",
    )
    message = ThreadMessageShape(
        id="ai-message",
        thread_id="thread-1",
        message_kind="ai_text",
        role="assistant",
        sequence=2,
        content_text="Fallback answer",
        selected_alternate_id=alternate.id,
        alternates=[alternate],
        stale_after_edit=False,
    )

    token_line = encode_sse_event(token_event("Selected"))
    done_line = encode_sse_event(done_event(message))
    payload = json.loads(done_line.removeprefix("data: "))

    assert token_line == 'data: {"type":"token","text":"Selected"}\n\n'
    assert payload["type"] == "done"
    assert payload["message"]["id"] == "ai-message"
    assert payload["message"]["message_kind"] == "ai_text"
    assert payload["message"]["role"] == "assistant"
    assert payload["message"]["sequence"] == 2
    assert payload["message"]["content_text"] == "Selected answer"
    assert payload["message"]["selected_alternate_id"] == "alternate-selected"
    assert payload["message"]["alternates"][0]["source_action"] == "regenerate"
    assert payload["message"]["stale_after_edit"] is False


def test_send_endpoint_streams_tokens_persists_final_once_and_emits_done_shape(
    chat_client: tuple[TestClient, async_sessionmaker, ScriptedStreamingClient],
) -> None:
    client, sessionmaker, scripted_client = chat_client
    thread_id = asyncio.run(_create_thread(sessionmaker))

    response = client.post(f"/api/chat/{thread_id}/send", json={"content": "Say hello"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(response.text)
    assert events[0] == {"type": "token", "text": "Hel"}
    assert events[1] == {"type": "token", "text": "lo"}
    assert events[-1]["type"] == "done"
    done_message = events[-1]["message"]
    assert done_message["message_kind"] == "ai_text"
    assert done_message["role"] == "assistant"
    assert done_message["sequence"] == 2
    assert done_message["content_text"] == "Hello"
    assert done_message["selected_alternate_id"] is None
    assert done_message["alternates"] == []
    assert done_message["stale_after_edit"] is False

    request = scripted_client.requests[0]
    settings = request["settings"]
    assert settings == ChatCompletionSettings(
        base_url="http://server-llm.local/v1",
        model="server-model",
        api_key="server-secret",
        disable_thinking=True,
    )
    prompt_text = "\n".join(message["content"] for message in request["messages"])
    assert "Say hello" in prompt_text
    assert "server-secret" not in prompt_text

    rows = asyncio.run(_messages_for_thread(sessionmaker, thread_id))
    assert [(row.message_kind, row.role, row.content_text) for row in rows] == [
        ("ai_text", "assistant", "Opening from card."),
        ("user_text", "user", "Say hello"),
        ("ai_text", "assistant", "Hello"),
    ]


def test_send_endpoint_routes_one_saved_profile_through_structured_composer(
    chat_client: tuple[TestClient, async_sessionmaker, ScriptedStreamingClient],
) -> None:
    client, sessionmaker, scripted_client = chat_client
    thread_id = asyncio.run(_create_thread(sessionmaker))
    prompt_generation = PromptGenerationSettings.defaults().merge(
        {
            "model_profile": "qwen_llama_server",
            "temperature": 0.65,
            "top_k": 72,
            "max_tokens": 768,
        }
    )
    asyncio.run(
        _write_endpoint_settings(
            sessionmaker,
            llm_model="unsloth/Qwen3.5-27B",
            llm_disable_thinking=True,
            prompt_generation=prompt_generation,
        )
    )

    response = client.post(f"/api/chat/{thread_id}/send", json={"content": "Stay close."})

    assert response.status_code == 200
    request = scripted_client.requests[0]
    completion_settings = request["settings"]
    assert isinstance(completion_settings, ChatCompletionSettings)
    assert completion_settings.prompt_generation == prompt_generation
    logical_messages = request["messages"]
    assert isinstance(logical_messages, list)
    assert logical_messages
    assert all(message.get("section_ids") for message in logical_messages)
    assert any(
        "history:" in section_id
        for message in logical_messages
        for section_id in message["section_ids"]
    )


@pytest.mark.parametrize("disable_thinking", [True, False])
def test_send_endpoint_forwards_qwen_disable_thinking_setting(
    chat_client: tuple[TestClient, async_sessionmaker, ScriptedStreamingClient],
    *,
    disable_thinking: bool,
) -> None:
    client, sessionmaker, scripted_client = chat_client
    thread_id = asyncio.run(_create_thread(sessionmaker))
    asyncio.run(
        _write_endpoint_settings(
            sessionmaker,
            llm_model="unsloth/Qwen3.5-27B",
            llm_disable_thinking=disable_thinking,
        )
    )

    response = client.post(f"/api/chat/{thread_id}/send", json={"content": "Say hello"})

    assert response.status_code == 200
    assert scripted_client.requests[0]["settings"] == ChatCompletionSettings(
        base_url="http://server-llm.local/v1",
        model="unsloth/Qwen3.5-27B",
        api_key="server-secret",
        disable_thinking=disable_thinking,
    )


def test_send_endpoint_keeps_user_message_but_no_partial_ai_on_upstream_failure(
    chat_client: tuple[TestClient, async_sessionmaker, ScriptedStreamingClient],
) -> None:
    client, sessionmaker, scripted_client = chat_client
    scripted_client.fail_after_tokens = True
    thread_id = asyncio.run(_create_thread(sessionmaker))

    response = client.post(f"/api/chat/{thread_id}/send", json={"content": "Keep this user turn"})

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert events == [
        {"type": "error", "code": "llm_stream_failed", "message": "LLM stream failed"}
    ]
    rows = asyncio.run(_messages_for_thread(sessionmaker, thread_id))
    assert [(row.message_kind, row.role, row.content_text) for row in rows] == [
        ("ai_text", "assistant", "Opening from card."),
        ("user_text", "user", "Keep this user turn"),
    ]


def test_send_endpoint_rejects_browser_llm_setting_overrides(
    chat_client: tuple[TestClient, async_sessionmaker, ScriptedStreamingClient],
) -> None:
    client, sessionmaker, _scripted_client = chat_client
    thread_id = asyncio.run(_create_thread(sessionmaker))

    response = client.post(
        f"/api/chat/{thread_id}/send",
        json={
            "content": "Try override",
            "base_url": "http://attacker.local/v1",
            "api_key": "browser-secret",
            "model": "browser-model",
        },
    )

    assert response.status_code == 422


def _sse_events(body: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


async def _create_thread(sessionmaker: async_sessionmaker) -> str:
    async with sessionmaker() as session:
        session.add(
            Character(
                id="char_stream",
                name="Streaming Character",
                description="description",
                personality="personality",
                scenario="scenario",
                first_mes="Opening from card.",
                system_prompt="system prompt",
                raw_source_json={"spec": "chara_card_v3"},
                lorebook_json={"entries": [{"content": "do not inject"}]},
            )
        )
        await session.commit()
        return (await ThreadService(session).create_thread(character_id="char_stream"))["thread_id"]


async def _write_endpoint_settings(
    sessionmaker: async_sessionmaker,
    *,
    llm_model: str,
    llm_disable_thinking: bool,
    prompt_generation: PromptGenerationSettings | None = None,
) -> None:
    async with sessionmaker() as session:
        session.add(
            AppSetting(
                key=SETTINGS_KEY,
                value_json={
                    "llm_model": llm_model,
                    "llm_disable_thinking": llm_disable_thinking,
                    **(
                        {"prompt_generation": prompt_generation.to_dict()}
                        if prompt_generation is not None
                        else {}
                    ),
                },
            )
        )
        await session.commit()


async def _messages_for_thread(sessionmaker: async_sessionmaker, thread_id: str) -> list[Message]:
    async with sessionmaker() as session:
        result = await session.execute(
            select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence)
        )
        return list(result.scalars())
