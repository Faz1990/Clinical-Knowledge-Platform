CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS guideline_embeddings (
    chunk_id          TEXT PRIMARY KEY,
    guideline_id      TEXT NOT NULL,
    guideline_version TEXT NOT NULL,
    content_hash      TEXT NOT NULL,
    chunk_index       INT NOT NULL,
    total_chunks      INT NOT NULL,
    chunk_text        TEXT NOT NULL,
    embedding         VECTOR(1536),
    embedded_at       TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast approximate cosine similarity search.
-- Works on small corpora without a minimum row count requirement (unlike IVFFlat).
CREATE INDEX IF NOT EXISTS idx_embedding_hnsw
ON guideline_embeddings USING hnsw (embedding vector_cosine_ops);
