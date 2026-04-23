#!/usr/bin/env bash
# Lab 0.1 SOLUTION — fresh-clone walkthrough.
#
# Takes a cold repo from `git clone` to a fully running stack with all three
# services healthy and a smoke-tested /api/v1/generate endpoint.
#
# Usage:  bash workshop/part0_introduction/task01_getting_started/lab/solution/walkthrough.sh
#
# Environment (optional):
#   POSTGRES_PATH   "docker" (default) or "native"
#   BASE_URL        gateway URL (default http://localhost:8000)
set -euo pipefail

POSTGRES_PATH="${POSTGRES_PATH:-docker}"
BASE_URL="${BASE_URL:-http://localhost:8000}"

# Resolve repo root from this script's location so the walkthrough works
# regardless of the current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
cd "${REPO_ROOT}"

echo "==> Lab 0.1 walkthrough (SOLUTION)"
echo "    repo root  : ${REPO_ROOT}"
echo "    postgres   : ${POSTGRES_PATH}"
echo "    gateway    : ${BASE_URL}"
echo

# ---------------------------------------------------------------------------
# 1. Setup (venv + deps + .env from template)
# ---------------------------------------------------------------------------
echo "==> scripts/setup.sh ..."
bash scripts/setup.sh >/dev/null
echo "    done"

# ---------------------------------------------------------------------------
# 2. Force mock mode so this lab is runnable without a Groq API key
# ---------------------------------------------------------------------------
if [ -f .env ]; then
    if grep -q '^USE_MOCK=' .env; then
        # Cross-platform sed: write to a temp file, then swap
        sed 's/^USE_MOCK=.*/USE_MOCK=true/' .env > .env.tmp && mv .env.tmp .env
    else
        echo 'USE_MOCK=true' >> .env
    fi
    echo "==> .env exists: yes (USE_MOCK forced to true for this lab)"
else
    echo "!!  .env missing after setup.sh — aborting"
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Start Postgres
# ---------------------------------------------------------------------------
if [ "${POSTGRES_PATH}" = "docker" ]; then
    echo "==> make db-up ..."
    make db-up
else
    echo "==> make db-up-native ..."
    make db-up-native
fi
echo "    Postgres ready on localhost:5432"

# ---------------------------------------------------------------------------
# 4. Apply migrations
# ---------------------------------------------------------------------------
echo "==> make db-migrate ..."
make db-migrate
echo "    schema up to date"

# ---------------------------------------------------------------------------
# 5. Launch services in the background (activate venv first)
# ---------------------------------------------------------------------------
# shellcheck disable=SC1091
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate
echo "==> make run (background) ..."
make run >/tmp/prodigon_services.log 2>&1 &
SERVICES_PID=$!
echo "    services starting (pid=${SERVICES_PID})"

# Cleanup on exit so we don't leave orphans behind
cleanup() {
    echo
    echo "==> cleanup: kill ${SERVICES_PID}"
    kill "${SERVICES_PID}" 2>/dev/null || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 6. Wait for /health on each service (30s max each)
# ---------------------------------------------------------------------------
wait_healthy() {
    local url=$1
    local label=$2
    for _ in $(seq 1 30); do
        if curl -sf "${url}/health" >/dev/null 2>&1; then
            echo "==> /health: ${label} OK"
            return 0
        fi
        sleep 1
    done
    echo "!!  /health: ${label} did not come up in 30s"
    echo "    service log:"
    tail -n 40 /tmp/prodigon_services.log
    return 1
}

wait_healthy "http://localhost:8000" "api-gateway   :8000"
wait_healthy "http://localhost:8001" "model-service :8001"
wait_healthy "http://localhost:8002" "worker-service:8002"

# ---------------------------------------------------------------------------
# 7. Smoke test /api/v1/generate
# ---------------------------------------------------------------------------
echo "==> /api/v1/generate smoke test ..."
RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/generate" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "hello"}')
LEN=$(printf '%s' "${RESPONSE}" | wc -c | tr -d ' ')
if [ "${LEN}" -gt 20 ]; then
    echo "    OK (response length: ${LEN} chars)"
else
    echo "!!  response too short or empty: ${RESPONSE}"
    exit 1
fi

echo
echo "✓ Walkthrough complete. Stack is live on ports 8000/8001/8002 and Postgres 5432."
echo "  Services will be terminated when this script exits."
echo "  Press Ctrl+C to shut down cleanly, or leave the script running."

# Keep the script alive so services stay up until the user Ctrl+C's
wait "${SERVICES_PID}"
