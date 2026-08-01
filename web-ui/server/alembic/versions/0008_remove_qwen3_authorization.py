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

QWEN_ENGINE_IDS = frozenset({"qwen3_1_7b", "qwen3_0_6b"})
QWEN_AUTHORIZATION_METADATA_KEY = "qwen3_authorization"
LEGACY_AUTHORIZATION_METADATA_KEY = "authorization"
LEGACY_AUTHORIZATION_SOURCE = "phase09_hardware_tracer"


def upgrade() -> None:
    connection = op.get_bind()
    voices = sa.table(
        "voices",
        sa.column("id", sa.String()),
        sa.column("default_engine", sa.String()),
        sa.column("metadata_json", sa.JSON()),
    )
    rows = connection.execute(
        sa.select(voices.c.id, voices.c.default_engine, voices.c.metadata_json)
    ).mappings()
    for row in rows:
        if row["default_engine"] not in QWEN_ENGINE_IDS:
            continue
        metadata = _metadata_object(row["metadata_json"])
        changed = QWEN_AUTHORIZATION_METADATA_KEY in metadata
        metadata.pop(QWEN_AUTHORIZATION_METADATA_KEY, None)
        if (
            metadata.get("source") == LEGACY_AUTHORIZATION_SOURCE
            and LEGACY_AUTHORIZATION_METADATA_KEY in metadata
        ):
            metadata.pop(LEGACY_AUTHORIZATION_METADATA_KEY, None)
            changed = True
        if not changed:
            continue
        connection.execute(
            sa.update(voices)
            .where(voices.c.id == row["id"])
            .values(metadata_json=metadata)
        )


def downgrade() -> None:
    raise RuntimeError(
        "0008 is irreversible: removed Qwen authorization claims cannot be reconstructed"
    )


def _metadata_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {"legacy_metadata": value}
