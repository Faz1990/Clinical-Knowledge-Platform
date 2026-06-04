# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC ## Silver: Two-Gate Contract Pipeline
# MAGIC
# MAGIC **P2 flagship failure story — data-contract catch.**
# MAGIC
# MAGIC Two gates, two failure classes, one quarantine table:
# MAGIC
# MAGIC ```
# MAGIC Bronze
# MAGIC   │
# MAGIC   ├─[Gate 1: Structural] ── provenance null / bad hash / bad date / empty / bad ID
# MAGIC   │     └─ INVALID → quarantine (reason codes: NULL_PROVENANCE, INVALID_HASH_FORMAT, ...)
# MAGIC   │
# MAGIC   ├─[Manifest join on filename — 1:1, no fan-out]
# MAGIC   │
# MAGIC   ├─[Gate 2: Semantic]  ── scope check against ACCEPTED_CLINICAL_AREAS
# MAGIC   │     ├─ null expected_clinical_area  → quarantine: MISSING_MANIFEST_ENTRY
# MAGIC   │     └─ out-of-scope (e.g. NG17 type_1_diabetes) → quarantine: INVALID_CLINICAL_AREA
# MAGIC   │
# MAGIC   └─[Parse + MERGE] ── PDF text extracted, deduped on content_hash → Silver
# MAGIC ```
# MAGIC
# MAGIC **Design notes:**
# MAGIC - Structural gate is row-only (no external lookups) — can run before manifest join
# MAGIC - Semantic gate requires the manifest join; signal does not exist earlier
# MAGIC - Join key is `filename` (unique per document) — avoids NG28 fan-out on `guideline_id`
# MAGIC - `ACCEPTED_CLINICAL_AREAS` config is git-versioned in `src/clinical_platform/config.py`
# MAGIC - Structural UDF mirrors `contract.py`; scope logic mirrors `scope.py`.
# MAGIC   TODO P6: install wheel so notebook imports directly, eliminating drift.

# COMMAND ----------
# MAGIC %pip install pdfplumber --quiet

# COMMAND ----------
import io
import re

import pandas as pd
import pdfplumber
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql import Window

dbutils.widgets.text("pipeline_run_id", "", "Pipeline Run ID")
dbutils.widgets.text("bronze_table", "clinical_platform.bronze.guidelines_raw", "Bronze table")
dbutils.widgets.text("silver_table", "clinical_platform.silver.guidelines_parsed", "Silver table")
dbutils.widgets.text(
    "quarantine_table", "clinical_platform.silver.guidelines_quarantine", "Quarantine table"
)
dbutils.widgets.text(
    "manifest_table", "clinical_platform.bronze.guidelines_manifest", "Manifest UC table"
)

pipeline_run_id = dbutils.widgets.get("pipeline_run_id")
bronze_table = dbutils.widgets.get("bronze_table")
silver_table = dbutils.widgets.get("silver_table")
quarantine_table = dbutils.widgets.get("quarantine_table")
manifest_table = dbutils.widgets.get("manifest_table")

assert pipeline_run_id, "pipeline_run_id widget must be set"

# COMMAND ----------
# MAGIC %md ### Gate 1 — Structural contract
# MAGIC
# MAGIC Mirrors `src/clinical_platform/contract.py` (unit-tested via pytest).
# MAGIC Five rules, all row-only — no external state required.
# MAGIC TODO P6: replace inline logic with direct import once wheel is installed on cluster.

# COMMAND ----------
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GID = re.compile(r"^[A-Z]+\d+$")


@F.pandas_udf(T.ArrayType(T.StringType()))
def validate_contract(
    source_url: pd.Series,
    retrieved_at: pd.Series,
    content_hash: pd.Series,
    guideline_version: pd.Series,
    p_run_id: pd.Series,
    ingest_timestamp: pd.Series,
    length: pd.Series,
    guideline_id: pd.Series,
) -> pd.Series:
    provenance = {
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "content_hash": content_hash,
        "guideline_version": guideline_version,
        "pipeline_run_id": p_run_id,
        "ingest_timestamp": ingest_timestamp,
    }
    results = []
    for i in range(len(source_url)):
        reasons = []
        for col, series in provenance.items():
            val = series.iloc[i]
            if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
                reasons.append(f"NULL_PROVENANCE:{col}")
        ch = str(content_hash.iloc[i] or "")
        if ch and not _SHA256.match(ch):
            reasons.append("INVALID_HASH_FORMAT")
        gv = str(guideline_version.iloc[i] or "")
        if gv and not _DATE.match(gv):
            reasons.append("INVALID_VERSION_FORMAT")
        ln = length.iloc[i]
        if ln is None or pd.isna(ln) or int(ln) <= 0:
            reasons.append("EMPTY_CONTENT")
        gid = str(guideline_id.iloc[i] or "")
        if not gid or not _GID.match(gid):
            reasons.append("INVALID_GUIDELINE_ID")
        results.append(reasons)
    return pd.Series(results)


