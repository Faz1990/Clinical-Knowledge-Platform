{% snapshot dim_guideline_snapshot %}

{{
    config(
        target_schema='gold',
        unique_key='guideline_id',
        strategy='check',
        check_cols=['current_version', 'title', 'clinical_area', 'nice_url'],
    )
}}

-- SCD Type-2 snapshot of dim_guideline.
-- Records a new history row whenever any of the tracked columns change.
-- dbt adds: dbt_scd_id, dbt_valid_from, dbt_valid_to (null = current), dbt_updated_at.
--
-- Proof query to run after a version transition:
--   SELECT guideline_id, current_version, title, dbt_valid_from, dbt_valid_to
--   FROM clinical_platform.gold.dim_guideline_snapshot
--   WHERE guideline_id = 'NG28'
--   ORDER BY dbt_valid_from
-- Expect 2 rows: old version (dbt_valid_to not null) + new version (dbt_valid_to null).

SELECT * FROM {{ ref('dim_guideline') }}

{% endsnapshot %}
