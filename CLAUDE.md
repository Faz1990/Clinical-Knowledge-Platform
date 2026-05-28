# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**Clinical Knowledge Platform — governed lakehouse with AI-serving and retrieval observability.**

NHS/NICE guideline data ingested through a dbt-modelled medallion architecture on Azure/Databricks, orchestrated by Airflow with CI/CD via GitHub Actions, serving a RAG application with RAGAS evaluation and retrieval observability. The AI layer is the consumer of the DE platform — its correctness depends on the data engineering being solid.

## Architecture

```
SOURCES                  INGESTION               LAKEHOUSE (Databricks · Delta · Unity Catalog)
NHS/NICE guidelines  →   ADF Copy Activity    →  Bronze (raw, append-only, 6 provenance cols)
(HTML / PDF)             + Auto Loader            ↓ schema-contract gate + quarantine
corpus/raw/              (cloudFiles,             Silver (parsed text + metadata, deduped)
                          binaryFile format)       ↓ dbt (staging → intermediate → marts)
                                                   Gold ├─ star schema (fact_guideline_section)
                                                        ├─ dim_guideline (SCD Type 2)
                                                        └─ RAG-ready chunks
                                                              ↓
AI SERVING:   chunk → embed (Azure OpenAI) → pgvector → LangChain retrieve → LLM → cited answer
RAGAS EVAL:   faithfulness · answer-relevancy · context-recall · context-precision (runs in DAG)
OBSERVABILITY: retrieval latency · hit rate · citation coverage · eval-score trend · index freshness

ORCHESTRATION: Airflow DAG (ingest → bronze → silver → gold/dbt → embed → eval → publish)
CI/CD:         GitHub Actions (lint → pytest → dbt build → deploy → smoke test)
```

## Tech Stack

| Layer | Tool |
|---|---|
| Cloud | Azure (ADLS Gen2, ADF, Azure OpenAI) |
| Lakehouse | Databricks, Delta Lake, Unity Catalog |
| Transforms | dbt (incremental merge, 4+ test types, custom test, lineage) |
| Orchestration | Apache Airflow (retries, backoff, SLAs, sensors) |
| Vector store | pgvector on Postgres (not Azure AI Search — intentional trade-off) |
| RAG | LangChain (thin glue layer) |
| Eval | RAGAS |
| CI/CD | GitHub Actions |
| IaC | Terraform |
| Python linting | ruff / black |

## Corpus

10–15 NICE guidelines, **one clinical area only** (type 2 diabetes / hypertension / CKD — TBD). Coherence over breadth. Files land in `corpus/raw/`; manifests in `corpus/manifest/`.

## Bronze Provenance Columns (non-negotiable)

Every Bronze Delta row must carry: `source_url`, `retrieved_at`, `content_hash` (SHA-256), `guideline_version`, `pipeline_run_id`, `ingest_timestamp`.

## Three Flagship Failure Stories

These are the interview centrepieces. Every other instrumentation is light; these three are perfected.

1. **Data-contract catch (P2):** bad guideline data → quarantine batch → downstream blocked → reason codes logged. System: Silver does NOT update.
2. **CI/CD block (P6):** bad PR → GitHub Actions fails → merge blocked. Fixed commit → green → deploy proceeds.
3. **Silent RAG degradation (P10):** embedding swap / corpus drift → system keeps running → RAGAS metrics degrade → dashboard catches it → postmortem written. The killer: monitoring quality decay, not just crashes.

## Build Phases

P1–P6 (DE spine) must complete before P7–P9 (AI layer). P10 is the postmortem.

| Phase | Goal | Key proof artifact |
|---|---|---|
| P1 | ADF + Auto Loader → Bronze | Same-hash/different-run idempotency screenshot |
| P2 ⭐ | Silver + contract gate + quarantine | Quarantined rows with reason codes; Silver unchanged |
| P3 | dbt models + tests (Silver → Gold) | `dbt build` clean; lineage graph |
| P4 | Dimensional model (star schema + SCD2) | SCD2 version-history query; semantic-validation catch |
| P5 | Airflow DAG orchestration | Induced failure → retry → recovery; no duplicate outputs |
| P6 ⭐ | CI/CD via GitHub Actions | Bad PR blocked; fixed PR passes and deploys |
| P7 | RAG serving layer | Clinical Q&A with resolvable citation to guideline version |
| P8 | RAGAS eval harness | Baseline RAGAS score table logged from a DAG run |
| P9 | Retrieval observability dashboard | Dashboard + tripped freshness alert |
| P10 ⭐ | Silent-degradation postmortem | Before/after RAGAS degradation curve + postmortem doc |

## Development Commands

```bash
# Terraform (provision Azure infra — P1)
cd terraform
cp terraform.tfvars.example terraform.tfvars  # fill in subscription_id + cluster_id
terraform init
terraform plan
terraform apply

# dbt (P3+)
dbt build                   # run all models + tests
dbt test                    # tests only
dbt docs generate           # regenerate lineage graph

# CI (P6+)
ruff check .                # lint
black --check .             # format check
pytest                      # unit tests

# Airflow (P5+)
# commands TBD based on deployment target (local Docker vs managed)
```

## Key Constraints

- **Scope is locked.** Do not add tools or proof points beyond the plan. Maximum trust per unit of complexity.
- **pgvector over Azure AI Search** — this is a deliberate trade-off, not an oversight. Interview answer: "I evaluated Azure AI Search but chose pgvector for relational integration and portability."
- **Execution order matters.** DE spine (P1–P6) before AI layer (P7–P9). The RAG layer's correctness depends on the pipeline underneath it.
