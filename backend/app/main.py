"""FastAPI app entry point: lifespan, routers, static frontend."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import chat, health, portfolio, watchlist
from app.api.dependencies import set_market_source, set_price_cache
from app.api.trade_executor import record_portfolio_snapshot
from app.market import PriceCache, create_market_data_source, create_stream_router
from db import get_db, init_db

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

DEFAULT_TICKERS: list[str] = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]

PORTFOLIO_SNAPSHOT_INTERVAL_S = 30.0

# Module-level singletons. The PriceCache must exist at app-construction time
# so the SSE router can be registered BEFORE the static catch-all at "/";
# Starlette resolves routes in registration order, and a `/` mount otherwise
# shadows everything (including /api/stream/prices).
price_cache: PriceCache = PriceCache()
set_price_cache(price_cache)


async def _portfolio_snapshot_loop(cache: PriceCache) -> None:
    """Record a portfolio_snapshots row every PORTFOLIO_SNAPSHOT_INTERVAL_S seconds."""
    while True:
        try:
            await asyncio.sleep(PORTFOLIO_SNAPSHOT_INTERVAL_S)
            async with get_db() as conn:
                await record_portfolio_snapshot(conn, cache)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("portfolio snapshot loop iteration failed")


async def _load_user_watchlist() -> list[str]:
    """Read the persisted watchlist from the DB; falls back to defaults if empty."""
    async with get_db() as conn:
        async with conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
        ) as cursor:
            rows = await cursor.fetchall()
    tickers = [row[0] for row in rows]
    return tickers or DEFAULT_TICKERS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, start market data source, schedule snapshot task."""
    await init_db()

    market_source = create_market_data_source(price_cache)
    set_market_source(market_source)

    tickers = await _load_user_watchlist()
    await market_source.start(tickers)

    snapshot_task = asyncio.create_task(_portfolio_snapshot_loop(price_cache))

    try:
        yield
    finally:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await market_source.stop()
        except Exception:
            logger.exception("error stopping market data source")


def create_app() -> FastAPI:
    """Build the FastAPI app with all routers and static frontend mount."""
    app = FastAPI(title="FinAlly Backend", lifespan=lifespan)

    # SSE stream router first — registered at app creation time so it sits
    # ahead of the static catch-all in the route table. The router already
    # carries its own "/api/stream" prefix, so don't double it here.
    stream_router = create_stream_router(price_cache)
    app.include_router(stream_router)

    app.include_router(health.router, prefix="/api")
    app.include_router(portfolio.router, prefix="/api")
    app.include_router(watchlist.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    # Static catch-all LAST — must be after every API route or it shadows them.
    static_path = Path(__file__).resolve().parent.parent / "static"
    if static_path.exists() and static_path.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(static_path), html=True),
            name="static",
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )
