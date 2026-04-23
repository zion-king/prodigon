.PHONY: setup run run-docker test lint clean help db-up db-up-native db-down db-migrate db-revision dev-setup dev-setup-native

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and set up the project
	python -m pip install -e ".[dev]"
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example — edit it with your GROQ_API_KEY"; fi

dev-setup: setup db-up db-migrate ## One-shot (Docker path): install deps + start Postgres in Docker + migrate

dev-setup-native: setup db-up-native db-migrate ## One-shot (native path): install deps + bootstrap native Postgres + migrate

db-up: ## Start a local Postgres in Docker (uses baseline/docker-compose.yml postgres service)
	cd baseline && docker-compose up -d postgres
	@echo "Waiting for Postgres to accept connections..."
	@cd baseline && for i in $$(seq 1 30); do \
		if docker-compose exec -T postgres pg_isready -U prodigon -q 2>/dev/null; then \
			echo "Postgres ready."; exit 0; \
		fi; \
		sleep 1; \
	done; echo "Postgres did not become ready in 30s"; exit 1

db-up-native: ## Provision prodigon role/db in an already-running native Postgres (no Docker)
	@pg_isready -h localhost -p 5432 -q || { \
		echo "ERROR: Postgres isn't running on localhost:5432."; \
		echo "  Install it first if you haven't:"; \
		echo "    Windows: https://www.postgresql.org/download/windows/  (EDB installer)"; \
		echo "    macOS:   brew install postgresql@16"; \
		echo "    Linux:   sudo apt install postgresql-16  (or your distro's equivalent)"; \
		echo "  Then start the service:"; \
		echo "    Windows: net start postgresql-x64-16   (from an elevated shell)"; \
		echo "    macOS:   brew services start postgresql@16"; \
		echo "    Linux:   sudo systemctl start postgresql"; \
		exit 1; \
	}
	@echo "Bootstrapping prodigon role + database..."
	@psql -h localhost -U "$${PGUSER:-postgres}" -d postgres -v ON_ERROR_STOP=1 -f scripts/db_bootstrap.sql
	@echo "Native Postgres ready. Run 'make db-migrate' next."

db-down: ## Stop the local Postgres container (data preserved in named volume). Docker path only.
	cd baseline && docker-compose stop postgres

db-migrate: ## Apply pending Alembic migrations to the database in $$DATABASE_URL
	cd baseline && alembic upgrade head

db-revision: ## Generate a new Alembic revision from model changes (usage: make db-revision M="message")
	cd baseline && alembic revision --autogenerate -m "$(M)"

run: ## Run all services locally (no Docker). Requires Postgres up + migrations applied.
	bash scripts/run_all.sh

run-gateway: ## Run API gateway only
	cd baseline && python -m uvicorn api_gateway.app.main:app --host 0.0.0.0 --port 8000 --reload

run-model: ## Run model service only
	cd baseline && python -m uvicorn model_service.app.main:app --host 0.0.0.0 --port 8001 --reload

run-worker: ## Run worker service only
	cd baseline && python -m uvicorn worker_service.app.main:app --host 0.0.0.0 --port 8002 --reload

run-docker: ## Run all services with Docker Compose
	cd baseline && docker-compose up --build

test: ## Run all tests
	cd baseline && python -m pytest tests/ -v

lint: ## Run linter
	ruff check baseline/ workshop/

health: ## Check health of all services
	bash scripts/check_health.sh

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

run-frontend: ## Run frontend dev server
	cd frontend && npm run dev

build-frontend: ## Build frontend for production
	cd frontend && npm run build

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name *.egg-info -exec rm -rf {} + 2>/dev/null || true
