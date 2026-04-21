"""
Tightly-Coupled AI Service -- THE "BAD" VERSION.

This file demonstrates common anti-patterns in AI service code:
  1. Configuration read inline via os.environ (scattered, unvalidated)
  2. Groq client created directly in route handlers (untestable)
  3. Authentication logic mixed into business logic (no separation)
  4. No way to mock or swap components without modifying handlers

It works -- but it is fragile, untestable, and painful to maintain.

Run it:
    GROQ_API_KEY=your-key SERVICE_API_KEY=secret123 uvicorn tightly_coupled:app --port 8000

Try:
    curl -X POST http://localhost:8000/generate \
      -H "Content-Type: application/json" \
      -H "X-API-Key: secret123" \
      -d '{"prompt": "Explain dependency injection in one sentence."}'
"""

import os
import time

from fastapi import FastAPI, HTTPException, Request
from groq import Groq
from pydantic import BaseModel

app = FastAPI(title="Tightly Coupled AI Service")


# ---------------------------------------------------------------------------
# Request/Response models (the one thing done reasonably here)
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7


class GenerateResponse(BaseModel):
    text: str
    model: str
    latency_ms: float


# ---------------------------------------------------------------------------
# Anti-pattern: Everything jammed into a single route handler
# ---------------------------------------------------------------------------
@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, raw_request: Request):
    """Generate text -- but everything is tightly coupled inside this handler."""

    # --- Auth: hardcoded inline -------------------------------------------
    # Problem: auth logic is duplicated if you add more protected endpoints.
    # Problem: you cannot test this endpoint without setting SERVICE_API_KEY.
    api_key = raw_request.headers.get("X-API-Key")
    expected_key = os.environ.get("SERVICE_API_KEY", "")
    if not api_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # --- Config: read from os.environ every single request ----------------
    # Problem: no validation -- a typo in the env var name silently returns "".
    # Problem: no type coercion -- max_tokens would be a string if read here.
    # Problem: scattered -- every handler reads its own config.
    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")

    model_name = os.environ.get("MODEL_NAME", "llama-3.3-70b-versatile")

    # --- Client creation: new client every request ------------------------
    # Problem: creating a new Groq client on every request is wasteful.
    # Problem: you cannot mock this in tests without monkeypatching Groq.
    # Problem: if the constructor signature changes, every handler breaks.
    client = Groq(api_key=groq_api_key)

    # --- Business logic: mixed with all the infrastructure ----------------
    start_time = time.time()
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": request.prompt},
            ],
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
    except Exception as e:
        # Problem: generic catch -- no structured error handling
        raise HTTPException(status_code=502, detail=f"Model inference failed: {e}")

    latency_ms = (time.time() - start_time) * 1000

    return GenerateResponse(
        text=completion.choices[0].message.content,
        model=model_name,
        latency_ms=round(latency_ms, 2),
    )


# ---------------------------------------------------------------------------
# Anti-pattern: Health check also reads config inline
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Health endpoint -- but even this has inline config access."""
    service_name = os.environ.get("SERVICE_NAME", "ai-service")
    environment = os.environ.get("ENVIRONMENT", "development")

    # Problem: if you want to check the Groq client status,
    # you would have to create another client here. No shared state.
    return {
        "status": "healthy",
        "service": service_name,
        "environment": environment,
    }


# ---------------------------------------------------------------------------
# Anti-pattern: Metrics endpoint duplicates config reading
# ---------------------------------------------------------------------------
@app.get("/metrics")
async def metrics():
    """Basic metrics -- again reading config from env directly."""
    model_name = os.environ.get("MODEL_NAME", "llama-3.3-70b-versatile")
    return {
        "model": model_name,
        "version": "0.1.0",
        # With this structure there is no shared state to track request counts.
        "requests_served": "unknown -- no shared state to track this",
    }


# ---------------------------------------------------------------------------
# Summary of problems:
#
# 1. TESTABILITY: Cannot test /generate without a real GROQ_API_KEY.
#    Mocking requires monkeypatching os.environ AND the Groq constructor.
#
# 2. DUPLICATION: os.environ calls repeated in every handler.
#    Change an env var name? Find-and-replace across the file.
#
# 3. COUPLING: The handler knows HOW to create a Groq client, not just
#    how to USE one. Changing the client means changing every handler.
#
# 4. NO SEPARATION: Auth, config, client creation, and business logic
#    are all in the same function. Each concern cannot evolve independently.
#
# 5. NO REUSE: Groq client is created per-request. No connection pooling,
#    no singleton, no way to share it across handlers.
# ---------------------------------------------------------------------------
