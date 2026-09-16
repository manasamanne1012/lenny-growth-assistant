"""Data access. All SQL lives here; routes and the agent never write SQL.

Keeping persistence behind a narrow repository is what makes the unit tests
runnable without Postgres and what will make swapping the vector store later a
contained change (see ADR-002).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _uuid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------- sessions
async def create_session(
    db: AsyncSession,
    *,
    title: str = "New chat",
    user_id: str = "local-evaluator",
    user_metadata: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                INSERT INTO sessions (id, title, user_id, user_metadata, provider, model)
                VALUES (:id, :title, :user_id, CAST(:meta AS jsonb), :provider, :model)
                RETURNING id, title, user_id, user_metadata, provider, model,
                          created_at, updated_at
                """
            ),
            {
                "id": _uuid(),
                "title": title,
                "user_id": user_id,
                "meta": json.dumps(user_metadata or {}),
                "provider": provider,
                "model": model,
            },
        )
    ).mappings().one()
    return dict(row)


async def list_sessions(
    db: AsyncSession, *, user_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT s.id, s.title, s.user_id, s.provider, s.model,
                       s.created_at, s.updated_at,
                       (SELECT count(*) FROM messages m WHERE m.session_id = s.id)
                           AS message_count
                FROM sessions s
                WHERE s.user_id = :user_id AND s.archived_at IS NULL
                ORDER BY s.updated_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def get_session_row(db: AsyncSession, session_id: str) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text("SELECT * FROM sessions WHERE id = CAST(:id AS uuid)"),
            {"id": session_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row else None


async def touch_session(
    db: AsyncSession,
    session_id: str,
    *,
    title: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            UPDATE sessions
               SET updated_at = now(),
                   title    = COALESCE(:title, title),
                   provider = COALESCE(:provider, provider),
                   model    = COALESCE(:model, model)
             WHERE id = CAST(:id AS uuid)
            """
        ),
        {"id": session_id, "title": title, "provider": provider, "model": model},
    )


async def archive_session(db: AsyncSession, session_id: str) -> bool:
    result = await db.execute(
        text(
            "UPDATE sessions SET archived_at = now() "
            "WHERE id = CAST(:id AS uuid) AND archived_at IS NULL"
        ),
        {"id": session_id},
    )
    return result.rowcount > 0


# --------------------------------------------------------------------- messages
async def add_message(
    db: AsyncSession,
    *,
    session_id: str,
    role: str,
    content: str,
    skill: str | None = None,
    grounding: str | None = None,
    citations: list[dict] | None = None,
    trace: dict | None = None,
    provider: str | None = None,
    model: str | None = None,
    latency_ms: int | None = None,
    token_usage: dict | None = None,
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                INSERT INTO messages (id, session_id, role, content, skill, grounding,
                                      citations, trace, provider, model, latency_ms,
                                      token_usage)
                VALUES (:id, CAST(:session_id AS uuid), :role, :content, :skill,
                        :grounding, CAST(:citations AS jsonb), CAST(:trace AS jsonb),
                        :provider, :model, :latency_ms, CAST(:usage AS jsonb))
                RETURNING *
                """
            ),
            {
                "id": _uuid(),
                "session_id": session_id,
                "role": role,
                "content": content,
                "skill": skill,
                "grounding": grounding,
                "citations": json.dumps(citations or []),
                "trace": json.dumps(trace or {}),
                "provider": provider,
                "model": model,
                "latency_ms": latency_ms,
                "usage": json.dumps(token_usage or {}),
            },
        )
    ).mappings().one()
    return dict(row)


