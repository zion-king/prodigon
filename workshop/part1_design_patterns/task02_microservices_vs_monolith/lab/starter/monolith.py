"""
Monolithic AI Platform — Single-File Application
=================================================

This is the MONOLITHIC version of the AI assistant platform. All functionality
lives in one file, one process, one deployment:

  - API routing (health, generate, jobs)
  - LLM inference (Groq API or mock)
  - Background job processing (in-memory queue + worker loop)
  - Configuration, logging, and error handling

Run:
    USE_MOCK=true python -m uvicorn monolith:app --port 8000 --reload

    Or with a Groq API key:
    GROQ_API_KEY=your-key python -m uvicorn monolith:app --port 8000 --reload

Test endpoints:
    curl http://localhost:8000/health
    curl -X POST http://localhost:8000/api/v1/generate -H "Content-Type: application/json" \\
         -d '{"prompt": "Explain microservices in one sentence"}'
    curl -X POST http://localhost:8000/api/v1/jobs -H "Content-Type: application/json" \\
         -d '{"prompts": ["Hello", "World"]}'
    curl http://localhost:8000/api/v1/jobs/{job_id}

Why study this?
    This file represents the "before" state. It works perfectly fine for a small
    team, a prototype, or a demo. But as the system grows, everything is coupled:
    a change to inference logic risks breaking the job queue, scaling inference
    means scaling the entire app, and a bug in the worker can crash the API.

    Your task: break this apart into the microservices in baseline/.
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# =============================================================================
# CONFIGURATION
# =============================================================================
# In a monolith, config is simple: just read env vars at the top of the file.
# There is no need for a shared config module because there is only one process.
# =============================================================================

SERVICE_NAME = "ai-platform-monolith"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
USE_MOCK = os.getenv("USE_MOCK", "false").lower() in ("true", "1", "yes")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama-3.3-70b-versatile")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "llama-3.1-8b-instant")
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.7
WORKER_POLL_INTERVAL = 1.0  # seconds


# =============================================================================
# LOGGING
# =============================================================================
# Structured logging with structlog. In a monolith, we configure it once here.
# In microservices, this would live in a shared module.
# =============================================================================

def setup_logging(service_name: str, log_level: str = "INFO") -> None:
    """Configure structlog with JSON output for production, console for dev."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if log_level == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)


setup_logging(SERVICE_NAME, LOG_LEVEL)
logger = structlog.get_logger(__name__)


# =============================================================================
# ERROR HANDLING
# =============================================================================
# Custom exception so we can return clean JSON error responses.
# In a monolith, this is trivial. In microservices, errors must be serialized
# across HTTP boundaries (status codes, error codes in JSON bodies).
# =============================================================================

class AppError(Exception):
    """Base application error with HTTP semantics."""

    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)


class InferenceError(AppError):
    def __init__(self, message: str = "Inference failed"):
        super().__init__(message=message, status_code=502, error_code="INFERENCE_ERROR")


# =============================================================================
# SCHEMAS
# =============================================================================
# Request/response models. In a monolith, these are just Pydantic models in the
# same file. In microservices, they live in a shared module to keep services
# aligned on data shapes.
# =============================================================================

