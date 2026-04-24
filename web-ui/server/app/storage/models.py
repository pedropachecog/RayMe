"""Storage model names and chat thread shape contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

CHARACTERS_TABLE = "characters"
THREADS_TABLE = "threads"
MESSAGES_TABLE = "messages"
MESSAGE_ALTERNATES_TABLE = "message_alternates"

MODEL_TABLE_NAMES = (
    CHARACTERS_TABLE,
    THREADS_TABLE,
    MESSAGES_TABLE,
    MESSAGE_ALTERNATES_TABLE,
)

MESSAGE_KIND_VALUES = (
    "user_text",
    "ai_text",
    "user_speech",
    "ai_speech",
    "call_start",
    "call_end",
)

MESSAGE_ROLE_VALUES = ("user", "assistant", "system", "event")

MESSAGE_ALTERNATE_SOURCE_ACTIONS = (
    "first_mes",
    "regenerate",
    "swipe",
    "continue",
)

MESSAGE_SCHEMA_REQUIRED_COLUMNS = (
    "id",
    "thread_id",
    "parent_message_id",
    "message_kind",
    "role",
    "sequence",
    "content_text",
    "selected_alternate_id",
    "edited_from_message_id",
    "stale_after_edit",
    "branch_root_id",
    "created_at",
    "updated_at",
)

MESSAGE_ALTERNATE_SCHEMA_REQUIRED_COLUMNS = (
    "id",
    "message_id",
    "alternate_index",
    "content_text",
    "source_action",
    "created_at",
)

MessageKind = Literal[
    "user_text",
    "ai_text",
    "user_speech",
    "ai_speech",
    "call_start",
    "call_end",
]
MessageRole = Literal["user", "assistant", "system", "event"]
MessageAlternateSourceAction = Literal["first_mes", "regenerate", "swipe", "continue"]


class MessageAlternateDict(TypedDict):
    id: str
    message_id: str
    alternate_index: int
    content_text: str
    source_action: MessageAlternateSourceAction
    created_at: str | None


class ThreadMessageDict(TypedDict):
    id: str
    thread_id: str
    message_kind: MessageKind
    role: MessageRole
    sequence: int
    content_text: str | None
    selected_alternate_id: str | None
    alternates: list[MessageAlternateDict]
    stale_after_edit: bool
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True, slots=True)
class MessageAlternateShape:
    """Thread hydration shape for stored alternates."""

    id: str
    message_id: str
    alternate_index: int
    content_text: str
    source_action: MessageAlternateSourceAction
    created_at: str | None = None

    def to_dict(self) -> MessageAlternateDict:
        return {
            "id": self.id,
            "message_id": self.message_id,
            "alternate_index": self.alternate_index,
            "content_text": self.content_text,
            "source_action": self.source_action,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ThreadMessageShape:
    """Backend-to-client message shape shared by thread detail and stream done events."""

    id: str
    thread_id: str
    message_kind: MessageKind
    role: MessageRole
    sequence: int
    content_text: str | None
    selected_alternate_id: str | None = None
    alternates: list[MessageAlternateShape] = field(default_factory=list)
    stale_after_edit: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    def selected_content(self) -> str | None:
        if self.selected_alternate_id is None:
            return self.content_text

        for alternate in self.alternates:
            if alternate.id == self.selected_alternate_id:
                return alternate.content_text

        return self.content_text

    def to_dict(self) -> ThreadMessageDict:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "message_kind": self.message_kind,
            "role": self.role,
            "sequence": self.sequence,
            "content_text": self.selected_content(),
            "selected_alternate_id": self.selected_alternate_id,
            "alternates": [alternate.to_dict() for alternate in self.alternates],
            "stale_after_edit": self.stale_after_edit,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


__all__ = [
    "CHARACTERS_TABLE",
    "MESSAGE_ALTERNATES_TABLE",
    "MESSAGE_ALTERNATE_SCHEMA_REQUIRED_COLUMNS",
    "MESSAGE_ALTERNATE_SOURCE_ACTIONS",
    "MESSAGE_KIND_VALUES",
    "MESSAGE_ROLE_VALUES",
    "MESSAGE_SCHEMA_REQUIRED_COLUMNS",
    "MESSAGES_TABLE",
    "MODEL_TABLE_NAMES",
    "MessageAlternateDict",
    "MessageAlternateShape",
    "MessageAlternateSourceAction",
    "MessageKind",
    "MessageRole",
    "THREADS_TABLE",
    "ThreadMessageDict",
    "ThreadMessageShape",
]
