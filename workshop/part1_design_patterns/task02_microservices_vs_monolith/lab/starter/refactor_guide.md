# Refactoring Guide: Monolith to Microservices

This guide walks you through breaking `monolith.py` into three independent services.
Each section extracts one service, with code snippets showing exactly what to move.

---

## Before You Start

Create the project structure:

```
your_project/
  shared/
    __init__.py
    config.py
    schemas.py
    logging.py
    errors.py
    http_client.py
    constants.py
  model_service/
    __init__.py
    app/
      __init__.py
      main.py
      config.py
      dependencies.py
      routes/
        __init__.py
        health.py
        inference.py
      services/
        __init__.py
        groq_client.py
        model_manager.py
  worker_service/
    __init__.py
    app/
      __init__.py
      main.py
      config.py
      dependencies.py
      worker.py
      routes/
        __init__.py
        health.py
        jobs.py
      services/
        __init__.py
        queue.py
        processor.py
  api_gateway/
    __init__.py
    app/
      __init__.py
      main.py
      config.py
      dependencies.py
      routes/
        __init__.py
        health.py
        generate.py
        jobs.py
      middleware/
        __init__.py
        timing.py
        logging_mw.py
```

---

## Step 0: Extract Shared Code

Before extracting services, pull out code that multiple services will need.

### shared/config.py

Extract the base configuration pattern:

```python
from pydantic_settings import BaseSettings

class BaseServiceSettings(BaseSettings):
    service_name: str = "unknown"
    environment: str = "development"
    log_level: str = "INFO"
    use_mock: bool = False

    model_config = {
        "env_file": "../../.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
```

### shared/schemas.py

Move ALL Pydantic models (GenerateRequest, GenerateResponse, JobStatus, JobSubmission,
JobResponse, HealthResponse) from the monolith into this file. These are the contracts
between services.

### shared/logging.py

Move `setup_logging()` and add a `get_logger()` helper:

```python
def get_logger(name: str):
    return structlog.get_logger(name)
```

### shared/errors.py

Move `AppError` and `InferenceError`. Add other error types:

```python
class ServiceUnavailableError(AppError):
    def __init__(self, message="Service unavailable", service="unknown"):
        super().__init__(f"{message}: {service}", 503, "SERVICE_UNAVAILABLE")

class JobNotFoundError(AppError):
    def __init__(self, job_id: str):
        super().__init__(f"Job not found: {job_id}", 404, "JOB_NOT_FOUND")
```

### shared/http_client.py

This is NEW -- the monolith does not have this because everything is in-process.
Create an async HTTP client for service-to-service communication:

```python
import httpx
from shared.errors import ServiceUnavailableError

class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = None

    async def start(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def post(self, path, json, headers=None):
        try:
            response = await self._client.post(path, json=json, headers=headers or {})
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise ServiceUnavailableError(service=self.base_url)
        except httpx.TimeoutException:
            raise ServiceUnavailableError(message="Timeout", service=self.base_url)

    async def get(self, path, headers=None):
        try:
            response = await self._client.get(path, headers=headers or {})
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise ServiceUnavailableError(service=self.base_url)
```

**Key insight:** This HTTP client is the glue that replaces direct function calls.
In the monolith, `worker_loop` calls `model_manager.generate()` directly. In
microservices, it calls `ServiceClient.post("/inference", ...)` over HTTP.

---

## Section 1: Extract the Model Service

The Model Service owns all inference logic. It has no dependencies on other services.

### What to move from monolith.py

| Monolith Section | Destination |
|---|---|
| `MockInferenceClient` | `model_service/app/services/groq_client.py` |
| `GroqInferenceClient` | `model_service/app/services/groq_client.py` |
| `ModelManager` | `model_service/app/services/model_manager.py` |
| `generate_text` route | `model_service/app/routes/inference.py` |

### model_service/app/config.py

```python
from shared.config import BaseServiceSettings

class ModelServiceSettings(BaseServiceSettings):
    service_name: str = "model-service"
    groq_api_key: str = ""
    default_model: str = "llama-3.3-70b-versatile"
    fallback_model: str = "llama-3.1-8b-instant"
```

### model_service/app/routes/inference.py

The route no longer calls the model manager directly from the module scope.
Instead, use FastAPI dependency injection:

```python
from fastapi import APIRouter, Depends
from model_service.app.dependencies import get_model_manager
from shared.schemas import GenerateRequest, GenerateResponse

router = APIRouter()

@router.post("/inference", response_model=GenerateResponse)
async def run_inference(
    request: GenerateRequest,
    model_manager = Depends(get_model_manager),
):
    result = await model_manager.generate(
        prompt=request.prompt,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        system_prompt=request.system_prompt,
    )
    return GenerateResponse(**result)
```

**Notice the path changed** from `/api/v1/generate` to `/inference`. The Model Service
exposes an internal API; the public `/api/v1/generate` path lives in the Gateway.

### model_service/app/dependencies.py

Wire up the singleton instances using FastAPI's dependency system:

```python
from functools import lru_cache
from model_service.app.config import ModelServiceSettings

_model_manager = None

@lru_cache()
def get_settings():
    return ModelServiceSettings()

def init_dependencies(settings):
    global _model_manager
    # Create inference client (mock or real) and model manager
    ...

def get_model_manager():
    return _model_manager
```

### model_service/app/main.py

```python
from fastapi import FastAPI
from model_service.app.routes import health, inference

app = FastAPI(title="Model Service", version="0.1.0")
app.include_router(health.router)
app.include_router(inference.router)
```

### Test independently

```bash
USE_MOCK=true uvicorn model_service.app.main:app --port 8001 --reload
curl -X POST http://localhost:8001/inference \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test"}'
```

---

## Section 2: Extract the Worker Service

The Worker Service owns job management and background processing. It depends on
the Model Service for inference (via HTTP, not direct import).

### What to move from monolith.py

| Monolith Section | Destination |
|---|---|
| `InMemoryJobQueue` | `worker_service/app/services/queue.py` |
| `worker_loop` | `worker_service/app/worker.py` |
| `submit_job` route | `worker_service/app/routes/jobs.py` |
| `get_job_status` route | `worker_service/app/routes/jobs.py` |

### The critical change: HTTP instead of direct calls

In the monolith, `worker_loop` calls:
```python
result = await model_manager.generate(prompt=prompt, ...)
```

In the Worker Service, this becomes:
```python
result = await model_service_client.post("/inference", json={
    "prompt": prompt,
    "model": submission.model,
    "max_tokens": submission.max_tokens,
})
```

Create a `JobProcessor` class that encapsulates this:

```python
class JobProcessor:
    def __init__(self, model_service_client, queue):
        self.model_client = model_service_client
        self.queue = queue

    async def process(self, job_id, submission):
        results = []
        for i, prompt in enumerate(submission.prompts):
            response = await self.model_client.post("/inference", json={
                "prompt": prompt,
                "model": submission.model,
                "max_tokens": submission.max_tokens,
            })
            results.append(response["text"])
            await self.queue.update_job(job_id, completed_prompts=i+1, results=results.copy())

        await self.queue.update_job(job_id, status="completed", results=results, ...)
```

### worker_service/app/config.py

```python
from shared.config import BaseServiceSettings

class WorkerServiceSettings(BaseServiceSettings):
    service_name: str = "worker-service"
    model_service_url: str = "http://localhost:8001"
    poll_interval: float = 1.0
```

### worker_service/app/routes/jobs.py

The job routes move here almost unchanged. The key difference is they use dependency
injection for the queue:

```python
@router.post("", response_model=JobResponse, status_code=202)
async def submit_job(
    submission: JobSubmission,
    queue = Depends(get_queue),
):
    return await queue.enqueue(submission)
```

**Notice the route prefix changes** from `/api/v1/jobs` to `/jobs`. The public
`/api/v1/jobs` prefix lives in the Gateway.

---

## Section 3: Convert the Monolith into an API Gateway

After extracting inference and job processing, what remains is the routing shell.
The API Gateway:
- Accepts public requests
- Validates them
- Proxies to the appropriate backend service
- Returns the response

### What stays in the Gateway

- CORS middleware
- Request timing middleware
- Request logging middleware
- Error handling
- Route definitions (but now they proxy instead of doing work)

### What gets removed

- `ModelManager`, all inference clients -- moved to Model Service
- `InMemoryJobQueue`, `worker_loop` -- moved to Worker Service
- Direct business logic in route handlers

### The generate route becomes a proxy

