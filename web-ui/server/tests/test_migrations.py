"""Alembic migration tests for unified chat storage."""

from __future__ import annotations

import sqlite3
import json
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
VOICE_ASSET_INDEX = "ix_voice_assets_voice_id"
CHARACTER_DEFAULT_VOICE_INDEX = "ix_characters_default_voice_id"
MESSAGE_CALL_TURN_UNIQUE_INDEX = "uq_messages_call_turn"


def run_migration(tmp_path: Path) -> Path:
    db_path = tmp_path / "rayme.sqlite3"
    config = Config(str(SERVER_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")

    command.upgrade(config, "head")

    return db_path


def migration_config(db_path: Path) -> Config:
    config = Config(str(SERVER_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    return config


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


def column_info(connection: sqlite3.Connection, table_name: str) -> dict[str, sqlite3.Row]:
    return {
        row["name"]: row for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def index_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA index_list({table_name})")}


def foreign_keys(connection: sqlite3.Connection, table_name: str) -> list[sqlite3.Row]:
    return list(connection.execute(f"PRAGMA foreign_key_list({table_name})"))


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
            "character_snapshot_mes_example",
        }.issubset(thread_columns)
        assert column_info(connection, models.THREADS_TABLE)[
            "character_snapshot_mes_example"
        ]["notnull"] == 0

        voice_columns = column_names(connection, "voices")
        assert VOICE_COLUMNS.issubset(voice_columns)

        voice_asset_columns = column_names(connection, "voice_assets")
        assert VOICE_ASSET_COLUMNS.issubset(voice_asset_columns)


def test_voice_storage_schema_has_indexes_and_default_voice_fk(tmp_path: Path) -> None:
    db_path = run_migration(tmp_path)

    assert models.VOICES_TABLE in models.MODEL_TABLE_NAMES
    assert models.VOICE_ASSETS_TABLE in models.MODEL_TABLE_NAMES

    with connect(db_path) as connection:
        assert VOICE_ASSET_INDEX in index_names(connection, "voice_assets")
        assert CHARACTER_DEFAULT_VOICE_INDEX in index_names(connection, models.CHARACTERS_TABLE)

        character_voice_fks = [
            row
            for row in foreign_keys(connection, models.CHARACTERS_TABLE)
            if row["from"] == "default_voice_id"
        ]
        assert len(character_voice_fks) == 1
        assert character_voice_fks[0]["table"] == models.VOICES_TABLE
        assert character_voice_fks[0]["to"] == "id"
        assert character_voice_fks[0]["on_delete"].upper() == "SET NULL"


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


def test_completed_call_turn_identity_is_durably_unique(tmp_path: Path) -> None:
    db_path = run_migration(tmp_path)

    with connect(db_path) as connection:
        insert_thread(connection)
        assert MESSAGE_CALL_TURN_UNIQUE_INDEX in index_names(connection, "messages")
        connection.execute(
            """
            INSERT INTO messages
                (id, thread_id, call_id, call_turn_id, message_kind, role, sequence,
                 content_text)
            VALUES
                ('ai-call-1', 'thread-1', 'call-1', 'turn-1', 'ai_speech',
                 'assistant', 0, 'Only once')
            """
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO messages
                    (id, thread_id, call_id, call_turn_id, message_kind, role,
                     sequence, content_text)
                VALUES
                    ('ai-call-duplicate', 'thread-1', 'call-1', 'turn-1',
                     'ai_speech', 'assistant', 1, 'Must fail')
                """
            )


def test_call_turn_lifecycle_reservation_is_durably_unique(tmp_path: Path) -> None:
    db_path = run_migration(tmp_path)

    with connect(db_path) as connection:
        insert_thread(connection)
        assert "call_turns" in table_names(connection)
        assert {
            "call_id",
            "turn_id",
            "thread_id",
            "request_sha256",
            "state",
            "owner_token",
            "lease_expires_at",
            "user_message_id",
            "assistant_message_id",
        }.issubset(column_names(connection, "call_turns"))
        connection.execute(
            """
            INSERT INTO call_turns
                (id, call_id, turn_id, thread_id, request_sha256, state)
            VALUES ('call-turn-1', 'call-1', 'turn-1', 'thread-1', ?, 'reserved')
            """,
            ("a" * 64,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO call_turns
                    (id, call_id, turn_id, thread_id, request_sha256, state)
                VALUES ('call-turn-2', 'call-1', 'turn-1', 'thread-1', ?, 'running')
                """,
                ("a" * 64,),
            )


def test_call_turn_ownership_upgrade_preserves_existing_lifecycle_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "call-turn-ownership.sqlite3"
    config = migration_config(db_path)
    command.upgrade(config, "0006_call_turn_lifecycle")

    with connect(db_path) as connection:
        insert_thread(connection)
        connection.execute(
            """
            INSERT INTO call_turns
                (id, call_id, turn_id, thread_id, request_sha256, state)
            VALUES ('legacy-turn', 'legacy-call', 'turn-1', 'thread-1', ?, 'running')
            """,
            ("b" * 64,),
        )
        connection.commit()

    command.upgrade(config, "head")

    with connect(db_path) as connection:
        assert {"owner_token", "lease_expires_at"}.issubset(
            column_names(connection, "call_turns")
        )
        row = connection.execute(
            """
            SELECT state, owner_token, lease_expires_at
            FROM call_turns
            WHERE id = 'legacy-turn'
            """
        ).fetchone()
        assert dict(row) == {
            "state": "running",
            "owner_token": None,
            "lease_expires_at": None,
        }


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


def test_qwen3_identity_upgrade_is_exact_truthful_and_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "rayme-qwen-identity.sqlite3"
    config = migration_config(db_path)
    command.upgrade(config, "0002_voice_storage")

    with connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO voices (id, name, default_engine, reference_transcript, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    "voice-legacy-qwen",
                    "Legacy Qwen",
                    "qwen3_0_6b",
                    "Exact legacy transcript.",
                    json.dumps({"keep": {"nested": True}}),
                ),
                (
                    "voice-current-qwen",
                    "Current Qwen",
                    "qwen3_1_7b",
                    "Current transcript.",
                    json.dumps({"authorization_status": "external"}),
                ),
                (
                    "voice-legacy-recorded",
                    "Legacy Recorded Qwen",
                    "qwen3_0_6b",
                    "Recorded legacy transcript.",
                    json.dumps(
                        {
                            "keep": "preserved",
                            "qwen3_authorization": {
                                "authorization_status": "recorded",
                                "voice_data_steward": "private-steward",
                                "authorization_basis": "legacy-grant",
                                "use_scope": "rayme_lan_call_testing",
                                "reference_sha256": "a" * 64,
                                "transcript_sha256": "b" * 64,
                            },
                        }
                    ),
                ),
                (
                    "voice-unknown-qwen",
                    "Unknown Qwen",
                    "qwen3_future_unknown",
                    "Unknown transcript.",
                    json.dumps({"keep": "untouched"}),
                ),
            ),
        )
        connection.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?, ?)",
            (
                "endpoint_settings",
                json.dumps(
                    {
                        "tts_default_engine": "qwen3_0_6b",
                        "unrelated": {"qwen3_0_6b": "must-not-change"},
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?, ?)",
            ("unrelated_setting", json.dumps({"tts_default_engine": "qwen3_0_6b"})),
        )
        connection.commit()

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    with connect(db_path) as connection:
        voices = {
            row["id"]: row
            for row in connection.execute(
                "SELECT id, default_engine, metadata_json FROM voices ORDER BY id"
            )
        }
        legacy_metadata = json.loads(voices["voice-legacy-qwen"]["metadata_json"])
        recorded_legacy_metadata = json.loads(
            voices["voice-legacy-recorded"]["metadata_json"]
        )
        current_metadata = json.loads(voices["voice-current-qwen"]["metadata_json"])
        unknown_metadata = json.loads(voices["voice-unknown-qwen"]["metadata_json"])

        assert voices["voice-legacy-qwen"]["default_engine"] == "qwen3_1_7b"
        assert legacy_metadata == {"keep": {"nested": True}}
        assert voices["voice-legacy-recorded"]["default_engine"] == "qwen3_1_7b"
        assert recorded_legacy_metadata == {"keep": "preserved"}
        assert voices["voice-current-qwen"]["default_engine"] == "qwen3_1_7b"
        assert current_metadata == {"authorization_status": "external"}
        assert voices["voice-unknown-qwen"]["default_engine"] == "qwen3_future_unknown"
        assert unknown_metadata == {"keep": "untouched"}

        endpoint_settings = json.loads(
            connection.execute(
                "SELECT value_json FROM app_settings WHERE key = 'endpoint_settings'"
            ).fetchone()["value_json"]
        )
        unrelated_settings = json.loads(
            connection.execute(
                "SELECT value_json FROM app_settings WHERE key = 'unrelated_setting'"
            ).fetchone()["value_json"]
        )
        assert endpoint_settings == {
            "tts_default_engine": "qwen3_1_7b",
            "unrelated": {"qwen3_0_6b": "must-not-change"},
        }
        assert unrelated_settings == {"tts_default_engine": "qwen3_0_6b"}


def test_forward_repair_resets_authorization_already_recorded_by_original_0003(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "rayme-qwen-forward-repair.sqlite3"
    config = migration_config(db_path)
    command.upgrade(config, "0003_qwen3_engine_identity")

    stale_authorization = {
        "authorization_status": "recorded",
        "voice_data_steward": "stale-private-steward",
        "authorization_basis": "legacy-model-grant",
        "use_scope": "rayme_lan_call_testing",
        "reference_sha256": "a" * 64,
        "transcript_sha256": "b" * 64,
    }
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO voices
                (id, name, default_engine, reference_transcript, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "voice-original-0003-state",
                "Already upgraded Qwen",
                "qwen3_1_7b",
                "Exact stale transcript.",
                json.dumps(
                    {
                        "keep": {"unrelated": True},
                        "qwen3_authorization": stale_authorization,
                    }
                ),
            ),
        )
        connection.commit()

    command.upgrade(config, "0005_reconfirm_qwen3_authorization")
    command.upgrade(config, "0005_reconfirm_qwen3_authorization")

    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT default_engine, metadata_json FROM voices WHERE id = ?",
            ("voice-original-0003-state",),
        ).fetchone()
        metadata = json.loads(row["metadata_json"])

    assert row["default_engine"] == "qwen3_1_7b"
    assert metadata == {
        "keep": {"unrelated": True},
        "qwen3_authorization": {"authorization_status": "needs_confirmation"},
    }
    serialized = json.dumps(metadata)
    assert "stale-private-steward" not in serialized
    assert "legacy-model-grant" not in serialized


def test_upload_implies_authorization_migration_removes_legacy_qwen_metadata(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "rayme-qwen-upload-authorization.sqlite3"
    config = migration_config(db_path)
    command.upgrade(config, "0007_call_turn_ownership")

    with connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO voices
                (id, name, default_engine, reference_transcript, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    "voice-legacy-authorization",
                    "Uploaded Qwen voice",
                    "qwen3_1_7b",
                    "Exact uploaded transcript.",
                    json.dumps(
                        {
                            "keep": {"unrelated": True},
                            "source": "phase09_hardware_tracer",
                            "qwen3_authorization": {
                                "authorization_status": "needs_confirmation",
                                "voice_data_steward": "remove-me",
                            },
                            "authorization": {
                                "authorization_status": "recorded",
                                "voice_data_steward": "remove-legacy-steward",
                                "authorization_basis": "remove-legacy-basis",
                                "use_scope": "remove-legacy-scope",
                                "reference_sha256": "c" * 64,
                                "transcript_sha256": "d" * 64,
                            },
                        },
                    )
                ),
                (
                    "voice-legacy-engine-authorization",
                    "Legacy engine Qwen voice",
                    "qwen3_0_6b",
                    "Exact legacy transcript.",
                    json.dumps(
                        {
                            "keep": "legacy-engine",
                            "source": "phase09_hardware_tracer",
                            "authorization": {"voice_data_steward": "remove-legacy"},
                        }
                    ),
                ),
                (
                    "voice-qwen-generic-authorization",
                    "Qwen generic authorization",
                    "qwen3_1_7b",
                    "Exact generic transcript.",
                    json.dumps(
                        {
                            "source": "voice_lab",
                            "authorization": {"owner": "legal", "license": "CC-BY"},
                            "qwen3_authorization": {"authorization_status": "retired"},
                        }
                    ),
                ),
                (
                    "voice-f5-authorization",
                    "F5 authorized metadata",
                    "F5-TTS",
                    "F5 transcript.",
                    json.dumps(
                        {
                            "source": "phase09_hardware_tracer",
                            "authorization": {"owner": "legal", "license": "CC-BY"},
                            "qwen3_authorization": {"note": "non-Qwen metadata"},
                        }
                    ),
                ),
                (
                    "voice-voxcpm2-authorization",
                    "VoxCPM2 authorized metadata",
                    "voxcpm2",
                    "VoxCPM2 transcript.",
                    json.dumps(
                        {
                            "source": "phase09_hardware_tracer",
                            "authorization": {"owner": "legal", "license": "CC-BY-SA"},
                            "qwen3_authorization": {"note": "non-Qwen metadata"},
                        }
                    ),
                ),
            ),
        )
        connection.commit()

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    with connect(db_path) as connection:
        metadata_by_id = {
            row["id"]: json.loads(row["metadata_json"])
            for row in connection.execute(
                "SELECT id, metadata_json FROM voices ORDER BY id"
            )
        }

    metadata = metadata_by_id["voice-legacy-authorization"]
    assert metadata == {
        "keep": {"unrelated": True},
        "source": "phase09_hardware_tracer",
    }
    serialized = json.dumps(metadata)
    assert "remove-legacy-steward" not in serialized
    assert "remove-legacy-basis" not in serialized
    assert "remove-legacy-scope" not in serialized
    assert metadata_by_id["voice-legacy-engine-authorization"] == {
        "keep": "legacy-engine",
        "source": "phase09_hardware_tracer",
    }
    assert metadata_by_id["voice-qwen-generic-authorization"] == {
        "source": "voice_lab",
        "authorization": {"owner": "legal", "license": "CC-BY"},
    }
    assert metadata_by_id["voice-f5-authorization"] == {
        "source": "phase09_hardware_tracer",
        "authorization": {"owner": "legal", "license": "CC-BY"},
        "qwen3_authorization": {"note": "non-Qwen metadata"},
    }
    assert metadata_by_id["voice-voxcpm2-authorization"] == {
        "source": "phase09_hardware_tracer",
        "authorization": {"owner": "legal", "license": "CC-BY-SA"},
        "qwen3_authorization": {"note": "non-Qwen metadata"},
    }