async def list_messages(
    db: AsyncSession, session_id: str, *, limit: int = 200
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT * FROM messages
                 WHERE session_id = CAST(:sid AS uuid)
                 ORDER BY created_at ASC
                 LIMIT :limit
                """
            ),
            {"sid": session_id, "limit": limit},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def recent_turns(
    db: AsyncSession, session_id: str, *, turns: int
) -> list[dict[str, Any]]:
    """Last N messages in chronological order, for conversation context."""
    rows = (
        await db.execute(
            text(
                """
                SELECT role, content FROM (
                    SELECT role, content, created_at FROM messages
                     WHERE session_id = CAST(:sid AS uuid) AND role IN ('user','assistant')
                     ORDER BY created_at DESC LIMIT :limit
                ) t ORDER BY created_at ASC
                """
            ),
            {"sid": session_id, "limit": turns},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# -------------------------------------------------------------------- artifacts
async def add_artifact(
    db: AsyncSession,
    *,
    session_id: str,
    message_id: str | None,
    kind: str,
    title: str,
    content: str,
    sanitized: bool,
    sanitizer_report: dict,
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
            INSERT INTO artifacts (id, session_id, message_id, kind, title,
                       content, sanitized, sanitizer_report)
VALUES (:id, CAST(:sid AS uuid),
        CAST(:mid AS uuid),
        :kind, :title, :content, :sanitized,
        CAST(:report AS jsonb))
RETURNING *    
                """
            ),
            {
                "id": _uuid(),
                "sid": session_id,
                "mid": message_id,
                "kind": kind,
                "title": title,
                "content": content,
                "sanitized": sanitized,
                "report": json.dumps(sanitizer_report),
            },
        )
    ).mappings().one()
    return dict(row)


