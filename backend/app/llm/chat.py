"""Chat handler: load context, call LLM, auto-execute actions, persist messages."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from .client import LLMConfigurationError, call_llm
from .mock import get_mock_response
from .models import LLMResponse, TradeRequest, WatchlistChange
from .prompt import build_portfolio_context, build_system_prompt

USER_ID = "default"
HISTORY_LIMIT = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


async def _load_user_profile(db: Any) -> dict[str, Any]:
    """Return the default user's profile (cash_balance) or sane defaults."""
    async with db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?",
        (USER_ID,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return {"cash_balance": 0.0}
    return {"cash_balance": float(row[0])}


async def _load_positions(db: Any, price_cache: Any) -> list[dict[str, Any]]:
    """Load all positions for the default user, joined with cached prices."""
    async with db.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ?",
        (USER_ID,),
    ) as cursor:
        rows = await cursor.fetchall()

    positions: list[dict[str, Any]] = []
    for ticker, quantity, avg_cost in rows:
        current_price = price_cache.get_price(ticker) if price_cache else None
        price = float(current_price) if current_price is not None else 0.0
        qty = float(quantity)
        avg = float(avg_cost)
        market_value = qty * price
        cost_basis = qty * avg
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
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
    return positions


async def _load_watchlist(db: Any, price_cache: Any) -> list[dict[str, Any]]:
    """Load watchlist tickers with latest cached prices."""
    async with db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at",
        (USER_ID,),
    ) as cursor:
        rows = await cursor.fetchall()

    watchlist: list[dict[str, Any]] = []
    for (ticker,) in rows:
        update = price_cache.get(ticker) if price_cache else None
        if update is not None:
            watchlist.append(
                {
                    "ticker": ticker,
                    "price": update.price,
                    "previous_price": update.previous_price,
                    "direction": update.direction,
                }
            )
        else:
            watchlist.append(
                {
                    "ticker": ticker,
                    "price": None,
                    "previous_price": None,
                    "direction": None,
                }
            )
    return watchlist