def test_upload_implies_authorization_migration_rejects_downgrade(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "rayme-qwen-irreversible-authorization.sqlite3"
    config = migration_config(db_path)
    command.upgrade(config, "head")

    with pytest.raises(
        RuntimeError,
        match="0008 is irreversible: removed Qwen authorization claims cannot be reconstructed",
    ):
        command.downgrade(config, "0007_call_turn_ownership")

    with connect(db_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert revision["version_num"] == "0008_remove_qwen3_authorization"


def test_thread_example_snapshot_upgrade_keeps_legacy_null_and_preserves_all_other_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "rayme-thread-example-legacy.sqlite3"
    config = migration_config(db_path)
    command.upgrade(config, "0008_remove_qwen3_authorization")

    character_lorebook = '{"entries":[{"key":["Café"],"content":"e\\u0301 🐉"}],"order":7}'
    character_raw_source = '{"spec":"chara_card_v3","nested":{"preserve":true}}'
    thread_lorebook = '{"thread_copy":{"bytes":"stay exactly here"},"order":[2,1]}'
    thread_raw_source = '{"thread":"snapshot","nested":["a","b"]}'

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO characters
                (id, name, description, personality, scenario, first_mes, mes_example,
                 system_prompt, post_history_instructions, raw_source_json, lorebook_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "char-legacy-example",
                "Legacy Character",
                "description-before-0009",
                "personality-before-0009",
                "scenario-before-0009",
                "first-before-0009",
                "<START>\n{{char}}: Live card text must never be imported.",
                "system-before-0009",
                "phi-before-0009",
                character_raw_source,
                character_lorebook,
            ),
        )
        connection.execute(
            """
            INSERT INTO threads
                (id, character_id, title, character_snapshot_name,
                 character_snapshot_description, character_snapshot_personality,
                 character_snapshot_scenario, character_snapshot_first_mes,
                 character_snapshot_system_prompt,
                 character_snapshot_post_history_instructions,
                 character_snapshot_lorebook_json, character_snapshot_raw_source_json,
                 last_message_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-legacy-example",
                "char-legacy-example",
                "Legacy Thread",
                "Legacy Character Snapshot",
                "snapshot-description",
                "snapshot-personality",
                "snapshot-scenario",
                "snapshot-first",
                "snapshot-system",
                "snapshot-phi",
                thread_lorebook,
                thread_raw_source,
                "2026-08-30 23:59:58",
                None,
            ),
        )
        connection.commit()
        character_before = dict(
            connection.execute(
                "SELECT * FROM characters WHERE id = 'char-legacy-example'"
            ).fetchone()
        )
        thread_before = dict(
            connection.execute(
                "SELECT * FROM threads WHERE id = 'thread-legacy-example'"
            ).fetchone()
        )

    command.upgrade(config, "head")

    with connect(db_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert revision["version_num"] == "0009_thread_example_snapshot"
        info = column_info(connection, "threads")["character_snapshot_mes_example"]
        assert info["type"] == "TEXT"
        assert info["notnull"] == 0
        upgraded_character = dict(
            connection.execute(
                "SELECT * FROM characters WHERE id = 'char-legacy-example'"
            ).fetchone()
        )
        upgraded_thread = dict(
            connection.execute(
                "SELECT * FROM threads WHERE id = 'thread-legacy-example'"
            ).fetchone()
        )
        assert upgraded_thread.pop("character_snapshot_mes_example") is None
        assert upgraded_character == character_before
        assert upgraded_thread == thread_before
        assert upgraded_character["lorebook_json"] == character_lorebook
        assert upgraded_thread["character_snapshot_lorebook_json"] == thread_lorebook

    command.downgrade(config, "0008_remove_qwen3_authorization")

    with connect(db_path) as connection:
        assert "character_snapshot_mes_example" not in column_names(connection, "threads")
        assert dict(
            connection.execute(
                "SELECT * FROM characters WHERE id = 'char-legacy-example'"
            ).fetchone()
        ) == character_before
        assert dict(
            connection.execute(
                "SELECT * FROM threads WHERE id = 'thread-legacy-example'"
            ).fetchone()
        ) == thread_before

    command.upgrade(config, "head")

    with connect(db_path) as connection:
        restored = dict(
            connection.execute(
                "SELECT * FROM threads WHERE id = 'thread-legacy-example'"
            ).fetchone()
        )
        assert restored.pop("character_snapshot_mes_example") is None
        assert restored == thread_before
        assert dict(
            connection.execute(
                "SELECT * FROM characters WHERE id = 'char-legacy-example'"
            ).fetchone()
        ) == character_before
