# Project State — Clinical Knowledge Platform

**Last updated:** 2026-06-04
**Current phase:** P6 (CI/CD via GitHub Actions) — IN PROGRESS

---

## Current Objective

Close P6 by building three things:
1. **SP/OAuth M2M auth** — replace the P5 personal-token workaround with non-interactive SP auth using MSAL client-credentials flow. There are **two auth paths** in the DAG — both must be closed (see risks).
2. **Tests as a merge gate** — GitHub Actions CI blocks PRs when lint or unit tests fail.
3. **Deploy-as-code** — Databricks Asset Bundles make the workspace layout reproducible from git.

---

## Proven Facts (P1–P5 complete, committed, pushed)

| Fact | Verified by |
|---|---|
| Bronze Delta table `clinical_platform.bronze.guidelines_raw` with 6 provenance cols | Databricks query |
| Auto Loader idempotency: same hash on re-run does not duplicate rows | `evidence/bronze_idempotency_proof_run_comparison.png` |
| Silver contract gate quarantines bad rows with reason codes; Silver unchanged | `evidence/p2_contract_gate_proof.png` |
| `dbt test` passes **25/25** (confirmed from `dbt/target/run_results.json`, generated 2026-06-02) | `evidence/p5_dbt_tests_pass.png` |
| dbt lineage graph generated clean | `evidence/p3_dbt_lineage.png` |
| SCD2 `dim_guideline_snapshot` captures version history | `evidence/p4_scd2_transition.png` |
| Governance test fires on clinical-area drift (`scd2_no_clinical_area_change`) | `evidence/p4_governance_test_fires.png` |
| Airflow DAG end-to-end: Bronze → Silver → Gold → stubs | `evidence/p5_dag_run_success.png` |
| P5 idempotency: re-run full pipeline → Silver still 7 rows, not 14 | `evidence/p5_idempotency_silver_7.png` |
| SP `clinical-platform-cicd` created, secret rotated, registered in workspace | SCIM query: `totalResults: 1`, `active: true`, no duplicates |

---

## P6 Infrastructure Already Done

| Item | Value |
|---|---|
| SP appId (client ID) | `91171f7d-478d-4dfd-a6cb-33e0e2011b23` |
| SP tenant | `5095ccc0-a03b-426e-999a-9a34539529ee` |
| SP Databricks workspace id | `144343832918962` |
| Secret location | Key Vault `kv-clinpl-dev` → `databricks-cicd-sp-secret`; local `.env` (gitignored). **Never paste or screenshot.** |
| Databricks workspace | `adb-7405614006245057.17.azuredatabricks.net` |
| SQL warehouse http_path | `/sql/1.0/warehouses/38837e3baf7e2b92` |
| All-purpose cluster | `0529-152429-s8benrb4` |
| AAD resource GUID (Databricks OAuth scope base) | `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d` |
| Airflow version | 2.9.3 (WSL) |
| Databricks Airflow provider | `apache-airflow-providers-databricks` (unpinned — installs latest compatible with 2.9.3) |

---

## P6 Remaining Work — In Order

### Step 1: Unity Catalog grants (manual, run once as admin)

**Why this is first:** Azure RBAC (Contributor on resource group) = control-plane only. Unity Catalog is a separate permission system. The SP can call the Databricks REST API but cannot read any table until UC grants exist.

Run `notebooks/admin/00_grant_sp_permissions.sql` in Databricks SQL Editor as `faisal1990@hotmail.co.uk`.
Then set `CAN USE` on the SQL warehouse via the UI (SQL Warehouses → `38837e3baf7e2b92` → Permissions → add SP).

Verify:
```sql
SHOW GRANTS TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;
```
Expected: `USE CATALOG` (catalog), `USE SCHEMA` ×3 (bronze/silver/gold), `SELECT` ×3, `CREATE TABLE` ×3, `MODIFY` ×3.

### Step 2: MSAL swap — dbt path (`get_databricks_token()`)

File: `airflow/dags/clinical_platform_pipeline.py`
Replace the body of `get_databricks_token()`. Remove `DATABRICKS_TOKEN` env-var dependency.

```python
import msal

def get_databricks_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_credential=os.environ["AZURE_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
    )
    result = app.acquire_token_for_client(
        scopes=["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"]
    )
    if "access_token" not in result:
        raise RuntimeError(f"MSAL token acquisition failed: {result.get('error_description', result)}")
    return result["access_token"]
```

Add `msal` to `requirements-dev.txt`. Update `airflow/.env.example` to remove `DATABRICKS_TOKEN` and add `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`.

### Step 3: MSAL swap — operator path (`databricks_default` connection)

**This is the second auth path** — the one the MSAL swap in step 2 does NOT close.
`DatabricksSubmitRunOperator` uses the `databricks_default` Airflow connection, which currently has `password = <token>` set once at startup. That token can expire on long runs.

Fix: update `AIRFLOW_CONN_DATABRICKS_DEFAULT` to use SP client credentials via the provider's `extra` fields so the hook refreshes tokens automatically.

