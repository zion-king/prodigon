# Changelog

All notable changes to the Prodigon application are recorded here.
Entries are ordered **most recent first**.

The [Initial Baseline](#initial-baseline) section at the bottom captures the
state of the system immediately before frontend v1 overhaul. 
Use it as the reference point for everything that follows.

---

## How to maintain this file

- **Add new entries at the top**, just below this section. Newest first.
- Use a date heading in the form `## YYYY-MM-DD — Short title`. If two
  landings happen on the same day, give each its own heading; don't
  pile them into one.
- Group bullet points under one of: **Added**, **Changed**, **Fixed**,
  **Security**, **Deprecated**, **Removed**. Omit groups that don't apply.
- Cite file paths when the change is code-localised; say *why* the change
  was made when the *what* isn't self-evident.
- Move work out of the roadmap into here as it lands.
  Keep the roadmap forward-looking and the changelog backward-looking.

---

## 2026-04-23 — Workshop Part 0: Baseline Introduction

### Added
- **`workshop/part0_introduction/`** — six-lesson preparatory module that
  tours the baseline system before attendees tackle Part I refactors. Follows
  Part I's file conventions exactly (`README.md` / `slides.md` /
  `production_reality.md` / `lab/`), so the Topics Panel and Content Viewer
  render it with zero component changes.
  - **0.1 Getting Started** — dev environment walkthrough (Makefile targets,
    `.env`, Postgres Docker vs native, `make health`). Full lab with
    `starter/` + `solution/` including a `verify.py` smoke test.
  - **0.2 System Architecture Tour** — 3-service split, `shared/` module,
    request pipeline. Lightweight lab.
  - **0.3 Service Lifecycle & Dependency Injection** — FastAPI lifespan,
    module-global init, `Depends()`. Full lab: attendees wire a
    request-counter dep through the DI system and verify with pytest.
  - **0.4 Request Flows — Sync, Streaming, Jobs** — trace a request through
    sync `/generate`, SSE `/generate/stream`, and the Postgres-backed job
    queue; watch `request_id` propagate across services. Lightweight lab.
  - **0.5 Persistence, Config, and Observability** — ORM models, Alembic,
    Pydantic Settings, structlog, `AppError` hierarchy. Lightweight lab.
  - **0.6 Frontend Primer** — three-panel layout, Zustand stores, SSE token
    reconciliation, localStorage keys. Lightweight lab.
- **`workshop/README.md`** — Part 0 section added at the top of the Parts
  listing with a prominent "New to the baseline?" callout directing newcomers
  to Part 0 before Part I. Updated the Suggested Workshop Formats section
  with a Part-0-only half-day format and a Part-0-plus-Part-I full-day format.

### Changed
- **`frontend/src/lib/topics-data.ts`** — extended `PartId` to
  `'0' | 'I' | 'II' | 'III'`, generalised `makeSubtopics` to accept a
  `partPrefix` parameter (defaults to `'part1_design_patterns'` so existing
  Part I callers are untouched), prepended six Part 0 task entries with
  decimal `taskNumber`s (0.1–0.6) for clean display, and added Part 0 to
  `PART_LABELS` + `TASKS_BY_PART`.
- **`frontend/src/pages/topics-page.tsx`** and
  **`frontend/src/components/topics/topic-tree.tsx`** — `PARTS` array bumped
  from `['I', 'II', 'III']` to `['0', 'I', 'II', 'III']` so the Topics page
  and Topics Panel accordion render Part 0 first.

### Why
Parts I–III teach refactors of the baseline, but the repo had no orientation
material for the baseline itself. A newcomer landing on Task 1 (REST vs gRPC)
already had to understand the 3-service split, `shared/`, lifespans, DI, all
three request flows, Postgres-backed persistence, migrations, structured
logging, and the error hierarchy — a cliff. Part 0 flattens that cliff into
six digestible lessons, so attendees arrive at Task 1 with a mental model
instead of a guess. The Topics Panel surfaces Part 0 first, so the
guided reading path is obvious without any curriculum prose.

---

## 2026-04-23 — Local dev workflow: Postgres prerequisites wired into Make/setup

### Added
- **`make db-up` / `make db-down`** — spin up just the `postgres` service from
  `baseline/docker-compose.yml` so bare-metal `make run` has a database to
  talk to without running the full stack in Docker. `db-up` blocks until
  `pg_isready` reports healthy (30s timeout).
