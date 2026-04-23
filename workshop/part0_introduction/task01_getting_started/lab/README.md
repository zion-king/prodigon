# Lab 0.1 — Getting Started

## Problem statement

Clone the repo cold. In under 15 minutes, have:
- All 3 backend services running
- Postgres running with the baseline schema applied
- The frontend running
- A `verify.py` script that proves end-to-end connectivity

## Prerequisites

- Python 3.11+
- Node.js 20+
- Git
- **Either** Docker Desktop **or** Postgres 16 installed natively
- A Groq API key (`console.groq.com`) **or** willingness to run in mock mode (`USE_MOCK=true`)

## What's in the starter

```
lab/starter/
├── walkthrough.sh      # Stub shell script with placeholders for each step
├── verify.py           # Skeleton smoke test with TODOs
└── __init__.py
```

`walkthrough.sh` has 7 numbered TODOs; your job is to fill each with the right `make` / `npm` / `curl` command. `verify.py` has 3 TODOs for three endpoints to hit.

## Steps

### Task 1 — Complete the walkthrough script

Open `lab/starter/walkthrough.sh`. Fill in each TODO with the right command. When you're done, `bash lab/starter/walkthrough.sh` should:

1. Run `scripts/setup.sh` (fresh-clone setup)
2. Remind you to edit `.env` (or just auto-set `USE_MOCK=true` for this lab)
3. Start Postgres — pick one path based on your environment
4. Apply migrations
5. Start `make run` in the background
6. Wait for `/health` to report green
7. Curl the generate endpoint as a smoke test

### Task 2 — Complete the verification script

Open `lab/starter/verify.py`. It has three functions with TODOs:

- `test_gateway_health()` — GET `http://localhost:8000/health`, assert 200
- `test_generate()` — POST `http://localhost:8000/api/v1/generate` with a prompt, assert 200 + non-empty response
- `test_chat_session_roundtrip()` — POST `/api/v1/chat/sessions`, GET it back, assert the ID matches

Fill in the bodies. Run it: `python lab/starter/verify.py`. All three should print `OK`.

### Task 3 — Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Create a chat session. Send a message (in mock mode the response will be canned — that's fine). Refresh the tab. Your session should still be there (Postgres persistence from ADR-011).

### Task 4 — Break and repair (optional but instructive)

Stop Postgres (`make db-down` for Docker; stop your native service). Try `make run` again. You should see the preflight fire and print a clear error. Start Postgres again. `make run` should succeed without any code change.

This is the fail-fast preflight in action.

## Expected output

After `bash lab/solution/walkthrough.sh` completes:

```
==> scripts/setup.sh ... done
==> .env exists: yes
==> Postgres ready on localhost:5432
==> alembic upgrade head: applied 1 revision (or already at head)
==> make run: services starting in background (pid=XXXXX)
==> /health: api-gateway :8000 OK
==> /health: model-service :8001 OK
==> /health: worker-service :8002 OK
==> /api/v1/generate smoke test: OK (response length: 142 chars)
✓ Walkthrough complete. Stack is live on ports 8000/8001/8002 and Postgres 5432.
```

And `python lab/solution/verify.py`:

```
test_gateway_health ............. OK
test_generate ................... OK
test_chat_session_roundtrip ..... OK

3 passed
```

## Bonus challenges

1. **Add a new health check** — modify `scripts/check_health.sh` to also verify Postgres is accepting connections (beyond what `make health` already does). Hint: `psql -c 'SELECT 1'` or `pg_isready`.

2. **Measure cold-start time** — wrap `make run` in a timer. How long from invocation to all three `/health` endpoints green? Where's the slowest phase?

3. **Native-to-Docker swap** — switch your local dev from native Postgres to Docker Postgres (or vice versa) without losing your chat history. Hint: `pg_dump` / `pg_restore`.

4. **Automate the `.env` template** — write a one-liner that generates a `.env` with `USE_MOCK=true` and a random-but-unused port for `DATABASE_URL` so you can run two baselines side by side.

5. **Make `verify.py` parallel** — use `asyncio.gather()` to run the three tests concurrently. Does it actually get faster, or is the bottleneck somewhere else (Groq API latency, DB I/O)?

## Where this leads

- Lesson 0.2 uses the running stack to tour the architecture
- Lesson 0.3 adds a new dependency-injected route to the gateway
- Lesson 0.4 exercises all three request flows through the stack you just built
- The `verify.py` pattern from this lab is the template for every integration test in Parts I–III

## Troubleshooting

| Symptom | Check |
|---|---|
| `scripts/setup.sh: command not found` | You need Git Bash (Windows) or a real shell (macOS/Linux). |
| `pg_isready: command not found` on native path | Postgres not installed, or its `bin/` isn't in `PATH`. On Windows, add `C:\Program Files\PostgreSQL\16\bin`. |
| `make run` prints "Postgres not reachable" | You haven't started Postgres yet. Run `make db-up` or `make db-up-native`. |
| 500 on `/api/v1/chat/sessions` | Migrations didn't run. Run `make db-migrate`. |
| Frontend shows "Failed to fetch" | CORS: check `ALLOWED_ORIGINS` in `.env` includes `http://localhost:5173`. |
| Groq 401 on `/api/v1/generate` | Either set `USE_MOCK=true` or fix `GROQ_API_KEY` in `.env`. |
