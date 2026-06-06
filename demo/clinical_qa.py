"""End-to-end clinical Q&A demo.

Run:
    cd <repo-root>
    docker-compose up -d          # start pgvector
    python -m clinical_platform.embed   # embed Gold chunks (first time only)
    python demo/clinical_qa.py

Citations in the output resolve to guideline_id + guideline_version in dim_guideline.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from clinical_platform.qa import ask  # noqa: E402 — must load env before imports

QUESTION = (
    "What HbA1c target is recommended for adults with type 2 diabetes on dual therapy, "
    "and when should a third agent be added?"
)


def main() -> None:
    print(f"Question: {QUESTION}\n")
    result = ask(QUESTION, top_k=5)

    print("Answer:")
    print(result.answer)
    print()
    print("Citations (resolve via dim_guideline on guideline_id + guideline_version):")
    for c in result.citations:
        print(
            f"  {c.guideline_id}  version={c.guideline_version}"
            f"  chunk={c.chunk_index}  similarity={c.similarity}"
        )


if __name__ == "__main__":
    main()
