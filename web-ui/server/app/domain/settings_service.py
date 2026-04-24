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
)


@dataclass(frozen=True, slots=True)
class EndpointSettings:
    web_url: str
    ai_backend_url: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @property
    def llm_api_key_configured(self) -> bool:
        return bool(self.llm_api_key.strip())

    def to_public_dict(self) -> dict[str, str | bool]:
        return {
            "web_url": self.web_url,
            "ai_backend_url": self.ai_backend_url,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_api_key_configured": self.llm_api_key_configured,
        }

    def to_private_dict(self) -> dict[str, str]:
        return {
            "web_url": self.web_url,
            "ai_backend_url": self.ai_backend_url,
            "llm_base_url": self.llm_base_url,
            "llm_api_key": self.llm_api_key,
            "llm_model": self.llm_model,
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
            merged[key] = _clean_setting_value(value)

        snapshot = self._snapshot(merged)
        await self._save(snapshot.to_private_dict())
        return snapshot

    async def _load_persisted(self) -> dict[str, str]:
        row = await self._session.get(AppSetting, SETTINGS_KEY)
        if row is None or not isinstance(row.value_json, dict):
            return {}

        return {
            key: value.strip()
            for key, value in row.value_json.items()
            if key in SETTING_FIELDS and isinstance(value, str)
        }

    async def _save(self, values: Mapping[str, str]) -> None:
        row = await self._session.get(AppSetting, SETTINGS_KEY)
        if row is None:
            self._session.add(AppSetting(key=SETTINGS_KEY, value_json=dict(values)))
        else:
            row.value_json = dict(values)
        await self._session.commit()

    def _snapshot(self, persisted: Mapping[str, str]) -> EndpointSettings:
        defaults = {
            "web_url": self._runtime_settings.web_public_url,
            "ai_backend_url": self._runtime_settings.ai_backend_base_url,
            "llm_base_url": self._runtime_settings.llm_base_url,
            "llm_api_key": self._runtime_settings.llm_api_key,
            "llm_model": self._runtime_settings.llm_model,
        }
        values = {**defaults, **persisted}
        return EndpointSettings(
            web_url=values["web_url"],
            ai_backend_url=values["ai_backend_url"],
            llm_base_url=values["llm_base_url"],
            llm_api_key=values["llm_api_key"],
            llm_model=values["llm_model"],
        )


def _clean_setting_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


__all__ = ["EndpointSettings", "SETTING_FIELDS", "SETTINGS_KEY", "SettingsService"]
