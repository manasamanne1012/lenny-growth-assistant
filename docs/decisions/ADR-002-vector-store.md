# ADR-002 — pgvector in the application database, not a dedicated vector store

**Status:** Accepted · **Date:** 2026-09 · **Affects:** `migrations/001_init.sql`, `db/repository.py`, `docker-compose.yml`

## Context

The brief mandates PostgreSQL for session persistence and requires the whole system to start with one command on an evaluator's laptop. Embeddings need to live somewhere searchable.

## Decision

Store embeddings in the same PostgreSQL instance using `pgvector`, in a `chunks` table alongside a generated `tsvector` column.

## Alternatives considered

**A dedicated vector database (Qdrant, Weaviate, Chroma).** Better ANN ergonomics and better performance at scale. Rejected here for three reasons, in order of weight:

1. **Hybrid retrieval becomes a distributed join.** The core retrieval design (ADR-003) fuses vector and lexical rankings. With both in Postgres that is one SQL statement. Split across two systems it becomes two round trips, fused in Python, with two failure modes and two consistency stories.
2. **A fourth container** to start, health-check, document, and debug — against a brief that is explicitly graded on one-command startup.
3. **Transactional consistency for free.** A transcript row and its chunks commit or roll back together. Across two stores that requires reconciliation logic that is pure downside at this scale.

**FAISS or an in-process index.** Rejected: no persistence story, no concurrent access, and rebuilding the index on boot is a bad first-run experience.

**Managed (Pinecone).** Rejected: an API key requirement in a local-first, offline-capable brief.

## Consequences

- One database to run, back up, and reason about.
- Hybrid search is a single statement — see `repository.hybrid_search`.
- `ivfflat` requires `ANALYZE` after bulk insert to be useful; ingest does this.
- **The vector column has a fixed width.** Changing embedding model is therefore a schema change. Made explicit: startup warns, `make doctor` catches it, `make resize-embeddings DIM=n` performs it, re-ingestion follows. Hiding this would produce silent dimension-mismatch errors at query time, which are miserable to diagnose.
- ANN quality below a dedicated store at large scale.

## Revisit when

Chunk count passes a few million, or recall at fixed latency becomes the bottleneck. The first step then is HNSW with tuned `ef_search` inside Postgres — still cheaper than a second datastore. All retrieval SQL is confined to `repository.py` to keep that migration contained.
