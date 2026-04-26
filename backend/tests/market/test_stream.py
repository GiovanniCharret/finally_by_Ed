"""Tests for the SSE stream generator and router factory."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import APIRouter

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


class _FakeClient:
    host = "test-client"


class FakeRequest:
    """Minimal stand-in for fastapi.Request used by the SSE generator."""

    def __init__(self, disconnect_after: int | None = None) -> None:
        self.client = _FakeClient()
        self._calls = 0
        self._disconnect_after = disconnect_after

    async def is_disconnected(self) -> bool:
        self._calls += 1
        if self._disconnect_after is None:
            return False
        return self._calls > self._disconnect_after


async def _drain(gen, *, max_events: int) -> list[str]:
    """Pull at most `max_events` chunks from the generator, then close it."""
    chunks: list[str] = []
    try:
        for _ in range(max_events):
            chunks.append(await asyncio.wait_for(gen.__anext__(), timeout=2.0))
    except StopAsyncIteration:
        pass
    finally:
        await gen.aclose()
    return chunks


@pytest.mark.asyncio
class TestStreamGenerator:
    async def test_first_chunk_is_retry_directive(self):
        cache = PriceCache()
        request = FakeRequest(disconnect_after=0)
        gen = _generate_events(cache, request, interval=0.01, heartbeat_interval=999.0)
        chunks = await _drain(gen, max_events=2)
        assert chunks[0] == "retry: 1000\n\n"

    async def test_emits_data_event_on_version_change(self):
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        request = FakeRequest(disconnect_after=2)
        gen = _generate_events(cache, request, interval=0.01, heartbeat_interval=999.0)

        chunks = await _drain(gen, max_events=4)

        event_chunks = [c for c in chunks if c.startswith("event: price\n")]
        assert event_chunks, "expected at least one price event"
        first = event_chunks[0]
        assert first.startswith("event: price\ndata: ")
        data_line = first.split("\n")[1]
        payload = json.loads(data_line[len("data: ") :])
        assert payload["ticker"] == "AAPL"
        assert payload["price"] == 190.50
        assert payload["previous_price"] == 190.50
        # Timestamp must be ISO 8601 UTC per PLAN.md §6
        assert payload["timestamp"].endswith("Z")
        assert "T" in payload["timestamp"]
        assert payload["direction"] in ("up", "down", "unchanged")

    async def test_no_data_event_when_version_unchanged(self):
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        request = FakeRequest(disconnect_after=4)
        gen = _generate_events(cache, request, interval=0.01, heartbeat_interval=999.0)

        chunks = await _drain(gen, max_events=10)
        event_chunks = [c for c in chunks if c.startswith("event: price\n")]
        # Exactly one snapshot — the initial cache version. No further changes occurred.
        assert len(event_chunks) == 1

    async def test_emits_data_event_after_remove(self):
        """Removing a ticker bumps the version and must surface to the stream."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        request = FakeRequest(disconnect_after=6)
        gen = _generate_events(cache, request, interval=0.01, heartbeat_interval=999.0)

        # Pull the initial snapshot first so subsequent changes register as new
        first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # retry
        second = await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # initial data
        assert first.startswith("retry:")
        assert second.startswith("event: price\n")

        cache.remove("AAPL")
        # Drain a few more cycles
        rest = await _drain(gen, max_events=4)
        events_after_remove = [c for c in rest if c.startswith("event: price\n")]
        # Cache is empty after remove, so no price event is emitted (generator
        # only yields when prices is non-empty). The version still changed, so
        # last_version was advanced — but we should NOT see a stale snapshot.
        assert all('"AAPL"' not in chunk for chunk in events_after_remove)

    async def test_heartbeat_emitted_when_idle(self):
        cache = PriceCache()
        request = FakeRequest(disconnect_after=10)
        gen = _generate_events(cache, request, interval=0.01, heartbeat_interval=0.02)

        chunks = await _drain(gen, max_events=20)
        heartbeat_chunks = [c for c in chunks if c == ": heartbeat\n\n"]
        assert heartbeat_chunks, "expected at least one heartbeat during idle stream"

    async def test_disconnect_terminates_generator(self):
        cache = PriceCache()
        request = FakeRequest(disconnect_after=1)
        gen = _generate_events(cache, request, interval=0.01, heartbeat_interval=999.0)

        chunks = await _drain(gen, max_events=10)
        # Generator must eventually stop; we should not block beyond the timeout.
        assert len(chunks) >= 1


class TestRouterFactory:
    def test_returns_a_fresh_router_each_call(self):
        cache = PriceCache()
        router_a = create_stream_router(cache)
        router_b = create_stream_router(cache)
        assert isinstance(router_a, APIRouter)
        assert router_a is not router_b

    def test_no_duplicate_routes_after_repeated_factory_calls(self):
        """Calling the factory N times must not register N copies of /prices."""
        cache = PriceCache()
        for _ in range(5):
            router = create_stream_router(cache)

        prices_routes = [r for r in router.routes if getattr(r, "path", "") == "/api/stream/prices"]
        assert len(prices_routes) == 1
