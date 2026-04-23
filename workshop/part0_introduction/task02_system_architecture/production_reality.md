# Production Reality — Lesson 0.2 System Architecture Tour

> The three-service split is a design choice with real teeth. It looks clean in the architecture diagram, but every arrow is a failure mode, every box is a deployment target, and every shared dependency is a version-skew hazard. Here's what actually goes wrong, and what senior engineers do about it.

## What breaks at scale

### 1. Static service URLs

**The failure mode:** `api_gateway` reads `settings.model_service_url = "http://localhost:8001"` from `.env`. Works in dev. In Kubernetes, the model-service pod's IP changes every restart — the gateway keeps hitting a dead IP for up to `settings.model_service_url`'s TTL (forever, if httpx doesn't re-resolve DNS).

**In production:** we replace static URLs with DNS-based service discovery:
- Kubernetes: `http://model-service.prodigon.svc.cluster.local:8001` — the cluster DNS resolver handles pod churn.
- Consul / Eureka / etcd: a service registry the client queries before each call (or caches for ~30s).
- AWS Cloud Map / App Mesh: L7 service mesh does this for you.

**What senior engineers do:**
- Pass **DNS names, not IPs**, and let httpx use `http_client.AsyncClient` in a way that re-resolves.
- Add a **health-check ping** to every outbound service call's hot path, so a dead backend trips a circuit breaker fast.
- In `shared/http_client.py`, plan for the evolution from URL-string → resolver function → service-mesh sidecar.

### 2. Retry storms and cascading failure

**The failure mode:** `model_service` gets slow (Groq is degraded, say 5s per request instead of 500ms). `api_gateway`'s default httpx timeout is 30s, so each request blocks a gateway worker for 5s. Gateway's connection pool fills. Gateway latency spikes. Frontend retries. Now you have a **retry storm** — the gateway is amplifying load on a service that's already struggling.

**What senior engineers do:**
- **Tighter timeouts upstream than downstream.** If model_service's own call to Groq has a 30s timeout, the gateway's call to model_service should be 5-10s — never 30s.
- **Circuit breakers.** After N failures in T seconds, stop calling the downstream entirely for a cooldown window. Return a fast 503 to the client instead of blocking.
- **Jittered exponential backoff** on retries — and never retry on timeouts that aren't clearly transient.
- **Bulkheads.** Dedicate a connection-pool subset per downstream so one slow service can't starve the others.

`shared/http_client.py` today has none of these. Task 8 (Caching & Load Balancing) adds caching; a real production version would add a circuit breaker next.

### 3. Version skew across services

**The failure mode:** you add a field to `shared/schemas.py::GenerateResponse`. You deploy `model_service` (which now returns the new field). `api_gateway` is still on the old `shared/`, its Pydantic model rejects the unknown field — every request fails with a parse error.

**In production:** this is the single most common failure mode of microservices. It's also silent: the deploy looks green until traffic hits the new path.

**What senior engineers do:**
- **Backwards-compatible schemas only.** Add optional fields, never rename, never change types. Deprecate for at least two deploy cycles before removing.
- **Pydantic `extra = "ignore"` on inbound DTOs.** Unknown fields pass through silently instead of crashing.
- **Schema versioning in the URL** (`/api/v1/`, `/api/v2/`) so old and new clients can coexist.
- **Contract tests in CI.** `api_gateway`'s test suite pins a snapshot of `model_service`'s responses; a breaking change in `shared/` fails CI, not production.
- **Pin `shared/` as a versioned package.** In a real monorepo, each service's dependencies include `prodigon-shared==1.4.2`, and rollouts upgrade it service-by-service.

### 4. The shared DB as a blast radius

**The failure mode:** the baseline has one Postgres. Today, `chat`, `users`, and `batch_jobs` live there peacefully. Tomorrow, someone adds a `user_analytics` table with a huge insert rate. Postgres I/O saturates. Every service sharing the DB slows down — even the ones that have nothing to do with analytics.

**What senior engineers do:**
- **Partition by ownership.** Every table has exactly one service that writes it. Our baseline already does this (gateway owns `chat_*`, worker owns `batch_jobs`). The partitioning discipline is what lets us physically split the DB later without a data migration nightmare.
- **Separate read replicas per workload.** Analytics reads off a replica, transactional writes hit primary.
- **Row-level locks, not table locks.** `SELECT FOR UPDATE SKIP LOCKED` on `batch_jobs` (the queue) is safe only because it's a row-level lock. A table-level `LOCK TABLE` here would serialize all workers.
- **Plan the extraction path.** "If `batch_jobs` grew 100x, we'd move it to its own Postgres, and the only code change is `shared.db.get_worker_engine()`." Write that plan down; it's an architectural decision record (ADR).

## What fails in production

### The 3 AM cascading timeout

Groq returns 503s for 10 minutes. `model_service` retries each request 3 times (30s × 3 = 90s). `api_gateway` has a 30s timeout per call to model_service — but its frontend clients retry on 500, and every retry lands on a different gateway pod with a full connection pool. Within 60 seconds:

- Every gateway pod is blocked on model_service
- Every model_service pod is blocked on Groq
- New `/chat/sessions` requests — which don't touch Groq at all — are rejected because gateway's worker pool is starved

**The fix** is almost never "more workers." It's shorter timeouts, circuit breakers, and a fast-fail path that doesn't compete for the same connection pool as the slow path.

### The quiet version-skew bug

Friday afternoon. Someone deploys `model_service` with a new `top_p` parameter in the Groq call. The new code uses `settings.default_top_p = 0.9` — but `default_top_p` was added to `shared/config.py` in the same commit.

Gateway wasn't redeployed. Gateway still pins the old `shared`. Gateway's `Settings.model_validate` succeeds (the field is new, it just doesn't read it). But during a gateway → model_service HTTP call, the request schema mismatches because `GenerateRequest` on the gateway side doesn't have `top_p` and Pydantic's defaults fill in `0.0` — producing garbage completions for 48 hours until someone notices.

**The root cause** isn't the code. It's the absence of a **schema contract test** that would have caught it in CI.

### The worker that never died

A `worker_service` pod starts a long inference call. It's killed mid-call (K8s rolling deploy). The `batch_jobs` row still has `status='running'` and `locked_by='pod-7f3'`. No other worker picks it up because `SKIP LOCKED` respects the existing lock.

**What senior engineers do:**
- **Heartbeat + lease timeout.** Workers write `locked_at=NOW()` on claim; a janitor job releases rows with `locked_at < NOW() - INTERVAL '10 minutes'`.
- **Idempotent processing.** If a job might be retried after a pod death, the processing logic must tolerate that (e.g., append `results` keyed by prompt index, don't overwrite).
- **Graceful shutdown.** Catch SIGTERM, finish the current job or release the lock, then exit.

The baseline doesn't implement heartbeats. Task 8 adds them when we talk about resilient queues.

## Senior engineer patterns

### Pattern 1 — The contract-first service boundary

Every service-to-service call is defined by a Pydantic schema in `shared/schemas.py`. That schema is the contract — not the implementation, not the docstring, the *schema*. If you can't roundtrip the schema through JSON without losing data, you don't have a contract.

In production, evolve this to OpenAPI specs checked into the repo and enforced by CI (`schemathesis` generates client tests from the spec).

### Pattern 2 — Outbound retries, inbound idempotency

Two complementary halves of the same design:
- **Every outbound HTTP call has a retry policy** (bounded, jittered, with a circuit breaker).
- **Every inbound endpoint is idempotent** (safe to call twice with the same request ID).

Together these make network failures recoverable. Without both, you get duplicate charges, duplicate messages, duplicate job submissions.

### Pattern 3 — "Services own tables, not databases"

The baseline intentionally shares one Postgres across three services, but it treats each table as owned by exactly one service. That's the difference between a **shared database** (OK) and a **shared schema** (dangerous).

When you want to extract a service to its own DB later, you already know which tables go with it. The migration is a schema move, not a cross-team archaeological dig.

### Pattern 4 — The "synthetic transaction" health check

Don't just check `/health` returns 200. Health-check the full dependency chain:

```python
# api_gateway /health/deep
- Can I open a DB connection and SELECT 1?      → postgres
- Can I reach model_service /health?            → model path
- Can I reach worker_service /health?           → worker path
- Can I reach groq's /models endpoint?          → upstream API key valid
```

Fail `/health/deep` if any dependency is red. Kubernetes stops routing traffic to broken pods *before* a user sees an error.

## Monitoring needed

| Signal | Why it matters | Where it fires first |
|---|---|---|
| **Inter-service request rate + p50/p95/p99 latency** | Detects slow backends before they cascade | Gateway logs (outbound calls) |
| **Circuit breaker state transitions** | "Closed → Open" is the canary for upstream distress | Structured log event, alerted |
| **Job queue depth** (`SELECT COUNT(*) FROM batch_jobs WHERE status='pending'`) | Backlog = consumers too slow or inbound spike | Prometheus gauge scraped every 15s |
| **Version hash per service at startup** | Version skew detection across replicas | Logged at boot, compared in dashboard |
| **DB connection pool saturation per service** | Pool exhaustion → random 500s under load | SQLAlchemy pool events |
| **`shared/` package version per service** | `prodigon-shared==1.4.2` on gateway vs `1.4.3` on worker | Deploy-time metric |

## Common mistakes

1. **Calling `model_service` directly from the frontend.** `:8001` is not public. If you think you want this, add a new route on the gateway.
2. **Putting FastAPI-specific code in `shared/`.** `shared/` must be importable from a pure Python script. Route handlers, `Depends()`, `APIRouter` — none of those belong in `shared/`.
3. **Two services writing the same table.** If gateway and worker both write to `batch_jobs`, you've created a distributed-transaction problem. Pick one owner.
4. **Using the Postgres queue for everything.** It works because the baseline has <1 job/sec. Do not assume it scales to millions. Task 8 migrates to a real broker when the scale demands it.
5. **Retries without idempotency.** If `ServiceClient.post` retries a non-idempotent POST on failure, you can create the same job twice. Always pair retries with a request ID.
6. **Ignoring the frontend as a failure mode.** The gateway's job includes serving a sensible error to the frontend. If `/generate` fails, return `{error: {code: "model_unavailable", retry_after_ms: 5000}}`, not a 500 with a stack trace.

## Interview-style questions

1. **Why is the Postgres-as-queue pattern OK in the baseline but an anti-pattern at scale?**
   *Plain Postgres handles ~thousands of competing-consumer polls/sec on a well-tuned instance — fine for human-submitted batches. At millions of events/sec the polling turns into a table scan, vacuum falls behind, and contention on the row locks becomes the bottleneck. Switch to Redis Streams / Kafka when poll rate or throughput crosses that threshold.*

2. **If `model_service` goes down, which endpoints still work and which fail?**
   *`/health`, `/chat/sessions` (CRUD), `/jobs` POST/GET still work — none of them call model_service synchronously. `/api/v1/generate`, `/api/v1/generate/stream` fail immediately with a 503. Background workers start timing out on Groq calls and accumulating pending jobs. Graceful degradation in action.*

3. **You see gateway request latency spike to p99 = 30s. What's your first hypothesis?**
   *A downstream service (likely model_service or Groq) is slow and the gateway's timeout is 30s, so every request is hitting that ceiling. Check: `model_service` latency first, then Groq dashboard. Fix: tighten the gateway's outbound timeout and add a circuit breaker.*

4. **`shared/` is deployed to model_service on v1.5 and to api_gateway on v1.4. What breaks first, and how do you detect it?**
   *A request that uses a field added in v1.5 fails to parse on the gateway side. Detection: log the `shared` package version at each service's startup, emit as a metric, and alert on inequality across services. Prevention: pin `shared` as a versioned dependency and enforce "deploy consumers before producers" in CI.*

5. **Why does the baseline put authentication on the gateway instead of every service?**
   *Authentication is expensive (JWT validation + role lookup per request) and duplicating it in every service means N places to update when the auth policy changes. Centralizing at the edge keeps internal services fast and the auth surface small. The cost: network isolation becomes a correctness property — if `:8001` ever reaches the internet, the security model collapses.*

6. **How would you split the shared Postgres if `batch_jobs` grew 100x?**
   *Because `batch_jobs` is owned only by `worker_service`, move it: (1) spin up a dedicated Postgres for the worker, (2) run Alembic migrations against it, (3) switch `worker_service.config.DATABASE_URL` to the new instance, (4) dual-write for one deploy cycle to verify, (5) backfill, (6) cut over, (7) drop the table from the original DB. Gateway never needs to know.*

## Further reading

- [Release It! — Michael Nygard](https://pragprog.com/titles/mnee2/release-it-second-edition/) — the canonical book on circuit breakers, bulkheads, and cascading-failure patterns
- [The Tanenbaum-Torvalds Debate](https://www.oreilly.com/openbook/opensources/book/appa.html) — the original monolith vs microkernel argument, still relevant
- `architecture/system-overview.md` — the baseline's architecture in full detail
- `architecture/backend-architecture.md` — service-by-service breakdown
- `architecture/design-decisions.md` — ADRs covering service boundaries, queue choice, and schema sharing
- Part I Task 2 (Microservices vs Monolith) — quantifies the trade-offs we've described qualitatively here
- Part II Task 8 (Load Balancing & Caching) — graduates the Postgres queue to Redis
