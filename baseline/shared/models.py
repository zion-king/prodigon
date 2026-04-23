"""
ORM models — the persistent schema for the platform.

Four tables, keyed by UUIDs (stable across environments, safe to expose to
clients, no auto-increment collision on multi-writer setups):

    users           — accounts (placeholder for Part III auth work)
    chat_sessions   — a conversation thread, owned by a user
    chat_messages   — individual turns within a session (role + content)
    batch_jobs      — the worker_service's durable job queue

Why these four, and not more:
    The baseline only needs to prove end-to-end persistence. Anything else
    (usage stats, audit logs, rate-limit tokens) belongs to later workshop
    tasks and would bloat the migration surface area now.

Design choices:
    - UUID PKs (`uuid.uuid4`) stored as Postgres-native `UUID` columns.
    - `created_at` / `updated_at` default to server-side `now()` so the DB
      clock is the source of truth — not the app, which could drift.
    - `batch_jobs.prompts` / `.results` are JSONB: variable-length lists
      without a separate table. JSONB indexes well if we need to search
      later, and pydantic serialises/deserialises cleanly on the way in.
    - `status` is a plain VARCHAR, not a Postgres ENUM: enums are a pain to
      migrate (adding a value requires a transactional dance). String +
      application-level validation via `JobStatus` enum is more flexible.
    - Foreign keys use `ondelete="CASCADE"` for chat_messages → chat_sessions
      so deleting a session drops its messages atomically.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

class User(Base):
    """A platform account.

    The schema is intentionally minimal for the baseline — Part III (security)
    will layer password hashes, roles, and auth tokens on top. A `default_user`
    row is seeded by the initial migration so chat/job endpoints can attribute
    ownership before real auth exists.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# chat_sessions + chat_messages
# ---------------------------------------------------------------------------

class ChatSession(Base):
    """A conversation thread, grouping an ordered list of messages.

    `title` is free-text — the frontend auto-generates it from the first user
    message, but the client can rename later. `system_prompt` is stored per
    session (not per message) because it's a session-level setting.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New Chat")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """A single turn in a chat session — user input or assistant response.

    `role` is one of: "user", "assistant", "system". Validated at the
    Pydantic/API layer; stored as plain string for migration simplicity.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional token-usage metadata captured when the assistant replies.
    # Stored as JSONB so we can grow this without a migration every time.
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


# ---------------------------------------------------------------------------
# batch_jobs
# ---------------------------------------------------------------------------

class BatchJob(Base):
    """A worker_service background job.

    Replaces the in-memory queue. Survives restarts, supports horizontal
    scaling (multiple workers can SELECT ... FOR UPDATE SKIP LOCKED on the
    same table), and gives operators a paper trail of what ran.

    Status lifecycle: pending → running → (completed | failed).

    `prompts` is the input list; `results` is the output list, appended to as
    the worker processes each prompt. Both JSONB to keep the schema flat.
    """

    __tablename__ = "batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    prompts: Mapped[list] = mapped_column(JSONB, nullable=False)
    results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total_prompts: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_prompts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
