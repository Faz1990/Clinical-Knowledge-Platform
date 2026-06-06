"""pgvector connection, upsert, and similarity search — raw psycopg2, no ORM."""

from __future__ import annotations

import os
from typing import Any

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector


def _conn() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=os.environ["PGVECTOR_HOST"],
        port=int(os.environ.get("PGVECTOR_PORT", 5432)),
        dbname=os.environ["PGVECTOR_DB"],
        user=os.environ["PGVECTOR_USER"],
        password=os.environ["PGVECTOR_PASSWORD"],
    )
    register_vector(conn)
    return conn


def upsert_chunks(rows: list[dict[str, Any]]) -> int:
    """Insert or replace embedding rows. Returns number of rows written."""
    if not rows:
        return 0

    sql = """
        INSERT INTO guideline_embeddings
            (chunk_id, guideline_id, guideline_version, content_hash,
             chunk_index, total_chunks, chunk_text, embedding)
        VALUES
            (%(chunk_id)s, %(guideline_id)s, %(guideline_version)s, %(content_hash)s,
             %(chunk_index)s, %(total_chunks)s, %(chunk_text)s, %(embedding)s)
        ON CONFLICT (chunk_id) DO UPDATE SET
            embedding   = EXCLUDED.embedding,
            embedded_at = NOW()
    """
    conn = _conn()
    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, sql, rows, page_size=100)
        return len(rows)
    finally:
        conn.close()


def similarity_search(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Return top-k chunks by cosine similarity. Each row includes provenance metadata."""
    sql = """
        SELECT
            chunk_id,
            guideline_id,
            guideline_version,
            content_hash,
            chunk_index,
            chunk_text,
            1 - (embedding <=> %s::vector) AS similarity
        FROM guideline_embeddings
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (query_embedding, query_embedding, top_k))
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
