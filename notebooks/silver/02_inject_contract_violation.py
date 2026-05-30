# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC ## Demo: Structural Gate — Inject a Bad Bronze Row
# MAGIC
# MAGIC **Purpose:** Demonstrate Gate 1 (structural contract) in isolation.
# MAGIC
# MAGIC Injects one synthetic row with four deliberate structural violations:
# MAGIC - `NULL_PROVENANCE:content_hash` — hash is null
# MAGIC - `INVALID_VERSION_FORMAT` — guideline_version is not `YYYY-MM-DD`
# MAGIC - `EMPTY_CONTENT` — length is 0
# MAGIC - `INVALID_GUIDELINE_ID` — guideline_id is lowercase
# MAGIC
# MAGIC **Note — you do not need this notebook for the semantic gate story.**
# MAGIC NG17, NG3, and NG18 are already in the corpus and will quarantine automatically
# MAGIC with `INVALID_CLINICAL_AREA` when `01_bronze_to_silver` runs against real data.
# MAGIC This notebook exists only to demo structural violations on demand.
# MAGIC
# MAGIC Tagged `pipeline_run_id = demo-contract-violation-001` for easy identification and cleanup.

# COMMAND ----------
from pyspark.sql import Row
from pyspark.sql import functions as F
from pyspark.sql import types as T

dbutils.widgets.text("bronze_table", "clinical_platform.bronze.guidelines_raw", "Bronze table")
bronze_table = dbutils.widgets.get("bronze_table")

DEMO_RUN_ID = "demo-contract-violation-001"

# COMMAND ----------
schema = T.StructType([
    T.StructField("source_url",        T.StringType()),
    T.StructField("retrieved_at",      T.TimestampType()),
    T.StructField("content_hash",      T.StringType()),    # intentionally null
    T.StructField("guideline_version", T.StringType()),    # intentionally malformed
    T.StructField("pipeline_run_id",   T.StringType()),
    T.StructField("ingest_timestamp",  T.TimestampType()),
    T.StructField("guideline_id",      T.StringType()),    # intentionally lowercase
    T.StructField("content",           T.BinaryType()),
    T.StructField("length",            T.LongType()),      # intentionally 0
])

bad_row = spark.createDataFrame(
    [Row(
        source_url        = "DEMO_BAD_ROW — safe to delete after P2 demo",
        retrieved_at      = None,
        content_hash      = None,           # → NULL_PROVENANCE:content_hash
        guideline_version = "INVALID",      # → INVALID_VERSION_FORMAT
        pipeline_run_id   = DEMO_RUN_ID,
        ingest_timestamp  = None,
        guideline_id      = "invalid-row",  # → INVALID_GUIDELINE_ID
        content           = b"",
        length            = 0,              # → EMPTY_CONTENT
    )],
    schema=schema,
)

bad_row.write.format("delta").mode("append").saveAsTable(bronze_table)

print(f"Injected 1 bad row with pipeline_run_id='{DEMO_RUN_ID}'")
print("Now run 01_bronze_to_silver with pipeline_run_id='demo-contract-violation-001'")
print("Expected: row quarantined with 4 reason codes; Silver row count unchanged.")

# COMMAND ----------
display(
    spark.sql(f"""
        SELECT source_url, content_hash, guideline_version, guideline_id, length, pipeline_run_id
        FROM {bronze_table}
        WHERE pipeline_run_id = '{DEMO_RUN_ID}'
    """)
)
