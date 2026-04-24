"""Character-card import and character lifecycle services."""

from __future__ import annotations

import base64
import binascii
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from app.domain.card_models import (
    CardSourceFormat,
    CharacterCard,
    CharacterCardImportResult,
    LorebookStatus,
    PNG_TEXT_CHUNK_KEYS_IN_ORDER,
    SourceCharacterCard,
    UNTRUSTED_CARD_FIELDS,
)

MAX_CARD_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PNG_CARD_JSON_BYTES = 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class CharacterCardParseError(ValueError):
    """Raised when uploaded card bytes cannot be parsed safely."""


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

    return await repository.delete_character_preserving_thread_snapshots(character_id)


def _safe_parse_error(message: str) -> CharacterCardParseError:
    return CharacterCardParseError(f"Invalid character card: {message}")


def _json_object_from_bytes(content: bytes) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8")
        payload = json.loads(decoded)
    except UnicodeDecodeError as exc:
        raise _safe_parse_error("JSON must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise _safe_parse_error("JSON payload is malformed") from exc

    if not isinstance(payload, dict):
        raise _safe_parse_error("JSON payload must be an object")
    return payload


def _detect_card_version(payload: Mapping[str, Any]) -> Literal["v2", "v3"]:
    spec = str(payload.get("spec") or "").lower()
    spec_version = str(payload.get("spec_version") or "").lower()
    if "v3" in spec or spec_version.startswith("3"):
        return "v3"
    return "v2"


def _source_format(payload: Mapping[str, Any], source_key: str | None) -> CardSourceFormat:
    version = _detect_card_version(payload)
    if source_key is None:
        return "v3_json" if version == "v3" else "v2_json"
    return "v3_png" if version == "v3" else "v2_png"


def _string_tuple(values: object, *, field_name: str, warnings: list[str]) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,)
    if not isinstance(values, list):
        warnings.append(f"Ignored non-list {field_name}")
        return ()

    strings: list[str] = []
    ignored = 0
    for value in values:
        if isinstance(value, str):
            strings.append(value)
        else:
            ignored += 1
    if ignored:
        warnings.append(f"Ignored non-string values in {field_name}")
    return tuple(strings)


def _lorebook_from_payload(
    source: Mapping[str, Any],
    data: Mapping[str, Any],
) -> Mapping[str, Any] | list[Any] | None:
    for key in ("character_book", "lorebook", "world_info", "world"):
        value = data.get(key)
        if isinstance(value, (dict, list)):
            return value
    extensions = data.get("extensions")
    if isinstance(extensions, Mapping):
        for key in ("character_book", "lorebook", "world_info", "world"):
            value = extensions.get(key)
            if isinstance(value, (dict, list)):
                return value
    for key in ("character_book", "lorebook", "world_info", "world"):
        value = source.get(key)
        if isinstance(value, (dict, list)):
            return value
    return None


def _extract_extensions(data: Mapping[str, Any]) -> dict[str, Any]:
    extensions = data.get("extensions")
    if isinstance(extensions, Mapping):
        return dict(extensions)

    known = {
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
        "character_book",
        "lorebook",
        "world_info",
        "world",
    }
    return {key: value for key, value in data.items() if key not in known}


def _normalize_source_card(
    payload: dict[str, Any],
    *,
    source_key: str | None,
) -> CharacterCardImportResult:
    source_payload = dict(payload)
    if "data" not in source_payload and "name" in source_payload:
        source_payload = {
            "spec": source_payload.get("spec"),
            "spec_version": source_payload.get("spec_version"),
            "data": source_payload,
        }

    try:
        source = SourceCharacterCard.model_validate(source_payload)
    except ValidationError as exc:
        raise _safe_parse_error("required card fields are missing or invalid") from exc

    data = source.data.model_dump(mode="python")
    warnings: list[str] = []
    tags = _string_tuple(data.get("tags"), field_name="tags", warnings=warnings)
    alternate_greetings = _string_tuple(
        data.get("alternate_greetings"),
        field_name="alternate_greetings",
        warnings=warnings,
    )
    lorebook_json = _lorebook_from_payload(source_payload, data)
    prompt_excluded_fields: tuple[str, ...] = ()
    lorebook_status: LorebookStatus = "absent"
    if lorebook_json is not None:
        lorebook_status = "present_not_used_in_v1"
        warnings.append("Lorebook present - not used in v1")
        prompt_excluded_fields = ("lorebook_json",)

    character = CharacterCard(
        name=source.data.name.strip(),
        description=source.data.description,
        personality=source.data.personality,
        scenario=source.data.scenario,
        first_mes=source.data.first_mes,
        mes_example=source.data.mes_example,
        system_prompt=source.data.system_prompt,
        creator_notes=source.data.creator_notes,
        character_notes=source.data.character_notes,
        tags=tags,
        alternate_greetings=alternate_greetings,
        post_history_instructions=source.data.post_history_instructions,
        creator=source.data.creator,
        character_version=source.data.character_version,
        extensions=_extract_extensions(data),
    )
    if not character.name:
        raise _safe_parse_error("character name must not be empty")

    return CharacterCardImportResult(
        source_format=_source_format(source_payload, source_key),
        source_key=source_key,
        character=character,
        raw_source_json=payload,
        lorebook_json=lorebook_json,
        lorebook_status=lorebook_status,
        warnings=tuple(warnings),
        prompt_excluded_fields=prompt_excluded_fields,
    )


def _decode_png_card_json(encoded: str) -> bytes:
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _safe_parse_error("PNG card metadata is malformed") from exc
    if len(decoded) > MAX_PNG_CARD_JSON_BYTES:
        raise _safe_parse_error("PNG card metadata is too large")
    return decoded


def _parse_png_card(content: bytes) -> tuple[dict[str, Any], str]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "PNG":
                raise _safe_parse_error("PNG upload is not a valid PNG image")
            metadata = dict(image.text)
    except CharacterCardParseError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise _safe_parse_error("PNG upload cannot be read safely") from exc

    for key in PNG_TEXT_CHUNK_KEYS_IN_ORDER:
        encoded = metadata.get(key)
        if encoded is None:
            continue
        decoded = _decode_png_card_json(encoded)
        return _json_object_from_bytes(decoded), key

    raise _safe_parse_error("PNG does not contain a supported character card chunk")


def parse_character_card_bytes(
    content: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> CharacterCardImportResult:
    """Parse JSON or PNG-embedded SillyTavern card bytes into RayMe storage fields."""

    if len(content) > MAX_CARD_UPLOAD_BYTES:
        raise _safe_parse_error("upload is too large")

    lower_filename = (filename or "").lower()
    is_png = (
        content.startswith(PNG_SIGNATURE)
        or lower_filename.endswith(".png")
        or (content_type or "").lower() == "image/png"
    )
    if is_png:
        payload, source_key = _parse_png_card(content)
    else:
        payload = _json_object_from_bytes(content)
        source_key = None

    return _normalize_source_card(payload, source_key=source_key)


__all__ = [
    "CardSourceFormat",
    "CharacterCard",
    "CharacterCardImportResult",
    "CharacterCardParseError",
    "CharacterDeleteRepository",
    "CharacterDeleteResult",
    "LorebookStatus",
    "MAX_CARD_UPLOAD_BYTES",
    "MAX_PNG_CARD_JSON_BYTES",
    "PNG_TEXT_CHUNK_KEYS_IN_ORDER",
    "UNTRUSTED_CARD_FIELDS",
    "delete_character_preserving_thread_snapshots",
    "parse_character_card_bytes",
]
