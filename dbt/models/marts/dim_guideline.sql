-- Type-1 dimension: one row per NICE guideline (guideline_id grain).
--
-- Collapse rule: ORDER BY guideline_version ASC, title ASC
-- The earliest version + alphabetically-first title selects the canonical root
-- document rather than a supplement. For NG28 (4 docs), this yields
-- "Type 2 diabetes in adults: management" (the main guideline, version 2026-02-18)
-- rather than any of the supplements that share the same guideline_id.
--
-- Type-2 SCD history (tracking version changes over time) is added in P4.
-- This is a deliberate scope boundary: P3 = conformed Type-1 dims, P4 = history.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY guideline_id
            ORDER BY guideline_version ASC, title ASC
        ) AS _rn
    FROM {{ ref('stg_guidelines_parsed') }}
)

SELECT
    guideline_id,
    title,
    clinical_area,
    nice_url,
    publication_date,
    guideline_version AS current_version
FROM ranked
WHERE _rn = 1
