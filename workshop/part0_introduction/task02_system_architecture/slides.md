# Lesson 0.2 — System Architecture Tour (Slides)

**Duration:** ~30 min live (plus a 30 min read-along lab)
**Audience:** anyone who ran Lesson 0.1 successfully
**Format:** 17 slides

---

## Slide 1 — Title

**System Architecture Tour**
*The three services, the shared library, and the wires between them*

Workshop Part 0 · Lesson 0.2

---

## Slide 2 — What you should leave with

By the end of this lesson you will be able to:

- Name each of the three backend services and what it does
- Explain why `shared/` exists and what belongs in it
- Trace an HTTP request from the frontend to Groq and back
- Say in one sentence **why the baseline is split into services at all**

This is the mental model every other lesson in Parts I–III will build on.

---

## Slide 3 — The five boxes (refresher)

```
Frontend  →  api_gateway  →  model_service  →  Groq
 :5173        :8000           :8001
                │
                ├─  worker_service  :8002
                │
                └─  Postgres        :5432
```

Five boxes. Three Python services. One database. One frontend.

---

## Slide 4 — The port map (memorize this)

| Port | Service | Role |
|---:|---|---|
| 5173 | frontend | React dev server |
| 8000 | api_gateway | Public API |
| 8001 | model_service | Internal inference API |
| 8002 | worker_service | Internal job API + worker loop |
| 5432 | Postgres | Data + durable job queue |

**Only `:8000` is public.** In prod, `:8001` and `:8002` live on a private network.

---

## Slide 5 — api_gateway: the single entry point

Routes in `baseline/api_gateway/app/routes/`:

- `health.py` — `/health`
- `generate.py` — `/api/v1/generate` + `/api/v1/generate/stream`
- `chat.py` — chat session CRUD
- `jobs.py` — `/api/v1/jobs` (submit, poll)
- `workshop.py` — diagnostics

**What it does NOT do:** call Groq, run inference, pop jobs.
**What it DOES do:** validate, authenticate, route, decorate.

---

## Slide 6 — model_service: the Groq encapsulator

`baseline/model_service/app/`:

- `main.py` — FastAPI app + lifespan hooks (warm cache, open HTTP pool)
- `routes/inference.py` — `POST /inference`, `POST /inference/stream`
- `services/` — model adapter, response cache, retry/backoff

**One reason it exists:** swap Groq for OpenAI tomorrow, and only files in `model_service/` change. The gateway's contract stays put.

---

## Slide 7 — worker_service: two things in one process

1. **HTTP API** (`routes/jobs.py`) — the gateway calls this to enqueue. Writes a row to `batch_jobs`. Returns `202 Accepted`.
2. **Polling loop** (`app/worker.py`) — wakes every 1s, runs `SELECT ... FOR UPDATE SKIP LOCKED` on `batch_jobs`, claims one row, calls `model_service` to process it.

`SKIP LOCKED` → competing-consumers semantics from plain Postgres. No Redis. No Kafka.

---

## Slide 8 — shared/: the common library

Everything every service needs, in one package:

| File | Purpose |
|---|---|
| `config.py` | Pydantic `BaseSettings` base |
| `constants.py` | Model IDs, timeouts, job statuses |
| `db.py` | Async SQLAlchemy engine + session factory |
| `errors.py` | `AppError` hierarchy |
| `http_client.py` | Typed `ServiceClient` |
| `logging.py` | Structured JSON logger |
| `models.py` | ORM: `ChatSession`, `BatchJob`, `User` |
| `schemas.py` | Pydantic DTOs (the wire contract) |

**Rule:** no FastAPI, no routes, no service-specific imports in `shared/`.

---

## Slide 9 — Why share instead of duplicate?

Consider the alternative: each service defines its own `GenerateRequest` schema.

```python
# api_gateway/schemas.py
class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 256

# model_service/schemas.py
class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512  # ← drift
```

One changes, the other doesn't. Requests parse fine on the wire but have different defaults. Silent bug.

`shared/schemas.py` makes that impossible. The contract is one file, imported everywhere.

---

## Slide 10 — Communication: HTTP + Postgres

**Two channels. No other channels.**

- **HTTP between services** via `shared.http_client.ServiceClient`
  - Timeout: 30s default
  - Typed errors: `ConnectError` → `ServiceUnavailableError`
  - Every failure logged with URL + status + body
- **Postgres as a shared DB**
  - `api_gateway` owns `chat_sessions`, `chat_messages`, `users`
  - `worker_service` owns `batch_jobs`
  - No table written by more than one service

---

## Slide 11 — The "shared DB is an anti-pattern" caveat

True in general. False in our baseline. **Why?**

Each table has exactly one writer. No cross-service transactions. If we ever extracted `worker_service` into its own DB, we'd migrate one schema and change one config file.

**Anti-pattern is cross-service writes**, not physical co-location.

---

## Slide 12 — Why three services, not one app?

Honest answer, not a religious one:

- **Failure isolation** — OOM in the Groq client shouldn't crash chat.
- **Independent scaling** — inference is expensive, `/health` is free.
- **Deploy cadence** — model routing changes daily; chat storage monthly.
- **Teaching** — Part I needs a microservice baseline to compare against a monolith.

---

## Slide 13 — The cost of splitting

What you pay, every day:

- 3 `uvicorn` processes to watch instead of 1
- Network hops with failure modes (timeouts, retries, partial failures)
- **Version skew** — deploy `shared/schemas.py` to model_service but not gateway? Responses fail to parse.

The question isn't "monolith or microservices." It's "**is the split worth the skew risk?**" Part I Task 2 answers that precisely.

---

## Slide 14 — Request flow: sync generate

```
Browser → api_gateway /api/v1/generate
        → model_service /inference
        → Groq
        ← response
        ← GenerateResponse
        ← JSON to browser
```

**Two network hops + one cloud call.** p50 latency ~600-800ms in the baseline. Lesson 0.4 profiles each hop.

---

## Slide 15 — Request flow: async batch job

```
Browser → api_gateway /api/v1/jobs
        → worker_service /jobs (HTTP)
        → INSERT INTO batch_jobs ... RETURNING id
        ← {job_id, status: pending}
        ← 202 Accepted

... meanwhile, in the worker loop (every 1s) ...

worker_service.worker_loop
        → SELECT ... FOR UPDATE SKIP LOCKED
        → model_service /inference (N times)
        → UPDATE batch_jobs SET status='done', results=...
```

Submission is fast. Processing runs in the background. Client polls for results.

---

## Slide 16 — Senior-engineer mental model

Three rules the baseline enforces:

1. **The gateway is the only trust boundary.** Auth lives there, nowhere else. Internal services trust their callers.
2. **shared/ is primitives only.** If it imports FastAPI, it doesn't belong.
3. **Each DB table has one writer.** Physical DB sharing is fine; logical ownership isn't.

Break any of these, and "microservices" turns into "distributed monolith." That's the failure mode Part I Task 2 teaches you to spot.

---

## Slide 17 — Key takeaways + what's next

1. Three services: gateway (public), model (Groq), worker (async).
2. `shared/` is the glue — settings, DB, HTTP, schemas, logs, errors.
3. Two communication channels: HTTP (service → service) and Postgres (data + queue).
4. The split is deliberate, and it has a real cost. Part I Task 2 quantifies it.

**Next up:**
- **Lesson 0.3** — dependency injection & service lifecycles
- **Lesson 0.4** — walk three request flows line by line

**Lab:** go to `lab/README.md` and annotate the request paths for three endpoints.
