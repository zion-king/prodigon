# Lab: Refactoring a Monolith into Microservices

## Problem Statement

You have a working monolithic AI platform (`starter/monolith.py`) -- a single FastAPI
application that handles API routing, LLM inference, and background job processing in one
file, one process, one deployment.

Your task is to **refactor it into the microservices architecture** found in `baseline/`:

| Service | Port | Responsibility |
|---|---|---|
| API Gateway | 8000 | Public entry point, request routing, middleware |
| Model Service | 8001 | LLM inference (Groq API / mock) |
| Worker Service | 8002 | Background job queue and processing |

Both architectures must produce **identical behavior** from the client's perspective.

---

## Prerequisites

```bash
pip install fastapi uvicorn httpx pydantic pydantic-settings structlog groq
```

---

## Step 1: Run the Monolith

Start the monolithic application and verify all endpoints work:

```bash
cd workshop/part1_design_patterns/task02_microservices_vs_monolith/lab/starter

# Run in mock mode (no API key needed)
USE_MOCK=true uvicorn monolith:app --port 8000 --reload
```

Test the endpoints:

```bash
# Health check
curl http://localhost:8000/health

# Text generation
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is a microservice?"}'

# Submit a batch job
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"prompts": ["Hello", "World", "Test"]}'

# Check job status (replace JOB_ID with the ID from the response above)
curl http://localhost:8000/api/v1/jobs/JOB_ID
```

Take note of the responses. After refactoring, they should be identical.

---

## Step 2: Identify Service Boundaries

Read through `monolith.py` and identify three natural boundaries:

1. **API Routing** (lines with `@app.*` decorators and middleware) -- becomes the **API Gateway**
2. **Inference Logic** (`ModelManager`, `GroqInferenceClient`, `MockInferenceClient`) -- becomes the **Model Service**
3. **Job Processing** (`InMemoryJobQueue`, `worker_loop`, job routes) -- becomes the **Worker Service**
4. **Shared Code** (schemas, config base, logging, errors) -- becomes the **shared module**

Draw the dependency graph:
- API routing depends on inference and jobs
- Job processing depends on inference
- Inference is independent

This tells you inference should be extracted first.

---

## Step 3: Extract the Model Service

The Model Service is the most independent piece -- it has no dependencies on other services.

Follow the detailed instructions in `starter/refactor_guide.md`, Section 1.

Summary:
1. Create `model_service/` directory with its own `main.py` and routes
2. Move `ModelManager`, `GroqInferenceClient`, `MockInferenceClient` into it
3. Expose an `/inference` POST endpoint
4. Run on port 8001

Test it independently:
```bash
USE_MOCK=true uvicorn model_service.app.main:app --port 8001 --reload

curl -X POST http://localhost:8001/inference \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello from the model service"}'
```

---

## Step 4: Extract the Worker Service

The Worker Service depends on Model Service (it calls inference for each prompt in a batch).

Follow `starter/refactor_guide.md`, Section 2.

Summary:
1. Create `worker_service/` directory
2. Move `InMemoryJobQueue`, `worker_loop`, job routes into it
3. Replace direct `model_manager.generate()` calls with HTTP calls to Model Service
4. Run on port 8002

Test it (with Model Service running on 8001):
```bash
USE_MOCK=true uvicorn worker_service.app.main:app --port 8002 --reload

curl -X POST http://localhost:8002/jobs \
  -H "Content-Type: application/json" \
  -d '{"prompts": ["Test prompt 1", "Test prompt 2"]}'
```

---

## Step 5: Convert the Monolith into an API Gateway

What remains of the monolith is the API Gateway -- it no longer does inference or job
processing, only routing.

Follow `starter/refactor_guide.md`, Section 3.

Summary:
1. Remove all inference and job logic from the monolith
2. Replace direct calls with HTTP proxy calls to Model Service and Worker Service
3. Keep middleware (CORS, timing, logging)
4. Run on port 8000

---

## Step 6: Run Everything Together

Run all three services (in separate terminals):
```bash
# Terminal 1: Model Service
USE_MOCK=true uvicorn model_service.app.main:app --port 8001 --reload

# Terminal 2: Worker Service
USE_MOCK=true MODEL_SERVICE_URL=http://localhost:8001 uvicorn worker_service.app.main:app --port 8002 --reload

# Terminal 3: API Gateway
USE_MOCK=true MODEL_SERVICE_URL=http://localhost:8001 WORKER_SERVICE_URL=http://localhost:8002 \
  uvicorn api_gateway.app.main:app --port 8000 --reload
```

Or use docker-compose (from the baseline directory):
```bash
cd baseline
docker-compose up --build
```

Test the same endpoints as Step 1 and verify identical responses.

---

## Step 7: Compare the Architectures

| Aspect | Monolith (Step 1) | Microservices (Step 6) |
|---|---|---|
| Files to edit for an inference change | 1 (`monolith.py`) | 1 (`model_service/`) |
| Processes running | 1 | 3 (+ nginx, redis optional) |
| Network calls per /generate request | 0 | 1 (Gateway -> Model Service) |
| Network calls per /jobs request | 0 | 1-2 (Gateway -> Worker -> Model) |
| What happens if inference crashes? | Entire app dies | Only Model Service dies; Gateway returns 503 |
| Scaling inference to 3 instances | Scale the whole app 3x | Scale only Model Service 3x |

---

## Expected Output

After completing the refactoring, you should have:
- Three independently running services
- Same API contract (same URLs, same request/response shapes)
- The client cannot tell the difference between the monolith and microservices

---

## Bonus Challenges

### Bonus 1: Health Aggregation
Add a `/health/all` endpoint to the API Gateway that calls `/health` on both Model Service
and Worker Service, and returns an aggregated status:

```json
{
  "status": "healthy",
  "services": {
    "api-gateway": "healthy",
    "model-service": "healthy",
    "worker-service": "healthy"
  }
}
```

### Bonus 2: Failure Isolation
1. Start all three services
2. Kill the Model Service (Ctrl+C in its terminal)
3. Try `/api/v1/generate` -- it should return a 503 error
4. Try `/api/v1/jobs` submit -- it should return 202 (accepted into queue)
5. Check job status -- it should show "failed" (worker could not reach Model Service)
6. Restart Model Service
7. Submit another job -- it should complete successfully

This demonstrates **failure isolation**: the Gateway and Worker survive even when Model
Service is down.

### Bonus 3: Add Request Tracing
Add an `X-Request-ID` header to every request in the API Gateway, and forward it to backend
services. Log it in every service so you can trace a single request across all three services.

---

## Stuck?

The completed microservices architecture is the baseline codebase at `baseline/`.
See `solution/README.md` for a mapping of monolith sections to baseline services.
