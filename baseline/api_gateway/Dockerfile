# Build context should be baseline/ (set in docker-compose.yml)
FROM python:3.11-slim

WORKDIR /app

COPY api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY api_gateway/ /app/api_gateway/
# Alembic config + migrations — the gateway applies `alembic upgrade head`
# on startup so a fresh DB becomes usable without a manual migration step.
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

EXPOSE 8000

# `alembic upgrade head` is idempotent — safe to run on every start. If the
# DB is already at head, it's a no-op.
CMD ["sh", "-c", "alembic upgrade head && uvicorn api_gateway.app.main:app --host 0.0.0.0 --port 8000"]
