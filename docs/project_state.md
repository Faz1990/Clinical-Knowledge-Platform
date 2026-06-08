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

## P8 Complete — Findings

**Harness:** `src/clinical_platform/eval.py` + `data/eval_questions.json` + `requirements-eval.txt`. Baseline CSV in `data/ragas_scores/` (contexts column dropped — NICE © copyright). Ground truths authored from observed chunk text only; conditional linking §1.25.1 (DPP-4) to §1.25.2 (SU/pio/insulin) verified against PDF pages 104–105.

**Test set (4 questions):**

| ID | Phrasing | Purpose |
|---|---|---|
| Q_P7 | Clinical vocab "dual therapy / third agent" | Vocab-mismatch failure — fabrication case |
| Q2 | Guideline vocab "SGLT-2 / individualised glycaemic targets" | Clean positive anchor (different topic) |
| Q3a | Guideline vocab "further medicines / no relevant comorbidity" | Vocab contrast — retrieves on-topic |
| Q3b | Clinical vocab "third agent / dual therapy" | Vocab contrast — same GT, different surface phrasing |

**Baseline scores:**

| Metric | Aggregate | Q_P7 | Q2 | Q3a | Q3b |
|---|---|---|---|---|---|
| faithfulness | 0.867 | 1.000 | 1.000 | 0.667 | 0.800 |
| answer_relevancy | 0.900 | 0.786 | 0.978 | 0.910 | 0.928 |
| context_precision | 0.500 | 0.000 | 1.000 | 1.000 | 0.000 |
| context_recall | 0.917 | 1.000 | 1.000 | 1.000 | 0.667 |

**Findings from baseline run:**

**Finding P8-1 — Precision is valid rank-weighted AP (confirmed empirically).** Interleaved mixed-context test (on/off/on/off/on order) returned 0.7556, matching closed-form AP exactly ((1.0 + 0.667 + 0.6) / 3). Binary values in main run reflect uniform per-question topic relevance — all 5 retrieved chunks for Q_P7/Q3b were off-topic, all 5 for Q3a were on-topic. No metric collapse.

**Finding P8-2 — Precision is the cleaner vocab-mismatch signal.** Q_P7 precision = 0.0 and Q3b precision = 0.0: clinical-vocab questions retrieve uniformly off-topic chunk sets (HbA1c monitoring, metformin alternatives). Q3a precision ≈ 1.0: guideline-vocab question retrieves on-topic set. Q2 precision ≈ 1.0 but is the clean anchor on a different topic (SGLT-2 continuation) — not part of the vocab experiment. The vocab contrast is Q3a vs Q3b.

**Finding P8-3 — Recall directionally confirms the vocab contrast (magnitude soft).** Q3a context_recall > Q3b context_recall (1.0 vs 0.667), consistent with the vocabulary hypothesis. Magnitude is treated as an upper bound — same-model judge inflation (P8-4) affects recall. The precision split (1.0 vs 0.0) is the validated signal; recall corroborates direction only.

**Finding P8-4 — Lenient same-model judge inflates both recall and faithfulness.** Q_P7 recall = 1.0 is over-attributed: the judge (GPT-4o) found "DPP-4 inhibitor" in the retrieved contexts and credited the ground-truth claim, without distinguishing the §1.25.1 no-comorbidity scenario from the metformin-contraindication scenario where DPP-4 also appears. Mechanism: when judge and generator are the same model, the judge over-credits paraphrases it would itself produce.

**Finding P8-5 — The P7 fabrication reproduced; faithfulness=1.0 is a judge error.** The Q_P7 generated answer reads: *"a third agent should be added to intensify treatment."* The dual→triple bridge is present. faithfulness=1.0 is a judge error: GPT-4o accepted "add a third agent to intensify" as a faithful paraphrase of "intensify medicines" from the retrieved chunk. This is consistent with P8-4 — the lenient judge inflated faithfulness by the same mechanism it inflated recall. The fabrication is retrieval-dependent (reproduced here; grounding available but not binding at temperature=0) and the faithfulness metric did not catch it. Reading the generated answer is the only reliable check when judge=generator.

**Finding P8-6 — Bold-heading extraction artifact (Silver backlog).** PDF extractor double-renders bold subheadings throughout the corpus ("PPeeooppllee" for "People"). Degrades embedding quality on rationale-section chunks. Fix: targeted normaliser detecting fully-doubled tokens at parse time — not a global double-letter strip, not a diagram-extraction rewrite. Low priority; out of P8 scope.

**Finding P8-7 — Embedding dilution / pointer-outranks-content (retrieval backlog).** §1.13.1 first-line no-comorbidity recommendation ("offer metformin + SGLT-2") exists in chunk 12, clean text. Chunk 12's embedding is dominated by ~400 words of preamble before §1.13.1 appears. Result: chunk 13 (the navigation pointer to §1.13) outranks chunk 12 for a direct question about first-line treatment. Distinct mechanism from vocabulary mismatch — content present, embedding diluted by co-located preamble.

**P8 open items (carry to P9):**
- DAG: replace `run_ragas_eval` EmptyOperator with real PythonOperator call to `eval.run()`
- `requirements-dev.txt`: pin ruff + black to match CI versions (open from P7)
- Auto Loader `pathGlobFilter "*.pdf"` — stop manifest CSV at source (P7 Finding 1)
- Confirm Bronze MERGE `ON` clause idempotency (carries from P7)

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