async def list_artifacts(db: AsyncSession, session_id: str) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                "SELECT * FROM artifacts WHERE session_id = CAST(:sid AS uuid) "
                "ORDER BY created_at DESC"
            ),
            {"sid": session_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def get_artifact(db: AsyncSession, artifact_id: str) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text("SELECT * FROM artifacts WHERE id = CAST(:id AS uuid)"),
            {"id": artifact_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row else None


# ------------------------------------------------------------------ transcripts
async def upsert_transcript(
    db: AsyncSession,
    *,
    source_id: str,
    title: str,
    guest: str | None,
    episode_url: str | None,
    published_on: datetime | None,
    source_path: str,
    content_hash: str,
    word_count: int,
) -> tuple[str, bool]:
    """Returns (transcript_id, changed). `changed` is False when the content hash
    matches, which lets re-ingestion skip unchanged episodes."""
    existing = (
        await db.execute(
            text("SELECT id, content_hash FROM transcripts WHERE source_id = :sid"),
            {"sid": source_id},
        )
    ).mappings().one_or_none()

    if existing and existing["content_hash"] == content_hash:
        return str(existing["id"]), False

    if existing:
        await db.execute(
            text("DELETE FROM chunks WHERE transcript_id = :tid"),
            {"tid": existing["id"]},
        )
        await db.execute(
            text(
                """
                UPDATE transcripts
                   SET title=:title, guest=:guest, episode_url=:url,
                       published_on=:pub, source_path=:path, content_hash=:hash,
                       word_count=:wc, ingested_at=now()
                 WHERE id = :id
                """
            ),
            {
                "title": title, "guest": guest, "url": episode_url,
                "pub": published_on, "path": source_path, "hash": content_hash,
                "wc": word_count, "id": existing["id"],
            },
        )
        return str(existing["id"]), True

    new_id = _uuid()
    await db.execute(
        text(
            """
            INSERT INTO transcripts (id, source_id, title, guest, episode_url,
                                     published_on, source_path, content_hash, word_count)
            VALUES (CAST(:id AS uuid), :sid, :title, :guest, :url, :pub, :path,
                    :hash, :wc)
            """
        ),
        {
            "id": new_id, "sid": source_id, "title": title, "guest": guest,
            "url": episode_url, "pub": published_on, "path": source_path,
            "hash": content_hash, "wc": word_count,
        },
    )
    return new_id, True


async def insert_chunks(
    db: AsyncSession, transcript_id: str, chunks: Sequence[dict[str, Any]]
) -> int:
    for c in chunks:
        await db.execute(
            text(
                """
                INSERT INTO chunks (id, transcript_id, chunk_index, content, heading,
                                    speaker, start_char, token_estimate, embedding)
                VALUES (CAST(:id AS uuid), CAST(:tid AS uuid), :idx, :content, :heading,
                        :speaker, :start, :tokens, CAST(:emb AS vector))
                ON CONFLICT (transcript_id, chunk_index) DO UPDATE
                  SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
                """
            ),
            {
                "id": _uuid(),
                "tid": transcript_id,
                "idx": c["chunk_index"],
                "content": c["content"],
                "heading": c.get("heading"),
                "speaker": c.get("speaker"),
                "start": c.get("start_char", 0),
                "tokens": c.get("token_estimate", 0),
                "emb": "[" + ",".join(f"{v:.6f}" for v in c["embedding"]) + "]",
            },
        )
    return len(chunks)


async def knowledge_base_stats(db: AsyncSession) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT (SELECT count(*) FROM transcripts)                AS transcripts,
                       (SELECT count(*) FROM chunks)                     AS chunks,
                       (SELECT count(*) FROM chunks WHERE embedding IS NULL)
                                                                         AS unembedded,
                       (SELECT max(ingested_at) FROM transcripts)        AS last_ingest
                """
            )
        )
    ).mappings().one()
    return dict(row)


# ------------------------------------------------------------------ retrieval
async def hybrid_search(
    db: AsyncSession,
    *,
    query: str,
    embedding: list[float],
    candidate_k: int,
    top_k: int,
    rrf_k: int,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion over pgvector cosine distance and Postgres FTS.

    Semantic search alone misses exact terminology ("PLG", "aha moment",
    a guest's name); lexical search alone misses paraphrase. Fusing the two
    ranked lists with RRF needs no tuned weights and no reranker model, which
    keeps the local-only demo honest. See ADR-003.
    """
    vec = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
    rows = (
        await db.execute(
            text(
                """
                WITH semantic AS (
                    SELECT c.id,
                           ROW_NUMBER() OVER (ORDER BY c.embedding <=> CAST(:vec AS vector))
                               AS rank
                    FROM chunks c
                    WHERE c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> CAST(:vec AS vector)
                    LIMIT :candidate_k
                ),
                lexical AS (
                    SELECT c.id,
                           ROW_NUMBER() OVER (
                               ORDER BY ts_rank_cd(c.tsv, plainto_tsquery('english', :q)) DESC
                           ) AS rank
                    FROM chunks c
                    WHERE c.tsv @@ plainto_tsquery('english', :q)
                    LIMIT :candidate_k
                ),
                fused AS (
                    SELECT COALESCE(s.id, l.id) AS id,
                           COALESCE(1.0 / (:rrf_k + s.rank), 0)
                         + COALESCE(1.0 / (:rrf_k + l.rank), 0) AS score,
                           s.rank AS semantic_rank,
                           l.rank AS lexical_rank
                    FROM semantic s
                    FULL OUTER JOIN lexical l ON s.id = l.id
                )
                SELECT f.id AS chunk_id, f.score, f.semantic_rank, f.lexical_rank,
                       c.content, c.chunk_index, c.heading, c.speaker,
                       t.id AS transcript_id, t.source_id, t.title, t.guest,
                       t.episode_url
                FROM fused f
                JOIN chunks c      ON c.id = f.id
                JOIN transcripts t ON t.id = c.transcript_id
                ORDER BY f.score DESC
                LIMIT :top_k
                """
            ),
            {
                "vec": vec,
                "q": query,
                "candidate_k": candidate_k,
                "top_k": top_k,
                "rrf_k": rrf_k,
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ eval runs
async def save_eval_run(
    db: AsyncSession,
    *,
    label: str,
    provider: str,
    model: str,
    summary: dict,
    results: list[dict],
) -> str:
    run_id = _uuid()
    await db.execute(
        text(
            """
            INSERT INTO eval_runs (id, label, provider, model, summary, results)
            VALUES (CAST(:id AS uuid), :label, :provider, :model,
                    CAST(:summary AS jsonb), CAST(:results AS jsonb))
            """
        ),
        {
            "id": run_id, "label": label, "provider": provider, "model": model,
            "summary": json.dumps(summary), "results": json.dumps(results),
        },
    )
    return run_id
