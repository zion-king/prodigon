<!-- Version: v0 | Last updated: 2026-04-16 | Status: current -->

# Getting Started

This is the step-by-step setup guide for the **prod-ai-system-design** workshop codebase. Follow every step in order. Every command is copy-pasteable. A developer following this guide should be able to set up the entire system without hitting any blockers.

---

## Prerequisites

| Tool | Version | Check Command | Install From |
|------|---------|--------------|-------------|
| Python | 3.11+ | `python --version` | python.org |
| Node.js | 20+ | `node --version` | nodejs.org (LTS) |
| npm | 10+ | `npm --version` | Included with Node.js |
| Git | Any | `git --version` | git-scm.com |
| Docker | Optional | `docker --version` | docker.com (Docker Desktop) |

> **Important:** Python and Node.js are separate runtimes. Python runs the backend services. Node.js runs the frontend build tooling. Both are required for full-stack development.

---

## Step 1: Clone the Repository

```bash
git clone <repo-url>
cd prod-ai-system-design
```

---

## Step 2: Python Backend Setup

### 2a. Create a virtual environment

```bash
python -m venv venv
```

If `python` doesn't work, try `python3`.

### 2b. Activate the virtual environment

| Platform | Shell | Command |
|----------|-------|---------|
| Windows | Git Bash | `source venv/Scripts/activate` |
| Windows | PowerShell | `.\venv\Scripts\Activate.ps1` |
| Windows | CMD | `venv\Scripts\activate.bat` |
| macOS/Linux | bash/zsh | `source venv/bin/activate` |

You should see `(venv)` at the start of your prompt.

> **CRITICAL: You must activate the venv before running ANY `make` commands.** The Makefile uses bare `python` which resolves to the system Python. The system Python does not have uvicorn or other dependencies installed. If you see `No module named uvicorn`, your venv is not activated.

### 2c. Install Python dependencies

```bash
pip install --upgrade setuptools pip
pip install -e ".[dev]"
```

> **Known Issue (Windows Git Bash):** If you run `scripts/setup.sh`, the command `pip install -e "$PROJECT_ROOT[dev]"` may fail with "is not a valid editable requirement." This is because Git Bash rewrites the path, making pip unable to parse the `[dev]` extras specifier.
>
> **Fix:** Always `cd` to the project root first and use a relative path:
> ```bash
> cd /c/Users/yourname/.../prod-ai-system-design
> pip install -e ".[dev]"
> ```

