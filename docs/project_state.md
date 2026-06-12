# Project State — Clinical Knowledge Platform

**Last updated:** 2026-06-12
**Current phase:** P10 — Silent-degradation postmortem

---

## Current Objective

Induce and document silent RAG degradation: re-embed a targeted chunk subset with a different model, measure the precision drop via `eval.run()`, write the postmortem doc, and update `project_state.md` with the before/after curve.

Proof artifact: before/after RAGAS degradation curve (precision drop) + postmortem doc.

**The closing-the-loop story:** P9 built the automated eval gate. P10 proves the gate catches the one failure mode that doesn't crash the system — embedding model drift causes silent retrieval degradation. Freshness alert is structurally blind to this (re-embedding updates `embedded_at`, so freshness reads *fresh*); only the eval signal catches it. That is the "eval-as-infrastructure" argument demonstrated rather than asserted.

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

**Finding P8-5 — CLOSED (2026-06-12, P10 step 7). Judge leniency confirmed; faithfulness=1.0 is a judge error. Pre-registered prediction held.**

Q_P7 answer: *"the recommended HbA1c target is 53 mmol/mol (7.0%). If HbA1c levels are not adequately controlled and rise to 58 mmol/mol (7.5%) or higher, a third agent should be added to intensify treatment."*

Retrieved chunks (the exact evidence the judge scored against, post-restore — P8 conditions reconstructed):
- Chunk 1 (sim=0.670): HbA1c monitoring *frequency* and IFCC calibration [NG28] — not targets, not escalation
- Chunk 2 (sim=0.596): Relaxing targets for older/frailer patients [NG28] — nearest keyword is *"intensive management would not be appropriate"* — argues the opposite of the answer's bridge
- Chunk 3 (sim=0.573): Tirzepatide pricing [TA924] — entirely off-topic
- Chunk 4 (sim=0.571): Insulin adverse-event scenarios [NG28] — off-topic for the bridge
- Chunk 5 (sim=0.565): Insulin initiation (continue metformin, stop other agents) [NG28] — off-topic

Neither the 53/58 thresholds nor the dual→third-agent rule appears in any chunk. The numbers are real NICE values but came from GPT-4o's parametric knowledge, not the retrieved context. The bridge is fabricated. The judge scored faithfulness=1.0 against chunks that do not support either the numbers or the clinical logic — and the nearest keyword occurrence (Chunk 2 "intensive management") argues the reverse.

**P8-4 mechanism confirmed to extend to faithfulness:** same-model judge (GPT-4o) rewards the generator's plausible parametric output regardless of whether the context supports it. Recall inflation (P8-4) and faithfulness inflation (P8-5) share the same root cause.

**Interview-grade finding:** faithfulness measures grounding-in-context, not truth. This answer is arguably correct in the world yet unfaithful to what was retrieved. The metric scored 1.0; reading the context shows no grounding. This is why eval discipline requires reading the context, not trusting the score — and it is what the platform was built to catch. Proof artifact: `evidence/p10_6_qp7_context_read.png`.

**Finding P8-6 — Bold-heading extraction artifact (Silver backlog).** PDF extractor double-renders bold subheadings throughout the corpus ("PPeeooppllee" for "People"). Degrades embedding quality on rationale-section chunks. Fix: targeted normaliser detecting fully-doubled tokens at parse time — not a global double-letter strip, not a diagram-extraction rewrite. Low priority; out of P8 scope.

**Finding P8-7 — Embedding dilution / pointer-outranks-content (retrieval backlog).** §1.13.1 first-line no-comorbidity recommendation ("offer metformin + SGLT-2") exists in chunk 12, clean text. Chunk 12's embedding is dominated by ~400 words of preamble before §1.13.1 appears. Result: chunk 13 (the navigation pointer to §1.13) outranks chunk 12 for a direct question about first-line treatment. Distinct mechanism from vocabulary mismatch — content present, embedding diluted by co-located preamble.

**P8 open items — resolved in P9:**
- DAG: `run_ragas_eval` EmptyOperator → PythonOperator ✅ (2026-06-12)

