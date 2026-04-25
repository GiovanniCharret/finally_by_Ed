"""Cross-source conformance tests.

Both `SimulatorDataSource` and `MassiveDataSource` must satisfy the same
lifecycle contract documented in `MarketDataSource`. This file runs both
through identical scripts so regressions on one side surface immediately.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market.cache import PriceCache
from app.market.interface import MarketDataSource
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource


def _snap(ticker: str, price: float, ts_ms: int = 1707580800000) -> MagicMock:
    snap = MagicMock()
    snap.ticker = ticker
    snap.last_trade = MagicMock()
    snap.last_trade.price = price
    snap.last_trade.timestamp = ts_ms
    return snap


async def _build_simulator(cache: PriceCache) -> SimulatorDataSource:
    return SimulatorDataSource(price_cache=cache, update_interval=0.5)


async def _build_massive(cache: PriceCache) -> MassiveDataSource:
    source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
    # Patch the thread boundary on the instance so the executor is never engaged.
    source._fetch_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[_snap("AAPL", 190.50), _snap("GOOGL", 175.25), _snap("TSLA", 250.00)]
    )
    return source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "builder",
    [_build_simulator, _build_massive],
    ids=["simulator", "massive"],
)
class TestSourceConformance:
    async def test_lifecycle_script(self, builder):
        cache = PriceCache()
        source = await builder(cache)
        assert isinstance(source, MarketDataSource)

        with patch("app.market.massive_client.RESTClient"):
            await source.start([" aapl ", "GOOGL"])
            try:
                tickers = source.get_tickers()
                assert "AAPL" in tickers
                assert "GOOGL" in tickers

                await source.add_ticker(" tsla ")
                assert "TSLA" in source.get_tickers()

                await source.remove_ticker("googl")
                assert "GOOGL" not in source.get_tickers()
            finally:
                await source.stop()

        # Stop must be idempotent across both implementations.
        await source.stop()

    async def test_initial_tickers_are_normalized(self, builder):
        cache = PriceCache()
        source = await builder(cache)

        with patch("app.market.massive_client.RESTClient"):
            await source.start([" aapl ", "googl"])
            try:
                tickers = source.get_tickers()
                assert all(t == t.upper() == t.strip() for t in tickers)
            finally:
                await source.stop()
