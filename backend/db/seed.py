"""Seed default user profile and watchlist tickers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

DEFAULT_USER_ID = "default"
DEFAULT_CASH_BALANCE = 10000.0
DEFAULT_WATCHLIST_TICKERS: tuple[str, ...] = (
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def seed_defaults(conn: aiosqlite.Connection) -> None:
    """Insert default user and watchlist if they don't already exist."""
    await _seed_user(conn)
    await _seed_watchlist(conn)


async def _seed_user(conn: aiosqlite.Connection) -> None:
    async with conn.execute(
        "SELECT id FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is not None:
        return
    await conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, _utc_now_iso()),
    )


async def _seed_watchlist(conn: aiosqlite.Connection) -> None:
    for ticker in DEFAULT_WATCHLIST_TICKERS:
        await conn.execute(
            """
            INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, _utc_now_iso()),
        )
