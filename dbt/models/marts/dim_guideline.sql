-- Current-state dimension: one row per NICE guideline (guideline_id grain).
--
-- Collapse rule — three-tier priority:
--   1. Primary document first: title WITHOUT ' — ' (supplements carry a subtitle after an em-dash)
--   2. Latest guideline_version within the primary group (most recently updated version in force)
--   3. title ASC as final tiebreaker (stable sort)
--
-- Rationale for primary-document preference:
--   NICE guidelines can have multiple associated documents per guideline_id — the main
--   guidance document plus supplementary summaries and decision aids. The canonical
--   entry for a dimension should be the root management document, not the most recent
--   supplement. For NG28, this selects "Type 2 diabetes in adults: management" rather
--   than "...management — GLP-1 and tirzepatide summary" (the most recently dated but
--   supplementary). Single-document guidelines (QS209, TA924, PH38) are unaffected.
--
-- Why latest (DESC) within the primary group:
--   This dimension feeds the SCD2 snapshot (dim_guideline_snapshot). The snapshot tracks
--   "what version was current when." If we used earliest (ASC), a new primary update would
--   never change the dim, making the snapshot inert after initial load. Latest = current
--   authoritative state; snapshot = system of record for history.
--
-- P3 used pure ASC (earliest = original publication) for canonical root selection.
-- P4 adds the primary-doc filter so that latest-within-primary gives both the right
-- document AND current-state semantics for the snapshot.

WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY guideline_id
            ORDER BY
                CASE WHEN title NOT LIKE '% — %' THEN 0 ELSE 1 END ASC,
                guideline_version DESC,
                title ASC
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
