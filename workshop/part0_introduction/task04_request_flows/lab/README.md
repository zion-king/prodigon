# Lab 0.4 — Trace the Three Flows End-to-End

> **Goal:** watch each of the three request flows (sync, streaming, jobs)
> actually execute — through `curl`, through the service logs, and
> through the `batch_jobs` table. No code to write; this is a read-along
> lab.

## Problem statement

You've read about the three flows in `README.md`. This lab makes them
concrete: you will fire each flow with `curl`, find the corresponding log
lines in both services, and (for jobs) watch the state transitions in
Postgres in real time.

## Prerequisites

- Lab 0.1 completed — `make run` brings up the full stack
- `psql` available (the compose stack exposes Postgres on `localhost:5432`)
- Two terminals open, ideally three
- Your `GROQ_API_KEY` set in `.env`

## Files in this lab

This is a read-along lab. There are no `starter/` or `solution/` dirs to
copy — you're exercising the baseline as-is and observing it.

## Setup — one-time

From the repo root:

```bash
make run           # brings up api_gateway, model_service, worker_service, postgres
```

Wait for all three services to log `*_ready`. Open a second terminal for
`curl` and a third for `psql`.

In terminal 3, connect to the database:

```bash
docker compose exec postgres psql -U prodigon -d prodigon
```

(Credentials are in `baseline/.env.example`; adjust if you changed them.)

## Task 1 — Sync flow: trace one request across two services

### Fire the request

In terminal 2:

```bash
curl -s -X POST localhost:8000/api/v1/generate \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: sync-demo-001' \
  -d '{"prompt": "Say hello in exactly three words."}' | jq
```

Note the `X-Request-ID` header. Setting it explicitly makes the logs
trivially searchable; omit it and the gateway generates a UUID.

You should see a JSON response with the generated text, model name, token
usage, and latency_ms.

### Find the matching logs

In terminal 1 (where `make run` is tailing logs), you'll see four key
structured log lines, in order:

```
service=api-gateway    event=request_started     request_id=sync-demo-001  path=/api/v1/generate
service=model-service  event=inference_completed model=...
service=api-gateway    event=request_completed   request_id=sync-demo-001  status=200
```

### Observe

- The gateway's `request_started` and `request_completed` bracket the
  whole flow. Diff the timestamps → end-to-end latency.
- Between them, model_service logs its own entries. They do **not** yet
  carry `request_id=sync-demo-001` — the baseline doesn't propagate
  `X-Request-ID` as an outbound header in `ServiceClient`. This is the
  gap Lesson 0.5 closes.
- Correlate by timestamp window for now. In a workshop setting, this
  works. In production, it breaks the moment concurrent requests overlap.

## Task 2 — Streaming flow: watch tokens arrive

### Fire the stream

```bash
curl -N -s -X POST localhost:8000/api/v1/generate/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Write a three-line haiku about production software."}'
```

The `-N` flag disables curl's output buffering so you see tokens as they
arrive. You should see output like:

```
data: "Deploy"\n\n
data: " on"\n\n
data: " Friday"\n\n
data: ","\n\n
data: "\n"\n\n
data: "pager"\n\n
...
data: [DONE]\n\n
```

### Read the wire format

Each token is one SSE frame:

- `data: ` — the SSE field name (required).
- `"<json-string>"` — the token, JSON-encoded. This matters for tokens
  that contain newlines: `data: "\n\n"\n\n` is unambiguous because the
  `\n\n` inside the quoted JSON is an escape sequence, while the
  terminating `\n\n` is literal.
- blank line = end of frame.
- `[DONE]` is a plain-text sentinel, not JSON.

### Observe backpressure

Try piping through a slow reader:

```bash
curl -N -s -X POST localhost:8000/api/v1/generate/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Count from 1 to 30."}' \
  | while IFS= read -r line; do echo "$line"; sleep 0.2; done
```

The tokens still arrive in order, but they're throttled by your slow
reader. On the server side, this means Groq is (indirectly) generating
slower — the `yield` in model_service's event_generator blocks on gateway
reading, which blocks on your shell reading. That's the natural
backpressure chain.

### Observe disconnect propagation

Start the stream and hit Ctrl-C after 2–3 tokens. In terminal 1 you should
see:

```
service=api-gateway    event=proxy_stream_aborted    reason=client_disconnected
service=model-service  event=stream_aborted          reason=client_disconnected
```

Both services noticed and bailed. No more tokens billed against Groq.

## Task 3 — Jobs flow: watch state transitions in Postgres

### Submit a job

```bash
curl -s -X POST localhost:8000/api/v1/jobs/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "prompts": [
      "Summarize the French Revolution in one sentence.",
      "Summarize the Industrial Revolution in one sentence.",
      "Summarize the Internet Revolution in one sentence."
    ],
    "max_tokens": 100
  }' | jq
```

