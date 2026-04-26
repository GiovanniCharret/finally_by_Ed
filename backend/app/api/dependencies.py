"""FastAPI dependency providers for the API routes.

These are simple module-level singletons populated by the lifespan in app.main.
Tests override them via FastAPI's `app.dependency_overrides` machinery.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.market import PriceCache
from db.database import get_db as _get_db_ctx

_state: dict[str, Any] = {
    "price_cache": None,
    "market_source": None,
}


def set_price_cache(cache: PriceCache) -> None:
    _state["price_cache"] = cache


def set_market_source(source: Any) -> None:
    _state["market_source"] = source


def get_price_cache() -> PriceCache:
    cache = _state["price_cache"]
    if cache is None:
        raise RuntimeError("PriceCache has not been initialized.")
    return cache


def get_market_source() -> Any:
    return _state["market_source"]


async def get_db() -> AsyncIterator[Any]:
    """Yield an async sqlite connection for one request."""
    async with _get_db_ctx() as conn:
        yield conn
