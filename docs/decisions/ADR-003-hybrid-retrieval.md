# ADR-003 — Hybrid retrieval fused with Reciprocal Rank Fusion, no reranker

**Status:** Accepted · **Date:** 2026-09 · **Affects:** `db/repository.py`, `rag/retriever.py`

## Context

Podcast transcripts break pure vector search in a specific way. Users ask about **exact tokens** — a guest's name, a company, "PLG", "NPS", "the 40% rule" — and dense embeddings of ~700-token conversational chunks blur precisely those tokens into the surrounding discussion. Meanwhile users also ask in paraphrase ("how do you know it's working?" for product-market fit), which lexical search cannot reach at all.

Neither retrieval mode is adequate alone, and the two failures do not overlap.

## Decision

Run both and fuse by rank:

- **Dense:** pgvector cosine over chunk embeddings, top `RETRIEVAL_CANDIDATE_K`.
- **Lexical:** Postgres full-text (`ts_rank_cd`) over a generated `tsvector`, top `RETRIEVAL_CANDIDATE_K`.
- **Fusion:** Reciprocal Rank Fusion, `score = Σ 1 / (RRF_K + rank)`, `RRF_K = 60`, in one SQL statement.

## Why RRF rather than a weighted score blend

This is the crux of the decision.

A weighted blend (`α · cosine + (1-α) · ts_rank`) requires choosing `α`. Choosing `α` honestly requires labelled relevance data for *this* corpus. That data does not exist here, so any `α` I picked would be a guess wearing the costume of a tuned parameter — and it would sit in the codebase indistinguishable from a measured value, which is worse than having no parameter at all.

The scores are also not commensurable: cosine similarity and `ts_rank_cd` have different distributions, and normalising them introduces its own unjustified choices.

RRF consumes **only rank positions**. It needs no score normalisation and no relevance data. `RRF_K = 60` is the value from Cormack et al., is known to be insensitive within a wide band, and is documented as "do not move without eval evidence".

## Alternatives considered

**Vector only.** Rejected: fails on proper nouns and exact terms, which is a large share of real queries here.

**Lexical only.** Rejected: fails on paraphrase, which is most of how questions are actually phrased.

**Weighted blend.** Rejected above.

**Cross-encoder reranker over fused candidates.** The strongest rejected option, and would likely improve precision meaningfully. Rejected *for now* because: (a) it adds a second model to a setup that must run locally, roughly doubling local latency on the path the demo uses; (b) with ten eval cases I cannot demonstrate the gain, and adopting an unmeasured complexity increase is the habit this repository is trying to argue against. It is the top retrieval item in the PRD's "what next".

## Consequences

- Robust across both query styles with no tuned constants.
- One database round trip.
- Fused scores are small and unitless, which is why `MIN_GROUNDING_SCORE` is `0.018` rather than something intuitively readable. Documented at the knob.
- Ceiling below a reranked pipeline.
- If embeddings are unavailable, the same query degrades cleanly to lexical-only and the trace says so.

## Revisit when

The golden set is large enough (~50+ cases) to measure a reranker's contribution. Then evaluate `bge-reranker-base` over the fused top-30.
