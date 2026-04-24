"""Character-card export contracts."""

from __future__ import annotations

import json

from app.domain.card_export import export_character_v2_json
from app.domain.cards import CharacterCard


def test_v2_export_omits_v3_png_export() -> None:
    character = CharacterCard(
        name="Exported Character",
        description="<img src=x onerror=alert(1)> stays data, not rendered HTML",
        personality="friendly",
        scenario="testing export",
        first_mes="Hello",
        mes_example="<START>\n{{char}}: Hello",
        system_prompt="Stay helpful.",
        creator_notes="Private creator notes",
        character_notes="Character notes",
        tags=("export", "v2"),
        alternate_greetings=("Alt hello",),
        post_history_instructions="Post history",
        creator="RayMe",
        character_version="1.0",
    )

    exported = export_character_v2_json(character)

    assert exported["spec"] == "chara_card_v2"
    assert exported["spec_version"].startswith("2.")
    assert exported["data"]["name"] == "Exported Character"
    assert exported["data"]["description"] == character.description
    assert "rendered_html" not in exported["data"]
    assert "preview_html" not in exported["data"]
    serialized = json.dumps(exported).lower()
    assert "ccv3" not in serialized
    assert "png" not in serialized
    assert "chara" not in exported


def test_v2_export_preserves_lorebook_without_png_bytes() -> None:
    exported = export_character_v2_json(
        {
            "name": "Lore Export",
            "description": "plain data",
            "lorebook_json": {"entries": [{"keys": ["secret"], "content": "stored only"}]},
            "alternate_greetings": ["Alt"],
        }
    )

    assert exported["spec"] == "chara_card_v2"
    assert exported["data"]["character_book"]["entries"][0]["content"] == "stored only"
    assert exported["data"]["alternate_greetings"] == ["Alt"]
    assert isinstance(json.dumps(exported), str)
