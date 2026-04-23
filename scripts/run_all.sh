#!/usr/bin/env bash
# =============================================================================
# Run all services locally (without Docker)
# Usage: bash scripts/run_all.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BASELINE_DIR="$PROJECT_ROOT/baseline"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Ensure local service URLs
export MODEL_SERVICE_URL="${MODEL_SERVICE_URL:-http://localhost:8001}"
export WORKER_SERVICE_URL="${WORKER_SERVICE_URL:-http://localhost:8002}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://prodigon:prodigon@localhost:5432/prodigon}"

# --- Preflight: Postgres reachable? -----------------------------------------
# The gateway and worker will blow up on the first request otherwise — much
# nicer to fail fast here with an actionable hint.
PG_URL_REGEX='.*@([^:/]+):([0-9]+)/.*'
if [[ "$DATABASE_URL" =~ $PG_URL_REGEX ]]; then
    PG_HOST="${BASH_REMATCH[1]}"
    PG_PORT="${BASH_REMATCH[2]}"
    if ! python -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('${PG_HOST}', ${PG_PORT}))==0 else 1)" 2>/dev/null; then
        echo "ERROR: Postgres not reachable at ${PG_HOST}:${PG_PORT}." >&2
        echo "  Start it with: make db-up" >&2
        echo "  Then migrate:  make db-migrate" >&2
        exit 1
    fi
fi

# --- Preflight: migrations applied? -----------------------------------------
# Run `alembic upgrade head` every boot — it's idempotent when already at head.
echo "Applying Alembic migrations..."
(cd "$BASELINE_DIR" && alembic upgrade head)

echo "================================================"
echo "  Starting all services..."
echo "================================================"

# Track PIDs for cleanup
PIDS=()

cleanup() {
    echo ""
    echo "Shutting down services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    echo "All services stopped."
}
trap cleanup EXIT INT TERM

# Start Model Service (port 8001)
echo "Starting Model Service on :8001..."
cd "$BASELINE_DIR" && python -m uvicorn model_service.app.main:app --host 0.0.0.0 --port 8001 &
PIDS+=($!)

# Start Worker Service (port 8002)
echo "Starting Worker Service on :8002..."
cd "$BASELINE_DIR" && python -m uvicorn worker_service.app.main:app --host 0.0.0.0 --port 8002 &
PIDS+=($!)

# Brief pause for backend services to start
sleep 2

# Start API Gateway (port 8000)
echo "Starting API Gateway on :8000..."
cd "$BASELINE_DIR" && python -m uvicorn api_gateway.app.main:app --host 0.0.0.0 --port 8000 &
PIDS+=($!)

echo ""
echo "================================================"
echo "  All services running:"
echo "    API Gateway:    http://localhost:8000"
echo "    Model Service:  http://localhost:8001"
echo "    Worker Service: http://localhost:8002"
echo ""
echo "    API Docs:       http://localhost:8000/docs"
echo "================================================"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for all background processes
wait
