"""Reusable same-origin policy for browser-owned mutation-adjacent APIs."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings

CALL_ORIGIN_NOT_ALLOWED = "call_origin_not_allowed"
CALL_ORIGIN_NOT_ALLOWED_MESSAGE = "Call controls must come from the RayMe Web UI origin."


def get_runtime_settings(request: Request) -> Settings:
    """Return the immutable process settings used to establish trusted origins."""

    return request.app.state.settings


async def enforce_same_origin(
    request: Request,
    runtime_settings: Settings = Depends(get_runtime_settings),
) -> None:
    """Allow same-origin browser traffic and non-browser requests without Origin."""

    origin = request.headers.get("origin")
    if not origin:
        return

    allowed_origins = {
        _origin_from_url(runtime_settings.web_public_url),
        *(_origin_from_url(candidate) for candidate in runtime_settings.allowed_origins),
        _origin_from_url(str(request.base_url)),
    }
    if _origin_from_url(origin) not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": CALL_ORIGIN_NOT_ALLOWED,
                "message": CALL_ORIGIN_NOT_ALLOWED_MESSAGE,
            },
        )


def _origin_from_url(value: str) -> str:
    stripped = value.strip().rstrip("/")
    if "://" not in stripped:
        return stripped
    scheme, rest = stripped.split("://", 1)
    authority = rest.split("/", 1)[0]
    return f"{scheme.lower()}://{authority.lower()}"


__all__ = [
    "CALL_ORIGIN_NOT_ALLOWED",
    "CALL_ORIGIN_NOT_ALLOWED_MESSAGE",
    "enforce_same_origin",
    "get_runtime_settings",
]
