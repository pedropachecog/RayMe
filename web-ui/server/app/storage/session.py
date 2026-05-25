"""Async SQLAlchemy session helpers for RayMe storage."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.storage.models import Base

SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = SERVER_ROOT / "data" / "rayme.sqlite3"
DEFAULT_DATABASE_URL = f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return

    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or os.environ.get("RAYME_DATABASE_URL", DEFAULT_DATABASE_URL)
    _ensure_sqlite_parent(url)
    engine = create_async_engine(url, pool_pre_ping=True)
    if make_url(url).get_backend_name() == "sqlite":
        _configure_sqlite_pragmas(engine)
    return engine


engine = create_engine()
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


__all__ = [
    "Base",
    "DEFAULT_DATABASE_PATH",
    "DEFAULT_DATABASE_URL",
    "async_session_factory",
    "create_engine",
    "engine",
    "get_session",
]
