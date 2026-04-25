# Market Simulator

Approach and code structure for simulating realistic stock prices when `MASSIVE_API_KEY` is unset. This is the **default** market data path for FinAlly — most users (and all CI runs) will never see real data.

The simulator must look and feel like a live tape: prices that wiggle smoothly, occasionally jump, and don't all move in the same direction at the same time. It must also be *cheap* (we run it inside the FastAPI process, ~2 ticks/second, alongside everything else).

---

## 1. Approach: Geometric Brownian Motion

GBM is the classical lognormal price process underlying Black‑Scholes. We pick it for three concrete reasons:

| Property | Why it matters here |
|----------|---------------------|
| **Lognormal** — `S(t) > 0` always | Prices never go negative; no bounds checking, no "if price < 0 reset" hacks. |
| **Stationary log‑returns** | Tunable per ticker via two scalars (`mu`, `sigma`) — easy to make AAPL boring and TSLA wild. |
| **Closed‑form one‑step update** | One `exp()` and a normal draw per ticker per tick → trivially fast for ≤ 50 tickers at 2 Hz. |

The simulation is **discrete‑time, fixed step**: every 500 ms we advance every tracked ticker by one tick. This matches the SSE cadence so the dashboard sees a fresh price on every event without buffering.

---

## 2. The GBM Step

For each ticker at each tick:

```
S(t + dt) = S(t) · exp( (μ − σ²/2) · dt  +  σ · √dt · Z )
```

| Symbol | Meaning | Typical value |
|--------|---------|---------------|
| `S(t)` | current price | seeded per‑ticker (see §5) |
| `μ`    | annualised drift (expected return) | 0.03 – 0.08 |
| `σ`    | annualised volatility | 0.17 – 0.50 |
| `dt`   | time step as fraction of a trading year | ~8.48 × 10⁻⁸ |
| `Z`    | standard normal draw, *correlated* across tickers | N(0,1) |

### Choosing `dt`

A US trading year is **252 days × 6.5 hours × 3600 seconds ≈ 5,896,800 seconds**. A 500 ms tick is therefore:

```
dt = 0.5 / 5_896_800 ≈ 8.48e-8
```

This tiny `dt` is the trick that makes the per‑tick move realistic. With `σ = 0.22`:

```
σ · √dt ≈ 0.22 · √8.48e-8 ≈ 6.4e-5
```

…i.e. roughly **0.0064% expected move per tick** for AAPL. Multiplied by 2 ticks/s × 23,400 s/day ≈ 46,800 ticks/day, you get a daily standard deviation of `0.22 / √252 ≈ 1.39%`, which is exactly the volatility we asked for.

This is why we *don't* hand‑tune the per‑tick move: pick the annualised σ you want, the math gives you the right tick size for free.

---

## 3. Correlated Moves via Cholesky

Real markets co‑move. If AAPL drops 1 %, GOOGL probably dropped 0.6 % at the same time. Independent draws would look completely fake.

We build a correlation matrix `C` (described in §6) and decompose it via Cholesky:

```
L = cholesky(C)        # lower-triangular, L · Lᵀ = C
Z_correlated = L @ Z_independent
```

`Z_independent` are `n` i.i.d. standard normals; `Z_correlated` are `n` standard normals with the desired pairwise correlations. Each ticker's GBM step then uses its own component of `Z_correlated`.

Cholesky is rebuilt only when the watchlist changes (rare), not every tick. The hot path is just one `n × n` matrix‑vector product, which is dominated by the `numpy` overhead for small `n`.

---

## 4. Random Shocks

Smooth GBM alone is too smooth — a real terminal occasionally lights up green or red on a headline. We sprinkle in shocks:

```python
EVENT_PROB = 0.001                                  # ~0.1% per ticker per tick

if random.random() < EVENT_PROB:
    magnitude = random.uniform(0.02, 0.05)          # 2–5%
    sign      = random.choice([-1, 1])
    price    *= 1 + magnitude * sign
```

