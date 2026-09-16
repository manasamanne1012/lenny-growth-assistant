# ADR-004 — Idempotent SQL applied at startup, instead of Alembic

**Status:** Accepted, with a stated expiry · **Date:** 2026-09 · **Affects:** `db/bootstrap.py`, `migrations/`

## Context

The schema needs to exist before the first request, on a machine where nobody has run a setup script. The brief is graded on one-command startup, and the most common way that grade is lost is a migration step the evaluator has to know about.

## Decision

`migrations/*.sql` contains idempotent DDL (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE EXTENSION IF NOT EXISTS`). `db/bootstrap.apply_migrations()` runs them in filename order during the FastAPI lifespan, retrying while Postgres finishes initialising.

It also compares `EMBEDDING_DIM` against the live vector column width and logs a loud warning on mismatch, rather than letting the failure surface later as an opaque error at query time.

## Alternatives considered

**Alembic.** The correct answer for a service with a deployment pipeline and a team. Rejected *here*: it brings a version table, a revision graph, autogenerate diffs that need reviewing, and a separate `alembic upgrade head` step in the startup path. For a single-service take-home with one schema version, that is more machinery than the problem has — and every extra step is a new way for a stranger's first run to fail.

**`create_all()` from SQLAlchemy models.** Rejected: it cannot express `pgvector` column types, generated `tsvector` columns, `ivfflat` index parameters, or extension creation. The interesting parts of this schema are exactly the parts it cannot produce.

**A manual `psql -f` step in the README.** Rejected: a documented manual step is a step someone will skip, and it fails the one-command requirement.

## Consequences

- `docker compose up` produces a working database with no further action.
- Migrations are safe to re-run; boot order does not matter.
- **This does not handle destructive or data-transforming migrations.** `002_embedding_dim.sql` is therefore *not* auto-applied — it is invoked deliberately through `make resize-embeddings`, because silently rewriting a column at boot is exactly the behaviour that makes people distrust automatic migrations.
- No down-migrations. Acceptable at one schema version; not acceptable with real data in production.

## Revisit when

A second developer joins, a second environment exists, or the first migration is needed that cannot be expressed idempotently. At that point adopt Alembic and stamp the current schema as the baseline revision. This decision has a deliberate expiry date.