- **`make db-up-native`** — the no-Docker alternative. Assumes a native
  Postgres is already installed and running on `localhost:5432` (EDB
  installer on Windows, Homebrew on macOS, distro package on Linux) and
  runs `scripts/db_bootstrap.sql` via `psql` to idempotently create the
  `prodigon` role + `prodigon` database. Fails fast with install/start
  hints per platform if `pg_isready` can't find a server.
- **`scripts/db_bootstrap.sql`** — guarded `CREATE ROLE` / `CREATE DATABASE`
  for the native path. Safe to re-run; `db-up-native` invokes it every time.
- **`make db-migrate`** — thin wrapper around `cd baseline && alembic upgrade head`.
  Idempotent; safe to run repeatedly. Works against both Docker and native
  Postgres since it only cares about `$DATABASE_URL`.
- **`make db-revision M="message"`** — autogenerate a new Alembic revision
  against the current models.
- **`make dev-setup` / `make dev-setup-native`** — one-shot targets that
  chain `setup` + (`db-up` or `db-up-native`) + `db-migrate`. Pick whichever
  matches your Postgres install.
- **Postgres preflight in `scripts/run_all.sh`** — opens a TCP socket to the
  host/port parsed out of `DATABASE_URL` and fails fast with an actionable
  hint (`make db-up` / `make db-up-native`) instead of letting uvicorn boot
  into a broken state. The script now also runs `alembic upgrade head` on
  every boot (idempotent at head), so a stale schema can't silently drift.

### Changed
- **`.env.example`** now includes `DATABASE_URL` with a comment pointing at
  `make db-up` / `make db-migrate`, flips `QUEUE_TYPE` default from `memory`
  to `postgres` (the durable SKIP LOCKED queue introduced in the persistence
  landing), and adds `http://localhost:5173` to `ALLOWED_ORIGINS` so the
  Vite dev server can hit the gateway without CORS rejection.
