"""Deterministic mock LLM responses for tests and offline mode."""

from __future__ import annotations

from .models import LLMResponse

MOCK_MESSAGE = (
    "I'm your AI trading assistant. How can I help you analyze your "
    "portfolio or execute trades?"
)


def get_mock_response(user_message: str) -> LLMResponse:
    """Return a deterministic mock response.

    The `user_message` is accepted (and ignored) so callers can swap this
    for the real LLM without changing the call signature. Tests that need
    a richer mock should patch this function or use parsing helpers
    directly.
    """
    return LLMResponse(message=MOCK_MESSAGE, trades=[], watchlist_changes=[])
