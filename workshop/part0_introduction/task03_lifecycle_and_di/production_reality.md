# Production Reality — Lesson 0.3 Lifecycle & Dependency Injection

> Lifespans and DI are what keep a service healthy across thousands of requests per second. Here's what goes wrong when they're done poorly.

## What breaks at scale

### 1. The slow startup that blocks rollouts

**The failure mode:** your `lifespan` calls `await model_client.start()` which in turn opens a connection pool that DNS-resolves the model service URL. The DNS server is momentarily slow; the resolve takes 30 seconds; uvicorn times out; the pod crash-loops.

**In the baseline:** `init_dependencies` creates `ServiceClient` instances eagerly. If the model service is unreachable, startup doesn't fail — but the first request does. That's a design trade-off: fail-fast at startup vs. fail-slow at first request.

**What senior engineers do:**
- **Separate "construct" from "warm up".** Construction is synchronous and safe. Warm-up (opening sockets, pre-loading models, checking external dependencies) is a separate async step you can time-bound.
- **Time-box every startup await.** `asyncio.wait_for(client.start(), timeout=10)` — better to crash explicitly than hang forever.
- **Make the health endpoint reflect startup state.** Return 503 until all lifespan steps complete; only flip to 200 after `yield`.

### 2. The dependency that outlives its owner

**The failure mode:** `init_dependencies` creates an `httpx.AsyncClient`. Somewhere in a route, code grabs a reference to it, stores it in a module-level dict, and keeps using it after `lifespan` closes the client at shutdown. Result: `RuntimeError: client has been closed`.

**Rule of thumb:** if you resolved it via `Depends()`, don't save it. If you need to "remember" a client across requests, store the result of its work, not the client itself.

**What senior engineers do:**
- **Treat `Depends()` return values as request-scoped**, even if the underlying object is a singleton.
- **Only the code in `dependencies.py` should hold long-lived references.** Everyone else gets a view via `Depends()`.
- **Write a test that creates the app, sends 100 requests, shuts down, and asserts no outstanding connections.** Leaks show up immediately.

### 3. `@lru_cache` hiding a live config drift

**The failure mode:** `get_settings()` is `@lru_cache`d. Someone rotates a secret in AWS Secrets Manager. The running pod keeps using the old secret because the settings object was cached at import. The secret is revoked at the provider; the pod starts 401-ing until someone restarts it.

**In production:** secret rotation is a thing. Pods need to either pull fresh config periodically or crash on 401 so K8s restarts them.

**What senior engineers do:**
- **For secrets: don't cache forever.** Pull from the secret manager on every request, with a short local TTL (e.g., 60s). Expensive-but-bounded.
- **For infrequent-change config: crash-then-reload.** Use a watcher (ConfigMap reload, file watcher) that either triggers a graceful restart or mutates the cached settings in place.
- **For the baseline's dev workflow:** `@lru_cache` on settings is fine because `.env` doesn't change at runtime. Don't copy-paste this pattern to production secret handling without modification.

### 4. Generator dependencies that swallow exceptions

**The failure mode:** someone writes:

```python
async def get_session():
    session = sm()
    try:
        yield session
    except Exception:
        pass  # "be defensive"
    finally:
        await session.close()
```

Now every route exception is silently swallowed. The client sees 500 with no message; the logs show nothing.

**What senior engineers do:**
- **Re-raise or don't catch.** The `async with` in the real `get_session()` does the right thing because SQLAlchemy's context manager re-raises.
- **Never `except Exception: pass` in dependency code.** If cleanup needs to happen on error, use `try/finally` — not `try/except`.

## What fails in production

### The deploy that leaks connections

You deploy a new version. New pods start, old pods terminate. Old pods' `lifespan` shutdown code should close their DB connections. If it doesn't — if `await dispose_engine()` is missing — each deploy leaks up to `pool_size + max_overflow` connections. After 5 deploys, you've consumed 75 of Postgres's 100 `max_connections`. After 7 deploys, the new pods can't connect.

**In the baseline:** `dispose_engine()` is called in the gateway and worker `lifespan` shutdowns. Verified by the shutdown-sequence assertion in the integration tests.

**In production:** add a Prometheus alert on `pg_stat_activity.numbackends` trending upward over a deploy-free window. It's a leak detector.

### The race between lifespan shutdown and in-flight requests

You send SIGTERM. uvicorn starts draining — it stops accepting new connections but lets in-flight requests finish. Your `lifespan` shutdown code runs **in parallel** with the drain. If it closes the DB engine while a drain request is mid-query, the request fails.

**What senior engineers do:**
- **Drain first, then close resources.** In Starlette/uvicorn, lifespan shutdown runs *after* the drain by default. Don't override this.
- **Never close a DB engine before in-flight requests complete.** If you see "DatabaseError: connection closed" in shutdown logs, you have this bug.
- **Set a shutdown timeout longer than your p99 latency** so slow requests get to finish. K8s `terminationGracePeriodSeconds: 30` is default; bump to 60 if your p99 is > 20s.

## Senior engineer patterns

### Pattern 1 — "Configure, construct, warm up" triad