# COMMAND ----------
# MAGIC %md ### PDF parsing UDF

# COMMAND ----------
_parse_schema = T.StructType(
    [
        T.StructField("parsed_text", T.StringType()),
        T.StructField("page_count", T.IntegerType()),
        T.StructField("char_count", T.IntegerType()),
        T.StructField("word_count", T.IntegerType()),
    ]
)


@F.pandas_udf(_parse_schema)
def parse_pdf(content_series: pd.Series) -> pd.DataFrame:
    results = []
    for content in content_series:
        if content is None:
            results.append({"parsed_text": None, "page_count": 0, "char_count": 0, "word_count": 0})
            continue
        try:
            with pdfplumber.open(io.BytesIO(bytes(content))) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
                text = "\n\n".join(pages)
            results.append(
                {
                    "parsed_text": text,
                    "page_count": len(pages),
                    "char_count": len(text),
                    "word_count": len(text.split()),
                }
            )
        except Exception:
            results.append({"parsed_text": None, "page_count": 0, "char_count": 0, "word_count": 0})
    return pd.DataFrame(results)


# COMMAND ----------
# MAGIC %md ### Step 1 — New Bronze rows

# COMMAND ----------
df_bronze = spark.table(bronze_table)
df_silver_hashes = spark.table(silver_table).select("content_hash")
df_quarantine_hashes = spark.table(quarantine_table).select("content_hash")
df_already_processed = df_silver_hashes.union(df_quarantine_hashes).distinct()

df_new = df_bronze.join(df_already_processed, on="content_hash", how="left_anti")

# Within-batch dedup: Bronze may contain multiple runs of the same file (same content_hash).
# Keep only the latest ingest per content_hash so both gates and the MERGE see one row each.
# Without this, a Bronze table with run-001 + run-002 produces 2× rows through every step.
_w = Window.partitionBy("content_hash").orderBy(F.col("ingest_timestamp").desc())
df_new = df_new.withColumn("_rn", F.row_number().over(_w)).filter(F.col("_rn") == 1).drop("_rn")

new_count = df_new.count()
print(f"New Bronze rows to process: {new_count}")
if new_count == 0:
    dbutils.notebook.exit("No new rows — Silver is already up to date.")

# COMMAND ----------
# MAGIC %md ### Step 2 — Structural gate

# COMMAND ----------
df_checked = df_new.withColumn(
    "structural_violations",
    validate_contract(
        F.col("source_url"),
        F.col("retrieved_at"),
        F.col("content_hash"),
        F.col("guideline_version"),
        F.col("pipeline_run_id"),
        F.col("ingest_timestamp"),
        F.col("length"),
        F.col("guideline_id"),
    ),
).withColumn("passes_structural", F.size("structural_violations") == 0)

df_structural_invalid = (
    df_checked.filter(~F.col("passes_structural"))
    .withColumn("quarantine_reason", F.array_join("structural_violations", " | "))
    .withColumn("quarantine_timestamp", F.current_timestamp())
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
        "quarantine_reason",
        "quarantine_timestamp",
    )
)

structural_invalid_count = df_structural_invalid.count()
if structural_invalid_count > 0:
    df_structural_invalid.write.format("delta").mode("append").saveAsTable(quarantine_table)
    print(f"Structural gate: quarantined {structural_invalid_count} row(s).")

df_structural_valid = df_checked.filter(F.col("passes_structural"))
structural_valid_count = df_structural_valid.count()
print(f"Structural gate: {structural_valid_count} row(s) passed.")

# COMMAND ----------
# MAGIC %md ### Step 3 — Manifest join
# MAGIC
# MAGIC Join key: `filename` extracted from `source_url` (last path segment).
# MAGIC Using filename rather than `guideline_id` because `guideline_id` is not unique
# MAGIC per document — NG28 has 4 documents sharing one ID, which would fan out 4×4=16 rows
# MAGIC on a `guideline_id` join. Filename is a 1:1 key.

# COMMAND ----------
df_manifest = spark.table(manifest_table).select(
    F.col("filename"),
    F.col("guideline_id").alias("manifest_guideline_id"),
    F.col("title"),
    F.col("expected_clinical_area"),
    F.col("nice_url"),
    F.to_date("publication_date").alias("publication_date"),
)

df_with_filename = df_structural_valid.withColumn(
    "_filename",
    F.element_at(F.split(F.col("source_url"), "/"), -1),
)

df_joined = df_with_filename.join(
    df_manifest,
    df_with_filename["_filename"] == df_manifest["filename"],
    how="left",
).drop("filename", "manifest_guideline_id", "_filename")

