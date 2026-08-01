"""Add durable ownership and expiry to call turns.

Revision ID: 0007_call_turn_ownership
Revises: 0006_call_turn_lifecycle
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_call_turn_ownership"
down_revision: str | None = "0006_call_turn_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "call_turns",
        sa.Column("owner_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "call_turns",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("call_turns", "lease_expires_at")
    op.drop_column("call_turns", "owner_token")
