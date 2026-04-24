"""Durable voice storage service for Voice Lab and Voice Library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.voice_assets import (
    VoiceSampleValidationError,
    validate_voice_sample_upload,
    write_voice_sample_blob,
)
from app.storage.models import Character, Voice, VoiceAsset, utc_now

ACTIVE_SAMPLE_KIND = "sample"


class VoiceAssetNotFoundError(LookupError):
    """Raised when a requested voice asset is missing."""


class VoiceNotFoundError(LookupError):
    """Raised when a requested voice is missing."""


class VoiceReferencedError(ValueError):
    """Raised when deleting a referenced voice without explicit force."""

    def __init__(self, referents: list[dict[str, str]]) -> None:
        super().__init__("Voice is referenced")
        self.referents = referents


@dataclass(frozen=True, slots=True)
class VoiceSampleBlob:
    path: Path
    content_type: str | None
    storage_path: str


def new_voice_id() -> str:
    return f"voice_{uuid4().hex}"


def new_voice_asset_id() -> str:
    return f"voice_asset_{uuid4().hex}"


class VoiceService:
    def __init__(self, session: AsyncSession, voice_blob_dir: Path, processor: object) -> None:
        self.session = session
        self.voice_blob_dir = voice_blob_dir
        self.processor = processor

    async def upload_sample(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, Any]:
        sample = validate_voice_sample_upload(filename, content_type, content)
        asset_id = new_voice_asset_id()
        blob_path = write_voice_sample_blob(self.voice_blob_dir, asset_id, sample)
        asset = VoiceAsset(
            id=asset_id,
            voice_id=None,
            asset_kind=ACTIVE_SAMPLE_KIND,
            storage_path=blob_path.name,
            content_type=sample.content_type,
            byte_size=sample.byte_size,
            sha256=sample.sha256,
            duration_seconds=sample.duration_seconds,
            sample_rate_hz=sample.sample_rate_hz,
            channel_count=sample.channel_count,
        )
        self.session.add(asset)
        await self.session.commit()
        return self.asset_to_response(asset, warnings=sample.warnings)

    async def transcribe_asset(self, asset_id: str) -> dict[str, Any]:
        asset = await self.get_asset(asset_id)
        sample = await self.sample_blob(asset_id)
        result = await self.processor.transcribe(
            asset_id=asset.id,
            content=sample.path.read_bytes(),
            content_type=asset.content_type,
        )
        return {
            "asset_id": asset.id,
            "reference_transcript": result.get("transcript", ""),
            "reference_transcript_editable": True,
            "language": result.get("language"),
            "confidence": result.get("confidence"),
        }

    async def preview_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
        asset = await self.get_asset(str(payload.get("asset_id", "")))
        sample = await self.sample_blob(asset.id)
        preview = getattr(self.processor, "synthesize_preview", None)
        if preview is None:
            preview = self.processor.preview
        return await preview(
            **payload,
            content=sample.path.read_bytes(),
            content_type=asset.content_type,
        )

    async def save_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
        asset = await self.get_asset(str(payload["asset_id"]))
        voice = Voice(
            id=new_voice_id(),
            name=str(payload["name"]),
            default_engine=str(payload["default_engine"]),
            reference_transcript=payload.get("reference_transcript"),
            metadata_json={"sample_asset_id": asset.id},
            deleted_at=None,
        )
        asset.voice_id = voice.id
        self.session.add(voice)
        await self.session.commit()
        await self.session.refresh(voice)
        await self.session.refresh(asset)
        return self.voice_to_response(voice, asset)

    async def list_voices(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Voice).where(Voice.deleted_at.is_(None)).order_by(Voice.created_at)
        )
        voices = list(result.scalars())
        return [await self.voice_detail(voice) for voice in voices]

    async def get_voice(self, voice_id: str) -> dict[str, Any]:
        return await self.voice_detail(await self._voice(voice_id, include_deleted=True))

    async def rename_voice(self, voice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        voice = await self._voice(voice_id)
        if "name" in payload and payload["name"] is not None:
            voice.name = str(payload["name"])
        if "default_engine" in payload and payload["default_engine"] is not None:
            voice.default_engine = str(payload["default_engine"])
        if "reference_transcript" in payload:
            voice.reference_transcript = payload["reference_transcript"]
        await self.session.commit()
        await self.session.refresh(voice)
        return await self.voice_detail(voice)

    async def delete_voice(self, voice_id: str, *, force: bool) -> dict[str, Any]:
        voice = await self._voice(voice_id)
        referents = await self.referents_for_voice(voice_id)
        if referents and not force:
            raise VoiceReferencedError(referents)

        voice.deleted_at = utc_now()
        await self.session.commit()
        await self.session.refresh(voice)
        return {
            "voice_id": voice.id,
            "deleted_at": voice.deleted_at.isoformat() if voice.deleted_at else None,
            "strategy": "soft_delete",
            "referents": referents,
            "tombstone": {"name": voice.name},
        }

    async def test_play_voice(self, voice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        voice = await self._voice(voice_id)
        asset = await self.asset_for_voice(voice.id)
        if asset is None:
            raise VoiceAssetNotFoundError(voice.id)
        sample = await self.sample_blob(asset.id)
        engine = voice.default_engine if payload.get("use_default_engine", True) else payload.get("engine")
        result = await self.processor.test_play(
            voice_id=voice.id,
            text=payload.get("text", ""),
            engine=engine,
            content=sample.path.read_bytes(),
            content_type=asset.content_type,
        )
        return {
            "voice_id": voice.id,
            "engine": engine,
            "audio_url": result.get("audio_url"),
        }

    async def sample_blob(self, asset_id: str) -> VoiceSampleBlob:
        asset = await self.get_asset(asset_id)
        storage_name = Path(asset.storage_path).name
        if storage_name != asset.storage_path:
            raise VoiceAssetNotFoundError(asset_id)
        path = self.voice_blob_dir / storage_name
        if not path.is_file():
            raise VoiceAssetNotFoundError(asset_id)
        return VoiceSampleBlob(path=path, content_type=asset.content_type, storage_path=asset.storage_path)

    async def get_asset(self, asset_id: str) -> VoiceAsset:
        result = await self.session.execute(select(VoiceAsset).where(VoiceAsset.id == asset_id))
        asset = result.scalar_one_or_none()
        if asset is None:
            raise VoiceAssetNotFoundError(asset_id)
        return asset

    async def asset_for_voice(self, voice_id: str) -> VoiceAsset | None:
        result = await self.session.execute(
            select(VoiceAsset)
            .where(VoiceAsset.voice_id == voice_id, VoiceAsset.asset_kind == ACTIVE_SAMPLE_KIND)
            .order_by(VoiceAsset.created_at.desc())
        )
        return result.scalars().first()

    async def voice_detail(self, voice: Voice) -> dict[str, Any]:
        return self.voice_to_response(voice, await self.asset_for_voice(voice.id))

    async def referents_for_voice(self, voice_id: str) -> list[dict[str, str]]:
        result = await self.session.execute(
            select(Character).where(
                Character.default_voice_id == voice_id,
                Character.deleted_at.is_(None),
            )
        )
        return [
            {"kind": "character", "id": character.id, "name": character.name}
            for character in result.scalars()
        ]

    async def _voice(self, voice_id: str, *, include_deleted: bool = False) -> Voice:
        criteria = [Voice.id == voice_id]
        if not include_deleted:
            criteria.append(Voice.deleted_at.is_(None))
        result = await self.session.execute(select(Voice).where(*criteria))
        voice = result.scalar_one_or_none()
        if voice is None:
            raise VoiceNotFoundError(voice_id)
        return voice

    def asset_to_response(self, asset: VoiceAsset, *, warnings: list[str] | None = None) -> dict[str, Any]:
        return {
            "asset_id": asset.id,
            "voice_id": asset.voice_id,
            "asset_kind": asset.asset_kind,
            "storage_path": asset.storage_path,
            "content_type": asset.content_type,
            "byte_size": asset.byte_size,
            "sha256": asset.sha256,
            "duration_seconds": asset.duration_seconds,
            "sample_rate_hz": asset.sample_rate_hz,
            "channel_count": asset.channel_count,
            "warnings": list(warnings or []),
        }

    def voice_to_response(self, voice: Voice, asset: VoiceAsset | None) -> dict[str, Any]:
        response = {
            "voice_id": voice.id,
            "asset_id": asset.id if asset else None,
            "name": voice.name,
            "default_engine": voice.default_engine,
            "reference_transcript": voice.reference_transcript,
            "metadata": dict(voice.metadata_json or {}),
            "status": "deleted" if voice.deleted_at else "available",
            "deleted_at": voice.deleted_at.isoformat() if voice.deleted_at else None,
            "created_at": voice.created_at.isoformat() if voice.created_at else None,
            "updated_at": voice.updated_at.isoformat() if voice.updated_at else None,
        }
        if voice.deleted_at is not None:
            response["unavailable_label"] = "Voice unavailable"
        return response


__all__ = [
    "ACTIVE_SAMPLE_KIND",
    "VoiceAssetNotFoundError",
    "VoiceNotFoundError",
    "VoiceReferencedError",
    "VoiceSampleValidationError",
    "VoiceService",
    "new_voice_asset_id",
    "new_voice_id",
]
