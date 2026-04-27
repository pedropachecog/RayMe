"""Persistence helpers for browser-editable endpoint settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.storage.models import AppSetting

SETTINGS_KEY = "endpoint_settings"
SETTING_FIELDS = (
    "web_url",
    "ai_backend_url",
    "llm_base_url",
    "llm_api_key",
    "llm_model",
    "llm_disable_thinking",
    "save_ai_audio",
    "save_mic_audio",
    "vad_threshold",
    "vad_end_silence_ms",
    "stt_model",
    "tts_default_engine",
)


@dataclass(frozen=True, slots=True)
class EndpointSettings:
    web_url: str
    ai_backend_url: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_disable_thinking: bool
    save_ai_audio: bool
    save_mic_audio: bool
    vad_threshold: float
    vad_end_silence_ms: int
    stt_model: str
    tts_default_engine: str

    @property
    def llm_api_key_configured(self) -> bool:
        return bool(self.llm_api_key.strip())

    def to_public_dict(self) -> dict[str, object]:
        return {
            "web_url": self.web_url,
            "ai_backend_url": self.ai_backend_url,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_disable_thinking": self.llm_disable_thinking,
            "llm_api_key_configured": self.llm_api_key_configured,
            "save_ai_audio": self.save_ai_audio,
            "save_mic_audio": self.save_mic_audio,
            "vad_threshold": self.vad_threshold,
            "vad_end_silence_ms": self.vad_end_silence_ms,
            "stt_model": self.stt_model,
            "tts_default_engine": self.tts_default_engine,
            "ai_backend_status": _default_ai_backend_status(),
        }

    def to_private_dict(self) -> dict[str, object]:
        return {
            "web_url": self.web_url,
            "ai_backend_url": self.ai_backend_url,
            "llm_base_url": self.llm_base_url,
            "llm_api_key": self.llm_api_key,
            "llm_model": self.llm_model,
            "llm_disable_thinking": self.llm_disable_thinking,
            "save_ai_audio": self.save_ai_audio,
            "save_mic_audio": self.save_mic_audio,
            "vad_threshold": self.vad_threshold,
            "vad_end_silence_ms": self.vad_end_silence_ms,
            "stt_model": self.stt_model,
            "tts_default_engine": self.tts_default_engine,
        }


class SettingsService:
    """Read and update endpoint settings stored in the app_settings table."""

    def __init__(self, session: AsyncSession, runtime_settings: Settings) -> None:
        self._session = session
        self._runtime_settings = runtime_settings

    async def read(self) -> EndpointSettings:
        return self._snapshot(await self._load_persisted())

    async def update(self, updates: Mapping[str, Any]) -> EndpointSettings:
        persisted = await self._load_persisted()
        merged = {**persisted}
        for key, value in updates.items():
            if key not in SETTING_FIELDS:
                continue
            merged[key] = _clean_setting_value(key, value)

        snapshot = self._snapshot(merged)
        await self._save(snapshot.to_private_dict())
        return snapshot

    async def _load_persisted(self) -> dict[str, object]:
        row = await self._session.get(AppSetting, SETTINGS_KEY)
        if row is None or not isinstance(row.value_json, dict):
            return {}

        return {
            key: _clean_persisted_setting(key, value)
            for key, value in row.value_json.items()
            if key in SETTING_FIELDS
        }

    async def _save(self, values: Mapping[str, object]) -> None:
        row = await self._session.get(AppSetting, SETTINGS_KEY)
        if row is None:
            self._session.add(AppSetting(key=SETTINGS_KEY, value_json=dict(values)))
        else:
            row.value_json = dict(values)
        await self._session.commit()

    def _snapshot(self, persisted: Mapping[str, object]) -> EndpointSettings:
        defaults = {
            "web_url": self._runtime_settings.web_public_url,
            "ai_backend_url": self._runtime_settings.ai_backend_base_url,
            "llm_base_url": self._runtime_settings.llm_base_url,
            "llm_api_key": self._runtime_settings.llm_api_key,
            "llm_model": self._runtime_settings.llm_model,
            "llm_disable_thinking": self._runtime_settings.llm_disable_thinking,
            "save_ai_audio": True,
            "save_mic_audio": False,
            "vad_threshold": 0.5,
            "vad_end_silence_ms": 700,
            "stt_model": "distil-large-v3",
            "tts_default_engine": "f5",
        }
        values = {**defaults, **persisted}
        return EndpointSettings(
            web_url=str(values["web_url"]),
            ai_backend_url=str(values["ai_backend_url"]),
            llm_base_url=str(values["llm_base_url"]),
            llm_api_key=str(values["llm_api_key"]),
            llm_model=str(values["llm_model"]),
            llm_disable_thinking=bool(values["llm_disable_thinking"]),
            save_ai_audio=bool(values["save_ai_audio"]),
            save_mic_audio=bool(values["save_mic_audio"]),
            vad_threshold=float(values["vad_threshold"]),
            vad_end_silence_ms=int(values["vad_end_silence_ms"]),
            stt_model=str(values["stt_model"]).strip(),
            tts_default_engine=str(values["tts_default_engine"]).strip(),
        )


def _clean_setting_value(key: str, value: Any) -> object:
    if value is None:
        if key in {"save_ai_audio", "save_mic_audio", "llm_disable_thinking"}:
            return False
        if key == "vad_threshold":
            return 0.5
        if key == "vad_end_silence_ms":
            return 700
        return ""
    if key in {"save_ai_audio", "save_mic_audio", "llm_disable_thinking"}:
        return bool(value)
    if key == "vad_threshold":
        return float(value)
    if key == "vad_end_silence_ms":
        return int(value)
    return str(value).strip()


def _clean_persisted_setting(key: str, value: Any) -> object:
    if key in {"save_ai_audio", "save_mic_audio", "llm_disable_thinking"}:
        return bool(value)
    if key == "vad_threshold":
        return float(value)
    if key == "vad_end_silence_ms":
        return int(value)
    return str(value).strip() if isinstance(value, str) else ""


def _default_ai_backend_status() -> dict[str, object]:
    return {
        "endpoint_status": "Not configured",
        "status": "error",
        "stt_model": None,
        "stt_compute_type": None,
        "vad_ready": False,
        "resident_tts_engine": None,
        "available_engines": [],
        "loading_engine": None,
        "vram_used_mb": None,
        "vram_headroom_mb": None,
    }


__all__ = ["EndpointSettings", "SETTING_FIELDS", "SETTINGS_KEY", "SettingsService"]
