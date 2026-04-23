# Lesson 0.4 — Request Flows: Sync, Streaming, Jobs (Slides)

**Duration:** ~30 min live + 30 min lab
**Audience:** engineers who've read through the baseline once and want to
understand *how a request actually executes*
**Format:** 17 slides

---

## Slide 1 — Title

**Request Flows: Sync, Streaming, Jobs**
*Three HTTP shapes, three trade-offs, one codebase*

Workshop Part 0 · Lesson 0.4

---

## Slide 2 — What you should leave with

- Know the three canonical flows in the baseline and when to pick each
- Be able to trace a request end-to-end through the logs
- Understand why `SELECT ... FOR UPDATE SKIP LOCKED` is the queue primitive
- Understand why the streaming path has natural backpressure and the sync path doesn't
- Spot a dropped-SSE-connection bug in review

---

## Slide 3 — The three shops

| Flow | Metaphor | UX |
|---|---|---|
| **Sync** | espresso bar | wait at the counter, walk out with the drink |
| **Streaming** | sushi conveyor | plates flow past, eat as they arrive |
| **Jobs** | dry cleaner | drop off, get a ticket, come back later |

Same customer, same menu, wildly different time-shape.

---

## Slide 4 — Three HTTP shapes at a glance

```
Sync:       client ──req──► server ──(wait)──► rsp ──► client
Streaming:  client ──req──► server ──tok──► ──tok──► ──tok──► ...
Jobs:       client ──submit──► 202 + id ──► client (goes away)
                         ...later...
            client ──GET /jobs/{id}──► status ──► client
```

Pick sync for fast/simple. Streaming for slow-but-progressive.
Jobs for "too long to hold a connection."

---

## Slide 5 — Flow A: Sync `/api/v1/generate`

```python
@router.post("/generate", response_model=GenerateResponse)
async def generate_text(
    request: GenerateRequest,
    model_client: ServiceClient = Depends(get_model_client),
):
    result = await model_client.post("/inference", json=request.model_dump())
    return GenerateResponse(**result)
```

Four lines. Validate → proxy → return. Caller blocks for the full
gateway→model_service→Groq round trip.

---

## Slide 6 — Flow B: Streaming `/api/v1/generate/stream`

Gateway opens a *streaming* httpx connection (not the usual
`ServiceClient`, which buffers):

```python
async with client.stream("POST", ".../inference/stream", json=body) as rsp:
    async for chunk in rsp.aiter_bytes():
        if await http_request.is_disconnected():
            return
        yield chunk
```

Gateway doesn't parse SSE frames — just proxies bytes.

---

## Slide 7 — SSE wire format

Each token is a single SSE frame:

```
data: "Hello"\n\n
data: " world"\n\n
data: [DONE]\n\n
```

- `data:` is the SSE field name.
- The value is a **JSON-encoded** string (so tokens containing newlines
  don't fake-terminate the frame).
- Blank line (`\n\n`) = end of frame.
- `[DONE]` is a sentinel, not JSON.

Debuggable with `curl -N`.

---

## Slide 8 — Streaming has natural backpressure

```
Groq → model_service : yield blocks until gateway reads
model_service → gateway : yield blocks until TCP window opens
gateway → browser : TCP blocks until client reads
```

A slow client implicitly slows Groq. **No explicit rate limiting needed**
for this flow.

Sync has none of this — the only protection is the 30 s `ServiceClient` timeout.

---

## Slide 9 — Disconnect propagation

When the browser closes the tab:

1. Gateway's `http_request.is_disconnected()` → true
2. Gateway exits `aiter_bytes`, closes upstream TCP
3. Model service's `is_disconnected()` → true
4. Model service exits generator, cancels Groq iterator

Forget the check at any hop → you keep paying for tokens nobody will see.

---

## Slide 10 — Flow C: Jobs submit

```python
@router.post("/jobs", response_model=JobResponse, status_code=202)
async def submit_job(submission: JobSubmission,
                     worker_client: ServiceClient = Depends(get_worker_client)):
    result = await worker_client.post("/jobs", json=submission.model_dump())
    return JobResponse(**result)
```

Gateway is a thin proxy. The interesting work is in worker_service.
Returns **202 Accepted + job_id** — not 200.

---

## Slide 11 — Postgres as a queue (SKIP LOCKED)

```python
stmt = (select(BatchJob)
        .where(BatchJob.status == "pending")
        .order_by(BatchJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True))   # the magic
```

Translates to:

```sql
SELECT ... FROM batch_jobs WHERE status='pending'
ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED;
```

Competing workers claim **different** rows without coordination. No
Redis, no broker, no retries.

---

## Slide 12 — The worker loop

```python
while True:
    item = await queue.dequeue()
    if item is None:
        await asyncio.sleep(poll_interval)   # 1 s default
        continue
    job_id, submission = item
    await processor.process(job_id, submission)
```

Boring by design. Survives bad jobs (try/except inside the processor).
Cost of idleness: one `LIMIT 1` query per worker per second.

---

## Slide 13 — Request IDs and log correlation

`RequestLoggingMiddleware` on every gateway request:

```python
request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
logger.info("request_started", request_id=request_id, ...)
response.headers["X-Request-ID"] = request_id
```

Structured JSON logs → grep by `request_id` finds every line.

**Honest caveat:** the baseline doesn't yet forward `X-Request-ID` as an
outbound header to downstream services. Lesson 0.5 fixes that.

---

## Slide 14 — Picking the right flow

| Question | Pick |
|---|---|
| One prompt, <10 s, user is waiting? | **Sync** |
| User wants progressive text / "feels live"? | **Streaming** |
| 30 prompts to process, user doesn't care about order? | **Jobs** |
| Nightly re-summarization over 10k rows? | **Jobs** |
| Completion inside a script that retries on 5xx? | **Sync** |

Wrong choice = the flow still works, just expensively.

---

## Slide 15 — Common mistakes

1. **Sync for batches.** 30 prompts × 3 s each = a request that holds a
   connection for 90 s. Use jobs.
2. **Streaming without the disconnect check.** Closed browser tab, infinite
   Groq bill.
3. **Jobs without a 202.** Returning 200 suggests "it's done" — callers
   won't poll.
4. **Polling with `SELECT ... UPDATE` and no `FOR UPDATE SKIP LOCKED`.**
   Two workers process the same job.
5. **Forgetting the 30 s timeout in `ServiceClient`.** Hung upstream = stuck
   requests forever.

---

## Slide 16 — Lab preview (read-along)

Three curls, one `psql`, ~10 minutes:

1. `curl .../generate` — find matching `request_id` in gateway + model logs
2. `curl -N .../generate/stream` — watch tokens arrive
3. `POST .../jobs/batch` → poll — watch status transitions in `psql`

Bonus: kill the worker, submit, restart, watch the claim.

See `lab/README.md`.

---

## Slide 17 — Key takeaways

1. **Three flows, three shapes.** Sync blocks the caller; streaming dribbles
   bytes; jobs decouple submit from execute.
2. **SSE is the simplest streaming primitive** that works through any HTTP
   proxy and debugs with `curl -N`.
3. **SKIP LOCKED is how you use Postgres as a queue** without Redis.
4. **Disconnects must propagate upstream** or you leak work.
5. **Structured logs + request_id = end-to-end tracing** without a full
   tracing stack.

**Next up:** Lesson 0.5 — Persistence & Observability.