**P8 open items — carry to P10:**
- `requirements-dev.txt`: pin ruff + black to match CI versions (open from P7)
- Auto Loader `pathGlobFilter "*.pdf"` — stop manifest CSV at source (P7 Finding 1)
- Confirm Bronze MERGE `ON` clause idempotency (carries from P7)
- **P8-5 CLOSED — see Finding P8-5 above.** Judge leniency confirmed in P10 step 7 by direct context read. The `observability_report.py` footnote hedge was correctly written and stands.

---

## P9 Complete — What Was Built

**Files:**
- `src/clinical_platform/telemetry.py` — `get_index_built_ts()` (pgvector `MAX(embedded_at)`; epoch on empty table), `write_eval_telemetry()` (idempotent DELETE+INSERT, single multi-row commit per run)
- `src/clinical_platform/eval.py` — per-question timing, `retrieval_mean_similarity` (mean cosine sim), positional concat with assert for RAGAS→perf join, returns `(dict, DataFrame)`
- `airflow/dags/clinical_platform_pipeline.py` — `run_ragas_eval` + `publish_metrics` swapped from EmptyOperator; freshness uses `total_seconds() / 86400` (exact boundary); alert raises `AirflowException` so task goes red in UI
- `notebooks/observability/01_retrieval_dashboard.py` — Databricks notebook, 4 panels from Delta table, P8 trust labels
- `demo/observability_report.py` — local proof artifact (3 panels: precision trend, trust-labelled metrics, freshness)

**Telemetry table:** `clinical_platform.gold.retrieval_telemetry`
Schema: `ts, question, latency_ms, k, retrieval_mean_similarity, index_built_ts, eval_run_id, context_precision, context_recall`
Note: column is `retrieval_mean_similarity` (mean cosine sim of retrieved chunks), NOT `citation_coverage` — different things.

**Key P9 finding (load-bearing for P10):**
Re-embedding updates `embedded_at` → freshness alert reads the index as *fresher than ever* while retrieval is silently broken. Freshness is structurally blind to model-version drift. Only the eval signal (`context_precision` drop) catches it. This is the argument for eval-as-infrastructure, demonstrated in P10.

**Proof artifact:** `python demo/observability_report.py` with `FRESHNESS_TTL_DAYS=1` trips the alert (index is ~6d old at time of P10 session). Screenshot this as evidence.

**P9 open items — carry to P10:**
- `embed_chunks` EmptyOperator → real PythonOperator (deferred; not P9 critical path)
- See also P8 open items above

---

## P10 Plan — Silent-Degradation Postmortem

**Approach: Option A — real re-embedding with a different model (NOT synthetic noise)**
Rationale: noise-corruption tests the detection path but poisons the narrative. "I added noise" isn't a production failure mode. "Embedding model version drift" is — it's already on the CV, it's the scenario the P3 prevention plan (signature validation, version pinning) guards against.

**Model choice: `text-embedding-ada-002` (1536-dim)**
- DO NOT use `text-embedding-3-large` at default settings → 3072-dim vs 1536-dim index → pgvector errors loudly. That's a crash, not silent degradation.
- `ada-002` is 1536-dim (same as `text-embedding-3-small` index). Cosine similarity computes, means nothing. That's the silent part.
- Alternative: `text-embedding-3-large` with `dimensions=1536` also works.

**Targeted subset, not random:**
- Re-embed only the chunks currently serving Q2 and Q3a's precision-1.0 retrieval sets (top-k from the P8 baseline CSV).
- Why: a random subset may miss the eval questions' retrieval sets entirely → precision doesn't move → demo fails.
- Expected result: aggregate precision drops from 0.500 toward 0.0–0.25. Q3a precision drops from 1.0. Q_P7 stays at 0.0 (already broken, unaffected).
- Falsifier: if Q3a holds at 1.0 after re-embedding, the targeted subset missed its retrieval set.

**Pre-flight checks (verified 2026-06-12):**
- `store.py` `ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding, embedded_at = NOW()` — upsert updates, not skips. Both `induce` and `restore` will write. ✅
- `eval.py` save path: `ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")` then `SCORES_DIR / f"baseline_{ts}.csv"` — `ts` is generated per `run()` call, so each eval run writes a new file. ✅

