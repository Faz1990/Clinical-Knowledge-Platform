# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC ## P9: Retrieval Observability Dashboard
# MAGIC
# MAGIC Reads `clinical_platform.gold.retrieval_telemetry` and renders four panels:
# MAGIC 1. **context_precision trend** — primary alert signal (validated P8-2; rank-weighted AP)
# MAGIC 2. **retrieval_mean_similarity trend** — mean cosine similarity per eval run
# MAGIC 3. **latency trend** — per-question end-to-end latency (embed query + retrieval + LLM)
# MAGIC 4. **freshness banner** — index age vs TTL; trips when `age > TTL`
# MAGIC
# MAGIC **Trust labels (P8 findings):**
# MAGIC - `context_recall`: treat as upper bound — same-model judge inflation (P8-4)
# MAGIC - `faithfulness`: unreliable when judge = generator (P8-5); read generated answers directly
# MAGIC - `context_precision`: validated via interleaved AP test; use as primary signal

# COMMAND ----------

import os
from datetime import datetime, timezone

TELEMETRY_TABLE = "clinical_platform.gold.retrieval_telemetry"
FRESHNESS_TTL_DAYS = int(os.environ.get("FRESHNESS_TTL_DAYS", "7"))

# COMMAND ----------
# MAGIC %md ### Load telemetry

# COMMAND ----------

df = spark.sql(f"SELECT * FROM {TELEMETRY_TABLE} ORDER BY ts")
display(df)

# COMMAND ----------
# MAGIC %md ### Panel 1 — context_precision trend (primary signal)
# MAGIC
# MAGIC Values near 1.0 = retrieved chunks are ranked relevant.
# MAGIC Drop toward 0.0 = vocab mismatch or corpus drift (see P8-2 / P10 postmortem).

# COMMAND ----------

precision_trend = spark.sql(f"""
    SELECT
        eval_run_id,
        MIN(ts) AS run_ts,
        AVG(context_precision) AS mean_precision
    FROM {TELEMETRY_TABLE}
    WHERE eval_run_id IS NOT NULL
    GROUP BY eval_run_id
    ORDER BY run_ts
""")
display(precision_trend)

# COMMAND ----------
# MAGIC %md ### Panel 2 — retrieval_mean_similarity trend
# MAGIC
# MAGIC Average cosine similarity of retrieved chunks per run.
# MAGIC Drops when clinical-vocab questions retrieve off-topic chunks (vocab mismatch signal).

# COMMAND ----------

similarity_trend = spark.sql(f"""
    SELECT
        eval_run_id,
        MIN(ts) AS run_ts,
        AVG(retrieval_mean_similarity) AS mean_similarity,
        AVG(context_recall)            AS mean_recall_upper_bound
    FROM {TELEMETRY_TABLE}
    WHERE eval_run_id IS NOT NULL
    GROUP BY eval_run_id
    ORDER BY run_ts
""")
display(similarity_trend)

# COMMAND ----------
# MAGIC %md ### Panel 3 — latency trend
# MAGIC
# MAGIC End-to-end per-question latency: embed query + pgvector search + Azure OpenAI call.

# COMMAND ----------

latency_trend = spark.sql(f"""
    SELECT
        eval_run_id,
        MIN(ts)         AS run_ts,
        AVG(latency_ms) AS mean_latency_ms,
        MAX(latency_ms) AS max_latency_ms
    FROM {TELEMETRY_TABLE}
    WHERE eval_run_id IS NOT NULL
    GROUP BY eval_run_id
    ORDER BY run_ts
""")
display(latency_trend)

# COMMAND ----------
# MAGIC %md ### Panel 4 — Freshness alert
# MAGIC
# MAGIC `index_built_ts` = MAX(embedded_at) from pgvector at eval time.
# MAGIC Alert trips when `now() - latest index_built_ts > TTL`.

# COMMAND ----------

latest_row = spark.sql(f"""
    SELECT MAX(index_built_ts) AS latest_index_ts
    FROM {TELEMETRY_TABLE}
""").collect()[0]

latest_index_ts = latest_row["latest_index_ts"]

if latest_index_ts is None:
    print("FRESHNESS: no telemetry rows found — index age unknown.")
else:
    now = datetime.now(timezone.utc)
    # index_built_ts stored as UTC; make tz-aware for comparison
    if latest_index_ts.tzinfo is None:
        from datetime import timezone as _tz
        latest_index_ts = latest_index_ts.replace(tzinfo=_tz.utc)
    age_days = (now - latest_index_ts).total_seconds() / 86400

    if age_days > FRESHNESS_TTL_DAYS:
        print(
            f"[FRESHNESS ALERT] Index is {age_days:.1f}d old "
            f"(TTL={FRESHNESS_TTL_DAYS}d). "
            f"Re-index required — run embed_chunks."
        )
    else:
        print(
            f"[Freshness OK] Index is {age_days:.1f}d old "
            f"(TTL={FRESHNESS_TTL_DAYS}d)."
        )

# COMMAND ----------
# MAGIC %md ### P8 baseline reference
# MAGIC
# MAGIC | Metric | Aggregate | Q_P7 | Q2 | Q3a | Q3b |
# MAGIC |---|---|---|---|---|---|
# MAGIC | context_precision | 0.500 | 0.000 | 1.000 | 1.000 | 0.000 |
# MAGIC | context_recall* | 0.917 | 1.000 | 1.000 | 1.000 | 0.667 |
# MAGIC | faithfulness* | 0.867 | 1.000 | 1.000 | 0.667 | 0.800 |
# MAGIC | answer_relevancy | 0.900 | 0.786 | 0.978 | 0.910 | 0.928 |
# MAGIC
# MAGIC *Upper bound — same-model judge inflation (P8-4/P8-5). Precision is the validated signal.
