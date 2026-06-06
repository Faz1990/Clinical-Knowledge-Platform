"""Embed a query and return top-k similar chunks with provenance metadata."""

from __future__ import annotations

import os

from openai import AzureOpenAI

from clinical_platform.store import similarity_search


def _openai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2024-02-01",
    )


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Embed query, run cosine similarity search, return top-k chunks.

    Each returned dict has: chunk_id, guideline_id, guideline_version,
    content_hash, chunk_index, chunk_text, similarity.
    """
    client = _openai_client()
    deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    response = client.embeddings.create(model=deployment, input=[query])
    query_embedding = response.data[0].embedding
    return similarity_search(query_embedding, top_k=top_k)
