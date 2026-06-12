"""P10: Induce and restore silent RAG degradation via embedding model swap.

Three operations:
  snapshot  — identify Q2/Q3a top-5 chunks via live retriever, save full rows
              (including original embeddings) to data/p10_snapshot.json
  induce    — re-embed snapshotted chunks with a drift model, upsert to pgvector
  restore   — restore original embeddings from snapshot

Typical P10 sequence:
  1. python demo/p10_induce_degradation.py snapshot
  2. python -m clinical_platform.eval          # measures the degraded state
  3. python demo/observability_report.py       # Panel 1 shows the drop; Panel 3 shows FRESH
  4. python demo/p10_induce_degradation.py restore
  5. python -m clinical_platform.eval          # verify precision returns to ~0.500

Step 5 closes the full arc: induce → detect → diagnose → recover → verify recovery.
Without it "restored" is an assertion, not a demonstrated fact.

NOTE — expected magnitude: Q3a precision will drop from 1.0 to some value < 1.0, not
necessarily 0.0. Re-embedding the targeted chunks means other chunks rise into top-5;
if any are incidentally on-topic, Q3a lands between 0 and 1. The falsifier is Q3a < 1.0
and Q_P7 unchanged at 0.0 (already broken, unaffected by this subset). Precision returning
to ~0.500 aggregate after restore confirms recovery.

NOTE — freshness blindness (postmortem headline): both induce and restore update
embedded_at to NOW() via the upsert ON CONFLICT clause. The freshness alert reads
the index as FRESH throughout the entire incident — during active degradation and after
restore — while remaining structurally silent about what model produced the embeddings.
Only the eval signal catches the degradation, and only the eval signal confirms recovery.
This is the eval-as-infrastructure argument demonstrated rather than asserted.

Requires .env with AZURE_OPENAI_* and PGVECTOR_* vars.
For induce, --model must match a deployment that exists in your Azure OpenAI resource
and returns 1536-dim vectors (ada-002 or text-embedding-3-large with dimensions=1536).
Cost hygiene: create the ada-002 deployment before induce, delete it straight after.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

_TARGET_QUESTION_IDS = {"Q2", "Q3a"}
_SNAPSHOT_PATH = _REPO_ROOT / "data" / "p10_snapshot.json"
_EVAL_QUESTIONS_PATH = _REPO_ROOT / "data" / "eval_questions.json"


def _load_target_questions() -> list[dict]:
    pairs = json.loads(_EVAL_QUESTIONS_PATH.read_text(encoding="utf-8"))
    return [p for p in pairs if p["id"] in _TARGET_QUESTION_IDS]


def _fetch_rows_by_chunk_ids(chunk_ids: list[str]) -> list[dict]:
    """Query pgvector for full rows including the embedding vector."""
    import psycopg2
    import psycopg2.extras
    from pgvector.psycopg2 import register_vector

    conn = psycopg2.connect(
        host=os.environ["PGVECTOR_HOST"],
        port=int(os.environ.get("PGVECTOR_PORT", 5432)),
        dbname=os.environ["PGVECTOR_DB"],
        user=os.environ["PGVECTOR_USER"],
        password=os.environ["PGVECTOR_PASSWORD"],
    )
    register_vector(conn)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT chunk_id, guideline_id, guideline_version, content_hash,
                       chunk_index, total_chunks, chunk_text, embedding
                FROM guideline_embeddings
                WHERE chunk_id = ANY(%s)
                """,
                (chunk_ids,),
            )
            rows = []
            for row in cur.fetchall():
                r = dict(row)
                # numpy float32 → Python float for JSON serialisation
                r["embedding"] = [float(x) for x in r["embedding"]]
                rows.append(r)
        return rows
    finally:
        conn.close()


def _embed_texts(texts: list[str], deployment: str) -> list[list[float]]:
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2024-02-01",
    )
    response = client.embeddings.create(model=deployment, input=texts)
    # Sort by index: the API does not guarantee input order in batched responses.
    # Correctness matters if this helper is reused in a serving path (P3+).
    return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