# COMMAND ----------
# MAGIC %md ### Step 4 — Semantic scope gate
# MAGIC
# MAGIC Mirrors `src/clinical_platform/scope.py` and `src/clinical_platform/config.py`.
# MAGIC `ACCEPTED_CLINICAL_AREAS` is the single declared platform scope — git history is the audit trail.
# MAGIC
# MAGIC Two distinct reason codes:
# MAGIC - `MISSING_MANIFEST_ENTRY`  — document not in governance catalog (uncatalogued)
# MAGIC - `INVALID_CLINICAL_AREA`   — catalogued but out of platform scope (e.g. NG17 type_1_diabetes)

# COMMAND ----------
ACCEPTED_CLINICAL_AREAS = {"type_2_diabetes"}  # mirrors config.py

df_scope_checked = df_joined.withColumn(
    "scope_violations",
    F.when(F.col("expected_clinical_area").isNull(), F.array(F.lit("MISSING_MANIFEST_ENTRY")))
    .when(
        ~F.col("expected_clinical_area").isin(list(ACCEPTED_CLINICAL_AREAS)),
        F.array(F.lit("INVALID_CLINICAL_AREA")),
    )
    .otherwise(F.array().cast(T.ArrayType(T.StringType()))),
).withColumn("passes_scope", F.size("scope_violations") == 0)

df_scope_invalid = (
    df_scope_checked.filter(~F.col("passes_scope"))
    .withColumn("quarantine_reason", F.array_join("scope_violations", " | "))
    .withColumn("quarantine_timestamp", F.current_timestamp())
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
        "quarantine_reason",
        "quarantine_timestamp",
    )
)

scope_invalid_count = df_scope_invalid.count()
if scope_invalid_count > 0:
    df_scope_invalid.write.format("delta").mode("append").saveAsTable(quarantine_table)
    print(f"Semantic gate: quarantined {scope_invalid_count} row(s).")

df_scope_valid = df_scope_checked.filter(F.col("passes_scope"))
scope_valid_count = df_scope_valid.count()
print(f"Semantic gate: {scope_valid_count} row(s) passed.")

if scope_valid_count == 0:
    print("All rows blocked — Silver NOT updated.")
    dbutils.notebook.exit("Both gates blocked all rows. Check quarantine table.")

# COMMAND ----------
# MAGIC %md ### Step 5 — Parse and MERGE into Silver

# COMMAND ----------
df_parsed_raw = df_scope_valid.withColumn("_pdf", parse_pdf(F.col("content")))
df_parsed = (
    df_parsed_raw.withColumn("parsed_text", F.col("_pdf.parsed_text"))
    .withColumn("page_count", F.col("_pdf.page_count"))
    .withColumn("char_count", F.col("_pdf.char_count"))
    .withColumn("word_count", F.col("_pdf.word_count"))
    .withColumn("clinical_area", F.col("expected_clinical_area"))
    .drop(
        "_pdf",
        "content",
        "structural_violations",
        "passes_structural",
        "scope_violations",
        "passes_scope",
        "expected_clinical_area",
    )
)

df_silver_ready = df_parsed.withColumn("silver_processed_at", F.current_timestamp()).select(
    "source_url",
    "retrieved_at",
    "content_hash",
    "guideline_version",
    "pipeline_run_id",
    "ingest_timestamp",
    "guideline_id",
    "title",
    "clinical_area",
    "nice_url",
    "publication_date",
    "parsed_text",
    "page_count",
    "char_count",
    "word_count",
    "silver_processed_at",
)

df_silver_ready.createOrReplaceTempView("_silver_incoming")

spark.sql(f"""
    MERGE INTO {silver_table} AS target
    USING _silver_incoming        AS source
    ON target.content_hash = source.content_hash
    WHEN NOT MATCHED THEN INSERT *
""")

# COMMAND ----------
# MAGIC %md ### Step 6 — Proof summary

# COMMAND ----------
total_quarantined = structural_invalid_count + scope_invalid_count
print(f"pipeline_run_id  : {pipeline_run_id}")
print(f"new rows in      : {new_count}")
print(f"structural blocks: {structural_invalid_count}")
print(f"semantic blocks  : {scope_invalid_count}")
print(f"loaded to Silver : {scope_valid_count}")

print("\n── Silver ───────────────────────────────────────────────────────────")
display(spark.sql(f"""
        SELECT guideline_id, title, clinical_area, page_count, word_count, silver_processed_at
        FROM {silver_table}
        ORDER BY silver_processed_at DESC
    """))

if total_quarantined > 0:
    print("\n── Quarantine (all gates) ───────────────────────────────────────────")
    display(spark.sql(f"""
            SELECT guideline_id, source_url, quarantine_reason, quarantine_timestamp
            FROM {quarantine_table}
            ORDER BY quarantine_timestamp DESC
        """))
