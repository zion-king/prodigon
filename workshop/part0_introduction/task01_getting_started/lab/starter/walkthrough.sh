#!/usr/bin/env bash
# Lab 0.1 STARTER — fresh-clone walkthrough.
#
# Fill in each TODO with the right command. When complete, running this
# script from the repo root should take you from a fresh clone to a fully
# running stack with all three services healthy.
#
# Usage:  bash workshop/part0_introduction/task01_getting_started/lab/starter/walkthrough.sh
set -euo pipefail

echo "==> Lab 0.1 walkthrough (STARTER)"

# ---------------------------------------------------------------------------
# TODO 1 — run scripts/setup.sh to create venv, install deps, copy .env
# ---------------------------------------------------------------------------
# Hint: bash scripts/setup.sh


# ---------------------------------------------------------------------------
# TODO 2 — ensure .env exists and USE_MOCK=true is set (for offline lab runs).
# ---------------------------------------------------------------------------
# Hint:
#   if ! grep -q '^USE_MOCK=true' .env; then
#     sed -i.bak 's/^USE_MOCK=.*/USE_MOCK=true/' .env
#   fi


# ---------------------------------------------------------------------------
# TODO 3 — start Postgres. Pick ONE based on your environment.
# ---------------------------------------------------------------------------
# Docker:  make db-up
# Native:  make db-up-native


# ---------------------------------------------------------------------------
# TODO 4 — apply Alembic migrations.
# ---------------------------------------------------------------------------
# Hint: make db-migrate


# ---------------------------------------------------------------------------
# TODO 5 — start all three services in the background.
# ---------------------------------------------------------------------------
# Hint: make run &
# Save the PID: SERVICES_PID=$!


# ---------------------------------------------------------------------------
# TODO 6 — wait until /health on each service returns 200.
# ---------------------------------------------------------------------------
# Hint: a for-loop that curls each /health with a 1s sleep until success.


# ---------------------------------------------------------------------------
# TODO 7 — smoke test /api/v1/generate with a single prompt.
# ---------------------------------------------------------------------------
# Hint:
#   curl -s -X POST http://localhost:8000/api/v1/generate \
#     -H "Content-Type: application/json" \
#     -d '{"prompt": "hello"}'


echo "✓ Walkthrough complete (if you got here without errors)."
echo "  To stop: kill \${SERVICES_PID:-}"