- **`scripts/setup.sh`** sources `.env`, probes Postgres via `pg_isready`
  (with a Python socket fallback for machines that don't ship it), runs
  `alembic upgrade head` when reachable, and prints next-steps that cover
  both Docker (`db-up`) and native (`db-up-native`) paths.

### Why
Postgres persistence (previous entry) assumed a Docker-first workflow — the
gateway/worker Dockerfiles run `alembic upgrade head` on boot. Developers
running `make run` directly hit 500s on first request because migrations
never ran and `DATABASE_URL` wasn't in `.env.example`. The native path was
added so contributors without Docker installed can still get a working
local stack — install Postgres via their platform's package manager,
`make db-up-native` provisions the role/db, `make db-migrate` applies the
schema, `make run` just works.

---

## 2026-04-23 — Frontend: Chat sessions migrated from in-memory to server-backed

### Added
- **`frontend/src/api/chat.ts`** — typed wrappers around `/api/v1/chat/*`
  (`listSessions`, `getSession`, `createSession`, `updateSession`,
  `deleteSession`, `appendMessage`), plus DTO→store-shape mappers
  (`mapSessionSummary`, `mapSessionDetail`). The server sends ISO 8601
  timestamps; mappers convert to epoch ms so the rest of the app doesn't
  need to care about the boundary.
- **`patch` and `del` verbs on `HttpClient`** (`frontend/src/api/client.ts`).
  `del` doesn't parse a body (gateway returns 204); the generic `request`
  method gained a `parseJson` flag to support that.
- **Lazy message loading** on the chat store: `setActiveSession(id)` is
  now async, and the first time a session becomes active it fetches
  `GET /api/v1/chat/sessions/:id` to populate messages. The sessions
  list endpoint returns summaries only, so the initial payload stays
  small even if a user has many sessions.

### Changed
- **`frontend/src/stores/chat-store.ts`** is a near-total rewrite. The
  store is now a cache of server state; every mutation persists through
  the chat API:
  - `hydrate()` — pulls the session list on app mount, auto-selects the
    most recent session, eagerly loads its messages so first paint shows
    real content (not an empty state).
  - `createSession` / `deleteSession` / `renameSession` — async,
    optimistic locally, confirmed on the server. Deletes roll back the
    local state if the server call fails.
  - `persistUserMessage(sessionId, content)` — optimistic local add with
    a temp id, followed by POST; the temp id is swapped for the server
    UUID when the response returns.
  - `addAssistantPlaceholder` + `appendToMessage` + `updateMessage` +
    `persistAssistantMessage` — the streaming flow. The assistant turn
    runs entirely against a client-side temp id until `onDone`, at
    which point `persistAssistantMessage` POSTs the completed content
    and reconciles the id. Failed streams are deliberately not saved.
  - Auto-titling the session from the first user message still works
    client-side; the new title is pushed to the server via PATCH so the
    sidebar stays consistent.
- **`frontend/src/App.tsx`** calls `useChatStore.getState().hydrate()`
  in a mount-effect. The store guards against duplicate invocations so
  re-renders don't re-fetch.
- **`frontend/src/pages/chat-page.tsx`** waits for `hydrated` before
  deciding whether to create a new session, so returning users don't
  get a spurious "New Chat" row every page load.
- **`frontend/src/components/chat/chat-view.tsx`** swapped the old
  `addMessage`/`updateMessage` pair for the new
  `persistUserMessage` + `addAssistantPlaceholder` +
  `persistAssistantMessage` flow.
- **`frontend/src/components/layout/sidebar.tsx`**,
  **`frontend/src/components/layout/mobile-nav.tsx`**,
  **`frontend/src/components/ui/command-palette.tsx`**,
  **`frontend/src/components/topics/content-viewer.tsx`** — updated for
  the new async store surface (`await createSession()`,
  `void setActiveSession(id)`, `void deleteSession(id)`).
- **`ChatSession`** gains a `messageCount: number` field populated from
  the server so the sidebar and dashboard can show totals for sessions
  whose messages haven't been lazy-loaded yet. Used in
  `command-palette.tsx` (recent-session row) and `dashboard-view.tsx`
  (total-messages aggregate) — previously both read
  `s.messages.length` and undercounted.

### Notes
- Chat sessions now survive page refresh, tab close, and
  browser-switch. Clearing localStorage no longer loses history — the
  server is the source of truth.
- Authentication is still not wired; every session is attributed to the
  seeded default user (`00000000-0000-0000-0000-000000000001`). Once
  Part III (security) lands, swapping to a real authenticated user id
  becomes a one-line change in
  `baseline/api_gateway/app/routes/chat.py::_repo`.
- Partial streaming responses are intentionally not persisted. If the
  user refreshes mid-stream, they lose the in-flight assistant turn.
  This is a deliberate simplification — saving half-rendered markdown
  or truncated code blocks is worse UX than losing the turn.

---

## 2026-04-23 — Backend: Postgres persistence (chat sessions, messages, batch jobs, users)

### Added
- **New Postgres service** in `baseline/docker-compose.yml`
  (`postgres:16-alpine`, named volume `postgres-data`, `pg_isready`
  healthcheck). `api-gateway` and `worker-service` now gate startup on
  `postgres: condition: service_healthy` via compose, so they never race
  the DB.
- **`baseline/shared/db.py`** — shared async SQLAlchemy engine, session
  factory, and `DeclarativeBase`. One engine per process,
  `expire_on_commit=False` for async-friendly ORM objects,
  `pool_pre_ping=True` to survive DB restarts. Exposes `get_session` as a
  FastAPI dependency and `dispose_engine` for lifespan shutdown.
- **`baseline/shared/models.py`** — ORM models for the four baseline
  tables:
  - `users` — minimal account row; a seeded default user
    (`00000000-0000-0000-0000-000000000001`) attributes ownership until
    Part III's auth work replaces it.
  - `chat_sessions` — per-user conversation threads with `title` and
    optional per-session `system_prompt`.
  - `chat_messages` — ordered turns within a session; `role` ∈
    `{user, assistant, system}`; JSONB `meta` for token-usage metadata.
  - `batch_jobs` — durable replacement for the in-memory worker queue;
    JSONB `prompts`/`results`, status stored as `VARCHAR` for migration
    simplicity. Foreign keys cascade appropriately (`chat_messages` ON
    DELETE CASCADE; `batch_jobs.user_id` ON DELETE SET NULL).
- **Alembic migrations** — `baseline/alembic.ini`, `baseline/alembic/env.py`
  (async-aware via `run_sync`), and the initial revision
  `20260423_0900_initial_baseline_schema.py`. The migration creates all
  four tables plus indexes on high-selectivity columns
  (`chat_sessions.user_id`, `chat_messages.session_id`,
  `chat_messages.created_at`, `batch_jobs.status`,
  `batch_jobs.created_at`, `batch_jobs.user_id`) and seeds the default
  user. `env.py` reads `DATABASE_URL` from env so compose and local dev
  share the same migration script.
- **`baseline/api_gateway/Dockerfile`** runs `alembic upgrade head`
  before starting uvicorn — the first gateway container that boots
  against a fresh DB applies migrations idempotently, so there is no
  manual operator step.
- **`baseline/worker_service/app/services/queue.py`** gains a
  `PostgresQueue` implementation alongside the existing `InMemoryQueue`.
  Dequeue uses `SELECT ... FOR UPDATE SKIP LOCKED`, which lets multiple
  worker processes compete on the same `batch_jobs` table safely — each
  pending row goes to exactly one worker, and concurrent consumers skip
  past locked rows instead of blocking. Worker `queue_type` now defaults
  to `postgres`; `memory` remains for no-DB quick-start demos.
- **Chat persistence endpoints** in the gateway (`/api/v1/chat/...`):
  - `POST   /sessions` — create a session
  - `GET    /sessions` — list sessions (metadata + message counts,
    ordered by recent activity)
  - `GET    /sessions/{id}` — session detail including ordered messages
  - `PATCH  /sessions/{id}` — rename / update `system_prompt`
  - `DELETE /sessions/{id}` — cascades to messages
  - `POST   /sessions/{id}/messages` — append a turn
  Implemented behind a `ChatRepository` service object
  (`baseline/api_gateway/app/services/chat_repository.py`) so route
  handlers stay focused on HTTP concerns and tests can stub the
  repository directly.
- **Chat Pydantic schemas** in `baseline/shared/schemas.py`:
  `ChatMessageRole`, `ChatMessageCreate`, `ChatMessageOut`,
  `ChatSessionCreate`, `ChatSessionUpdate`, `ChatSessionOut`,
  `ChatSessionDetail`.

### Changed
- **`baseline/worker_service/app/config.py`** — default `queue_type`
  flipped from `"memory"` to `"postgres"` so baseline behaviour is
  durable out of the box. `"memory"` remains opt-in.
- **`baseline/worker_service/app/dependencies.py`** — `init_dependencies`
  now threads `shared.db.get_sessionmaker()` into the queue factory when
  `queue_type == "postgres"`, so the queue and any future DB-aware
  worker code share one connection pool.
- **Lifespan shutdown** in both `api_gateway/app/main.py` and
  `worker_service/app/main.py` now calls `await dispose_engine()` so the
  pool closes cleanly on `docker stop`.
- **`pyproject.toml`** and both services' `requirements.txt` pick up
  `sqlalchemy[asyncio]>=2.0.30`, `asyncpg>=0.29.0`, `alembic>=1.13.0`.

### Notes
- The frontend still persists chat sessions to `localStorage`; wiring
  the React chat store to the new endpoints is follow-up work,
  deliberately out of scope for this landing. Backend capability is in
  place; the frontend migration will be its own changelog entry.
- Auth is not yet real. Every write attributes to the seeded default
  user. The repository layer already scopes reads and writes by
  `user_id`, so swapping to a real `get_current_user` dependency in
  Part III is a one-line route change per endpoint.
- Baseline throughput (human-scale batches) doesn't justify Redis for
  the job queue yet. Postgres + `SKIP LOCKED` is well within its
  capability envelope. Task 8 (Load Balancing & Caching) is where we
  introduce Redis for latency-sensitive paths.

---

## 2026-04-23 — Backend: Client-disconnect handling on SSE streaming

### Fixed
- **`baseline/model_service/app/routes/inference.py`** and
  **`baseline/api_gateway/app/routes/generate.py`** now check
  `await request.is_disconnected()` inside their streaming loops and
  return early when the downstream client has gone away.
- Before this change, closing a browser tab mid-generation left the gateway
  still reading bytes from the model service and the model service still
  pulling tokens from Groq — generating (and billing) output that no one
  would ever see. Both layers now abort cleanly within one token of the
  TCP FIN and emit structured abort logs (`stream_aborted`,
  `proxy_stream_aborted`) with `tokens_sent` / `bytes_proxied` for cost
  observability. Happy-path completion logs (`stream_completed`,
  `proxy_stream_completed`) were added for parity.
- The streaming handlers deliberately use `except Exception` (not
  `except BaseException`) so `asyncio.CancelledError` — which in Python
  3.8+ is a `BaseException` subclass — skips our error handler and
  propagates to Starlette's task runtime, letting it cancel the Groq
  async iterator cleanly. A `noqa: BLE001` with comment documents the
  intent so a later "tidy up" refactor doesn't regress it.

### Changed
- Rename the Pydantic body parameter in both streaming endpoints from
  `request` to `body`, so the handlers can also accept a `Request` object
  (`http_request`) without a name collision.

---

## 2026-04-22 — Mermaid diagram validation and error UI

### Fixed
- **`frontend/src/components/chat/markdown-renderer.tsx`**: mermaid v11's
  `render()` does **not** throw on invalid syntax — it silently returns an
  SVG whose visible text is "Syntax error in text mermaid version 11.14.0".
  Our `try/catch` never fired, so the error SVG was injected into the DOM
  and users saw an unhelpful message with no indication of what went wrong.
- Added `await mermaid.parse(source)` as a validation gate before
  `mermaid.render()`. `parse()` does throw, with a specific message such as
  *"Parse error on line 2: expecting 'NODE', got 'PARTICIPANT'"* — exactly
  what's needed to diagnose LLM output that mixes dialects (e.g. `graph LR`
  declaration with `participant`/`->>` sequenceDiagram syntax).
