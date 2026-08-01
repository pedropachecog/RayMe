"""Durable voice storage service for Voice Lab and Voice Library."""

from __future__ import annotations

import hashlib
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
QWEN3_ENGINE_ID = "qwen3_1_7b"
LEGACY_QWEN3_ENGINE_ID = "qwen3_0_6b"
SUPPORTED_VOICE_ENGINE_IDS = {
    "f5",
    "F5-TTS",
    "xtts_v2",
    "XTTS v2",
    QWEN3_ENGINE_ID,
    "luxtts",
    "LuxTTS",
    "chatterbox_turbo",
    "Chatterbox Turbo",
    "tada_1b",
    "TADA 1B",
    "voxcpm2",
}
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
RETIRED_QWEN_AUTHORIZATION_METADATA_KEY = "qwen3_authorization"
LEGACY_QWEN_AUTHORIZATION_METADATA_KEY = "authorization"
LEGACY_QWEN_AUTHORIZATION_SOURCE = "phase09_hardware_tracer"


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


class VoicePromptInvalidationError(RuntimeError):
    """Raised when backend prompt eviction cannot be confirmed."""


@dataclass(frozen=True, slots=True)
class VoiceSampleBlob:
    path: Path
    content_type: str | None
    storage_path: str


@dataclass(frozen=True, slots=True)
class SavedQwenReference:
    voice_key: str
    reference_bytes: bytes
    reference_transcript: str
    content_type: str | None


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
        reference_bytes = sample.path.read_bytes()
        engine = payload.get("engine") or payload.get("default_engine")
        if engine is not None:
            engine = normalize_voice_engine_id(engine)
            payload = {**payload, "engine": engine, "default_engine": engine}
        if engine == QWEN3_ENGINE_ID:
            _require_qwen3_target(payload.get("preview_text"))
            _validate_asset_bytes(asset, reference_bytes)
            _require_qwen3_transcript(payload.get("reference_transcript"))
            payload = _qwen3_processor_payload(
                payload,
                owner_id=asset.id,
            )
        payload = _with_voxcpm2_payload_settings(payload)
        preview = getattr(self.processor, "synthesize_preview", None)
        if preview is None:
            preview = self.processor.preview
        return await preview(
            **payload,
            content=reference_bytes,
            content_type=asset.content_type,
        )

    async def preparation_status(self) -> dict[str, Any]:
        status_reader = getattr(self.processor, "preparation_status", None)
        if not callable(status_reader):
            raise VoiceSynthesisFailedError("Voice preparation status is unavailable")
        result = await status_reader()
        if not isinstance(result, dict):
            raise VoiceSynthesisFailedError("Voice preparation status is unavailable")
        return result

    async def save_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
        asset = await self.get_asset(str(payload["asset_id"]))
        sample = await self.sample_blob(asset.id)
        reference_bytes = sample.path.read_bytes()
        _validate_asset_bytes(asset, reference_bytes)
        engine_id = normalize_voice_engine_id(payload["default_engine"])
        metadata = normalize_voice_metadata(
            payload.get("metadata"),
            engine_id=engine_id,
        )
        metadata["sample_asset_id"] = asset.id
        if engine_id == QWEN3_ENGINE_ID:
            _require_qwen3_transcript(payload.get("reference_transcript"))
        voice = Voice(
            id=new_voice_id(),
            name=str(payload["name"]),
            default_engine=engine_id,
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
            voice.metadata_json = merge_voice_metadata(
                existing_metadata,
                payload["metadata"],
                engine_id=voice.default_engine,
            )
        await self.session.commit()
        await self.session.refresh(voice)
        return await self.voice_detail(voice)

    async def delete_voice(self, voice_id: str, *, force: bool) -> dict[str, Any]:
        voice = await self._voice(voice_id, include_deleted=True)
        referents = await self.referents_for_voice(voice_id)
        if voice.deleted_at is not None:
            return _voice_deletion_response(voice, referents=referents)
        if referents and not force:
            raise VoiceReferencedError(referents)

        prompt_invalidation: dict[str, Any] | None = None
        if normalize_voice_engine_id(voice.default_engine) == QWEN3_ENGINE_ID:
            owner_key = qwen3_voice_key(voice.id)
            invalidate = getattr(self.processor, "invalidate_qwen_prompt", None)
            if not callable(invalidate):
                raise VoicePromptInvalidationError(
                    "Voice prompt removal failed"
                )
            try:
                raw_invalidation = await invalidate(owner_key)
                prompt_invalidation = _qwen3_invalidation_result(
                    raw_invalidation,
                    owner_key=owner_key,
                )
            except VoicePromptInvalidationError:
                raise
            except Exception as exc:
                raise VoicePromptInvalidationError(
                    "Voice prompt removal failed"
                ) from exc

        voice.deleted_at = utc_now()
        await self.session.commit()
        await self.session.refresh(voice)
        return _voice_deletion_response(
            voice,
            referents=referents,
            prompt_invalidation=prompt_invalidation,
        )

    async def test_play_voice(self, voice_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        voice = await self._voice(voice_id)
        asset = await self.asset_for_voice(voice.id)
        if asset is None:
            raise VoiceAssetNotFoundError(voice.id)
        sample = await self.sample_blob(asset.id)
        reference_bytes = sample.path.read_bytes()
        engine = normalize_voice_engine_id(
            voice.default_engine if payload.get("use_default_engine", True) else payload.get("engine")
        )
        voice_key = voice.id
        if engine == QWEN3_ENGINE_ID:
            _require_qwen3_target(payload.get("text"))
            saved_reference = validate_saved_qwen3_reference(
                voice,
                asset,
                reference_bytes=reference_bytes,
                content_type=asset.content_type,
            )
            voice_key = saved_reference.voice_key
        engine_settings, warnings = _voxcpm2_settings_for_engine(
            engine,
            metadata=voice.metadata_json,
            reference_transcript=voice.reference_transcript,
        )
        result = await self.processor.test_play(
            voice_id=voice_key,
            text=payload.get("text", ""),
            engine=engine,
            reference_transcript=voice.reference_transcript,
            engine_settings=engine_settings,
            warnings=warnings,
            content=reference_bytes,
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
        blob_root = self.voice_blob_dir.resolve()
        path = self.voice_blob_dir / storage_name
        try:
            path.resolve().relative_to(blob_root)
        except ValueError as exc:
            raise VoiceAssetNotFoundError(asset_id) from exc
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
            "default_engine": canonical_voice_engine_id_for_read(voice.default_engine),
            "reference_transcript": voice.reference_transcript,
            "metadata": strip_retired_qwen_authorization_metadata(
                dict(voice.metadata_json or {}),
                engine_id=voice.default_engine,
            ),
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
    "LEGACY_QWEN3_ENGINE_ID",
    "QWEN3_ENGINE_ID",
    "SavedQwenReference",
    "VoiceAssetNotFoundError",
    "VoiceNotFoundError",
    "VoiceReferencedError",
    "VoiceSampleValidationError",
    "VoiceSynthesisFailedError",
    "VoiceMetadataValidationError",
    "VoicePromptInvalidationError",
    "VoiceService",
    "canonical_voice_engine_id_for_read",
    "merge_voice_metadata",
    "new_voice_asset_id",
    "new_voice_id",
    "normalize_voice_engine_id",
    "normalize_voice_metadata",
    "qwen3_voice_key",
    "strip_retired_qwen_authorization_metadata",
    "validate_saved_qwen3_reference",
]


def canonical_voice_engine_id_for_read(value: Any) -> str:
    engine_id = str(value).strip()
    if engine_id == LEGACY_QWEN3_ENGINE_ID:
        return QWEN3_ENGINE_ID
    return engine_id


def normalize_voice_engine_id(value: Any) -> str:
    engine_id = canonical_voice_engine_id_for_read(value)
    if engine_id not in SUPPORTED_VOICE_ENGINE_IDS:
        raise VoiceMetadataValidationError("Voice engine is not supported")
    return engine_id


def validate_saved_qwen3_reference(
    voice: Voice,
    asset: VoiceAsset,
    *,
    reference_bytes: bytes,
    content_type: str | None,
) -> SavedQwenReference:
    if voice.deleted_at is not None or normalize_voice_engine_id(voice.default_engine) != QWEN3_ENGINE_ID:
        raise VoiceMetadataValidationError("Qwen3-TTS saved voice is unavailable")
    _validate_asset_bytes(asset, reference_bytes)

    transcript = _require_qwen3_transcript(voice.reference_transcript)
    return SavedQwenReference(
        voice_key=qwen3_voice_key(voice.id),
        reference_bytes=reference_bytes,
        reference_transcript=transcript,
        content_type=content_type,
    )


def qwen3_voice_key(saved_voice_id: str) -> str:
    """Derive the opaque prompt owner key without private clone content."""
    if not isinstance(saved_voice_id, str) or not saved_voice_id.strip():
        raise VoiceMetadataValidationError("Qwen3-TTS saved voice identity is invalid")
    identity = f"rayme:{QWEN3_ENGINE_ID}:{saved_voice_id}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def _validate_asset_bytes(asset: VoiceAsset, reference_bytes: bytes) -> None:
    if not reference_bytes:
        raise VoiceMetadataValidationError("Saved voice reference is invalid")
    actual_sha256 = hashlib.sha256(reference_bytes).hexdigest()
    if not isinstance(asset.sha256, str) or asset.sha256 != actual_sha256:
        raise VoiceMetadataValidationError("Saved voice reference is invalid")


def _require_qwen3_target(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VoiceMetadataValidationError("Qwen3-TTS speech text is required")
    return value


def _require_qwen3_transcript(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VoiceMetadataValidationError(
            "Qwen3-TTS requires a matching reference transcript"
        )
    return value


def _qwen3_processor_payload(
    payload: dict[str, Any],
    *,
    owner_id: str,
) -> dict[str, Any]:
    return {**payload, "voice_id": qwen3_voice_key(owner_id)}


def _qwen3_invalidation_result(
    raw: Any,
    *,
    owner_key: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise VoicePromptInvalidationError("Voice prompt removal failed")
    status = raw.get("status")
    matched = raw.get("matched")
    active_cancelled = raw.get("active_cancelled")
    if (
        raw.get("engine_id") != QWEN3_ENGINE_ID
        or raw.get("voice_key") != owner_key
        or status not in {"invalidated", "not_present"}
        or not isinstance(matched, bool)
        or not isinstance(active_cancelled, bool)
        or (status == "invalidated") != matched
    ):
        raise VoicePromptInvalidationError("Voice prompt removal failed")
    return {
        "engine_id": QWEN3_ENGINE_ID,
        "voice_key": owner_key,
        "status": status,
        "matched": matched,
        "active_cancelled": active_cancelled,
    }


def _voice_deletion_response(
    voice: Voice,
    *,
    referents: list[dict[str, str]],
    prompt_invalidation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "voice_id": voice.id,
        "deleted_at": voice.deleted_at.isoformat() if voice.deleted_at else None,
        "strategy": "soft_delete",
        "referents": referents,
        "tombstone": {"name": voice.name},
    }
    if prompt_invalidation is not None:
        response["prompt_invalidation"] = prompt_invalidation
    return response


def normalize_voice_metadata(
    raw_metadata: Any,
    *,
    engine_id: Any | None = None,
) -> dict[str, Any]:
    if raw_metadata is None:
        return {}
    if not isinstance(raw_metadata, dict):
        raise VoiceMetadataValidationError("Voice metadata must be an object")

    metadata = strip_retired_qwen_authorization_metadata(
        dict(raw_metadata),
        engine_id=engine_id,
    )
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


def merge_voice_metadata(
    existing_metadata: dict[str, Any],
    patch_metadata: Any,
    *,
    engine_id: Any | None = None,
) -> dict[str, Any]:
    sanitized_existing = strip_retired_qwen_authorization_metadata(
        existing_metadata,
        engine_id=engine_id,
    )
    normalized_patch = normalize_voice_metadata(
        patch_metadata,
        engine_id=engine_id,
    )
    if "engine_settings" not in normalized_patch:
        return strip_retired_qwen_authorization_metadata(
            {**sanitized_existing, **normalized_patch},
            engine_id=engine_id,
        )

    existing_engine_settings = sanitized_existing.get("engine_settings")
    if not isinstance(existing_engine_settings, dict):
        existing_engine_settings = {}

    patch_engine_settings = normalized_patch.get("engine_settings")
    if not isinstance(patch_engine_settings, dict):
        patch_engine_settings = {}

    merged = {**sanitized_existing, **normalized_patch}
    merged["engine_settings"] = {**existing_engine_settings, **patch_engine_settings}
    return strip_retired_qwen_authorization_metadata(
        merged,
        engine_id=engine_id,
    )


def strip_retired_qwen_authorization_metadata(
    metadata: dict[str, Any],
    *,
    engine_id: Any | None = None,
) -> dict[str, Any]:
    sanitized = dict(metadata)
    if canonical_voice_engine_id_for_read(engine_id) != QWEN3_ENGINE_ID:
        return sanitized
    sanitized.pop(RETIRED_QWEN_AUTHORIZATION_METADATA_KEY, None)
    if sanitized.get("source") == LEGACY_QWEN_AUTHORIZATION_SOURCE:
        sanitized.pop(LEGACY_QWEN_AUTHORIZATION_METADATA_KEY, None)
    return sanitized


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
