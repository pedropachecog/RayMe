"""Typed settings shell for the RayMe Web UI API."""

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    """Server defaults that avoid exposing the app beyond localhost implicitly."""

    app_name: str = "RayMe Web UI API"
    host: str = "127.0.0.1"
    port: int = 8443


@lru_cache
def get_settings() -> Settings:
    return Settings()
