"""Tests for app.llm.prompt."""

from __future__ import annotations

from app.llm.prompt import build_portfolio_context, build_system_prompt


def test_system_prompt_mentions_finally_and_json():
    prompt = build_system_prompt()
    assert "FinAlly" in prompt
    assert "JSON" in prompt or "json" in prompt


def test_portfolio_context_renders_positions_and_watchlist():
    portfolio = {
        "cash_balance": 8420.50,
        "total_value": 10120.75,
        "unrealized_pnl": 120.75,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 5,
                "avg_cost": 190.00,
                "current_price": 194.25,
                "market_value": 971.25,
                "unrealized_pnl": 21.25,
                "unrealized_pnl_percent": 2.24,
            }
        ],
    }
    watchlist = [
        {"ticker": "GOOGL", "price": 175.0, "previous_price": 174.5, "direction": "up"},
        {"ticker": "TSLA", "price": None, "previous_price": None, "direction": None},
    ]
    ctx = build_portfolio_context(portfolio, watchlist)

    assert "AAPL" in ctx
    assert "$8,420.50" in ctx
    assert "GOOGL" in ctx
    assert "TSLA" in ctx
    assert "n/a" in ctx  # for the missing TSLA price


def test_portfolio_context_handles_empty_state():
    ctx = build_portfolio_context(
        {"cash_balance": 10000.0, "total_value": 10000.0, "unrealized_pnl": 0.0, "positions": []},
        [],
    )
    assert "Positions: (none)" in ctx
    assert "(empty)" in ctx
