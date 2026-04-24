"""FastAPI application factory for the RayMe Web UI API."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from app.config import Settings, get_settings
from app.security import configure_cors, configure_security_headers

CLIENT_BUILD_DIR = Path(__file__).resolve().parents[2] / "client" / "build"


class SpaStaticFiles(StaticFiles):
    """StaticFiles variant that serves SvelteKit's SPA fallback."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("200.html", scope)


def mount_static_client(app: FastAPI, build_dir: Path = CLIENT_BUILD_DIR) -> bool:
    """Mount the built Svelte client when build output is present."""
    fallback = build_dir / "200.html"
    if not build_dir.is_dir() or not fallback.is_file():
        return False

    app.mount("/", SpaStaticFiles(directory=build_dir, html=True), name="client")
    return True


def create_app(
    settings: Settings | None = None,
    *,
    static_client_dir: Path | None = CLIENT_BUILD_DIR,
) -> FastAPI:
    """Build the API application without binding sockets."""
    runtime_settings = settings or get_settings()
    app = FastAPI(title=runtime_settings.app_name)
    configure_cors(app, runtime_settings.allowed_origins)
    configure_security_headers(app)

    if static_client_dir is not None:
        mount_static_client(app, static_client_dir)

    return app


__all__ = ["create_app", "mount_static_client"]
