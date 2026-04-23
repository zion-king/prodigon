# Lesson 0.1 — Getting Started (Slides)

**Duration:** ~30 min live (or 20 min self-paced with the lab)
**Audience:** anyone who just cloned the repo
**Format:** 16 slides

---

## Slide 1 — Title

**Getting Started**
*Dev Environment Walkthrough — from `git clone` to green health checks*

Workshop Part 0 · Lesson 0.1

---

## Slide 2 — What you should leave with

By the end of this lesson, you will have:

- A running 3-service stack on `localhost:8000–8002`
- A Postgres database with the baseline schema applied
- A running React frontend on `localhost:5173`
- Confidence in **which `make` target to reach for** when something breaks

Prerequisite for every other lesson in Part 0 and every task in Parts I–III.

---

## Slide 3 — The stack at a glance

```
Frontend  →  API Gateway  →  Model Service  →  Groq API
 :5173        :8000           :8001              (cloud)
                │
                ├─  Worker Service  :8002
                │
                └─  Postgres        :5432
```

3 Python services + 1 database + 1 frontend = 5 boxes to keep alive.

---

## Slide 4 — Two tools do all the work

**`make`** — one-word commands for setup/run/test/migrate.

**`.env`** — config (Groq key, DB URL, CORS origins).

That's it. Everything else is implementation detail.

```bash
make help        # see every target with a 1-line description
```

---

## Slide 5 — The happy path (5 commands)

```bash
bash scripts/setup.sh               # deps + .env
source venv/Scripts/activate        # or venv/bin/activate
# edit .env: set GROQ_API_KEY OR USE_MOCK=true
make dev-setup-native               # or: make dev-setup (Docker)
make run                            # in terminal A
cd frontend && npm install && npm run dev  # in terminal B
```

Open `http://localhost:5173`.

---

## Slide 6 — Docker path vs native path

| | Docker path | Native path |
|---|---|---|
| DB tool | `docker-compose` | `psql` |
| Start DB | `make db-up` | `make db-up-native` |
| Stop DB | `make db-down` | Your OS service manager |
| Best when | You have Docker Desktop | You installed Postgres yourself |

**Pick one.** Don't mix.

---

## Slide 7 — What `make dev-setup-native` does

```
dev-setup-native:
  ├─ setup          # scripts/setup.sh: venv + deps + .env
  ├─ db-up-native   # psql -f scripts/db_bootstrap.sql
  └─ db-migrate     # alembic upgrade head
```

One command, three idempotent phases. Run it again? Nothing breaks.

---

## Slide 8 — What `make run` actually does

`scripts/run_all.sh`:

1. Parse `DATABASE_URL` → extract host, port
2. TCP socket probe on Postgres (1-second timeout)
3. `alembic upgrade head` (no-op if already at head)
4. Launch three `uvicorn` servers in the background

**Fail-fast preflight** — you get "Postgres not reachable" instead of a 500 on your first request.

---

## Slide 9 — The `.env` fields that matter

```
GROQ_API_KEY=...            # or USE_MOCK=true for offline
USE_MOCK=false
DATABASE_URL=postgresql+asyncpg://prodigon:prodigon@localhost:5432/prodigon
QUEUE_TYPE=postgres         # postgres (durable) | memory (tests)
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
LOG_LEVEL=INFO
```

Pydantic `BaseSettings` validates these at startup. Typo = fail-fast with an error.

---

## Slide 10 — Verify: `make health`

```bash
$ make health
✓ api-gateway   :8000  healthy
✓ model-service :8001  healthy
✓ worker-service:8002  healthy
```

Three `curl http://localhost:8XXX/health` calls. If any one is red, *that* service is the problem.

---

## Slide 11 — First real API call

```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain microservices in one sentence"}'
```

Request flow: browser → Gateway → Model Service → Groq → back. You just used all three services.

---

## Slide 12 — When things break: the 3 first checks

| Symptom | First thing to check |
|---|---|
| `make run` fails, "Postgres not reachable" | `make db-up` (Docker) or `make db-up-native` (native) |
| 500 on `/api/v1/chat/sessions` | `make db-migrate` — tables missing |
| Frontend can't reach backend | `ALLOWED_ORIGINS` in `.env` includes `http://localhost:5173`? |

These three cover ~80% of first-day failures.

---

## Slide 13 — Senior-engineer mental model

The dev workflow intentionally mirrors production:

- **Preflight before boot** → K8s readiness probe
- **Idempotent migrations on every start** → init containers
- **Pydantic-validated config** → Vault / Parameter Store secrets with validation
- **Structured JSON logs** → Datadog / CloudWatch ingestion

When you hit Part III (security, secrets) you'll see these patterns scale up.

---

## Slide 14 — Live demo (5 min)

1. `git status` — clean repo
2. `bash scripts/setup.sh` — deps installing
3. Edit `.env` → `USE_MOCK=true`
4. `make dev-setup-native`
5. `make run`
6. `make health`
7. `curl` the generate endpoint
8. Open frontend, create a chat session

Expected time: 5 minutes end to end on a warm `pip` cache.

---

## Slide 15 — Lab preview

In `lab/starter/` you'll find:

- `walkthrough.sh` — stub with placeholders for each step
- `verify.py` — skeleton that tests generate + chat + health

Your job: fill them in. `lab/solution/` contains the completed reference. Run `python lab/solution/verify.py` to smoke-test your own stack.

---

## Slide 16 — Key takeaways

1. **5 boxes**: frontend, gateway, model, worker, Postgres.
2. **2 tools**: `make` for orchestration, `.env` for config.
3. **1 decision**: Docker path or native path — pick one.
4. **Preflight pattern**: fail fast on missing deps, don't crash mid-request.
5. **Everything idempotent**: re-running any `make` target is safe.

**Next up:** Lesson 0.2 — System Architecture Tour.
