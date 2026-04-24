"""Settings and endpoint connection-test API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.llm_probe import (
    CONNECTED,
    NOT_CONFIGURED,
    ConnectionStatus,
    probe_http_health,
    probe_openai_compatible_llm,
)
from app.domain.settings_service import EndpointSettings, SettingsService
from app.storage.session import get_session

router = APIRouter(prefix="/api/settings", tags=["settings"])

HealthProbe = Callable[[str | None], Awaitable[ConnectionStatus]]
LlmProbe = Callable[..., Awaitable[ConnectionStatus]]


class SettingsPatch(BaseModel):
    web_url: str | None = Field(default=None, max_length=500)
    ai_backend_url: str | None = Field(default=None, max_length=500)
    llm_base_url: str | None = Field(default=None, max_length=500)
    llm_api_key: str | None = Field(default=None, max_length=2000)
    llm_model: str | None = Field(default=None, max_length=200)

    @field_validator("web_url", "ai_backend_url", "llm_base_url")
    @classmethod
    def require_http_url_or_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value

        stripped = value.strip()
        if not stripped:
            return ""
        if not stripped.startswith(("http://", "https://")):
            msg = "Endpoint URLs must be absolute http(s) URLs"
            raise ValueError(msg)
        return stripped

    @field_validator("llm_api_key", "llm_model")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip()


class PublicSettings(BaseModel):
    web_url: str
    ai_backend_url: str
    llm_base_url: str
    llm_model: str
    llm_api_key_configured: bool


class ConnectionTestResponse(BaseModel):
    status: ConnectionStatus


async def get_settings_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_runtime_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_settings_service(
    session: AsyncSession = Depends(get_settings_session),
    runtime_settings: Settings = Depends(get_runtime_settings),
) -> SettingsService:
    return SettingsService(session, runtime_settings)


def get_ai_backend_probe() -> HealthProbe:
    return probe_http_health


def get_llm_probe() -> LlmProbe:
    return probe_openai_compatible_llm


@router.get("", response_model=PublicSettings)
async def read_settings(
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, str | bool]:
    return (await service.read()).to_public_dict()


@router.patch("", response_model=PublicSettings)
async def update_settings(
    payload: SettingsPatch,
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, str | bool]:
    updates = payload.model_dump(exclude_unset=True)
    return (await service.update(updates)).to_public_dict()


@router.post("/test/web", response_model=ConnectionTestResponse)
async def test_web_settings(
    service: SettingsService = Depends(get_settings_service),
) -> dict[str, ConnectionStatus]:
    settings = await service.read()
    if not _is_configured(settings.web_url):
        return {"status": NOT_CONFIGURED}
    return {"status": CONNECTED}


@router.post("/test/ai-backend", response_model=ConnectionTestResponse)
async def test_ai_backend_settings(
    service: SettingsService = Depends(get_settings_service),
    probe: HealthProbe = Depends(get_ai_backend_probe),
) -> dict[str, ConnectionStatus]:
    settings = await service.read()
    if not _is_configured(settings.ai_backend_url):
        return {"status": NOT_CONFIGURED}
    return {"status": await probe(settings.ai_backend_url)}


@router.post("/test/llm", response_model=ConnectionTestResponse)
async def test_llm_settings(
    service: SettingsService = Depends(get_settings_service),
    probe: LlmProbe = Depends(get_llm_probe),
) -> dict[str, ConnectionStatus]:
    settings = await service.read()
    return {"status": await _probe_llm(settings, probe)}


async def _probe_llm(settings: EndpointSettings, probe: LlmProbe) -> ConnectionStatus:
    return await probe(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )


def _is_configured(value: str | None) -> bool:
    return value is not None and bool(value.strip())


__all__ = [
    "ConnectionTestResponse",
    "PublicSettings",
    "SettingsPatch",
    "get_ai_backend_probe",
    "get_llm_probe",
    "get_runtime_settings",
    "get_settings_service",
    "get_settings_session",
    "router",
]
