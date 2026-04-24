"""Streaming chat contracts."""

import json

from app.domain.llm_stream import (
    ChatCompletionSettings,
    done_event,
    encode_sse_event,
    stream_chat_completion,
    token_event,
)
from app.storage.models import MessageAlternateShape, ThreadMessageShape


class FakeStreamingClient:
    def __init__(self) -> None:
        self.tokens = ["Hel", "lo"]


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
            client=FakeStreamingClient(),
            persist_final=persist_final,
        )
    ]

    assert json.loads(events[0].removeprefix("data: ")) == {"type": "token", "text": "Hel"}
    assert json.loads(events[1].removeprefix("data: ")) == {"type": "token", "text": "lo"}
    assert len(persisted) == 1
    assert json.loads(events[-1].removeprefix("data: "))["type"] == "done"


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
