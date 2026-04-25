# Market Data Interface

Unified Python interface so the rest of FinAlly never knows whether prices come from the Massive API or the in‑process simulator. This document is the source‑of‑truth contract for `backend/app/market/`.

---

## 1. Goal

> **One interface, two implementations, one cache.**
>
> SSE streaming, portfolio valuation, trade execution, and tests all read from the same `PriceCache`. Producers (real or fake) write into it on their own schedule.

```
                ┌─────────────────────────────┐
                │   create_market_data_source │
                │  (reads MASSIVE_API_KEY)    │
                └──────────────┬──────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
   ┌────────────────────┐           ┌────────────────────┐
   │ SimulatorDataSource│           │ MassiveDataSource  │
   │  (default, GBM)    │           │  (REST poller)     │
   └─────────┬──────────┘           └─────────┬──────────┘
             │                                │
             └──────────────┬─────────────────┘
                            ▼
                  ┌──────────────────┐
                  │   PriceCache     │  ← single point of truth
                  └─────────┬────────┘
                            │ readers
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
       SSE stream    portfolio /api      trade exec
```

Selection rule: `MASSIVE_API_KEY` set & non‑empty → real data; otherwise simulator. **The selection happens once, at startup.** No fallback / hybrid mode.

---

## 2. Core Data Model — `PriceUpdate`

`models.py` defines the only data structure that escapes the market layer. It is a frozen dataclass (immutable, hashable, slot‑optimised) so it can be safely shared across threads and serialised straight to JSON.

```python
from dataclasses import dataclass, field
import time

@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)   # Unix seconds

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        if   self.price > self.previous_price: return "up"
        elif self.price < self.previous_price: return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker":         self.ticker,
            "price":          self.price,
            "previous_price": self.previous_price,
            "timestamp":      self.timestamp,
            "change":         self.change,
            "change_percent": self.change_percent,
            "direction":      self.direction,
        }
```

Design notes:
- `change`, `change_percent`, `direction` are **properties, not stored**. Avoids the "the cached direction lies after a quick double‑update" class of bug.
- `timestamp` is Unix **seconds** (float). Massive returns ms — the adapter divides.
- Frozen + slots = ~3× cheaper than a regular dataclass when allocated in a tight tick loop.

---

## 3. Producer Contract — `MarketDataSource`

```python
from abc import ABC, abstractmethod

class MarketDataSource(ABC):
    """Pushes PriceUpdate rows into a shared PriceCache.

    The interface deliberately does NOT return prices to callers — readers
    consult the cache. This keeps the producer/consumer decoupled and lets
    us swap the producer at startup without touching anything downstream.
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...
    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...
    @abstractmethod
    def    get_tickers(self) -> list[str]: ...
```

Lifecycle invariants (apply to **both** implementations):

| Method | Invariant |
|--------|-----------|
| `start(tickers)` | Called exactly once. MUST seed the cache with at least one `PriceUpdate` per ticker before returning, so SSE has data on the first connection. |
| `stop()`        | Idempotent. After `stop()` no further writes to the cache. |
| `add_ticker()`  | Idempotent. Normalises ticker (uppercase, strip whitespace). New ticker appears in cache by the *next* tick at the latest. |
| `remove_ticker()` | Idempotent. Also calls `cache.remove(ticker)` so stale data doesn't leak into the SSE stream. |
| `get_tickers()` | Pure read; never blocks. |

---

## 4. Shared Store — `PriceCache`

Thread‑safe (one `threading.Lock`) so the synchronous Massive SDK call running in `asyncio.to_thread` can write while the SSE generator reads from the event loop.

```python
class PriceCache:
    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock    = Lock()
        self._version = 0          # bumped on every update; SSE reads this

    def update(self, ticker, price, timestamp=None) -> PriceUpdate: ...
    def get(self, ticker)           -> PriceUpdate | None: ...
    def get_price(self, ticker)     -> float | None: ...
    def get_all(self)               -> dict[str, PriceUpdate]: ...
    def remove(self, ticker)        -> None: ...

    @property
    def version(self) -> int: ...
```

