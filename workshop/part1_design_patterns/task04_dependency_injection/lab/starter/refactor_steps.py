"""
Partially Refactored AI Service -- YOUR TURN TO COMPLETE.

The Settings model and request/response schemas are provided.
Your job: create the dependency functions and wire them into the routes.

Look for "YOUR CODE HERE" markers -- there are 4 sections to complete.

When finished, all tests in solution/test_with_overrides.py should pass.
"""

import time
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from groq import Groq
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# ===========================================================================
# SECTION 1: Configuration (provided)
# ===========================================================================
class Settings(BaseSettings):
    """Centralized configuration -- read from environment variables.

    Unlike scattered os.environ calls, this gives us:
    - Type validation at startup
    - Default values in one place
    - Easy override in tests
    """

    groq_api_key: str = ""
    default_model: str = "llama-3.3-70b-versatile"
    max_tokens: int = 1024
    temperature: float = 0.7
    api_key: str = "dev-key-123"
    service_name: str = "inference-service"
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# ===========================================================================
# SECTION 2: Request/Response models (provided)
# ===========================================================================
class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int | None = None
    temperature: float | None = None


class GenerateResponse(BaseModel):
    text: str
    model: str
    latency_ms: float


# ===========================================================================
# SECTION 3: Dependency functions -- YOUR CODE HERE
# ===========================================================================

# --- Step 1: Settings dependency -------------------------------------------
# Create a get_settings() function that:
# - Returns a Settings instance
# - Uses @lru_cache so it is created only once
# - Has return type annotation -> Settings

# YOUR CODE HERE: get_settings()


# --- Step 2: Groq client dependency ---------------------------------------
# Create a get_groq_client() function that:
# - Takes settings as a parameter using Depends(get_settings)
# - Returns an initialized Groq client using settings.groq_api_key
# - If groq_api_key is empty, returns None (we will handle this in the route)

# YOUR CODE HERE: get_groq_client()


# --- Step 3: Auth dependency -----------------------------------------------
# Create a verify_api_key() function that:
# - Reads the X-API-Key header (use Header(alias="X-API-Key"))
# - Gets settings via Depends(get_settings)
# - Raises HTTPException(status_code=403) if the key does not match settings.api_key
# - Returns True if the key is valid
#
# Hint: Use this signature pattern:
#   def verify_api_key(
#       x_api_key: str = Header(..., alias="X-API-Key"),
#       settings: Settings = Depends(get_settings),
#   ) -> bool:

# YOUR CODE HERE: verify_api_key()


# ===========================================================================
# SECTION 4: Application + Routes -- wire in the dependencies
# ===========================================================================
app = FastAPI(title="Refactored AI Service")


# --- Step 4: Wire dependencies into the /generate route -------------------
# Update this route to:
# - Accept settings via Depends(get_settings)
# - Accept the Groq client via Depends(get_groq_client)
# - Require auth via Depends(verify_api_key)
#
# The business logic is provided -- just fix the function signature.
@app.post("/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    # YOUR CODE HERE: add Depends() parameters for:
    # - settings (from get_settings)
    # - client (from get_groq_client)
    # - auth gate (from verify_api_key)
):
    """Generate text using the injected Groq client."""

    # Use injected settings for defaults
    max_tokens = request.max_tokens or settings.max_tokens  # noqa: F821
    temperature = request.temperature or settings.temperature  # noqa: F821
    model_name = settings.default_model  # noqa: F821

    if client is None:  # noqa: F821
        raise HTTPException(status_code=500, detail="Model client not configured")

    start_time = time.time()
    try:
        completion = client.chat.completions.create(  # noqa: F821
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": request.prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Inference failed: {e}")

    latency_ms = (time.time() - start_time) * 1000

    return GenerateResponse(
        text=completion.choices[0].message.content,
        model=model_name,
        latency_ms=round(latency_ms, 2),
    )


# --- Step 4b: Wire dependencies into /health ------------------------------
@app.get("/health")
async def health(
    # YOUR CODE HERE: add Depends(get_settings) parameter
):
    """Health check using injected settings."""
    return {
        "status": "healthy",
        "service": settings.service_name,  # noqa: F821
        "environment": settings.environment,  # noqa: F821
    }
