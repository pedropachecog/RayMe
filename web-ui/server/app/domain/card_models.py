"""Character-card models used at the parser and storage boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

CardSourceFormat = Literal["v2_json", "v3_json", "v2_png", "v3_png"]
LorebookStatus = Literal["absent", "present_not_used_in_v1"]

PNG_TEXT_CHUNK_KEYS_IN_ORDER = ("ccv3", "chara")
UNTRUSTED_CARD_FIELDS = (
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "system_prompt",
    "creator_notes",
    "character_notes",
    "post_history_instructions",
)


class SourceCardData(BaseModel):
    """Permissive SillyTavern data section preserving unknown fields."""

    model_config = ConfigDict(extra="allow")

    name: str
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_mes: str | None = None
    mes_example: str | None = None
    system_prompt: str | None = None
    creator_notes: str | None = None
    character_notes: str | None = None
    tags: list[str] | None = None
    alternate_greetings: list[str] | None = None
    post_history_instructions: str | None = None
    creator: str | None = None
    character_version: str | None = None
    extensions: dict[str, Any] | None = None
    character_book: dict[str, Any] | list[Any] | None = None
    lorebook: dict[str, Any] | list[Any] | None = None
    world_info: dict[str, Any] | list[Any] | None = None
    world: dict[str, Any] | list[Any] | None = None


class SourceCharacterCard(BaseModel):
    """Permissive source-card boundary for v2/v3 JSON payloads."""

    model_config = ConfigDict(extra="allow")

    spec: str | None = None
    spec_version: str | None = None
    data: SourceCardData


@dataclass(frozen=True, slots=True)
class CharacterCard:
    """Normalized v3-shaped character fields stored by RayMe."""

    name: str
    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_mes: str | None = None
    mes_example: str | None = None
    system_prompt: str | None = None
    creator_notes: str | None = None
    character_notes: str | None = None
    tags: tuple[str, ...] = ()
    alternate_greetings: tuple[str, ...] = ()
    post_history_instructions: str | None = None
    creator: str | None = None
    character_version: str | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CharacterCardImportResult:
    """Parser output that keeps untrusted source data separate from rendering."""

    source_format: CardSourceFormat
    source_key: str | None
    character: CharacterCard
    raw_source_json: Mapping[str, Any]
    lorebook_json: Mapping[str, Any] | Sequence[Any] | None = None
    lorebook_status: LorebookStatus = "absent"
    warnings: tuple[str, ...] = ()
    prompt_excluded_fields: tuple[str, ...] = ()
    untrusted_fields: tuple[str, ...] = UNTRUSTED_CARD_FIELDS
    rendered_html: None = None

    @property
    def lorebook_present(self) -> bool:
        return self.lorebook_json is not None


__all__ = [
    "CardSourceFormat",
    "CharacterCard",
    "CharacterCardImportResult",
    "LorebookStatus",
    "PNG_TEXT_CHUNK_KEYS_IN_ORDER",
    "SourceCardData",
    "SourceCharacterCard",
    "UNTRUSTED_CARD_FIELDS",
]
