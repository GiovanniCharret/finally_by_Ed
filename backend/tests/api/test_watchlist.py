"""Tests for the /api/watchlist routes."""

from __future__ import annotations


def test_get_watchlist_returns_seeded_tickers(client) -> None:
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    body = response.json()
    tickers = body["tickers"]
    assert any(t["ticker"] == "AAPL" for t in tickers)
    aapl = next(t for t in tickers if t["ticker"] == "AAPL")
    assert aapl["price"] == 100.0
    assert aapl["direction"] in ("up", "down", "flat")


def test_get_watchlist_handles_uncached_ticker(client, db_conn) -> None:
    import asyncio

    async def _add():
        await db_conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            ("w-uncached", "default", "ZZZ", "2026-04-22T12:00:01Z"),
        )
        await db_conn.commit()

    asyncio.get_event_loop().run_until_complete(_add())

    response = client.get("/api/watchlist")
    assert response.status_code == 200
    tickers = response.json()["tickers"]
    zzz = next(t for t in tickers if t["ticker"] == "ZZZ")
    assert zzz["price"] is None
    assert zzz["direction"] is None


def test_post_watchlist_adds_and_normalizes(client, market_source) -> None:
    response = client.post("/api/watchlist", json={"ticker": " googl "})
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "GOOGL"
    assert body["status"] == "added"
    # market source should be informed
    assert "GOOGL" in market_source.added

    listing = client.get("/api/watchlist").json()
    assert any(t["ticker"] == "GOOGL" for t in listing["tickers"])


def test_post_watchlist_duplicate_returns_409(client) -> None:
    response = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "duplicate_ticker"


def test_post_watchlist_invalid_ticker(client) -> None:
    response = client.post("/api/watchlist", json={"ticker": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_ticker"


def test_delete_watchlist_removes_and_normalizes(client, market_source) -> None:
    response = client.delete("/api/watchlist/aapl")
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["status"] == "removed"
    assert "AAPL" in market_source.removed

    listing = client.get("/api/watchlist").json()
    assert all(t["ticker"] != "AAPL" for t in listing["tickers"])


def test_delete_watchlist_not_found_returns_404(client) -> None:
    response = client.delete("/api/watchlist/UNKNOWN")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
