#!/usr/bin/env bash
# Start Airflow standalone with a freshly minted Databricks token.
#
# Mint LAST — immediately before triggering — so the ~1hr token window
# covers the full demo run. If the token expires mid-session, the ONLY fix
# is Ctrl-C and re-run this script. Re-exporting DATABRICKS_TOKEN in another
# shell does NOT reach the running standalone processes (they inherit env at
# launch and freeze it). Don't debug a silent 403 before checking token age.
#
# Prerequisites (one-time, in WSL):
#   1. pip install -r requirements-airflow.txt --constraint <constraints-url>
#   2. az login   (needs Storage Blob Data Reader on stclinpldev for the sensor)
#   3. Copy Windows dbt profiles: cp /mnt/c/Users/Faisal/.dbt/profiles.yml ~/.dbt/profiles.yml
#   4. Verify BRONZE_NOTEBOOK / SILVER_NOTEBOOK paths in the DAG file
#   5. Ensure cluster 0529-152429-s8benrb4 is running in Databricks

set -euo pipefail

echo "Minting Databricks token..."
TOKEN=$(az account get-access-token \
    --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d \
    --query accessToken -o tsv)

export DATABRICKS_TOKEN="$TOKEN"

# Pass token via env var, not argv — keeps it out of ps aux output
export AIRFLOW_CONN_DATABRICKS_DEFAULT=$(TOKEN="$TOKEN" python3 -c "
import json, os
print(json.dumps({
    'conn_type': 'databricks',
    'host': 'adb-7405614006245057.17.azuredatabricks.net',
    'password': os.environ['TOKEN'],
}))
")

export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"

echo "Token minted (${#TOKEN} chars). Starting Airflow standalone..."
echo "UI: http://localhost:8080  |  admin password in \$AIRFLOW_HOME/standalone_admin_password.txt"
echo ""
echo "Idempotency proof (run both inside the same token window):"
echo "  1. Trigger DAG → wait for green → query Silver: expect type_2_diabetes = 7"
echo "  2. Re-trigger   → wait for green → query Silver: still 7, not 14"
echo ""

airflow standalone
