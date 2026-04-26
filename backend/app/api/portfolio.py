"""Portfolio routes: positions, trade execution, history snapshots."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .dependencies import get_db, get_price_cache
from .trade_executor import USER_ID, TradeError, execute_trade

router = APIRouter(tags=["portfolio"])


class TradeRequestBody(BaseModel):
    ticker: str
    quantity: int = Field(..., gt=0)
    side: Literal["buy", "sell"]


def _error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


@router.get("/portfolio")
async def get_portfolio(
    db: Any = Depends(get_db),
    price_cache: Any = Depends(get_price_cache),
) -> dict[str, Any]:
    """Return cash, total value, unrealized P&L, and per-position details."""
    async with db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,)
    ) as cursor:
        profile_row = await cursor.fetchone()
    cash = float(profile_row[0]) if profile_row is not None else 0.0

    async with db.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
        (USER_ID,),
    ) as cursor:
        rows = await cursor.fetchall()

    positions: list[dict[str, Any]] = []
    market_value_total = 0.0
    cost_basis_total = 0.0

    for ticker, quantity, avg_cost in rows:
        qty = float(quantity)
        avg = float(avg_cost)
        current_price = price_cache.get_price(ticker)
        price = float(current_price) if current_price is not None else 0.0
        market_value = qty * price
        cost_basis = qty * avg
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
        market_value_total += market_value
        cost_basis_total += cost_basis
        positions.append(
            {
                "ticker": ticker,
                "quantity": qty,
                "avg_cost": avg,
                "current_price": price,
                "market_value": market_value,
                "unrealized_pnl": pnl,
                "unrealized_pnl_percent": pnl_pct,
            }
        )

    return {
        "cash_balance": cash,
        "total_value": cash + market_value_total,
        "unrealized_pnl": market_value_total - cost_basis_total,
        "positions": positions,
    }


@router.post("/portfolio/trade")
async def trade(
    req: TradeRequestBody,
    db: Any = Depends(get_db),
    price_cache: Any = Depends(get_price_cache),
) -> Any:
    """Execute a market buy or sell. Returns the executed trade or a structured error."""
    try:
        result = await execute_trade(req.ticker, req.side, req.quantity, db, price_cache)
    except TradeError as exc:
        status = 400
        if exc.code == "price_unavailable":
            status = 503
        return _error_response(exc.code, exc.message, status)
    return result


@router.get("/portfolio/history")
async def portfolio_history(db: Any = Depends(get_db)) -> dict[str, Any]:
    """Return portfolio value snapshots ordered by recorded_at ascending."""
    async with db.execute(
        """
        SELECT total_value, recorded_at FROM portfolio_snapshots
        WHERE user_id = ?
        ORDER BY recorded_at
        """,
        (USER_ID,),
    ) as cursor:
        rows = await cursor.fetchall()

    snapshots = [
        {"total_value": float(total_value), "recorded_at": recorded_at}
        for total_value, recorded_at in rows
    ]
    return {"snapshots": snapshots}
