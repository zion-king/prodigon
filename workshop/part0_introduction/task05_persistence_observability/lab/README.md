# Lesson 0.5 Lab — Persistence, Config, and Observability

**Duration:** ~30 minutes
**Format:** read-along, hands-on in the live repo. No starter or solution directories — you work directly against `baseline/`.

---

## Problem statement

You have read about the state layer and the cross-cutting concerns. Now you prove to yourself that you can:

1. Read an Alembic migration and map it back to the ORM models.
2. Generate a migration from a model change and inspect what autogenerate produces — **without applying it**.
3. Raise a custom error and trace it end-to-end through the HTTP response and the structured log.

Each exercise takes 5–10 minutes. No code lives in this lab directory; everything happens in `baseline/`.

---

## Setup

From the repo root, with the baseline stack running (see Lesson 0.1 if it isn't):

```bash
docker compose -f baseline/docker-compose.yml up -d postgres
```

You need the database up for all three exercises. You do **not** need the gateway container — for exercise 3 we will run the gateway locally against the containerized Postgres.

Make sure Alembic sees the right database:

```bash
export DATABASE_URL="postgresql+asyncpg://prodigon:prodigon@localhost:5432/prodigon"
```

(Windows PowerShell: `$env:DATABASE_URL = "postgresql+asyncpg://prodigon:prodigon@localhost:5432/prodigon"`.)

Run migrations if this is a fresh DB:

```bash
alembic -c baseline/alembic.ini upgrade head
```

---

## Exercise 1 — Inspect an Alembic migration

**Goal:** read a migration and explain, in your own words, what it does.

**Steps:**

1. List the migration history:

   ```bash
   alembic -c baseline/alembic.ini history
   ```

   You should see at least one revision — the initial baseline schema (`0001_initial`).

2. Show which revision the DB is currently at:

   ```bash
   alembic -c baseline/alembic.ini current
   ```

   This should match the head revision from step 1.

3. Open the revision file under `baseline/alembic/versions/`. Find the one named something like `20260423_0900_initial_baseline_schema.py`.

4. For each `op.create_table(...)` call, open `baseline/shared/models.py` and find the matching ORM class. Confirm that:
   - The column names match the `mapped_column(...)` declarations.
   - The foreign keys line up with the `relationship(...)` declarations.
   - The `op.create_index(...)` calls correspond to `index=True` on the model.

5. Write one sentence per table explaining what it stores. Example:

   > `batch_jobs`: a durable queue row per worker job, with JSONB `prompts`/`results` and a string `status` (pending → running → completed/failed).

**Expected output:** four sentences (one per table) and a clear mental map from migration DDL → ORM class → index.

---

## Exercise 2 — Generate a migration, inspect, revert

**Goal:** see what `alembic revision --autogenerate` actually produces. **You will not apply or commit this migration.**

**Steps:**

1. Create a scratch branch so you cannot accidentally keep the change:

   ```bash
   git checkout -b scratch/lesson-05-autogen-preview
   ```

2. Open `baseline/shared/models.py` and add a nullable field to the `User` class. For example, right after `display_name`:

   ```python
   nickname: Mapped[str | None] = mapped_column(String(80), nullable=True)
   ```

3. Generate the migration:

   ```bash
   alembic -c baseline/alembic.ini revision --autogenerate -m "add nickname to users"
   ```

4. Open the newly-created file under `baseline/alembic/versions/`. Read it carefully. You should see:
   - An `op.add_column("users", sa.Column("nickname", sa.String(length=80), nullable=True))` in `upgrade()`.
   - An `op.drop_column("users", "nickname")` in `downgrade()`.
   - A `revision` string and a `down_revision` pointing at `0001_initial`.

5. Notice what is **not** there: any comment explaining why, any data migration, any attempt at a default backfill. Autogenerate only diffs the schema.

6. **Revert everything.** Do not apply this migration, do not commit it, do not merge it.

   ```bash
   git checkout baseline/shared/models.py
   rm baseline/alembic/versions/*_add_nickname_to_users.py    # adjust filename
   git checkout main
   git branch -D scratch/lesson-05-autogen-preview
   ```

   (Windows PowerShell: `Remove-Item baseline\alembic\versions\*_add_nickname_to_users.py`.)

**Expected output:** you have seen, first-hand, what autogenerate produces for a trivial change. You noticed what it does *not* include (explanations, data migrations, defaults), and you are back on `main` with no changes.

---

## Exercise 3 — Raise a custom error, observe the structured log

**Goal:** prove that raising an `AppError` subclass produces a correct HTTP response **and** a correlated structured log line.

**Steps:**

1. Open `baseline/api_gateway/app/routes/health.py`. Add a temporary route at the bottom:

   ```python
   from shared.errors import JobNotFoundError

   @router.get("/health/demo-error")
   async def demo_error():
       raise JobNotFoundError("demo-job-id-123")
   ```

2. Run the gateway locally (not in Docker, so you see logs in your terminal):

   ```bash
   uvicorn api_gateway.app.main:app --app-dir baseline --port 8000
   ```

3. In another terminal, hit the route and capture response + headers:

   ```bash
   curl -i http://localhost:8000/health/demo-error
   ```

   You should see:
   - HTTP status `404`.
   - A JSON body shaped like `{"error": {"code": "JOB_NOT_FOUND", "message": "Job not found: demo-job-id-123", "request_id": "..."}}`.
   - An `X-Request-ID` response header matching the `request_id` in the body.

4. Switch back to the terminal running the gateway. Find the log line for this request. It should:
   - Be JSON.
   - Contain a `request_id` field matching the one in the response.
   - Contain the path `/health/demo-error` and status `404`.
   - Contain a reference to `JOB_NOT_FOUND` or the error class name.

5. Confirm you can `grep` the server logs by `request_id` and find exactly the one request. This is the debugging superpower the observability layer gives you.

6. **Clean up.** Remove the temporary route, remove the import if it is only used there, stop the gateway:

   ```bash
   git checkout baseline/api_gateway/app/routes/health.py
   ```

**Expected output:**
- HTTP 404 with a clean JSON error envelope.
- A single structured log line, correlated by `request_id`, showing the failure.
- The `request_id` appears in both the response header and the log.

---

## Bonus challenges

Pick one or both if you finish early.

### Bonus A — Hand-write an index migration

The baseline indexes `batch_jobs.status` already, but imagine it did not.

1. Generate an empty migration:
   ```bash
   alembic -c baseline/alembic.ini revision -m "add jobs status index"
   ```
2. In the generated file, write the `upgrade()` and `downgrade()` by hand:
   ```python
   def upgrade():
       op.create_index("ix_batch_jobs_status_manual", "batch_jobs", ["status"])
   def downgrade():
       op.drop_index("ix_batch_jobs_status_manual", table_name="batch_jobs")
   ```
3. Apply with `alembic upgrade head`, verify in `psql` with `\d batch_jobs`, then `alembic downgrade -1` to revert.

Point: you now know that **not every migration has to come from autogenerate**. Hand-written migrations are first-class.

### Bonus B — Switch log renderer via config

`baseline/shared/logging.py` uses `ConsoleRenderer` when `log_level=DEBUG`, `JSONRenderer` otherwise. That is a slightly awkward coupling.

1. Refactor `BaseServiceSettings` in `baseline/shared/config.py` to add a `log_format: str = "json"` field (accept `"json"` or `"console"`).
2. Change `setup_logging(...)` to accept the format string and pick the renderer from it, independent of log level.
3. Set `LOG_FORMAT=console` in your shell and restart a service — confirm you get colored, human-readable output even at `INFO` level.
4. Revert when done (or keep the change and submit a PR — it is a real improvement).

Point: config is a design tool, not just an env-var dump. Small config refactors unlock cleaner code paths.

---

## What you should walk away with

- You can read an Alembic migration file and map each `op.create_table` / `op.create_index` back to its ORM declaration.
- You know how to generate a migration, review it, and recognize what autogenerate misses.
- You have seen a custom error travel from a Python `raise` to an HTTP 404 response with a structured JSON body, and you found the correlated log line.
- You understand that `request_id` is the thread connecting all three layers — response headers, log lines, and (in later lessons) inter-service traces.

Next: Lesson 0.6 (frontend primer). Then Part I begins the real refactoring.
