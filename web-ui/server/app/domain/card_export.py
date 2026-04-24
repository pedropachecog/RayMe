"""Character-card export helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from app.domain.cards import CharacterCard


class CharacterCardExportError(ValueError):
    """Raised when a character cannot be exported safely."""


def export_character_v2_json(
    character: CharacterCard | Mapping[str, Any],
    *,
    include_raw_source_json: bool = True,
) -> dict[str, Any]:
    """Export a character as a SillyTavern v2 JSON card.

    Phase 1 exports JSON only. v3 PNG/tEXt chunk export remains out of scope.
    """

    values = _character_values(character)
    name = _string_value(values, "name")
    if not name:
        raise CharacterCardExportError("Character name is required for v2 export")

    data: dict[str, Any] = {
        "name": name,
        "description": _string_value(values, "description"),
        "personality": _string_value(values, "personality"),
        "scenario": _string_value(values, "scenario"),
        "first_mes": _string_value(values, "first_mes"),
        "mes_example": _string_value(values, "mes_example"),
        "system_prompt": _string_value(values, "system_prompt"),
        "creator_notes": _string_value(values, "creator_notes"),
        "character_notes": _string_value(values, "character_notes"),
        "tags": _list_value(values, "tags"),
        "alternate_greetings": _list_value(values, "alternate_greetings"),
        "post_history_instructions": _string_value(values, "post_history_instructions"),
        "creator": _string_value(values, "creator"),
        "character_version": _string_value(values, "character_version"),
    }
    extensions = values.get("extensions")
    if isinstance(extensions, Mapping) and extensions:
        data["extensions"] = dict(extensions)

    lorebook_json = values.get("lorebook_json")
    if isinstance(lorebook_json, (dict, list)):
        data["character_book"] = lorebook_json

    if include_raw_source_json:
        raw_source_json = values.get("raw_source_json")
        if isinstance(raw_source_json, Mapping):
            data["rayme_source_card"] = dict(raw_source_json)

    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": data,
    }


def _character_values(character: CharacterCard | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(character, Mapping):
        return dict(character)
    if is_dataclass(character):
        return asdict(character)

    values: dict[str, Any] = {}
    for field in (
        "name",
        "description",
        "personality",
        "scenario",
        "first_mes",
        "mes_example",
        "system_prompt",
        "creator_notes",
        "character_notes",
        "tags",
        "alternate_greetings",
        "post_history_instructions",
        "creator",
        "character_version",
        "extensions",
        "raw_source_json",
        "lorebook_json",
    ):
        values[field] = getattr(character, field, None)
    return values


def _string_value(values: Mapping[str, Any], key: str) -> str | None:
    value = values.get(key)
    return value if isinstance(value, str) else None


def _list_value(values: Mapping[str, Any], key: str) -> list[str]:
    value = values.get(key)
    if isinstance(value, str):
        return [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]


__all__ = ["CharacterCardExportError", "export_character_v2_json"]
