#!/usr/bin/env bash
# =============================================================================
# Setup script for Production AI System workshop
# Usage: bash scripts/setup.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "================================================"
echo "  Production AI System - Setup"
echo "================================================"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>/dev/null || python --version 2>/dev/null)
echo "Using: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_ROOT/venv" || python -m venv "$PROJECT_ROOT/venv"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$PROJECT_ROOT/venv/bin/activate" 2>/dev/null || source "$PROJECT_ROOT/venv/Scripts/activate"

# Install dependencies
echo "Installing dependencies..."
# pip install -e "$PROJECT_ROOT[dev]"
cd "$PROJECT_ROOT" && pip install --upgrade setuptools pip && pip install -e ".[dev]"


# Create .env if it doesn't exist
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    echo ""
    echo "Created .env from .env.example"
    echo "  -> Edit .env and set your GROQ_API_KEY"
fi

# Load .env so DATABASE_URL is visible to alembic below
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

# ---- Database bootstrap --------------------------------------------------
# Chat sessions + batch jobs live in Postgres. If a local Postgres isn't
# reachable, skip migrations and tell the user how to start one. We don't
# hard-fail here because setup.sh should remain idempotent on a fresh clone.
echo ""
echo "Checking Postgres availability..."
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
if command -v pg_isready >/dev/null 2>&1 && pg_isready -h "$PG_HOST" -p "$PG_PORT" -q; then
    PG_READY=1
elif python -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('${PG_HOST}', ${PG_PORT}))==0 else 1)" 2>/dev/null; then
    PG_READY=1
else
    PG_READY=0
fi

if [ "$PG_READY" -eq 1 ]; then
    echo "  -> Postgres reachable on ${PG_HOST}:${PG_PORT}, running migrations..."
    (cd "$PROJECT_ROOT/baseline" && alembic upgrade head)
else
    echo "  -> Postgres not reachable on ${PG_HOST}:${PG_PORT}."
    echo "     Pick one of the two paths:"
    echo "       Docker:  make db-up          (spins up the postgres service from docker-compose)"
    echo "       Native:  make db-up-native   (assumes a local Postgres is installed + running)"
    echo "     Then migrate:  make db-migrate"
fi

echo ""
echo "================================================"
echo "  Setup complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  0. Activate virtual env if needed:  source venv/Scripts/activate  (or venv/bin/activate)"
echo "  1. Edit .env and add your GROQ_API_KEY"
echo "  2. Start Postgres — pick one:"
echo "       Docker:   make db-up"
echo "       Native:   make db-up-native     (local Postgres already installed + running)"
echo "  3. Apply migrations:                 make db-migrate"
echo "  4. Run services:                     make run"
echo "  5. Or everything in Docker:          make run-docker"
echo "  6. Check health:                     make health"
echo ""
