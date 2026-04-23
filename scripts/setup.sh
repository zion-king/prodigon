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

echo ""
echo "================================================"
echo "  Setup complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  0. Activate virtual environment if not already activated: "source venv/Scripts/activate"
echo "  1. Edit .env and add your GROQ_API_KEY"
echo "  2. Run services: make run"
echo "  3. Or with Docker: make run-docker"
echo "  4. Check health: make health"
echo ""
