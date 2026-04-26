"""Tests for app.llm.client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.client import LLMConfigurationError, call_llm
from app.llm.models import LLMResponse


@pytest.mark.asyncio
async def test_call_llm_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError):
        await call_llm([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_call_llm_parses_structured_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")

    fake_content = (
        '{"message":"Done.","trades":[{"ticker":"AAPL","side":"buy","quantity":1}],'
        '"watchlist_changes":[]}'
    )
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=fake_content))]
    )

    with patch(
        "app.llm.client.litellm.acompletion",
        new=AsyncMock(return_value=fake_response),
    ) as mock_completion:
        result = await call_llm([{"role": "user", "content": "buy AAPL"}])

    assert isinstance(result, LLMResponse)
    assert result.message == "Done."
    assert len(result.trades) == 1
    assert result.trades[0].ticker == "AAPL"

    # Confirm the LiteLLM call used the documented Cerebras setup.
    kwargs = mock_completion.await_args.kwargs
    assert kwargs["model"] == "openrouter/openai/gpt-oss-120b"
    assert kwargs["api_key"] == "fake-key"
    assert kwargs["response_format"] is LLMResponse
    assert kwargs["extra_body"] == {"provider": {"order": ["cerebras"]}}


@pytest.mark.asyncio
async def test_call_llm_raises_on_empty_content(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
    )
    with patch(
        "app.llm.client.litellm.acompletion",
        new=AsyncMock(return_value=fake_response),
    ):
        with pytest.raises(ValueError):
            await call_llm([{"role": "user", "content": "hi"}])
