"""Tests for app.llm.mock."""

from __future__ import annotations

from app.llm.mock import get_mock_response
from app.llm.models import LLMResponse


def test_mock_returns_llm_response():
    result = get_mock_response("hello")
    assert isinstance(result, LLMResponse)
    assert result.message
    assert result.trades == []
    assert result.watchlist_changes == []


def test_mock_is_deterministic():
    a = get_mock_response("anything")
    b = get_mock_response("else")
    assert a.message == b.message
