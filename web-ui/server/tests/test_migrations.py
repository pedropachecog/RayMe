"""Alembic migration tests for unified chat storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.storage import models

SERVER_ROOT = Path(__file__).resolve().parents[1]
VOICE_TABLES = {"voices", "voice_assets"}
VOICE_COLUMNS = {
    "id",
    "name",
    "default_engine",
    "reference_transcript",
    "metadata_json",
    "deleted_at",
}
VOICE_ASSET_COLUMNS = {
    "voice_id",
    "asset_kind",
    "storage_path",
}


def run_migration(tmp_path: Path) -> Path:
    db_path = tmp_path / "rayme.sqlite3"
    config = Config(str(SERVER_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")

    command.upgrade(config, "head")

    return db_path


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }


def column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def insert_thread(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO threads (id, title, character_snapshot_name)
        VALUES ('thread-1', 'Opening Chat', 'Snapshot Character')
        """,
    )


def role_for(message_kind: str) -> str:
    if message_kind.startswith("call_"):
        return "event"
    if message_kind.startswith("ai_"):
        return "assistant"
    return "user"


def test_initial_migration_creates_all_storage_tables(tmp_path: Path) -> None:
    db_path = run_migration(tmp_path)

    with connect(db_path) as connection:
        assert set(models.MODEL_TABLE_NAMES).issubset(table_names(connection))
        assert VOICE_TABLES.issubset(table_names(connection))

        character_columns = column_names(connection, models.CHARACTERS_TABLE)
        assert {
            "description",
            "personality",
            "scenario",
            "first_mes",
            "mes_example",
            "system_prompt",
            "creator_notes",
            "character_notes",
            "post_history_instructions",
            "raw_source_json",
            "lorebook_json",
            "deleted_at",
            "default_voice_id",
        }.issubset(character_columns)

        thread_columns = column_names(connection, models.THREADS_TABLE)
        assert {
            "character_snapshot_name",
            "character_snapshot_description",
            "character_snapshot_personality",
            "character_snapshot_scenario",
            "character_snapshot_first_mes",
            "character_snapshot_system_prompt",
            "character_snapshot_post_history_instructions",
            "character_snapshot_lorebook_json",
            "character_snapshot_raw_source_json",
        }.issubset(thread_columns)

        voice_columns = column_names(connection, "voices")
        assert VOICE_COLUMNS.issubset(voice_columns)

        voice_asset_columns = column_names(connection, "voice_assets")
        assert VOICE_ASSET_COLUMNS.issubset(voice_asset_columns)


def test_messages_accept_only_unified_message_kinds(tmp_path: Path) -> None:
    db_path = run_migration(tmp_path)

    with connect(db_path) as connection:
        insert_thread(connection)
        for sequence, message_kind in enumerate(models.MESSAGE_KIND_VALUES):
            connection.execute(
                """
                INSERT INTO messages
                    (id, thread_id, message_kind, role, sequence, content_text)
                VALUES (?, 'thread-1', ?, ?, ?, ?)
                """,
                (
                    f"message-{sequence}",
                    message_kind,
                    role_for(message_kind),
                    sequence,
                    f"{message_kind} content",
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO messages
                    (id, thread_id, message_kind, role, sequence, content_text)
                VALUES ('bad-kind', 'thread-1', 'typing_indicator', 'event', 99, 'bad')
                """,
            )


def test_message_alternates_accept_only_supported_source_actions(tmp_path: Path) -> None:
    db_path = run_migration(tmp_path)

    with connect(db_path) as connection:
        insert_thread(connection)
        connection.execute(
            """
            INSERT INTO messages (id, thread_id, message_kind, role, sequence, content_text)
            VALUES ('ai-1', 'thread-1', 'ai_text', 'assistant', 1, 'Original')
            """,
        )

        for index, source_action in enumerate(models.MESSAGE_ALTERNATE_SOURCE_ACTIONS):
            connection.execute(
                """
                INSERT INTO message_alternates
                    (id, message_id, alternate_index, content_text, source_action)
                VALUES (?, 'ai-1', ?, ?, ?)
                """,
                (f"alt-{index}", index, f"{source_action} text", source_action),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO message_alternates
                    (id, message_id, alternate_index, content_text, source_action)
                VALUES ('alt-bad', 'ai-1', 99, 'bad', 'delete')
                """,
            )


def test_branch_columns_persist_selected_alternate_and_stale_state(tmp_path: Path) -> None:
    db_path = run_migration(tmp_path)

    with connect(db_path) as connection:
        messages_columns = column_names(connection, models.MESSAGES_TABLE)
        assert set(models.MESSAGE_SCHEMA_REQUIRED_COLUMNS).issubset(messages_columns)
        assert {"selected_alternate_id", "stale_after_edit", "branch_root_id"}.issubset(
            messages_columns,
        )

        alternate_columns = column_names(connection, models.MESSAGE_ALTERNATES_TABLE)
        assert set(models.MESSAGE_ALTERNATE_SCHEMA_REQUIRED_COLUMNS).issubset(alternate_columns)

        insert_thread(connection)
        connection.execute(
            """
            INSERT INTO messages (id, thread_id, message_kind, role, sequence, content_text)
            VALUES ('ai-1', 'thread-1', 'ai_text', 'assistant', 1, 'Original')
            """,
        )
        connection.execute(
            """
            INSERT INTO message_alternates
                (id, message_id, alternate_index, content_text, source_action, branch_root_id)
            VALUES ('alt-1', 'ai-1', 0, 'Selected branch', 'swipe', 'ai-1')
            """,
        )
        connection.execute(
            """
            UPDATE messages
            SET selected_alternate_id = 'alt-1',
                stale_after_edit = 1,
                branch_root_id = 'ai-1'
            WHERE id = 'ai-1'
            """,
        )

        row = connection.execute(
            """
            SELECT selected_alternate_id, stale_after_edit, branch_root_id
            FROM messages
            WHERE id = 'ai-1'
            """,
        ).fetchone()

        assert dict(row) == {
            "selected_alternate_id": "alt-1",
            "stale_after_edit": 1,
            "branch_root_id": "ai-1",
        }
