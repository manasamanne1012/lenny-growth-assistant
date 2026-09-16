-- 002_embedding_dim.sql — resize the embedding column when the operator picks a
-- model with a different dimensionality (e.g. OpenAI text-embedding-3-small at
-- 1536 instead of nomic-embed-text at 768).
--
-- This file is NOT run automatically. Run it deliberately, then re-ingest:
--     make resize-embeddings DIM=1536 && make ingest
--
-- Placeholder :dim is substituted by scripts/resize_embeddings.py.

DROP INDEX IF EXISTS chunks_embedding_idx;
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(:dim) USING NULL;
CREATE INDEX chunks_embedding_idx ON chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
