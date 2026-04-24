"""FastAPI application factory for the RayMe Web UI API."""

from fastapi import FastAPI

from app.config import get_settings


def create_app() -> FastAPI:
    """Build the API application without binding sockets or configuring origins."""
    settings = get_settings()
    return FastAPI(title=settings.app_name)


__all__ = ["create_app"]
