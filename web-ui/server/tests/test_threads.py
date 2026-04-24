"""Thread creation and hydration contracts."""

from app.storage.models import MessageAlternateShape, ThreadMessageShape


def test_thread_creation_inserts_first_message_or_selected_alternate() -> None:
    selected_greeting = MessageAlternateShape(
        id="alternate-greeting-2",
        message_id="opening-message",
        alternate_index=2,
        content_text="Alternate greeting selected before thread creation.",
        source_action="first_mes",
    )
    opening_message = ThreadMessageShape(
        id="opening-message",
        thread_id="thread-1",
        message_kind="ai_text",
        role="assistant",
        sequence=0,
        content_text="Default first message.",
        selected_alternate_id=selected_greeting.id,
        alternates=[selected_greeting],
    )

    assert opening_message.sequence == 0
    assert opening_message.selected_content() == selected_greeting.content_text
    assert opening_message.alternates[0].source_action == "first_mes"


def test_thread_detail_hydrates_selected_alternates_and_stale_flags() -> None:
    selected = MessageAlternateShape(
        id="alternate-selected",
        message_id="ai-message",
        alternate_index=1,
        content_text="Visible selected branch.",
        source_action="swipe",
    )
    unselected = MessageAlternateShape(
        id="alternate-unselected",
        message_id="ai-message",
        alternate_index=2,
        content_text="Stored but hidden branch.",
        source_action="swipe",
    )
    message = ThreadMessageShape(
        id="ai-message",
        thread_id="thread-1",
        message_kind="ai_text",
        role="assistant",
        sequence=3,
        content_text="Original response.",
        selected_alternate_id=selected.id,
        alternates=[selected, unselected],
        stale_after_edit=True,
    )
    payload = message.to_dict()

    assert payload["content_text"] == "Visible selected branch."
    assert payload["selected_alternate_id"] == "alternate-selected"
    assert [alternate["alternate_index"] for alternate in payload["alternates"]] == [1, 2]
    assert payload["stale_after_edit"] is True
