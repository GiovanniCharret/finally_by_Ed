"""Tests for app.llm.chat.handle_chat_message."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from app.llm import chat as chat_module
from app.llm.chat import handle_chat_message
from app.llm.models import LLMResponse, TradeRequest, WatchlistChange
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

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    actions TEXT,
    created_at TEXT NOT NULL
);
"""


@pytest.fixture
async def db():
    """In-memory aiosqlite db seeded with the FinAlly schema and defaults."""
    conn = await aiosqlite.connect(":memory:")
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
def price_cache():
    cache = PriceCache()
    cache.update("AAPL", 100.0)
    cache.update("GOOGL", 175.0)
    return cache


async def test_mock_mode_returns_message(monkeypatch, db, price_cache):
    monkeypatch.setenv("LLM_MOCK", "true")
    result = await handle_chat_message("Hi", db, price_cache)

    assert "message" in result
    assert isinstance(result["message"], str) and result["message"]
    assert result["trades"] == []
    assert result["watchlist_changes"] == []
    assert result["action_results"] == []

    async with db.execute(
        "SELECT role, content FROM chat_messages ORDER BY created_at"
    ) as cursor:
        rows = await cursor.fetchall()
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert rows[0][1] == "Hi"


async def test_buy_trade_via_llm_executes_and_updates_db(monkeypatch, db, price_cache):
    monkeypatch.delenv("LLM_MOCK", raising=False)

    fake_response = LLMResponse(
        message="Bought 2 AAPL.",
        trades=[TradeRequest(ticker="aapl", side="buy", quantity=2)],
        watchlist_changes=[],
    )
    with patch.object(chat_module, "call_llm", new=AsyncMock(return_value=fake_response)):
        result = await handle_chat_message("Buy 2 AAPL", db, price_cache)

    assert len(result["action_results"]) == 1
    action = result["action_results"][0]
    assert action["status"] == "executed"
    assert action["ticker"] == "AAPL"
    assert action["price"] == 100.0
    assert action["trade_id"]

    async with db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", ("default",)
    ) as cursor:
        cash = (await cursor.fetchone())[0]
    assert cash == pytest.approx(10000.0 - 200.0)

    async with db.execute(
        "SELECT quantity, avg_cost FROM positions WHERE ticker = ?", ("AAPL",)
    ) as cursor:
        pos = await cursor.fetchone()
    assert pos == (2.0, 100.0)

    async with db.execute(
        "SELECT side, quantity, price FROM trades WHERE ticker = ?", ("AAPL",)
    ) as cursor:
        trade_row = await cursor.fetchone()
    assert trade_row == ("buy", 2.0, 100.0)

    async with db.execute(
        "SELECT actions FROM chat_messages WHERE role = 'assistant'"
    ) as cursor:
        actions_json = (await cursor.fetchone())[0]
    assert actions_json is not None
    assert json.loads(actions_json)[0]["status"] == "executed"


async def test_buy_with_insufficient_cash_records_failure(monkeypatch, db, price_cache):
    monkeypatch.delenv("LLM_MOCK", raising=False)

    fake_response = LLMResponse(
        message="Trying to buy 1000 AAPL.",
        trades=[TradeRequest(ticker="AAPL", side="buy", quantity=1000)],
        watchlist_changes=[],
    )
    with patch.object(chat_module, "call_llm", new=AsyncMock(return_value=fake_response)):
        result = await handle_chat_message("buy 1000 AAPL", db, price_cache)

    action = result["action_results"][0]
    assert action["status"] == "failed"
    assert "Insufficient cash" in action["reason"]

    async with db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", ("default",)
    ) as cursor:
        cash = (await cursor.fetchone())[0]
    assert cash == 10000.0  # unchanged

    async with db.execute("SELECT COUNT(*) FROM trades") as cursor:
        count = (await cursor.fetchone())[0]
    assert count == 0


