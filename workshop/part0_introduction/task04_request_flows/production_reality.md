# Production Reality — Lesson 0.4 Request Flows

> Sync, streaming, and job flows each fail in their own particular way.
> Here's the map of where they break, what a senior engineer changes, and
> what to monitor.

## What breaks at scale

### 1. Sync fan-out amplifies upstream latency

**The failure mode:** an endpoint `POST /summarize-thread` takes a list of 20
messages and calls `/api/v1/generate` once per message synchronously. Each
call is 2 s on a good day, 8 s when Groq is slow. So the endpoint's p99 is
`20 × 8 s = 160 s` — well past any sane client timeout.

**In the baseline:** nothing protects you. `ServiceClient` has a 30 s
per-call timeout, but the outer endpoint has no overall budget.

**What senior engineers do:**
- **Fan out with `asyncio.gather`** — 20 parallel calls, p99 becomes
  max(call latency), not sum.
- **Set an overall deadline.** `async with asyncio.timeout(30):` wraps the
  whole endpoint so one slow call doesn't drag the rest.
- **Push the whole operation to a job** if the work is >10 s even under
  ideal conditions. Sync is for interactive latency, not batch.

### 2. SSE connections silently pile up behind a load balancer

**The failure mode:** each SSE response holds a TCP connection open for the
duration of generation — 10–60 s. Behind an nginx or ALB with default
worker_connections = 1024, 1024 concurrent streams and you're out of
connection slots. New requests queue, then 504.

**In the baseline:** no limit on concurrent streams. An attacker who opens
2000 `generate/stream` calls and never reads them can DoS the gateway.

**What senior engineers do:**
- **Cap concurrent streams per IP/user** at the reverse proxy (nginx
  `limit_conn`) or middleware level.
- **Send periodic keep-alive comments** (`: keepalive\n\n`) every 15 s so
  idle proxies don't terminate mid-stream.
- **Use HTTP/2 or HTTP/3 for streams.** One connection multiplexes many
  streams; the "1024 sockets" ceiling disappears.

### 3. The jobs table becomes a long-tail hotspot

**The failure mode:** your app has run for 6 months. The `batch_jobs` table
has 4 million rows, 3.98 million of them `completed`. Every `dequeue()`
runs `SELECT ... WHERE status='pending' ORDER BY created_at ... SKIP LOCKED`
— and Postgres still has to traverse or filter past all the completed rows
unless the index is right.

**In the baseline:** there's an index on `status`, but no archival process.
Eventually every query is slower than it should be.

**What senior engineers do:**
- **Partial indexes** — `CREATE INDEX ... ON batch_jobs (created_at) WHERE
  status = 'pending';`. Index only covers rows you actually query.
- **Archive completed rows** nightly to a `batch_jobs_archive` table or to
  S3/object storage. Keep the live table small.
- **TTL on completed rows** — 30-day retention is typical for operational
  logs.

### 4. Request-ID correlation breaks the moment someone forgets to propagate

**The failure mode:** gateway generates `request_id=abc`, logs it, calls
`model_service`. Someone adds a new microservice `embedding_service` and
calls it from `model_service` via a fresh httpx instance that doesn't copy
the `X-Request-ID` header. Now half the logs for that request are
uncorrelated. You can't find the embedding-related error without knowing
the timestamp within a second.

**In the baseline:** the gateway generates and logs request_ids but does
**not** forward them as outbound headers. Lesson 0.5 closes this loop; for
now it's a deliberate known-gap.

**What senior engineers do:**
- **Bake propagation into the shared HTTP client.** `ServiceClient.post`
  should automatically pull the current request_id from a context var and
  add `X-Request-ID` to every outbound request.
- **Use OpenTelemetry trace headers** (`traceparent`) instead of a custom
  scheme once multiple teams are involved — the standard buys you
  compatibility with every observability vendor.
- **Assert in CI** that every outbound service call includes the header.
  One forgotten call silently destroys correlation.

## What fails in production

### The dropped SSE that nobody notices

A client opens a stream. A network hiccup drops the TCP connection mid-word.
The browser's `EventSource` will **automatically reconnect and retry the
request** — which means a second full generation starts. User ends up with
`"Hello worldHello world"` or two parallel streams if the frontend isn't
careful.

**Detect from the server side:** `ClientDisconnect` / `is_disconnected()`
firing unexpectedly often, coupled with `stream_aborted` log events at
`tokens_sent < 10`. Those are users whose connection died before useful
output.

**Detect from the client side:** `EventSource.onerror` fires — but it
doesn't tell you whether this was a transient drop or a real failure.
Browsers retry by default.

