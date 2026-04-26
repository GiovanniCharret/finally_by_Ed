"""Async SQLite connection management and lazy initialization."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

DB_PATH: Path = Path(__file__).resolve().parent.parent.parent / "db" / "finally.db"
SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"


def _resolve_db_path() -> Path:
    return DB_PATH


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with row_factory set to aiosqlite.Row.

    The connection runs in autocommit mode (isolation_level=None); callers
    that need atomicity should use BEGIN/COMMIT explicitly.
    """
    path = _resolve_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(path), isolation_level=None)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    finally:
        await conn.close()


async def init_db() -> None:
    """Create tables from schema.sql and seed default data if missing."""
    from .seed import seed_defaults

    schema_sql = SCHEMA_PATH.read_text()
    async with get_db() as conn:
        await conn.executescript(schema_sql)
        await seed_defaults(conn)
