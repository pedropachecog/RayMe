"""Initial RayMe storage schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("personality", sa.Text(), nullable=True),
        sa.Column("scenario", sa.Text(), nullable=True),
        sa.Column("first_mes", sa.Text(), nullable=True),
        sa.Column("mes_example", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("creator_notes", sa.Text(), nullable=True),
        sa.Column("character_notes", sa.Text(), nullable=True),
        sa.Column("post_history_instructions", sa.Text(), nullable=True),
        sa.Column("creator", sa.String(length=200), nullable=True),
        sa.Column("character_version", sa.String(length=80), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("alternate_greetings_json", sa.JSON(), nullable=True),
        sa.Column("raw_source_json", sa.JSON(), nullable=True),
        sa.Column("lorebook_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "character_assets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("asset_kind", sa.String(length=40), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("character_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("character_snapshot_name", sa.String(length=200), nullable=False),
        sa.Column("character_snapshot_description", sa.Text(), nullable=True),
        sa.Column("character_snapshot_personality", sa.Text(), nullable=True),
        sa.Column("character_snapshot_scenario", sa.Text(), nullable=True),
        sa.Column("character_snapshot_first_mes", sa.Text(), nullable=True),
        sa.Column("character_snapshot_system_prompt", sa.Text(), nullable=True),
        sa.Column("character_snapshot_post_history_instructions", sa.Text(), nullable=True),
        sa.Column("character_snapshot_lorebook_json", sa.JSON(), nullable=True),
        sa.Column("character_snapshot_raw_source_json", sa.JSON(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("parent_message_id", sa.String(length=64), nullable=True),
        sa.Column("message_kind", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("selected_alternate_id", sa.String(length=64), nullable=True),
        sa.Column("edited_from_message_id", sa.String(length=64), nullable=True),
        sa.Column("stale_after_edit", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("branch_root_id", sa.String(length=64), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "message_kind IN ('user_text', 'ai_text', 'user_speech', 'ai_speech', 'call_start', 'call_end')",
            name="ck_messages_message_kind",
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'event')",
            name="ck_messages_role",
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["edited_from_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["branch_root_id"], ["messages.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("thread_id", "sequence", name="uq_messages_thread_sequence"),
    )

    op.create_table(
        "message_alternates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("alternate_index", sa.Integer(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("source_action", sa.String(length=40), nullable=False),
        sa.Column("edited_from_alternate_id", sa.String(length=64), nullable=True),
        sa.Column("stale_after_edit", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("branch_root_id", sa.String(length=64), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "source_action IN ('first_mes', 'regenerate', 'swipe', 'continue')",
            name="ck_message_alternates_source_action",
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["edited_from_alternate_id"],
            ["message_alternates.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("message_id", "alternate_index", name="uq_message_alternates_index"),
    )

    op.create_index("ix_character_assets_character_id", "character_assets", ["character_id"])
    op.create_index("ix_threads_character_id", "threads", ["character_id"])
    op.create_index("ix_messages_thread_id", "messages", ["thread_id"])
    op.create_index("ix_message_alternates_message_id", "message_alternates", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_message_alternates_message_id", table_name="message_alternates")
    op.drop_index("ix_messages_thread_id", table_name="messages")
    op.drop_index("ix_threads_character_id", table_name="threads")
    op.drop_index("ix_character_assets_character_id", table_name="character_assets")
    op.drop_table("message_alternates")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("character_assets")
    op.drop_table("characters")
    op.drop_table("app_settings")
