# Market Data Backend — Detailed Design

Implementation-ready design for the FinAlly market data subsystem. Consolidates the architecture, contracts, code, and edge cases for the three pillars:

- **Unified API** — abstract interface, shared cache, factory, FastAPI lifecycle, SSE streaming
- **Simulator** — Geometric Brownian Motion (GBM) with correlated moves and shock events (default path)
- **Massive API** — REST polling adapter for real market data via Polygon.io / Massive

Everything described here lives under `backend/app/market/`. This is the source-of-truth design contract for that package.

---

## Table of Contents

1. [Goals & Architecture](#1-goals--architecture)
2. [File Layout](#2-file-layout)
3. [Data Model — `PriceUpdate`](#3-data-model--priceupdate)
4. [Shared Store — `PriceCache`](#4-shared-store--pricecache)
5. [Producer Contract — `MarketDataSource`](#5-producer-contract--marketdatasource)
6. [Factory Selection — `create_market_data_source`](#6-factory-selection--create_market_data_source)
7. [Simulator — `GBMSimulator` + `SimulatorDataSource`](#7-simulator--gbmsimulator--simulatordatasource)
8. [Massive API Client — `MassiveDataSource`](#8-massive-api-client--massivedatasource)
9. [SSE Streaming Endpoint — `create_stream_router`](#9-sse-streaming-endpoint--create_stream_router)
10. [FastAPI Lifecycle Wiring](#10-fastapi-lifecycle-wiring)
11. [Testing Strategy](#11-testing-strategy)
12. [Error Handling & Edge Cases](#12-error-handling--edge-cases)
13. [Configuration Summary](#13-configuration-summary)
14. [Future Extensions](#14-future-extensions)

---

## 1. Goals & Architecture

> **One interface, two implementations, one cache.**

The rest of FinAlly never knows whether prices come from real markets or a simulator. SSE streaming, portfolio valuation, and trade execution all read from the same `PriceCache`. Producers (real or fake) write into it on their own schedule.

```
                ┌─────────────────────────────┐
                │  create_market_data_source  │
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

**Selection rule:** `MASSIVE_API_KEY` set & non-empty → real data; otherwise simulator. Selection happens **once, at startup**. No fallback / hybrid mode.

### Why this shape

| Decision | Rationale |
|---|---|
| Strategy pattern over a giant `if MASSIVE_API_KEY` | Lets us add a third source (e.g. WebSocket) without touching consumers. |
| Cache as the only consumer-facing surface | Decouples poll cadence from read cadence. SSE doesn't care if the source ticks every 500 ms or every 15 s. |
| Frozen, slot-optimised `PriceUpdate` | Cheap to allocate per tick; safe to share across threads; serialises straight to JSON. |
| `version` counter on the cache | SSE generator detects "did anything change?" without diffing dicts. Keeps bandwidth flat when prices are stable. |
| One asyncio task per source | No locks beyond the cache; cancel cleanly via `Task.cancel()`. |

---

## 2. File Layout

```
backend/app/market/
├── __init__.py        # Public re-exports only
├── models.py          # PriceUpdate (frozen dataclass)
├── cache.py           # PriceCache (thread-safe store + version counter)
├── interface.py       # MarketDataSource ABC
├── seed_prices.py     # SEED_PRICES, TICKER_PARAMS, correlation tables (pure data)
├── simulator.py       # GBMSimulator + SimulatorDataSource
├── massive_client.py  # MassiveDataSource (REST poller)
├── factory.py         # create_market_data_source()
└── stream.py          # create_stream_router() — FastAPI SSE
```

**Public import surface** (kept tight — these five names are the entire contract):

```python
from app.market import (
    PriceUpdate,
    PriceCache,
    MarketDataSource,
    create_market_data_source,
    create_stream_router,
)
```

`__init__.py`:

```python
"""Market data subsystem for FinAlly."""
from .cache     import PriceCache
from .factory   import create_market_data_source
from .interface import MarketDataSource
from .models    import PriceUpdate
from .stream    import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "create_market_data_source",
    "create_stream_router",
]
```

---

## 3. Data Model — `PriceUpdate`

**File:** `app/market/models.py`

The only data structure that escapes the market layer. Frozen + slots = ~3× cheaper than a regular dataclass when allocated in a tight tick loop.

```python
from __future__ import annotations
import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

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
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
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

### Design notes

- **`change`, `change_percent`, `direction` are properties, not stored fields.** Avoids the "the cached direction lies after a quick double-update" class of bug.
- **`timestamp` is Unix seconds (float).** Massive returns ms — the adapter divides by 1000 before storing.
- **Direction string is `"flat"`, not `"unchanged"`** — frontend reducer expects three values: `"up"`, `"down"`, `"flat"`.
- **Frozen** so the same instance can be shared across threads without copying.

---

## 4. Shared Store — `PriceCache`

**File:** `app/market/cache.py`

Thread-safe (one `threading.Lock`) so the synchronous Massive SDK call running in `asyncio.to_thread` can write while the SSE generator reads from the event loop.

```python
from __future__ import annotations
import time
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    """Thread-safe in-memory cache of the latest price for each ticker.

    Writers: SimulatorDataSource OR MassiveDataSource (one at a time).
    Readers: SSE streaming endpoint, portfolio valuation, trade execution.
    """

    def __init__(self) -> None:
        self._prices:  dict[str, PriceUpdate] = {}
        self._lock     = Lock()
        self._version  = 0   # bumped on every update

    def update(self, ticker: str, price: float,
               timestamp: float | None = None) -> PriceUpdate:
        with self._lock:
            ts             = timestamp or time.time()
            prev           = self._prices.get(ticker)
            previous_price = prev.price if prev else price

            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        u = self.get(ticker)
        return u.price if u else None

    def get_all(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._prices)            # shallow copy — values are frozen

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._prices.pop(ticker, None)

    @property
    def version(self) -> int:
        return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
```

### Why a `version` counter?

The SSE generator polls the cache every 500 ms and only emits when something has changed:

```python
last_version = -1
while True:
    if cache.version != last_version:
        last_version = cache.version
        yield f"data: {json.dumps(...)}\n\n"
    await asyncio.sleep(0.5)
```

This keeps bandwidth flat when no prices have moved (e.g. market closed) without the SSE code needing to diff dictionaries.

### Invariants

- **First update for a ticker** sets `previous_price == price`, so `direction == "flat"` on the first event.
- **Prices are stored rounded to 2 decimals** — JSON-friendly, matches what users see.
- **Reads never block writes for long** — the lock is held only for dict access, no I/O.

---

## 5. Producer Contract — `MarketDataSource`

**File:** `app/market/interface.py`

```python
from __future__ import annotations
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

### Lifecycle invariants (apply to **both** implementations)

| Method | Invariant |
|--------|-----------|
| `start(tickers)` | Called exactly once. **MUST seed the cache with at least one `PriceUpdate` per ticker before returning**, so SSE has data on the first connection (no "0.00 → real price" flicker). |
| `stop()` | Idempotent. After `stop()` no further writes to the cache. |
| `add_ticker(t)` | Idempotent. Normalises ticker (uppercase, strip whitespace). New ticker appears in cache by the *next* tick at the latest. |
| `remove_ticker(t)` | Idempotent. Also calls `cache.remove(ticker)` so stale data doesn't leak into the SSE stream. |
| `get_tickers()` | Pure read; never blocks. |

---

## 6. Factory Selection — `create_market_data_source`

**File:** `app/market/factory.py`

The **only** place where `MASSIVE_API_KEY` is read. Code that needs a data source always goes through this factory.

```python
from __future__ import annotations
import logging
import os

from .cache          import PriceCache
from .interface      import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator      import SimulatorDataSource

log = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Create the appropriate market data source from environment variables.

    - MASSIVE_API_KEY set and non-empty  → MassiveDataSource (real data)
    - Otherwise                          → SimulatorDataSource (GBM)

    Returns an *unstarted* source. Caller must `await source.start(tickers)`.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        log.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)

    log.info("Market data source: GBM Simulator")
    return SimulatorDataSource(price_cache=price_cache)
```

---

## 7. Simulator — `GBMSimulator` + `SimulatorDataSource`

**File:** `app/market/simulator.py` (with seed data in `seed_prices.py`)

The default path. Most users — and all CI runs — will never see real data.

### 7.1 Approach: Geometric Brownian Motion

GBM is the classical lognormal price process. Picked for three reasons:

| Property | Why it matters |
|----------|----------------|
| Lognormal: `S(t) > 0` always | Prices never go negative; no bounds checking. |
| Stationary log-returns | Tunable per ticker via two scalars (`μ`, `σ`) — easy to make AAPL boring and TSLA wild. |
| Closed-form one-step update | One `exp()` and one normal draw per ticker per tick → trivial cost for ≤ 50 tickers at 2 Hz. |

### 7.2 The GBM step

For each ticker at each tick:

```
S(t + dt) = S(t) · exp( (μ − σ²/2) · dt  +  σ · √dt · Z )
```

| Symbol | Meaning | Typical |
|--------|---------|---------|
| `S(t)` | current price | seeded per-ticker (§7.4) |
| `μ`    | annualised drift (expected return) | 0.03 – 0.08 |
| `σ`    | annualised volatility | 0.17 – 0.50 |
| `dt`   | time step as fraction of a trading year | ~8.48 × 10⁻⁸ |
| `Z`    | standard normal draw, *correlated* across tickers | N(0, 1) |

**Why this `dt`?** A US trading year is `252 days × 6.5 hours × 3600 s ≈ 5,896,800 s`. A 500 ms tick → `dt = 0.5 / 5_896_800 ≈ 8.48e-8`. With `σ = 0.22` (AAPL), `σ·√dt ≈ 6.4e-5` — about **0.0064 % expected move per tick**. Across `46_800` ticks/day this reproduces the requested 1.39 % daily standard deviation. We don't hand-tune the per-tick move; pick the annualised σ, the math gives the right tick size for free.

### 7.3 Correlated moves via Cholesky

Real markets co-move. If AAPL drops 1 %, GOOGL probably dropped ~0.6 % at the same time. Independent draws would look fake.

```
L = cholesky(C)        # lower-triangular, L · Lᵀ = C
Z_correlated = L @ Z_independent
```

`L` is rebuilt **only when the watchlist changes** (rare). The hot path is one `n × n` matrix-vector product, dominated by numpy overhead for small `n`.

### 7.4 Seed prices and per-ticker parameters

**File:** `app/market/seed_prices.py` — pure data, no imports beyond `dict`/`set`.

```python
SEED_PRICES: dict[str, float] = {
    "AAPL":  190.00,  "GOOGL": 175.00,  "MSFT": 420.00,  "AMZN": 185.00,
    "TSLA":  250.00,  "NVDA":  800.00,  "META": 500.00,  "JPM":  195.00,
    "V":     280.00,  "NFLX":  600.00,
}

TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},   # high vol, modest drift
    "NVDA":  {"sigma": 0.40, "mu": 0.08},   # high vol AND strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},   # bank, low vol
    "V":     {"sigma": 0.17, "mu": 0.04},   # payments, low vol
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}
DEFAULT_PARAMS = {"sigma": 0.25, "mu": 0.05}    # fallback for unknown tickers

CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech":    {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

INTRA_TECH_CORR    = 0.6
INTRA_FINANCE_CORR = 0.5
CROSS_GROUP_CORR   = 0.3
TSLA_CORR          = 0.3      # TSLA is in tech but does its own thing
```

Tickers added at runtime that aren't in the table fall back to a price drawn from `random.uniform(50, 300)` and `DEFAULT_PARAMS`. Wide enough to avoid screen-filling six-digit prices, narrow enough to look plausible.

The matrix built from this lookup is positive semi-definite for any subset of the default ten tickers (verified in tests), so `np.linalg.cholesky` always succeeds.

### 7.5 Random shocks

Smooth GBM alone is too smooth — a real terminal occasionally lights up green or red on a headline.

```python
EVENT_PROB = 0.001                          # ~0.1% per ticker per tick

if random.random() < EVENT_PROB:
    magnitude = random.uniform(0.02, 0.05)  # 2–5%
    sign      = random.choice([-1, 1])
    price    *= 1 + magnitude * sign
```

With 10 tickers ticking twice a second, expected time between shocks across the watchlist is `1 / (10 · 2 · 0.001) = 50 s` — frequent enough to notice, rare enough to feel like news. Shocks compound on top of the diffusion (applied *after* the GBM step).

### 7.6 The `GBMSimulator` class

```python
import math, random
import numpy as np

from .seed_prices import (
    SEED_PRICES, TICKER_PARAMS, DEFAULT_PARAMS,
    CORRELATION_GROUPS,
    INTRA_TECH_CORR, INTRA_FINANCE_CORR, CROSS_GROUP_CORR, TSLA_CORR,
)


class GBMSimulator:
    """Correlated GBM price paths for an arbitrary set of tickers."""

    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600          # 5,896,800
    DEFAULT_DT               = 0.5 / TRADING_SECONDS_PER_YEAR

    def __init__(self, tickers: list[str],
                 dt: float = DEFAULT_DT,
                 event_probability: float = 0.001) -> None:
        self._dt        = dt
        self._evt_prob  = event_probability
        self._tickers:  list[str]                     = []
        self._prices:   dict[str, float]              = {}
        self._params:   dict[str, dict[str, float]]   = {}
        self._cholesky: np.ndarray | None             = None

        for t in tickers:
            self._add_ticker_internal(t)
        self._rebuild_cholesky()

    # ── hot path ────────────────────────────────────────────────────
    def step(self) -> dict[str, float]:
        n = len(self._tickers)
        if n == 0:
            return {}

        z_indep = np.random.standard_normal(n)
        z_corr  = self._cholesky @ z_indep if self._cholesky is not None else z_indep

        out: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            mu, sigma = self._params[ticker]["mu"], self._params[ticker]["sigma"]

            drift     = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_corr[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            if random.random() < self._evt_prob:
                self._prices[ticker] *= (
                    1 + random.uniform(0.02, 0.05) * random.choice([-1, 1])
                )

            out[ticker] = round(self._prices[ticker], 2)

        return out

    # ── lifecycle ───────────────────────────────────────────────────
    def add_ticker(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # ── internals ───────────────────────────────────────────────────
    def _add_ticker_internal(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50, 300))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = corr[j, i] = rho
        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        tech    = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

### 7.7 The async adapter — `SimulatorDataSource`

The simulator itself is synchronous. The adapter just runs it on a 500 ms loop and writes results to the cache.

```python
import asyncio, logging
from .interface import MarketDataSource
from .cache     import PriceCache

log = logging.getLogger(__name__)


class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache,
                 update_interval: float = 0.5,
                 event_probability: float = 0.001) -> None:
        self._cache    = price_cache
        self._interval = update_interval
        self._evt_prob = event_probability
        self._sim:  GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        normalized = [t.upper().strip() for t in tickers]
        self._sim  = GBMSimulator(tickers=normalized,
                                  event_probability=self._evt_prob)
        # Seed cache so the first SSE message has data
        for t in normalized:
            p = self._sim.get_price(t)
            if p is not None:
                self._cache.update(ticker=t, price=p)

        self._task = asyncio.create_task(self._loop(), name="simulator-loop")

    async def _loop(self) -> None:
        while True:
            try:
                if self._sim:
                    for ticker, price in self._sim.step().items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                log.exception("Simulator step failed")    # never let the loop die
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def add_ticker(self, t: str) -> None:
        if not self._sim:
            return
        t = t.upper().strip()
        self._sim.add_ticker(t)
        p = self._sim.get_price(t)
        if p is not None:
            self._cache.update(ticker=t, price=p)

    async def remove_ticker(self, t: str) -> None:
        t = t.upper().strip()
        if self._sim:
            self._sim.remove_ticker(t)
        self._cache.remove(t)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []
```

Two non-obvious details:

- `start()` writes seed prices into the cache **before** kicking off the loop, so the very first SSE message after page load has data — no flicker.
- The loop **swallows any exception** from `step()` and logs it. We want to see the error, not bring the dashboard down.

---

## 8. Massive API Client — `MassiveDataSource`

**File:** `app/market/massive_client.py`

### 8.1 Why a poller, not a WebSocket?

FinAlly only needs a "current price" snapshot for ≤ ~50 tickers, refreshed on a fixed cadence. A REST poller — one HTTP call returns prices for *all* tickers — is simpler, works on every paid tier and the free tier, has no reconnect/backpressure logic to write, and matches the simulator's tick model 1:1.

### 8.2 Setup

| Item | Value |
|------|-------|
| Base URL | `https://api.massive.com` (legacy `https://api.polygon.io` still routes) |
| Python package | `massive` (formerly `polygon-api-client`) |
| Auth | `Authorization: Bearer <API_KEY>` (added by the SDK) |
| Env var | `MASSIVE_API_KEY` |

Install:
```bash
cd backend
uv add massive
```

### 8.3 Rate limits and poll cadence

| Tier | Stated limit | Default poll interval |
|------|--------------|-----------------------|
| Free ("Basic") | 5 req/min | every **15 s** |
| Starter / Developer | unmetered (fair use) | every **2–5 s** |
| Advanced / Business | unmetered | every **1–2 s** |

The snapshot endpoint returns **all watched tickers in a single HTTP call**, so a 10-ticker watchlist on the free tier costs 1 request per poll. A 429 is treated as a transient error: log and skip.

### 8.4 The endpoint we use

```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,MSFT
```

Per-ticker response (relevant subset):

```jsonc
{
  "ticker": "AAPL",
  "lastTrade": { "p": 194.25, "s": 100, "t": 1735905312000, "i": "abcd" },
  "todaysChangePerc": 0.7521,
  "updated": 1735905312123
}
```

Fields FinAlly consumes:
- `last_trade.price` → live price written into `PriceCache`
- `last_trade.timestamp` → Unix **milliseconds**; divide by 1000 for our `time.time()`-style seconds
- `todays_change_perc` → optional, for the daily-change column
- `updated` → useful in logs for debugging stale data

### 8.5 The adapter

```python
import asyncio, logging
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

from .interface import MarketDataSource
from .cache     import PriceCache

log = logging.getLogger(__name__)


class MassiveDataSource(MarketDataSource):
    def __init__(self, api_key: str, price_cache: PriceCache,
                 poll_interval: float = 15.0) -> None:
        self._api_key  = api_key
        self._cache    = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task:   asyncio.Task | None = None
        self._client: RESTClient  | None  = None

    async def start(self, tickers: list[str]) -> None:
        self._client  = RESTClient(api_key=self._api_key)
        self._tickers = [t.upper().strip() for t in tickers]
        await self._poll_once()                                       # seed cache
        self._task = asyncio.create_task(self._loop(), name="massive-poller")

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        if not self._tickers or not self._client:
            return
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
                    timestamp=s.last_trade.timestamp / 1000.0,        # ms → s
                )
        except Exception as e:
            log.error("Massive poll failed: %s", e)                   # do NOT re-raise

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task   = None
        self._client = None

    async def add_ticker(self, t: str) -> None:
        t = t.upper().strip()
        if t not in self._tickers:
            self._tickers.append(t)

    async def remove_ticker(self, t: str) -> None:
        t = t.upper().strip()
        self._tickers = [x for x in self._tickers if x != t]
        self._cache.remove(t)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)
```

### 8.6 Key trade-offs

- **No ad-hoc `get_snapshot_ticker()` lookups on the request path.** That adds an unbounded request rate against the API. Anything price-related reads from the cache.
- **A failed poll is logged and swallowed.** The cache keeps the previous price; clients see no event for that tick. The next interval will retry.
- **The SDK is synchronous**, so every call is wrapped in `asyncio.to_thread` to keep the event loop unblocked.

### 8.7 Error matrix

| HTTP / Exception | Cause | Behaviour |
|------------------|-------|-----------|
| 401 | Bad / missing API key | Log error; poller keeps trying — operator must fix env var |
| 403 | Endpoint not on plan | Log and downgrade silently — snapshot is on every plan |
| 429 | Rate limit | Log warning, continue — next interval will retry |
| 5xx | Transient server error | SDK retries 3× with backoff; log final failure |
| `ConnectionError` / timeout | Network hiccup | Same — log, continue |

The poller **never raises out of the loop**.

### 8.8 Common pitfalls

- **Timestamps are Unix milliseconds.** Divide by 1000 before storing.
- **The SDK is synchronous.** Always wrap in `asyncio.to_thread`.
- **Tickers are case-sensitive.** Always uppercase before sending; the adapter normalises.
- **Snapshot resets at 03:30 EST.** Right after that, expect a few empty / zero-volume responses until the market opens.
- **Free-tier gotcha:** 5 req/min applies across **all endpoints**. Don't mix snapshot polling with per-click lookups.

---

## 9. SSE Streaming Endpoint — `create_stream_router`

**File:** `app/market/stream.py`

The streamer reads from the cache and pushes a single JSON envelope keyed by ticker on every change.

```python
from __future__ import annotations
import asyncio, json, logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stream", tags=["streaming"])


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Create the SSE streaming router with a reference to the price cache."""

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control":     "no-cache",
                "Connection":        "keep-alive",
                "X-Accel-Buffering": "no",     # Disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    yield "retry: 1000\n\n"

    last_version = -1
    client_ip = request.client.host if request.client else "unknown"
    log.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                log.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()
                if prices:
                    payload = {t: u.to_dict() for t, u in prices.items()}
                    yield f"data: {json.dumps(payload)}\n\n"

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("SSE stream cancelled for: %s", client_ip)
```

### Wire format

A single `data:` line per event, JSON object keyed by ticker:

```
retry: 1000

data: {"AAPL":{"ticker":"AAPL","price":194.25,"previous_price":193.80,"timestamp":1735905312.0,"change":0.45,"change_percent":0.232,"direction":"up"}, "GOOGL":{...}}

data: {"AAPL":{"ticker":"AAPL","price":194.30, ... "direction":"up"}, ...}
```

### Why a single envelope (not one event per ticker)

- Frontend reducer is one line: `Object.assign(state, payload)`.
- Fewer events / less per-ticker overhead.
- Cost: one slightly larger payload every 500 ms (~1 KB for 10 tickers) — negligible.

### Frontend usage

```ts
const es = new EventSource("/api/stream/prices");
es.onmessage = (e) => {
  const payload = JSON.parse(e.data);
  // payload = { AAPL: {ticker, price, previous_price, ..., direction}, ... }
  setPrices((prev) => ({ ...prev, ...payload }));
};
```

`EventSource` automatically reconnects on disconnect — no client-side retry logic needed. The `retry: 1000` directive sets the reconnection delay to 1 s.

---

## 10. FastAPI Lifecycle Wiring

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

### Watchlist coordination

- Watchlist mutations (e.g. `POST /api/watchlist`) call:
  ```python
  await app.state.market.add_ticker(ticker)
  ```
- And on remove:
  ```python
  await app.state.market.remove_ticker(ticker)
  ```
- Trade execution and portfolio valuation read from:
  ```python
  update = app.state.price_cache.get(ticker)
  if update is None:
      raise HTTPException(400, "no price available for ticker")
  ```

The cache is the single contract. No other module reaches into the source directly.

---

## 11. Testing Strategy

The interface design directly enables four categories of test.

### 11.1 Cache unit tests (`tests/market/test_cache.py`)

- `update()` populates the cache and returns the right `PriceUpdate`.
- First update for a ticker has `previous_price == price` and `direction == "flat"`.
- Subsequent updates set `previous_price` to the prior `price`.
- `version` is monotonically increasing; bumped on every update.
- `remove(ticker)` deletes the entry; `get(ticker)` returns `None` after.
- Concurrent writes from multiple threads don't corrupt state (use `concurrent.futures`).

### 11.2 Simulator unit tests (`tests/market/test_simulator.py`)

Properties the simulator must satisfy:

1. **Positivity:** `price > 0` for every ticker after every `step()`.
2. **Smoothness without shocks:** with `event_probability=0`, `|ln(S_{t+1} / S_t)| ≤ 5σ√dt` with overwhelming probability.
3. **Correct long-run vol:** `Var(ln(S))` averaged over many ticks reproduces `σ²·dt`.
4. **Correlation:** with `corr(AAPL, GOOGL) = 0.6`, the empirical correlation of returns over 100 k ticks is within ±0.05.
5. **Add/remove invariance:** removing a ticker and re-adding it preserves the *other* tickers' prices exactly.
6. **PSD correlation matrix:** Cholesky never raises for any subset of the default ten tickers.
7. **Shock rate:** empirical event rate is within 20 % of `event_probability` over 50 k ticks per ticker.

Tests seed both `random` and `np.random` before construction for determinism.

### 11.3 Massive unit tests (`tests/market/test_massive.py`)

Mock the SDK at the `RESTClient` boundary:

```python
@patch("app.market.massive_client.RESTClient")
async def test_poll_once_writes_cache(MockClient):
    mock = MockClient.return_value
    mock.get_snapshot_all.return_value = [
        SimpleNamespace(
            ticker="AAPL",
            last_trade=SimpleNamespace(price=194.25, timestamp=1_735_905_312_000),
        ),
    ]
    cache  = PriceCache()
    source = MassiveDataSource(api_key="test", price_cache=cache)
    await source.start(["AAPL"])
    assert cache.get_price("AAPL") == 194.25
    assert cache.get("AAPL").timestamp == 1_735_905_312.0   # ms → s
```

Verify: ms→s conversion, error swallowing (a thrown SDK exception doesn't kill the task), ticker case normalisation.

### 11.4 Conformance test (most valuable)

Both `SimulatorDataSource` and `MassiveDataSource` (with mocked SDK) are run against the **same** lifecycle script:

```python
@pytest.mark.parametrize("source_factory", [
    lambda c: SimulatorDataSource(price_cache=c),
    lambda c: MassiveDataSource(api_key="test", price_cache=c),     # mocked
])
async def test_lifecycle_conformance(source_factory):
    cache  = PriceCache()
    source = source_factory(cache)

    await source.start(["AAPL", "GOOGL"])
    assert set(source.get_tickers()) == {"AAPL", "GOOGL"}
    assert "AAPL" in cache and "GOOGL" in cache         # seeded

    await source.add_ticker("MSFT")
    assert "MSFT" in source.get_tickers()

    await source.remove_ticker("GOOGL")
    assert "GOOGL" not in source.get_tickers()
    assert "GOOGL" not in cache                         # cache cleaned

    await source.stop()
    await source.stop()                                 # idempotent
```

This catches drift between the two implementations without us writing parallel suites.

### Coverage target

- `models.py`, `cache.py`, `factory.py`: 100 %.
- `simulator.py`: ≥ 95 %.
- `massive_client.py`: ≥ 50 % (SDK methods are mocked).
- Overall: ≥ 80 %.

---

## 12. Error Handling & Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Source throws inside `_loop()` | Caught, logged via `log.exception`, loop continues at next interval. |
| Massive returns empty snapshot list | Cache untouched; SSE emits no event for that tick. |
| First connection to SSE before any tick | `_generate_events` yields `retry: 1000` immediately; first `data:` event arrives within `interval` once seeding completes (which `start()` guarantees). |
| Client disconnects mid-stream | `request.is_disconnected()` returns `True`; loop breaks, generator returns. |
| `add_ticker("aapl  ")` | Normalised to `"AAPL"`. Idempotent if already present. |
| `remove_ticker("UNKNOWN")` | No-op on source side; `cache.remove("UNKNOWN")` is also a no-op. |
| Trade execution before a ticker has a price | `cache.get(ticker)` returns `None`. Trade endpoint returns 400 (`"no price available"`). |
| Watchlist changed during a poll | Massive: next poll uses updated `_tickers`. Simulator: Cholesky already rebuilt by `add_ticker()`. |
| Process killed without `stop()` | OS reclaims the asyncio task; SQLite is fine; cache is in-memory so it's gone. No persistent corruption. |
| Two `start()` calls on the same source | Undefined behaviour. Lifespan hook calls it exactly once. |

---

## 13. Configuration Summary

### Environment variables

| Var | Default | Effect |
|-----|---------|--------|
| `MASSIVE_API_KEY` | unset | If set & non-empty: use Massive. Else: use simulator. |

### Tunable constants (no env vars; change in code)

| Constant | File | Default | Notes |
|----------|------|---------|-------|
| Simulator update interval | `simulator.py` | `0.5 s` | Matches SSE cadence. |
| Massive poll interval | `massive_client.py` | `15.0 s` | Free-tier safe. Lower for paid tiers. |
| `event_probability` | `simulator.py` / `seed_prices.py` | `0.001` | ~0.1 % chance per ticker per tick. |
| `SEED_PRICES`, `TICKER_PARAMS`, correlations | `seed_prices.py` | see §7.4 | Pure data; trivially editable. |
| SSE poll interval | `stream.py` | `0.5 s` | How often the generator checks `cache.version`. |

### Public import surface

```python
from app.market import (
    PriceUpdate,                # data type
    PriceCache,                 # shared store
    MarketDataSource,           # ABC for type hints
    create_market_data_source,  # factory (reads env)
    create_stream_router,       # FastAPI router factory
)
```

That's the entire surface area. Anything else is internal.

---

## 14. Future Extensions (out of MVP scope)

- **Per-ticker history** for sparkline backfill: ring buffer in `PriceCache` of the last N updates per ticker. SSE could send the buffer once on connect.
- **`MultiSourceDataSource`** that fans out to several upstreams and prefers the freshest. Worth doing once a second provider is on the table.
- **Persistence**: dump cache to SQLite on shutdown so reboots don't show "$0.00" for a few seconds. Cheap if needed.
- **WebSocket upgrade path**: a `MassiveWebSocketDataSource` that implements the same ABC. Nothing else in the system would change.
- **Per-source health metrics** exposed at `/api/health/market` (last successful poll timestamp, number of tickers, error counter).
