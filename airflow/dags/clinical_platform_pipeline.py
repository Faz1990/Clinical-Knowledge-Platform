"""
Clinical Platform Pipeline — Medallion orchestration with SP/OAuth M2M auth.

Medallion pipeline: Bronze (Auto Loader) → Silver (contract gate) → Gold (dbt).
P7/P9 tasks are EmptyOperator stubs showing the full pipeline shape.

Auth — two adapters, both using the clinical-platform-cicd SP:
  - dbt task:               get_databricks_token() → MSAL client-credentials flow →
                            short-lived token injected as DBT_DATABRICKS_TOKEN env var
  - Databricks operators:   AIRFLOW_CONN_DATABRICKS_DEFAULT with SP extra fields;
                            provider refreshes tokens automatically — no startup token
  - Sensor:                 DefaultAzureCredential (Azure Storage resource; orthogonal
                            to Databricks auth — legitimately separate)

Connection extra fields (apache-airflow-providers-databricks==6.7.0, verified):
  azure_tenant_id, azure_client_id, azure_client_secret.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta

import msal
from airflow.exceptions import AirflowException
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator
from airflow.sensors.python import PythonSensor

from airflow import DAG


# ---------------------------------------------------------------------------
# Auth — adapter 1 of 2 (dbt).
# SP/OAuth M2M via MSAL client-credentials. Databricks operators use the
# databricks_default connection (adapter 2) with its own SP token refresh.
# ---------------------------------------------------------------------------
def get_databricks_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_credential=os.environ["AZURE_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
    )
    result = app.acquire_token_for_client(scopes=["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"])
    if "access_token" not in result:
        raise RuntimeError(
            f"MSAL token acquisition failed: {result.get('error_description', result)}"
        )
    return result["access_token"]


# ---------------------------------------------------------------------------
# Workspace config
# Verify notebook paths match your Databricks workspace before triggering.
# If using Repos:         /Repos/faisal1990@hotmail.co.uk/Clinical-Knowledge-Platform/notebooks/...
# If using direct upload: /Users/faisal1990@hotmail.co.uk/notebooks/...
# Verify EXISTING_CLUSTER_ID is active; note: job cluster is the prod pattern.
# ---------------------------------------------------------------------------
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "")
EXISTING_CLUSTER_ID = os.environ.get("EXISTING_CLUSTER_ID", "")

BRONZE_NOTEBOOK = "/Workspace/clinical-knowledge-platform/bronze/01_auto_loader_bronze"

SILVER_NOTEBOOK = "/Workspace/clinical-knowledge-platform/silver/01_bronze_to_silver"

_STORAGE_ACCOUNT = os.environ.get("STORAGE_ACCOUNT", "")
SOURCE_PATH = f"abfss://bronze-files@{_STORAGE_ACCOUNT}.dfs.core.windows.net/"
SCHEMA_LOCATION = f"abfss://autoloader-schema@{_STORAGE_ACCOUNT}.dfs.core.windows.net/"

DBT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dbt"))
DBT_BIN = "/home/faz/dbt-venv/bin/dbt"  # dbt isolated in its own venv in WSL

# clinical_platform package lives in src/ relative to repo root
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

FRESHNESS_TTL_DAYS: int = int(os.environ.get("FRESHNESS_TTL_DAYS", "7"))


# ---------------------------------------------------------------------------
# Sensor: checks ADLS landing for files before the pipeline runs.
# Auth: DefaultAzureCredential (az login in WSL — legitimately separate from
# the Databricks token; this resource is Azure Storage, not Databricks).
# BlobServiceClient needs .blob.core.windows.net; SOURCE_PATH/SCHEMA_LOCATION
# stay on .dfs (abfss:// paths consumed by Spark — correct for that SDK).
# Requires Storage Blob Data Reader on $STORAGE_ACCOUNT (data-plane RBAC — control-
# plane Owner/Contributor is insufficient; 403 with correct code = missing grant).
# ---------------------------------------------------------------------------
def _files_in_landing() -> bool:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    cred = DefaultAzureCredential()
    client = BlobServiceClient(f"https://{_STORAGE_ACCOUNT}.blob.core.windows.net", credential=cred)
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
# Both pass ("25/25 PASS") and fail ("accepted_values failed") output is visible.
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
# P9: RAGAS eval + publish metrics
# Both functions do lazy imports so Airflow doesn't fail to load the DAG if
# eval/telemetry deps aren't installed in the scheduler environment.
# ---------------------------------------------------------------------------
def _run_ragas_eval(**_) -> None:
    import sys
    import uuid
    from datetime import datetime, timezone

    if _SRC_DIR not in sys.path:
        sys.path.insert(0, _SRC_DIR)

    from clinical_platform.eval import run as eval_run
    from clinical_platform import telemetry

    # Timestamp + 8 random hex chars guarantees uniqueness across runs and retries.
    # DELETE WHERE eval_run_id = X clears only this run's failed partial rows,
    # never rows from a different run.
    eval_run_id = (
        f"eval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        f"_{uuid.uuid4().hex[:8]}"
    )

    index_built_ts = telemetry.get_index_built_ts()
    scores, per_q_df = eval_run()
    telemetry.write_eval_telemetry(eval_run_id, per_q_df, index_built_ts)
    print(
        f"Eval complete: run_id={eval_run_id} "
        f"precision={scores['context_precision']:.3f} "
        f"recall={scores['context_recall']:.3f}"
    )


def _publish_metrics(**_) -> None:
    import sys
    from datetime import datetime, timezone

    if _SRC_DIR not in sys.path:
        sys.path.insert(0, _SRC_DIR)

    from clinical_platform import telemetry

    index_built_ts = telemetry.get_index_built_ts()
    # total_seconds() / 86400 gives exact fractional days; .days floors and fires up to 24h late
    age_days = (datetime.now(timezone.utc) - index_built_ts).total_seconds() / 86400

    if age_days > FRESHNESS_TTL_DAYS:
        # Raise so the task goes red in the Airflow UI — a print-only alert is
        # a log line; a failed task is the automated gate P9 exists to demonstrate.
        raise AirflowException(
            f"FRESHNESS ALERT: index is {age_days:.1f}d old (TTL={FRESHNESS_TTL_DAYS}d). "
            f"Run embed_chunks to re-index."
        )

    print(f"Freshness OK: index is {age_days:.1f}d old (TTL={FRESHNESS_TTL_DAYS}d).")


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
        retries=1,  # absorbs serverless cold-start timeout on first query
        retry_delay=timedelta(minutes=2),
    )

    embed_chunks = EmptyOperator(task_id="embed_chunks")

    run_ragas_eval = PythonOperator(
        task_id="run_ragas_eval",
        python_callable=_run_ragas_eval,
    )

    publish_metrics = PythonOperator(
        task_id="publish_metrics",
        python_callable=_publish_metrics,
    )

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
