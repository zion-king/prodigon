# Lesson 0.5 — Production Reality Check

The baseline's persistence, config, and observability layers are clean, typed, and work on a laptop. That is where most tutorials stop. This document covers what actually goes wrong once the system has real users, real traffic, and real operations on call.

---

## What breaks at scale

### Connection pool exhaustion

`baseline/shared/db.py` uses `pool_size=5, max_overflow=10`. That is 15 connections per process.

At N replicas per service × M services:
```
pool_size=5, max_overflow=10, per process
× 4 gateway replicas
× 2 worker replicas
= 90 Postgres connections in normal operation, 150+ under burst
```

Default Postgres `max_connections` is 100. You exhaust it before your first horizontal scaling event.

**Fixes (in order):**
1. Put **pgBouncer in transaction-pooling mode** between services and Postgres.
2. Reduce per-process `pool_size` and let pgBouncer multiplex.
3. Make sure connections are being **released** — any route that forgets `async with` leaks them.

### Log volume at scale

A JSON log line is ~300–500 bytes. At 10k rps with 5 log lines per request, you are shipping ~25 MB/s per replica. That blows through most logging tier budgets in a weekend.

**Fixes:**
- Sample health/metrics paths **before** they hit the aggregator (drop them in middleware).
- Demote noisy INFO logs to DEBUG; promote to INFO only what you would actually alert on.
- Rate-limit chatty loops (e.g. polling workers) with `structlog.throttle` or a simple counter.

### N+1 queries on chat history

```python
session = await db.get(ChatSession, session_id)
for msg in session.messages:   # lazy-loaded, one query per access in async
    ...
```

The `messages` relationship in `shared/models.py` is lazy by default. Accessing it from an async context fires an implicit I/O call per attribute access — an N+1 query storm.

**Fixes:**
- `selectinload(ChatSession.messages)` for 1-to-many — emits two queries (sessions, then messages WHERE session_id IN (...)).
- `joinedload` for to-one relationships — one query with a JOIN.
- Add a linting rule in CI that flags lazy loads in async handlers.

---

## What fails in production

### Alembic autogenerate misses things

The classic blind spots:
- **Index changes on existing columns** — autogenerate often drops and recreates instead of emitting `ALTER`. Downtime on a 100M-row table.
- **Postgres enum additions** — requires `ALTER TYPE ... ADD VALUE`, which cannot run inside a transaction on older Postgres. Autogenerate does not know this.
- **Constraint renames** — autogenerate drops the old and adds a new, losing referential integrity briefly.
- **Partial indexes, expression indexes** — often missed entirely; compare `compare_type=True` in `env.py` does not cover expressions.
- **Server defaults computed differently** — `server_default=func.now()` and `server_default=sa.text("now()")` look identical but render different DDL; autogenerate may flag a false diff every run.

**Rule:** every generated migration is a **draft**. Read it, diff it against intent, hand-edit when necessary.

### Schema drift between environments

Developer A adds a column locally and forgets to commit the migration. The code merges. Staging breaks on deploy. Production breaks worse.

**Fix:** CI job runs:
```bash
alembic -c baseline/alembic.ini upgrade head
alembic -c baseline/alembic.ini check   # fails if models and head disagree
```

This single check catches 90% of migration-related production outages.

### Secret rotation requires a pod restart

`BaseServiceSettings` is effectively read once at import. `@lru_cache` in the dependency layer caches the instance. When Vault/KMS rotates `GROQ_API_KEY`, every running pod continues using the stale value until it restarts.

**Tradeoffs:**
- Accept the restart model (requires rolling-restart automation on rotation events).
- Front secrets with a fetcher that has its own TTL (adds latency to first request after TTL expiry).
- Use a sidecar (Vault Agent) that writes rotated secrets to a tmpfs; main process reads the file. Restart-free but complex.

Production teams usually pick restart model + rotation automation. Simpler, less surface area.

### Error message leakage

```python
except Exception as e:
    raise HTTPException(500, str(e))   # NO
```

`str(e)` from a SQLAlchemy error can contain:
- The full SQL statement including bound parameters
- File paths revealing your deploy structure
- Driver internals hinting at versions

The `AppError.message` abstraction in `shared/errors.py` exists exactly to prevent this. Raise a typed error with a sanitized message; log the raw exception with `exc_info=True` for internal consumption.

---

## Senior engineer patterns

