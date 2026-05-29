-- Databricks notebook source
-- COMMAND ----------
-- MAGIC %md
-- MAGIC ## UC Setup: Clinical Knowledge Platform
-- MAGIC
-- MAGIC **What this notebook does and doesn't do**
-- MAGIC
-- MAGIC | Step | How | Cells below |
-- MAGIC |---|---|---|
-- MAGIC | Create storage credential | **Databricks UI** (see Step 1) | — |
-- MAGIC | Create / fix external locations | **REST API with `force=true`** (see Step 2) | — |
-- MAGIC | Create catalog + schemas | SQL cells | Cells 3–7 |
-- MAGIC | Verify + smoke test | SQL cells | Cells 8–9 |
-- MAGIC
-- MAGIC `CREATE STORAGE CREDENTIAL` and `ALTER EXTERNAL LOCATION` hit a persistent parser
-- MAGIC issue on this workspace. The equivalent operations were completed via the UI and REST
-- MAGIC API respectively. The SQL cells below are the subset that actually ran.
-- MAGIC
-- MAGIC ---
-- MAGIC
-- MAGIC ### Step 1 — Create storage credential (Databricks UI, one-time)
-- MAGIC
-- MAGIC 1. Open workspace → **Catalog** → **External Data** → **Credentials** → **Create credential**
-- MAGIC 2. Name: `clinical_platform_sc`
-- MAGIC 3. Type: Azure Managed Identity
-- MAGIC 4. Access Connector ID:
-- MAGIC    `/subscriptions/6abf7041-719b-42fb-b395-86f5c1a02ef6/resourceGroups/rg-clinical-platform-dev/providers/Microsoft.Databricks/accessConnectors/dbac-clinical-platform-dev`
-- MAGIC 5. Save.
-- MAGIC
-- MAGIC **Prerequisite:** the Access Connector MSI must have `Storage Blob Data Contributor`
-- MAGIC on `stclinpldev` before this credential can reach the storage. Granted via:
-- MAGIC ```bash
-- MAGIC az role assignment create \
-- MAGIC   --role "Storage Blob Data Contributor" \
-- MAGIC   --assignee b93b7ee3-0e7c-4c5f-894d-0550b1ad6938 \
-- MAGIC   --scope /subscriptions/6abf7041-719b-42fb-b395-86f5c1a02ef6/resourceGroups/rg-clinical-platform-dev/providers/Microsoft.Storage/storageAccounts/stclinpldev
-- MAGIC ```
-- MAGIC
-- MAGIC ---
-- MAGIC
-- MAGIC ### Step 2 — Create / swap external locations (REST API, one-time)
-- MAGIC
-- MAGIC External locations were first created via the SQL cells that did work (using the
-- MAGIC workspace default credential `dbw_clinical_platform_dev`), then swapped to
-- MAGIC `clinical_platform_sc` via the REST API because the UI blocked the change
-- MAGIC (dependent managed file event queue) and `ALTER EXTERNAL LOCATION` SQL hit the
-- MAGIC same parser issue as the credential creation.
-- MAGIC
-- MAGIC To reproduce from scratch (or re-run if locations need re-pointing):
-- MAGIC ```bash
-- MAGIC TOKEN=$(az account get-access-token \
-- MAGIC   --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d \
-- MAGIC   --query accessToken -o tsv)
-- MAGIC HOST="https://adb-7405614006245057.17.azuredatabricks.net"
-- MAGIC
-- MAGIC # Create or update all three external locations
-- MAGIC for loc in clinical_platform_bronze_files \
-- MAGIC            clinical_platform_autoloader_schema \
-- MAGIC            clinical_platform_catalog_managed; do
-- MAGIC
-- MAGIC   # Create (no-op if already exists)
-- MAGIC   curl -s -X POST \
-- MAGIC     -H "Authorization: Bearer $TOKEN" \
-- MAGIC     -H "Content-Type: application/json" \
-- MAGIC     -d "{
-- MAGIC       \"name\": \"$loc\",
-- MAGIC       \"url\": \"<see mapping below>\",
-- MAGIC       \"credential_name\": \"clinical_platform_sc\"
-- MAGIC     }" "$HOST/api/2.1/unity-catalog/external-locations"
-- MAGIC
-- MAGIC   # Swap credential on existing location (force bypasses dependent-object block)
-- MAGIC   curl -s -X PATCH \
-- MAGIC     -H "Authorization: Bearer $TOKEN" \
-- MAGIC     -H "Content-Type: application/json" \
-- MAGIC     -d '{"credential_name":"clinical_platform_sc","force":true}' \
-- MAGIC     "$HOST/api/2.1/unity-catalog/external-locations/$loc"
-- MAGIC done
-- MAGIC ```
-- MAGIC
-- MAGIC URL mapping:
-- MAGIC | Name | URL |
-- MAGIC |---|---|
-- MAGIC | `clinical_platform_bronze_files` | `abfss://bronze-files@stclinpldev.dfs.core.windows.net/` |
-- MAGIC | `clinical_platform_autoloader_schema` | `abfss://autoloader-schema@stclinpldev.dfs.core.windows.net/` |
-- MAGIC | `clinical_platform_catalog_managed` | `abfss://catalog-managed@stclinpldev.dfs.core.windows.net/` |

-- COMMAND ----------
-- MAGIC %md ### Step 3 — Verify credential and external locations exist before continuing

-- COMMAND ----------
SHOW STORAGE CREDENTIALS;

-- COMMAND ----------
SHOW EXTERNAL LOCATIONS;

-- COMMAND ----------
-- MAGIC %md ### Step 4 — Catalog

-- COMMAND ----------
CREATE CATALOG IF NOT EXISTS clinical_platform
  MANAGED LOCATION 'abfss://catalog-managed@stclinpldev.dfs.core.windows.net/'
  COMMENT 'Clinical Knowledge Platform — governed lakehouse';

-- COMMAND ----------
-- MAGIC %md ### Step 5 — Schemas

-- COMMAND ----------
CREATE SCHEMA IF NOT EXISTS clinical_platform.bronze
  COMMENT 'Raw ingested documents — append-only, no business transformation';

-- COMMAND ----------
CREATE SCHEMA IF NOT EXISTS clinical_platform.silver
  COMMENT 'Parsed and validated guideline text with metadata';

-- COMMAND ----------
CREATE SCHEMA IF NOT EXISTS clinical_platform.gold
  COMMENT 'dbt-modelled star schema and RAG-ready chunks';

-- COMMAND ----------
-- MAGIC %md ### Step 6 — Verify

-- COMMAND ----------
SHOW SCHEMAS IN clinical_platform;

-- COMMAND ----------
-- Smoke test: confirm external location + credential can reach bronze-files
SELECT _metadata.file_path, _metadata.file_size
FROM read_files(
  'abfss://bronze-files@stclinpldev.dfs.core.windows.net/',
  format => 'binaryFile'
)
LIMIT 3;
