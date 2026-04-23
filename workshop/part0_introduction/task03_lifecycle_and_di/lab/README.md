# Lab 0.3 — Wire a Request Counter Through FastAPI DI

> **Goal:** practice the three-piece pattern (module-global + `init_*` + `get_*`)
> by adding a request counter to the API Gateway. You'll touch the same files
> that every service in `baseline/` uses — `dependencies.py`, `main.py`, a new
> middleware, and a new route — but in a tiny, self-contained problem.

## Problem statement

The ops team wants a quick-and-dirty metric: how many requests has the gateway
handled since it started? They don't care about percentiles or per-endpoint
breakdowns yet — just a running count exposed at `GET /api/v1/metrics/requests`.

You'll build this using **only the patterns from the lesson**:

1. A module-global counter object in `dependencies.py` (the "expensive" resource
   here is just a thread-safe int, but the shape is identical to a real client).
2. An `init_counter()` function called from `lifespan`.
3. A `get_counter()` FastAPI dependency.
4. A middleware that increments the counter on every request.
5. A route `GET /api/v1/metrics/requests` that returns the current value via
   `Depends(get_counter)`.

## Prerequisites

- Lab 0.1 completed — stack runs end-to-end, `/api/v1/generate` works
- Lesson 0.3 read through at least once
- Familiarity with `baseline/api_gateway/app/` layout from Lesson 0.2

## Files in this lab

```
lab/
├── starter/
│   ├── count_middleware.py   # middleware skeleton with TODOs
│   └── custom_dep.py         # counter class + get_counter skeleton
└── solution/
    ├── count_middleware.py   # completed middleware
    ├── custom_dep.py         # completed counter + deps
    └── test_counter_dep.py   # pytest that asserts counter == 10 after 10 calls
```

The **starter** files are stubs you copy into the baseline. The **solution**
files are the reference implementation — peek only after you've tried it
yourself, or use them as the answer key during review.

## Tasks

### Task 1 — Read the three anchor files

Open these three files side-by-side before you touch anything:

- `baseline/api_gateway/app/dependencies.py`
- `baseline/api_gateway/app/main.py`
- `baseline/api_gateway/app/middleware/timing.py`

You're going to imitate the patterns you see there. In particular, notice:

- How `_model_client` is declared, populated in `init_dependencies`, and
  accessed via `get_model_client()`.
- How `lifespan` calls `init_dependencies(settings)` before `yield`.
- How `TimingMiddleware` subclasses `BaseHTTPMiddleware` and overrides
  `dispatch`.

### Task 2 — Complete `custom_dep.py`

Open `starter/custom_dep.py`. It contains:

- A `RequestCounter` class with a thread-safe `increment()` and a `value`
  property (already written — it's trivial on purpose).
- A module-global `_counter: RequestCounter | None = None` slot.
- `init_counter()` — **TODO:** populate the global and return the instance.
- `get_counter()` — **TODO:** return the global, or raise if uninitialized.

Copy `starter/custom_dep.py` into
`baseline/api_gateway/app/dependencies_counter.py` (new file; keep it separate
from the production `dependencies.py` to keep the diff surgical), then fill in
the two TODOs.

### Task 3 — Complete `count_middleware.py`

Open `starter/count_middleware.py`. It has a `CountMiddleware` class that
subclasses `BaseHTTPMiddleware`. The `dispatch` method is a stub — **TODO:**
call `get_counter().increment()` and return the response.

Copy it into `baseline/api_gateway/app/middleware/count.py`.

### Task 4 — Wire it into `main.py`

Two edits to `baseline/api_gateway/app/main.py`:

1. In `lifespan`, call `init_counter()` right after `init_dependencies(settings)`.
2. Add `app.add_middleware(CountMiddleware)` in the middleware block. Order
   matters — add it **before** `TimingMiddleware` so counting runs outside
   timing (the reason: timing wraps the actual work; counting is a pure
   side-effect that shouldn't affect the measured latency).

### Task 5 — Add the metrics route

Create `baseline/api_gateway/app/routes/metrics.py`:

```python
from fastapi import APIRouter, Depends
from ..dependencies_counter import RequestCounter, get_counter

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

@router.get("/requests")
async def request_count(counter: RequestCounter = Depends(get_counter)):
    return {"count": counter.value}
```

Register it in `main.py`: `app.include_router(metrics.router)`.

### Task 6 — Verify manually

```bash
make run          # in one terminal
# in another:
curl -s localhost:8000/api/v1/metrics/requests
# {"count": 1}
curl -s localhost:8000/health
curl -s localhost:8000/api/v1/metrics/requests
# {"count": 3}  (the /metrics call itself counts)
```

### Task 7 — Verify with pytest

Copy `solution/test_counter_dep.py` into `baseline/tests/test_counter_dep.py`
and run:

```bash
pytest baseline/tests/test_counter_dep.py -v
```

The test spins up the app with `TestClient`, fires 10 requests, and asserts
the counter reads 10. If your wiring is correct it passes in <1s.

## Expected output

After Task 6:

```
{"count": 3}
```

(or whatever number reflects the requests you've made — the exact number
doesn't matter, monotonic increase does.)

After Task 7:

```
test_counter_dep.py::test_counter_increments_per_request PASSED
```

## Bonus challenges

1. **Per-endpoint breakdown.** Extend `RequestCounter` to hold a
   `dict[str, int]` keyed by `request.url.path`. Expose via
   `GET /api/v1/metrics/requests/by-path`.
2. **Reset endpoint.** Add `POST /api/v1/metrics/requests/reset` that zeroes
   the counter. What test would you write to ensure reset and increment race
   cleanly? (Hint: think about the `threading.Lock` already in
   `RequestCounter`.)
3. **Override in tests.** Use `app.dependency_overrides[get_counter] =
   lambda: FakeCounter()` to test a route in isolation without the real
   middleware ever running. Why is this possible? (Answer: because
   `get_counter` is a function, not a hardcoded object — this is the whole
   point of the module-global pattern.)
4. **Prometheus version.** Swap `RequestCounter` for `prometheus_client.Counter`
   and expose the standard `/metrics` endpoint. What changes about the
   lifespan wiring? (Answer: almost nothing — that's the pattern's value.)

## Troubleshooting

**`RuntimeError: Counter not initialized` on first request.** You forgot to
call `init_counter()` in `lifespan`. The assertion in `get_counter()` fires
because the global is still `None`.

**Counter doesn't increment.** Middleware isn't registered, or it's registered
after the response path (e.g. as a router-level dependency instead of via
`add_middleware`). Check the order of `app.add_middleware` calls.

**Test fails with `500 Internal Server Error`.** Likely an import cycle —
`dependencies_counter.py` importing from `main.py` or vice versa. Counter
module should have zero baseline imports except `logging`.

**Counter value is huge on first check.** You probably have the frontend or
another curl open hitting the gateway. Add a `print()` in `CountMiddleware.dispatch`
to see what paths are counted.

## What you learned

- The **3-piece DI pattern** is mechanical: global slot, init, getter. Repeat
  it for every shared resource.
- **Middleware wiring is order-sensitive** — `app.add_middleware` LIFO means
  last-added is outermost.
- **`dependency_overrides` is free testability** because the getter is a
  function, not a hardcoded object.
- You can wire a brand-new cross-cutting concern (counting) into the gateway
  in ~40 lines of code, across 3 files, with a pytest that pins it down.

Part I Task 4 goes much deeper on DI — including scoped dependencies,
dependency overrides, and testing strategies. This lab is the warm-up.
