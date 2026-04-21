# Production Reality Check: Dependency Injection in AI Systems

## What Breaks at Scale?

### 1. Singleton Dependencies That Hold State

At scale, you run multiple worker processes (e.g., `uvicorn --workers 4`). Each process has its own `@lru_cache` singleton. This means:

- `get_settings()` runs once per process, not once per server
- If you cache a model object in memory, you have N copies for N workers
- Token buckets or rate limiters in singletons do not share state across processes

**Fix:** Use external state stores (Redis) for shared state. Keep singletons only for truly process-local resources like config and clients.

### 2. Heavy Initialization in Dependency Functions

If `get_groq_client()` takes 2 seconds to initialize (downloading certs, warming connections), the first request to each worker is slow ("cold start"). At scale, rolling deployments cause waves of cold starts.

**Fix:** Use the lifespan pattern (as the baseline does). Initialize heavy objects at startup, not on first request. Health checks should only pass after initialization completes.

### 3. Dependency Functions That Block the Event Loop

```python
# BAD: sync HTTP call inside a dependency
def get_external_config():
    response = requests.get("http://config-service/config")  # blocks!
    return response.json()
```

FastAPI's async event loop is single-threaded. A blocking dependency stalls all requests.

**Fix:** Use `async def` dependencies with `httpx` or `aiohttp` for I/O. Or move sync work to a thread pool:
```python
async def get_external_config():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://config-service/config")
    return response.json()
```

### 4. Missing Cleanup on Shutdown

If the Groq client has an internal connection pool and you never close it:
- File descriptors leak across restarts
- Connections pile up on the API server side
- In Kubernetes, pods that do not drain connections get killed mid-request

**Fix:** Use `yield` dependencies or explicit cleanup in the lifespan shutdown phase:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    client = init_dependencies(settings)
    yield
    await client.close()  # cleanup
```

### 5. Circular Dependencies in Larger Systems

As the service grows, it becomes easy to accidentally introduce cycles:
```
AuthService needs UserRepo
UserRepo needs CacheService
CacheService needs AuthService  <-- cycle!
```

**Fix:** Enforce one-directional dependency flow. Use interfaces (Python Protocol classes) to break cycles. Code review the dependency graph when adding new services.

---

## What Monitoring Is Needed?

### Dependency Health

Each dependency should report its status to the health endpoint:

```python
@app.get("/health")
async def health():
    return {
        "groq_client": "connected" if client else "unavailable",
        "settings_loaded": True,
        "queue_depth": queue.size(),
    }
```

### Dependency Initialization Time

Track how long each dependency takes to initialize. If `init_dependencies()` suddenly takes 30 seconds, something changed upstream (DNS, API latency, cert rotation).

```python
import time

start = time.time()
client = GroqInferenceClient(api_key=settings.groq_api_key)
init_time = time.time() - start
logger.info("groq_client_initialized", duration_ms=init_time * 1000)
```

### Dependency Failure Rates

When an injected client fails (network error, auth error, timeout):
- Log the dependency name, error type, and duration
- Track failure rates per dependency
- Alert when a dependency's error rate exceeds a threshold

### Cache Hit Rates

For `@lru_cache` dependencies, monitor the cache info:
```python
print(get_settings.cache_info())
# CacheInfo(hits=9999, misses=1, maxsize=128, currsize=1)
```

If `misses` is growing, something is invalidating the cache unexpectedly.

---

## Common Mistakes

### 1. Over-Injecting: Everything Is a Dependency

```python
# Too far -- this is just a utility, not a dependency
def get_current_timestamp():
    return time.time()

@app.get("/")
async def handler(ts=Depends(get_current_timestamp)):
    ...
```

Not everything needs to be a dependency. Only inject things that need to be:
- Configured differently per environment
- Mocked in tests
- Shared across handlers

### 2. Forgetting to Clear Overrides in Tests

```python
# Test 1 overrides settings
app.dependency_overrides[get_settings] = lambda: TestSettings()

# Test 2 runs -- still using Test 1's override!
# The test passes for the wrong reason or fails mysteriously
```

**Fix:** Always clear overrides in teardown:
```python
@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()
```

### 3. Using `@lru_cache` on Functions with Parameters

```python
@lru_cache
def get_client(settings: Settings = Depends(get_settings)):
    return Groq(api_key=settings.groq_api_key)
