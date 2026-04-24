"""SQLAlchemy storage models and chat thread shape contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, TypedDict

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

APP_SETTINGS_TABLE = "app_settings"
CHARACTERS_TABLE = "characters"
CHARACTER_ASSETS_TABLE = "character_assets"
THREADS_TABLE = "threads"
MESSAGES_TABLE = "messages"
MESSAGE_ALTERNATES_TABLE = "message_alternates"

MODEL_TABLE_NAMES = (
    APP_SETTINGS_TABLE,
    CHARACTERS_TABLE,
    CHARACTER_ASSETS_TABLE,
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
    "edited_from_alternate_id",
    "stale_after_edit",
    "branch_root_id",
    "created_at",
    "updated_at",
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


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for ORM defaults."""

    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base metadata for RayMe storage tables."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class AppSetting(TimestampMixin, Base):
    __tablename__ = APP_SETTINGS_TABLE

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[dict[str, object] | list[object] | str | int | float | bool | None] = (
        mapped_column(JSON, nullable=True)
    )


class Character(TimestampMixin, Base):
    __tablename__ = CHARACTERS_TABLE

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_mes: Mapped[str | None] = mapped_column(Text, nullable=True)
    mes_example: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_history_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    character_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tags_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    alternate_greetings_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    raw_source_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    lorebook_json: Mapped[dict[str, object] | list[object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CharacterAsset(TimestampMixin, Base):
    __tablename__ = CHARACTER_ASSETS_TABLE
    __table_args__ = (Index("ix_character_assets_character_id", "character_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{CHARACTERS_TABLE}.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Thread(TimestampMixin, Base):
    __tablename__ = THREADS_TABLE
    __table_args__ = (Index("ix_threads_character_id", "character_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(f"{CHARACTERS_TABLE}.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    character_snapshot_name: Mapped[str] = mapped_column(String(200), nullable=False)
    character_snapshot_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_snapshot_personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_snapshot_scenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_snapshot_first_mes: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_snapshot_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_snapshot_post_history_instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    character_snapshot_lorebook_json: Mapped[dict[str, object] | list[object] | None] = (
        mapped_column(JSON, nullable=True)
    )
    character_snapshot_raw_source_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(TimestampMixin, Base):
    __tablename__ = MESSAGES_TABLE
    __table_args__ = (
        CheckConstraint(
            "message_kind IN ('user_text', 'ai_text', 'user_speech', "
            "'ai_speech', 'call_start', 'call_end')",
            name="ck_messages_message_kind",
        ),
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'event')",
            name="ck_messages_role",
        ),
        UniqueConstraint("thread_id", "sequence", name="uq_messages_thread_sequence"),
        Index("ix_messages_thread_id", "thread_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{THREADS_TABLE}.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_message_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(f"{MESSAGES_TABLE}.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_kind: Mapped[MessageKind] = mapped_column(String(40), nullable=False)
    role: Mapped[MessageRole] = mapped_column(String(40), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_alternate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    edited_from_message_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(f"{MESSAGES_TABLE}.id", ondelete="SET NULL"),
        nullable=True,
    )
    stale_after_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    branch_root_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(f"{MESSAGES_TABLE}.id", ondelete="SET NULL"),
        nullable=True,
    )


class MessageAlternate(TimestampMixin, Base):
    __tablename__ = MESSAGE_ALTERNATES_TABLE
    __table_args__ = (
        CheckConstraint(
            "source_action IN ('first_mes', 'regenerate', 'swipe', 'continue')",
            name="ck_message_alternates_source_action",
        ),
        UniqueConstraint("message_id", "alternate_index", name="uq_message_alternates_index"),
        Index("ix_message_alternates_message_id", "message_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{MESSAGES_TABLE}.id", ondelete="CASCADE"),
        nullable=False,
    )
    alternate_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_action: Mapped[MessageAlternateSourceAction] = mapped_column(String(40), nullable=False)
    edited_from_alternate_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(f"{MESSAGE_ALTERNATES_TABLE}.id", ondelete="SET NULL"),
        nullable=True,
    )
    stale_after_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    branch_root_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
    "APP_SETTINGS_TABLE",
    "AppSetting",
    "Base",
    "CHARACTERS_TABLE",
    "CHARACTER_ASSETS_TABLE",
    "Character",
    "CharacterAsset",
    "MESSAGE_ALTERNATES_TABLE",
    "MESSAGE_ALTERNATE_SCHEMA_REQUIRED_COLUMNS",
    "MESSAGE_ALTERNATE_SOURCE_ACTIONS",
    "MESSAGES_TABLE",
    "MESSAGE_KIND_VALUES",
    "MESSAGE_ROLE_VALUES",
    "MESSAGE_SCHEMA_REQUIRED_COLUMNS",
    "Message",
    "MessageAlternate",
    "MODEL_TABLE_NAMES",
    "MessageAlternateDict",
    "MessageAlternateShape",
    "MessageAlternateSourceAction",
    "MessageKind",
    "MessageRole",
    "THREADS_TABLE",
    "Thread",
    "ThreadMessageDict",
    "ThreadMessageShape",
    "utc_now",
]
