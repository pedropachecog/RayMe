from __future__ import annotations

import asyncio
from pathlib import Path

from app.storage.session import create_engine


def test_create_engine_pre_pings_pooled_sqlite_connections(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rayme-session.sqlite3'}")
    try:
        assert engine.sync_engine.pool._pre_ping is True
    finally:
        asyncio.run(engine.dispose())
