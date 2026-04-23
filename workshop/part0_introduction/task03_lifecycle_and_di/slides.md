# Lesson 0.3 — Service Lifecycle & Dependency Injection (Slides)

**Duration:** ~30 min live + 30 min lab
**Audience:** anyone who can read Python but hasn't written FastAPI at scale
**Format:** 17 slides

---

## Slide 1 — Title

**Service Lifecycle & Dependency Injection**
*The two patterns every service in the baseline uses*

Workshop Part 0 · Lesson 0.3

---

## Slide 2 — What you should leave with

- Know what a **lifespan** is and when things run
- Know what `Depends()` does and why it beats calling functions yourself
- Recognize the **module-global singleton pattern** for expensive dependencies
- Recognize the **generator dependency pattern** for setup+teardown resources
- Be able to add a new dependency-injected route to any service in the repo

---

## Slide 3 — The repeated shape

Every service in `baseline/` has the same startup story:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_dependencies(settings)     # startup
    yield                           # (app runs here)
    await dispose_engine()          # shutdown
```

And every route that needs resources looks like:

```python
async def endpoint(db = Depends(get_session)):
    ...
```

Learn these once, the whole codebase opens up.

---

## Slide 4 — Intuition: the restaurant

- **Lifespan** = opening prep + closing cleanup. Done *once*, not per order.
- **Dependency Injection** = the waiter hands the cook their pan. Cook doesn't go find it.

The prep kitchen is the `lifespan` block. The waiter is FastAPI's `Depends()` resolver.

---

## Slide 5 — A minimal lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await open_expensive_connection()
    app.state.client = client
    yield
    await client.close()
```

`yield` is the split point. Before = startup. After = shutdown.

```python
app = FastAPI(lifespan=lifespan)
```

---

## Slide 6 — A minimal dependency

```python
def get_logger():
    return logging.getLogger(__name__)

@app.get("/hi")
async def hi(log = Depends(get_logger)):
    log.info("called")
    return {"ok": True}
```

`Depends(get_logger)` tells FastAPI "call this function, pass me the result."

---

## Slide 7 — The baseline's three-file structure

Every service has:

| File | Purpose |
|---|---|
| `config.py` | Pydantic `BaseSettings` — env-driven config |
| `dependencies.py` | Module-level globals + `init_*` + `get_*` functions |
| `main.py` | `lifespan` + `app = FastAPI()` + middleware + routers |

When you're lost, these three files have the answer.

---

## Slide 8 — The DI layer in detail

`baseline/api_gateway/app/dependencies.py`:

```python
_model_client: ServiceClient | None = None

def init_dependencies(settings):
    global _model_client
    _model_client = ServiceClient(base_url=settings.model_service_url)
    return _model_client

def get_model_client() -> ServiceClient:
    if _model_client is None:
        raise RuntimeError("Model client not initialized.")
    return _model_client
```

**Three pieces:** the global slot, the initializer, the accessor.

---

## Slide 9 — Why `@lru_cache` on settings?

```python
@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()
```

- Pydantic `BaseSettings()` re-reads `.env` every time
- Routes that `Depends(get_settings)` run on every request
- Without cache: 200ms `.env` parse on every request — wasteful
- With cache: first call parses, rest return the cached instance

With no args, `@lru_cache` acts as a singleton.

---

## Slide 10 — Database sessions: generator dependency

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
```

FastAPI detects the generator. Runs up to `yield`, returns the session, then **resumes after the route** to run the cleanup. Session always closed, even on exception.

Usage:

```python
async def endpoint(db: AsyncSession = Depends(get_session)):
    ...
```

---

## Slide 11 — Middleware order (gotcha)

```python
app.add_middleware(TimingMiddleware)      # outermost, runs first
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSMiddleware, ...)   # innermost, runs last
```

**Last added = outermost.** Counterintuitive. Timing wraps everything so it captures full latency including CORS cost.

---

## Slide 12 — Lifespan sequence diagram

```
import main.py ──► settings = get_settings()        (module-level)
                   setup_logging()
                   app = FastAPI(lifespan=lifespan)
                                          │
                                          ▼
                    async with lifespan(app):
                         init_dependencies()          ◄── before yield
                         await client.start()
                         (yield)                      ◄── traffic flows
                         await client.close()         ◄── after yield
                         await dispose_engine()
                                          │
                                          ▼
                                       exit 0
```

---

## Slide 13 — The dependency override escape hatch

Testing magic:

```python
app.dependency_overrides[get_model_client] = lambda: FakeModelClient()
```

- Works because `get_model_client` is a *function*, not a hard-coded object
- Reset with `app.dependency_overrides.clear()` between tests
- This is why module-global singletons beat `client = ServiceClient()` at the top of the file

Part I Task 4 goes deep on this.

---

## Slide 14 — Common mistakes

1. **Instantiating in a route body** — `client = ServiceClient(...)` inside a handler. New connection every request. Pool exhaustion within minutes under load.
2. **Forgetting `await ... close()`** — connections leak across restarts, eventually the DB rejects new connections.
3. **Mutable default args on dependencies** — Python evaluates defaults once at import; a mutable default shared across requests is a subtle concurrency bug.
4. **Reading `.env` in a route** — same cost as instantiating in a route. Use `Depends(get_settings)`.

---

## Slide 15 — Live walkthrough

Open these three files, read them *in order*:

1. `baseline/api_gateway/app/config.py` (Pydantic settings)
2. `baseline/api_gateway/app/dependencies.py` (DI layer)
3. `baseline/api_gateway/app/main.py` (lifespan + app)

Each is under 100 lines. Together they're the whole recipe.

---

## Slide 16 — Lab preview

Add a **request counter** to the API Gateway:

1. `starter/count_middleware.py` — stubbed middleware that increments on every request
2. `starter/custom_dep.py` — stubbed `get_counter` dependency
3. Wire it through `dependencies.py` (you'll edit a real file)
4. Add a `GET /api/v1/metrics/requests` route
5. Verify with pytest: 10 requests → counter == 10

Full lab with `starter/` + `solution/`.

---

## Slide 17 — Key takeaways

1. **Lifespan** = one `async with` that wraps the whole app lifetime. `yield` splits startup from shutdown.
2. **`Depends()`** = FastAPI calls a function for you, passes the result. That's it.
3. **Module-level globals + init_*() + get_*()** — the pattern for shared, expensive resources.
4. **Generator dependencies** — the pattern for setup+teardown (DB sessions, file handles, transactions).
5. **Everything is a function** — which is why `dependency_overrides` makes testing trivial.

**Next up:** Lesson 0.4 — Request Flows.
