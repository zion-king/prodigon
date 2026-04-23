"""
API Gateway — FastAPI application entry point.

The public-facing service that routes requests to backend services. Handles:
  - Request validation and routing
  - CORS configuration
  - Request logging and timing middleware
  - Error translation (backend errors → clean client responses)

Run directly:
    cd baseline && uvicorn api_gateway.app.main:app --port 8000 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api_gateway.app.config import GatewaySettings
from api_gateway.app.dependencies import get_model_client, get_settings, get_worker_client, init_dependencies
from api_gateway.app.middleware.logging_mw import RequestLoggingMiddleware
from api_gateway.app.middleware.timing import TimingMiddleware
from api_gateway.app.routes import chat, generate, health, jobs, workshop
from shared.db import dispose_engine
from shared.errors import AppError
from shared.logging import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.service_name, settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize HTTP clients on startup, close on shutdown."""
    logger.info("api_gateway_starting", environment=settings.environment)

    model_client, worker_client = init_dependencies(settings)
    await model_client.start()
    await worker_client.start()

    logger.info("api_gateway_ready")
    yield

    await model_client.close()
    await worker_client.close()
    await dispose_engine()
    logger.info("api_gateway_stopped")


app = FastAPI(
    title="AI Platform API",
    description="Production AI assistant platform — API Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware (order matters — outermost runs first)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router, tags=["health"])
app.include_router(generate.router)
app.include_router(jobs.router)
app.include_router(workshop.router)
app.include_router(chat.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error("app_error", error_code=exc.error_code, message=exc.message, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.error_code, "message": exc.message}},
    )
