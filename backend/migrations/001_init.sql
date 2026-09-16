-- 001_init.sql — base schema for The Lenny Growth Assistant.
-- Applied idempotently at startup by app/db/bootstrap.py.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------- sessions
CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY,
    title           TEXT        NOT NULL DEFAULT 'New chat',
    user_id         TEXT        NOT NULL DEFAULT 'local-evaluator',
    user_metadata   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    provider        TEXT,
    model           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS sessions_user_updated_idx
    ON sessions (user_id, updated_at DESC);

-- ---------------------------------------------------------------- messages
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY,
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user','assistant','system')),
    content         TEXT        NOT NULL,
    skill           TEXT,
    grounding       TEXT        CHECK (grounding IN ('grounded','partial','ungrounded','abstained','n/a')),
    citations       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    trace           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    provider        TEXT,
    model           TEXT,
    latency_ms      INTEGER,
    token_usage     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_session_created_idx
    ON messages (session_id, created_at);

-- --------------------------------------------------------------- artifacts
CREATE TABLE IF NOT EXISTS artifacts (
    id              UUID PRIMARY KEY,
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id      UUID        REFERENCES messages(id) ON DELETE SET NULL,
    kind            TEXT        NOT NULL CHECK (kind IN ('markdown','html')),
    title           TEXT        NOT NULL DEFAULT 'Untitled artifact',
    content         TEXT        NOT NULL,
    sanitized       BOOLEAN     NOT NULL DEFAULT false,
    sanitizer_report JSONB      NOT NULL DEFAULT '{}'::jsonb,
    version         INTEGER     NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS artifacts_session_created_idx
    ON artifacts (session_id, created_at DESC);

-- ------------------------------------------------------------ transcripts
CREATE TABLE IF NOT EXISTS transcripts (
    id              UUID PRIMARY KEY,
    source_id       TEXT        NOT NULL UNIQUE,   -- stable slug, e.g. repo file path
    title           TEXT        NOT NULL,
    guest           TEXT,
    episode_url     TEXT,
    published_on    DATE,
    source_path     TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,          -- drives incremental re-ingest
    word_count      INTEGER     NOT NULL DEFAULT 0,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id              UUID PRIMARY KEY,
    transcript_id   UUID        NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    chunk_index     INTEGER     NOT NULL,
    content         TEXT        NOT NULL,
    heading         TEXT,
    speaker         TEXT,
    start_char      INTEGER     NOT NULL DEFAULT 0,
    token_estimate  INTEGER     NOT NULL DEFAULT 0,
    embedding       vector(768),
    tsv             TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (transcript_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx  ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_trgm_idx ON chunks USING GIN (content gin_trgm_ops);

-- IVFFlat needs data before it helps; created here so it exists, ANALYZE after ingest.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'chunks_embedding_idx') THEN
        EXECUTE 'CREATE INDEX chunks_embedding_idx ON chunks
                 USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'skipping ivfflat index: %', SQLERRM;
END $$;

-- -------------------------------------------------------------- eval runs
CREATE TABLE IF NOT EXISTS eval_runs (
    id              UUID PRIMARY KEY,
    label           TEXT        NOT NULL,
    provider        TEXT,
    model           TEXT,
    summary         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    results         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
