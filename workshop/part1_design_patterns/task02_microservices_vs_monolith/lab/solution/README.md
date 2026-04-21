# Solution: Microservices Architecture

The completed microservices refactoring is the **baseline codebase** at:

```
baseline/
```

This is not a separate solution -- the baseline IS the production microservices architecture
that the monolith was refactored into.

---

## Mapping: Monolith Sections to Baseline Services

| Monolith Section (monolith.py) | Baseline Location | Notes |
|---|---|---|
| **Configuration** (lines 53-65) | `baseline/shared/config.py` | Extended by each service's own config |
| **Logging** (lines 71-88) | `baseline/shared/logging.py` | Identical, now imported by all services |
| **Error Handling** (lines 95-108) | `baseline/shared/errors.py` | Extended with ServiceUnavailableError, JobNotFoundError |
| **Schemas** (lines 114-151) | `baseline/shared/schemas.py` | Identical models, shared across services |
| **MockInferenceClient** (lines 163-182) | `baseline/model_service/app/services/groq_client.py` | MockGroqClient class |
| **GroqInferenceClient** (lines 185-216) | `baseline/model_service/app/services/groq_client.py` | GroqInferenceClient class |
| **ModelManager** (lines 224-260) | `baseline/model_service/app/services/model_manager.py` | Same logic, same fallback behavior |
| **InMemoryJobQueue** (lines 268-304) | `baseline/worker_service/app/services/queue.py` | InMemoryQueue, behind BaseQueue interface |
| **worker_loop** (lines 313-354) | `baseline/worker_service/app/worker.py` | Same loop, but calls Model Service via HTTP |
| **Direct inference calls in worker** | `baseline/worker_service/app/services/processor.py` | `JobProcessor` uses `ServiceClient.post("/inference", ...)` |
| **generate_text route** | `baseline/api_gateway/app/routes/generate.py` | Proxies to Model Service via HTTP |
| **submit_job route** | `baseline/api_gateway/app/routes/jobs.py` | Proxies to Worker Service via HTTP |
| **get_job_status route** | `baseline/api_gateway/app/routes/jobs.py` | Proxies to Worker Service via HTTP |
| **health_check route** | Each service has its own `routes/health.py` | Independent health checks |
| **CORS + timing middleware** | `baseline/api_gateway/app/middleware/` | Stays in the Gateway |
| *(new)* HTTP client | `baseline/shared/http_client.py` | `ServiceClient` for inter-service HTTP calls |

---

## Key Differences from the Monolith

### 1. Inter-service communication via HTTP

The monolith calls `model_manager.generate()` directly. The baseline uses
`ServiceClient.post("/inference", ...)` -- an HTTP call to Model Service on port 8001.

See: `baseline/shared/http_client.py`

### 2. Dependency injection instead of module globals

The monolith uses module-level singletons (`model_manager = ModelManager(...)`).
The baseline uses FastAPI's `Depends()` system for clean injection and testability.

See: `baseline/model_service/app/dependencies.py`

### 3. Queue abstraction

The monolith has a concrete `InMemoryJobQueue`. The baseline defines a `BaseQueue`
abstract class with `InMemoryQueue` as one implementation, making it easy to swap in
Redis later (Task 8).

See: `baseline/worker_service/app/services/queue.py`

### 4. Separate Docker containers

Each service has its own Dockerfile and runs as an independent container.
The `docker-compose.yml` wires them together with environment variables for
service discovery.

See: `baseline/docker-compose.yml`

---

## Running the Solution

```bash
# From the baseline directory
cd baseline

# Option 1: Docker Compose
docker-compose up --build

# Option 2: Run services individually
USE_MOCK=true uvicorn model_service.app.main:app --port 8001 --reload &
USE_MOCK=true MODEL_SERVICE_URL=http://localhost:8001 uvicorn worker_service.app.main:app --port 8002 --reload &
MODEL_SERVICE_URL=http://localhost:8001 WORKER_SERVICE_URL=http://localhost:8002 uvicorn api_gateway.app.main:app --port 8000 --reload &
```

---

## Verifying Equivalence

The client-facing API is identical:

```bash
# Same endpoints, same request/response shapes
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/generate -H "Content-Type: application/json" \
  -d '{"prompt": "Test"}'
curl -X POST http://localhost:8000/api/v1/jobs -H "Content-Type: application/json" \
  -d '{"prompts": ["A", "B"]}'
```

The only observable difference: slightly higher latency due to network hops between services
(typically 1-5ms per hop on localhost, more in production with containers on separate hosts).
