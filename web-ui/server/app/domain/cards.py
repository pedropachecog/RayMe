"""Character-card import and character lifecycle contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

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


class CharacterCardParseError(ValueError):
    """Raised when uploaded card bytes cannot be parsed safely."""


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
    lorebook_json: Mapping[str, Any] | None = None
    lorebook_status: LorebookStatus = "absent"
    warnings: tuple[str, ...] = ()
    prompt_excluded_fields: tuple[str, ...] = ()
    untrusted_fields: tuple[str, ...] = UNTRUSTED_CARD_FIELDS
    rendered_html: None = None

    @property
    def lorebook_present(self) -> bool:
        return self.lorebook_json is not None


@dataclass(frozen=True, slots=True)
class CharacterDeleteResult:
    """Character delete response shape that preserves existing thread snapshots."""

    character_id: str
    deleted_at: str
    preserved_thread_ids: tuple[str, ...]
    strategy: Literal["soft_delete", "detach_threads"]


class CharacterDeleteRepository(Protocol):
    """Storage boundary for safe character deletion."""

    async def delete_character_preserving_thread_snapshots(
        self,
        character_id: str,
    ) -> CharacterDeleteResult: ...


async def delete_character_preserving_thread_snapshots(
    character_id: str,
    *,
    repository: CharacterDeleteRepository,
) -> CharacterDeleteResult:
    """Delete or detach a character without deleting historical chat threads."""

    raise NotImplementedError


def parse_character_card_bytes(
    content: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> CharacterCardImportResult:
    """Parse JSON or PNG-embedded SillyTavern card bytes into RayMe storage fields."""

    raise NotImplementedError


__all__ = [
    "CardSourceFormat",
    "CharacterCard",
    "CharacterCardImportResult",
    "CharacterCardParseError",
    "CharacterDeleteRepository",
    "CharacterDeleteResult",
    "LorebookStatus",
    "PNG_TEXT_CHUNK_KEYS_IN_ORDER",
    "UNTRUSTED_CARD_FIELDS",
    "delete_character_preserving_thread_snapshots",
    "parse_character_card_bytes",
]
