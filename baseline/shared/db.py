"""
Shared database layer — async SQLAlchemy engine, session factory, and Base.

All services that touch the database import from this module so there is
exactly one engine per process and one declarative `Base` for all models.

Why a shared module:
    Each service could spin up its own engine, but then migrations and model
    classes would drift. Centralizing here means the gateway and worker see
    the same schema and share the same ORM metadata — which is what Alembic
    needs to autogenerate migrations.

Design choices:
    - SQLAlchemy 2.x native async API (`AsyncEngine`, `AsyncSession`).
      No blocking I/O in the event loop.
    - `asyncpg` driver — fastest Postgres driver for asyncio. The URL scheme
      `postgresql+asyncpg://` tells SQLAlchemy which dialect/driver to use.
    - `expire_on_commit=False` — after a commit, ORM objects remain usable
      without triggering a refresh. Essential in async code where lazy loads
      would otherwise need `await`.
    - Pool pre-ping — checks connection liveness before handing it out, so a
      stale socket after a DB restart becomes a retry instead of an error.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Root ORM class. Every model in shared/models.py inherits from this.

    Alembic's autogenerate reads `Base.metadata` to diff the live DB schema
    against declared models, so all models MUST be importable from a single
    place (see baseline/alembic/env.py, which imports shared.models).
    """


# ---------------------------------------------------------------------------
# Engine + session factory (one per process)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _resolve_database_url() -> str:
    """Read DATABASE_URL from env with a dev-friendly default.

    In Docker, compose sets DATABASE_URL to the Postgres container's DSN.
    For bare-metal local runs, developers can export their own or rely on
    the default (which assumes a Postgres listening on localhost:5432).
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return "postgresql+asyncpg://prodigon:prodigon@localhost:5432/prodigon"


def get_engine() -> AsyncEngine:
    """Lazily construct the shared engine.

    We don't build at import time — that would require env vars to be set
    before any service module is imported, which is fragile during tests.
    """
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(
            _resolve_database_url(),
            echo=False,
            pool_pre_ping=True,  # validates connection before use
            pool_size=5,
            max_overflow=10,
        )
        _sessionmaker = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Returns the module-level session factory, constructing it if needed."""
    if _sessionmaker is None:
        get_engine()  # side-effect: initializes _sessionmaker
    assert _sessionmaker is not None  # narrow for type checker
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session, ensures it is closed.

    Usage in a route:
        async def endpoint(db: AsyncSession = Depends(get_session)):
            ...
    """
    sm = get_sessionmaker()
    async with sm() as session:
        yield session


async def dispose_engine() -> None:
    """Close all pooled connections. Call during app shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
