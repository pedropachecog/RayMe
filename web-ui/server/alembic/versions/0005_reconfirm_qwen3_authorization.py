"""Require fresh authorization for existing canonical Qwen voices.

Revision ID: 0005_reconfirm_qwen3_authorization
Revises: 0004_call_turn_idempotency
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0005_reconfirm_qwen3_authorization"
down_revision: str | None = "0004_call_turn_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANONICAL_ENGINE_ID = "qwen3_1_7b"
AUTHORIZATION_METADATA_KEY = "qwen3_authorization"


def upgrade() -> None:
    connection = op.get_bind()
    voices = sa.table(
        "voices",
        sa.column("id", sa.String()),
        sa.column("default_engine", sa.String()),
        sa.column("metadata_json", sa.JSON()),
    )
    rows = connection.execute(
        sa.select(voices.c.id, voices.c.metadata_json).where(
            voices.c.default_engine == CANONICAL_ENGINE_ID
        )
    ).mappings()
    for row in rows:
        metadata = _metadata_object(row["metadata_json"])
        if AUTHORIZATION_METADATA_KEY not in metadata:
            continue
        if metadata.get(AUTHORIZATION_METADATA_KEY) == {
            "authorization_status": "needs_confirmation"
        }:
            continue
        metadata[AUTHORIZATION_METADATA_KEY] = {
            "authorization_status": "needs_confirmation"
        }
        connection.execute(
            sa.update(voices)
            .where(voices.c.id == row["id"])
            .values(metadata_json=metadata)
        )


def downgrade() -> None:
    # Fresh authorization cannot be reconstructed from a stale model-specific
    # grant, so this safety repair is deliberately irreversible.
    pass


def _metadata_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {"legacy_metadata": value}
