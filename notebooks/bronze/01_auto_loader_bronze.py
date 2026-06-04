# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC ## Bronze: Auto Loader → guidelines_raw
# MAGIC
# MAGIC Reads PDF/HTML files from the `bronze-files` ADLS container using Auto Loader
# MAGIC (cloudFiles binaryFile format). Computes SHA-256 provenance and appends to the
# MAGIC Bronze Delta table. Idempotent: same file re-landed produces the same content_hash
# MAGIC under a new pipeline_run_id — the idempotency proof for P1.

# COMMAND ----------
import hashlib
from pyspark.sql import functions as F
from pyspark.sql.types import StringType
from pyspark.sql.functions import udf

dbutils.widgets.text("pipeline_run_id", "", "Pipeline Run ID")
dbutils.widgets.text("source_path", "", "Source path (abfss://bronze-files@...)")
dbutils.widgets.text(
    "schema_location", "", "Auto Loader schema/checkpoint path (abfss://autoloader-schema@...)"
)
dbutils.widgets.text(
    "bronze_table", "clinical_platform.bronze.guidelines_raw", "Bronze Delta table"
)

pipeline_run_id = dbutils.widgets.get("pipeline_run_id")
source_path = dbutils.widgets.get("source_path")
schema_location = dbutils.widgets.get("schema_location")
bronze_table = dbutils.widgets.get("bronze_table")

assert pipeline_run_id, "pipeline_run_id widget must be set"
assert source_path, "source_path widget must be set"
assert schema_location, "schema_location widget must be set"


# COMMAND ----------
@udf(returnType=StringType())
def sha256_udf(content: bytes) -> str:
    if content is None:
        return None
    return hashlib.sha256(bytes(content)).hexdigest()


# COMMAND ----------
# Auto Loader: incremental, exactly-once file discovery
df_raw = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "binaryFile")
    .option("cloudFiles.schemaLocation", f"{schema_location}/schema")
    .option("cloudFiles.includeExistingFiles", "true")
    .load(source_path)
)

# COMMAND ----------
# Provenance enrichment — all six required columns
df_bronze = (
    df_raw.withColumn("source_url", F.col("path"))
    .withColumn("retrieved_at", F.col("modificationTime"))
    .withColumn("content_hash", sha256_udf(F.col("content")))
    .withColumn(
        "guideline_version",
        # Extracts date from filename pattern: NG28_2022-11-30.pdf → 2022-11-30
        F.regexp_extract(F.col("path"), r"_(\d{4}-\d{2}-\d{2})\.", 1),
    )
    .withColumn("pipeline_run_id", F.lit(pipeline_run_id))
    .withColumn("ingest_timestamp", F.current_timestamp())
    # Derived convenience column — not one of the six required but useful downstream
    .withColumn("guideline_id", F.regexp_extract(F.col("path"), r"/([A-Z]+\d+)_", 1))
    .select(
        "source_url",
        "retrieved_at",
        "content_hash",
        "guideline_version",
        "pipeline_run_id",
        "ingest_timestamp",
        "guideline_id",
        "content",
        "length",
    )
)

# COMMAND ----------
# Append-only write — never merge/overwrite Bronze
(
    df_bronze.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", f"{schema_location}/checkpoint")
    .option("mergeSchema", "false")
    .trigger(availableNow=True)  # process all queued files then stop (batch semantics)
    .toTable(bronze_table)
    .awaitTermination()
)

# COMMAND ----------
# Proof: show row count and distinct content_hashes per pipeline_run_id
display(spark.sql(f"""
        SELECT
            pipeline_run_id,
            COUNT(*)          AS files_loaded,
            COUNT(DISTINCT content_hash) AS unique_hashes,
            MIN(ingest_timestamp) AS run_start,
            MAX(ingest_timestamp) AS run_end
        FROM {bronze_table}
        GROUP BY pipeline_run_id
        ORDER BY run_start DESC
    """))
