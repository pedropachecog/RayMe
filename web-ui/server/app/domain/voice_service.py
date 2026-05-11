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
VOXCPM2_ENGINE_ID = "voxcpm2"
VOXCPM2_WARNING_REFERENCE_ONLY_WITHOUT_TRANSCRIPT = "voxcpm2_reference_only_without_transcript"
VOXCPM2_DEFAULT_SETTINGS = {
    "cloning_mode": "reference_only",
    "style_prompt": "",
    "cfg_value": 2.0,
    "inference_timesteps": 10,
    "normalize": False,
    "denoise": False,
}
VOXCPM2_CLONING_MODES = {"reference_only", "transcript_guided"}
VOXCPM2_STYLE_PROMPT_MAX_LENGTH = 300
VOXCPM2_CFG_VALUE_MIN = 1.0
VOXCPM2_CFG_VALUE_MAX = 3.0
VOXCPM2_INFERENCE_TIMESTEPS_MIN = 4
VOXCPM2_INFERENCE_TIMESTEPS_MAX = 30


class VoiceAssetNotFoundError(LookupError):
    """Raised when a requested voice asset is missing."""


class VoiceNotFoundError(LookupError):
    """Raised when a requested voice is missing."""


class VoiceReferencedError(ValueError):
    """Raised when deleting a referenced voice without explicit force."""

    def __init__(self, referents: list[dict[str, str]]) -> None:
        super().__init__("Voice is referenced")
        self.referents = referents


class VoiceSynthesisFailedError(RuntimeError):
    """Raised when a voice test-play request does not produce audio."""


