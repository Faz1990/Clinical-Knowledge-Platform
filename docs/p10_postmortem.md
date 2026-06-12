# P10 Postmortem — Silent RAG Degradation via Embedding Model Drift

**Date:** 2026-06-12  
**Phase:** P10 — Silent-degradation postmortem  
**Status:** Resolved  

---

## Incident Summary

Embedding model version drift was induced on a targeted subset of the clinical RAG index: 10 chunks serving the two precision-1.0 retrieval sets (Q2 and Q3a) were re-embedded with `text-embedding-ada-002` (1536-dim, same dimensionality as the production `text-embedding-3-small` index). The system continued operating without error. The freshness alert showed the index as fresh throughout — 0.2d old at the time of peak degradation, well under the 7d TTL. Aggregate `context_precision` dropped from 0.500 to 0.425. The eval gate caught the aggregate degradation via Q2; the freshness alert caught nothing.

---

## Timeline

| Time (UTC) | Event |
|---|---|
| 2026-06-12T15:56 | `induce` re-embedded 10 targeted chunks with ada-002. `embedded_at` updated to NOW(). |
| 2026-06-12T15:59 | Degraded eval run: aggregate precision 0.500 → 0.425. Q2 dropped 1.000 → 0.700. |
| 2026-06-12T16:37 | Observability report (degraded): Panel 1 −0.075 drop; Panel 3 Freshness OK, 0.2d old (TTL=7d). |
| 2026-06-12T22:25 | `restore` applied original 3-small embeddings. Write verified at data layer (float comparison vs snapshot). |
| 2026-06-12T22:27 | Recovery eval: aggregate precision returned to 0.500. Q2 restored to 1.000. |
| 2026-06-12T22:32 | Observability report (recovered): Panel 1 restored; Panel 3 still FRESH, 0.0d old (TTL=7d). |
| 2026-06-12T22:40 | Q_P7 context read: P8-5 closed. Faithfulness=1.0 confirmed judge leniency. |

---

## Before / After Precision Table

| Question | Baseline (P8) | Degraded | Recovered |
|---|---|---|---|
| Q_P7 (clinical vocab, vocab-mismatch) | 0.000 | 0.000 | 0.000 |
| Q2 (SGLT-2 continuation, clean anchor) | 1.000 | **0.700** | 1.000 |
| Q3a (further medicines, guideline vocab) | 1.000 | 1.000 * | 1.000 |
| Q3b (clinical vocab, dual-therapy) | 0.000 | 0.000 | 0.000 |
| **Aggregate** | **0.500** | **0.425** | **0.500** |

\* Q3a precision held at 1.000 despite full retrieval-set replacement — see Finding 2.

---

## Detection Gap

The freshness alert was uninformative throughout the entire incident. During degradation, `upsert_chunks` sets `embedded_at = NOW()` on conflict: re-embedding with ada-002 updated `embedded_at` on all 10 affected rows, and the freshness alert read the index as 0.2d old — comfortably under the 7d TTL, reading FRESH — at the exact moment retrieval quality was degraded. After recovery, restore also called `upsert_chunks`, again setting `embedded_at = NOW()`. The freshness alert read FRESH post-recovery as well. The entire incident was invisible to freshness monitoring from start to finish.

The freshness signal answers "when was the index last written?" not "which model wrote it?" These are different questions. Conflating them is what makes this failure mode silent.

The eval gate caught the aggregate degradation (−0.075, driven by Q2). But the eval gate itself had a partial blind spot: Q3a's precision held at 1.000 despite full retrieval-set corruption, because corpus redundancy masked it (see Finding 2). Nothing here is a complete safety net: freshness monitoring is structurally blind to model-version drift; the eval gate is necessary but not sufficient when the corpus has on-topic redundancy. Both layers are required, and even together they do not eliminate the need for direct chunk_id inspection.

**Evidence:** `p10_3_degraded_report.png` — Panel 1 shows −0.075 drop; Panel 3 shows Freshness OK, 0.2d old (TTL=7d). Both in the same frame.

