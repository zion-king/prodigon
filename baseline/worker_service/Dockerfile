# Build context should be baseline/ (set in docker-compose.yml)
FROM python:3.11-slim

WORKDIR /app

COPY worker_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY worker_service/ /app/worker_service/
# The worker also ships the migrations so it can run standalone (e.g. for
# CLI ops like `docker-compose run worker-service alembic upgrade head`).
# At runtime we rely on api-gateway to apply migrations first — worker just
# waits for the DB to be healthy via compose's `depends_on`.
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

EXPOSE 8002

CMD ["uvicorn", "worker_service.app.main:app", "--host", "0.0.0.0", "--port", "8002"]