> **Note (already fixed in repo):** The `pyproject.toml` uses `build-backend = "setuptools.build_meta"` (not `setuptools.backends._legacy:_Backend` which doesn't exist in all setuptools versions) and includes `[tool.setuptools.packages.find] where = ["baseline"]` to prevent the "Multiple top-level packages discovered" error. These fixes are already applied -- this note is for maintainers.

---

## Step 3: Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

- **Required:** Set `GROQ_API_KEY=your-groq-api-key-here` (get one free at [console.groq.com](https://console.groq.com))
- **Alternative:** Set `USE_MOCK=true` to use the mock client (no API key needed, returns canned responses)

All other defaults are fine for local development.

---

## Step 4: Run Backend Services

Make sure your venv is activated (you should see `(venv)` in your prompt).

```bash
make run
```

This starts all 3 services via `scripts/run_all.sh`:

- **Model Service** on http://localhost:8001
- **Worker Service** on http://localhost:8002
- **API Gateway** on http://localhost:8000 (starts 2s after others)

### Verify

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status":"healthy","service":"api-gateway","version":"0.1.0","environment":"development"}
```

### Explore the API

Open http://localhost:8000/docs in your browser for the Swagger UI.

### Test inference

```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello!", "max_tokens": 100}'
```

### Test streaming

```bash
curl -N -X POST http://localhost:8000/api/v1/generate/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a haiku"}'
```

---

## Step 5: Frontend Setup

**Open a NEW terminal** (keep the backend running in the first one).

### 5a. Install Node.js dependencies

```bash
cd frontend
npm install
```

> **Note:** `npm audit` may report moderate vulnerabilities:
> - **esbuild** (development server only) -- does NOT affect production builds
> - **prismjs** (in react-syntax-highlighter) -- DOM clobbering, low risk for this app
>
> These are acceptable for a workshop codebase. Do NOT run `npm audit fix --force` as it may introduce breaking changes.

### 5b. Start the Vite dev server

```bash
npm run dev
```

Output:
```
VITE v5.4.x  ready in XXX ms
  ➜  Local:   http://localhost:5173/
```

### 5c. Open the app

Navigate to http://localhost:5173 in your browser.

You should see the Prodigon chat interface. If the backend is running, the connection banner should NOT appear. Try typing a message and pressing Enter to test streaming.

---

## Step 6: Docker Mode (Alternative)

If you prefer to run everything in containers:

```bash
# From the project root
cd baseline
docker-compose up --build
```

This starts:

| Service | Port |
|---------|------|
| nginx | :80 |
| api-gateway | :8000 |
| model-service | :8001 |
| worker-service | :8002 |
| frontend | :3000 |
| redis | :6379 |

Access the app at http://localhost:80.

> **Note:** You still need a `.env` file with `GROQ_API_KEY` (or `USE_MOCK=true`) in the project root.

---

## Troubleshooting

### "No module named uvicorn" when running `make run`

Your virtual environment is not activated. Run `source venv/Scripts/activate` (Windows Git Bash) or the equivalent for your platform. You should see `(venv)` in your prompt.

### "is not a valid editable requirement" during `pip install`

Windows Git Bash munges paths with brackets. `cd` to the project root first, then run `pip install -e ".[dev]"` with a relative path.

### "Cannot import setuptools.backends._legacy"

The `pyproject.toml` `build-backend` must be `"setuptools.build_meta"`. This is already fixed in the repo. If you see this error, pull the latest code.

### "Multiple top-level packages discovered in a flat-layout"

The `pyproject.toml` needs `[tool.setuptools.packages.find] where = ["baseline"]`. This is already fixed in the repo. If you see this error, pull the latest code.

### Vite shows "ECONNREFUSED /health" errors

The backend is not running. The frontend's health poll is trying to reach the API Gateway. Start the backend in a separate terminal with `make run`.

### npm audit reports moderate vulnerabilities

The esbuild vulnerability only affects the Vite development server (not production). The prismjs vulnerability is in react-syntax-highlighter (low risk). Neither affects production builds. Do not run `npm audit fix --force`.

### Frontend components show "No matching export" errors

Some components use `export default` while others use named exports. If you see this error after modifying imports, check whether the target file uses `export default class/function X` (import as `import X from ...`) or `export function X` / `export const X` (import as `import { X } from ...`).

---

## Quick Reference: Make Targets

| Command | Description |
|---------|-------------|
| `make setup` | Install Python deps |
| `make run` | Start all backend services |
| `make run-gateway` | Start API Gateway only |
| `make run-model` | Start Model Service only |
| `make run-worker` | Start Worker Service only |
| `make run-docker` | Docker Compose up |
| `make test` | Run pytest |
| `make lint` | Run ruff linter |
| `make health` | Check service health |
| `make install-frontend` | npm install |
| `make run-frontend` | npm run dev |
| `make build-frontend` | npm run build |
| `make clean` | Remove caches |
| `make help` | Show all targets |

---

## Setup Decision Flowchart

```mermaid
flowchart TD
    A[Start] --> B{Do you want Docker?}
    B -->|Yes| C["make run-docker"]
    C --> D["Access at http://localhost:80"]
    B -->|No| E["Activate venv"]
    E --> F["pip install -e '.[dev]'"]
    F --> G["Configure .env"]
    G --> H["make run"]
    H --> I["Open new terminal"]
    I --> J["cd frontend && npm install && npm run dev"]
    J --> K["Access at http://localhost:5173"]
```

---

## Cross-references

- [Infrastructure](infrastructure.md)
- [System Overview](system-overview.md)
