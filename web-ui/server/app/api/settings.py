"""Settings and endpoint connection-test API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.ai_backend_client import AiBackendClient, AiBackendStatus, AiBackendUnavailable
from app.domain.llm_probe import (
    CONNECTED,
    NOT_CONFIGURED,
    UNAUTHORIZED,
    UNREACHABLE,
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
    save_ai_audio: bool | None = None
    save_mic_audio: bool | None = None
    vad_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    vad_end_silence_ms: int | None = Field(default=None, ge=100, le=3000)
    stt_model: str | None = Field(default=None, max_length=200)
    tts_default_engine: str | None = Field(default=None, max_length=100)

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

    @field_validator("llm_api_key", "llm_model", "stt_model", "tts_default_engine")
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
    save_ai_audio: bool
    save_mic_audio: bool
    vad_threshold: float
    vad_end_silence_ms: int
    stt_model: str
    tts_default_engine: str
    ai_backend_status: dict[str, object]


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


def get_ai_backend_client() -> AiBackendClient:
    return AiBackendClient()


def get_llm_probe() -> LlmProbe:
    return probe_openai_compatible_llm


@router.get("", response_model=PublicSettings)
async def read_settings(
    service: SettingsService = Depends(get_settings_service),
    client: AiBackendClient = Depends(get_ai_backend_client),
) -> dict[str, object]:
    settings = await service.read()
    return await _public_settings(settings, client)


@router.patch("", response_model=PublicSettings)
async def update_settings(
    payload: SettingsPatch,
    service: SettingsService = Depends(get_settings_service),
    client: AiBackendClient = Depends(get_ai_backend_client),
) -> dict[str, object]:
    updates = payload.model_dump(exclude_unset=True)
    settings = await service.update(updates)
    return await _public_settings(settings, client)


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
    client: AiBackendClient = Depends(get_ai_backend_client),
) -> dict[str, ConnectionStatus]:
    settings = await service.read()
    if not _is_configured(settings.ai_backend_url):
        return {"status": NOT_CONFIGURED}
    try:
        await client.get_status(settings.ai_backend_url)
    except AiBackendUnavailable as exc:
        if exc.code == "unauthorized":
            return {"status": UNAUTHORIZED}
        return {"status": UNREACHABLE}
    return {"status": CONNECTED}


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


async def _public_settings(
    settings: EndpointSettings,
    client: AiBackendClient,
) -> dict[str, object]:
    payload = settings.to_public_dict()
    payload["ai_backend_status"] = await _settings_ai_backend_status(settings, client)
    return payload


async def _settings_ai_backend_status(
    settings: EndpointSettings,
    client: AiBackendClient,
) -> dict[str, object]:
    if not _is_configured(settings.ai_backend_url):
        return _unavailable_ai_backend_status("Not configured")
    try:
        status = await client.get_status(settings.ai_backend_url)
    except AiBackendUnavailable as exc:
        endpoint_status = "Unauthorized" if exc.code == "unauthorized" else "Unreachable"
        return _unavailable_ai_backend_status(endpoint_status)

    return _compact_ai_backend_status(status)


def _compact_ai_backend_status(status: AiBackendStatus) -> dict[str, object]:
    return {
        "endpoint_status": status.status,
        "status": status.status,
        "stt_model": status.stt_model,
        "stt_compute_type": status.stt_compute_type,
        "vad_ready": status.vad_ready,
        "resident_tts_engine": status.resident_tts_engine,
        "available_engines": [
            engine.model_dump(exclude_none=True) for engine in status.available_engines
        ],
        "loading_engine": status.loading_engine,
        "vram_used_mb": status.vram_used_mb,
        "vram_headroom_mb": status.vram_headroom_mb,
    }


def _unavailable_ai_backend_status(endpoint_status: str) -> dict[str, object]:
    return {
        "endpoint_status": endpoint_status,
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


def _is_configured(value: str | None) -> bool:
    return value is not None and bool(value.strip())


__all__ = [
    "ConnectionTestResponse",
    "PublicSettings",
    "SettingsPatch",
    "get_ai_backend_client",
    "get_ai_backend_probe",
    "get_llm_probe",
    "get_runtime_settings",
    "get_settings_service",
    "get_settings_session",
    "router",
]