```

`@lru_cache` caches based on arguments. Since `settings` is an object, it hashes the object reference. If a new Settings object is created (different reference, same values), the cache misses and a new client is created.

**Fix:** Use `@lru_cache` only on zero-parameter functions. For parameterized singletons, use the module-global + lifespan pattern.

### 4. Not Handling Dependency Initialization Failure

```python
def get_model_manager() -> ModelManager:
    if _model_manager is None:
        raise RuntimeError("Not initialized")
    return _model_manager
```

This is correct, but some teams forget the None check and get `NoneType has no attribute 'generate'` errors in production. Always validate that lifespan-initialized dependencies are actually initialized.

### 5. Injecting Mutable Global State

```python
request_count = {"value": 0}

def get_counter():
    return request_count

@app.post("/generate")
async def generate(counter=Depends(get_counter)):
    counter["value"] += 1  # race condition with async!
```

Mutable shared state plus async handlers equals race conditions.

**Fix:** Use `asyncio.Lock`, atomic counters, or external stores (Redis).

---

## What Would a Senior Engineer Change?

### 1. Add Dependency Injection Container for Large Services

For services with 20+ dependencies, the manual wiring becomes verbose. A senior engineer might introduce `dependency-injector` or a custom container:

```python
class Container:
    settings = providers.Singleton(Settings)
    groq_client = providers.Factory(Groq, api_key=settings.provided.groq_api_key)
    model_manager = providers.Singleton(ModelManager, client=groq_client)
```

But only when the manual approach becomes a bottleneck -- not prematurely.

### 2. Health Check Dependencies in a Separate Module

Instead of checking health inline, create a `HealthChecker` dependency that probes all downstream services:

```python
class HealthChecker:
    async def check_all(self) -> dict:
        return {
            "groq": await self._check_groq(),
            "redis": await self._check_redis(),
            "database": await self._check_db(),
        }
```

### 3. Type-Safe Dependency Protocols

Use Python `Protocol` classes to define the interface a dependency must satisfy:

```python
class InferenceClient(Protocol):
    async def generate(self, prompt: str, **kwargs) -> dict: ...

# Both of these satisfy the protocol:
class GroqInferenceClient:
    async def generate(self, prompt: str, **kwargs) -> dict: ...

class MockInferenceClient:
    async def generate(self, prompt: str, **kwargs) -> dict: ...
```

This makes it explicit what the handler expects, regardless of the implementation.

### 4. Dependency Graph Validation at Startup

Write a startup check that ensures all dependencies resolve without cycles:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate dependency graph
    for route in app.routes:
        for dep in route.dependencies:
            assert dep is not None, f"Unresolved dependency in {route.path}"
    yield
```

---

## Interview Questions

### Beginner

1. **What is dependency injection?** Explain it without using the word "inject."
   > Answer: It means a function declares what objects it needs, and something else provides them -- instead of the function creating them itself.

2. **What does `@lru_cache` do on a dependency function?**
   > Answer: It ensures the function runs only once. All subsequent calls return the cached result, making it a singleton.

### Intermediate

3. **Why use `Depends()` instead of just importing and calling the function directly?**
   > Answer: `Depends()` enables override for testing, automatic resolution of sub-dependencies, and framework-managed lifecycle. A direct call cannot be overridden without monkeypatching.

4. **What is the difference between a `yield` dependency and a regular one?**
   > Answer: A `yield` dependency has a setup phase (before yield) and a cleanup phase (after yield). It runs cleanup after the request completes. Useful for database sessions, file handles, etc.

5. **How would you test an endpoint that requires authentication without providing real credentials?**
   > Answer: Override the auth dependency with a function that always returns True: `app.dependency_overrides[verify_auth] = lambda: True`

### Advanced

6. **Your service has 4 workers and a `@lru_cache` settings dependency. How many Settings objects exist in memory?**
   > Answer: 4 -- one per worker process. `@lru_cache` is per-process, not per-server.

7. **A dependency calls an external config service synchronously. What happens under load?**
   > Answer: It blocks the async event loop. All concurrent requests are stalled until the sync call completes. This causes cascading timeouts under load. Fix: use an async HTTP client.

8. **How would you implement a per-request dependency that generates a correlation ID and propagates it through all downstream service calls?**
   > Answer: Create a dependency function (no cache) that generates a UUID. Pass it to the handler and include it in outbound request headers. Use a context variable (contextvars.ContextVar) if the ID needs to be available deep in the call stack.