- **One engine per process, created lazily.** `get_engine()` in `shared/db.py` already does this. Do not build engines in module scope — it breaks test isolation.
- **Never `create_all()` against a real database.** Migrations are the contract. `create_all` is acceptable only in unit tests against an ephemeral SQLite.
- **Every migration is reversible or explicitly irreversible.** A `downgrade()` that raises `NotImplementedError` is better than a silent incorrect downgrade. The initial baseline migration has a proper downgrade; the pattern should continue.
- **`request_id` is sacred.** Bind it in middleware, never overwrite it, propagate it as a header on every outbound HTTP/gRPC call, log it in the worker when dequeuing a job. One request = one trace = one grep.
- **Typed errors, never strings.** If you catch an exception you cannot classify, wrap it: `raise InferenceError("upstream failed") from e`. The `from e` preserves the original traceback for logs without exposing it to clients.
- **Eager load by default in async.** Lazy relationships are a footgun in `asyncio`. Consider setting `lazy="raise"` on relationships to force explicit `selectinload` calls.
- **Commit early, commit small.** One logical change per migration. Don't bundle "add column + rename table + drop index" in a single revision — you cannot bisect a failure.

---

## Monitoring needed

At minimum, per service:

- **DB connection pool utilization** — `engine.pool.size()`, `engine.pool.checkedout()`. Alert when checked-out > 80% of max for more than a minute.
- **Slow query log** — Postgres `log_min_duration_statement=200ms`. Surface the top slow statements daily.
- **Log volume by level** — sudden spike in ERROR level is a page; sudden drop means something stopped logging (often a bigger problem).
- **Migration drift** — a metric emitted by the gateway at startup comparing `alembic current` vs `alembic heads`. If they differ, alert.
- **Settings divergence** — log the hash of the loaded settings at startup. If one pod has a different hash than its peers, someone rolled bad config.
- **Exception rate by `error_code`** — grouped by the `AppError.error_code` field. A spike in `INFERENCE_ERROR` is a model-side problem; a spike in `SERVICE_UNAVAILABLE` is a network or downstream problem. The code distinguishes them cleanly.

---

## Common mistakes

1. **`Base.metadata.create_all()` in production startup.** Skips migration history, breaks on schema changes, hides drift.
2. **Building the engine at module import.** Forces env vars to be set before any test can run. Use lazy initialization.
3. **`expire_on_commit=True` in async.** Silent I/O errors on attribute access after commit.
4. **Mutable default in a model column.** `default=[]` is shared across instances. Use `default=list` (the callable) — the baseline already does.
5. **Logging the exception twice.** Once in the handler, once in a catch-all. Log it where you catch it; propagate a typed error upward.
6. **Inline credentials in `alembic.ini`.** `sqlalchemy.url` should be empty — `env.py` pulls from `DATABASE_URL`.
7. **Forgetting `index=True` on FK columns.** Every FK benefits from an index; the baseline has them on `user_id`, `session_id`, `status`. A missed index shows up as a 30-second query after one week of data.
8. **Writing tests that hit the real engine.** Tests should use a fresh ephemeral database (pytest-asyncio + test container, or SQLite with compatible types).

---

## Interview-style questions

1. **Why is `expire_on_commit=False` the default choice in async SQLAlchemy?** What goes wrong with `True`, and what is the tradeoff you accept by setting it to `False`?

2. **An engineer merges a PR that adds a column but forgets the Alembic migration. What detects this, and where in CI should it run?**

3. **Your service has `pool_size=10, max_overflow=20` and runs 8 replicas. Postgres `max_connections=100`. You scale to 12 replicas and Postgres starts rejecting connections. Walk through two different fixes and their tradeoffs.**

4. **A client reports seeing internal SQL in a 500 response. Trace the path the error took, and describe where the leak happened and how the error hierarchy prevents it.**

5. **You have a chat history endpoint that loads a `ChatSession` and iterates over `session.messages` to render them. Under load, p99 latency is terrible. Why, and what is the single-line fix?**

6. **Your application reads `GROQ_API_KEY` via `BaseServiceSettings`. Ops rotates the key in Vault. Nothing breaks for two hours, then everything fails. Why, and what are two ways to fix it?**

7. **A developer writes `logger.info(f"processing user {user.email}")`. What is wrong with this line in a production structured-logging pipeline, even before considering PII?**

8. **Alembic autogenerate produces a migration that drops and recreates an index. The table has 500M rows. What do you do?**

9. **A worker is stuck on a job. You have the `request_id`. Walk through exactly how you would trace the request end-to-end using the baseline's observability.**

10. **The baseline uses VARCHAR for `batch_jobs.status` with application-level validation. When would you switch to a Postgres ENUM, and what is the migration pain?**

---

## Cross-references

- Engine/session **lifecycle** (when it's built, when it's disposed): [`../task03_lifecycle_and_di/`](../task03_lifecycle_and_di/)
- Where `request_id` is **bound into logs**: [`../task04_request_flows/`](../task04_request_flows/)
- Part II (scalability) revisits pool sizing, caching layer in front of the DB, and log sampling.
- Part III (security) revisits secret rotation, PII in logs, and error-message sanitization.
