# Massive API Reference (formerly Polygon.io)

Reference for the Massive REST API as used in FinAlly. On **2025‑10‑30** Polygon.io completed its rebrand to **Massive.com**. The product, accounts and API keys are unchanged; the legacy `api.polygon.io` host and the legacy `polygon-api-client` package continue to work in parallel during the transition, but new code should use the `massive` package and `api.massive.com` host.

> **Why a poller, not a WebSocket?** FinAlly only needs a "current price" snapshot for ≤ ~50 tickers, refreshed on a fixed cadence. A REST poller (one HTTP call returns prices for *all* tickers) is simpler than a WebSocket, works on every paid tier and the free tier, has no reconnect/backpressure logic to write, and matches the simulator's "tick" model 1:1.

---

## 1. Setup

| Item | Value |
|------|-------|
| Base URL | `https://api.massive.com` (legacy `https://api.polygon.io` still routes) |
| Python package | `massive` (formerly `polygon-api-client`) |
| Min Python | 3.9+ (FinAlly targets 3.12) |
| Auth header | `Authorization: Bearer <API_KEY>` (added by the SDK) |
| Env var convention | `MASSIVE_API_KEY` |

```bash
# Install via uv (FinAlly project)
cd backend
uv add massive

# Or with pip
pip install -U massive
```

The SDK reads `MASSIVE_API_KEY` from the environment automatically when constructed without arguments, so production code should pass the key explicitly to make the dependency obvious:

```python
import os
from massive import RESTClient

client = RESTClient(api_key=os.environ["MASSIVE_API_KEY"])
```

---

## 2. Rate Limits

| Tier | Stated limit | FinAlly poll cadence |
|------|--------------|----------------------|
| Free ("Basic") | 5 requests / minute | every **15 s** |
| Starter / Developer | unmetered (fair use) | every **2–5 s** |
| Advanced / Business | unmetered | every **1–2 s** |

The snapshot endpoint we use returns **all watched tickers in a single HTTP call**, so a 10‑ticker watchlist on the free tier costs 1 request per poll, which fits comfortably under the 5 req/min ceiling at a 15 s interval.

A 429 ("rate limited") is treated as a transient error: log and skip; the next tick will retry. Do **not** add aggressive client‑side throttling — `poll_interval` already governs spacing.

---

## 3. Endpoints Used by FinAlly

### 3.1 Snapshot — Many Tickers (primary endpoint)

The single endpoint that FinAlly relies on for live data. One HTTP request, N tickers, current trade/quote/day data per ticker.

**REST:**
```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,MSFT
```

**Python client:**
```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient(api_key=API_KEY)

snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
)

for snap in snapshots:
    print(f"{snap.ticker}: ${snap.last_trade.price}  "
          f"({snap.todays_change_perc:+.2f}%)")
```

**Per‑ticker response (relevant subset):**
```jsonc
{
  "ticker": "AAPL",
  "day": {
    "o": 192.10, "h": 194.80, "l": 191.55, "c": 194.25,
    "v": 38_412_500, "vw": 193.12
  },
  "min": { "o": 194.20, "h": 194.30, "l": 194.18, "c": 194.25, "v": 31_200, "t": 1735905300000 },
  "prevDay":   { "o": 191.00, "h": 193.40, "l": 190.50, "c": 192.80, "v": 41_223_900 },
  "lastTrade": { "p": 194.25, "s": 100, "x": 11, "t": 1735905312000, "i": "abcd" },
  "lastQuote": { "p": 194.24, "P": 194.26, "s": 500, "S": 1000, "t": 1735905311999 },
  "todaysChange":     1.45,
  "todaysChangePerc": 0.7521,
  "updated":          1735905312123
}
```

The Python SDK exposes these as snake_case attributes on typed objects, so `snap.last_trade.price`, `snap.day.close`, `snap.todays_change_perc`, `snap.updated`, etc.

**Fields FinAlly actually consumes:**
- `last_trade.price` → the live price written into `PriceCache`
- `last_trade.timestamp` → Unix **milliseconds**; divide by 1000 for `time.time()`‑style seconds
- `todays_change_perc` → optional, used by the frontend for the daily‑change column
- `updated` → useful in logs for debugging stale data

> **Behavior note:** snapshot data is cleared daily at 03:30 EST and repopulates as the market wakes up. Outside US market hours the snapshot still returns the most recent trade — the price will simply not change between polls. This is the desired behaviour: FinAlly's UI continues to show the last traded price.

### 3.2 Snapshot — Single Ticker

Same data shape as 3.1 but for one ticker. Useful when the user clicks into a ticker for a detail view and we want a fresh quote without waiting for the next poll cycle.

```python
snap = client.get_snapshot_ticker(
    market_type=SnapshotMarketType.STOCKS,
    ticker="AAPL",
)

print(f"Bid/Ask: ${snap.last_quote.bid_price} / ${snap.last_quote.ask_price}")
print(f"Day range: ${snap.day.low} - ${snap.day.high}")
```

