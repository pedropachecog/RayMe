"""Typed runtime settings for the RayMe Web UI API."""

from functools import lru_cache
import os
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, Field, field_validator

WILDCARD_BIND_HOSTS = {"0.0.0.0", "::", "[::]"}
DEFAULT_ALLOWED_ORIGINS = ("https://127.0.0.1:8443",)


class Settings(BaseModel, frozen=True):
    """Server defaults that avoid exposing the app beyond localhost implicitly."""

    app_name: str = "RayMe Web UI API"
    web_bind_host: str = Field(default="127.0.0.1")
    web_port: int = Field(default=8443, ge=1, le=65535)
    web_public_url: str = "https://127.0.0.1:8443"
    tls_cert: Path | None = None
    tls_key: Path | None = None
    allowed_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS))
    ai_backend_base_url: str = "https://127.0.0.1:9443"
    ai_backend_synthesis_timeout_seconds: float = Field(default=300.0, gt=0, le=600)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_disable_thinking: bool = True

    @field_validator("web_bind_host")
    @classmethod
    def reject_wildcard_bind_host(cls, value: str) -> str:
        normalized = value.strip()
        if normalized in WILDCARD_BIND_HOSTS:
            msg = "RAYME_WEB_BIND_HOST must be an explicit LAN IP or hostname, not 0.0.0.0"
            raise ValueError(msg)
        if not normalized:
            msg = "RAYME_WEB_BIND_HOST must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        elif isinstance(value, (list, tuple, set)):
            origins = [str(origin).strip() for origin in value if str(origin).strip()]
        else:
            msg = "RAYME_ALLOWED_ORIGINS must be a comma-separated origin list"
            raise ValueError(msg)

        if not origins:
            msg = "RAYME_ALLOWED_ORIGINS must include at least one explicit origin"
            raise ValueError(msg)
        if any(origin == "*" or "*" in origin for origin in origins):
            msg = "RAYME_ALLOWED_ORIGINS must not contain wildcard origins"
            raise ValueError(msg)
        if any(not origin.startswith(("http://", "https://")) for origin in origins):
            msg = "RAYME_ALLOWED_ORIGINS entries must be absolute http(s) origins"
            raise ValueError(msg)
        return origins

    @property
    def host(self) -> str:
        """Compatibility alias for callers that expect a host setting."""
        return self.web_bind_host

    @property
    def port(self) -> int:
        """Compatibility alias for callers that expect a port setting."""
        return self.web_port


ENV_TO_FIELD = {
    "RAYME_WEB_BIND_HOST": "web_bind_host",
    "RAYME_WEB_PORT": "web_port",
    "RAYME_WEB_PUBLIC_URL": "web_public_url",
    "RAYME_TLS_CERT": "tls_cert",
    "RAYME_TLS_KEY": "tls_key",
    "RAYME_ALLOWED_ORIGINS": "allowed_origins",
    "RAYME_AI_BACKEND_BASE_URL": "ai_backend_base_url",
    "RAYME_AI_BACKEND_SYNTHESIS_TIMEOUT_SECONDS": "ai_backend_synthesis_timeout_seconds",
    "RAYME_LLM_BASE_URL": "llm_base_url",
    "RAYME_LLM_API_KEY": "llm_api_key",
    "RAYME_LLM_MODEL": "llm_model",
    "RAYME_LLM_DISABLE_THINKING": "llm_disable_thinking",
}


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load settings from environment variables without binding any sockets."""
    source = os.environ if environ is None else environ
    values = {
        field_name: source[env_name]
        for env_name, field_name in ENV_TO_FIELD.items()
        if env_name in source
    }
    return Settings(**values)


@lru_cache
def get_settings() -> Settings:
    return load_settings()