---

## Findings

### Finding 1 — Eval caught the aggregate degradation; freshness caught nothing

Aggregate `context_precision` dropped from 0.500 to 0.425 (−0.075). Q2 degraded from 1.000 to 0.700. The freshness alert showed FRESH throughout. The eval gate is the only mechanism in this architecture that detects embedding model version drift at the signal level. For Q2, this worked: the corpus is not redundant enough for a complete retrieval-set replacement to go undetected. For Q3a it did not — see Finding 2.

### Finding 2 — Corpus redundancy and intra-document segment shuffling created a blind spot in the eval signal

Q3a's retrieval set was completely replaced at the chunk level: 0 of 5 original chunks appeared in the degraded top-5, confirmed by direct chunk_id comparison (`p10_2_q3a_blindness.png`). Yet Q3a's `context_precision` held at 1.000.

The mechanism is structural, not coincidental. Examining the document hashes underlying the chunk_ids:

- **Chunk overlap: 0/5** — no original chunk appeared in the degraded top-5.
- **Document overlap: 4/5** — 4 of the 5 degraded chunks came from the same 3 source documents as the snapshot (only `ee885b59` is genuinely new). Example: chunk `_20` from document `bf9908ef` was sunk and replaced by chunk `_58` from the same document `bf9908ef`.

This is intra-document segment shuffling: displacing the optimal segment of a guideline promotes a neighbouring segment from the same guideline. Because adjacent segments of a clinical guideline are topically identical, a topical-relevance metric (`context_precision`) cannot distinguish the corruption from a clean retrieval. The retrieval set looks different at the chunk level while being nearly identical at the document level.

**Implication:** `context_precision` of 1.000 does not prove the intended chunks were retrieved. It proves the retrieved set was topically relevant. When the corpus has on-topic redundancy within source documents, embedding corruption can produce correct precision scores from a corrupted retrieval set. A chunk_id stability check — not a RAGAS metric — is required to detect this failure class.

### Finding 3 — faithfulness=1.0 confirmed as judge leniency (closes P8-5)

Q_P7 generated answer: *"the recommended HbA1c target is 53 mmol/mol (7.0%). If HbA1c levels are not adequately controlled and rise to 58 mmol/mol (7.5%) or higher, a third agent should be added to intensify treatment."*

The 5 retrieved chunks at the time of scoring (post-restore, P8 conditions reconstructed):

| Chunk | Similarity | Content |
|---|---|---|
| 1 | 0.670 | HbA1c monitoring *frequency* and IFCC calibration [NG28] |
| 2 | 0.596 | Relaxing targets for older/frailer patients [NG28] — nearest keyword: *"intensive management would not be appropriate"* |
| 3 | 0.573 | Tirzepatide pricing [TA924] |
| 4 | 0.571 | Insulin adverse-event scenarios [NG28] |
| 5 | 0.565 | Insulin initiation guidance [NG28] |

Neither the 53/58 mmol/mol thresholds nor the dual→third-agent escalation logic appears in any retrieved chunk. The answer's numbers are real NICE values but came from GPT-4o's parametric knowledge, not the retrieved context. The clinical bridge was fabricated. The nearest keyword match (Chunk 2: "intensive management would not be appropriate") argues the opposite of the answer's claim. The RAGAS judge (GPT-4o) scored faithfulness=1.0 against this context.

**Note on P7 consistency:** P7's finding was "numbers grounded in NG28, clinical logic fabricated." In this run, neither the numbers nor the bridge was grounded in the retrieved context. Both findings are true: retrieval is query- and index-state-dependent, and the top-5 chunks differ across runs. In P7 a monitoring-threshold chunk happened to be retrieved; in this run it was not. The fabricated bridge is consistent across both runs; the grounding of the numbers is run-dependent.

**Mechanism (extends P8-4 to faithfulness):** when judge and generator are the same model, the judge rewards the generator's plausible parametric output regardless of whether the retrieved context supports it. P8-4 documented this for recall; P8-5 confirms it extends to faithfulness.

