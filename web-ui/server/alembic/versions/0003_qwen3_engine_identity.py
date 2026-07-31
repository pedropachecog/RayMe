"""Migrate the exact legacy Qwen engine identity without inventing consent.

Revision ID: 0003_qwen3_engine_identity
Revises: 0002_voice_storage
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0003_qwen3_engine_identity"
down_revision: str | None = "0002_voice_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_ENGINE_ID = "qwen3_0_6b"
CANONICAL_ENGINE_ID = "qwen3_1_7b"
SETTINGS_KEY = "endpoint_settings"
AUTHORIZATION_METADATA_KEY = "qwen3_authorization"


def upgrade() -> None:
    connection = op.get_bind()
    voices = sa.table(
        "voices",
        sa.column("id", sa.String()),
        sa.column("default_engine", sa.String()),
        sa.column("metadata_json", sa.JSON()),
    )
    settings = sa.table(
        "app_settings",
        sa.column("key", sa.String()),
        sa.column("value_json", sa.JSON()),
    )

    legacy_rows = connection.execute(
        sa.select(voices.c.id, voices.c.metadata_json).where(
            voices.c.default_engine == LEGACY_ENGINE_ID
        )
    ).mappings()
    for row in legacy_rows:
        metadata = _metadata_object(row["metadata_json"])
        existing_authorization = metadata.get(AUTHORIZATION_METADATA_KEY)
        if not isinstance(existing_authorization, Mapping):
            metadata[AUTHORIZATION_METADATA_KEY] = {
                "authorization_status": "needs_confirmation"
            }
        connection.execute(
            sa.update(voices)
            .where(voices.c.id == row["id"])
            .values(default_engine=CANONICAL_ENGINE_ID, metadata_json=metadata)
        )

    endpoint_settings = connection.execute(
        sa.select(settings.c.value_json).where(settings.c.key == SETTINGS_KEY)
    ).scalar_one_or_none()
    if isinstance(endpoint_settings, Mapping):
        normalized_settings = dict(endpoint_settings)
        if normalized_settings.get("tts_default_engine") == LEGACY_ENGINE_ID:
            normalized_settings["tts_default_engine"] = CANONICAL_ENGINE_ID
            connection.execute(
                sa.update(settings)
                .where(settings.c.key == SETTINGS_KEY)
                .values(value_json=normalized_settings)
            )


def downgrade() -> None:
    # Deliberately irreversible: after this revision, a canonical 1.7B value can
    # be newly created or migrated. Rewriting every canonical value back to the
    # obsolete 0.6B identity would lie about user-created data.
    pass


def _metadata_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {"legacy_metadata": value}
