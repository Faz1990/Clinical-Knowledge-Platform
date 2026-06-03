"""
Clinical Platform Pipeline — P5 Orchestration

Medallion pipeline: Bronze (Auto Loader) → Silver (contract gate) → Gold (dbt).
P7/P9 tasks are EmptyOperator stubs showing the full pipeline shape.

Auth — two adapters, one short-lived AD token:
  - dbt task:               get_databricks_token() → DBT_DATABRICKS_TOKEN env var
  - Databricks operators:   databricks_default Airflow connection (password = same token)
  - Sensor:                 DefaultAzureCredential (az login; different resource, separate)
Both dbt and the connection draw from DATABRICKS_TOKEN set at Airflow startup.

Prod-TODO (P6): swap personal AD token for SP/OAuth M2M client-credentials.
  Changes needed: (1) get_databricks_token() body — replace az-minted token with
  msal client_credentials call; (2) rebuild AIRFLOW_CONN_DATABRICKS_DEFAULT using
  the SP client_id/secret stored in an Airflow connection or Key Vault.
  Zero DAG topology changes. Introduced in P6 alongside CI/CD deploy secrets.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator


# ---------------------------------------------------------------------------
# Auth — adapter 1 of 2 (dbt).
# Prod-TODO (P6): replace body with msal client_credentials for SP/OAuth M2M.
# Databricks operators use the databricks_default connection (adapter 2), not this.
# ---------------------------------------------------------------------------
def get_databricks_token() -> str:
    token = os.environ.get("DATABRICKS_TOKEN")
    if not token:
        raise RuntimeError(
            "DATABRICKS_TOKEN not set.\n"
            "Mint: export DATABRICKS_TOKEN=$(az account get-access-token "
            "--resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv)\n"
            "then set AIRFLOW_CONN_DATABRICKS_DEFAULT per .env.example and restart."
        )
    return token


# ---------------------------------------------------------------------------
# Workspace config
# Verify notebook paths match your Databricks workspace before triggering.
# If using Repos:         /Repos/faisal1990@hotmail.co.uk/Clinical-Knowledge-Platform/notebooks/...
# If using direct upload: /Users/faisal1990@hotmail.co.uk/notebooks/...
# Verify EXISTING_CLUSTER_ID is active; note: job cluster is the prod pattern.
# ---------------------------------------------------------------------------
DATABRICKS_HOST     = "adb-7405614006245057.17.azuredatabricks.net"
EXISTING_CLUSTER_ID = "0529-152429-s8benrb4"

BRONZE_NOTEBOOK = "/Workspace/clinical-knowledge-platform/bronze/01_auto_loader_bronze"

SILVER_NOTEBOOK = "/Workspace/clinical-knowledge-platform/silver/01_bronze_to_silver"

SOURCE_PATH     = "abfss://bronze-files@stclinpldev.dfs.core.windows.net/"
SCHEMA_LOCATION = "abfss://autoloader-schema@stclinpldev.dfs.core.windows.net/"

DBT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "dbt")
)
DBT_BIN = "/home/faz/dbt-venv/bin/dbt"  # dbt isolated in its own venv in WSL


# ---------------------------------------------------------------------------
# Sensor: checks ADLS landing for files before the pipeline runs.
# Auth: DefaultAzureCredential (az login in WSL — legitimately separate from
# the Databricks token; this resource is Azure Storage, not Databricks).
# BlobServiceClient needs .blob.core.windows.net; SOURCE_PATH/SCHEMA_LOCATION
# stay on .dfs (abfss:// paths consumed by Spark — correct for that SDK).
# Requires Storage Blob Data Reader on stclinpldev (data-plane RBAC — control-
# plane Owner/Contributor is insufficient; 403 with correct code = missing grant).
# ---------------------------------------------------------------------------
def _files_in_landing() -> bool:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    cred   = DefaultAzureCredential()
    client = BlobServiceClient(
        "https://stclinpldev.blob.core.windows.net", credential=cred
    )
    blobs = list(client.get_container_client("bronze-files").list_blobs())
    return len(blobs) > 0


# ---------------------------------------------------------------------------
# Retry-demo task: fails on attempt 1 when SIMULATE_FAILURE=true.
# Demonstrates Airflow retry mechanics. The headline failure story is the
# idempotency re-run: trigger → complete → re-trigger → Silver still = 7 rows.
# ---------------------------------------------------------------------------
def _preflight_check(**context) -> None:
    if os.environ.get("SIMULATE_FAILURE", "false").lower() != "true":
        return

    ti = context["task_instance"]
    if ti.try_number <= 1:
        raise RuntimeError(
            "Simulated transient failure on attempt 1 "
            "(SIMULATE_FAILURE=true). Airflow will retry."
        )


# ---------------------------------------------------------------------------
# dbt task: no capture_output — dbt streams directly to the Airflow task log.
# Both pass ("27/27 PASS") and fail ("accepted_values failed") output is visible.
# dbt test failure raises CalledProcessError → task fails → pipeline stops.
# This IS the contract gate showing up in orchestration.
# ---------------------------------------------------------------------------
def _run_dbt_gold(**_) -> None:
    profiles_dir = os.path.expanduser("~/.dbt")
    env = {**os.environ, "DBT_DATABRICKS_TOKEN": get_databricks_token()}

    for step in ([DBT_BIN, "run"], [DBT_BIN, "test"]):
        subprocess.run(
            step + ["--project-dir", DBT_DIR, "--profiles-dir", profiles_dir],
            env=env,
            check=True,
        )


# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------
with DAG(
    dag_id="clinical_platform_pipeline",
    schedule=None,  # manual trigger only; set '@daily' once P6 SP auth lands
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={
        "owner": "faisal",
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    },
    tags=["clinical", "medallion"],
) as dag:

    check_landing = PythonSensor(
        task_id="check_landing_files",
        python_callable=_files_in_landing,
        mode="reschedule",  # frees worker slot between pokes; avoids slot starvation
        poke_interval=30,
        timeout=300,
    )

    preflight = PythonOperator(
        task_id="preflight_check",
        python_callable=_preflight_check,
        retries=2,
        retry_delay=timedelta(seconds=30),
    )

    run_bronze = DatabricksSubmitRunOperator(
        task_id="run_bronze_autoloader",
        databricks_conn_id="databricks_default",
        json={
            "run_name": "bronze_autoloader_{{ run_id }}",
            "existing_cluster_id": EXISTING_CLUSTER_ID,
            "notebook_task": {
                "notebook_path": BRONZE_NOTEBOOK,
                "base_parameters": {
                    "pipeline_run_id": "{{ run_id }}",
                    "source_path": SOURCE_PATH,
                    "schema_location": SCHEMA_LOCATION,
                    "bronze_table": "clinical_platform.bronze.guidelines_raw",
                },
            },
        },
    )

    run_silver = DatabricksSubmitRunOperator(
        task_id="run_silver_contract",
        databricks_conn_id="databricks_default",
        json={
            "run_name": "silver_contract_{{ run_id }}",
            "existing_cluster_id": EXISTING_CLUSTER_ID,
            "notebook_task": {
                "notebook_path": SILVER_NOTEBOOK,
                "base_parameters": {
                    "pipeline_run_id": "{{ run_id }}",
                    "bronze_table": "clinical_platform.bronze.guidelines_raw",
                    "silver_table": "clinical_platform.silver.guidelines_parsed",
                    "quarantine_table": "clinical_platform.silver.guidelines_quarantine",
                    "manifest_table": "clinical_platform.bronze.guidelines_manifest",
                },
            },
        },
    )

    run_dbt_gold = PythonOperator(
        task_id="run_dbt_gold",
        python_callable=_run_dbt_gold,
        retries=1,              # absorbs serverless cold-start timeout on first query
        retry_delay=timedelta(minutes=2),
    )

    # P7/P9 stubs — full pipeline shape declared; filled in later phases
    embed_chunks    = EmptyOperator(task_id="embed_chunks")
    run_ragas_eval  = EmptyOperator(task_id="run_ragas_eval")
    publish_metrics = EmptyOperator(task_id="publish_metrics")

    (
        check_landing
        >> preflight
        >> run_bronze
        >> run_silver
        >> run_dbt_gold
        >> embed_chunks
        >> run_ragas_eval
        >> publish_metrics
    )