- The error UI now surfaces mermaid's actual parser message above the
  collapsed `<details>` element containing the raw source.

---

## 2026-04-22 — SSE token encoding fix (newlines preserved)

### Fixed
- **`baseline/model_service/app/routes/inference.py`** — tokens on the wire
  are now emitted as `data: {json.dumps(token)}\n\n` rather than
  `data: {token}\n\n`. Previously, any `\n` character inside a streamed
  token (which is common in markdown output — headings, fenced code blocks,
  list separators) was consumed by the SSE protocol as the `data:`-field
  terminator and silently dropped. The result was chat responses rendered
  as one long run-on paragraph with all markdown structure destroyed.
- **`frontend/src/api/endpoints.ts`** — the SSE consumer now calls
  `JSON.parse()` on each non-sentinel `data:` payload to recover the real
  string with newlines, quotes, and escapes intact. Wrapped in a try/catch
  that falls back to the raw payload, so an older backend emitting
  un-encoded tokens degrades gracefully instead of hard-failing.
- The `[DONE]` and `[ERROR]` sentinels remain plain strings (they never
  contain newlines, and are trivially distinguishable from JSON since
  neither starts with `"`).

---

## 2026-04-21 — Markdown rendering for chat responses

### Added
- **`frontend/src/components/chat/message-bubble.tsx`** renders assistant
  messages through the existing `MarkdownRenderer` component (user messages
  remain plain text with `whitespace-pre-wrap`). Chat now gets the same
  formatting treatment that workshop-topic pages enjoy: GFM tables,
  syntax-highlighted code blocks, mermaid diagrams, headings, lists, etc.
