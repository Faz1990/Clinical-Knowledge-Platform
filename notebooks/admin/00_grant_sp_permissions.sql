-- Databricks notebook source
-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## UC Grants: clinical-platform-cicd Service Principal
-- MAGIC
-- MAGIC **Run this notebook once, as a metastore admin, in Databricks SQL Editor.**
-- MAGIC Identity: `faisal1990@hotmail.co.uk`
-- MAGIC
-- MAGIC **What this does:** grants the CI/CD SP the minimum Unity Catalog privileges needed
-- MAGIC to execute the full DAG (ingest → bronze → silver → gold/dbt → embed stubs),
-- MAGIC including clean-deploy scenarios where tables do not yet exist.
-- MAGIC
-- MAGIC **SP details:**
-- MAGIC | Field | Value |
-- MAGIC |---|---|
-- MAGIC | Display name | `clinical-platform-cicd` |
-- MAGIC | Application (client) ID | `91171f7d-478d-4dfd-a6cb-33e0e2011b23` |
-- MAGIC | Workspace SP id (SCIM) | `144343832918962` |
-- MAGIC
-- MAGIC **After each block:** run the SHOW GRANTS verification cell to confirm the grant
-- MAGIC took effect before proceeding. The backtick-UUID format is the primary risk —
-- MAGIC if a GRANT fails, retry with the display name `clinical-platform-cicd`.
-- MAGIC
-- MAGIC **Manual steps not covered here (do in Databricks UI):**
-- MAGIC - SQL Warehouses → `38837e3baf7e2b92` → Permissions → add SP → CAN USE
-- MAGIC - Compute → Clusters → `0529-152429-s8benrb4` → Permissions → add SP → Can Attach To

-- COMMAND ----------
-- MAGIC %md ### 1 — Catalog access

-- COMMAND ----------
GRANT USE CATALOG ON CATALOG clinical_platform
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

-- COMMAND ----------
-- Verify
SHOW GRANTS `91171f7d-478d-4dfd-a6cb-33e0e2011b23` ON CATALOG clinical_platform;

-- COMMAND ----------
-- MAGIC %md ### 2 — Schema navigation (all three tiers)

-- COMMAND ----------
GRANT USE SCHEMA ON SCHEMA clinical_platform.bronze
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

GRANT USE SCHEMA ON SCHEMA clinical_platform.silver
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

GRANT USE SCHEMA ON SCHEMA clinical_platform.gold
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

-- COMMAND ----------
-- Verify
SHOW GRANTS `91171f7d-478d-4dfd-a6cb-33e0e2011b23` ON SCHEMA clinical_platform.bronze;
SHOW GRANTS `91171f7d-478d-4dfd-a6cb-33e0e2011b23` ON SCHEMA clinical_platform.silver;
SHOW GRANTS `91171f7d-478d-4dfd-a6cb-33e0e2011b23` ON SCHEMA clinical_platform.gold;

-- COMMAND ----------
-- MAGIC %md ### 3 — Bronze: read + write
-- MAGIC
-- MAGIC The ingestion notebook (Auto Loader) creates and writes `guidelines_raw`;
-- MAGIC the silver notebook reads it.
-- MAGIC CREATE TABLE is required for clean-deploy scenarios where the table does not yet exist.

-- COMMAND ----------
GRANT SELECT ON SCHEMA clinical_platform.bronze
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

GRANT CREATE TABLE ON SCHEMA clinical_platform.bronze
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

GRANT MODIFY ON SCHEMA clinical_platform.bronze
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

-- COMMAND ----------
-- Verify
SHOW GRANTS `91171f7d-478d-4dfd-a6cb-33e0e2011b23` ON SCHEMA clinical_platform.bronze;

-- COMMAND ----------
-- MAGIC %md ### 4 — Silver: read + write
-- MAGIC
-- MAGIC Silver notebook creates and writes parsed rows; dbt reads silver as its declared source.
-- MAGIC CREATE TABLE required for clean-deploy, same reasoning as bronze.

-- COMMAND ----------
GRANT SELECT ON SCHEMA clinical_platform.silver
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

GRANT CREATE TABLE ON SCHEMA clinical_platform.silver
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

GRANT MODIFY ON SCHEMA clinical_platform.silver
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

-- COMMAND ----------
-- Verify
SHOW GRANTS `91171f7d-478d-4dfd-a6cb-33e0e2011b23` ON SCHEMA clinical_platform.silver;

-- COMMAND ----------
-- MAGIC %md ### 5 — Gold: full dbt write access
-- MAGIC
-- MAGIC dbt materialises staging models, intermediate models, and marts in gold.
-- MAGIC SELECT to self-reference existing models in incremental merges,
-- MAGIC CREATE TABLE + CREATE VIEW for first materialisation, MODIFY for subsequent writes.

-- COMMAND ----------
GRANT SELECT ON SCHEMA clinical_platform.gold
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

GRANT CREATE TABLE ON SCHEMA clinical_platform.gold
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;


GRANT MODIFY ON SCHEMA clinical_platform.gold
  TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

-- COMMAND ----------
-- Verify
SHOW GRANTS `91171f7d-478d-4dfd-a6cb-33e0e2011b23` ON SCHEMA clinical_platform.gold;

-- COMMAND ----------
-- MAGIC %md
-- MAGIC ### Fallback — if backtick-UUID syntax fails
-- MAGIC
-- MAGIC If any GRANT above returns a parse error or "principal not found", retry using the
-- MAGIC SP display name instead of the UUID:
-- MAGIC
-- MAGIC ```sql
-- MAGIC GRANT USE CATALOG ON CATALOG clinical_platform
-- MAGIC   TO `clinical-platform-cicd`;
-- MAGIC -- (repeat pattern for each statement above)
-- MAGIC ```
-- MAGIC
-- MAGIC UUID form is preferred (survives SP renames) but display name is the documented
-- MAGIC fallback if the SQL editor rejects UUID principals.
