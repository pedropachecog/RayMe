"""Remove superseded Qwen reference-authorization metadata.

Revision ID: 0008_remove_qwen3_authorization
Revises: 0007_call_turn_ownership
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0008_remove_qwen3_authorization"
down_revision: str | None = "0007_call_turn_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTHORIZATION_METADATA_KEY = "qwen3_authorization"


def upgrade() -> None:
    connection = op.get_bind()
    voices = sa.table(
        "voices",
        sa.column("id", sa.String()),
        sa.column("metadata_json", sa.JSON()),
    )
    rows = connection.execute(
        sa.select(voices.c.id, voices.c.metadata_json)
    ).mappings()
    for row in rows:
        metadata = _metadata_object(row["metadata_json"])
        if AUTHORIZATION_METADATA_KEY not in metadata:
            continue
        metadata.pop(AUTHORIZATION_METADATA_KEY, None)
        connection.execute(
            sa.update(voices)
            .where(voices.c.id == row["id"])
            .values(metadata_json=metadata)
        )


def downgrade() -> None:
    # Removed reference-authorization claims cannot be reconstructed truthfully.
    pass


def _metadata_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {"legacy_metadata": value}
