"""Tests for app.llm.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.models import LLMResponse, TradeRequest, WatchlistChange


def test_llm_response_parses_full_payload():
    payload = """
    {
      "message": "Bought 5 AAPL.",
      "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5}],
      "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]
    }
    """
    parsed = LLMResponse.model_validate_json(payload)
    assert parsed.message == "Bought 5 AAPL."
    assert parsed.trades == [TradeRequest(ticker="AAPL", side="buy", quantity=5)]
    assert parsed.watchlist_changes == [
        WatchlistChange(ticker="PYPL", action="add")
    ]


def test_llm_response_defaults_empty_lists():
    parsed = LLMResponse.model_validate_json('{"message": "Hi."}')
    assert parsed.message == "Hi."
    assert parsed.trades == []
    assert parsed.watchlist_changes == []


def test_trade_request_rejects_invalid_side():
    with pytest.raises(ValidationError):
        TradeRequest(ticker="AAPL", side="hold", quantity=1)  # type: ignore[arg-type]


def test_watchlist_change_rejects_invalid_action():
    with pytest.raises(ValidationError):
        WatchlistChange(ticker="AAPL", action="watch")  # type: ignore[arg-type]


def test_llm_response_rejects_missing_message():
    with pytest.raises(ValidationError):
        LLMResponse.model_validate_json("{}")