**Senior engineer fix:** use `fetch()` with a ReadableStream instead of
`EventSource` if you don't want auto-retry; disable retry on the server by
including the `retry: 0` SSE directive; or switch to WebSockets if
bidirectional control is needed.

### The worker that crashes mid-job

Worker claims row #42 (status → `running`), starts processing, OOMs.
Kubernetes restarts it. Row #42 is stuck in `running` forever.

**In the baseline:** no recovery. The row is orphaned.

**Production fix — the three options:**
1. **Heartbeat + reaper.** Worker updates `heartbeat_at` every 5 s while
   processing. A cron job resets rows where `status='running' AND
   heartbeat_at < now() - 60s` back to `pending`.
2. **Visibility timeout** (SQS-style). When you claim, you get an exclusive
   lease valid for N seconds. If you don't `ack` by then, the job is
   requeued automatically.
3. **Idempotent jobs + at-least-once.** Make `process(job_id, ...)` safe to
   run twice, then accept that occasional duplicates are better than
   complex recovery.

### The poll-heavy worker that dominates the DB

4 workers × 1 poll/sec × 86400 sec/day = 345,600 queries per day doing
nothing. Fine. Scale to 50 workers and you're at 4.3M queries/day. Still
cheap per query, but now it's the top query in `pg_stat_statements` and
it's making the DBA nervous.

**Fix progression (pick the cheapest that works):**
1. **Raise poll interval when idle.** Exponential backoff: 1 s → 2 s → 4 s
   → ... → 30 s when the queue stays empty. Reset on any claim.
2. **Postgres `LISTEN`/`NOTIFY`.** Workers `LISTEN jobs_channel`; enqueuer
   does `NOTIFY jobs_channel` after commit. Workers wake on a real signal.
   Eliminates polling entirely; Postgres-native.
3. **Dedicated broker** (Redis Streams, RabbitMQ, SQS). Warranted when
   throughput > 100 jobs/sec, ordering requirements are complex, or you
   want fan-out to multiple consumer groups.

### Sync calls with no timeout become a DoS vector

`ServiceClient` sets a 30 s default timeout. Someone writes a new endpoint
that does `httpx.post(...)` directly, forgetting the timeout. Upstream
hangs. The endpoint hangs. The uvicorn worker's event loop has one fewer
slot. Multiply by N — eventually no workers are free.

**Senior engineer patterns:**
- **Ban raw `httpx.post` in routes.** Lint rule: all inter-service calls
  go through `ServiceClient`.
- **Enforce a default timeout at the global httpx level.** `httpx.Timeout`
  applied to a shared client instance is inherited by every call.
- **Kill long-running tasks from the outside.** `asyncio.timeout(N)` at
  the endpoint level is a defense in depth against any single missing
  timeout.

## Senior engineer patterns

### Pattern 1 — Pick the flow by customer-visible latency budget

| Latency the user will tolerate | Pick |
|---|---|
| <1 s, UI freezes if longer | Sync |
| 5–30 s, UI shows "typing…" | Streaming |
| >30 s, user goes to do something else | Jobs |
| >5 min, user won't wait at all | Jobs with notification (webhook/email when done) |

Notice the tension: streaming is where the *perceived* latency is low even
when the *actual* latency is high, because bytes are arriving.

### Pattern 2 — Shared request context, not passed-around request_ids

Rather than passing `request_id` explicitly through every function call,
use `contextvars`:

```python
# middleware
request_id_var.set(request.headers.get("X-Request-ID", str(uuid.uuid4())))
structlog.contextvars.bind_contextvars(request_id=request_id_var.get())

# ServiceClient.post
headers["X-Request-ID"] = request_id_var.get()
```

Every log line and every outbound call automatically carries the id. Zero
plumbing in business logic.

### Pattern 3 — Idempotency keys for job submission

```python
@router.post("/jobs", status_code=202)
async def submit_job(submission: JobSubmission,
                     idempotency_key: str = Header(...)):
    existing = await queue.find_by_idempotency_key(idempotency_key)
    if existing:
        return existing    # same key, same job, no duplicate work
    return await queue.enqueue(submission)
```

Client retries (from network blips, from at-least-once delivery, from
human impatience) become free. Critical once real money or LLM tokens are
at stake.

### Pattern 4 — Backpressure via max_concurrency, not rate limits

A worker processing jobs should be bounded by `max_concurrency` —
"process at most N jobs in parallel." This is per-worker, in-process,
and deterministic. A global rate limit (e.g., 100 jobs/min across the
fleet) is harder to get right because it requires shared state.

Start with `asyncio.Semaphore(N)` inside the processor. Add rate limits
only when you have a concrete upstream that enforces them.

## Monitoring needed

