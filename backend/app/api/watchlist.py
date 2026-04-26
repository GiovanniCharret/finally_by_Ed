"""Watchlist CRUD routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .dependencies import get_db, get_market_source, get_price_cache
from .trade_executor import USER_ID

router = APIRouter(tags=["watchlist"])


class WatchlistAddBody(BaseModel):
    ticker: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


def _error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


@router.get("/watchlist")
async def list_watchlist(
    db: Any = Depends(get_db),
    price_cache: Any = Depends(get_price_cache),
) -> dict[str, Any]:
    async with db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at",
        (USER_ID,),
    ) as cursor:
        rows = await cursor.fetchall()

    tickers: list[dict[str, Any]] = []
    for (ticker,) in rows:
        update = price_cache.get(ticker)
        if update is not None:
            tickers.append(
                {
                    "ticker": ticker,
                    "price": update.price,
                    "previous_price": update.previous_price,
                    "direction": update.direction,
                }
            )
        else:
            tickers.append(
                {
                    "ticker": ticker,
                    "price": None,
                    "previous_price": None,
                    "direction": None,
                }
            )
    return {"tickers": tickers}


@router.post("/watchlist")
async def add_to_watchlist(
    body: WatchlistAddBody,
    db: Any = Depends(get_db),
) -> Any:
    ticker = _normalize_ticker(body.ticker)
    if not ticker:
        return _error_response("invalid_ticker", "Ticker is required.", 400)

    async with db.execute(
        "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
        (USER_ID, ticker),
    ) as cursor:
        existing = await cursor.fetchone()
    if existing is not None:
        return _error_response(
            "duplicate_ticker", f"{ticker} is already on the watchlist.", 409
        )

    await db.execute(
        """
        INSERT INTO watchlist (id, user_id, ticker, added_at)
        VALUES (?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), USER_ID, ticker, _now_iso()),
    )
    await db.commit()

    market_source = get_market_source()
    if market_source is not None:
        try:
            await market_source.add_ticker(ticker)
        except Exception:
            # Adding to a live market source must not block the DB write.
            pass

    return {"ticker": ticker, "status": "added"}


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    db: Any = Depends(get_db),
) -> Any:
    ticker_norm = _normalize_ticker(ticker)
    async with db.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (USER_ID, ticker_norm),
    ) as cursor:
        removed = cursor.rowcount
    await db.commit()
    if not removed:
        return _error_response(
            "not_found", f"{ticker_norm} is not on the watchlist.", 404
        )

    market_source = get_market_source()
    if market_source is not None:
        try:
            await market_source.remove_ticker(ticker_norm)
        except Exception:
            pass

    return {"ticker": ticker_norm, "status": "removed"}
