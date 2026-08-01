from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_service_auth
from app.config import AiBackendSettings
from app.models.model_manager import ModelManager

router = APIRouter()


@router.get("/ready", dependencies=[Depends(require_service_auth)])
def authenticated_readiness() -> dict[str, object]:
    """Prove service identity without loading models or mutating runtime state."""

    return {
        "service": "rayme-ai-backend",
        "status": "ready",
        "authenticated": True,
    }


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    manager = getattr(request.app.state, "model_manager", None)
    if manager is None:
        manager = ModelManager(AiBackendSettings())
        manager.startup()
        request.app.state.model_manager = manager
    elif manager.resident_tts_engine is None:
        manager.startup()

    payload = manager.health()
    return {
        **payload,
        "phase": "02",
        "capabilities": ["health", "stt", "vad", "tts"],
    }
