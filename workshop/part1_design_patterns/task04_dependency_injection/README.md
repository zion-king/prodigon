# Task 4: FastAPI Dependency Injection for AI Systems

## Overview

Dependency Injection (DI) is one of the most powerful patterns in production AI systems. It determines how your services acquire the objects they need — API clients, configuration, database connections, model loaders — and it directly impacts testability, maintainability, and operational flexibility.

This task teaches DI through FastAPI's `Depends()` system, using real patterns from the baseline AI platform codebase.

---

## Architecture Diagram

```mermaid
graph TD
    subgraph "Model Service — Dependency Graph"
        REQ[Incoming HTTP Request]
        REQ --> ROUTE[Route Handler: /inference]

        ROUTE -->|Depends| GMM[get_model_manager]
        ROUTE -->|Depends| GS1[get_settings]

        GMM --> MM[ModelManager instance]
        MM --> GC[GroqInferenceClient]
        MM --> CFG1[default_model, fallback_model]

        GS1 -->|@lru_cache| SETTINGS[ModelServiceSettings]
        SETTINGS --> ENV[Environment Variables / .env]
    end

    subgraph "Lifespan Initialization"
        STARTUP[App Startup] --> INIT[init_dependencies]
        INIT --> MM
        INIT --> GC
    end

    style REQ fill:#e1f5fe
    style ROUTE fill:#fff3e0
    style SETTINGS fill:#e8f5e9
    style MM fill:#fce4ec
```

```
Request Flow (ASCII version):

  HTTP Request
      |
      v
  Route Handler ---- Depends(get_model_manager) ----> ModelManager
      |                                                     |
      |--- Depends(get_settings) --> Settings (@lru_cache)  |
      |                                  |                   |
      v                                  v                   v
  Response                         .env / OS env       GroqInferenceClient
```

---

## Three-Level Explanation

### Level 1: Beginner — What Is Dependency Injection?

**The restaurant analogy:**

Imagine you are a chef (a route handler). You need ingredients (dependencies) to cook a dish (handle a request).

**Without DI:** You walk out of the kitchen, drive to the farm, pick vegetables, drive back, and then cook. Every chef does this independently. If the farm moves, every chef's code breaks.

**With DI:** You write a list of what you need on a ticket. A runner (the framework) brings you exactly what you need. You just cook.

In code terms:

```python
# WITHOUT DI — the handler creates its own dependencies
@app.post("/inference")
async def run_inference(request: GenerateRequest):
    api_key = os.environ["GROQ_API_KEY"]            # Reading config inline
    client = Groq(api_key=api_key)                   # Creating client inline
    response = client.chat.completions.create(...)    # Using it
    return response

# WITH DI — the handler declares what it needs
@app.post("/inference")
async def run_inference(
    request: GenerateRequest,
    model_manager: ModelManager = Depends(get_model_manager),  # "I need this"
):
    result = await model_manager.generate(prompt=request.prompt)
    return result
```

The handler does not know or care *how* the ModelManager was created, what API key it uses, or whether it is real or fake. It just uses it.

### Level 2: Intermediate — How FastAPI's Depends() Works

FastAPI's DI system is function-based. You write a callable (usually a function), and FastAPI calls it to produce the dependency value.

**Key mechanics:**

1. **Dependency functions** return the object a handler needs:
   ```python
   def get_settings() -> ModelServiceSettings:
       return ModelServiceSettings()
   ```

2. **`Depends()` wires them in** as default parameter values:
   ```python
   @router.get("/health")
   async def health(settings=Depends(get_settings)):
       return {"service": settings.service_name}
   ```

3. **Dependency trees** — dependencies can depend on other dependencies:
   ```python
   def get_model_manager(settings=Depends(get_settings)):
       client = GroqInferenceClient(api_key=settings.groq_api_key)
       return ModelManager(groq_client=client)
   ```

4. **Caching with `@lru_cache`** — prevents re-creation on every request:
   ```python
   @lru_cache
   def get_settings() -> ModelServiceSettings:
       return ModelServiceSettings()  # Created once, reused forever
   ```

5. **Override mechanism for testing:**
   ```python
   # In tests — swap real dependencies for fakes
   app.dependency_overrides[get_settings] = lambda: FakeSettings()
   app.dependency_overrides[get_model_manager] = lambda: MockModelManager()
   ```

**Why this matters for AI systems specifically:**

- Model clients are expensive to create (API connections, token management)
- Configuration determines which model, which API key, which fallback
- Testing AI endpoints without real API calls requires mock injection
- Different environments (dev/staging/prod) need different wiring

