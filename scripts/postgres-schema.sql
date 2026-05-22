CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    heading     TEXT,
    content     TEXT NOT NULL,
    embedding   vector(768),
    created_at  TIMESTAMPTZ DEFAULT now()
    UNIQUE (source_file, chunk_index)
);

CREATE INDEX ON documents
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS ingested_files (
    id           SERIAL PRIMARY KEY,
    source_file  TEXT        NOT NULL UNIQUE,
    content_hash TEXT        NOT NULL,
    chunk_count  INTEGER     NOT NULL DEFAULT 0,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memories (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    embedding   vector(768),
    topics      TEXT[]      DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON memories
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX ON documents (source_file);
CREATE INDEX ON ingested_files (source_file);