class VoiceMetadataValidationError(ValueError):
    """Raised when durable voice metadata is not bounded for storage."""


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
        payload = _with_voxcpm2_payload_settings(payload)
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
        metadata = normalize_voice_metadata(payload.get("metadata"))
        metadata["sample_asset_id"] = asset.id
        voice = Voice(
            id=new_voice_id(),
            name=str(payload["name"]),
            default_engine=str(payload["default_engine"]),
            reference_transcript=payload.get("reference_transcript"),
            metadata_json=metadata,
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
        if "metadata" in payload and payload["metadata"] is not None:
            existing_metadata = dict(voice.metadata_json or {})
            voice.metadata_json = merge_voice_metadata(existing_metadata, payload["metadata"])
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
        engine_settings, warnings = _voxcpm2_settings_for_engine(
            engine,
            metadata=voice.metadata_json,
            reference_transcript=voice.reference_transcript,
        )
        result = await self.processor.test_play(
            voice_id=voice.id,
            text=payload.get("text", ""),
            engine=engine,
            reference_transcript=voice.reference_transcript,
            engine_settings=engine_settings,
            warnings=warnings,
            content=sample.path.read_bytes(),
            content_type=asset.content_type,
            speech_speed=payload.get("speech_speed", _voice_speech_speed(voice)),
        )
        audio_url = result.get("audio_url")
        audio_base64 = result.get("audio_base64")
        if result.get("status") == "tts_failed" or not (audio_url or audio_base64):
            raise VoiceSynthesisFailedError("Voice test-play did not produce generated audio")
        return {
            "voice_id": voice.id,
            "engine": engine,
            "audio_url": audio_url,
            "audio_base64": audio_base64,
            "content_type": result.get("content_type"),
            "duration_ms": result.get("duration_ms"),
            "warnings": list(result.get("warnings") or warnings),
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
    "VoiceSynthesisFailedError",
    "VoiceMetadataValidationError",
    "VoiceService",
    "merge_voice_metadata",
    "new_voice_asset_id",
    "new_voice_id",
    "normalize_voice_metadata",
]


def normalize_voice_metadata(raw_metadata: Any) -> dict[str, Any]:
    if raw_metadata is None:
        return {}
    if not isinstance(raw_metadata, dict):
        raise VoiceMetadataValidationError("Voice metadata must be an object")

    metadata = dict(raw_metadata)
    if "engine_settings" not in metadata:
        return metadata

    engine_settings = metadata.get("engine_settings")
    if engine_settings is None:
        metadata["engine_settings"] = {}
        return metadata
    if not isinstance(engine_settings, dict):
        raise VoiceMetadataValidationError("metadata.engine_settings must be an object")

    normalized_engine_settings = dict(engine_settings)
    if VOXCPM2_ENGINE_ID in normalized_engine_settings:
        normalized_engine_settings[VOXCPM2_ENGINE_ID] = normalize_voxcpm2_engine_settings(
            normalized_engine_settings[VOXCPM2_ENGINE_ID]
        )
    metadata["engine_settings"] = normalized_engine_settings
    return metadata


def merge_voice_metadata(existing_metadata: dict[str, Any], patch_metadata: Any) -> dict[str, Any]:
    normalized_patch = normalize_voice_metadata(patch_metadata)
    if "engine_settings" not in normalized_patch:
        return {**existing_metadata, **normalized_patch}

    existing_engine_settings = existing_metadata.get("engine_settings")
    if not isinstance(existing_engine_settings, dict):
        existing_engine_settings = {}

    patch_engine_settings = normalized_patch.get("engine_settings")
    if not isinstance(patch_engine_settings, dict):
        patch_engine_settings = {}

    merged = {**existing_metadata, **normalized_patch}
    merged["engine_settings"] = {**existing_engine_settings, **patch_engine_settings}
    return merged


def normalize_voxcpm2_engine_settings(raw_settings: Any) -> dict[str, Any]:
    if raw_settings is None:
        raw_settings = {}
    if not isinstance(raw_settings, dict):
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2 must be an object")

    settings = {**VOXCPM2_DEFAULT_SETTINGS, **dict(raw_settings)}
    cloning_mode = settings["cloning_mode"]
    if cloning_mode not in VOXCPM2_CLONING_MODES:
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2.cloning_mode is invalid")

    style_prompt = settings["style_prompt"]
    if style_prompt is None:
        style_prompt = ""
    if not isinstance(style_prompt, str):
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2.style_prompt must be text")
    if len(style_prompt) > VOXCPM2_STYLE_PROMPT_MAX_LENGTH:
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2.style_prompt is too long")

    cfg_value = settings["cfg_value"]
    if isinstance(cfg_value, bool) or not isinstance(cfg_value, int | float):
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2.cfg_value must be numeric")
    cfg_value = float(cfg_value)
    if not VOXCPM2_CFG_VALUE_MIN <= cfg_value <= VOXCPM2_CFG_VALUE_MAX:
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2.cfg_value is out of range")

    inference_timesteps = settings["inference_timesteps"]
    if isinstance(inference_timesteps, bool) or not isinstance(inference_timesteps, int):
        raise VoiceMetadataValidationError(
            "metadata.engine_settings.voxcpm2.inference_timesteps must be an integer"
        )
    if not VOXCPM2_INFERENCE_TIMESTEPS_MIN <= inference_timesteps <= VOXCPM2_INFERENCE_TIMESTEPS_MAX:
        raise VoiceMetadataValidationError(
            "metadata.engine_settings.voxcpm2.inference_timesteps is out of range"
        )

    normalize = settings["normalize"]
    denoise = settings["denoise"]
    if not isinstance(normalize, bool):
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2.normalize must be boolean")
    if not isinstance(denoise, bool):
        raise VoiceMetadataValidationError("metadata.engine_settings.voxcpm2.denoise must be boolean")

    return {
        "cloning_mode": cloning_mode,
        "style_prompt": style_prompt,
        "cfg_value": cfg_value,
        "inference_timesteps": inference_timesteps,
        "normalize": normalize,
        "denoise": denoise,
    }


def _with_voxcpm2_payload_settings(payload: dict[str, Any]) -> dict[str, Any]:
    engine = payload.get("engine") or payload.get("default_engine")
    metadata = payload.get("metadata")
    engine_settings, warnings = _voxcpm2_settings_for_engine(
        engine,
        metadata=metadata,
        reference_transcript=payload.get("reference_transcript"),
    )
    return {**payload, "engine_id": engine, "engine_settings": engine_settings, "warnings": warnings}


def _voxcpm2_settings_for_engine(
    engine: Any,
    *,
    metadata: Any,
    reference_transcript: Any,
) -> tuple[dict[str, Any], list[str]]:
    if engine != VOXCPM2_ENGINE_ID:
        return {}, []

    normalized_metadata = normalize_voice_metadata(metadata)
    engine_settings = normalized_metadata.get("engine_settings")
    voxcpm2_settings: dict[str, Any] = dict(VOXCPM2_DEFAULT_SETTINGS)
    if isinstance(engine_settings, dict) and VOXCPM2_ENGINE_ID in engine_settings:
        voxcpm2_settings = normalize_voxcpm2_engine_settings(engine_settings[VOXCPM2_ENGINE_ID])

    warnings: list[str] = []
    if voxcpm2_settings["cloning_mode"] == "transcript_guided" and not str(reference_transcript or "").strip():
        voxcpm2_settings = {**voxcpm2_settings, "cloning_mode": "reference_only"}
        warnings.append(VOXCPM2_WARNING_REFERENCE_ONLY_WITHOUT_TRANSCRIPT)
    return {VOXCPM2_ENGINE_ID: voxcpm2_settings}, warnings


def _voice_speech_speed(voice: Voice) -> float:
    metadata = dict(voice.metadata_json or {})
    value = metadata.get("speech_speed")
    if isinstance(value, int | float):
        return float(value)

    engine_settings = metadata.get("engine_settings")
    if isinstance(engine_settings, dict):
        engine_value = engine_settings.get(voice.default_engine)
        if isinstance(engine_value, dict):
            speed = engine_value.get("speech_speed")
            if isinstance(speed, int | float):
                return float(speed)

    return 1.0
