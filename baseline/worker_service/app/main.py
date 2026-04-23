"""
Worker Service — FastAPI application entry point.

This service manages background/batch inference jobs. It provides a REST API
for submitting and tracking jobs, and runs a background worker loop that
processes queued jobs by calling the Model Service.

Run directly:
    cd baseline && uvicorn worker_service.app.main:app --port 8002 --reload
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.db import dispose_engine
from shared.errors import AppError
from shared.logging import get_logger, setup_logging
from worker_service.app.dependencies import get_model_client, get_processor, get_queue, get_settings, init_dependencies
from worker_service.app.routes import health, jobs
from worker_service.app.worker import worker_loop

settings = get_settings()
setup_logging(settings.service_name, settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start dependencies and background worker on startup."""
    logger.info("worker_service_starting", environment=settings.environment)

    queue, processor, model_client = init_dependencies(settings)
    await model_client.start()

    # Start the background worker loop
    worker_task = asyncio.create_task(
        worker_loop(queue, processor, poll_interval=settings.poll_interval)
    )
    logger.info("worker_service_ready")

    yield

    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await model_client.close()
    await dispose_engine()
    logger.info("worker_service_stopped")


app = FastAPI(
    title="Worker Service",
    description="Background job processing for batch inference",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router, tags=["health"])
app.include_router(jobs.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error("app_error", error_code=exc.error_code, message=exc.message, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.error_code, "message": exc.message}},
    )