**Interview-grade finding:** faithfulness measures grounding-in-context, not truth. This answer is arguably correct in the real world, yet faithfulness=1.0 is a judge error — the context licenses neither the numbers nor the clinical bridge. The metric alone is insufficient; reading the context is the only reliable check when judge = generator. This project demonstrated the failure mode it was built to catch.

**Evidence:** `p10_6_qp7_context_read.png`.

### Finding 4 — Recovery demonstrated, not asserted

Aggregate `context_precision` returned to exactly 0.500 in the recovery eval run. Q2 restored to 1.000. The precision-return is the primary proof: a no-op restore would leave precision at 0.425, and 0.500 exact is not coincidence. Recovery is an observed fact.

**Evidence:** `p10_4_recovered_eval.png`.

---

## Root Cause

The `upsert_chunks` path has no model-version column. Any write to an existing `chunk_id` silently replaces the embedding regardless of which model produced it. The schema records *when* the index was last written; it does not record *which model* wrote it. These are different pieces of information, and only the second detects this failure class.

---

## Resolution

Index restored to `text-embedding-3-small` embeddings. Recovery confirmed by precision returning to 0.500. `text-embedding-ada-002` Azure OpenAI deployment deleted.

---

## Recommendations

1. **Add `model_version` column to `guideline_embeddings`.** Any upsert should record which embedding model produced the row. A (`embedded_at`, `model_version`) pair answers both "when was it written?" and "which model wrote it?" — the two questions the freshness alert currently collapses into one.

2. **Pin the embedding deployment name in the embed pipeline.** `embed.py` reads `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` from the environment. A misconfigured or rotated environment variable silently produces a valid-dimensionality vector from a different model with no error. The deployment name should be explicit in the pipeline config and validated at startup.

3. **Add a chunk_id stability check to the eval harness.** `context_precision` cannot detect intra-document segment shuffling when the corpus has on-topic redundancy (Finding 2). Comparing retrieved chunk_ids to a reference set from the prior eval run would catch Q3a-class silent replacements that RAGAS scores cannot surface. This check costs a single set intersection per question per run.

4. **Eval gate is load-bearing; treat it as such.** Freshness monitoring and the RAGAS eval gate answer different questions. Neither substitutes for the other, and even together they do not catch all corruption classes (Finding 2). The eval gate should run on every embedding pipeline execution.

---

## Evidence Artifacts

| File | Contents |
|---|---|
| `evidence/p10_1_degraded_eval.png` | Degraded eval table: Q2 1.000→0.700, aggregate 0.500→0.425 (from run `213501Z`; identical scores confirmed in `155955Z`) |
| `evidence/p10_2_q3a_blindness.png` | Q3a chunk_id comparison: 0/5 chunk overlap, 4/5 document overlap — intra-document shuffling |
| `evidence/p10_3_degraded_report.png` | Observability report (degraded): Panel 1 −0.075 + Panel 3 Freshness OK 0.2d TTL=7d (headline artifact) |
| `evidence/p10_4_recovered_eval.png` | Recovery eval: precision returned to 0.500, Q2 restored to 1.000 |
| `evidence/p10_5_recovered_report.png` | Observability report (recovered): Panel 1 restored + Panel 3 still FRESH 0.0d TTL=7d |
| `evidence/p10_6_qp7_context_read.png` | Q_P7 answer + retrieved chunks: faithfulness=1.0 is judge leniency, no grounding in context |
| `data/ragas_scores/baseline_20260607T004856Z.csv` | P8 baseline (before) |
| `data/ragas_scores/baseline_20260612T155955Z.csv` | Degraded scores — first degraded run |
| `data/ragas_scores/baseline_20260612T213501Z.csv` | Degraded scores — second degraded run (matches `155955Z` exactly: 0.425 aggregate) |
| `data/ragas_scores/baseline_20260612T222754Z.csv` | Recovery scores (after restore) |
