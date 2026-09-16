"""Change the pgvector column width when switching embedding models.

    python -m scripts.resize_embeddings --dim 1536

Destroys existing vectors by design — they are meaningless under a different
model — so re-ingestion is required afterwards and the script says so.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import text

from app.db.engine import get_engine

SQL = Path(__file__).resolve().parents[1] / "migrations" / "002_embedding_dim.sql"


async def run(dim: int) -> None:
    statements = SQL.read_text().replace(":dim", str(dim))
    async with get_engine().begin() as conn:
        for stmt in [s.strip() for s in statements.split(";") if s.strip()
                     and not s.strip().startswith("--")]:
            await conn.execute(text(stmt))
    print(f"embedding column resized to vector({dim}).")
    print("All existing vectors were cleared. Run `make ingest` to rebuild them.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dim", type=int, required=True)
    asyncio.run(run(p.parse_args().dim))