```python
async def lifespan(app):
    # 1. Configure — synchronous, pure
    settings = get_settings()

    # 2. Construct — synchronous, cheap
    clients = init_dependencies(settings)

    # 3. Warm up — async, time-bounded, fail-fast
    async with asyncio.timeout(30):
        await asyncio.gather(*(c.start() for c in clients))

    yield

    await asyncio.gather(*(c.close() for c in clients), return_exceptions=True)
    await dispose_engine()
```

Separating the phases means failures are attributable: a bad env var fails in phase 1, a bad URL in phase 2, an unreachable dependency in phase 3.

### Pattern 2 — Dependency chains

`Depends()` can call `Depends()`. This is legit and powerful:

```python
async def get_user_repo(db: AsyncSession = Depends(get_session)) -> UserRepository:
    return UserRepository(db)

async def endpoint(repo: UserRepository = Depends(get_user_repo)):
    ...
```

FastAPI builds the dependency graph and resolves it correctly. Use this to wrap raw sessions in higher-level repository objects — the pattern used in `baseline/api_gateway/app/routes/chat.py` via `_repo()`.

### Pattern 3 — Testing with `dependency_overrides`

```python
def test_endpoint_returns_count():
    app.dependency_overrides[get_model_client] = lambda: FakeModelClient(response="pong")
    with TestClient(app) as client:
        r = client.post("/api/v1/generate", json={"prompt": "ping"})
        assert r.json()["response"] == "pong"
    app.dependency_overrides.clear()
```

You never instantiate the real client in tests. Perfectly isolated, fast, no network.

### Pattern 4 — Request-scoped vs process-scoped resources

| Scope | Example | How |
|---|---|---|
| **Process** | Settings, service clients, ML model weights, engine | Module-level global + lifespan init |
| **Request** | DB session, per-request logger, current user | Generator dependency |
| **Batch** | Celery-ish task state | Task-scoped context var |

Getting the scope right is half the battle. Put a DB session in process scope and you get lock contention across concurrent requests. Put an ML model in request scope and you spend 3 seconds loading it on every request.

## Monitoring needed

| Signal | Why | Tool |
|---|---|---|
| **Startup time (p99)** | Detects slow `lifespan` steps | uvicorn access logs + Prometheus |
| **Shutdown time (p99)** | Detects drain-blocking bugs | K8s pod-lifecycle events |
| **Open DB connections** | Detects pool leaks across deploys | `pg_stat_activity.numbackends` |
| **`httpx` pool saturation** | Detects upstream-call contention | `httpx` hooks + Prometheus |
| **500s in first 10s after rollout** | Detects lifespan races | Datadog APM "recent deploys" view |
| **Settings cache hits** | Detects config drift | Log-based metric on `get_settings` calls |

## Common mistakes

1. **Creating a client in a route body.** `client = httpx.AsyncClient()` inside a handler → pool explosion under load. Always use `Depends()`.
2. **Forgetting to `await` in a dependency.** `def get_session(): return sm()` instead of `async def get_session(): async with sm() as s: yield s`. First form leaks; second is correct.
3. **Module-level side effects beyond `get_settings()`.** Opening files, making HTTP calls, connecting to DBs at import time. Imports must be fast and side-effect-free.
4. **Depending on `app.state` instead of `dependencies.py`.** `app.state.client = ...` works but isn't type-safe and makes testing harder. Use the `dependencies.py` pattern.
5. **Not closing resources on exception.** Always `try/finally` or `async with` — never just `try/except`.
6. **Caching mutable state with `@lru_cache`.** The cache returns the same object across callers. If one caller mutates it, everyone sees the mutation. Use it only for immutable results.

## Interview-style questions

1. **What's the difference between a function dependency and a generator dependency in FastAPI?**
   *Function dependency: returns a value; FastAPI passes it to the route. Generator dependency: yields a value to the route, then resumes after the route completes for cleanup. Used for setup+teardown resources like DB sessions.*

2. **Why is `@lru_cache` used on `get_settings()`?**
   *Pydantic `BaseSettings()` re-parses env vars every call. Without caching, every `Depends(get_settings)` would re-parse on every request. `@lru_cache` with no args makes it a singleton for the process lifetime.*

3. **In what order does middleware execute if added as `TimingMiddleware`, `RequestLoggingMiddleware`, `CORSMiddleware`?**
   *Last added = outermost. So request flow: `TimingMiddleware` → `RequestLoggingMiddleware` → `CORSMiddleware` → route. Response flow: reverse. Timing captures the full latency of everything inside it.*

4. **What's the risk of holding a reference to a `Depends()`-injected client past request boundaries?**
   *The underlying client may be closed at shutdown while your reference is still live. You'll get a `RuntimeError: client has been closed` on next use. Treat `Depends()` return values as request-scoped views.*

5. **How do you test a route that `Depends(get_model_client)` without hitting the real model service?**
   *Use `app.dependency_overrides[get_model_client] = lambda: FakeClient()`. FastAPI calls your lambda in place of the real dependency. Clear overrides between tests with `app.dependency_overrides.clear()`.*

## Further reading

- [FastAPI — Dependencies with yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)
- [FastAPI — Lifespan events](https://fastapi.tiangolo.com/advanced/events/)
- [Starlette — Middleware](https://www.starlette.io/middleware/) — the machinery under FastAPI's middleware
- `architecture/backend-architecture.md` §1 (Lifespan Lifecycle) and §5 (Shared Module)
- Part I Task 4 — FastAPI Dependency Injection — the deep dive that builds on this lesson
