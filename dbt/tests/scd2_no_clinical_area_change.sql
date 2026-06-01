-- Semantic-validation catch: flags any guideline whose clinical_area changed
-- between consecutive snapshot versions.
--
-- A guideline changing scope (e.g. NG28 from type_2_diabetes to type_1_diabetes)
-- is a governance event that should trigger human review, not an automatic update.
-- This test surfaces that signal before downstream Gold consumers are affected.
--
-- Returns rows (test FAILS) if any such change is detected.

SELECT
    current_ver.guideline_id,
    prev_ver.clinical_area   AS previous_clinical_area,
    current_ver.clinical_area AS current_clinical_area,
    current_ver.dbt_valid_from
FROM {{ ref('dim_guideline_snapshot') }} AS current_ver
JOIN {{ ref('dim_guideline_snapshot') }} AS prev_ver
    ON  current_ver.guideline_id   = prev_ver.guideline_id
    AND current_ver.dbt_valid_from > prev_ver.dbt_valid_from
    AND prev_ver.dbt_valid_to     IS NOT NULL
WHERE current_ver.clinical_area != prev_ver.clinical_area
