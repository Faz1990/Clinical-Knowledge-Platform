# Project State — Clinical Knowledge Platform

**Last updated:** 2026-06-05
**Current phase:** P7 — RAG serving layer

---

## Current Objective

Build the RAG serving layer: chunk → embed (Azure OpenAI) → store in pgvector → LangChain retrieval → LLM answer with resolvable citation to guideline version.

Proof artifact: a clinical Q&A that returns an answer with a citation traceable to a specific `guideline_id` + `guideline_version` in `dim_guideline`.

---

## Proven Facts (P1–P6 complete)

| Fact | Verified by |
|---|---|
| Bronze Delta table with 6 provenance cols, Auto Loader idempotency | `evidence/bronze_idempotency_proof_run_comparison.png` |
| Silver contract gate quarantines bad rows; Silver unchanged | `evidence/p2_contract_gate_proof.png` |
| dbt Silver → Gold: **25/25 tests pass**, lineage clean | `evidence/p5_dbt_tests_pass.png`, `evidence/p3_dbt_lineage.png` |
| SCD2 `dim_guideline_snapshot` captures version history | `evidence/p4_scd2_transition.png` |
| Governance test fires on clinical-area drift | `evidence/p4_governance_test_fires.png` |
| Airflow DAG end-to-end, idempotency verified (Silver 7 rows on re-run) | `evidence/p5_dag_run_success.png`, `evidence/p5_idempotency_silver_7.png` |
| SP `clinical-platform-cicd` MSAL auth (dbt path) — personal token closed | `airflow/dags/clinical_platform_pipeline.py` |
| GitHub Actions CI gate: ruff + black + pytest, blocks bad PRs | `evidence/p6_ci_gate_blocked.png`, `evidence/p6_ci_gate_passed.png` |
| GitHub Actions CD: `databricks bundle deploy` on merge to master | `evidence/p6_cd_deploy.png` |
| UC grants applied for SP on all three schemas | `notebooks/admin/00_grant_sp_permissions.sql` |

---

## P6 Open Item (carry into P7 if operator auth needed)

`databricks_default` Airflow connection not yet rebuilt with SP extra fields in the running Airflow instance. dbt auth path is closed. For interview: "dbt path uses MSAL; operator path uses the provider's built-in SP refresh once the connection is wired — extra fields are `azure_tenant_id`, `azure_client_id`, `azure_client_secret` (provider 6.7.0, verified)."

---

## P7 Architecture

```
Gold table (fact_guideline_section / RAG chunks)
  ↓ chunking (already in dbt model or new step)
  ↓ embed: Azure OpenAI text-embedding-3-small
  ↓ pgvector (Postgres on Azure) — stores chunk + embedding + guideline_id + version
  ↓ LangChain retriever (similarity search, top-k)
  ↓ LLM (Azure OpenAI GPT-4o) → cited answer
```

Citation must be resolvable: answer references `guideline_id` + `guideline_version` which maps to a row in `dim_guideline`.

---

## P7 Key Decisions (locked)

- **pgvector on Postgres** — not Azure AI Search. Interview answer: "evaluated Azure AI Search; chose pgvector for relational integration and portability."
- **LangChain** — thin glue layer only. No LangChain abstractions that obscure what's happening.
- **Azure OpenAI** — same subscription as the rest of the platform.
- **Corpus scope** — 10–15 NICE guidelines, one clinical area only (type 2 diabetes / hypertension / CKD — TBD at start of P7).

---

## Env-Var Naming (carry forward)

| Context | Variable names |
|---|---|
| Local `.env` + GitHub secrets | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` |
| Databricks CLI (bundle deploy) | `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID` |
| MSAL in Python (DAG) | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` |

---

## Infrastructure Reference

| Item | Value |
|---|---|
| SP appId | `91171f7d-478d-4dfd-a6cb-33e0e2011b23` |
| SP tenant | `5095ccc0-a03b-426e-999a-9a34539529ee` |
| Databricks workspace | `adb-7405614006245057.17.azuredatabricks.net` |
| SQL warehouse | `/sql/1.0/warehouses/38837e3baf7e2b92` |
| All-purpose cluster | `0529-152429-s8benrb4` |
| Key Vault | `kv-clinpl-dev` — secret: `databricks-cicd-sp-secret` |
| Storage account | `stclinpldev` |
| Airflow provider | `apache-airflow-providers-databricks==6.7.0` |

---

## Locked Decisions (all phases)

- **pgvector over Azure AI Search** — relational integration + portability.
- **Airflow trigger-not-execute** — submits notebook runs to Databricks; does not run Spark locally.
- **DAB for notebook sync, not replacing Airflow** — workspace layout reproducible from git; Airflow remains the scheduler.
- **CI = lint + pytest, no live Databricks** — dbt runs in CD or locally; CI stays dependency-free.
- **MSAL scope = `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default`**
