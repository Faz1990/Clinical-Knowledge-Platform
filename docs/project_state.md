# Project State — Clinical Knowledge Platform

**Last updated:** 2026-06-06
**Current phase:** P8 — RAGAS eval harness

---

## Current Objective

Build the RAGAS eval harness: log `(question, retrieved_contexts, generated_answer)` triples, run faithfulness / answer-relevancy / context-precision / context-recall, output a baseline score table from a DAG run.

Proof artifact: baseline RAGAS score table logged from a DAG run.

**The closing-the-loop story:** P7 caught a faithfulness failure manually (Finding 3). P8 turns that one-off catch into an automated gate — faithfulness metric flags the unsupported claim; context recall flags the retrieval miss that caused it.

---

## Proven Facts (P1–P7 complete)

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
| 145 Gold chunks (type 2 diabetes corpus, 6 guideline versions) embedded into pgvector | `evidence/p7_chunking_proof.png` |
| End-to-end cited Q&A — answer + `guideline_id` + `guideline_version` traceable to `dim_guideline` | `evidence/p7_qa_cited_answer.png` |
| Faithfulness failure documented: numbers grounded, clinical logic fabricated; retrieval vocabulary mismatch identified | `docs/project_state.md` §P7 findings |
| P7 PR merged to master through CI gate (ruff E501 + I001 caught and fixed) | `feat/p7-rag-serving-layer` PR |

---

## P7 Findings (carry into P8 as test cases)

**Finding 1 — Manifest CSV in Bronze (NULL `guideline_id`)**
Auto Loader ingested `guidelines_manifest.csv` alongside PDFs → two NULL-keyed rows, correctly blocked at the Silver scope gate. NULL rows accumulate (not deduplicated) because `NULL = NULL` is false in SQL join logic. Structural fix: `pathGlobFilter "*.pdf"` on Auto Loader. Open item: confirm the Bronze MERGE `ON` clause.

**Finding 2 — 7 Silver docs → 6 guideline versions in Gold (SCD2, not a gap)**
Three guidelines dropped at Bronze→Silver scope gate (NG17, NG3, NG18). NG28 alone has three SCD2 versions (2026-02-18: 74 chunks, 2026-03-04: 4, 2026-05-11: 3). EXCEPT query confirms completeness — every Silver `(guideline_id, guideline_version)` pair present in Gold.

**Finding 3 — Faithfulness failure (the headline; seeds P8)**
Numbers grounded (53/58 mmol/mol verbatim in NG28 chunk 6). Clinical logic fabricated: answer said "dual therapy → third agent"; guideline says "intensify medicines / add a DPP-4 inhibitor" (section 1.25). **Root cause: retrieval vocabulary mismatch** — question vocabulary didn't surface the 1.25.x pathway chunks; the model filled the gap from training data. The correct content was in the corpus but not retrieved.

Locked framing: *"Numbers grounded, clinical logic fabricated — the dangerous middle case RAG governance exists to catch. Caught it by reading the cited chunks. P8 automates this check."*

---

## P6 Open Item (carried forward)

`databricks_default` Airflow connection not yet rebuilt with SP extra fields in the running Airflow instance. dbt auth path is closed (MSAL). For interview: "dbt path uses MSAL; operator path uses the provider's built-in SP refresh once the connection is wired — extra fields are `azure_tenant_id`, `azure_client_id`, `azure_client_secret` (provider 6.7.0, verified)."

---

## P7 Open Items (carried forward)

- `pathGlobFilter "*.pdf"` on Auto Loader — stop the manifest CSV at source
- Confirm the Bronze MERGE `ON` clause — drop the "(or similar)" hedge on the idempotency story
- `requirements-dev.txt` pin ruff + black to the same versions CI uses — close the local/CI version-skew loop
- TA924 retrieved at 0.57 similarity on the HbA1c question — likely spurious; a reranker or metadata filter would remove it
- Operator auth path (`databricks_default`) — documented, not wired in running Airflow

---

## P7 Architecture (locked)

```
Silver table (guidelines_parsed — parsed_text)
  ↓ notebooks/gold/03_silver_to_rag_chunks.py (500-word chunks, 50-word overlap)
Gold table (rag_chunks — chunk_text + guideline_id + guideline_version + chunk_index)
  ↓ src/clinical_platform/embed.py — reads via Databricks SQL connector
  ↓ Azure OpenAI text-embedding-3-small (1536-dim)
  ↓ pgvector on Docker port 5433 (5432 taken by host Postgres) — HNSW cosine index
  ↓ src/clinical_platform/retriever.py — cosine similarity, top-5
  ↓ src/clinical_platform/qa.py — AzureChatOpenAI gpt-4o (temp=0) + Citation dataclass
  ↓ demo/clinical_qa.py → cited answer
```

pgvector runs on `5433:5432` permanently — host Postgres owns 5432. This is in `docker-compose.yml` and `.env`.

---

## P8 Setup

**RAGAS metrics to implement:**
- **Faithfulness** — atomic claim extraction vs. retrieved contexts. Catches Finding 3.
- **Answer relevance** — does the answer address the question.
- **Context precision / recall** — did retrieval surface the right chunks. Catches Finding A vocabulary mismatch (low recall: 1.25.x pathway not retrieved).

**What it consumes:** `(question, retrieved_contexts, generated_answer)` triples — pipeline already produces these, just needs logging.

**Scope:** light harness over a handful of curated Q/A pairs (include the diabetes dual-therapy question deliberately). Log a score table. Wire into the Airflow DAG. Do not gold-plate.

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
| SP appId | `<SP_APP_ID>` |
| SP tenant | `<TENANT_ID>` |
| Databricks workspace | `<DATABRICKS_WORKSPACE_URL>` |
| SQL warehouse | `<SQL_WAREHOUSE_HTTP_PATH>` |
| All-purpose cluster | `<CLUSTER_ID>` |
| Key Vault | `<KEY_VAULT_NAME>` — secret: `<SECRET_NAME>` |
| Storage account | `<STORAGE_ACCOUNT_NAME>` |
| Airflow provider | `apache-airflow-providers-databricks==6.7.0` |
| Azure OpenAI resource | `aoai-clinical-platform-dev` — UK South — manual (not Terraform) |
| Azure OpenAI endpoint | `https://aoai-clinical-platform-dev.openai.azure.com/` |
| pgvector container | `clinical_pgvector` — port `5433:5432` |

---

## Locked Decisions (all phases)

- **pgvector over Azure AI Search** — relational integration + portability.
- **HNSW over IVFFlat** — no minimum corpus size requirement; correct for a small clinical corpus.
- **`temperature=0` on GPT-4o** — determinism for a clinical tool; reproducibility is a property.
- **LangChain confined to `qa.py`** — `store.py` and `retriever.py` are raw psycopg2 + OpenAI SDK.
- **Separate `requirements-rag.txt`** — CI unit tests need no pgvector, OpenAI key, or Databricks connection.
- **Airflow trigger-not-execute** — submits notebook runs to Databricks; does not run Spark locally.
- **DAB for notebook sync, not replacing Airflow** — workspace layout reproducible from git; Airflow remains the scheduler.
- **CI = lint + pytest, no live Databricks** — dbt runs in CD or locally; CI stays dependency-free.
- **MSAL scope = `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default`**
