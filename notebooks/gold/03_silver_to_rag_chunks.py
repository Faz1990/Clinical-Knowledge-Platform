# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC ## Gold: Silver → RAG Chunks
# MAGIC
# MAGIC Reads `silver.guidelines_parsed` (full parsed PDF text per document), splits each
# MAGIC document into fixed-size word chunks with overlap, and writes to
# MAGIC `clinical_platform.gold.rag_chunks`.
# MAGIC
# MAGIC Each chunk row carries `guideline_id` + `guideline_version` so that any answer
# MAGIC citing a chunk can be traced back to a specific row in `dim_guideline`.
# MAGIC
# MAGIC Chunking strategy: 500 words per chunk, 50-word overlap.
# MAGIC With the type-2-diabetes corpus (~7 documents), this produces ~200–600 chunks total.

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql import types as T
import pandas as pd

dbutils.widgets.text("silver_table", "clinical_platform.silver.guidelines_parsed", "Silver table")
dbutils.widgets.text("gold_table", "clinical_platform.gold.rag_chunks", "Gold chunks table")
dbutils.widgets.text("chunk_size", "500", "Words per chunk")
dbutils.widgets.text("overlap", "50", "Overlap words")

silver_table = dbutils.widgets.get("silver_table")
gold_table = dbutils.widgets.get("gold_table")
chunk_size = int(dbutils.widgets.get("chunk_size"))
overlap = int(dbutils.widgets.get("overlap"))

# COMMAND ----------
# MAGIC %md ### Step 1 — Define chunking UDF

# COMMAND ----------
_chunk_schema = T.ArrayType(T.StructType([
    T.StructField("chunk_index", T.IntegerType()),
    T.StructField("total_chunks", T.IntegerType()),
    T.StructField("chunk_text", T.StringType()),
    T.StructField("word_count", T.IntegerType()),
]))


@F.pandas_udf(_chunk_schema)
def chunk_text(
    text_series: pd.Series,
    chunk_size_series: pd.Series,
    overlap_series: pd.Series,
) -> pd.Series:
    results = []
    for text, cs, ov in zip(text_series, chunk_size_series, overlap_series):
        if not text:
            results.append([])
            continue
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = min(start + cs, len(words))
            chunk_words = words[start:end]
            chunks.append(chunk_words)
            if end == len(words):
                break
            start += cs - ov
        total = len(chunks)
        results.append([
            {
                "chunk_index": i,
                "total_chunks": total,
                "chunk_text": " ".join(c),
                "word_count": len(c),
            }
            for i, c in enumerate(chunks)
        ])
    return pd.Series(results)


# COMMAND ----------
# MAGIC %md ### Step 2 — Load Silver and generate chunks

# COMMAND ----------
df_silver = spark.table(silver_table).select(
    "content_hash",
    "guideline_id",
    "guideline_version",
    "parsed_text",
)

doc_count = df_silver.count()
print(f"Documents in Silver: {doc_count}")

df_chunked = df_silver.withColumn(
    "_chunks",
    chunk_text(
        F.col("parsed_text"),
        F.lit(chunk_size),
        F.lit(overlap),
    ),
)

df_exploded = (
    df_chunked.select(
        "content_hash",
        "guideline_id",
        "guideline_version",
        F.explode("_chunks").alias("_chunk"),
    )
    .select(
        F.concat_ws(
            "_",
            F.col("content_hash"),
            F.col("_chunk.chunk_index").cast("string"),
        ).alias("chunk_id"),
        "guideline_id",
        "guideline_version",
        "content_hash",
        F.col("_chunk.chunk_index").alias("chunk_index"),
        F.col("_chunk.total_chunks").alias("total_chunks"),
        F.col("_chunk.chunk_text").alias("chunk_text"),
        F.col("_chunk.word_count").alias("word_count"),
        F.current_timestamp().alias("chunked_at"),
    )
)

chunk_count = df_exploded.count()
print(f"Total chunks produced: {chunk_count} ({chunk_count / doc_count:.0f} avg per doc)")

# COMMAND ----------
# MAGIC %md ### Step 3 — Write to Gold (overwrite for idempotency)

# COMMAND ----------
(
    df_exploded.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(gold_table)
)

print(f"Written {chunk_count} chunks to {gold_table}")

# COMMAND ----------
# MAGIC %md ### Step 4 — Proof summary

# COMMAND ----------
display(spark.sql(f"""
    SELECT
        guideline_id,
        guideline_version,
        COUNT(*) AS chunks,
        MIN(word_count) AS min_words,
        ROUND(AVG(word_count), 0) AS avg_words,
        MAX(word_count) AS max_words
    FROM {gold_table}
    GROUP BY guideline_id, guideline_version
    ORDER BY guideline_id, guideline_version
"""))