class GenerateRequest(BaseModel):
    """Request body for text generation."""
    prompt: str = Field(..., min_length=1, max_length=10000)
    model: str | None = Field(None, description="Model override")
    max_tokens: int = Field(DEFAULT_MAX_TOKENS, ge=1, le=8192)
    temperature: float = Field(DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    system_prompt: str | None = None


class GenerateResponse(BaseModel):
    """Response from text generation."""
    text: str
    model: str
    usage: dict = Field(default_factory=dict)
    latency_ms: float


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobSubmission(BaseModel):
    """Request to submit a batch job."""
    prompts: list[str] = Field(..., min_length=1, max_length=100)
    model: str | None = None
    max_tokens: int = Field(DEFAULT_MAX_TOKENS, ge=1, le=8192)


class JobResponse(BaseModel):
    """Status and results of a background job."""
    job_id: str
    status: JobStatus
    created_at: datetime
    completed_at: datetime | None = None
    total_prompts: int
    completed_prompts: int = 0
    results: list[str] = Field(default_factory=list)
    error: str | None = None


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str
    version: str = "0.1.0"
    environment: str = "development"


# =============================================================================
# INFERENCE CLIENT
# =============================================================================
# In a monolith, inference logic is called directly -- no HTTP, no serialization.
# This is both the strength (fast, simple) and the weakness (cannot scale
# inference independently from the API or worker).
# =============================================================================

class MockInferenceClient:
    """Mock client for development without a Groq API key."""

    async def generate(
        self, prompt: str, model: str, max_tokens: int = 1024,
        temperature: float = 0.7, system_prompt: str | None = None,
    ) -> dict:
        mock_text = (
            f"[Mock response for model={model}] "
            f"This is a simulated response to: '{prompt[:80]}...'"
        )
        logger.info("mock_inference", model=model, prompt_length=len(prompt))
        return {
            "text": mock_text,
            "model": f"{model}-mock",
            "usage": {
                "prompt_tokens": len(prompt) // 4,
                "completion_tokens": 20,
                "total_tokens": len(prompt) // 4 + 20,
            },
            "latency_ms": 5.0,
        }


class GroqInferenceClient:
    """Production client using the Groq API."""

    def __init__(self, api_key: str):
        from groq import AsyncGroq
        self._client = AsyncGroq(api_key=api_key)
        logger.info("groq_client_initialized")

    async def generate(
        self, prompt: str, model: str, max_tokens: int = 1024,
        temperature: float = 0.7, system_prompt: str | None = None,
    ) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start = time.perf_counter()
        response = await self._client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        result = {
            "text": response.choices[0].message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "latency_ms": round(latency_ms, 2),
        }
        logger.info("inference_completed", model=response.model,
                     latency_ms=result["latency_ms"],
                     tokens=result["usage"]["total_tokens"])
        return result


def create_inference_client():
    """Factory: returns mock or real client based on USE_MOCK env var."""
    if USE_MOCK:
        logger.info("using_mock_inference_client")
        return MockInferenceClient()
    if not GROQ_API_KEY:
        logger.warning("no_groq_api_key_falling_back_to_mock")
        return MockInferenceClient()
    return GroqInferenceClient(GROQ_API_KEY)


# =============================================================================
# MODEL MANAGER
# =============================================================================
# Handles model selection and fallback. In a monolith, this is just a class.
# In microservices, this lives inside the Model Service.
# =============================================================================

class ModelManager:
    """Model selection with automatic fallback on failure."""

    def __init__(self, client, default_model: str, fallback_model: str):
        self.client = client
        self.default_model = default_model
        self.fallback_model = fallback_model

    def resolve_model(self, requested: str | None) -> str:
        return requested or self.default_model

    async def generate(
        self, prompt: str, model: str | None = None,
        max_tokens: int = 1024, temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> dict:
        target = self.resolve_model(model)
        try:
            return await self.client.generate(
                prompt=prompt, model=target, max_tokens=max_tokens,
                temperature=temperature, system_prompt=system_prompt,
            )
        except Exception as primary_err:
            if target == self.fallback_model:
                raise InferenceError(f"Inference failed: {primary_err}") from primary_err

            logger.warning("primary_model_failed", primary=target,
                           fallback=self.fallback_model, error=str(primary_err))
            try:
                return await self.client.generate(
                    prompt=prompt, model=self.fallback_model,
                    max_tokens=max_tokens, temperature=temperature,
                    system_prompt=system_prompt,
                )
            except Exception as fallback_err:
                raise InferenceError(
                    f"Both {target} and {self.fallback_model} failed"
                ) from fallback_err


# =============================================================================
# JOB QUEUE (IN-MEMORY)
# =============================================================================
# In a monolith, the queue is just a dict in the same process. Simple and fast.
# In microservices, the Worker Service owns its own queue, and the Gateway
# must communicate over HTTP to submit and check jobs.
# =============================================================================

class InMemoryJobQueue:
    """Simple in-memory job queue. Not suitable for production at scale."""

    def __init__(self):
        self._jobs: dict[str, JobResponse] = {}
        self._submissions: dict[str, JobSubmission] = {}
        self._pending: list[str] = []

    async def enqueue(self, submission: JobSubmission) -> JobResponse:
        job_id = str(uuid.uuid4())
        job = JobResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            total_prompts=len(submission.prompts),
        )
        self._jobs[job_id] = job
        self._submissions[job_id] = submission
        self._pending.append(job_id)
        logger.info("job_enqueued", job_id=job_id, prompts=len(submission.prompts))
        return job

    async def dequeue(self) -> tuple[str, JobSubmission] | None:
        if not self._pending:
            return None
        job_id = self._pending.pop(0)
        self._jobs[job_id].status = JobStatus.RUNNING
        logger.info("job_dequeued", job_id=job_id)
        return job_id, self._submissions[job_id]

    async def get_job(self, job_id: str) -> JobResponse | None:
        return self._jobs.get(job_id)

    async def update_job(self, job_id: str, **kwargs) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)


