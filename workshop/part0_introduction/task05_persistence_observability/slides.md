# Lesson 0.5 — Persistence, Config, and Observability

**Slides for 30-minute live delivery.** 17 slides.
Audience: engineers building AI services who have seen the baseline run but have not read every file yet.

---

## Slide 1 — Title

**Persistence, Config, and Observability**
Part 0 — Baseline Introduction (Lesson 5 of 6)

The state layer, and the cross-cutting concerns that every service leans on.

---

## Slide 2 — Where this lesson sits

Lessons 0.1–0.4: the **request path** — gateway, dispatch, inter-service flow.

Lesson 0.5: what the request path **depends on** every time it runs.

- Database (persistence)
- Config (what this process should do)
- Logs (what just happened)
- Errors (how failure propagates)

Boring layers. First to break when the system grows.

---

## Slide 3 — The four shared modules

```
baseline/shared/
  db.py       engine + sessionmaker + get_session
  models.py   ORM classes
  config.py   BaseServiceSettings
  logging.py  structlog setup
  errors.py   AppError hierarchy
```

Rule: if more than one service needs it, it lives in `shared/`.

---

## Slide 4 — The persistence pipeline

```
.env → BaseServiceSettings → DATABASE_URL
     → create_async_engine
     → async_sessionmaker(expire_on_commit=False)
     → get_session (FastAPI dep)
     → route: db: AsyncSession
     → Postgres
```

One chain. Each step does one job.

---

## Slide 5 — SQLAlchemy 2.x async, minimal

```python
engine = create_async_engine(url, pool_pre_ping=True, pool_size=5)
SM = async_sessionmaker(engine, expire_on_commit=False)

async def get_session():
    async with SM() as session:
        yield session
```

Two things to remember:
- One engine per process (lazy-built).
- `expire_on_commit=False` — non-negotiable in async.

---

## Slide 6 — Why `expire_on_commit=False`

Sync default: after `commit()`, attributes auto-refresh on next access.

Async problem: attribute access is sync, but a refresh needs I/O — which needs `await`.
SQLAlchemy cannot sneak an `await` into `.foo`. It raises `ImplicitIOError` or silently blocks.

`expire_on_commit=False` = keep the committed object usable, skip the auto-refresh.
If you need fresh data, call `await session.refresh(obj)` explicitly.

---

## Slide 7 — Alembic: schema truth

**Not** `Base.metadata.create_all()`. Ever. In production.

Workflow:

```
1. Edit shared/models.py
2. alembic revision --autogenerate -m "..."
3. READ the generated file
4. alembic upgrade head
```

The models file is the desired state.
The migration history is the transition log.
Production only changes via migrations.

---

## Slide 8 — What autogenerate can miss

- Index changes on existing columns (drops/recreates instead of ALTER)
- Enum value additions in Postgres
- Constraint renames
- Partial indexes
- Server defaults that got computed differently

Autogenerate is a helper, not a decision-maker. **Always review and often hand-edit.**

---

## Slide 9 — Pydantic Settings: inheritance

```python
class BaseServiceSettings(BaseSettings):
    service_name: str = "unknown"
    environment: str = "development"
    log_level: str = "INFO"
    use_mock: bool = False
    model_config = {"env_file": "../../.env"}
```

Each service subclasses and adds its own fields (API keys, URLs, tuning knobs).

---

## Slide 10 — Why Pydantic Settings over `os.environ`

- Type coercion at startup — a bad env var fails at boot, not at first request.
- Defaults beside the field, not scattered.
- Inheritance — DRY shared fields.
- `.env` auto-loaded. Docker runtime env overrides it.

Fail fast, fail loud, fail at startup.

---

## Slide 11 — structlog: JSON out of the box

```python
logger = get_logger(__name__)
logger.info("generation_complete", model="llama", tokens=412)
```

Emits:
```json
{"event":"generation_complete","model":"llama","tokens":412,
 "level":"info","service":"api-gateway","timestamp":"2026-04-23T09:00:00Z"}
```

Grep-friendly, dashboard-friendly, alert-friendly.

---

## Slide 12 — Correlated logs with `request_id`

Middleware (see Lesson 0.4) binds once per request:

```python
structlog.contextvars.bind_contextvars(request_id=req_id)
```

Every subsequent log line in the route/helper/client inherits it.

One request = one `request_id` = one grep.

This is how you debug at 3 AM.

---

## Slide 13 — The error hierarchy

```
AppError(status_code, error_code)
 ├── ValidationError       (422)
 ├── InferenceError        (502)
 ├── ServiceUnavailableError (503)
 └── JobNotFoundError      (404)
```

A FastAPI exception handler catches any `AppError` and emits a consistent JSON body.

**Rule: never raise bare `Exception` in a route.**

---

## Slide 14 — What the client sees on error

```json
{
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Job not found: abc",
    "request_id": "r-8f3c"
  }
}
```

- Machine-readable `code` for the client.
- Human-readable `message`.
- `request_id` so support can find the server logs.

Never leak `str(exception)` — it can contain SQL, paths, secrets.

---

## Slide 15 — Common mistakes

1. Calling `create_all()` in application startup. (Skips migration history.)
2. Building the engine at module import time. (Breaks tests.)
3. Default `expire_on_commit=True` in async code. (Silent breakage.)
4. `raise Exception("something broke")` in a route. (No status code, leaks internals.)
5. Logging with plain `print()` or f-strings. (Not parseable, no correlation.)
6. Committing `.env` to git. (Just don't.)

---

## Slide 16 — What we did NOT cover yet

- Connection pooling tradeoffs at scale → Part II
- Secret rotation + Vault/KMS integrations → Part III
- Log shipping, retention, sampling → Part II observability
- Tracing (OpenTelemetry) → Advanced

Lesson 0.5 is the foundation. The real pain shows up when you try to scale it.

---

## Slide 17 — Lab + next steps

Lab (30 min, read-along):
1. Inspect the initial Alembic migration and map it to `shared/models.py`.
2. Generate (but don't apply) a migration from a tiny model change, then revert.
3. Raise a custom error from a temp route; observe the 404 + the correlated log line.

Next lesson: **0.6 — Frontend Primer.**
Then Part I: REST vs gRPC, microservice boundaries, streaming.
