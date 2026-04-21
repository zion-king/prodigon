"""
Well-Structured AI Service -- THE REFACTORED VERSION.

This file demonstrates proper use of FastAPI dependency injection:
  1. Configuration centralized in a Pydantic Settings class
  2. Groq client created once and injected into handlers
  3. Authentication as a separate, reusable dependency
  4. All components mockable/overridable for testing

Run it:
    uvicorn well_structured:app --port 8000

Run with environment overrides:
    GROQ_API_KEY=your-key API_KEY=secret123 uvicorn well_structured:app --port 8000

Test it (no API key needed):
    python -m pytest test_with_overrides.py -v
"""

import time
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from groq import Groq
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# ===========================================================================
# Configuration -- single source of truth for all settings
# ===========================================================================
class Settings(BaseSettings):
    """All configuration in one place, validated at startup.

    Why Pydantic BaseSettings:
    - Reads from environment variables automatically
    - Validates types (str stays str, int from "1024" string)
    - Provides defaults
    - Supports .env files
    - Easy to override in tests by constructing with explicit values
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
# Request/Response schemas
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
# Dependency Functions
# ===========================================================================

@lru_cache
def get_settings() -> Settings:
    """Cached settings -- created once, reused across all requests.

    @lru_cache ensures this function runs only once per process.
    Subsequent calls return the same Settings object. This is the
    "singleton" pattern for FastAPI dependencies.
    """
    return Settings()


def get_groq_client(settings: Settings = Depends(get_settings)) -> Groq | None:
    """Create the Groq client using injected settings.

    Why this is a dependency:
    - The route handler does not know how to create a client
    - Changing the API key or client type happens here, not in handlers
    - In tests, override this with a mock -- no real API calls
    - Returns None if no API key is configured (graceful degradation)
    """
    if not settings.groq_api_key:
        return None
    return Groq(api_key=settings.groq_api_key)


def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> bool:
    """Validate the API key from the request header.

    Why this is a dependency:
    - Auth logic is reusable across any number of endpoints
    - In tests, override this to skip auth entirely
    - Changing auth strategy (JWT, OAuth) means changing this one function
    - Returns True on success; raises 403 on failure (never reaches handler)
    """
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )
    return True


def check_service_health(
    settings: Settings = Depends(get_settings),
    client: Groq | None = Depends(get_groq_client),
) -> dict:
    """Check overall service health including downstream dependencies.

    This is a compound dependency -- it depends on both settings and the
    Groq client. It checks whether the service is properly configured.
    """
    groq_status = "connected" if client is not None else "not configured"
    return {
        "status": "healthy",
        "service": settings.service_name,
        "environment": settings.environment,
        "groq_client": groq_status,
    }


# ===========================================================================
# Application
# ===========================================================================
app = FastAPI(title="Well-Structured AI Service")


# ===========================================================================
# Routes -- handlers declare what they need, framework provides it
# ===========================================================================
@app.post("/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    settings: Settings = Depends(get_settings),
    client: Groq | None = Depends(get_groq_client),
    _auth: bool = Depends(verify_api_key),
):
    """Generate text using the injected Groq client.

    Notice what this handler does NOT do:
    - Does not read os.environ
    - Does not create a Groq client
    - Does not check API keys
    - Does not know about configuration details

    It only does business logic: call the model and return the result.
    """
    if client is None:
        raise HTTPException(status_code=500, detail="Model client not configured")

    max_tokens = request.max_tokens or settings.max_tokens
    temperature = request.temperature or settings.temperature
    model_name = settings.default_model

    start_time = time.time()
    try:
        completion = client.chat.completions.create(
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


@app.get("/health")
async def health(health_info: dict = Depends(check_service_health)):
    """Health check -- fully delegated to the dependency.

    The handler is just a pass-through. The check_service_health dependency
    does all the work, and can be reused or overridden independently.
    """
    return health_info


@app.get("/metrics")
async def metrics(settings: Settings = Depends(get_settings)):
    """Metrics endpoint using injected settings.

    In a real system, you would inject a metrics collector dependency
    that tracks request counts, latencies, error rates, etc.
    """
    return {
        "model": settings.default_model,
        "service": settings.service_name,
        "version": "0.1.0",
    }


# ===========================================================================
# What changed vs tightly_coupled.py:
#
# 1. TESTABILITY: Override get_groq_client -> test without real API.
#    Override verify_api_key -> test without auth headers.
#    Override get_settings -> test with any configuration.
#
# 2. CENTRALIZATION: All config in Settings. Change once, applies everywhere.
#
# 3. SEPARATION: Auth, config, client creation, and business logic are
#    each in their own function. Each can evolve independently.
#
# 4. REUSE: get_settings and verify_api_key work for any endpoint.
#    Adding a new route just means adding Depends() parameters.
#
# 5. FLEXIBILITY: Swap Groq for OpenAI? Change get_groq_client().
#    Switch to JWT auth? Change verify_api_key(). Handlers untouched.
# ===========================================================================
