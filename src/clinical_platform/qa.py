"""Assemble retrieved context, call Azure OpenAI, return answer with resolvable citations."""

from __future__ import annotations

import os
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from clinical_platform.retriever import retrieve


@dataclass
class Citation:
    guideline_id: str
    guideline_version: str
    chunk_index: int
    similarity: float


@dataclass
class Answer:
    question: str
    answer: str
    citations: list[Citation]


_SYSTEM_PROMPT = """\
You are a clinical knowledge assistant. Answer the question using ONLY the provided
guideline excerpts. Be concise and precise. After your answer, list the guideline
references you used — these will be appended automatically; do not add them yourself.
If the excerpts do not contain enough information to answer, say so explicitly."""


def ask(question: str, top_k: int = 5) -> Answer:
    """Retrieve relevant chunks and return a cited answer.

    Citations carry guideline_id + guideline_version, which resolve to a specific
    row in dim_guideline (the canonical current-state dimension).
    """
    chunks = retrieve(question, top_k=top_k)

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[{i}] {chunk['guideline_id']} v{chunk['guideline_version']} "
            f"(chunk {chunk['chunk_index']}):\n{chunk['chunk_text']}"
        )
    context = "\n\n".join(context_parts)

    llm = AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2024-02-01",
        azure_deployment=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
        temperature=0,
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Question: {question}\n\nGuideline excerpts:\n{context}"),
    ]
    response = llm.invoke(messages)

    citations = [
        Citation(
            guideline_id=c["guideline_id"],
            guideline_version=c["guideline_version"],
            chunk_index=c["chunk_index"],
            similarity=round(c["similarity"], 4),
        )
        for c in chunks
    ]

    return Answer(question=question, answer=response.content, citations=citations)