- **`MarkdownRenderer`** gained a `streaming?: boolean` prop. While true,
  `MermaidBlock` short-circuits to a `PlainBlock` instead of calling
  `mermaid.parse()` — partial mermaid source during streaming would always
  fail to parse, spraying the UI with errors on every token. The final
  render happens once streaming flips to false.
- `useDeferredValue(content)` is applied to the markdown source so React
  can re-parse large ASTs at lower scheduler priority during rapid token
  streams, preventing visible jank without changing perceived latency.

---

## 2026-04-20 — Polished Frontend v1

Large-scale overhaul of `frontend/` to turn a functional chat demo into a
workshop-grade teaching platform. No new npm dependencies were introduced
for the core features (all built on existing React, Zustand, Tailwind,
lucide-react, react-markdown); `remark-gfm` and `mermaid` were added for
the content-rendering work.

### Added

**Workshop browser**
- Right-side collapsible **Topics Panel**
  (`frontend/src/components/topics/topics-panel.tsx`,
  `topic-tree.tsx`) with accordion-style Part → Task hierarchy,
  keyboard navigation (Arrow keys, Enter, Escape), per-Part progress
  badges (`X/Y read`), and a read-history store persisted to
  `localStorage` (`frontend/src/stores/topics-store.ts`).
- **Workshop routes** inside the shared AppShell: `/topics` (grid of
  task cards grouped by Part, with Coming-Soon overlays for Parts II/III),
  `/topics/:taskId` (2×2 grid of subtopic cards), and
  `/topics/:taskId/:subtopicId` (content page).
