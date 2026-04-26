"""Tests for the /api/portfolio routes."""

from __future__ import annotations

import pytest


async def _seed_position(db, ticker: str, qty: float, avg: float) -> None:
    await db.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (f"p-{ticker}", "default", ticker, qty, avg, "2026-04-22T12:00:00Z"),
    )
    await db.commit()


def test_get_portfolio_empty(client) -> None:
    response = client.get("/api/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["cash_balance"] == 10000.0
    assert body["total_value"] == 10000.0
    assert body["unrealized_pnl"] == 0.0
    assert body["positions"] == []


@pytest.mark.asyncio
async def test_get_portfolio_with_positions(client, db_conn) -> None:
    await _seed_position(db_conn, "AAPL", 5.0, 90.0)  # cur 100, gain 50
    await _seed_position(db_conn, "GOOGL", 2.0, 200.0)  # cur 175, loss 50

    response = client.get("/api/portfolio")
    assert response.status_code == 200
    body = response.json()
    positions = {p["ticker"]: p for p in body["positions"]}

    aapl = positions["AAPL"]
    assert aapl["quantity"] == 5.0
    assert aapl["avg_cost"] == 90.0
    assert aapl["current_price"] == 100.0
    assert aapl["market_value"] == 500.0
    assert aapl["unrealized_pnl"] == 50.0
    assert aapl["unrealized_pnl_percent"] == pytest.approx(50.0 / 450.0 * 100.0)

    googl = positions["GOOGL"]
    assert googl["quantity"] == 2.0
    assert googl["current_price"] == 175.0
    assert googl["market_value"] == 350.0
    assert googl["unrealized_pnl"] == -50.0

    assert body["cash_balance"] == 10000.0
    assert body["total_value"] == pytest.approx(10000.0 + 500.0 + 350.0)
    assert body["unrealized_pnl"] == pytest.approx(0.0)


def test_post_trade_buy_success(client) -> None:
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "aapl", "quantity": 3, "side": "buy"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["side"] == "buy"
    assert body["quantity"] == 3
    assert body["price"] == 100.0
    assert "trade_id" in body
    assert body["executed_at"]

    # Verify portfolio reflects the buy
    portfolio = client.get("/api/portfolio").json()
    assert portfolio["cash_balance"] == pytest.approx(10000.0 - 300.0)
    aapl = next(p for p in portfolio["positions"] if p["ticker"] == "AAPL")
    assert aapl["quantity"] == 3.0
    assert aapl["avg_cost"] == 100.0


def test_post_trade_normalizes_ticker_case(client) -> None:
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "  aapl ", "quantity": 1, "side": "buy"},
    )
    assert response.status_code == 200
    assert response.json()["ticker"] == "AAPL"


def test_post_trade_buy_insufficient_cash(client) -> None:
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 10000, "side": "buy"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "insufficient_cash"


def test_post_trade_sell_no_position(client) -> None:
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 1, "side": "sell"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "insufficient_shares"


@pytest.mark.asyncio
async def test_post_trade_sell_too_many(client, db_conn) -> None:
    await _seed_position(db_conn, "AAPL", 2.0, 90.0)
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 5, "side": "sell"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "insufficient_shares"


@pytest.mark.asyncio
async def test_post_trade_sell_zeroes_position(client, db_conn) -> None:
    await _seed_position(db_conn, "AAPL", 2.0, 90.0)
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 2, "side": "sell"},
    )
    assert response.status_code == 200

    portfolio = client.get("/api/portfolio").json()
    assert all(p["ticker"] != "AAPL" for p in portfolio["positions"])
    assert portfolio["cash_balance"] == pytest.approx(10000.0 + 200.0)


def test_post_trade_price_unavailable(client) -> None:
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "TSLA", "quantity": 1, "side": "buy"},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "price_unavailable"


def test_post_trade_invalid_quantity(client) -> None:
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 0, "side": "buy"},
    )
    # Pydantic validation rejects with 422
    assert response.status_code == 422


def test_post_trade_invalid_side(client) -> None:
    response = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 1, "side": "hold"},
    )
    assert response.status_code == 422


def test_post_trade_buy_recomputes_avg_cost(client) -> None:
    # First buy: 2 @ 100
    r1 = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 2, "side": "buy"},
    )
    assert r1.status_code == 200
    # Second buy at different cached price
    from app.api.dependencies import get_price_cache

    get_price_cache().update("AAPL", 110.0)

    r2 = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 3, "side": "buy"},
    )
    assert r2.status_code == 200

    portfolio = client.get("/api/portfolio").json()
    aapl = next(p for p in portfolio["positions"] if p["ticker"] == "AAPL")
    assert aapl["quantity"] == 5.0
    expected_avg = (2 * 100.0 + 3 * 110.0) / 5
    assert aapl["avg_cost"] == pytest.approx(expected_avg)


@pytest.mark.asyncio
async def test_get_portfolio_history(client, db_conn) -> None:
    await db_conn.execute(
        """
        INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        ("s2", "default", 10500.0, "2026-04-22T12:01:00Z"),
    )
    await db_conn.execute(
        """
        INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        ("s1", "default", 10000.0, "2026-04-22T12:00:00Z"),
    )
    await db_conn.commit()

    response = client.get("/api/portfolio/history")
    assert response.status_code == 200
    snapshots = response.json()["snapshots"]
    # Ordered ascending by recorded_at
    assert [s["recorded_at"] for s in snapshots] == [
        "2026-04-22T12:00:00Z",
        "2026-04-22T12:01:00Z",
    ]
    assert [s["total_value"] for s in snapshots] == [10000.0, 10500.0]


def test_get_portfolio_history_empty(client) -> None:
    response = client.get("/api/portfolio/history")
    assert response.status_code == 200
    assert response.json() == {"snapshots": []}