Response (immediate, 202):

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "pending",
  "total_prompts": 3,
  "completed_prompts": 0,
  "results": []
}
```

Copy the `job_id`. Note the status: **202 Accepted**, not 200. The job
hasn't run yet.

### Watch the state transitions

In terminal 3 (`psql`), poll the row every second. Run this a few times
in quick succession:

```sql
SELECT id, status, completed_prompts, total_prompts, created_at
FROM batch_jobs
ORDER BY created_at DESC LIMIT 5;
```

You should see the row walk through:

```
pending   →   running   →   completed
```

With the worker's default poll interval of 1 s, the transition to
`running` happens almost immediately. The transition to `completed` takes
~3 × per-prompt-latency (the processor handles prompts sequentially in
the baseline).

### Read the result via the API

```bash
curl -s localhost:8000/api/v1/jobs/<job_id> | jq
```

The `results` array now has three entries, one per prompt, each with the
generated text and model name.

### Observe the SKIP LOCKED query in logs

In terminal 1, filter for worker_service logs. You'll see:

```
service=worker-service event=worker_loop_started poll_interval=1.0
service=worker-service event=job_enqueued        job_id=a1b2c3d4 prompts=3
service=worker-service event=job_dequeued        job_id=a1b2c3d4
service=worker-service event=job_updated         job_id=a1b2c3d4 updates=[...]
```

The `job_dequeued` event is the moment `SELECT ... FOR UPDATE SKIP LOCKED`
succeeded and the worker flipped the row to `running` in the same
transaction. `job_updated` entries accumulate as each prompt finishes.

## Task 4 (Bonus) — Disable the worker, see jobs pile up

This demonstrates the fundamental property of the job flow: **the gateway
doesn't need the worker to be healthy to accept work.**

### Stop the worker

```bash
docker compose stop worker_service
```

### Submit a job

```bash
curl -s -X POST localhost:8000/api/v1/jobs/batch \
  -H 'Content-Type: application/json' \
  -d '{"prompts": ["What is the airspeed velocity of an unladen swallow?"],
       "max_tokens": 50}' | jq
```

The submission succeeds — 202 Accepted with a job_id. The gateway only
needs the worker's **HTTP** interface to insert the row. Wait, it actually
calls the worker over HTTP...

**Observation:** the baseline's gateway calls `worker_service.post("/jobs")`
which does the DB insert. With the worker stopped, the submission returns
**503** (from `ServiceUnavailableError` in `ServiceClient`).

Try it and confirm you get a 503. This is a design honesty: a *true*
"decoupled" flow would have the gateway insert into `batch_jobs` directly
and the worker only consume. Part I Task 3 refactors toward that shape.

### Restart the worker and watch it drain

```bash
docker compose start worker_service
```

Submit the job again. Watch it transition pending → running → completed.
Now kill the worker *mid-job* and restart:

```bash
docker compose stop worker_service
# in psql:
SELECT id, status FROM batch_jobs WHERE status = 'running';
```

You'll see any in-flight job stuck in `running` — the worker crashed
before committing the completion. The baseline has no reaper; in
production you'd have a heartbeat column and a cron job to reset stuck
rows. See `production_reality.md` "Worker that crashes mid-job" for the
three recovery patterns.

## Expected output

After Task 1: matching log lines for `request_id=sync-demo-001` in
gateway and (by timestamp) in model_service.

After Task 2: SSE frames arriving progressively; `stream_aborted` logs on
Ctrl-C.

After Task 3: `batch_jobs` row walking pending → running → completed;
`GET /api/v1/jobs/{id}` returning filled-in `results`.

After Task 4: understanding that the baseline's job submission is not yet
fully decoupled from worker liveness, and a row stuck in `running` after
a crash (no reaper).

## Bonus challenges

1. **Multi-worker SKIP LOCKED race.** Scale the worker service:
   `docker compose up -d --scale worker_service=3`. Submit 10 jobs in
   quick succession. Inspect the logs and confirm each `job_dequeued`
   line comes from a different worker (via process or hostname markers).
   No duplicate claims.

2. **SSE keepalive.** With a generation that takes >60 s, a default nginx
   proxy would terminate the connection for inactivity. The baseline
   streams tokens continuously so it's not an issue, but what would you
   add to the server to defend against this? (Answer: periodic
   `: keepalive\n\n` comment frames every 15 s. Comments start with `:`
   and are ignored by SSE clients.)

3. **Request-ID propagation.** Patch `ServiceClient.post` to read a
   `request_id` from a `contextvars.ContextVar` and include it as
   `X-Request-ID` on every outbound call. Set the contextvar in
   `RequestLoggingMiddleware`. Re-run Task 1 and confirm the downstream
   model_service logs now carry `request_id=sync-demo-001` explicitly.
   This is a preview of what Lesson 0.5 formalizes.

4. **Idempotent job submission.** Add an `Idempotency-Key` header to
   `POST /api/v1/jobs/batch`. If the key has been seen before (lookup by
   a new column on `batch_jobs`), return the existing job instead of
   enqueuing a new one. Retry-safe job submission in ~20 lines of code.

## Troubleshooting

**`curl -N` still buffers.** Your curl version is old, or you're on a
terminal that buffers stdin. Try `curl -N --no-buffer` or pipe to
`cat -u`.

**`psql` shows no `batch_jobs` rows.** Migrations may not have run. From
the repo root: `make migrate` or `docker compose exec api_gateway
alembic upgrade head`.

**`request_id` in logs doesn't match.** Remember: the baseline logs the
id at the gateway but doesn't forward it as a header. Correlate by
timestamp, or implement Bonus 3.

**Streaming hangs on first token.** Groq is slow or rate-limiting.
Check model_service logs for `inference_error` or `rate_limited` events.

## What you learned

- **Three flows leave three distinct fingerprints in the logs.** Once
  you've seen each shape, you'll recognize them on sight in an unfamiliar
  codebase.
- **SSE is debuggable with `curl -N`** — no special tooling needed. That's
  half the reason the baseline picked it over WebSockets.
- **`SELECT ... FOR UPDATE SKIP LOCKED` is observable** — the `job_dequeued`
  log line is the moment of claim. Multiple workers show up as
  interleaved, never-duplicated claims.
- **Disconnect propagation is real and the baseline honors it** — closed
  tab, closed upstream, no wasted tokens.
- **Job flow failure modes are different from sync flow failure modes**
  — a stuck `running` row after a worker crash is a pattern you'll see
  again in every queue-based system you work on.

Lesson 0.5 goes deeper on the `batch_jobs` schema itself, on structured
logging with bound contextvars, and on the metrics you'd export to
actually alert on these failure modes.
