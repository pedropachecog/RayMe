"""RayMe-owned bridge routes for AI backend status."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.settings import get_settings_service
from app.domain.ai_backend_client import (
    AiBackendClient,
    AiBackendStatus,
    AiBackendUnavailable,
)
from app.domain.settings_service import SettingsService

router = APIRouter(prefix="/api/ai-backend", tags=["ai-backend"])


def get_ai_backend_client() -> AiBackendClient:
    return AiBackendClient()


@router.get("/status")
async def read_ai_backend_status(
    service: SettingsService = Depends(get_settings_service),
    client: AiBackendClient = Depends(get_ai_backend_client),
) -> dict[str, object]:
    settings = await service.read()
    if not settings.ai_backend_url.strip():
        return _unavailable_status("Not configured")

    try:
        status = await client.get_status(settings.ai_backend_url)
    except AiBackendUnavailable as exc:
        endpoint_status = "Unauthorized" if exc.code == "unauthorized" else "Unreachable"
        return _unavailable_status(endpoint_status)

    return compact_ai_backend_status(status)


def compact_ai_backend_status(status: AiBackendStatus) -> dict[str, object]:
    available_engines = [
        engine.model_dump(exclude_none=True)
        for engine in status.available_engines
    ]
    return {
        "endpoint_status": status.status,
        "status": status.status,
        "stt_model": status.stt_model,
        "stt_compute_type": status.stt_compute_type,
        "vad_ready": status.vad_ready,
        "resident_tts_engine": status.resident_tts_engine,
        "available_engines": available_engines,
        "loading_engine": status.loading_engine,
        "vram_used_mb": status.vram_used_mb,
        "vram_headroom_mb": status.vram_headroom_mb,
    }


def _unavailable_status(endpoint_status: str) -> dict[str, object]:
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


__all__ = ["compact_ai_backend_status", "get_ai_backend_client", "router"]
