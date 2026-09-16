"""Idempotent schema bootstrap.

Alembic is the right answer for a long-lived service with many contributors.
For a handoff where the priority is `docker compose up` working the first time,
a single idempotent SQL file applied at startup removes a whole class of
"did you run the migration?" failures. ADR-004 records the trade-off and the
migration path to Alembic.
"""

from __future__ import annotations

from pathlib import Path

import sqlparse
from sqlalchemy import text

from app.config import settings
from app.db.engine import get_engine
from app.obs import get_logger

log = get_logger("db.bootstrap")

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def apply_migrations() -> None:
    """Run every auto-applied migration (NNN_*.sql, excluding manual ones)."""
    files = sorted(
        p for p in MIGRATIONS_DIR.glob("*.sql") if not p.name.startswith("002_")
    )
    engine = get_engine()

    async with engine.begin() as conn:
        for path in files:
            log.info("db.migration.apply", file=path.name)

            statements = sqlparse.split(
                path.read_text(encoding="utf-8")
            )

            for statement in statements:
                statement = statement.strip()
                if statement:
                    await conn.execute(text(statement))

    await _align_embedding_dim()
    log.info("db.migration.complete", applied=[p.name for p in files])


async def _align_embedding_dim() -> None:
    """Warn loudly if the column width and the configured embedding model disagree.

    Silent dimension mismatch is the single most common way a pgvector RAG stack
    fails, and the error surfaces much later as an opaque insert failure.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT a.atttypmod
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = 'chunks' AND a.attname = 'embedding'
                """
            )
        )
        typmod = result.scalar_one_or_none()
    if typmod and typmod > 0 and typmod != settings.embedding_dim:
        log.warning(
            "db.embedding_dim.mismatch",
            column_dim=typmod,
            configured_dim=settings.embedding_dim,
            fix="make resize-embeddings DIM=%d && make ingest" % settings.embedding_dim,
        )
