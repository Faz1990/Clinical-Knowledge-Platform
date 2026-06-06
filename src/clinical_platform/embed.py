"""Embedding pipeline: read Gold chunks from Databricks, embed via Azure OpenAI, write to pgvector."""

from __future__ import annotations

import os
import time

from databricks import sql as dbsql
from openai import AzureOpenAI

from clinical_platform.store import upsert_chunks


def _openai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2024-02-01",
    )


def _embed_batch(client: AzureOpenAI, texts: list[str]) -> list[list[float]]:
    deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    response = client.embeddings.create(model=deployment, input=texts)
    return [item.embedding for item in response.data]


def run(batch_size: int = 50) -> None:
    """Read all Gold chunks from Databricks and upsert embeddings into pgvector.

    DATABRICKS_TOKEN is a personal access token for local dev runs.
    In CI/Airflow this should be replaced with an MSAL client-credentials token —
    consistent with the open operator-auth item carried from P6.
    """
    host = os.environ["DATABRICKS_HOST"]
    token = os.environ["DATABRICKS_TOKEN"]
    http_path = os.environ["DATABRICKS_HTTP_PATH"]
    gold_table = os.environ.get("GOLD_CHUNKS_TABLE", "clinical_platform.gold.rag_chunks")

    print(f"Connecting to Databricks: {host}")
    conn = dbsql.connect(server_hostname=host, http_path=http_path, access_token=token)
    client = _openai_client()

    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT chunk_id, guideline_id, guideline_version, content_hash,
                   chunk_index, total_chunks, chunk_text
            FROM {gold_table}
            ORDER BY guideline_id, chunk_index
        """)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        chunks = [dict(zip(columns, row)) for row in rows]
        cursor.close()
    finally:
        conn.close()

    print(f"Fetched {len(chunks)} chunks from Gold")

    total_written = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["chunk_text"] for c in batch]
        embeddings = _embed_batch(client, texts)

        records = [{**chunk, "embedding": emb} for chunk, emb in zip(batch, embeddings)]
        written = upsert_chunks(records)
        total_written += written
        print(f"  Batch {i // batch_size + 1}: {written} chunks upserted")

        # Stay within Azure OpenAI rate limits (~18k tokens/batch on S0)
        if i + batch_size < len(chunks):
            time.sleep(0.5)

    print(f"Done. {total_written} total chunks in pgvector.")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    run()
