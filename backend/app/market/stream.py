"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache
from .models import PriceUpdate

logger = logging.getLogger(__name__)

# Comment heartbeat sent on this cadence so proxies/clients can detect stalls
# during long stretches with no price-cache changes.
HEARTBEAT_INTERVAL = 15.0


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Create the SSE streaming router with a reference to the price cache.

    A fresh APIRouter is built per call so repeated invocations (in tests or
    future app factories) do not accumulate duplicate `/prices` routes on a
    shared module-level router.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint for live price updates.

        Streams all tracked ticker prices whenever the cache version changes.
        Emits a comment heartbeat every HEARTBEAT_INTERVAL seconds so clients
        and intermediaries can detect stalled streams.
        """
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
    heartbeat_interval: float = HEARTBEAT_INTERVAL,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted price events.

    Emits a JSON `data:` event on every cache version change and a `: heartbeat`
    comment every `heartbeat_interval` seconds when the cache is otherwise idle.
    Stops when the client disconnects.
    """
    yield "retry: 1000\n\n"

    last_version = -1
    last_heartbeat = time.monotonic()
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()

                if prices:
                    for update in prices.values():
                        yield _format_price_event(update)
                    last_heartbeat = time.monotonic()

            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)


def _format_price_event(update: PriceUpdate) -> str:
    """Render a PriceUpdate as a single SSE `event: price` block per PLAN.md §6."""
    direction = update.direction if update.direction != "flat" else "unchanged"
    payload = {
        "ticker": update.ticker,
        "price": update.price,
        "previous_price": update.previous_price,
        "timestamp": datetime.fromtimestamp(update.timestamp, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "direction": direction,
    }
    return f"event: price\ndata: {json.dumps(payload)}\n\n"
