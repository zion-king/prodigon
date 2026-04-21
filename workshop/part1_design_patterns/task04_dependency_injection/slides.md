# Slides: FastAPI Dependency Injection for AI Systems

**Duration:** ~30 minutes
**Audience:** Engineers building or maintaining AI services

---

## Slide 1: Title

**FastAPI Dependency Injection for AI Systems**

Why DI is the difference between a prototype and a production service.

---

## Slide 2: The Problem

A typical AI endpoint without DI:

```python
@app.post("/generate")
async def generate(request: GenerateRequest):
    api_key = os.environ["GROQ_API_KEY"]       # config reading
    client = Groq(api_key=api_key)             # client creation
    key = request.headers.get("X-API-Key")     # auth checking
    if key != os.environ["SERVICE_API_KEY"]:   # more config reading
        raise HTTPException(401)
    result = client.chat.completions.create(...)  # business logic
    return result
```

This handler does 4 different jobs. Testing it requires a real API key, a running service, and correct environment variables.

---

## Slide 3: What Is Dependency Injection?

**Definition:** A pattern where objects receive their dependencies from the outside instead of creating them internally.

| Approach | Code | Testable? |
|----------|------|-----------|
| **Hardcoded** | `client = Groq(api_key=os.environ["KEY"])` | No |
| **Injected** | `def handler(client=Depends(get_client))` | Yes |

The handler says "I need a client" and the framework provides one.

---

## Slide 4: FastAPI's Depends() System

Three building blocks:

1. **Dependency function** -- returns what a handler needs
2. **`Depends()`** -- declares a dependency in a handler signature
3. **`dependency_overrides`** -- swaps dependencies for testing

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()

@app.get("/health")
async def health(settings=Depends(get_settings)):
    return {"service": settings.service_name}
```

---

## Slide 5: Dependency Trees

Dependencies can depend on other dependencies:

```
get_settings()
    |
    v
get_groq_client(settings)
    |
    v
get_model_manager(client, settings)
    |
    v
route_handler(manager)
```

FastAPI resolves the entire chain automatically. You declare the leaf; the framework walks the tree.

---

## Slide 6: Diagram -- Baseline Model Service

```
                 +------------------+
                 |  HTTP Request    |
                 +--------+---------+
                          |
                 +--------v---------+
                 | /inference route  |
                 |   Depends():     |
                 |   - model_mgr    |
                 |   - settings     |
                 +--------+---------+
                          |
              +-----------+----------+
              |                      |
    +---------v--------+   +---------v--------+
    | get_model_manager|   | get_settings     |
    | (module global)  |   | (@lru_cache)     |
    +--------+---------+   +---------+--------+
             |                       |
    +--------v---------+   +---------v--------+
    | ModelManager      |   | Environment Vars |
    | (created in       |   | / .env file      |
    |  lifespan)        |   +------------------+
    +--------+----------+
             |
    +--------v---------+
    | GroqInference    |
    | Client           |
    +------------------+
```

---

## Slide 7: Live Demo -- The Tightly Coupled Version

Open `tightly_coupled.py`. Identify:

- 3 different `os.environ` calls
- Groq client created inside the handler
- Auth check mixed into business logic
- "How would you test this without a real API key?" (You cannot.)

---

## Slide 8: Live Demo -- The Refactored Version

Open `well_structured.py`. Show:

1. `Settings` class -- all config in one place
2. `get_settings()` -- cached singleton
3. `get_groq_client()` -- depends on settings
4. `verify_api_key()` -- auth as dependency
5. Route handler -- only business logic remains

**Key line:**
```python
async def generate(
    request: GenerateRequest,
    settings: Settings = Depends(get_settings),
    client: Groq = Depends(get_groq_client),
    _auth: bool = Depends(verify_api_key),
):
```

The handler signature IS the documentation of its dependencies.

---

## Slide 9: Testing with Overrides

The payoff -- testing without real services:

```python
# Override: use test settings
app.dependency_overrides[get_settings] = lambda: Settings(
    groq_api_key="fake",
    api_key="test-key",
    service_name="test",
)

# Override: mock the Groq client
app.dependency_overrides[get_groq_client] = lambda: mock_client

# Override: skip auth
app.dependency_overrides[verify_api_key] = lambda: True
```

One line to swap each dependency. No monkeypatching. No environment manipulation.

---

## Slide 10: Scope Patterns

| Pattern | When Created | When Destroyed | Use Case |
|---------|-------------|----------------|----------|
| `@lru_cache` | First call | Never (process lifetime) | Settings |
| Module global + lifespan | App startup | App shutdown | Model clients |
| Plain function | Every call | After call | Request IDs |
| `yield` function | Request start | Request end | DB sessions |

Choose the scope that matches the lifetime of the resource.

---

## Slide 11: The Baseline Pattern

All three services follow the same DI structure:

```
dependencies.py:
    get_settings()       -- @lru_cache singleton
    init_dependencies()  -- called from lifespan
    get_<resource>()     -- returns initialized object

main.py:
    lifespan()           -- calls init_dependencies()

routes/*.py:
    handler(x=Depends(get_<resource>))
```

This is the pattern you should use for any new service.

---

## Slide 12: Common Mistakes

1. **Creating expensive objects per-request** -- no caching on client factory
2. **Circular dependencies** -- A depends on B depends on A
3. **Heavy computation in dependency functions** -- blocks the event loop
4. **Forgetting cleanup** -- use `yield` for resources that need closing
5. **Not clearing overrides in tests** -- state leaks between test cases

---

## Slide 13: Benefits Summary

| Before DI | After DI |
|-----------|----------|
| Cannot test without real API | Mock everything in one line |
| Config scattered in handlers | One Settings class |
| Changing provider = editing every handler | Change one dependency function |
| Auth logic duplicated | One reusable dependency |
| No way to run locally without keys | USE_MOCK flag in settings |

---

## Slide 14: When NOT to Use DI

- Very simple scripts (single-file, no tests needed)
- Performance-critical hot paths where function call overhead matters
- When the dependency graph is trivial (one config, one handler)

For any service that will be maintained by a team, tested in CI, or run in production: always use DI.

---

## Slide 15: Hands-On Lab

**Your turn.** Open `lab/starter/refactor_steps.py` and complete the 4 `YOUR CODE HERE` sections:

1. Create `get_settings()` with `@lru_cache`
2. Create `get_groq_client()` depending on settings
3. Create `verify_api_key()` as an auth dependency
4. Wire all three into the route handlers

Check against `lab/solution/well_structured.py` when done.

Time: 30 minutes

---

## Slide 16: Key Takeaways

1. DI means **declaring what you need** instead of creating it yourself
2. FastAPI's `Depends()` makes DI simple and explicit
3. `dependency_overrides` is the testing superpower
4. Use `@lru_cache` for singletons, `yield` for request-scoped resources
5. The handler signature documents its dependencies -- keep it clean