**Build steps:**
0. Create `text-embedding-ada-002` deployment in `<azure-openai-resource>` (UK South). Per cost rule: delete at step 8. It almost certainly doesn't exist right now.
1. Snapshot affected rows: `python demo/p10_induce_degradation.py snapshot`.
2. **Back up the baseline before running eval:** `cp data/ragas_scores/baseline_20260607T004856Z.csv data/ragas_scores/_backup_p8_baseline.csv`. Eval writes a new timestamped file per run (verified from source), but the P8 baseline is irreplaceable — one command of insurance.
3. Re-embed Q2+Q3a top-k chunk_ids: `python demo/p10_induce_degradation.py induce --model text-embedding-ada-002`.
4. Run `python -m clinical_platform.eval` → new `baseline_<ts>.csv` appears alongside the P8 baseline. **Gate:** precision must be visibly lower than 0.500, and specifically Q3a < 1.0 with Q_P7 still 0.0. If aggregate precision is unchanged at 0.500, stop — induce no-op'd. Do not proceed; check the write landed before anything else.
5. `python demo/observability_report.py` → Panel 1 shows the precision drop; Panel 3 shows FRESH (freshness blindness in the same screenshot). **Capture this screenshot before touching restore** — step 6 overwrites the degraded index state that produces this artifact. Re-inducing to recover a missed screenshot is unnecessary work.
6. Restore: `python demo/p10_induce_degradation.py restore`. The script self-verifies the write by re-fetching one chunk's embedding from pgvector and comparing to the snapshot — exits non-zero if the upsert no-op'd.
7. **Verify recovery + close P8-5:** re-run `python -m clinical_platform.eval`. Precision must return to ~0.500 — without this, "restored" is an assertion. While reading output, call `ask()` interactively for Q_P7 and read the retrieved chunks alongside the generated answer. Answer text ("a third agent should be added to intensify treatment") is confirmed from the baseline CSV; the retrieved chunk vocabulary is not — contexts column was dropped. Seeing the chunks here closes P8-5 properly: if "intensify medicines" is in the context, the judge may have been correct; if not, faithfulness=1.0 is a confirmed judge error and the trust labels in `observability_report.py` need updating. **Pre-registered prediction:** P8-2 established Q_P7's retrieved set was uniformly off-topic (HbA1c monitoring, metformin alternatives). If those chunks don't contain dual→third-agent framing, the judge had no grounding basis for faithfulness=1.0 → confirmed judge leniency, extending P8-4 from recall to faithfulness. **Sanity check for restore validity:** verify the retrieved set for Q_P7 matches P8-2's off-topic description. If it looks different, the index isn't at baseline state — restore failed, and the recovery verification in this same step has also failed.
8. Delete `ada-002` deployment from Azure OpenAI (cost hygiene).
9. Write the postmortem doc.

**Expected magnitude:** Q3a precision drops from 1.0 to some value < 1.0, not necessarily 0.0. Re-embedding the targeted chunks displaces them; other chunks rise into top-5, and if any are incidentally on-topic Q3a lands between 0 and 1. Falsifier: Q3a < 1.0 and Q_P7 unchanged at 0.0. Don't pre-commit the postmortem to "precision collapsed to zero."

**Freshness blindness (postmortem headline):** Both `induce` and `restore` call `upsert_chunks`, which sets `embedded_at = NOW()` on conflict. The freshness alert reads FRESH throughout the entire incident — during active degradation and after recovery. The incident is invisible to P9's alert from start to finish. Only the eval signal detects degradation; only the eval signal confirms recovery. That is the eval-as-infrastructure argument demonstrated rather than asserted.

**Postmortem must include:**
- Before/after precision table (Q_P7, Q2, Q3a, Q3b)
- Detection-gap finding: freshness alert shows *green* during active degradation (embedded_at was just updated)
- Eval gate catches what freshness cannot
- Resolution: restore index + add model_version column + add version-pinning to embed pipeline

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
| Azure OpenAI resource | `<azure-openai-resource>` — UK South — manual (not Terraform) |
| Azure OpenAI endpoint | `https://<azure-openai-resource>.openai.azure.com/` |
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
