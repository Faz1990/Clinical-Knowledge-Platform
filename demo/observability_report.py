"""P9 local observability report — RAGAS precision trend + index freshness.

Local-dev equivalent of notebooks/observability/01_retrieval_dashboard.py.
Scope: this script covers panels that have a local data source:
  Panel 1 — context_precision trend  (reads data/ragas_scores/baseline_*.csv)
  Panel 2 — trust-labelled metrics   (recall + faithfulness from same CSVs; upper-bound labelled)
  Panel 3 — freshness alert          (queries pgvector MAX(embedded_at))

Latency and retrieval_mean_similarity trend are Databricks-only: they live in
clinical_platform.gold.retrieval_telemetry, written by the DAG's run_ragas_eval
task. See notebooks/observability/01_retrieval_dashboard.py for those panels.

Each eval.run(save_csv=True) appends a NEW baseline_<ts>.csv — the trend grows
over time. With one file (P8 baseline), Panel 1 shows a single reference point;
the delta column becomes meaningful once a second run lands.

Usage:
    python demo/observability_report.py

Requires .env with PGVECTOR_* vars. Set FRESHNESS_TTL_DAYS to override default (7).
Demo a tripped alert: FRESHNESS_TTL_DAYS=1 (index was last built ~2 days ago).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from clinical_platform.telemetry import get_index_built_ts  # noqa: E402

SCORES_DIR = _REPO_ROOT / "data" / "ragas_scores"
FRESHNESS_TTL_DAYS = int(os.environ.get("FRESHNESS_TTL_DAYS", "7"))

_P8_BASELINE = {
    "context_precision": 0.500,
    "context_recall": 0.917,
    "faithfulness": 0.867,
    "answer_relevancy": 0.900,
}

_SEP = "-" * 73


def _load_runs() -> list[dict]:
    """Read all RAGAS CSV files sorted by filename (chronological by timestamp suffix)."""
    import pandas as pd

    csv_files = sorted(SCORES_DIR.glob("baseline_*.csv"))
    if not csv_files:
        return []

    runs = []
    for path in csv_files:
        df = pd.read_csv(path)
        ts_str = path.stem.replace("baseline_", "")
        runs.append({
            "run_ts": ts_str,
            "n": len(df),
            "context_precision": df["context_precision"].mean() if "context_precision" in df.columns else None,
            "context_recall": df["context_recall"].mean() if "context_recall" in df.columns else None,
            "faithfulness": df["faithfulness"].mean() if "faithfulness" in df.columns else None,
            "answer_relevancy": df["answer_relevancy"].mean() if "answer_relevancy" in df.columns else None,
        })
    return runs


def _fmt(v) -> str:
    return f"{v:.3f}" if v is not None else "  n/a"


def _print_precision_trend(runs: list[dict]) -> None:
    print(f"\n-- Panel 1: context_precision trend (primary validated signal) {'-'*8}")
    print(f"  {'Timestamp (UTC)':23s}  {'precision':>9}  {'vs baseline':>11}  {'n':>3}")
    print(f"  {'-'*23}  {'-'*9}  {'-'*11}  {'-'*3}")
    baseline = _P8_BASELINE["context_precision"]
    for r in runs:
        p = r["context_precision"]
        delta = f"{round(p - baseline, 3):+.3f}".replace("-0.000", "+0.000") if p is not None else "      n/a"
        print(f"  {r['run_ts']:23s}  {_fmt(p):>9}  {delta:>11}  {r['n']:>3}")
    if len(runs) == 1:
        print("  (single baseline point — delta 0 is expected; trend grows on next eval run)")
    print()


def _print_trust_labelled_metrics(runs: list[dict]) -> None:
    print(f"-- Panel 2: trust-labelled metrics (upper bounds per P8-4/P8-5) {'-'*8}")
    print(f"  {'Timestamp (UTC)':23s}  {'recall*':>7}  {'faithfulness*':>13}  {'ans_rel':>7}")
    print(f"  {'-'*23}  {'-'*7}  {'-'*13}  {'-'*7}")
    for r in runs:
        print(
            f"  {r['run_ts']:23s}  {_fmt(r['context_recall']):>7}  "
            f"{_fmt(r['faithfulness']):>13}  {_fmt(r['answer_relevancy']):>7}"
        )
    print("  * Upper bound: same-model judge inflation (P8-4). faithfulness=1.0 on Q_P7 is")
    print("    not independent evidence of grounding — a same-model judge would pass a")
    print("    fabricated answer too (P8-5 closed 2026-06-12: retrieved chunks contained no")
    print("    grounding for the answer's claims — confirmed judge leniency).")
    print("    Precision is the validated signal. See docs/p10_postmortem.md §Finding 3.\n")


def _print_freshness() -> None:
    print(f"-- Panel 3: Index freshness {'-'*46}")
    try:
        index_built_ts = get_index_built_ts()
    except Exception as exc:
        print(f"  ERROR: could not reach pgvector — {exc}")
        print("  Is the container running?  docker-compose up -d\n")
        return

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_days = (now - index_built_ts).total_seconds() / 86400

    if index_built_ts == epoch:
        print("  [FRESHNESS ALERT] Index has never been built (guideline_embeddings is empty).")
        print(f"  Age: unbuilt  |  TTL: {FRESHNESS_TTL_DAYS}d  |  Status: TRIPPED")
    elif age_days > FRESHNESS_TTL_DAYS:
        print(f"  [FRESHNESS ALERT] Index is {age_days:.1f}d old (TTL={FRESHNESS_TTL_DAYS}d).")
        print(f"  Last built : {index_built_ts.isoformat()}")
        print(f"  Status     : TRIPPED — run embed_chunks to re-index.")
    else:
        print(f"  [Freshness OK] Index is {age_days:.1f}d old (TTL={FRESHNESS_TTL_DAYS}d).")
        print(f"  Last built : {index_built_ts.isoformat()}")
    print()


def main() -> None:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("=" * 73)
    print("  Clinical Knowledge Platform — Retrieval Observability Report")
    print(f"  {now_str}")
    print("  Local view: precision trend + freshness.")
    print("  Full telemetry (latency, retrieval_mean_similarity): see")
    print("  notebooks/observability/01_retrieval_dashboard.py (Databricks)")
    print("=" * 73)

    runs = _load_runs()
    if not runs:
        print(f"\n  No RAGAS score files found in {SCORES_DIR}")
        print("  Run: python -m clinical_platform.eval\n")
    else:
        _print_precision_trend(runs)
        _print_trust_labelled_metrics(runs)

    _print_freshness()

    print(f"-- P8 baseline reference {'-'*49}")
    print(f"  context_precision  {_P8_BASELINE['context_precision']:.3f}  (validated; primary signal)")
    print(f"  context_recall     {_P8_BASELINE['context_recall']:.3f}  (upper bound)")
    print(f"  faithfulness       {_P8_BASELINE['faithfulness']:.3f}  (upper bound)")
    print(f"  answer_relevancy   {_P8_BASELINE['answer_relevancy']:.3f}")
    print("=" * 73)


if __name__ == "__main__":
    main()
