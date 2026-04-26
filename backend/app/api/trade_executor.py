"""Shared trade execution helper used by both the REST trade route and the LLM chat flow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

USER_ID = "default"


class TradeError(Exception):
    """Raised when a trade fails validation.

    Attributes:
        code: Stable string identifier matching planning/PLAN.md error codes
            ("insufficient_cash", "insufficient_shares", "price_unavailable",
            "invalid_ticker", "invalid_quantity", "invalid_side", "no_position",
            "user_missing").
        message: Human-readable reason.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


async def execute_trade(
    ticker: str,
    side: str,
    quantity: int,
    db: Any,
    price_cache: Any,
) -> dict[str, Any]:
    """Execute a market order against the database and price cache.

    Returns a dict with keys: trade_id, ticker, side, quantity, price, executed_at.
    Raises TradeError with a stable code on validation failure.
    """
    ticker_norm = _normalize_ticker(ticker)
    if not ticker_norm:
        raise TradeError("invalid_ticker", "Ticker is required.")
    if side not in ("buy", "sell"):
        raise TradeError("invalid_side", f"Unknown side: {side}.")
    try:
        qty = int(quantity)
    except (TypeError, ValueError) as exc:
        raise TradeError("invalid_quantity", "Quantity must be an integer.") from exc
    if qty <= 0:
        raise TradeError("invalid_quantity", "Quantity must be positive.")

    price = price_cache.get_price(ticker_norm) if price_cache else None
    if price is None:
        raise TradeError(
            "price_unavailable",
            f"No live price available for {ticker_norm}.",
        )

    cost = price * qty

    async with db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,)
    ) as cursor:
        profile_row = await cursor.fetchone()
    if profile_row is None:
        raise TradeError("user_missing", "User profile missing.")
    cash = float(profile_row[0])

    async with db.execute(
        "SELECT id, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (USER_ID, ticker_norm),
    ) as cursor:
        pos_row = await cursor.fetchone()

    now = _now_iso()

    if side == "buy":
        if cost > cash:
            raise TradeError(
                "insufficient_cash",
                f"Need ${cost:.2f}, have ${cash:.2f}.",
            )
        new_cash = cash - cost
        if pos_row is None:
            await db.execute(
                """
                INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), USER_ID, ticker_norm, qty, price, now),
            )
        else:
            pos_id, old_qty, old_avg = pos_row
            old_qty_f = float(old_qty)
            new_qty = old_qty_f + qty
            new_avg = (old_qty_f * float(old_avg) + qty * price) / new_qty
            await db.execute(
                "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE id = ?",
                (new_qty, new_avg, now, pos_id),
            )
    else:  # sell
        if pos_row is None:
            raise TradeError(
                "insufficient_shares",
                f"No position in {ticker_norm} to sell.",
            )
        pos_id, old_qty, _ = pos_row
        old_qty_f = float(old_qty)
        if qty > old_qty_f:
            raise TradeError(
                "insufficient_shares",
                f"Trying to sell {qty}, only hold {old_qty_f:g}.",
            )
        new_qty = old_qty_f - qty
        new_cash = cash + cost
        if new_qty == 0:
            await db.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
        else:
            await db.execute(
                "UPDATE positions SET quantity = ?, updated_at = ? WHERE id = ?",
                (new_qty, now, pos_id),
            )

    await db.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (new_cash, USER_ID),
    )

    trade_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (trade_id, USER_ID, ticker_norm, side, qty, price, now),
    )
    await db.commit()

    return {
        "trade_id": trade_id,
        "ticker": ticker_norm,
        "side": side,
        "quantity": qty,
        "price": price,
        "executed_at": now,
    }


async def record_portfolio_snapshot(db: Any, price_cache: Any) -> float:
    """Compute total portfolio value (cash + market value) and insert a snapshot row.

    Returns the snapshot's total_value.
    """
    async with db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,)
    ) as cursor:
        profile_row = await cursor.fetchone()
    cash = float(profile_row[0]) if profile_row is not None else 0.0

    async with db.execute(
        "SELECT ticker, quantity FROM positions WHERE user_id = ?", (USER_ID,)
    ) as cursor:
        rows = await cursor.fetchall()

    market_value = 0.0
    for ticker, quantity in rows:
        price = price_cache.get_price(ticker) if price_cache else None
        if price is None:
            continue
        market_value += float(quantity) * float(price)

    total = cash + market_value
    await db.execute(
        """
        INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
        VALUES (?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), USER_ID, total, _now_iso()),
    )
    await db.commit()
    return total
