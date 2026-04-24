"""Add durable voice storage tables.

Revision ID: 0002_voice_storage
Revises: 0001_initial_schema
Create Date: 2026-04-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_voice_storage"
down_revision: str | None = "0001_initial_schema"
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
        "voices",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("default_engine", sa.String(length=80), nullable=False),
        sa.Column("reference_transcript", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "voice_assets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("voice_id", sa.String(length=64), nullable=True),
        sa.Column("asset_kind", sa.String(length=40), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=True),
        sa.Column("channel_count", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["voice_id"], ["voices.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_voice_assets_voice_id", "voice_assets", ["voice_id"])

    with op.batch_alter_table("characters") as batch_op:
        batch_op.add_column(sa.Column("default_voice_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_characters_default_voice_id_voices",
            "voices",
            ["default_voice_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_characters_default_voice_id", "characters", ["default_voice_id"])


def downgrade() -> None:
    op.drop_index("ix_characters_default_voice_id", table_name="characters")
    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_constraint("fk_characters_default_voice_id_voices", type_="foreignkey")
        batch_op.drop_column("default_voice_id")

    op.drop_index("ix_voice_assets_voice_id", table_name="voice_assets")
    op.drop_table("voice_assets")
    op.drop_table("voices")
