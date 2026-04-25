"""Character CRUD, import/export, and portrait storage services."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.card_export import export_character_v2_json
from app.domain.cards import (
    CharacterCard,
    CharacterCardImportResult,
    CharacterDeleteResult,
    parse_character_card_bytes,
)
from app.domain.portraits import validate_portrait_upload
from app.storage.blob_store import atomic_write_blob
from app.storage.models import Character, CharacterAsset, Message, Thread, Voice, utc_now

ACTIVE_PORTRAIT_KIND = "portrait"
HISTORICAL_PORTRAIT_KIND = "portrait_history"

EDITOR_FIELD_NAMES = (
    "name",
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "system_prompt",
    "creator_notes",
    "character_notes",
    "post_history_instructions",
    "creator",
    "character_version",
    "default_voice_id",
)


class CharacterNotFoundError(LookupError):
    """Raised when a requested character does not exist or is deleted."""


class DefaultVoiceNotFoundError(LookupError):
    """Raised when a character write references a missing or deleted voice."""


@dataclass(frozen=True)
class PortraitBlob:
    path: Path
    content_type: str
    asset_id: str
    storage_path: str


def new_character_id() -> str:
    return f"char_{uuid4().hex}"


def new_asset_id() -> str:
    return f"asset_{uuid4().hex}"


def portrait_url_for_asset(character_id: str, asset: CharacterAsset | None) -> str | None:
    if asset is None:
        return None

    encoded_character_id = quote(character_id, safe="")
    encoded_asset_id = quote(asset.id, safe="")
    return f"/api/characters/{encoded_character_id}/portrait?asset_id={encoded_asset_id}"


class CharacterService:
    def __init__(self, session: AsyncSession, portrait_blob_dir: Path) -> None:
        self.session = session
        self.portrait_blob_dir = portrait_blob_dir

    async def list_characters(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Character).where(Character.deleted_at.is_(None)).order_by(Character.created_at)
        )
        characters = list(result.scalars())
        return [await self.character_to_response(character) for character in characters]

    async def create_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        character = Character(id=new_character_id(), **await self._character_columns(payload))
        self.session.add(character)
        await self.session.commit()
        await self.session.refresh(character)
        return await self.character_to_response(character)

    async def get_character_response(self, character_id: str) -> dict[str, Any]:
        character = await self.get_character(character_id)
        return await self.character_to_response(character)

    async def update_character(self, character_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        character = await self.get_character(character_id)
        for key, value in (await self._character_columns(payload)).items():
            setattr(character, key, value)
        await self.session.commit()
        await self.session.refresh(character)
        return await self.character_to_response(character)

    async def delete_character(self, character_id: str) -> CharacterDeleteResult:
        character = await self.get_character(character_id)
        character.deleted_at = utc_now()
        result = await self.session.execute(
            select(Thread.id).where(Thread.character_id == character_id)
        )
        preserved_thread_ids = tuple(result.scalars())
        await self.session.commit()
        return CharacterDeleteResult(
            character_id=character_id,
            deleted_at=character.deleted_at.isoformat(),
            preserved_thread_ids=preserved_thread_ids,
            strategy="soft_delete",
        )

    async def import_character(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> dict[str, Any]:
        import_result = parse_character_card_bytes(
            content,
            filename=filename,
            content_type=content_type,
        )
        payload = _payload_from_import(import_result)
        character_response = await self.create_character(payload)
        if import_result.source_format.endswith("_png"):
            character_response = await self.replace_portrait(
                character_response["id"],
                filename="imported-card.png",
                content=content,
            )
        response = dict(character_response)
        response["source_format"] = import_result.source_format
        response["source_key"] = import_result.source_key
        response["warnings"] = list(import_result.warnings)
        response["character"] = character_response
        return response

    async def export_character_v2(self, character_id: str) -> dict[str, Any]:
        character = await self.get_character(character_id)
        return export_character_v2_json(_export_mapping(character))

    async def replace_portrait(
        self,
        character_id: str,
        *,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:
        character = await self.get_character(character_id)
        portrait = validate_portrait_upload(filename, content)
        asset_id = new_asset_id()
        final_name = f"{asset_id}{portrait.extension}"
        blob_path = atomic_write_blob(self.portrait_blob_dir, final_name, portrait.content)

        await self._archive_active_portraits(character_id)
        asset = CharacterAsset(
            id=asset_id,
            character_id=character.id,
            asset_kind=ACTIVE_PORTRAIT_KIND,
            storage_path=blob_path.name,
            content_type=portrait.content_type,
            byte_size=len(portrait.content),
            sha256=hashlib.sha256(portrait.content).hexdigest(),
        )
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(character)
        return await self.character_to_response(character)

    async def active_portrait_blob(self, character_id: str) -> PortraitBlob | None:
        await self.get_character(character_id)
        active_portrait = await self._active_portrait(character_id)
        if active_portrait is None:
            return None

        storage_name = Path(active_portrait.storage_path).name
        if storage_name != active_portrait.storage_path:
            return None

        path = self.portrait_blob_dir / storage_name
        if not path.is_file():
            return None

        return PortraitBlob(
            path=path,
            content_type=active_portrait.content_type,
            asset_id=active_portrait.id,
            storage_path=active_portrait.storage_path,
        )

    async def delete_portrait(self, character_id: str) -> dict[str, Any]:
        character = await self.get_character(character_id)
        await self._archive_active_portraits(character_id)
        await self.session.commit()
        await self.session.refresh(character)
        return await self.character_to_response(character)

    async def get_character(self, character_id: str) -> Character:
        result = await self.session.execute(
            select(Character).where(
                Character.id == character_id,
                Character.deleted_at.is_(None),
            )
        )
        character = result.scalar_one_or_none()
        if character is None:
            raise CharacterNotFoundError(character_id)
        return character

    async def character_to_response(self, character: Character) -> dict[str, Any]:
        active_portrait = await self._active_portrait(character.id)
        return {
            "id": character.id,
            "name": character.name,
            "description": character.description,
            "personality": character.personality,
            "scenario": character.scenario,
            "first_mes": character.first_mes,
            "mes_example": character.mes_example,
            "system_prompt": character.system_prompt,
            "creator_notes": character.creator_notes,
            "character_notes": character.character_notes,
            "tags": list(character.tags_json or []),
            "alternate_greetings": list(character.alternate_greetings_json or []),
            "post_history_instructions": character.post_history_instructions,
            "creator": character.creator,
            "character_version": character.character_version,
            "raw_source_json": character.raw_source_json,
            "lorebook_json": character.lorebook_json,
            "lorebook_present": character.lorebook_json is not None,
            "portrait_url": portrait_url_for_asset(character.id, active_portrait),
            "portrait_path": (
                active_portrait.storage_path if active_portrait else None
            ),
            "portrait_asset_id": active_portrait.id if active_portrait else None,
            "portrait_storage_path": active_portrait.storage_path if active_portrait else None,
            "portrait_mime_type": active_portrait.content_type if active_portrait else None,
            "portrait_size_bytes": active_portrait.byte_size if active_portrait else None,
            "portrait_updated_at": (
                active_portrait.updated_at.isoformat()
                if active_portrait and active_portrait.updated_at
                else None
            ),
            "default_voice_id": character.default_voice_id,
            "default_voice": await self._default_voice_response(character.default_voice_id),
            "created_at": character.created_at.isoformat() if character.created_at else None,
            "updated_at": character.updated_at.isoformat() if character.updated_at else None,
            "deleted_at": character.deleted_at.isoformat() if character.deleted_at else None,
        }

    async def _default_voice_response(self, voice_id: str | None) -> dict[str, str] | None:
        if voice_id is None:
            return None

        voice = await self.session.get(Voice, voice_id)
        if voice is None:
            return {
                "voice_id": voice_id,
                "name": "Voice unavailable",
                "status": "unavailable",
                "label": "Voice unavailable",
            }
        if voice.deleted_at is not None:
            return {
                "voice_id": voice.id,
                "name": voice.name,
                "status": "unavailable",
                "label": "Voice unavailable",
            }
        return {
            "voice_id": voice.id,
            "name": voice.name,
            "status": "available",
            "label": voice.name,
        }

    async def _active_portrait(self, character_id: str) -> CharacterAsset | None:
        result = await self.session.execute(
            select(CharacterAsset)
            .where(
                CharacterAsset.character_id == character_id,
                CharacterAsset.asset_kind == ACTIVE_PORTRAIT_KIND,
            )
            .order_by(CharacterAsset.created_at.desc())
        )
        return result.scalars().first()

    async def _archive_active_portraits(self, character_id: str) -> None:
        result = await self.session.execute(
            select(CharacterAsset).where(
                CharacterAsset.character_id == character_id,
                CharacterAsset.asset_kind == ACTIVE_PORTRAIT_KIND,
            )
        )
        for asset in result.scalars():
            asset.asset_kind = HISTORICAL_PORTRAIT_KIND

    async def _character_columns(self, payload: dict[str, Any]) -> dict[str, Any]:
        columns = {field: payload.get(field) for field in EDITOR_FIELD_NAMES}
        columns["default_voice_id"] = await self._validated_default_voice_id(
            columns["default_voice_id"]
        )
        tags = payload.get("tags")
        alternate_greetings = payload.get("alternate_greetings")
        columns["tags_json"] = list(tags) if isinstance(tags, list) else []
        columns["alternate_greetings_json"] = (
            list(alternate_greetings) if isinstance(alternate_greetings, list) else []
        )
        raw_source_json = payload.get("raw_source_json")
        lorebook_json = payload.get("lorebook_json")
        columns["raw_source_json"] = raw_source_json if isinstance(raw_source_json, dict) else None
        columns["lorebook_json"] = lorebook_json if isinstance(lorebook_json, (dict, list)) else None
        return columns

    async def _validated_default_voice_id(self, voice_id: object) -> str | None:
        if not isinstance(voice_id, str) or not voice_id:
            return None

        voice = await self.session.get(Voice, voice_id)
        if voice is None or voice.deleted_at is not None:
            raise DefaultVoiceNotFoundError(voice_id)
        return voice.id


def _payload_from_import(import_result: CharacterCardImportResult) -> dict[str, Any]:
    character = import_result.character
    return {
        **_payload_from_card(character),
        "raw_source_json": dict(import_result.raw_source_json),
        "lorebook_json": import_result.lorebook_json,
    }


def _payload_from_card(character: CharacterCard) -> dict[str, Any]:
    return {
        "name": character.name,
        "description": character.description,
        "personality": character.personality,
        "scenario": character.scenario,
        "first_mes": character.first_mes,
        "mes_example": character.mes_example,
        "system_prompt": character.system_prompt,
        "creator_notes": character.creator_notes,
        "character_notes": character.character_notes,
        "tags": list(character.tags),
        "alternate_greetings": list(character.alternate_greetings),
        "post_history_instructions": character.post_history_instructions,
        "creator": character.creator,
        "character_version": character.character_version,
    }


def _export_mapping(character: Character) -> dict[str, Any]:
    return {
        "name": character.name,
        "description": character.description,
        "personality": character.personality,
        "scenario": character.scenario,
        "first_mes": character.first_mes,
        "mes_example": character.mes_example,
        "system_prompt": character.system_prompt,
        "creator_notes": character.creator_notes,
        "character_notes": character.character_notes,
        "tags": character.tags_json or [],
        "alternate_greetings": character.alternate_greetings_json or [],
        "post_history_instructions": character.post_history_instructions,
        "creator": character.creator,
        "character_version": character.character_version,
        "raw_source_json": character.raw_source_json,
        "lorebook_json": character.lorebook_json,
    }


async def character_has_messages(session: AsyncSession, character_id: str) -> bool:
    result = await session.execute(
        select(Message.id)
        .join(Thread, Message.thread_id == Thread.id)
        .where(Thread.character_id == character_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


__all__ = [
    "ACTIVE_PORTRAIT_KIND",
    "CharacterNotFoundError",
    "CharacterService",
    "DefaultVoiceNotFoundError",
    "HISTORICAL_PORTRAIT_KIND",
    "PortraitBlob",
    "character_has_messages",
    "portrait_url_for_asset",
]
