# Market Data Backend Review

**Date:** 2026-04-25  
**Scope:** `backend/app/market/`, `backend/tests/market/`, and the market-data planning documents in `planning/`

## Executive Summary

The market data backend is close to the documented design: the shared `PriceCache`, immutable `PriceUpdate`, source factory, GBM simulator, Massive poller, and SSE envelope are all implemented with a clean separation of responsibilities. The non-Massive test coverage is healthy and passes locally.

However, I do **not** consider the implementation fully ready yet. The complete pytest suite is not currently reproducible because the Massive tests hang during process teardown, and there are several contract gaps around ticker normalization, cache versioning on removal, and SSE heartbeat behavior.

## Test Results

### Full Suite

Command:

```bash
cd backend
uv --cache-dir /tmp/uv-cache run pytest
```

Result:

- The first attempt without `--cache-dir` failed because the sandbox could not write to `~/.cache/uv`.
- With `--cache-dir /tmp/uv-cache`, pytest collected 73 tests.
- The run reached `21 passed` and then hung in `tests/market/test_massive.py`.
- I interrupted the hung process after roughly 3 minutes 47 seconds.

Observed output at interruption:

```text
21 passed in 227.81s
KeyboardInterrupt at /usr/lib/python3.12/selectors.py:468
```

### Non-Massive Market Tests

Command:

```bash
cd backend
uv --cache-dir /tmp/uv-cache run pytest \
  tests/market/test_cache.py \
  tests/market/test_factory.py \
  tests/market/test_models.py \
  tests/market/test_simulator.py \
  tests/market/test_simulator_source.py
```

Result:

```text
60 passed in 3.10s
```

### Massive Test Isolation

Running individual Massive tests with `timeout 10s` shows that tests such as `test_poll_updates_cache` and `test_malformed_snapshot_skipped` print `PASSED [100%]`, but the pytest process does not exit before the timeout kills it. This points to a teardown/process-lifetime leak around the Massive tests that use `asyncio.to_thread(...)`, not to a normal assertion failure.

### Lint

Command:

```bash
cd backend
uv --cache-dir /tmp/uv-cache run ruff check .
```

Result:

```text
All checks passed!
```

## Findings

### High: Complete Test Suite Hangs In Massive Tests

`backend/tests/market/test_massive.py:25` and similar tests patch `source._fetch_snapshots`, then exercise `_poll_once()`, which calls `asyncio.to_thread(...)` in `backend/app/market/massive_client.py:97`.

The assertions complete, but pytest does not terminate afterward. This blocks the documented claim that all market data tests pass and makes CI unreliable.

Recommended fix:

- Refactor `MassiveDataSource` so the thread boundary is mockable without leaving executor state behind, or add explicit test cleanup for the event loop default executor.
- Add a timeout guard in CI for this test module until the root cause is fixed.

### High: Simulator Source Does Not Normalize Tickers

The lifecycle contract says `add_ticker()` and related source operations normalize tickers by uppercasing and trimming whitespace. `SimulatorDataSource` does not do that:

- `backend/app/market/simulator.py:219` passes initial `tickers` directly into `GBMSimulator`.
- `backend/app/market/simulator.py:225` seeds the cache under the original ticker strings.
- `backend/app/market/simulator.py:242` adds ticker strings as provided.
- `backend/app/market/simulator.py:251` removes ticker strings as provided.

Impact:

- `await source.add_ticker("aapl")` creates a separate lowercase ticker instead of resolving to `AAPL`.
- `await source.remove_ticker(" aapl ")` will not remove `AAPL`.
- Unknown lowercase defaults get random seed prices instead of documented seed prices.

Recommended fix:

- Normalize in `SimulatorDataSource.start()`, `add_ticker()`, and `remove_ticker()`.
- Add tests for lowercase and whitespace on simulator start/add/remove.

### Medium: Massive Source Does Not Normalize Initial Tickers

`MassiveDataSource.add_ticker()` normalizes inputs, but `start()` does not:

