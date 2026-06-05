# Project State — Clinical Knowledge Platform

**Last updated:** 2026-06-05
**Current phase:** P6 (CI/CD via GitHub Actions) — PROOF RUN PENDING

---

## Current Objective

Execute the P6 hero story proof:
1. Open a PR with a deliberate lint/test failure → CI blocks merge (red ✗)
2. Fix it → CI passes (green ✓) → merge goes through → CD deploys bundle
3. Screenshot the blocked PR and the green deploy as evidence

---

## Proven Facts (P1–P5 complete + P6 code complete)

| Fact | Verified by |
|---|---|
| Bronze Delta table `clinical_platform.bronze.guidelines_raw` with 6 provenance cols | Databricks query |
| Auto Loader idempotency: same hash on re-run does not duplicate rows | `evidence/bronze_idempotency_proof_run_comparison.png` |
| Silver contract gate quarantines bad rows with reason codes; Silver unchanged | `evidence/p2_contract_gate_proof.png` |
| `dbt test` passes **25/25** (confirmed from `dbt/target/run_results.json`, 2026-06-02) | `evidence/p5_dbt_tests_pass.png` |
| dbt lineage graph generated clean | `evidence/p3_dbt_lineage.png` |
| SCD2 `dim_guideline_snapshot` captures version history | `evidence/p4_scd2_transition.png` |
| Governance test fires on clinical-area drift (`scd2_no_clinical_area_change`) | `evidence/p4_governance_test_fires.png` |
| Airflow DAG end-to-end: Bronze → Silver → Gold → stubs | `evidence/p5_dag_run_success.png` |
| P5 idempotency: re-run full pipeline → Silver still 7 rows, not 14 | `evidence/p5_idempotency_silver_7.png` |
| SP `clinical-platform-cicd` created, secret rotated, registered in workspace | SCIM query: `totalResults: 1`, `active: true` |
| UC grants applied for SP on all three schemas | `SHOW GRANTS` verified in Databricks SQL Editor |
| MSAL swap implemented in `get_databricks_token()` (dbt auth path) | `airflow/dags/clinical_platform_pipeline.py` |
| GitHub Actions CI gate live: ruff + black + pytest on PR | `.github/workflows/ci.yml` |
| GitHub secrets set: `AZURE_CLIENT_ID/SECRET/TENANT_ID` | GitHub repo settings |
| Branch protection on `main`: `lint-and-test` required before merge | GitHub repo settings |
| Databricks Asset Bundle defined: `databricks.yml` syncs `notebooks/` | `databricks.yml` |
| GitHub Actions CD live: `databricks bundle deploy --target prod` on merge | `.github/workflows/cd.yml` |

---

## P6 Infrastructure

| Item | Value |
|---|---|
| SP appId (client ID) | `91171f7d-478d-4dfd-a6cb-33e0e2011b23` |
| SP tenant | `5095ccc0-a03b-426e-999a-9a34539529ee` |
| SP Databricks workspace id | `144343832918962` |
| Secret location | Key Vault `kv-clinpl-dev` → `databricks-cicd-sp-secret`; local `.env` (gitignored). **Never paste or screenshot.** |
| Databricks workspace | `adb-7405614006245057.17.azuredatabricks.net` |
| SQL warehouse http_path | `/sql/1.0/warehouses/38837e3baf7e2b92` |
| All-purpose cluster | `0529-152429-s8benrb4` |
| Airflow provider version | `apache-airflow-providers-databricks==6.7.0` |
| Operator connection extra fields (verified) | `azure_tenant_id`, `azure_client_id`, `azure_client_secret` |

---

## P6 Three Hero Stories — Status

| Story | Status | Proof artifact needed |
|---|---|---|
| SP/OAuth M2M auth | dbt path ✅ closed via MSAL; operator path documented (connection not yet wired in running Airflow) | DAG code + commit |
| Tests as merge gate | ✅ CI live + branch protection set | Screenshot: bad PR blocked → fixed PR merged |
| Deploy-as-code | ✅ DAB + CD workflow live | Screenshot: CD run deploying bundle on merge |

---

## Open Items

| Item | What |
|---|---|
| **P6 proof run** | Open bad PR → show blocked → fix → show merged + CD deployed. This is the evidence artifact. |
| **Operator auth path** | `AIRFLOW_CONN_DATABRICKS_DEFAULT` not yet rebuilt with SP extra fields in running Airflow instance. Interview answer: "dbt path closed with MSAL; operator path uses provider's built-in SP refresh once connection is wired." |
| `DBT_BIN` WSL path | `"/home/faz/dbt-venv/bin/dbt"` hardcoded in DAG — fine for local WSL runs; CD installs dbt from PATH. |

---

## Env-Var Naming — Three Contexts

| Context | Variable names |
|---|---|
| Local `.env` + GitHub secrets | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` |
| Databricks CLI (bundle deploy) | `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID` |
| MSAL in Python (DAG) | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` |

CD workflow maps explicitly: `ARM_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}` etc.

---

## Next Session: P6 Proof Run

```
1. Create a feature branch
2. Introduce a deliberate lint error (e.g. unused import in any src/ file)
3. Open a PR → CI runs → lint-and-test fails → merge blocked (screenshot)
4. Fix the error → push → CI passes → merge
5. CD triggers → databricks bundle deploy → screenshot the Actions run
6. Save screenshots to evidence/
7. Update CLAUDE.md: P6 → ✅ DONE
8. /clear → start P7
```

---

## Locked Decisions

- **pgvector over Azure AI Search** — relational integration + portability. Not an oversight.
- **Airflow trigger-not-execute** — Airflow submits notebook runs to Databricks; does not run Spark locally.
- **DAB for notebook sync, not replacing Airflow** — Databricks Asset Bundles make the workspace reproducible; Airflow remains the scheduler.
- **CI = lint + pytest, no live Databricks** — dbt runs in CD or locally; CI stays dependency-free.
- **MSAL scope = `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default`** — `/.default` requests all pre-consented permissions; GUID is the AAD resource identifier for Databricks globally.
