WITH source AS (
    SELECT * FROM {{ source('silver', 'guidelines_parsed') }}
)

SELECT
    -- Natural key
    content_hash,
    guideline_id,
    -- Guideline metadata
    title,
    clinical_area,
    nice_url,
    publication_date,
    guideline_version,
    -- Provenance
    source_url,
    retrieved_at,
    pipeline_run_id,
    ingest_timestamp,
    -- Parsed content metrics
    page_count,
    char_count,
    word_count,
    -- Audit
    silver_processed_at
FROM source
