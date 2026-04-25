from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.config import AiBackendSettings
from app.models.model_manager import ModelManager

router = APIRouter()


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