- `backend/app/market/massive_client.py:41`
- `backend/app/market/massive_client.py:43`

The Massive API documentation notes tickers are case-sensitive, and the planning contract says sources normalize ticker symbols. If startup receives lowercase or whitespace-padded symbols from persistence or future watchlist code, the first poll can send invalid ticker strings.

Recommended fix:

- Normalize `tickers` in `MassiveDataSource.start()`.
- Add a test covering `await source.start([" aapl "])`.

### Medium: Removing A Ticker Does Not Bump Cache Version

`PriceCache.remove()` deletes the entry but does not increment `_version`:

- `backend/app/market/cache.py:59`
- `backend/app/market/cache.py:62`

The SSE generator emits only when `price_cache.version` changes:

- `backend/app/market/stream.py:75`
- `backend/app/market/stream.py:76`

Impact:

- A client can retain a removed ticker until some later producer update changes the cache version.
- With a slow Massive poll interval, this can last up to the next poll.
- If the source is stopped or no further updates arrive, the stale ticker can remain in the frontend indefinitely.

Recommended fix:

- Increment `_version` when an existing ticker is removed.
- Add a test that `remove()` bumps `version` only when it actually changes the cache.

### Medium: SSE Heartbeats Are Documented But Not Implemented

`planning/PLAN.md` describes a comment heartbeat every 15 seconds so clients can detect stalled streams. The current SSE implementation emits only:

- an initial `retry: 1000`
- data events when `PriceCache.version` changes

See `backend/app/market/stream.py:61` and `backend/app/market/stream.py:75`.

Impact:

- During long periods without cache changes, proxies and clients receive no heartbeat traffic.
- This matters more with the Massive source, where updates can be sparse or stale outside market hours.

Recommended fix:

- Emit `: heartbeat\n\n` on a fixed interval while the stream is open.
- Add a small async generator test for no-change heartbeat behavior.

### Low: Module-Level Router Can Accumulate Duplicate Routes

`backend/app/market/stream.py:17` creates a module-level `APIRouter`, and `create_stream_router()` registers a route on that shared instance at `backend/app/market/stream.py:26`.

If `create_stream_router()` is called more than once in tests or future app factories, it can register duplicate `/prices` routes on the same router object.

Recommended fix:

- Move `router = APIRouter(...)` inside `create_stream_router()`.

### Low: Explicit Timestamp `0.0` Is Ignored

`PriceCache.update()` uses `timestamp or time.time()`:

- `backend/app/market/cache.py:30`

An explicit timestamp of `0.0` is replaced with the current time. This is unlikely for valid live market data, but it is still surprising for a low-level cache API.

Recommended fix:

- Use `time.time() if timestamp is None else timestamp`.

## Coverage Gaps

The current tests miss several important contract cases:

- No SSE stream tests for envelope format, version-based emission, client disconnects, or heartbeat behavior.
- No tests for simulator ticker normalization.
- No tests for Massive `start()` ticker normalization.
- No tests that `PriceCache.remove()` changes SSE-visible state through the version counter.
- No conformance test that runs both data sources through the same lifecycle script.
- No full default-watchlist correlation matrix test, despite the design calling out Cholesky success for the default ten tickers.

## Strengths

- `PriceUpdate` is immutable, compact, and computes derived fields cleanly.
- `PriceCache` has a simple lock-based design and returns shallow snapshots safely because updates are immutable.
- The simulator implementation follows the documented GBM formula and uses Cholesky correlation in the intended way.
- Startup cache seeding is implemented for both source types.
- Massive timestamp conversion from milliseconds to seconds is implemented.
- The factory selection rule is simple and matches the environment-variable contract.
- Ruff passes cleanly.

## Conclusion

The implementation is architecturally sound, but the claim that the market data backend is fully tested is not currently reproducible. Before downstream API/frontend work depends on this subsystem, I would fix the Massive test hang, normalize tickers consistently across both sources, make cache removals visible to SSE clients through the version counter, and add the documented SSE heartbeat.