Before (monolith):
```python
@app.post("/api/v1/generate")
async def generate_text(request: GenerateRequest):
    result = await model_manager.generate(prompt=request.prompt, ...)
    return GenerateResponse(**result)
```

After (gateway):
```python
@router.post("/api/v1/generate")
async def generate_text(
    request: GenerateRequest,
    model_client: ServiceClient = Depends(get_model_client),
):
    result = await model_client.post("/inference", json=request.model_dump())
    return GenerateResponse(**result)
```

The Gateway does not know how inference works. It only knows the Model Service
is at `http://localhost:8001` and exposes `/inference`.

### The jobs route becomes a proxy

Before (monolith):
```python
@app.post("/api/v1/jobs")
async def submit_job(submission: JobSubmission):
    job = await job_queue.enqueue(submission)
    return job
```

After (gateway):
```python
@router.post("/api/v1/jobs")
async def submit_job(
    submission: JobSubmission,
    worker_client: ServiceClient = Depends(get_worker_client),
):
    result = await worker_client.post("/jobs", json=submission.model_dump())
    return JobResponse(**result)
```

### api_gateway/app/config.py

```python
from shared.config import BaseServiceSettings

class GatewaySettings(BaseServiceSettings):
    service_name: str = "api-gateway"
    model_service_url: str = "http://localhost:8001"
    worker_service_url: str = "http://localhost:8002"
```

---

## Section 4: Wire It All Together

### Running locally (three terminals)

```bash
# Terminal 1
USE_MOCK=true uvicorn model_service.app.main:app --port 8001 --reload

# Terminal 2
USE_MOCK=true MODEL_SERVICE_URL=http://localhost:8001 \
  uvicorn worker_service.app.main:app --port 8002 --reload

# Terminal 3
MODEL_SERVICE_URL=http://localhost:8001 WORKER_SERVICE_URL=http://localhost:8002 \
  uvicorn api_gateway.app.main:app --port 8000 --reload
```

### Running with Docker Compose

Create a `docker-compose.yml`:

```yaml
services:
  model-service:
    build: .
    command: uvicorn model_service.app.main:app --host 0.0.0.0 --port 8001
    ports: ["8001:8001"]
    environment:
      USE_MOCK: "true"

  worker-service:
    build: .
    command: uvicorn worker_service.app.main:app --host 0.0.0.0 --port 8002
    ports: ["8002:8002"]
    environment:
      USE_MOCK: "true"
      MODEL_SERVICE_URL: http://model-service:8001
    depends_on: [model-service]

  api-gateway:
    build: .
    command: uvicorn api_gateway.app.main:app --host 0.0.0.0 --port 8000
    ports: ["8000:8000"]
    environment:
      MODEL_SERVICE_URL: http://model-service:8001
      WORKER_SERVICE_URL: http://worker-service:8002
    depends_on: [model-service, worker-service]
```

---

## Verification Checklist

After refactoring, verify:

- [ ] `GET /health` on all three services returns healthy
- [ ] `POST /api/v1/generate` through the gateway returns the same response as the monolith
- [ ] `POST /api/v1/jobs` through the gateway returns 202 with a job_id
- [ ] `GET /api/v1/jobs/{id}` shows progress and eventually "completed"
- [ ] Killing Model Service does not crash Gateway or Worker Service
- [ ] Restarting Model Service restores full functionality

---

## What Changed and Why

| Change | Why |
|---|---|
| Direct function calls became HTTP calls | Service independence: each can run/scale/deploy separately |
| One process became three | Failure isolation: a crash in one does not kill the others |
| One config dict became three config classes | Each service has its own configuration concerns |
| Module-level singletons became dependency injection | Testability: swap real clients for mocks in tests |
| One log stream became three | Need distributed tracing (correlation IDs) to follow requests |
| Zero network latency became ~1-5ms per hop | The cost of independence; mitigated by async I/O |

---

## Common Mistakes

1. **Sharing the database directly.** If two services both read/write the same table,
   they are not independent. Each service should own its data.

2. **Synchronous chains.** If Gateway waits for Worker, which waits for Model Service,
   you have a synchronous distributed monolith. Use async (202 + polling) where possible.

3. **Too many services too soon.** Three services is reasonable for this system. Do not
   split further until you have evidence that a component needs independent scaling.

4. **Forgetting timeouts.** Every HTTP call needs a timeout. Without one, a slow Model
   Service blocks the Gateway indefinitely.
