-- Fact table at document grain.
-- One row per parsed guideline document (7 rows for the type_2_diabetes corpus).
-- NG28 contributes 4 rows (one per distinct document), all referencing the same
-- guideline_id in dim_guideline. All other guidelines contribute 1 row each.

SELECT
    content_hash,
    guideline_id,
    guideline_version,
    source_url,
    page_count,
    char_count,
    word_count,
    pipeline_run_id,
    silver_processed_at
FROM {{ ref('stg_guidelines_parsed') }}
