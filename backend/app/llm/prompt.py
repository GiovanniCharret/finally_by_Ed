"""Prompt construction for the FinAlly trading assistant."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant embedded in a simulated trading workstation.

Your responsibilities:
- Analyze the user's portfolio: composition, risk concentration, unrealized P&L, and exposure.
- Suggest trades with concise, data-driven reasoning when asked or when clearly warranted.
- Execute trades on the user's behalf when they ask or agree. Use the `trades` array.
- Manage the watchlist proactively when the user asks. Use the `watchlist_changes` array.
- Be concise. Prefer numbers over adjectives. No fluff.

Trading rules you must respect:
- This is a simulated portfolio with virtual cash. There is no real money involved.
- Buys require sufficient cash. Sells require sufficient shares (no short selling).
- Quantities are whole-number share counts (integers).
- Market orders only — fills happen at the latest streamed price.

Response format:
- Always respond with a JSON object matching the LLMResponse schema.
- `message` is the natural-language reply shown to the user.
- `trades` is an array of {ticker, side, quantity}; empty if none.
- `watchlist_changes` is an array of {ticker, action}; empty if none.
- Never wrap the JSON in markdown fences. Never include text outside the JSON.
- If a trade or watchlist change cannot be completed (insufficient cash/shares), still
  return your best message; the backend validates and reports outcomes.
"""


def build_system_prompt() -> str:
    """Return the system prompt for the FinAlly assistant."""
    return SYSTEM_PROMPT


def build_portfolio_context(
    portfolio: dict[str, Any],
    watchlist: list[dict[str, Any]],
) -> str:
    """Format portfolio + watchlist data into a human-readable LLM context block.

    `portfolio` shape:
        {
            "cash_balance": float,
            "total_value": float,
            "unrealized_pnl": float,
            "positions": [
                {"ticker", "quantity", "avg_cost", "current_price",
                 "market_value", "unrealized_pnl", "unrealized_pnl_percent"},
                ...
            ],
        }

    `watchlist` shape:
        [{"ticker": str, "price": float | None, "previous_price": float | None,
          "direction": str | None}, ...]
    """
    cash = portfolio.get("cash_balance", 0.0)
    total = portfolio.get("total_value", 0.0)
    pnl = portfolio.get("unrealized_pnl", 0.0)
    positions = portfolio.get("positions", []) or []

    lines: list[str] = []
    lines.append("=== PORTFOLIO ===")
    lines.append(f"Cash: ${cash:,.2f}")
    lines.append(f"Total value: ${total:,.2f}")
    lines.append(f"Unrealized P&L: ${pnl:,.2f}")

    if positions:
        lines.append("")
        lines.append("Positions:")
        for p in positions:
            ticker = p.get("ticker", "?")
            qty = p.get("quantity", 0)
            avg_cost = p.get("avg_cost", 0.0)
            price = p.get("current_price", 0.0)
            mv = p.get("market_value", 0.0)
            ppnl = p.get("unrealized_pnl", 0.0)
            ppct = p.get("unrealized_pnl_percent", 0.0)
            lines.append(
                f"  {ticker}: qty={qty} avg_cost=${avg_cost:.2f} "
                f"price=${price:.2f} mv=${mv:,.2f} "
                f"pnl=${ppnl:,.2f} ({ppct:+.2f}%)"
            )
    else:
        lines.append("")
        lines.append("Positions: (none)")

    lines.append("")
    lines.append("=== WATCHLIST ===")
    if watchlist:
        for w in watchlist:
            ticker = w.get("ticker", "?")
            price = w.get("price")
            prev = w.get("previous_price")
            direction = w.get("direction") or "flat"
            price_str = f"${price:.2f}" if isinstance(price, (int, float)) else "n/a"
            prev_str = f"${prev:.2f}" if isinstance(prev, (int, float)) else "n/a"
            lines.append(f"  {ticker}: price={price_str} prev={prev_str} dir={direction}")
    else:
        lines.append("  (empty)")

    return "\n".join(lines)