Why a `version` counter? The SSE generator polls the cache every 500 ms and only emits when something has changed:

```python
last_version = -1
while not await request.is_disconnected():
    if cache.version != last_version:
        last_version = cache.version
        yield f"data: {json.dumps(...)}\n\n"
    await asyncio.sleep(0.5)
```

This keeps SSE bandwidth flat when no prices have moved (e.g. market closed, simulator paused) without the SSE code needing to diff dictionaries.

---

## 5. Factory Selection

`factory.py` is the *only* place where the environment variable is read. Code that needs a data source should always go through it.

```python
import os, logging
from .cache     import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator      import SimulatorDataSource

log = logging.getLogger(__name__)

def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        log.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    log.info("Market data source: GBM Simulator")
    return SimulatorDataSource(price_cache=price_cache)
```

Returns an **unstarted** source; the caller awaits `source.start(...)`.

---

## 6. App Lifecycle Wiring

A FastAPI lifespan hook owns the cache + source for the process:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.config import DEFAULT_WATCHLIST   # ["AAPL", "GOOGL", ...]

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache  = PriceCache()
    source = create_market_data_source(cache)
    await source.start(DEFAULT_WATCHLIST)

    app.state.price_cache = cache
    app.state.market      = source
    app.include_router(create_stream_router(cache))
    try:
        yield
    finally:
        await source.stop()

app = FastAPI(lifespan=lifespan)
```

Watchlist mutations elsewhere call `app.state.market.add_ticker(...)` / `.remove_ticker(...)`. Trade execution and portfolio valuation read from `app.state.price_cache.get(ticker)`.

---

## 7. SSE Endpoint

The streamer lives in `stream.py` and is wired in via `create_stream_router(price_cache)`.

```python
async def _generate_events(cache: PriceCache, request: Request, interval: float = 0.5):
    yield "retry: 1000\n\n"
    last_version = -1
    while True:
        if await request.is_disconnected(): break
        if cache.version != last_version:
            last_version = cache.version
            data = {t: u.to_dict() for t, u in cache.get_all().items()}
            yield f"data: {json.dumps(data)}\n\n"
        await asyncio.sleep(interval)
```

The endpoint emits a single JSON envelope keyed by ticker rather than one event per ticker. This was a deliberate trade — fewer events / less per‑ticker overhead, simpler frontend reducer (just `Object.assign(state, payload)`), at the cost of one slightly larger payload every 500 ms (~1 KB for 10 tickers).

---

## 8. Massive Implementation Sketch

(See `MASSIVE_API.md` for endpoint specifics; this is just the lifecycle adapter.)

```python
import asyncio, logging
from massive import RESTClient
from massive.rest.models import SnapshotMarketType
from .cache import PriceCache
from .interface import MarketDataSource

log = logging.getLogger(__name__)

class MassiveDataSource(MarketDataSource):
    def __init__(self, api_key: str, price_cache: PriceCache, poll_interval: float = 15.0):
        self._api_key, self._cache, self._interval = api_key, price_cache, poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(self, tickers: list[str]) -> None:
        self._client  = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)
        await self._poll_once()                                # seed cache
        self._task = asyncio.create_task(self._loop(), name="massive-poller")

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        if not self._tickers or not self._client: return
        try:
            snaps = await asyncio.to_thread(
                self._client.get_snapshot_all,
                market_type=SnapshotMarketType.STOCKS,
                tickers=self._tickers,
            )
            for s in snaps:
                self._cache.update(
                    ticker=s.ticker,
                    price=s.last_trade.price,
                    timestamp=s.last_trade.timestamp / 1000.0,  # ms → s
                )
        except Exception as e:
            log.error("Massive poll failed: %s", e)             # do not re‑raise

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
        self._task = None
        self._client = None

    async def add_ticker(self, t: str) -> None:
        t = t.upper().strip()
        if t not in self._tickers: self._tickers.append(t)

    async def remove_ticker(self, t: str) -> None:
        t = t.upper().strip()
        self._tickers = [x for x in self._tickers if x != t]
        self._cache.remove(t)

    def get_tickers(self) -> list[str]: return list(self._tickers)
