"""
Shared Pydantic models (request/response schemas) used across services.

Centralizing schemas ensures the API gateway, model service, and worker service
all agree on data shapes. A change here propagates everywhere.

Why shared schemas:
    Without shared models, each service defines its own version of "GenerateRequest"
    and they silently drift apart. Shared schemas act as a contract — if you change
    a field, all services that import it must adapt.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inference schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    """Request to generate text from a prompt."""

    prompt: str = Field(..., min_length=1, max_length=10000, description="Input prompt for text generation")
    model: str | None = Field(None, description="Model override (uses default if not set)")
    max_tokens: int = Field(1024, ge=1, le=8192, description="Maximum tokens to generate")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    system_prompt: str | None = Field(None, description="Optional system prompt for the model")


class GenerateResponse(BaseModel):
    """Response from text generation."""

    text: str = Field(..., description="Generated text")
    model: str = Field(..., description="Model that produced the response")
    usage: dict = Field(default_factory=dict, description="Token usage stats")
    latency_ms: float = Field(..., description="Inference latency in milliseconds")


# ---------------------------------------------------------------------------
# Job schemas
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    """Lifecycle states of a background job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobSubmission(BaseModel):
    """Request to submit a batch/background job."""

    prompts: list[str] = Field(..., min_length=1, max_length=100, description="List of prompts to process")
    model: str | None = Field(None, description="Model override")
    max_tokens: int = Field(1024, ge=1, le=8192)


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


# ---------------------------------------------------------------------------
# Chat session schemas (persistence)
# ---------------------------------------------------------------------------

class ChatMessageRole(str, Enum):
    """Valid roles for a chat message turn."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessageCreate(BaseModel):
    """Input schema when appending a message to a session."""

    role: ChatMessageRole
    content: str = Field(..., min_length=1)
    meta: dict | None = None


class ChatMessageOut(BaseModel):
    """Single persisted message returned to clients."""

    id: str
    session_id: str
    role: ChatMessageRole
    content: str
    meta: dict | None = None
    created_at: datetime


class ChatSessionCreate(BaseModel):
    """Input schema when creating a new session."""

    title: str | None = Field(None, max_length=200)
    system_prompt: str | None = None


class ChatSessionUpdate(BaseModel):
    """Input schema when renaming / updating a session."""

    title: str | None = Field(None, max_length=200)
    system_prompt: str | None = None


class ChatSessionOut(BaseModel):
    """Session metadata returned by list endpoints (no messages)."""

    id: str
    user_id: str
    title: str
    system_prompt: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ChatSessionDetail(ChatSessionOut):
    """Session detail including its messages."""

    messages: list[ChatMessageOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health schemas
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Standard health check response."""

    status: str = "healthy"
    service: str
    version: str = "0.1.0"
    environment: str = "development"