def cmd_snapshot() -> None:
    from clinical_platform.retriever import retrieve

    targets = _load_target_questions()
    ids_label = ", ".join(t["id"] for t in targets)
    print(f"Identifying top-5 chunks for {len(targets)} precision-1.0 questions ({ids_label})...")

    chunk_ids_seen: set[str] = set()
    for t in targets:
        results = retrieve(t["question"], top_k=5)
        print(f"\n  [{t['id']}] {t['question'][:70]}...")
        for r in results:
            print(f"    {r['chunk_id']}  sim={r['similarity']:.4f}")
            chunk_ids_seen.add(r["chunk_id"])

    target_ids = list(chunk_ids_seen)
    print(f"\nUnique target chunk_ids: {len(target_ids)}")

    print("Fetching full rows including embeddings from pgvector...")
    rows = _fetch_rows_by_chunk_ids(target_ids)
    if len(rows) != len(target_ids):
        print(f"WARNING: expected {len(target_ids)} rows, fetched {len(rows)}")

    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    dim = len(rows[0]["embedding"]) if rows else 0
    print(f"Snapshot saved -> {_SNAPSHOT_PATH}  ({len(rows)} rows, {dim}-dim embeddings)")
    print("\nNext: python demo/p10_induce_degradation.py induce --model <deployment-name>")


def cmd_induce(drift_model: str) -> None:
    if not _SNAPSHOT_PATH.exists():
        print(f"ERROR: snapshot not found at {_SNAPSHOT_PATH}")
        print("Run: python demo/p10_induce_degradation.py snapshot")
        sys.exit(1)

    rows = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    original_dim = len(rows[0]["embedding"])
    print(f"Re-embedding {len(rows)} chunks with '{drift_model}'...")

    texts = [r["chunk_text"] for r in rows]
    new_embeddings = _embed_texts(texts, drift_model)

    new_dim = len(new_embeddings[0])
    if new_dim != original_dim:
        print(
            f"ERROR: dimensionality mismatch — index is {original_dim}-dim, "
            f"'{drift_model}' returned {new_dim}-dim.\n"
            f"       Use ada-002 (1536) or text-embedding-3-large with dimensions=1536."
        )
        sys.exit(1)

    from clinical_platform.store import upsert_chunks

    upsert_rows = [{**r, "embedding": emb} for r, emb in zip(rows, new_embeddings)]
    written = upsert_chunks(upsert_rows)

    print(f"\nUpserted {written} chunks with '{drift_model}' embeddings.")
    print("embedded_at updated to NOW() — freshness alert reads the index as FRESH.")
    print("The system keeps running. Cosine similarity computes silently; means nothing.")
    print("Only the eval signal will detect the degradation.\n")
    print("Next: python -m clinical_platform.eval")


def cmd_restore() -> None:
    if not _SNAPSHOT_PATH.exists():
        print(f"ERROR: snapshot not found at {_SNAPSHOT_PATH}")
        sys.exit(1)

    rows = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    print(f"Restoring {len(rows)} chunks to original text-embedding-3-small embeddings...")

    from clinical_platform.store import upsert_chunks

    written = upsert_chunks(rows)

    # Verify the write landed at the data layer — "Restored N chunks" counts rows submitted,
    # not rows modified. A silent no-op here invalidates both the recovery verification and
    # the P8-5 context read in the next step.
    check = _fetch_rows_by_chunk_ids([rows[0]["chunk_id"]])[0]["embedding"]
    orig = rows[0]["embedding"]
    ok = len(check) == len(orig) and all(abs(a - b) < 1e-6 for a, b in zip(check[:8], orig[:8]))
    print(f"Restore write verified against pgvector: {ok}")
    if not ok:
        print(
            "FAIL: re-fetched embedding != snapshot — upsert likely DO NOTHING."
            " Recovery NOT demonstrated."
        )
        sys.exit(1)

    print(f"Restored {written} chunks. Original 3-small embeddings verified in pgvector.")
    print("embedded_at updated to NOW() — freshness reads FRESH (as it did throughout).")
    print("The entire incident — degradation and recovery — was invisible to the freshness alert.")
    print("\nNext: python -m clinical_platform.eval   (verify precision returns to ~0.500)")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="P10: Induce / restore silent RAG degradation via embedding model swap."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "snapshot",
        help="Identify Q2/Q3a top-5 chunks and save rows+embeddings to data/p10_snapshot.json.",
    )
    p_induce = sub.add_parser(
        "induce",
        help="Re-embed the snapshotted chunks with a drift model and upsert to pgvector.",
    )
    p_induce.add_argument(
        "--model",
        default="text-embedding-ada-002",
        help="Azure OpenAI deployment name for the drift model (default: text-embedding-ada-002)",
    )
    sub.add_parser(
        "restore",
        help="Restore original embeddings from snapshot.",
    )

    args = parser.parse_args()

    if args.cmd == "snapshot":
        cmd_snapshot()
    elif args.cmd == "induce":
        cmd_induce(args.model)
    elif args.cmd == "restore":
        cmd_restore()


if __name__ == "__main__":
    main()
