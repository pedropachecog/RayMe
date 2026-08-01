"""Add durable exact-once identity for completed call turns.

Revision ID: 0004_call_turn_idempotency
Revises: 0003_qwen3_engine_identity
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_call_turn_idempotency"
down_revision: str | None = "0003_qwen3_engine_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CALL_TURN_UNIQUE_INDEX = "uq_messages_call_turn"


def upgrade() -> None:
    op.add_column("messages", sa.Column("call_id", sa.String(length=64), nullable=True))
    op.add_column(
        "messages",
        sa.Column("call_turn_id", sa.String(length=128), nullable=True),
    )
    # SQLite permits multiple NULL values in a unique index, so non-call
    # messages remain unaffected while one completed assistant row is allowed
    # for each durable call/turn identity.
    op.create_index(
        CALL_TURN_UNIQUE_INDEX,
        "messages",
        ["call_id", "call_turn_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(CALL_TURN_UNIQUE_INDEX, table_name="messages")
    op.drop_column("messages", "call_turn_id")
    op.drop_column("messages", "call_id")
