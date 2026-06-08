"""RAGAS eval harness: score the RAG pipeline over curated Q/A pairs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from datasets import Dataset
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

from clinical_platform.qa import ask

_REPO_ROOT = Path(__file__).parent.parent.parent
EVAL_QUESTIONS_PATH = _REPO_ROOT / "data" / "eval_questions.json"
SCORES_DIR = _REPO_ROOT / "data" / "ragas_scores"


def _llm() -> LangchainLLMWrapper:
    return LangchainLLMWrapper(
        AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            api_version="2024-02-01",
            azure_deployment=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
            temperature=0,
        )
    )


def _embeddings() -> LangchainEmbeddingsWrapper:
    # langchain-openai 0.1.x: AzureOpenAIEmbeddings uses `deployment`, not `azure_deployment`
    return LangchainEmbeddingsWrapper(
        AzureOpenAIEmbeddings(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            openai_api_version="2024-02-01",
            deployment=os.environ.get(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
            ),
        )
    )


def run(
    questions_path: Path = EVAL_QUESTIONS_PATH,
    save_csv: bool = True,
) -> dict[str, float]:
    """Run RAGAS eval over curated Q/A pairs. Returns aggregate scores dict."""
    pairs = json.loads(questions_path.read_text(encoding="utf-8"))

    records: dict[str, list] = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    print(f"Running RAG pipeline over {len(pairs)} questions...")
    for pair in pairs:
        result = ask(pair["question"], top_k=5)
        records["question"].append(pair["question"])
        records["answer"].append(result.answer)
        records["contexts"].append([c.chunk_text for c in result.citations])
        records["ground_truth"].append(pair["ground_truth"])
        print(f"  [{pair['id']}] retrieved {len(result.citations)} chunks")

    dataset = Dataset.from_dict(records)

    print("Scoring with RAGAS (ragas==0.1.22)...")
    scores = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=_llm(),
        embeddings=_embeddings(),
    )

    # Persist before rendering — display failures must not discard a completed scoring run
    if save_csv:
        SCORES_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = SCORES_DIR / f"baseline_{ts}.csv"
        scores.to_pandas().to_csv(path, index=False)
        print(f"Scores saved -> {path}")

    _print_table(scores)

    return {
        "faithfulness": scores["faithfulness"],
        "answer_relevancy": scores["answer_relevancy"],
        "context_precision": scores["context_precision"],
        "context_recall": scores["context_recall"],
    }


def _print_table(scores) -> None:
    print("\n-- RAGAS Baseline Scores ------------------------------------------")
    print(f"  faithfulness       {scores['faithfulness']:.3f}")
    print(f"  answer_relevancy   {scores['answer_relevancy']:.3f}")
    print(f"  context_precision  {scores['context_precision']:.3f}")
    print(f"  context_recall     {scores['context_recall']:.3f}")
    print("-------------------------------------------------------------------")
    df = scores.to_pandas()
    metric_cols = [
        c for c in [
            "question", "faithfulness", "answer_relevancy",
            "context_precision", "context_recall",
        ]
        if c in df.columns
    ]
    print("\nPer-question breakdown:")
    print(df[metric_cols].to_string(index=False))


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    from dotenv import load_dotenv

    load_dotenv()
    run()
