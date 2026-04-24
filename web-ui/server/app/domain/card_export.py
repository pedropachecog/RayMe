"""Character-card export contracts."""

from __future__ import annotations

from collections.abc import Mapping
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

    raise NotImplementedError


__all__ = ["CharacterCardExportError", "export_character_v2_json"]