async def test_sell_more_than_held_fails(monkeypatch, db, price_cache):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    # Seed a small position.
    await db.execute(
        """INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("p1", "default", "AAPL", 1.0, 90.0, "2026-04-22T12:00:00Z"),
    )
    await db.commit()

    fake_response = LLMResponse(
        message="Selling 5 AAPL.",
        trades=[TradeRequest(ticker="AAPL", side="sell", quantity=5)],
        watchlist_changes=[],
    )
    with patch.object(chat_module, "call_llm", new=AsyncMock(return_value=fake_response)):
        result = await handle_chat_message("sell 5 AAPL", db, price_cache)

    assert result["action_results"][0]["status"] == "failed"
    assert "Insufficient shares" in result["action_results"][0]["reason"]


async def test_sell_zeroes_position_and_deletes_row(monkeypatch, db, price_cache):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    await db.execute(
        """INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("p1", "default", "AAPL", 3.0, 90.0, "2026-04-22T12:00:00Z"),
    )
    await db.commit()

    fake_response = LLMResponse(
        message="Selling all.",
        trades=[TradeRequest(ticker="AAPL", side="sell", quantity=3)],
        watchlist_changes=[],
    )
    with patch.object(chat_module, "call_llm", new=AsyncMock(return_value=fake_response)):
        result = await handle_chat_message("sell 3 AAPL", db, price_cache)

    assert result["action_results"][0]["status"] == "executed"

    async with db.execute(
        "SELECT COUNT(*) FROM positions WHERE ticker = ?", ("AAPL",)
    ) as cursor:
        count = (await cursor.fetchone())[0]
    assert count == 0


async def test_watchlist_add_and_remove(monkeypatch, db, price_cache):
    monkeypatch.delenv("LLM_MOCK", raising=False)

    fake_response = LLMResponse(
        message="Updated watchlist.",
        trades=[],
        watchlist_changes=[
            WatchlistChange(ticker="GOOGL", action="add"),
            WatchlistChange(ticker="AAPL", action="remove"),
        ],
    )
    with patch.object(chat_module, "call_llm", new=AsyncMock(return_value=fake_response)):
        result = await handle_chat_message("update watchlist", db, price_cache)

    statuses = [a["status"] for a in result["action_results"]]
    assert statuses == ["executed", "executed"]

    async with db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ?", ("default",)
    ) as cursor:
        tickers = sorted(r[0] for r in await cursor.fetchall())
    assert tickers == ["GOOGL"]


async def test_llm_failure_returns_graceful_message(monkeypatch, db, price_cache):
    monkeypatch.delenv("LLM_MOCK", raising=False)

    with patch.object(
        chat_module, "call_llm", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        result = await handle_chat_message("hi", db, price_cache)

    assert "failed to respond" in result["message"]
    assert result["action_results"] == []

    async with db.execute(
        "SELECT COUNT(*) FROM chat_messages WHERE role = 'assistant'"
    ) as cursor:
        count = (await cursor.fetchone())[0]
    assert count == 1


async def test_history_passed_to_llm_with_portfolio_context(monkeypatch, db, price_cache):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    await db.execute(
        """INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("c1", "default", "user", "previous question", None, "2026-04-22T11:59:00Z"),
    )
    await db.execute(
        """INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("c2", "default", "assistant", "previous answer", None, "2026-04-22T11:59:01Z"),
    )
    await db.commit()

    fake_response = LLMResponse(message="ok", trades=[], watchlist_changes=[])
    mock_call = AsyncMock(return_value=fake_response)
    with patch.object(chat_module, "call_llm", new=mock_call):
        await handle_chat_message("new question", db, price_cache)

    messages = mock_call.await_args.args[0]
    roles = [m["role"] for m in messages]
    assert roles[0] == "system"
    assert "user" in roles and "assistant" in roles
    # Final message is the new user turn and includes portfolio context.
    assert messages[-1]["role"] == "user"
    assert "PORTFOLIO" in messages[-1]["content"]
    assert "new question" in messages[-1]["content"]