```

Key trade‑offs:
- We **don't** expose `get_snapshot_ticker` for ad‑hoc lookups on the request path — that adds an unbounded request rate against the API. Anything price‑related reads from the cache.
- A failed poll is logged and swallowed. The cache simply keeps the previous price; clients see no event for that tick.

---

## 9. Simulator Implementation Sketch

Detail: see `MARKET_SIMULATOR.md`. The adapter just runs the simulator on a 500 ms loop and writes results.

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, update_interval: float = 0.5,
                 event_probability: float = 0.001):
        self._cache    = price_cache
        self._interval = update_interval
        self._evt_prob = event_probability
        self._sim:  GBMSimulator | None  = None
        self._task: asyncio.Task | None  = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._evt_prob)
        for t in tickers:                           # seed cache
            p = self._sim.get_price(t)
            if p is not None: self._cache.update(ticker=t, price=p)
        self._task = asyncio.create_task(self._run(), name="simulator-loop")

    async def _run(self) -> None:
        while True:
            try:
                if self._sim:
                    for ticker, price in self._sim.step().items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                log.exception("Simulator step failed")
            await asyncio.sleep(self._interval)

    # add_ticker / remove_ticker / stop / get_tickers as in MassiveDataSource,
    # but delegating to self._sim.add_ticker / .remove_ticker.
```

---

## 10. File Layout

```
backend/app/market/
├── __init__.py        # public re-exports
├── models.py          # PriceUpdate
├── interface.py       # MarketDataSource ABC
├── cache.py           # PriceCache
├── factory.py         # create_market_data_source()
├── massive_client.py  # MassiveDataSource
├── simulator.py       # SimulatorDataSource + GBMSimulator
├── seed_prices.py     # SEED_PRICES, TICKER_PARAMS, correlation tables
└── stream.py          # create_stream_router() — FastAPI SSE
```

Public import surface (kept tight on purpose):

```python
from app.market import (
    PriceUpdate, PriceCache, MarketDataSource,
    create_market_data_source, create_stream_router,
)
```

---

## 11. Testing Strategy

The interface design directly enables three categories of test, all of which the existing suite covers (73 tests, ~84 % coverage):

1. **Cache unit tests** — direction logic, version monotonicity, thread‑safe updates.
2. **Source unit tests, simulator** — deterministic seed + frozen RNG, verify `step()` math, verify add/remove rebuilds Cholesky correctly.
3. **Source unit tests, Massive** — mock the SDK at the `RESTClient` boundary; verify timestamp ms→s conversion, error swallowing, ticker case normalisation.
4. **Conformance test** — both `SimulatorDataSource` and `MassiveDataSource` are run against the same lifecycle script (`start → add → remove → stop`) and asserted to leave the cache in equivalent shape.

Conformance is the most valuable: it catches drift between the two implementations without us having to write parallel suites.

---

## 12. Future Extensions (out of MVP scope)

- **Per‑ticker history** for sparkline backfill: a small ring buffer in `PriceCache` of the last N updates per ticker.
- **`MultiSourceDataSource`** that fans out to several upstreams and prefers the freshest. Only worth doing once a second provider is on the table.
- **Persistence**: dump cache to SQLite on shutdown so reboots don't show "$0.00" for a few seconds. Cheap if needed.
- **WebSocket upgrade path**: drop in a `MassiveWebSocketDataSource` that implements the same ABC. The rest of the system would not change.
