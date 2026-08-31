"""Add truthful nullable example snapshots to threads.

Revision ID: 0009_thread_example_snapshot
Revises: 0008_remove_qwen3_authorization
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_thread_example_snapshot"
down_revision: str | None = "0008_remove_qwen3_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column("character_snapshot_mes_example", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("threads", "character_snapshot_mes_example")
