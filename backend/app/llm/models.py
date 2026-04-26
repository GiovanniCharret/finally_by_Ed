"""Pydantic models for structured LLM output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TradeRequest(BaseModel):
    """A single trade requested by the LLM."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: int


class WatchlistChange(BaseModel):
    """A single watchlist modification requested by the LLM."""

    ticker: str
    action: Literal["add", "remove"]


class LLMResponse(BaseModel):
    """Full structured response returned by the LLM."""

    message: str
    trades: list[TradeRequest] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)
