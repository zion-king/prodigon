# Lab: Refactoring a Tightly-Coupled AI Service to Use Dependency Injection

## Problem Statement

You have inherited a working but poorly structured FastAPI service that performs AI inference using the Groq API. The code works, but it is:

- **Impossible to test** without a real API key
- **Rigid** — changing the model provider means rewriting route handlers
- **Fragile** — configuration is scattered across the codebase
- **Insecure** — auth logic is mixed into business logic

Your job: refactor it to use FastAPI's dependency injection system, making it testable, flexible, and production-ready.

---

## Files

| File | Purpose |
|------|---------|
| `starter/tightly_coupled.py` | The "bad" version. Read it first to understand the anti-patterns. |
| `starter/refactor_steps.py` | Partially refactored. Fill in the `YOUR CODE HERE` sections. |
| `solution/well_structured.py` | Complete solution. Compare after you finish. |
| `solution/test_with_overrides.py` | Tests that demonstrate dependency override power. |

---

## Step-by-Step Tasks

### Step 0: Read the Bad Version (5 min)

Open `starter/tightly_coupled.py` and identify these problems:

1. Where is configuration read? (Hint: scattered `os.environ` calls)
2. Where is the Groq client created? (Hint: inside the route handler)
3. How would you test `/generate` without a real Groq API key? (Hint: you cannot)
4. Where is the auth check? (Hint: hardcoded inline in the handler)
5. What happens if `GROQ_API_KEY` is missing? (Hint: runtime crash on first request)

Write down at least 3 specific problems before moving on.

### Step 1: Extract Configuration into Injectable Settings (10 min)

Open `starter/refactor_steps.py`. The `Settings` class is already provided:

```python
class Settings(BaseSettings):
    groq_api_key: str = ""
    default_model: str = "llama-3.3-70b-versatile"
    api_key: str = "dev-key-123"
    service_name: str = "inference-service"
    model_config = {"env_file": ".env", "extra": "ignore"}
```

**Your task:** Create the `get_settings()` dependency function.

Requirements:
- Use `@lru_cache` so settings are loaded once
- Return a `Settings` instance
- The function signature should be compatible with `Depends()`

### Step 2: Make the Model Client Injectable (10 min)

**Your task:** Create a `get_groq_client()` dependency function.

Requirements:
- Accept `settings` as a parameter using `Depends(get_settings)`
- Return an initialized Groq client (or a mock if `settings.groq_api_key` is empty)
- This creates a **dependency chain**: handler -> client -> settings

### Step 3: Add Auth as a Dependency (10 min)

**Your task:** Create a `verify_api_key()` dependency function.

Requirements:
- Extract the `X-API-Key` header from the request
- Compare it against `settings.api_key` (using `Depends(get_settings)`)
- Raise `HTTPException(403)` if invalid
- Return the validated key (or `True`) on success

### Step 4: Wire Dependencies into Route Handlers (10 min)

**Your task:** Update the route handler signatures to use `Depends()`.

The `/generate` endpoint should:
- Depend on `verify_api_key` (auth gate)
- Depend on `get_groq_client` (model client)
- Depend on `get_settings` (for default model config)
- NOT create any clients or read any config directly

### Step 5: Write Tests Using Dependency Overrides (10 min)

**Your task:** Look at `solution/test_with_overrides.py` for guidance, then try writing your own tests.

Key technique:
```python
# Override a dependency for testing
app.dependency_overrides[get_settings] = lambda: Settings(
    groq_api_key="fake",
    api_key="test-key",
)

# Override the Groq client with a mock
app.dependency_overrides[get_groq_client] = lambda: mock_client
```

Write tests that:
1. Test `/generate` with a mocked model client (no real API calls)
2. Test that missing auth returns 403
3. Test that invalid auth returns 403
4. Test `/health` returns service info from settings

### Step 6: Compare Before and After (5 min)

Put the two versions side by side:

| Aspect | `tightly_coupled.py` | `well_structured.py` |
|--------|---------------------|---------------------|
| Lines to change for new provider | ~15 (route handler) | 1 (dependency function) |
| Test setup needed | Real API key + running service | `dependency_overrides` dict |
| Config validation | None (crash at runtime) | Pydantic validates at startup |
| Auth logic location | Inside business handler | Separate dependency |
| Adding a new endpoint | Copy-paste everything | Add `Depends()` parameters |

---

## Expected Output

After completing the refactoring, you should be able to:

```bash
# Run the well-structured version
uvicorn solution.well_structured:app --port 8000

# Run the tests (no API key needed!)
python -m pytest solution/test_with_overrides.py -v
```

All tests should pass without any real API calls.

---

## Bonus Challenges

1. **Yield dependency with cleanup:** Create a dependency that opens a log file on request start and closes it on request end using `yield`:
   ```python
   async def get_request_logger():
       logger = open("request.log", "a")
       yield logger
       logger.close()
   ```

2. **Scoped dependency:** Create a dependency that generates a unique `request_id` per request (no caching!) and includes it in the response headers.

3. **Dependency tree visualization:** Draw the full dependency graph for the refactored app. Which dependencies are singletons? Which are per-request?

4. **Environment switching:** Add a `USE_MOCK` setting. When true, `get_groq_client()` should return a mock client automatically — no code changes in handlers.
