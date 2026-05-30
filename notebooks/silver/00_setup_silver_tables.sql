-- Silver-layer table DDL
-- Run once per environment after 00_setup_unity_catalog.sql
-- Schemas (bronze, silver, gold) are already created in the catalog setup notebook.

USE CATALOG clinical_platform;

-- ── Silver: validated, parsed, deduplicated rows ──────────────────────────────
CREATE TABLE IF NOT EXISTS silver.guidelines_parsed (
    -- Provenance inherited from Bronze (all 6 required columns)
    source_url          STRING    NOT NULL,
    retrieved_at        TIMESTAMP,
    content_hash        STRING    NOT NULL,
    guideline_version   STRING,
    pipeline_run_id     STRING    NOT NULL,
    ingest_timestamp    TIMESTAMP NOT NULL,
    guideline_id        STRING,
    -- Manifest metadata joined at Silver
    title               STRING,
    clinical_area       STRING,
    nice_url            STRING,
    publication_date    DATE,
    -- Parsed content
    parsed_text         STRING,
    page_count          INT,
    char_count          INT,
    word_count          INT,
    -- Silver bookkeeping
    silver_processed_at TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Parsed, deduplicated guideline text — one row per unique content_hash'
TBLPROPERTIES (
    'delta.enableChangeDataFeed' = 'true'
);

-- ── Quarantine: rows that failed the schema contract ─────────────────────────
CREATE TABLE IF NOT EXISTS silver.guidelines_quarantine (
    -- All Bronze columns preserved for forensics
    source_url          STRING,
    retrieved_at        TIMESTAMP,
    content_hash        STRING,
    guideline_version   STRING,
    pipeline_run_id     STRING,
    ingest_timestamp    TIMESTAMP,
    guideline_id        STRING,
    content             BINARY,
    length              LONG,
    -- Quarantine metadata
    quarantine_reason       STRING    NOT NULL,
    quarantine_timestamp    TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Bronze rows that failed the data contract — preserved with reason codes for forensics';

-- Verify
SHOW TABLES IN silver;
