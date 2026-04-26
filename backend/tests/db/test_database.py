"""Tests for the SQLite database layer."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import aiosqlite
import pytest

from db import database
from db.database import get_db, init_db
from db.seed import DEFAULT_USER_ID, DEFAULT_WATCHLIST_TICKERS

ISO_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

EXPECTED_TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point DB_PATH at a per-test temporary file."""
    db_file = tmp_path / "finally.db"
    monkeypatch.setattr(database, "DB_PATH", db_file)
    return db_file


class TestInitDb:
    async def test_creates_all_tables(self) -> None:
        await init_db()
        async with get_db() as conn:
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                names = {row["name"] async for row in cursor}
        assert EXPECTED_TABLES.issubset(names)

    async def test_seeds_default_user_with_starting_cash(self) -> None:
        await init_db()
        async with get_db() as conn:
            async with conn.execute(
                "SELECT id, cash_balance, created_at FROM users_profile"
            ) as cursor:
                rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == DEFAULT_USER_ID
        assert rows[0]["cash_balance"] == 10000.0
        assert ISO_UTC_PATTERN.match(rows[0]["created_at"])

    async def test_seeds_ten_watchlist_tickers(self) -> None:
        await init_db()
        async with get_db() as conn:
            async with conn.execute(
                "SELECT ticker FROM watchlist ORDER BY ticker"
            ) as cursor:
                tickers = [row["ticker"] async for row in cursor]
        assert len(tickers) == 10
        assert set(tickers) == set(DEFAULT_WATCHLIST_TICKERS)

    async def test_idempotent_no_duplicates(self) -> None:
        await init_db()
        await init_db()
        await init_db()
        async with get_db() as conn:
            async with conn.execute("SELECT COUNT(*) AS c FROM users_profile") as cursor:
                user_count = (await cursor.fetchone())["c"]
            async with conn.execute("SELECT COUNT(*) AS c FROM watchlist") as cursor:
                watchlist_count = (await cursor.fetchone())["c"]
        assert user_count == 1
        assert watchlist_count == 10


class TestConstraints:
    async def test_watchlist_unique_user_ticker(self) -> None:
        await init_db()
        async with get_db() as conn:
            with pytest.raises(aiosqlite.IntegrityError):
                await conn.execute(
                    """
                    INSERT INTO watchlist (id, user_id, ticker, added_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), DEFAULT_USER_ID, "AAPL", "2026-04-22T12:00:00Z"),
                )

    async def test_positions_unique_user_ticker(self) -> None:
        await init_db()
        async with get_db() as conn:
            await conn.execute(
                """
                INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), DEFAULT_USER_ID, "AAPL", 5.0, 190.0, "2026-04-22T12:00:00Z"),
            )
            with pytest.raises(aiosqlite.IntegrityError):
                await conn.execute(
                    """
                    INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        DEFAULT_USER_ID,
                        "AAPL",
                        3.0,
                        185.0,
                        "2026-04-22T12:01:00Z",
                    ),
                )


class TestRoundtrip:
    async def test_insert_and_query_position(self) -> None:
        await init_db()
        position_id = str(uuid.uuid4())
        timestamp = "2026-04-22T12:00:00Z"
        async with get_db() as conn:
            await conn.execute(
                """
                INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (position_id, DEFAULT_USER_ID, "AAPL", 5.0, 190.00, timestamp),
            )
            async with conn.execute(
                "SELECT id, ticker, quantity, avg_cost, updated_at FROM positions WHERE id = ?",
                (position_id,),
            ) as cursor:
                row = await cursor.fetchone()
        assert row is not None
        assert row["ticker"] == "AAPL"
        assert row["quantity"] == 5.0
        assert row["avg_cost"] == 190.00
        assert row["updated_at"] == timestamp

    async def test_seeded_timestamps_are_iso_utc(self) -> None:
        await init_db()
        async with get_db() as conn:
            async with conn.execute("SELECT created_at FROM users_profile") as cursor:
                user_ts = (await cursor.fetchone())["created_at"]
            async with conn.execute("SELECT added_at FROM watchlist LIMIT 1") as cursor:
                watch_ts = (await cursor.fetchone())["added_at"]
        assert isinstance(user_ts, str) and ISO_UTC_PATTERN.match(user_ts)
        assert isinstance(watch_ts, str) and ISO_UTC_PATTERN.match(watch_ts)

    async def test_trade_insert_roundtrip(self) -> None:
        await init_db()
        trade_id = str(uuid.uuid4())
        async with get_db() as conn:
            await conn.execute(
                """
                INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (trade_id, DEFAULT_USER_ID, "AAPL", "buy", 2.0, 194.25, "2026-04-22T12:00:00Z"),
            )
            async with conn.execute(
                "SELECT side, quantity, price FROM trades WHERE id = ?", (trade_id,)
            ) as cursor:
                row = await cursor.fetchone()
        assert row["side"] == "buy"
        assert row["quantity"] == 2.0
        assert row["price"] == 194.25
