"""Retrieval and grounding assessment.

Two responsibilities:
  1. Fetch the best candidate chunks (hybrid vector + lexical, fused by RRF).
  2. Decide honestly whether what came back is strong enough to answer from.

(2) is the part most RAG demos skip, and it is why they hallucinate confidently
on out-of-scope questions. The retriever returns a `sufficiency` verdict; the
agent is required to abstain when it reads `insufficient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import repository as repo
from app.llm import get_embedder
from app.llm.base import ChatProviderError
from app.obs import current_trace, get_logger
from app.rag.chunker import nearest_timestamp

log = get_logger("rag.retriever")


@dataclass
class RetrievedChunk:
    marker: str                 # "S1", "S2" ... the label the model must cite
    chunk_id: str
    transcript_id: str
    source_id: str
    title: str
    guest: str | None
    episode_url: str | None
    content: str
    score: float
    semantic_rank: int | None
    lexical_rank: int | None
    heading: str | None
    timestamp: str | None

    def to_citation(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "chunk_id": str(self.chunk_id),
            "source_id": self.source_id,
            "title": self.title,
            "guest": self.guest,
            "episode_url": self.episode_url,
            "timestamp": self.timestamp,
            "heading": self.heading,
            "score": round(self.score, 5),
            "retrieved_by": _retrieved_by(self.semantic_rank, self.lexical_rank),
            "excerpt": self.content[:320].strip(),
        }


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    sufficiency: str = "insufficient"   # sufficient | thin | insufficient
    reason: str = ""
    degraded: bool = False              # true when embeddings were unavailable

    @property
    def is_answerable(self) -> bool:
        return self.sufficiency in ("sufficient", "thin")

    def context_block(self, max_chars: int = 18_000) -> str:
        """The exact text handed to the model, with stable [S#] markers."""
        parts, used = [], 0
        for c in self.chunks:
            who = f"{c.guest} — " if c.guest else ""
            stamp = f" @ {c.timestamp}" if c.timestamp else ""
            header = f"[{c.marker}] {who}{c.title}{stamp}"
            block = f"{header}\n{c.content.strip()}"
            if used + len(block) > max_chars:
                break
            parts.append(block)
            used += len(block)
        return "\n\n---\n\n".join(parts)

    def citations(self) -> list[dict[str, Any]]:
        return [c.to_citation() for c in self.chunks]


def _retrieved_by(sem: int | None, lex: int | None) -> str:
    if sem and lex:
        return "both"
    if sem:
        return "semantic"
    if lex:
        return "keyword"
    return "unknown"


async def retrieve(
    db: AsyncSession,
    query: str,
    *,
    top_k: int | None = None,
) -> RetrievalResult:
    top_k = top_k or settings.retrieval_top_k
    trace = current_trace()

    # --- embed the query, degrading to lexical-only if the embedder is down ---
    embedding: list[float] | None = None
    degraded = False
    try:
        if trace:
            with trace.span("embed_query", provider=settings.embedding_provider):
                embedding = (await get_embedder().embed([query]))[0]
        else:
            embedding = (await get_embedder().embed([query]))[0]
    except (ChatProviderError, Exception) as exc:  # noqa: BLE001
        degraded = True
        log.warning("rag.embed_failed.lexical_only", error=str(exc))
        embedding = [0.0] * settings.embedding_dim

    # --- hybrid search ----------------------------------------------------
    if trace:
        with trace.span("hybrid_search", top_k=top_k) as span:
            rows = await repo.hybrid_search(
                db,
                query=query,
                embedding=embedding,
                candidate_k=settings.retrieval_candidate_k,
                top_k=top_k,
                rrf_k=settings.rrf_k,
            )
            span.detail["hits"] = len(rows)
    else:
        rows = await repo.hybrid_search(
            db,
            query=query,
            embedding=embedding,
            candidate_k=settings.retrieval_candidate_k,
            top_k=top_k,
            rrf_k=settings.rrf_k,
        )

    chunks = [
        RetrievedChunk(
            marker=f"S{i + 1}",
            chunk_id=str(r["chunk_id"]),
            transcript_id=str(r["transcript_id"]),
            source_id=r["source_id"],
            title=r["title"],
            guest=r["guest"],
            episode_url=r["episode_url"],
            content=r["content"],
            score=float(r["score"]),
            semantic_rank=r["semantic_rank"],
            lexical_rank=r["lexical_rank"],
            heading=r["heading"],
            timestamp=nearest_timestamp(r["content"]),
        )
        for i, r in enumerate(rows)
    ]

    result = RetrievalResult(query=query, chunks=chunks, degraded=degraded)
    _assess(result)

    if trace:
        trace.fact("retrieval", {
            "hits": len(chunks),
            "sufficiency": result.sufficiency,
            "top_score": round(chunks[0].score, 5) if chunks else 0,
            "degraded": degraded,
            "episodes": sorted({c.title for c in chunks}),
        })
    log.info(
        "rag.retrieved",
        query=query[:120],
        hits=len(chunks),
        sufficiency=result.sufficiency,
        degraded=degraded,
    )
    return result


def _assess(result: RetrievalResult) -> None:
    """Grounding gate.

    Thresholds are RRF scores, not cosine similarities, so they are stable
    across embedding models — a property that matters when the evaluator
    switches from nomic-embed-text to OpenAI embeddings mid-demo.
    """
    if not result.chunks:
        result.sufficiency = "insufficient"
        result.reason = "No transcript chunks matched this question."
        return

    top = result.chunks[0].score
    strong = [c for c in result.chunks if c.score >= settings.min_grounding_score]
    corroborating = len({c.transcript_id for c in strong})

    if top < settings.min_grounding_score * 0.6:
        result.sufficiency = "insufficient"
        result.reason = (
            f"Best match scored {top:.4f}, below the grounding floor "
            f"{settings.min_grounding_score:.4f}. The knowledge base does not "
            "cover this topic."
        )
    elif len(strong) >= 3 and corroborating >= 2:
        result.sufficiency = "sufficient"
        result.reason = (
            f"{len(strong)} strong chunks across {corroborating} episodes."
        )
    else:
        result.sufficiency = "thin"
        result.reason = (
            f"Only {len(strong)} strong chunk(s) from {corroborating} episode(s). "
            "The answer must be hedged and scoped to what the source says."
        )
