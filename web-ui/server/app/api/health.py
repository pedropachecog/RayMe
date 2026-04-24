"""Health route for the RayMe Web UI host."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"service": "rayme-web-ui", "status": "ok", "phase": "01"}


__all__ = ["router"]
