from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status


def require_service_auth(request: Request) -> None:
    """Authenticate one non-public AI processing or control request."""

    settings = getattr(request.app.state, "ai_backend_settings", None)
    expected = str(getattr(settings, "service_auth_token", "") or "")
    if len(expected) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "service_auth_not_configured",
                "message": "Service authentication is unavailable",
            },
        )
    authorization = request.headers.get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not supplied
        or not secrets.compare_digest(supplied, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "service_auth_invalid",
                "message": "Service authentication failed",
            },
        )


__all__ = ["require_service_auth"]
