from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import tts
from app.api.health import router as health_router
from app.api.stt import router as stt_router
from app.config import AiBackendSettings
from app.models.model_manager import ModelManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    manager = getattr(app.state, "model_manager", None)
    if manager is None:
        manager = ModelManager(AiBackendSettings())
        app.state.model_manager = manager
    manager.startup()
    try:
        yield
    finally:
        manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="RayMe AI Backend", version="0.2.0", lifespan=lifespan)
    app.state.model_manager = ModelManager(AiBackendSettings())
    app.include_router(health_router)
    app.include_router(stt_router)
    app.include_router(tts.router)
    return app
