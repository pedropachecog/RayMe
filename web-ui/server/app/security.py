"""Security middleware for the RayMe Web UI host."""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CSP_HEADER = (
    "default-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'"
)


def configure_cors(app: FastAPI, allowed_origins: Sequence[str]) -> None:
    """Configure explicit CORS origins for app APIs."""
    origins = [origin for origin in allowed_origins if origin]
    if not origins or any(origin == "*" or "*" in origin for origin in origins):
        msg = "CORS origins must be explicit and must not contain wildcards"
        raise ValueError(msg)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )


def configure_security_headers(app: FastAPI) -> None:
    """Attach browser security headers to every response."""

    @app.middleware("http")
    async def add_security_headers(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP_HEADER)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response
