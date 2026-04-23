"""
Alembic migration environment.

Runs in two modes:

- "offline": emits SQL text without a DB connection. Useful for generating
  idempotent SQL scripts to hand to a DBA.
- "online": connects to the DB, inspects the live schema, and applies
  revisions. This is the mode used by `alembic upgrade head`.

Why we override the async default
---------------------------------
Our app engine is async (`postgresql+asyncpg`), so a synchronous Alembic
connection would fail on that dialect. We use `create_async_engine` here and
bridge into Alembic via `connection.run_sync(do_migrations)` — the standard
pattern documented in the SQLAlchemy async migration recipe.

DATABASE_URL resolution
-----------------------
The URL comes from:
    1. the `DATABASE_URL` environment variable (set by docker-compose), else
    2. the `sqlalchemy.url` fallback in alembic.ini.

That ordering means local developers can point migrations at any DB with a
single env var, without editing the config file.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# --- Import all models so `target_metadata` is populated ------------------
# Importing `shared.models` registers every ORM class on `Base.metadata`.
# Alembic autogenerate needs this to diff declared models vs. live schema.
from shared.db import Base
from shared import models  # noqa: F401  (import for side-effect: model registration)

# Alembic Config object, provides access to values in the .ini file.
config = context.config

# Override URL from env if set (docker-compose sets DATABASE_URL per service).
env_url = os.environ.get("DATABASE_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata target used by autogenerate to detect schema drift.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit migration SQL to stdout without opening a DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sync callback invoked via `run_sync` on an async connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # notice column type changes
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Open an async engine, bridge to sync Alembic via run_sync()."""
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=None,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
