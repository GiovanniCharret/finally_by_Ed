"""Shared fixtures for the FastAPI API tests."""

from __future__ import annotations

from typing import AsyncIterator

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat, health, portfolio, watchlist
from app.api.dependencies import (
    get_db,
    get_price_cache,
    set_market_source,
    set_price_cache,
)
from app.market.cache import PriceCache

SCHEMA_SQL = """
CREATE TABLE users_profile (
    id TEXT PRIMARY KEY,
    cash_balance REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE watchlist (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE portfolio_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    total_value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    actions TEXT,
    created_at TEXT NOT NULL
);
"""


class _StubMarketSource:
    """No-op market source used by watchlist add/remove tests."""

    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)


@pytest.fixture
async def db_conn() -> AsyncIterator[aiosqlite.Connection]:
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA_SQL)
    await conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        ("default", 10000.0, "2026-04-22T12:00:00Z"),
    )
    await conn.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        ("w1", "default", "AAPL", "2026-04-22T12:00:00Z"),
    )
    await conn.commit()
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def price_cache() -> PriceCache:
    cache = PriceCache()
    cache.update("AAPL", 100.0)
    cache.update("GOOGL", 175.0)
    return cache


@pytest.fixture
def market_source() -> _StubMarketSource:
    return _StubMarketSource()


@pytest.fixture
def app(
    db_conn: aiosqlite.Connection,
    price_cache: PriceCache,
    market_source: _StubMarketSource,
) -> FastAPI:
    """Build a fresh FastAPI app with overridden dependencies for each test."""
    app = FastAPI()
    app.include_router(health.router, prefix="/api")
    app.include_router(portfolio.router, prefix="/api")
    app.include_router(watchlist.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    set_price_cache(price_cache)
    set_market_source(market_source)

    async def _override_get_db():
        yield db_conn

    def _override_get_price_cache():
        return price_cache

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_price_cache] = _override_get_price_cache
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