async def _build_portfolio_summary(
    db: Any, price_cache: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (portfolio_dict, watchlist_list) for prompt context."""
    profile = await _load_user_profile(db)
    positions = await _load_positions(db, price_cache)
    watchlist = await _load_watchlist(db, price_cache)

    cash = profile["cash_balance"]
    market_value = sum(p["market_value"] for p in positions)
    cost_basis = sum(p["quantity"] * p["avg_cost"] for p in positions)
    portfolio = {
        "cash_balance": cash,
        "total_value": cash + market_value,
        "unrealized_pnl": market_value - cost_basis,
        "positions": positions,
    }
    return portfolio, watchlist


async def _load_history(db: Any, limit: int = HISTORY_LIMIT) -> list[dict[str, str]]:
    """Load the most recent chat messages (oldest first), capped at `limit`."""
    async with db.execute(
        """
        SELECT role, content FROM chat_messages
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (USER_ID, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    rows = list(reversed(rows))
    return [{"role": role, "content": content} for role, content in rows]


# ---------------------------------------------------------------------------
# Trade & watchlist execution
# ---------------------------------------------------------------------------

# Friendly prefixes added to the reason text exposed in action_results so the
# LLM (and our chat-flow tests) can recognize categorized failures.
_FAILURE_PREFIXES: dict[str, str] = {
    "insufficient_cash": "Insufficient cash",
    "insufficient_shares": "Insufficient shares",
    "price_unavailable": "Price unavailable",
    "invalid_ticker": "Invalid ticker",
    "invalid_quantity": "Invalid quantity",
    "invalid_side": "Invalid side",
    "user_missing": "User missing",
}


async def _execute_trade(
    db: Any, price_cache: Any, trade: TradeRequest
) -> dict[str, Any]:
    """Validate and execute a single trade. Returns an action_result dict."""
    from app.api.trade_executor import TradeError, execute_trade

    ticker = _normalize_ticker(trade.ticker)
    base: dict[str, Any] = {
        "type": "trade",
        "ticker": ticker,
        "side": trade.side,
        "quantity": int(trade.quantity),
    }

    try:
        result = await execute_trade(
            trade.ticker, trade.side, trade.quantity, db, price_cache
        )
    except TradeError as exc:
        prefix = _FAILURE_PREFIXES.get(exc.code, exc.code)
        return {**base, "status": "failed", "reason": f"{prefix}: {exc.message}"}

    return {
        **base,
        "ticker": result["ticker"],
        "status": "executed",
        "trade_id": result["trade_id"],
        "price": result["price"],
        "executed_at": result["executed_at"],
    }


async def _execute_watchlist_change(
    db: Any, change: WatchlistChange
) -> dict[str, Any]:
    """Validate and execute a single watchlist change."""
    ticker = _normalize_ticker(change.ticker)
    action = change.action

    base: dict[str, Any] = {
        "type": "watchlist",
        "ticker": ticker,
        "action": action,
    }

    if not ticker:
        return {**base, "status": "failed", "reason": "Invalid ticker."}

    if action == "add":
        async with db.execute(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
            (USER_ID, ticker),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing is not None:
            return {**base, "status": "failed", "reason": "Already on watchlist."}
        await db.execute(
            """
            INSERT INTO watchlist (id, user_id, ticker, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), USER_ID, ticker, _now_iso()),
        )
        await db.commit()
        return {**base, "status": "executed"}

    if action == "remove":
        async with db.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
            (USER_ID, ticker),
        ) as cursor:
            removed = cursor.rowcount
        await db.commit()
        if not removed:
            return {**base, "status": "failed", "reason": "Not on watchlist."}
        return {**base, "status": "executed"}

    return {**base, "status": "failed", "reason": f"Unknown action: {action}."}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def handle_chat_message(
    user_message: str,
    db: Any,
    price_cache: Any,
) -> dict[str, Any]:
    """Process a user chat message end-to-end.

    Steps:
      1. Load portfolio & watchlist context from DB + cache.
      2. Load recent chat history.
      3. Build LLM messages (system + history + new turn).
      4. Call the LLM (or mock when LLM_MOCK=true).
      5. Auto-execute trades and watchlist changes.
      6. Persist user + assistant messages to chat_messages.
      7. Return the response payload for the API layer.
    """
    portfolio, watchlist = await _build_portfolio_summary(db, price_cache)
    history = await _load_history(db)

    system_prompt = build_system_prompt()
    portfolio_context = build_portfolio_context(portfolio, watchlist)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": f"{portfolio_context}\n\nUser: {user_message}",
        }
    )

    use_mock = os.environ.get("LLM_MOCK", "").lower() == "true"
    if use_mock:
        llm_response: LLMResponse = get_mock_response(user_message)
    else:
        try:
            llm_response = await call_llm(messages)
        except LLMConfigurationError as exc:
            llm_response = LLMResponse(
                message=f"LLM unavailable: {exc}",
                trades=[],
                watchlist_changes=[],
            )
        except Exception as exc:  # noqa: BLE001 — surface any LLM failure
            llm_response = LLMResponse(
                message=f"Sorry, the assistant failed to respond ({exc}).",
                trades=[],
                watchlist_changes=[],
            )

    action_results: list[dict[str, Any]] = []
    for trade in llm_response.trades:
        action_results.append(await _execute_trade(db, price_cache, trade))
    for change in llm_response.watchlist_changes:
        action_results.append(await _execute_watchlist_change(db, change))

    now = _now_iso()
    await db.execute(
        """
        INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), USER_ID, "user", user_message, None, now),
    )
    await db.execute(
        """
        INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            USER_ID,
            "assistant",
            llm_response.message,
            json.dumps(action_results) if action_results else None,
            _now_iso(),
        ),
    )
    await db.commit()

    return {
        "message": llm_response.message,
        "trades": [t.model_dump() for t in llm_response.trades],
        "watchlist_changes": [w.model_dump() for w in llm_response.watchlist_changes],
        "action_results": action_results,
    }