### Level 3: Advanced — Production DI Patterns

#### Scope Patterns

| Pattern | Scope | Use Case | Baseline Example |
|---------|-------|----------|------------------|
| `@lru_cache` on function | Singleton (process lifetime) | Settings, config | `get_settings()` |
| Module-level global + init | Singleton (app lifetime) | Model clients, heavy objects | `_model_manager` in init_dependencies |
| Plain function (no cache) | Per-request | Request-scoped auth, tracing context | Auth middleware |
| `yield` dependency | Request with cleanup | DB sessions, temp files | Not in baseline (shown in lab) |

#### The Lifespan + Global Pattern

The baseline uses a two-phase approach:

```python
# Phase 1: Lifespan initializes heavy objects
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_dependencies(settings)  # Creates ModelManager, clients
    yield
    # cleanup here

# Phase 2: Dependency functions return the initialized objects
_model_manager: ModelManager | None = None

def get_model_manager() -> ModelManager:
    if _model_manager is None:
        raise RuntimeError("Not initialized")
    return _model_manager
```

**Why not just create in the dependency function?**
- Model clients need async setup (connection pools)
- Startup failures should crash the app, not the first request
- Cleanup must happen on shutdown (close connections)

#### Comparison with Other DI Approaches

| Approach | Pros | Cons |
|----------|------|------|
| FastAPI `Depends()` | Simple, no magic, testing built in | Framework-specific, no auto-wiring |
| `dependency-injector` library | Full IoC container, declarative | Complex, steep learning curve |
| Manual constructor injection | No framework needed | Verbose, manual wiring |
| Global singletons | Simple | Untestable, hidden coupling |
| Service locator pattern | Flexible | Hides dependencies, hard to trace |

#### Avoiding Circular Dependencies

In a dependency tree, if A depends on B and B depends on A, FastAPI will infinite-loop. The fix is to introduce an interface or restructure:

```
BAD:  get_model_manager -> get_settings -> get_model_manager (circular!)
GOOD: get_model_manager -> get_settings (one direction only)
```

Rule: dependencies should form a Directed Acyclic Graph (DAG).

---

## How the Baseline Codebase Uses DI

### Model Service (`baseline/model_service/app/`)

**`dependencies.py`** — the central wiring module:
```python
@lru_cache
def get_settings() -> ModelServiceSettings:
    return ModelServiceSettings()

def init_dependencies(settings: ModelServiceSettings) -> ModelManager:
    global _model_manager
    if settings.use_mock:
        client = MockGroqClient()
    else:
        client = GroqInferenceClient(api_key=settings.groq_api_key)
    _model_manager = ModelManager(groq_client=client, ...)
    return _model_manager

def get_model_manager() -> ModelManager:
    if _model_manager is None:
        raise RuntimeError("ModelManager not initialized.")
    return _model_manager
```

**`routes/inference.py`** — handler declares its needs:
```python
@router.post("/inference", response_model=GenerateResponse)
async def run_inference(
    request: GenerateRequest,
    model_manager: ModelManager = Depends(get_model_manager),
):
    result = await model_manager.generate(prompt=request.prompt, ...)
    return GenerateResponse(text=result["text"], ...)
```

### API Gateway (`baseline/api_gateway/app/`)

Same pattern with service clients:
```python
def get_model_client() -> ServiceClient:
    if _model_client is None:
        raise RuntimeError("Model client not initialized.")
    return _model_client
```

### Worker Service (`baseline/worker_service/app/`)

Multiple dependencies composed together:
```python
def init_dependencies(settings):
    global _queue, _processor, _model_client
    _queue = create_queue(settings.queue_type)
    _model_client = ServiceClient(base_url=settings.model_service_url)
    _processor = JobProcessor(model_service_client=_model_client, queue=_queue)
```

---

## Key Benefits Summary

| Benefit | Without DI | With DI |
|---------|-----------|---------|
| **Testing** | Need real API keys, real services | Override with mocks in one line |
| **Configuration** | Scattered `os.environ` calls | Centralized, typed, validated |
| **Flexibility** | Hardcoded to one provider | Swap implementations without changing handlers |
| **Readability** | Handler does everything | Handler only does business logic |
| **Startup safety** | Fails on first request | Fails at startup (fail fast) |

---

## Next Steps

1. Complete the **hands-on lab** in `lab/README.md`
2. Review the **slides** in `slides.md` for presentation material
3. Read the **production reality check** in `production_reality.md`
