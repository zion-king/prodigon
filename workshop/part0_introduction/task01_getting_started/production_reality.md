# Production Reality — Lesson 0.1 Getting Started

> The dev-environment patterns in this lesson (preflight checks, idempotent migrations, env-driven config) aren't just conveniences — they're production-critical in different dress. Here's what actually goes wrong, and what senior engineers do about it.

## What breaks at scale

### 1. The "works on my machine" class of bugs

**The failure mode:** developer A configures `.env` with `DATABASE_URL=postgresql+asyncpg://localhost:5432/prodigon`, tests locally, commits. Developer B pulls and their app 500s because their Postgres is on `5433` (Docker Desktop's default when the native install is also running).

**In production:** same bug, higher stakes. Staging has `DATABASE_URL` pointing at a staging RDS; someone copies the staging config into prod by mistake; the prod app writes to the staging DB for 20 minutes before alerts fire.

**What senior engineers do:**
- **Never hardcode credentials** — pull from Vault / AWS Secrets Manager / GCP Secret Manager at boot, validate the connection works before opening the port for traffic.
- **Refuse to boot** if required env vars are missing. Pydantic's `BaseSettings` does this for free; don't defeat it with `Optional[...]` everywhere.
- **Log the sanitized DB host on startup** so you can see at a glance which environment you're actually connected to (strip passwords, keep host + db name).

### 2. Migrations running on every boot

**Dev mode:** `alembic upgrade head` on every `make run` is a feature — it means you never debug a stale schema.

**Production mode:** running migrations from every replica on every deploy is a **recipe for deadlocks**. 10 replicas rolling out simultaneously, all racing to `ALTER TABLE` the same table, is how you take down your own service.

**What senior engineers do:**
- Extract migrations into a **separate deploy step** — a Kubernetes `Job`, a CI/CD pipeline stage, or a dedicated init container — that runs *exactly once* before the app pods come up.
- Use **advisory locks** (`SELECT pg_advisory_lock(<constant>)`) in Alembic's `env.py` if you can't separate the steps cleanly. First replica wins, the rest block until it's done.
- Keep migrations **backwards-compatible for at least one deploy cycle** so a rollback doesn't require a migration-down.

### 3. Port collisions and process orphans

**Dev mode:** a killed `make run` sometimes leaves orphaned uvicorn processes bound to `:8000`. Next `make run` fails with "Address already in use."

**Production:** the equivalent is a pod that didn't drain cleanly — connections still flowing, Kubernetes marks it terminating, but it takes 30s+ to actually exit. During that window, load balancer still routes to it.

**What senior engineers do:**
- Wire up `SIGTERM` handlers in uvicorn (FastAPI does this by default) so a `kill` actually drains in-flight requests and closes the DB pool.
- Set a **graceful shutdown timeout** lower than the platform's forcible-kill timeout (K8s default: 30s → set uvicorn's to 25s).
- In dev, run `fuser -k 8000/tcp` (Linux/macOS) or `netstat -ano | findstr :8000` + `taskkill` (Windows) when you suspect orphans.

## What fails in production

### The five-minute integration failure

Day 1 of a new hire: they run `make dev-setup-native` and it fails at `db-up-native` with `psql: role "postgres" does not exist`.