Likely format (verify against installed provider version before setting):
```json
{
  "conn_type": "databricks",
  "host": "adb-7405614006245057.17.azuredatabricks.net",
  "extra": {
    "azure_tenant_id": "5095ccc0-a03b-426e-999a-9a34539529ee",
    "client_id": "91171f7d-478d-4dfd-a6cb-33e0e2011b23",
    "client_secret": "<secret>"
  }
}
```

**Risk:** exact extra field names (`client_id` vs `azure_client_id`, `client_secret` vs `azure_client_secret`) vary across provider versions. Provider is unpinned. Check `DatabricksHook._get_token()` source or run a test connection before committing this format.

### Step 4: GitHub Actions CI

File: `.github/workflows/ci.yml`
Trigger: push on all branches + PR targeting main.
Steps: checkout → Python 3.11 → install deps → `ruff check .` → `black --check .` → `pytest tests/unit/ -v`
**No Databricks connection required** — unit tests (`test_contract_gate.py`, `test_scope_gate.py`) are pure Python with zero external dependencies.

This is the "bad PR blocked" hero story trigger.

### Step 5: Databricks Asset Bundle

File: `databricks.yml` at repo root.
Syncs `notebooks/` to workspace + packages wheel. Makes workspace layout reproducible from git.
Auth in CI/CD: `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID` env vars (Databricks CLI uses `ARM_*`, not `AZURE_*` — see env-var naming section below).

### Step 6: GitHub Actions CD

File: `.github/workflows/cd.yml`
Trigger: push to `main`.
Steps: checkout → install Databricks CLI → set `ARM_*` env vars from GitHub secrets → `databricks bundle deploy --target prod`.

---

## Env-Var Naming — Three Contexts, Explicit Mapping

Same SP credentials, three different naming conventions:

| Context | Variable names | Source |
|---|---|---|
| Local `.env` (gitignored) | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` | Azure SDK convention; what's already in `.env` |
| GitHub Actions secrets | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` | Same — store once, reference as `${{ secrets.AZURE_CLIENT_ID }}` |
| Databricks CLI (bundle deploy) | `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID` | Databricks CLI reads `ARM_*` for Azure SP auth |
| MSAL in Python (DAG) | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` | What `get_databricks_token()` reads from `os.environ` |

In the CD workflow, the mapping is explicit:
```yaml
env:
  ARM_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  ARM_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  ARM_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  DATABRICKS_HOST: https://adb-7405614006245057.17.azuredatabricks.net
```

---

## Unresolved Risks

| Risk | What to do |
|---|---|
| UC GRANT: SP applicationId backtick format may not work as-is in all Databricks SQL editor versions | Run `SHOW GRANTS` immediately after each GRANT to confirm; if it fails, try the SP's display name |
| **Operator auth path not fully closed:** MSAL swap only fixes dbt; `DatabricksSubmitRunOperator` connection still needs updating (step 3) | Do not claim "token-expiry scar is closed" until both paths are fixed. Be honest in interviews: "I closed the dbt path with MSAL; the operator path uses the provider's built-in SP refresh." |
| ~~Databricks Airflow provider extra field names~~ | **Resolved** — provider is 6.7.0; confirmed fields: `azure_tenant_id`, `azure_client_id`, `azure_client_secret` |
| `DBT_BIN = "/home/faz/dbt-venv/bin/dbt"` is a WSL path — won't work in GitHub Actions | CD workflow installs dbt via `pip install dbt-databricks` and uses `dbt` from PATH |
| SP needs "Can Attach To" on cluster `0529-152429-s8benrb4` — workspace-level permission, not UC | Set via Databricks UI: Compute → Clusters → cluster → Permissions → add SP |
| SQL warehouse CAN USE is UI-only (no SQL GRANT equivalent) | Set manually in Databricks UI as part of step 1 |
| GitHub Actions secrets must exist before first CD run | Add `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` to repo secrets before merging any CD-triggering commit |

---

## Exact Next 3 Actions

```
1. Databricks SQL Editor (as faisal1990@hotmail.co.uk):
   Run each statement in notebooks/admin/00_grant_sp_permissions.sql
   Then verify: SHOW GRANTS TO `91171f7d-478d-4dfd-a6cb-33e0e2011b23`;

2. Databricks UI:
   SQL Warehouses → 38837e3baf7e2b92 → Permissions
   → Add principal 91171f7d-478d-4dfd-a6cb-33e0e2011b23 → CAN USE

3. Databricks UI:
   Compute → Clusters → 0529-152429-s8benrb4 → Permissions
   → Add SP 91171f7d-478d-4dfd-a6cb-33e0e2011b23 → Can Attach To
```

After these 3 manual steps, ask Claude Code to continue writing the P6 code files (steps 2–6 above).

---

## Locked Decisions

- **pgvector over Azure AI Search** — relational integration + portability. Not an oversight.
- **Airflow trigger-not-execute** — Airflow submits notebook runs to Databricks; it does not run Spark locally.
- **DAB for notebook sync, not for replacing Airflow** — Databricks Asset Bundles make the workspace layout reproducible; Airflow remains the scheduler.
- **CI = lint + pytest, no live Databricks** — `dbt build` requires a live SQL warehouse; CI stays dependency-free. dbt runs in CD or locally.
- **MSAL scope = `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default`** — the `/.default` suffix requests all pre-consented permissions; the GUID is the Azure AD resource identifier for Databricks globally.
