# Lab 0.2 — Annotate the Request Path

## Problem statement

Given the baseline architecture from the lesson, **trace three real endpoints through the stack**. For each endpoint, list every file the request passes through and every network hop it makes — on the way out to the external service (Groq or Postgres), and on the way back.

This is a read-along exercise. No code to write, no services to restart. Your deliverable is the annotated answer sheet in your own notebook (or a text file).

## Why this exercise

In Lesson 0.4 you'll profile these same three flows under load. Before you can reason about *where* latency lives, you have to know *what* the request actually does. The point of this lab is to build that map with your own eyes, not receive it pre-drawn.

## Prerequisites

- Stack running from Lesson 0.1 (you don't need to call anything — reading the source is enough)
- Your editor open on the `baseline/` directory
- ~30 minutes

## Endpoints to trace

### Endpoint 1 — `POST /api/v1/generate` (synchronous)

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, world"}'
```

**Your task.** For this request, list:

1. Which file on `api_gateway` receives the request?
2. What `shared/` modules does it depend on?
3. Which downstream service does it call, and through what function?
4. What file on `model_service` receives that inter-service call?
5. What external API is called, and how?
6. Every network hop, numbered in order.

### Endpoint 2 — `POST /api/v1/generate/stream` (SSE streaming)

**Request:**
```bash
curl -N -X POST http://localhost:8000/api/v1/generate/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a story"}'
```

**Your task.** Same as above, but pay attention to:

1. How is this different from the sync flow? (hint: the gateway does **not** use `ServiceClient` here — why?)
2. Who is responsible for closing the upstream connection if the client disconnects?
3. What HTTP headers signal "this is a stream, don't buffer me"?

### Endpoint 3 — `POST /api/v1/jobs` (asynchronous / batch)

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"prompts": ["one", "two", "three"]}'
```

**Your task.** This one has **two phases**:

Phase A — submission (the `curl` returns in <100ms):
1. Which file on the gateway receives the POST?
2. Which downstream service and endpoint does it call?
3. What row gets written to Postgres?
4. What HTTP status is returned to the curl client, and what body?

Phase B — background processing (happens after the 202):
1. Which loop picks the job up?
2. What SQL query claims it (exact clause)?
3. For each prompt in the batch, what HTTP call is made and to where?
4. What SQL update finalizes the job?

## Expected output

Write this in your notebook or a scratch file. Below is the answer key — try to produce yours before reading it.

<details>
<summary>Click to reveal answer: Endpoint 1 — /api/v1/generate</summary>

**Files touched:**
- `baseline/api_gateway/app/routes/generate.py` — `generate_text()` handler
- `baseline/api_gateway/app/dependencies.py` — `get_model_client()` provides the `ServiceClient`
- `baseline/shared/http_client.py` — `ServiceClient.post()` wraps the httpx call
- `baseline/shared/schemas.py` — `GenerateRequest`, `GenerateResponse` (DTOs on both sides)
- `baseline/shared/errors.py` — `ServiceUnavailableError` raised on connect/timeout
- `baseline/shared/logging.py` — structured log entries on success and failure
- `baseline/model_service/app/routes/inference.py` — handler receives `/inference`
- `baseline/model_service/app/services/*` — model adapter, cache, retry logic

**Network hops:**
1. Browser/curl → `api_gateway:8000` (TCP + HTTP/1.1)
2. `api_gateway` → `model_service:8001` (TCP + HTTP/1.1 via `httpx.AsyncClient`)
3. `model_service` → `api.groq.com` (HTTPS)
4. Response path reverses: Groq → model_service → api_gateway → browser

**Response:** JSON body matching `shared.schemas.GenerateResponse`, HTTP 200.

</details>

<details>
<summary>Click to reveal answer: Endpoint 2 — /api/v1/generate/stream</summary>

**What's different:** the gateway uses a **raw `httpx.AsyncClient.stream()`** instead of `ServiceClient.post()`. Why? `ServiceClient` returns a parsed JSON dict — streams aren't JSON, they're byte chunks (SSE frames). Using `ServiceClient` would buffer the entire stream into memory before returning. We need byte-by-byte proxying.

**Files touched:**
- `baseline/api_gateway/app/routes/generate.py` — `generate_text_stream()` (note the `proxy_stream()` inner generator)
- `baseline/api_gateway/app/dependencies.py` — `get_settings()` (for `model_service_url`)
- `baseline/shared/logging.py` — logs `proxy_stream_aborted` / `proxy_stream_completed`
- `baseline/model_service/app/routes/inference.py` — `/inference/stream` handler
- `baseline/model_service/app/services/*` — the generator that yields tokens from Groq

**Network hops:**
1. Browser → `api_gateway:8000` — persistent HTTP/1.1 with `text/event-stream`
2. `api_gateway` → `model_service:8001` — persistent HTTP/1.1 with `text/event-stream`
3. `model_service` → Groq streaming endpoint — persistent HTTPS
4. Tokens flow back through 3→2→1, byte-by-byte

**Client-disconnect handling:** the gateway calls `await http_request.is_disconnected()` inside the proxy loop. When the browser closes the tab, the gateway exits its `async for`, the `async with` closes the upstream socket, model_service sees *its* own connection close, and stops pulling tokens from Groq. This is load-bearing — without it the gateway would keep burning Groq tokens nobody reads.

**Headers that matter:**
- `Cache-Control: no-cache` — prevent intermediate caches from buffering
- `X-Accel-Buffering: no` — tell nginx (when we add it in Part III) to flush chunks immediately

</details>

<details>
<summary>Click to reveal answer: Endpoint 3 — /api/v1/jobs (two phases)</summary>

**Phase A — submission (curl returns in <100ms):**

Files:
- `baseline/api_gateway/app/routes/jobs.py` — `submit_job()` handler
- `baseline/api_gateway/app/dependencies.py` — `get_worker_client()`
- `baseline/shared/http_client.py` — `ServiceClient.post()` to worker
- `baseline/shared/schemas.py` — `JobSubmission`, `JobResponse`
- `baseline/worker_service/app/routes/jobs.py` — receives the HTTP enqueue
- `baseline/worker_service/app/services/queue.py` — `PostgresQueue.enqueue()` does the INSERT
- `baseline/shared/models.py` — `BatchJob` ORM model

Network hops (phase A only):
1. curl → `api_gateway:8000`
2. `api_gateway` → `worker_service:8002` (HTTP)
3. `worker_service` → `postgres:5432` (SQL `INSERT INTO batch_jobs (...) VALUES (...) RETURNING id`)
4. Response path: Postgres row → worker_service → api_gateway → curl
5. Curl sees: **HTTP 202 Accepted**, body `{job_id: "...", status: "pending", ...}`

**Phase B — background processing:**

Files:
- `baseline/worker_service/app/worker.py` — `worker_loop()`, the polling coroutine
- `baseline/worker_service/app/services/queue.py` — `PostgresQueue.dequeue()` (contains the `SKIP LOCKED` query)
- `baseline/worker_service/app/services/processor.py` — `JobProcessor` executes each prompt
- `baseline/model_service/app/routes/inference.py` — `/inference` (called N times, one per prompt)

SQL claim query (the important line):
```sql
SELECT id FROM batch_jobs
WHERE status = 'pending'
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1
```

Per-prompt processing:
- `worker_service` → `model_service:8001` (one HTTP call per prompt)
- `model_service` → Groq (one HTTPS call per prompt)

Finalization:
```sql
UPDATE batch_jobs
SET status = 'completed', completed_at = NOW(), results = $1
WHERE id = $2
```

Client polling:
- Browser periodically calls `GET /api/v1/jobs/{id}` → gateway → worker → Postgres SELECT → returns current state.

</details>

## Quiz

Try these without peeking at the code. Answers are in the collapsible below.

1. **If `model_service` crashes, which endpoints fail immediately, and which degrade gracefully?**
2. **If `worker_service` crashes but Postgres and model_service are healthy, what happens to (a) new `POST /api/v1/jobs` and (b) jobs already sitting in `batch_jobs` with `status='pending'`?**
3. **The gateway's `ServiceClient` has a 30-second default timeout. Is that the right value for calls to `model_service`? What would a senior engineer change?**
4. **Why does `generate_text_stream()` use raw `httpx` instead of `ServiceClient`? Could we extend `ServiceClient` to handle streams instead?**
5. **What SQL clause in `PostgresQueue.dequeue()` guarantees that two worker replicas never process the same job?**

<details>
<summary>Quiz answers</summary>

1. **Fail immediately:** `POST /api/v1/generate`, `POST /api/v1/generate/stream` (both raise `ServiceUnavailableError` → 503 to client). **Degrade gracefully:** `POST /api/v1/chat/sessions` and other chat CRUD (they only touch Postgres), `POST /api/v1/jobs` submission (it only touches worker, which only touches Postgres). However, already-submitted jobs stop making progress because the worker loop can't reach model_service to process each prompt.

2. **(a)** New POSTs fail with 503 because gateway can't reach `worker_service:8002`. **(b)** Existing pending jobs just sit in `batch_jobs`. When worker_service restarts, its `worker_loop` picks them up on the next poll. This is the durability win of using Postgres as the queue — job survival is independent of the consumer's availability.

3. **30s is too permissive for inter-service calls.** A senior engineer would set the gateway→model timeout to ~5-10s (long enough for a slow Groq response, short enough to fail fast on a dead backend), add a circuit breaker, and set a *separate, longer* timeout on model_service→Groq (which is the actually-slow leg).

4. **Streams aren't JSON** — they're an indefinite sequence of byte chunks. `ServiceClient.post()` calls `response.json()`, which buffers and parses the whole body. We'd need to extend `ServiceClient` with a `.stream()` method that returns an async iterator of bytes. That's a reasonable refactor — we don't do it in the baseline to keep `ServiceClient`'s interface narrow, but a production version would add it.

5. **`FOR UPDATE SKIP LOCKED`** — it acquires a row lock and skips rows already locked by another transaction, giving us competing-consumer semantics. Without `SKIP LOCKED`, concurrent workers would either deadlock (with `FOR UPDATE` alone) or race and process the same job twice (without `FOR UPDATE`).

</details>

## Where this leads

- **Lesson 0.3** — zooms in on dependency injection: how `get_model_client()` actually wires a `ServiceClient` into a route handler, and why `Depends()` beats global singletons.
- **Lesson 0.4** — takes these three flows and profiles them line by line, measuring where the milliseconds go.
- **Part I Task 1 (REST vs gRPC)** — reimplements the sync `/generate` flow over gRPC and benchmarks the difference.
- **Part I Task 3 (Batch / Real-time / Streaming)** — the three flows from this lab *are* the three paradigms that task teaches.

## Further references

- `baseline/api_gateway/app/routes/generate.py` — lines 1-97, the cleanest example of the two proxy patterns side-by-side
- `baseline/worker_service/app/services/queue.py` — the `PostgresQueue` class and its `SKIP LOCKED` query
- `architecture/data-flow.md` — canonical request flow diagrams for every endpoint
- `architecture/system-overview.md` — if you want the bird's-eye view again
