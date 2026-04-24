"""Schema contracts for unified chat storage."""

from app.storage import models


def test_initial_migration_creates_message_kinds() -> None:
    assert models.MESSAGES_TABLE == "messages"
    assert models.MESSAGE_KIND_VALUES == (
        "user_text",
        "ai_text",
        "user_speech",
        "ai_speech",
        "call_start",
        "call_end",
    )
    assert "message_kind" in models.MESSAGE_SCHEMA_REQUIRED_COLUMNS


def test_messages_support_selected_alternate_and_stale_flags() -> None:
    assert models.MESSAGE_ALTERNATES_TABLE == "message_alternates"
    assert "selected_alternate_id" in models.MESSAGE_SCHEMA_REQUIRED_COLUMNS
    assert "stale_after_edit" in models.MESSAGE_SCHEMA_REQUIRED_COLUMNS
    assert "edited_from_message_id" in models.MESSAGE_SCHEMA_REQUIRED_COLUMNS
    assert models.MESSAGE_ALTERNATE_SOURCE_ACTIONS == (
        "first_mes",
        "regenerate",
        "swipe",
        "continue",
    )