- **ContentViewer** (`frontend/src/components/topics/content-viewer.tsx`)
  with breadcrumb navigation, difficulty/duration badges, "Chat About
  This" and "Mark as Read" actions, IntersectionObserver-based
  auto-mark-as-read on scroll to bottom, and prev/next subtopic pagination.
- **"Chat About This"** — seeds a fresh chat session with a topic-scoped
  `topicSystemPrompt` in the settings store, kept separate from the
  user's configured `systemPrompt` so it's one-shot and clears after use.

**Command palette**
- Cmd+K / Ctrl+K opens `command-palette.tsx` with results grouped as
  Topics, Sessions, and Actions (New Chat, Dashboard, Toggle Theme, etc.).
  Arrow-key navigation, Enter to activate, Escape to close, focus trap,
  `aria-live="polite"` announcements on results update.

**Toast notifications**
- `frontend/src/stores/toast-store.ts` (max-3 queue; oldest drops when full).
- `frontend/src/components/ui/toast.tsx` — fixed bottom-right, slide-up
  animation, type-colored (success/error/info/warning) left border + icon,
  auto-dismiss with configurable duration, X dismiss button.
- Wired triggers: clipboard copy (markdown code blocks), chat export,
  batch-job completion/failure (`use-job-poll.ts`), topic "Chat About
  This", "Mark as Read".

**Markdown rendering stack**
- `MarkdownRenderer` (`frontend/src/components/chat/markdown-renderer.tsx`)
  built on `react-markdown` + `remark-gfm` for GFM tables.
- **Syntax highlighting** via `react-syntax-highlighter` (Prism), with a
  language-alias map (`sh`/`shell`/`console` → `bash`, `proto`/`proto3` →
  `protobuf`, `tf`/`terraform` → `hcl`, `dockerfile` → `docker`, etc.).
- **Mermaid diagrams** via dynamic `import('mermaid')`, so each diagram
  type lazy-splits into its own Vite chunk. Light/dark theme auto-detected
  from the `<html class="dark">` marker.
- **PlainBlock** component for fenced code blocks *without* a language tag
  (output, logs, ASCII art) — visually distinct from highlighted
  `CodeBlock`; uses `whitespace-pre` to preserve indentation exactly.
- Full GFM table components (`table/thead/tbody/tr/th/td`) with scrollable
  wrappers, hover-highlighted rows, and uppercase header cells.

**Backend — workshop content endpoint**
- **`baseline/api_gateway/app/routes/workshop.py`**:
  `GET /api/v1/workshop/content?path=<relative>.md` serves markdown files
  from `workshop/` with path-traversal defense: rejects `..`, absolute
  paths, and non-`.md` files; asserts the resolved path is still under
  `_WORKSHOP_ROOT` via `Path.relative_to()`; returns 400 `INVALID_PATH`
  or 404 `NOT_FOUND`.

**Chat enhancements**
- **Export chat session as markdown** (download button in chat header;
  `frontend/src/components/chat/chat-view.tsx`) — triggers `toast.success`.
- **Session stats strip** above the input: message count, token estimate,
  relative updated-at time.
- **Input token estimate** — below the textarea, `~N tokens` shown when
  input length > 20 chars (~`len/4`).
- **Onboarding banner** (first-visit only, gated on `prodigon-onboarded`
  in localStorage) prompting new users to open the Topics Panel.

**Primitives and polish**
- `Skeleton` component with shimmer animation (gradient bg-[length:200px]
  + `animate-shimmer` keyframe).
- `Badge` component with variants: default, secondary, success, warning,
  coming-soon (dashed border).
- Inter font via Google Fonts CDN (replaces system-font stack).
- CSS tokens for `--gradient-from` / `--gradient-to`, plus `.gradient-text`
  and `.glass` utility classes.
- New Tailwind keyframes: `slide-up`, `shimmer`, `scale-in`, `fade-in`.

**Accessibility**
- Skip-navigation link (sr-only, focus-visible) as the first focusable
  element in `AppShell`.
