-- =============================================================================
-- Native Postgres bootstrap for the Prodigon baseline.
--
-- Creates the `prodigon` role and `prodigon` database if they don't already
-- exist. Run as a superuser against the default `postgres` database:
--
--     psql -U postgres -d postgres -f scripts/db_bootstrap.sql
--
-- The `make db-up-native` target wraps this. Safe to re-run — every statement
-- is guarded against "already exists" errors.
-- =============================================================================

-- Role: idempotent via the pg_roles lookup. A bare CREATE ROLE errors on
-- re-run; wrapping it in a DO block lets us skip gracefully.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prodigon') THEN
    CREATE ROLE prodigon LOGIN PASSWORD 'prodigon';
  END IF;
END
$$;

-- Database: CREATE DATABASE can't run inside a transaction, so we use the
-- \gexec meta-command to conditionally execute it based on a SELECT.
SELECT 'CREATE DATABASE prodigon OWNER prodigon'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'prodigon')\gexec

GRANT ALL PRIVILEGES ON DATABASE prodigon TO prodigon;