With 10 tickers ticking twice a second, the expected time between shocks across the watchlist is `1 / (10 · 2 · 0.001) = 50 s` — frequent enough to be noticeable, rare enough to feel like news.

Shocks are applied *after* the GBM step, so they compound on top of the diffusion rather than replacing it.

---

## 5. Seed Prices

Realistic starting prices for the default ten tickers, baked into `seed_prices.py`:

```python
SEED_PRICES: dict[str, float] = {
    "AAPL":  190.00,
    "GOOGL": 175.00,
    "MSFT":  420.00,
    "AMZN":  185.00,
    "TSLA":  250.00,
    "NVDA":  800.00,
    "META":  500.00,
    "JPM":   195.00,
    "V":     280.00,
    "NFLX":  600.00,
}
```

Tickers added at runtime (e.g. via watchlist mutation) and not in the table fall back to `random.uniform(50, 300)`. That's a wide enough range to avoid screen‑filling six‑digit prices for an obscure ticker, narrow enough to look plausible.

---

## 6. Per‑Ticker Parameters

Each ticker carries its own `(μ, σ)`, in `seed_prices.py`:

```python
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
DEFAULT_PARAMS = {"sigma": 0.25, "mu": 0.05}        # fallback for unknown tickers
```

### Correlation Tables

```python
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech":    {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

INTRA_TECH_CORR    = 0.6      # within tech: high
INTRA_FINANCE_CORR = 0.5      # within finance: medium-high
CROSS_GROUP_CORR   = 0.3      # everything else: weak
TSLA_CORR          = 0.3      # TSLA is in tech but does its own thing
```

Pairwise correlation lookup:

```python
def _pairwise_correlation(t1: str, t2: str) -> float:
    if t1 == "TSLA" or t2 == "TSLA":           return TSLA_CORR
    if {t1, t2} <= CORRELATION_GROUPS["tech"]:    return INTRA_TECH_CORR
    if {t1, t2} <= CORRELATION_GROUPS["finance"]: return INTRA_FINANCE_CORR
    return CROSS_GROUP_CORR
```

The matrix built from this lookup is positive semi‑definite for any subset of these tickers (verified in tests), so `np.linalg.cholesky` always succeeds. If we ever introduce a correlation rule that breaks PSD‑ness, the Cholesky call will raise immediately at watchlist‑change time, which is the right place to surface that bug.

---

## 7. The `GBMSimulator` Class

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
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR          # ≈ 8.48e-8

    def __init__(self, tickers, dt=DEFAULT_DT, event_probability=0.001):
        self._dt        = dt
        self._evt_prob  = event_probability
        self._tickers:  list[str]                = []
        self._prices:   dict[str, float]         = {}
        self._params:   dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None        = None

        for t in tickers:
            self._add_ticker_internal(t)
        self._rebuild_cholesky()

    # ── hot path ────────────────────────────────────────────────────
    def step(self) -> dict[str, float]:
        n = len(self._tickers)
        if n == 0: return {}

        z_indep = np.random.standard_normal(n)
        z_corr  = self._cholesky @ z_indep if self._cholesky is not None else z_indep

        out: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            p   = self._params[ticker]
            mu, sigma = p["mu"], p["sigma"]

            drift     = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_corr[i]
            self._prices[ticker] *= math.exp(drift + diffusion)

            if random.random() < self._evt_prob:
                self._prices[ticker] *= 1 + random.uniform(0.02, 0.05) * random.choice([-1, 1])

            out[ticker] = round(self._prices[ticker], 2)

        return out

    # ── lifecycle ───────────────────────────────────────────────────
    def add_ticker(self, ticker: str) -> None:
        if ticker in self._prices: return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        if ticker not in self._prices: return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str)     -> float | None: return self._prices.get(ticker)
    def get_tickers(self)                -> list[str]:    return list(self._tickers)

    # ── internals ───────────────────────────────────────────────────
    def _add_ticker_internal(self, ticker: str) -> None:
        if ticker in self._prices: return
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
        tech, finance = CORRELATION_GROUPS["tech"], CORRELATION_GROUPS["finance"]
        if t1 == "TSLA" or t2 == "TSLA":         return TSLA_CORR
        if t1 in tech    and t2 in tech:         return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:      return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