### 3.3 Previous Day OHLC

Returns yesterday's bar for one ticker. Used for end‑of‑day baselines, sparkline seeding, or as a fallback for `previous_close` outside market hours.

**REST:** `GET /v2/aggs/ticker/{ticker}/prev?adjusted=true`

```python
prev = client.get_previous_close_agg(ticker="AAPL", adjusted=True)
for bar in prev:
    print(f"O={bar.open} H={bar.high} L={bar.low} C={bar.close}  "
          f"V={bar.volume}  t={bar.timestamp}")
```

**Response shape (per bar):**
```jsonc
{
  "o": 191.00, "h": 193.40, "l": 190.50, "c": 192.80,
  "v": 41_223_900, "vw": 192.10,
  "t": 1735819200000,           // Unix ms
  "n": 412_000                  // transaction count
}
```

### 3.4 Historical Aggregates (Bars)

Not used in the MVP, but listed here for the future "click ticker → see 30‑day chart" feature.

**REST:** `GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`

```python
bars = []
for bar in client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="day",       # second | minute | hour | day | week | month | quarter | year
    from_="2026-01-01",
    to="2026-04-25",
    limit=50_000,
):
    bars.append(bar)
```

The SDK paginates automatically. Use `pagination=False` if you want the first page only.

### 3.5 Last Trade / Last Quote (single‑shot)

Lightweight if you really only need the last print or NBBO and not the full snapshot:

```python
trade = client.get_last_trade(ticker="AAPL")    # .price, .size, .timestamp
quote = client.get_last_quote(ticker="AAPL")    # .bid, .ask, .bid_size, .ask_size
```

Snapshot is preferred over these because it returns multiple tickers per request.

---

## 4. How FinAlly Polls

The poller is a single asyncio task wrapping a synchronous SDK call inside `asyncio.to_thread`, so the event loop is never blocked.

```python
import asyncio
import logging
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

log = logging.getLogger(__name__)

class MassivePoller:
    def __init__(self, api_key: str, cache, interval: float = 15.0) -> None:
        self._client   = RESTClient(api_key=api_key)
        self._cache    = cache
        self._interval = interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)
        await self._poll_once()                       # warm cache before first SSE tick
        self._task = asyncio.create_task(self._loop(), name="massive-poller")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        if not self._tickers:
            return
        try:
            snapshots = await asyncio.to_thread(
                self._client.get_snapshot_all,
                market_type=SnapshotMarketType.STOCKS,
                tickers=self._tickers,
            )
            for snap in snapshots:
                self._cache.update(
                    ticker=snap.ticker,
                    price=snap.last_trade.price,
                    timestamp=snap.last_trade.timestamp / 1000.0,
                )
        except Exception as e:
            log.error("Massive poll failed: %s", e)   # don't re‑raise; next tick will retry
```

This is the exact contract implemented by `app/market/massive_client.py::MassiveDataSource`.

---

## 5. Error Handling

| HTTP status | Cause | Behaviour |
|-------------|-------|-----------|
| 401 | Bad / missing API key | Log error; poller keeps trying — operator must fix env var |
| 403 | Endpoint not on plan (e.g. realtime quotes on Basic) | Log and downgrade silently — snapshot is on every plan |
| 429 | Rate limit | Log warning, continue — next interval will retry |
| 5xx | Transient server error | SDK already retries 3× with backoff; we just log the final failure |
| `ConnectionError` / timeout | Network hiccup | Same — log, continue |

The poller **never raises out of the loop**. A failed tick simply means the cache keeps the previous price; the SSE stream will emit no event for that ticker until the next successful poll. This is fine — clients see the last good price and a "stale" age can be derived from `PriceUpdate.timestamp` if needed.

---

## 6. Common Pitfalls

- **Timestamps are Unix milliseconds.** Divide by 1000 before storing in `PriceUpdate.timestamp` (which is Unix seconds).
- **The SDK is synchronous.** Always wrap calls in `asyncio.to_thread` from FastAPI handlers or background tasks.
- **`tickers` is *case‑sensitive*.** Always uppercase before sending; FinAlly normalises in `MassiveDataSource.add_ticker()`.
- **Snapshot resets at 03:30 EST.** Right after that, expect a few empty / zero‑volume responses until the market opens.
- **Free tier gotcha:** five requests *per minute* applies across **all endpoints**. Don't mix snapshot polling with per‑click `get_snapshot_ticker()` lookups on Basic — you'll burn the budget in a few clicks.

---

## 7. References

- Rebrand announcement — <https://massive.com/blog/polygon-is-now-massive>
- API home — <https://massive.com/docs>
- Full‑market snapshot — <https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot>
- Previous‑day bar — <https://massive.com/docs/rest/stocks/aggregates/previous-day-bar>
- Python client (GitHub) — <https://github.com/massive-com/client-python>
