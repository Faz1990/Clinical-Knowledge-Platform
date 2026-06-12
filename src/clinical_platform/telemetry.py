"""Retrieval telemetry — write eval rows to Delta and check index freshness."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

_TELEMETRY_TABLE = "clinical_platform.gold.retrieval_telemetry"

# DOUBLE (64-bit) matches RAGAS float64 output. Column name retrieval_mean_similarity
# is intentional: mean cosine similarity of retrieved chunks, not citation coverage
# (fraction of answer claims cited — a different, harder-to-compute metric).
_CREATE_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TELEMETRY_TABLE} (
  ts                        TIMESTAMP,
  question                  STRING,
  latency_ms                BIGINT,
  k                         INT,
  retrieval_mean_similarity DOUBLE,
  index_built_ts            TIMESTAMP,
  eval_run_id               STRING,
  context_precision         DOUBLE,
  context_recall            DOUBLE
)
USING DELTA
"""


def _float_or_none(v) -> float | None:
    """Convert to float; return None for NaN or unconvertible values."""
    try:
        f = float(v)
        return None if f != f else f  # NaN != NaN is True in IEEE 754
    except (TypeError, ValueError):
        return None


def get_index_built_ts() -> datetime:
    """Return MAX(embedded_at) from pgvector — when the vector index was last built.

    Returns epoch (1970-01-01) when the table is empty. An unbuilt index is
    maximally stale, not fresh — callers comparing against a TTL will trip
    the freshness alert immediately, which is the correct behaviour.
    """
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ["PGVECTOR_HOST"],
        port=int(os.environ.get("PGVECTOR_PORT", 5432)),
        dbname=os.environ["PGVECTOR_DB"],
        user=os.environ["PGVECTOR_USER"],
        password=os.environ["PGVECTOR_PASSWORD"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(embedded_at) FROM guideline_embeddings")
            result = cur.fetchone()[0]
            if result is None:
                # Empty table: epoch age = now() - epoch → always trips any reasonable TTL
                return datetime(1970, 1, 1, tzinfo=timezone.utc)
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    finally:
        conn.close()


def write_eval_telemetry(
    eval_run_id: str,
    per_q_df: pd.DataFrame,
    index_built_ts: datetime,
) -> None:
    """Write per-question eval rows to clinical_platform.gold.retrieval_telemetry.

    Idempotent: DELETE WHERE eval_run_id = X, then a single multi-row INSERT.
    A retry of the same eval_run_id produces exactly one set of rows. The single
    INSERT is one Delta commit, so VERSION AS OF replays whole runs not individual rows.

    run_id uniqueness (caller responsibility): use timestamp + uuid suffix so DELETE
    matches only partial rows from a prior failed attempt, never a different run.

    Skipped with a warning if DATABRICKS_HOST is not set (local-only mode).

    per_q_df expected columns: question, latency_ms, k, retrieval_mean_similarity,
    context_precision, context_recall.
    """
    if not os.environ.get("DATABRICKS_HOST"):
        print("DATABRICKS_HOST not set — skipping Delta telemetry write (local-only mode)")
        return

    from databricks import sql as dbsql

    host = os.environ["DATABRICKS_HOST"]
    token = os.environ["DATABRICKS_TOKEN"]
    http_path = os.environ["DATABRICKS_HTTP_PATH"]

    now = datetime.now(timezone.utc)
    if index_built_ts.tzinfo is None:
        index_built_ts = index_built_ts.replace(tzinfo=timezone.utc)

    rows_params = []
    for _, row in per_q_df.iterrows():
        rows_params.append(
            (
                now,
                str(row["question"]),
                int(row["latency_ms"]),
                int(row["k"]),
                _float_or_none(row.get("retrieval_mean_similarity")),
                index_built_ts,
                eval_run_id,
                _float_or_none(row.get("context_precision")),
                _float_or_none(row.get("context_recall")),
            )
        )

    conn = dbsql.connect(server_hostname=host, http_path=http_path, access_token=token)
    try:
        cursor = conn.cursor()
        cursor.execute(_CREATE_DDL)

        # Idempotency: clear any rows from a prior failed attempt for this run_id
        cursor.execute(
            f"DELETE FROM {_TELEMETRY_TABLE} WHERE eval_run_id = %s",
            (eval_run_id,),
        )

        if not rows_params:
            print(f"Telemetry: 0 rows for eval_run_id={eval_run_id} — nothing to write")
            return  # DELETE already ran; a re-run will clear any prior partial

        # Single multi-row INSERT = one Delta commit = one replayable VERSION AS OF
        placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows_params))
        flat_params = [v for row in rows_params for v in row]
        cursor.execute(
            f"INSERT INTO {_TELEMETRY_TABLE} VALUES {placeholders}",
            flat_params,
        )

        print(
            f"Telemetry: {len(rows_params)} rows -> {_TELEMETRY_TABLE}"
            f" (eval_run_id={eval_run_id})"
        )
    finally:
        conn.close()