- `aria-current="page"` on active sidebar and mobile-nav items.
- Focus trap in settings dialog and command palette; focus restoration
  on close.
- `aria-live="polite"` screen-reader announcements when assistant
  streaming starts.
- `aria-expanded` on Topic-Tree accordion headers.

**Keyboard shortcuts** (via existing `useKeyboardShortcuts` hook)
- `Cmd+K` — open command palette
- `Cmd+Shift+E` — export current chat session
- `Cmd+/` — toggle sidebar
- `Cmd+Shift+T` — toggle topics panel
- `Escape` — close topmost open modal/overlay

### Changed
- Layout became **three-panel**: left sidebar (sessions + nav) / main
  content / right Topics Panel. Desktop: right panel collapses to zero
  width. Mobile: right panel overlays with backdrop and auto-closes on
  route change.
- **Header** gained a ⌘K search button (opens command palette), a
  BookOpen button to toggle the Topics Panel (`aria-pressed`-bound),
  and the Settings button's click handler — previously a no-op — now
  actually opens the dialog.

---

## Initial Baseline

This section describes the system state **immediately before** the
frontend overhaul above. Everything below was in place;
everything above has been added since.

### Backend (monorepo under `baseline/`)

- **`api_gateway/`** — FastAPI gateway exposing `/api/v1/generate` (sync
  text generation), `/api/v1/generate/stream` (SSE streaming with raw-text
  token wire format), and `/api/v1/jobs` batch-job submit/status. Stamps
  an `X-Request-ID` header on every request. Global exception handler
  emits a unified error envelope. CORS configured from settings.
- **`model_service/`** — FastAPI service wrapping the Groq SDK.
  `ModelManager` handles model selection with a hard-coded fallback model
  on primary-model failure. Exposes `/inference` and `/inference/stream`;
  no auth, no per-user quota.
- **`worker_service/`** — FastAPI service backed by an **in-memory**
  `asyncio.Queue` (`InMemoryQueue`). Processes batch jobs serially.
  Jobs are lost on restart — this is a known baseline limitation to be
  addressed in the Postgres landing immediately following this changelog
  entry.
- **`shared/`** — `schemas.py` (Pydantic request/response models),
  `http_client.py` (ServiceClient wrapper around httpx with per-call
  timeouts and structured error surfacing), `logging.py` (structlog with
  JSON output in production, ConsoleRenderer in dev).
- **`infra/`** — `docker-compose.yml` for all three services plus an
  unused Redis container; nginx reverse-proxy config with no rate
  limiting; per-service Dockerfiles.

### Frontend (`frontend/`)

- React 18 + TypeScript + Vite + Zustand + Tailwind.
- Basic chat interface with SSE streaming, rendering responses as
  **plain text only** — no markdown, no syntax highlighting, no diagrams.
- Dashboard page (health and stats), batch-jobs page, session sidebar.
- Session state persisted to localStorage.
- Light/dark theme toggle.
- No workshop browser, no command palette, no toasts, no content viewer,
  no onboarding UI, no accessibility attributes.

### Workshop content (`workshop/`)

- **Part I — Design Patterns** complete. Each task directory contains
  `README.md` (overview), `slides.md`, `production_reality.md`, and a
  `lab/` subdirectory with starter and solution code:
  - Task 1 — REST vs gRPC
  - Task 2 — Microservices vs Monolith
  - Task 3 — Batch vs Real-time vs Streaming
  - Task 4 — FastAPI Dependency Injection
- **Part II — Scalability & Performance** and **Part III — Security** not yet implemented.

### Deliberate omissions (on the roadmap, **not** tracked as gaps)

These are intentionally absent from the baseline and will be addressed
by specific workshop tasks:

| Capability | Workshop destination |
|---|---|
| Authentication / JWT / RBAC | Part III, Task 9 |
| HTTPS / CORS hardening / rate limiting | Part III, Task 10 |
| Secrets management (Vault / AWS SM) | Part III, Task 11 |
| Code profiling & optimization | Part II, Task 5 |
| Concurrency & parallelism (threads/processes/async) | Part II, Task 6 |
| Memory management & lazy loading | Part II, Task 7 |
| Load balancing & Redis caching | Part II, Task 8 |
| Retries / circuit breaking / timeouts | Future (post-Part II) |
| Prometheus metrics / distributed tracing | Future (observability phase) |
