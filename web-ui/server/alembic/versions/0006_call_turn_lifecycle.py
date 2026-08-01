"""Add durable call-turn reservation and lifecycle state.

Revision ID: 0006_call_turn_lifecycle
Revises: 0005_reconfirm_qwen3_authorization
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_call_turn_lifecycle"
down_revision: str | None = "0005_reconfirm_qwen3_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CALL_TURN_UNIQUE_CONSTRAINT = "uq_call_turns_call_turn"
CALL_TURN_THREAD_INDEX = "ix_call_turns_thread_id"


def upgrade() -> None:
    op.create_table(
        "call_turns",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("turn_id", sa.String(length=128), nullable=False),
        sa.Column(
            "thread_id",
            sa.String(length=64),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("user_message_id", sa.String(length=64), nullable=True),
        sa.Column("assistant_message_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('reserved', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_call_turns_state",
        ),
        sa.UniqueConstraint(
            "call_id",
            "turn_id",
            name=CALL_TURN_UNIQUE_CONSTRAINT,
        ),
    )
    op.create_index(
        CALL_TURN_THREAD_INDEX,
        "call_turns",
        ["thread_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(CALL_TURN_THREAD_INDEX, table_name="call_turns")
    op.drop_table("call_turns")