# =============================================================================
# BACKGROUND WORKER
# =============================================================================
# Processes jobs by pulling from the queue and calling the model manager
# DIRECTLY (in-process). In microservices, the worker calls Model Service
# over HTTP instead.
# =============================================================================

async def worker_loop(
    queue: InMemoryJobQueue,
    model_manager: ModelManager,
    poll_interval: float = 1.0,
):
    """Continuously poll the queue and process jobs."""
    logger.info("worker_loop_started", poll_interval=poll_interval)

    while True:
        try:
            item = await queue.dequeue()
            if item is None:
                await asyncio.sleep(poll_interval)
                continue

            job_id, submission = item
            logger.info("worker_processing_job", job_id=job_id)

            results = []
            try:
                for i, prompt in enumerate(submission.prompts):
                    # Direct in-process call -- no HTTP overhead
                    result = await model_manager.generate(
                        prompt=prompt,
                        model=submission.model,
                        max_tokens=submission.max_tokens,
                    )
                    results.append(result["text"])
                    await queue.update_job(
                        job_id,
                        completed_prompts=i + 1,
                        results=results.copy(),
                    )

                await queue.update_job(
                    job_id,
                    status=JobStatus.COMPLETED,
                    completed_at=datetime.now(timezone.utc),
                    completed_prompts=len(results),
                    results=results,
                )
                logger.info("job_completed", job_id=job_id, results=len(results))

            except Exception as exc:
                logger.error("job_failed", job_id=job_id, error=str(exc))
                await queue.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    completed_at=datetime.now(timezone.utc),
                    error=str(exc),
                )

        except asyncio.CancelledError:
            logger.info("worker_loop_cancelled")
            break
        except Exception as exc:
            logger.error("worker_loop_error", error=str(exc))
            await asyncio.sleep(poll_interval)


# =============================================================================
# APPLICATION SETUP
# =============================================================================
# Everything is wired together in one place. In microservices, each service
# has its own main.py with its own lifespan, middleware, and routes.
# =============================================================================

# Shared instances (module-level singletons)
inference_client = create_inference_client()
model_manager = ModelManager(inference_client, DEFAULT_MODEL, FALLBACK_MODEL)
job_queue = InMemoryJobQueue()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background worker on startup, cancel on shutdown."""
    logger.info("monolith_starting", environment=ENVIRONMENT, use_mock=USE_MOCK)

    worker_task = asyncio.create_task(
        worker_loop(job_queue, model_manager, poll_interval=WORKER_POLL_INTERVAL)
    )
    logger.info("monolith_ready")

    yield

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("monolith_stopped")


app = FastAPI(
    title="AI Platform (Monolith)",
    description="Single-process AI assistant platform — monolithic architecture",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


# Exception handler
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error("app_error", error_code=exc.error_code, message=exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.error_code, "message": exc.message}},
    )


# =============================================================================
# ROUTES
# =============================================================================
# All routes in one file. In microservices, each service has its own router
# module. The API Gateway just proxies; the real logic lives in backend services.
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        environment=ENVIRONMENT,
    )


@app.post("/api/v1/generate", response_model=GenerateResponse)
async def generate_text(request: GenerateRequest):
    """Generate text from a prompt.

    In the monolith, this calls the ModelManager directly (in-process).
    In microservices, the Gateway would proxy this to the Model Service over HTTP.
    """
    result = await model_manager.generate(
        prompt=request.prompt,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        system_prompt=request.system_prompt,
    )
    return GenerateResponse(
        text=result["text"],
        model=result["model"],
        usage=result["usage"],
        latency_ms=result["latency_ms"],
    )


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=202)
async def submit_job(submission: JobSubmission):
    """Submit a batch of prompts for background processing.

    In the monolith, jobs go directly into the in-memory queue.
    In microservices, the Gateway proxies this to the Worker Service.
    """
    job = await job_queue.enqueue(submission)
    return job


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Check the status of a background job.

    In the monolith, we read directly from the in-memory dict.
    In microservices, the Gateway proxies this to the Worker Service.
    """
    job = await job_queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


# =============================================================================
# ENTRY POINT
# =============================================================================
# One command starts everything: API + worker + inference -- that is the monolith.
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("monolith:app", host="0.0.0.0", port=8000, reload=True)