| Signal | Why | Alert when |
|---|---|---|
| **Streaming p99 first-byte latency** | SSE's key UX metric; buffering bugs show up here | > 2 s |
| **`stream_aborted` rate** | Dropped connections; retries; client-side bugs | > 5 % of streams |
| **Jobs queue depth (`pending` count)** | Queue getting ahead of workers | trending up for 10 min |
| **Oldest pending job age** | Workers are stuck or starved | > 5 × expected p99 processing time |
| **Stuck `running` job count** | Worker crashes / missing reaper | > 0 for > 10 min |
| **Sync endpoint p99 latency** | Unbounded upstream; missing timeout | > 30 s |
| **Worker poll rate × idle fraction** | Wasted DB queries | idle > 90 % and poll rate > 1 Hz |
| **`ServiceClient` timeout rate** | Upstream saturation | > 1 % of calls |

The first two are unique to streaming. The middle three are unique to
jobs. The last three apply to all three flows.

## Common mistakes

1. **Using sync for a batch.** 30 prompts in one sync call = a 90 s HTTP
   request that a load balancer will kill.
2. **SSE without keepalive.** Idle proxies close the connection at 60 s
   even if the server is still generating.
3. **`SELECT ... LIMIT 1` without `FOR UPDATE SKIP LOCKED`.** Two workers
   process the same job.
4. **Returning 200 from a job submit.** Callers assume it's done and
   don't poll.
5. **Forgetting `is_disconnected()` checks in streams.** Free tokens for
   people who close the tab.
6. **Global mutable dict as a job store.** Lost on restart. The baseline's
   `InMemoryQueue` is explicitly dev-only; the default is `PostgresQueue`.
7. **No `X-Request-ID` propagation.** Logs become unjoinable across
   services.
8. **Polling frequency hardcoded to 100 ms "for responsiveness".** 10 × the
   DB load for no user-visible benefit; users don't care about 900 ms of
   job latency.

## Interview-style questions

1. **When would you pick streaming over sync, and when over a job?**
   *Streaming when the work is slow (>5 s) AND the user will sit watching the
   output — perceived latency beats actual latency. Sync when the work is
   fast (<2 s) and the user wants the full result before doing anything.
   Jobs when the work is too slow to keep a connection open, or you want
   to decouple submission from execution for cost/throughput reasons.*

2. **Why does the baseline use `FOR UPDATE SKIP LOCKED` in the worker dequeue?**
   *So N workers can poll the same table concurrently without stepping on
   each other. `FOR UPDATE` locks the selected row; `SKIP LOCKED` tells
   concurrent transactions to ignore locked rows rather than waiting.
   Result: each worker claims a unique row, no retries, no contention
   storms.*

3. **A user closes their browser tab during a stream. What happens in each service?**
   *Browser sends TCP FIN. Gateway's `is_disconnected()` goes true; it
   exits `aiter_bytes` and closes the upstream socket. Model service's
   `is_disconnected()` goes true; it exits its event_generator and cancels
   the Groq iterator. Net effect: no more tokens are pulled from Groq, no
   more tokens billed.*

4. **What's the failure mode if a worker crashes after claiming a job but before completing it?**
   *The row is stuck with `status='running'` forever. The baseline doesn't
   recover; production fix is a heartbeat column + reaper, a visibility
   timeout, or idempotent at-least-once semantics.*

5. **How would you correlate logs for a single user request across 3 services?**
   *Gateway generates a `request_id` in its logging middleware. Propagate
   it as `X-Request-ID` on every outbound service call. Each service binds
   the header into structlog's contextvars so every log line carries it.
   Then `grep request_id=abc` across all log sinks finds every line.*

6. **Why is SSE preferred over WebSockets for LLM streaming output?**
   *SSE is one-way (server→client), which is all LLM output needs. It
   works through vanilla HTTP proxies, has native browser support via
   `EventSource`, and is trivially debuggable with `curl -N`. WebSockets
   are required only when bidirectional messaging in one connection is
   needed (e.g., interactive chat where both ends send mid-session).*

## Further reading

- `baseline/api_gateway/app/routes/generate.py` — sync + streaming reference
- `baseline/worker_service/app/services/queue.py` — `PostgresQueue`
- [MDN — Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [Stripe — Idempotency in distributed systems](https://stripe.com/blog/idempotency)
- [Brandur — Transactionally staged job drains](https://brandur.org/job-drain) —
  patterns for Postgres-as-a-queue done well
- Part I Task 1 (REST vs gRPC) — when streaming should move off HTTP
- Part I Task 3 (Batch vs Real-time vs Streaming) — deeper pipeline design
- Lesson 0.5 — adds request_id propagation + metrics