Why: their Postgres superuser is `mike` (matches their OS user — Homebrew's default). The baseline assumes `postgres`.

The error message in our `Makefile` is actionable (`export PGUSER=<your-name>` and retry), but it only works because someone thought about this failure mode *ahead of time*. A less careful setup script would produce the raw `psql` error, and the new hire loses 30 minutes on Google.

**Lesson:** every error message you emit is a future hour of someone's time. Spend 10 minutes writing a good one.

### The expired secret

`GROQ_API_KEY` in `.env` works for a week, then Groq rotates or expires it. First request fails with a 401 from Groq; Model Service propagates a generic 500 to the gateway; gateway propagates a generic 500 to the user.

**What's wrong:** no observability into *which* dependency failed, no fast-fail on a bad key at startup.

**What senior engineers do:**
- **Healthcheck against every external dependency at boot** — make a cheap test call to Groq on startup, cache the result for 60 seconds, fail `/health` if it's red.
- **Propagate upstream error codes** — Model Service should return 502 (Bad Gateway) to its caller when Groq is the problem, not 500. Gateway should preserve that distinction.
- **Alert on key expiration well before it happens** — Groq's dashboard shows key age; subscribe to rotation reminders.

## Senior engineer patterns

### Pattern 1 — Config-as-code, env-as-secret

Everything that isn't a secret goes in `config.py` (service URLs, feature flags, log levels). Everything that is a secret goes in `.env` (API keys, DB passwords, JWT signing keys). **Never mix them.**

Why: config changes get code-reviewed. Secrets rotate without code changes. Different lifecycle → different place.

### Pattern 2 — The "smoke test" script

Every service ships a `verify.py` (or equivalent) that hits a representative endpoint end-to-end. CI runs it post-deploy; devs run it after `make run` to confirm nothing regressed.

In this workshop, `lab/solution/verify.py` is that pattern in miniature.

### Pattern 3 — `make help` as documentation

The `Makefile` in this repo has `## Short description` comments on every target. `make help` greps them and prints a table. Cost: 30 seconds to add one line per target. Benefit: a self-updating runbook that never drifts from the code.

### Pattern 4 — Fail-fast preflights

`run_all.sh` checks Postgres before booting uvicorn. The production equivalent:
- Pod init container checks the DB connection
- Init container checks the message bus
- Init container checks the feature-flag service
- *Then* the main container starts

If any check fails, the pod never goes `Ready` — LB never sends traffic — no 500s for users.

## Monitoring needed

| Signal | Why | Tool |
|---|---|---|
| **Service health (per-service `/health`)** | Readiness probe; detects stuck startup | K8s `readinessProbe`, uptime monitor |
| **DB connection pool saturation** | Early signal for thread-starvation | Prometheus `sqlalchemy_pool_in_use` |
| **Migration version mismatch across replicas** | Rolling deploys can split-brain schema | Custom metric: replica reports `alembic_version` on startup |
| **Env config drift between envs** | "Works in staging, fails in prod" | Hash of config at boot, logged as a JSON field |
| **Startup time p99** | Slow preflights → slow rollouts | K8s pod-startup-latency metric |

## Common mistakes (first-week-of-the-job edition)

1. **Committing `.env`** — always in `.gitignore`, but someone always tries. Pre-commit hooks catch this; see Part III Task 11.
2. **Editing `.env.example` as if it were `.env`** — the template shouldn't have real secrets. If you do, rotate them immediately.
3. **Running both Docker Postgres and native Postgres simultaneously** — port collision on 5432. Pick one per dev session.
4. **`make db-migrate` before `make db-up`** — migrations need a target. The error is clear (`connection refused`) but disorienting on first encounter.
5. **Not activating the venv** — `make run` uses whatever `python` is in `PATH`. If that's the system Python, it doesn't have uvicorn. Symptom: `ModuleNotFoundError: No module named 'uvicorn'`.
6. **Frontend CORS errors** — `ALLOWED_ORIGINS` must include the dev URL. The error in the browser console tells you exactly which origin to add.

## Interview-style questions

1. **Why does `scripts/run_all.sh` do a TCP probe instead of `pg_isready -q`?**
   *Cross-platform: `pg_isready` isn't guaranteed to be on PATH on fresh Windows installs. The Python socket check works anywhere Python works.*

2. **Why is `alembic upgrade head` safe to run on every boot?**
   *Alembic tracks applied revisions in the `alembic_version` table. `upgrade head` when already at head is a no-op. Cost: ~100ms. Benefit: can't boot with a stale schema.*

3. **You have 10 replicas rolling out. How do you prevent them all racing on migrations?**
   *Extract migrations into a Kubernetes Job that runs once before the Deployment rollout, or gate migrations behind `pg_advisory_lock()` in Alembic's `env.py` so only one replica wins.*

4. **Why separate `config.py` and `.env`?**
   *Different lifecycles: config changes are code-reviewed and versioned; secrets rotate out-of-band. Keeping them separate means a secret rotation doesn't generate a code change and vice versa.*

5. **What's the failure mode if `Pydantic BaseSettings` wasn't validating `.env` at startup?**
   *Config errors would surface at first use (mid-request) instead of boot. Users would see 500s; logs would show `AttributeError` or `ValidationError` mid-request. Much harder to diagnose than a startup crash.*

## Further reading

- [12-Factor App — Config](https://12factor.net/config) — the canonical argument for env-driven config
- [Pydantic Settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — the library every service in this repo uses
- [Alembic cookbook — Running migrations in production](https://alembic.sqlalchemy.org/en/latest/cookbook.html#run-alembic-migrations-from-inside-a-python-script)
- `architecture/getting-started.md` — the long-form setup guide
- `architecture/design-decisions.md` — ADR-010 (async SQLAlchemy) and ADR-015 (client-side read history)
