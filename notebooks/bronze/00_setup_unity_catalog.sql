-- Run once as workspace admin after Terraform apply
-- Prerequisites: Unity Catalog metastore attached to this Databricks workspace
-- (If reusing the metastore from Project 1, skip the first two steps)

-- 1. Create a storage credential pointing to the ADLS managed identity
--    (replace <storage_account_name> with terraform output: storage_account_name)
-- CREATE STORAGE CREDENTIAL clinical_platform_sc
--   WITH AZURE_MANAGED_IDENTITY (
--     CREDENTIAL 'miCredential'
--   );

-- 2. Create external location for the platform storage
CREATE EXTERNAL LOCATION IF NOT EXISTS clinical_platform_adls
  URL 'abfss://bronze-files@<storage_account_name>.dfs.core.windows.net/'
  WITH (STORAGE CREDENTIAL clinical_platform_sc)
  COMMENT 'Bronze file storage for Clinical Knowledge Platform';

-- 3. Catalog and schemas
CREATE CATALOG IF NOT EXISTS clinical_platform
  COMMENT 'Clinical Knowledge Platform — governed lakehouse';

CREATE SCHEMA IF NOT EXISTS clinical_platform.bronze
  COMMENT 'Raw ingested documents — append-only, no business transformation';

CREATE SCHEMA IF NOT EXISTS clinical_platform.silver
  COMMENT 'Parsed and validated guideline text with metadata';

CREATE SCHEMA IF NOT EXISTS clinical_platform.gold
  COMMENT 'dbt-modelled star schema and RAG-ready chunks';

-- 4. Verify
SHOW SCHEMAS IN clinical_platform;