---

## 8. Wrapping the Simulator as a `MarketDataSource`

The simulator itself is synchronous and stateless‑per‑step. The async adapter is small:

```python
import asyncio, logging
from .interface import MarketDataSource
from .cache import PriceCache

log = logging.getLogger(__name__)

class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache,
                 update_interval: float = 0.5,
                 event_probability: float = 0.001):
        self._cache    = price_cache
        self._interval = update_interval
        self._evt_prob = event_probability
        self._sim:  GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._evt_prob)
        for t in tickers:                                 # seed cache so SSE has data immediately
            p = self._sim.get_price(t)
            if p is not None: self._cache.update(ticker=t, price=p)
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
            try: await self._task
            except asyncio.CancelledError: pass
        self._task = None

    async def add_ticker(self, t: str) -> None:
        if self._sim:
            self._sim.add_ticker(t)
            p = self._sim.get_price(t)
            if p is not None: self._cache.update(ticker=t, price=p)

    async def remove_ticker(self, t: str) -> None:
        if self._sim: self._sim.remove_ticker(t)
        self._cache.remove(t)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []
```

Two non‑obvious details:
- `start()` writes seed prices into the cache **before** kicking off the loop, so the very first SSE message after page load has data — no "0.00 → real price" flicker.
- The loop swallows any exception from `step()` and logs it. Test runs occasionally hit a transient `LinAlgError` if a developer messes up the correlation table; we want to see the error, not bring the dashboard down.

---

## 9. File Structure

```
backend/app/market/
├── seed_prices.py     # SEED_PRICES, TICKER_PARAMS, correlation constants  (≈ 50 LOC)
└── simulator.py       # GBMSimulator + SimulatorDataSource                 (≈ 270 LOC)
```

`seed_prices.py` is **pure data** — no imports of anything but `dict`/`set`. This makes it trivially testable and trivially editable for someone adding new tickers.

---

## 10. Properties & Sanity Checks

Properties the simulator must satisfy (all covered by `tests/market/test_simulator.py`):

1. **Positivity:** `price > 0` for every ticker after every `step()`.
2. **Smoothness without shocks:** with `event_probability=0`, the per‑tick log‑return is bounded: `|ln(S_{t+1} / S_t)| ≤ 5σ√dt` with overwhelming probability.
3. **Correct long‑run vol:** averaging `Var(ln(S))` over many ticks reproduces `σ²·dt` per tick.
4. **Correlation:** with `corr(AAPL, GOOGL) = 0.6`, the empirical correlation of returns over 100k ticks is within ±0.05.
5. **Add/remove invariance:** removing a ticker and re‑adding it preserves the *other* tickers' prices exactly.
6. **PSD correlation matrix:** Cholesky never raises for any subset of the default ten tickers.

A "shock test" also asserts the empirical event rate is within 20 % of `event_probability` over 50k ticks per ticker.

---

## 11. Behavioural Notes

- **Determinism for tests.** Tests seed both `random` and `numpy.random` before constructing the simulator, then compare exact prices. Production code never seeds.
- **Add‑mid‑session.** A ticker added after `start()` jumps in at its seed price; correlations apply from the next tick onward. There is intentionally no warm‑up.
- **Realism ceiling.** GBM has no fat tails, no autocorrelation, no volatility clustering. We're not pricing options; we're producing a believable visual feed. Don't over‑engineer this.
- **Concurrency.** `step()` is called from a single asyncio task. The simulator itself is *not* thread‑safe and doesn't need to be. Only `PriceCache` needs locking.
- **Live demo.** `backend/market_data_demo.py` runs the simulator standalone with a Rich terminal dashboard — useful for eyeballing changes to parameters before committing them.
