# Mistakes and Fixes — Clinical Knowledge Platform

**Purpose:** surface recurring failure patterns and the process rules that prevent them.
Not a changelog — skip trivia. Only log mistakes that carry a transferable lesson or reveal a root cause that explains multiple errors. Cross-reference study guides rather than repeating their concept lessons.

**Backfill note:** P1–P4 entries are sparse because this file was started mid-P6. Add genuine P1–P4 mistakes here when reviewing those study guides — only entries that fit an existing pattern or reveal a new one.

---

## Pattern 1: Verify State Before Planning

**Root cause behind:** M-vfy-1, M-vfy-2, M-vfy-3, M-vfy-4, M-vfy-5, M-vfy-6.

**The failure mode:** write a plan that references a file, tool, or system — then discover mid-execution the assumed state was wrong. The plan breaks, backtracking costs time, and in a live interview the stumble is visible.

**Process rule:** before writing a plan or a line of code that touches a file or system, *read that file or system first.* Read `requirements.txt` before adding a package. Glob the directory before referencing a path. Check the installed version before relying on a feature. Read the full module docstring before assuming one code path exists. Look up syntax before writing it.

### M-vfy-1 — Didn't check directories before referencing paths (P6)
Referred to `.github/workflows/ci.yml` and `docs/` as if both existed. Neither did.
`Glob(".github/**/*")` returned empty; `Test-Path docs` returned False.
**Rule applied:** glob or `Test-Path` a directory before referencing it in a plan.

### M-vfy-2 — Didn't read `requirements-dev.txt` before planning an install (P6)
Planned to use `msal` in the DAG without checking whether it was already present.
It wasn't — `requirements-dev.txt` had `pytest`, `ruff`, `black`, `pdfplumber` only.
**Rule applied:** read requirements files before listing what needs to be added.

### M-vfy-3 — Didn't check provider version before relying on its API (P6)
Planned the `databricks_default` connection `extra` field names without confirming which Databricks Airflow provider version was installed. Provider is unpinned in `requirements-airflow.txt`; extra field names (`client_id` vs `azure_client_id`) are unknown until verified against the installed version.
**Rule applied:** `pip show <package>` before referencing version-specific behaviour. (Resolved: 6.7.0, fields `azure_tenant_id`, `azure_client_id`, `azure_client_secret`.)

### M-vfy-4 — Didn't read the DAG before assuming one auth path (P5 → P6)
Planned the MSAL swap as if there was one token path in the DAG. There are two: `get_databricks_token()` (dbt subprocess) and `databricks_default` connection (Databricks operators). The DAG module docstring at line 1 documents both paths and the P6 TODO explicitly — reading it first would have caught this before writing the plan.
**Rule applied:** read the full module — especially its docstring — before planning changes to it.

### M-vfy-5 — Wrote `SHOW GRANTS TO` — `TO` is not valid syntax (P6)
Wrote `SHOW GRANTS TO \`uuid\` ON CATALOG ...` in the UC grants notebook. The `GRANT` statement uses `TO`; `SHOW GRANTS` does not — correct syntax is `SHOW GRANTS \`uuid\` ON <securable>`. Only the `SHOW GRANTS` cells errored; the `GRANT` cells succeeded, which proved the UUID format was fine — switching to display name (the assumed fallback) would have changed the wrong thing and still failed.
**Rule applied:** look up SQL syntax before writing it. Read the error evidence before reaching for a fallback.

### M-vfy-6 — Declared an empty `resources:` key in YAML (P6)
`databricks.yml` had `resources:` with comments underneath but no actual content. YAML parser sees a nil map and errors: `expected a map at "resources", found nil`. If a key has nothing under it, don't declare it.
**Rule applied:** verify spec/schema before writing config files with optional blocks.

### M-vfy-7 — Positional join without alignment guard (P9)
`eval.py` built `perf_records` in the loop and planned to merge with `scores.to_pandas()` on the `question` column. A string merge silently misattributes precision to the wrong question if any question string appears twice or if RAGAS reorders rows. Both DataFrames are built from the same loop in the same order, and `Dataset.from_dict` preserves that order — so positional concat is correct. But the alignment assumption was implicit, not verified.
**Fix:** positional `pd.concat([perf_df.reset_index(drop=True), ragas_df[cols].reset_index(drop=True)], axis=1)` with `assert len(ragas_df) == len(perf_records)` to catch any future divergence.
**Rule applied:** when two structures must align positionally, assert the invariant explicitly rather than relying on order preservation being documented elsewhere.

---

## Pattern 2: Partial Fix Claimed as Complete

### M-partial-1 — MSAL swap closes dbt path only, not operator path (P6)
Initial P6 auth plan described the MSAL swap as closing "the token-expiry scar" without acknowledging it only fixes one of two paths. `DatabricksSubmitRunOperator` uses `databricks_default`, set once at Airflow startup with a personal token that can expire on long runs. The MSAL swap in `get_databricks_token()` does not touch this connection.
**Correction:** two explicit steps: (1) MSAL in `get_databricks_token()` for dbt, (2) configure `databricks_default` to use the SP via provider `extra` fields for automatic token refresh.
**Interview framing:** "The auth had two paths; I closed the dbt one with MSAL and the operator one by configuring the Databricks Airflow provider's built-in SP refresh — here's how they differ."
**Root cause:** connected to M-vfy-4 — the two paths weren't visible because the DAG wasn't read first.

---

## Pattern 3: Inconsistent Naming Across Tool Boundaries

### M-naming-1 — AZURE_* vs ARM_* env vars for the same SP credentials (P6)
Used `AZURE_CLIENT_ID/SECRET/TENANT` throughout the initial CD plan without checking what the Databricks CLI actually reads. The CLI (Go, 0.200+) uses `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID` for Azure SP auth. MSAL code reads `AZURE_*`. GitHub secrets are named `AZURE_*`. Three tools, three conventions, same credentials.
**Correction:** CD workflow YAML explicitly maps `secrets.AZURE_*` → `env.ARM_*`.
**Impact if uncorrected:** `databricks bundle deploy` authenticates with nothing; 401 with no obvious diagnostic.

### M-naming-2 — Bash heredoc syntax in a PowerShell commit (P6)
Used `$(cat <<'EOF' ... EOF)` for a multi-line git commit message in PowerShell. PowerShell has no heredoc — `<<` is a redirection operator and the command fails immediately. The fix is multiple `-m` flags (git joins them with blank lines), which is portable and unambiguous in PowerShell.
**Rule applied:** know which shell the command runs in before writing its syntax. PowerShell ≠ bash. All git for this project runs in PowerShell; use PowerShell idioms.

---

## Pattern 4: Counting from Memory Instead of Artifact

### M-count-1 — dbt test count stated as 27, actual is 25 (P6 draft)
Wrote "27/27 dbt tests pass" without checking the build output.
**Correction:** `dbt/target/run_results.json` (run 2026-06-02) has exactly 25 entries, all `status: pass`. Every document that states a test count — CV, study guide, evidence captions, docs — must say **25/25**.
**Why it matters:** a number that disagrees across your own documents signals to an interviewer that you didn't run it yourself.
**Check:** `python -c "import json; r=json.load(open('dbt/target/run_results.json')); print(len(r['results']))"` → 25.

---

## Significant One-Off Lessons

### Secret exposure and rotation (P6 setup)
SP client secret appeared in a screenshot of `az ad sp create-for-rbac` output.
**Fix:** rotated immediately via `az ad app credential reset`. New secret lives only in Key Vault `kv-clinpl-dev` (`databricks-cicd-sp-secret`) and gitignored local `.env`.
**Rule:** never screenshot, paste into chat, or log a secret. If it touches a screen in a shareable context: rotate before anything else.

### Azure RBAC ≠ Unity Catalog (first surfaced P2, resurfaces every phase with a new SP or identity)
Contributor RBAC on the resource group grants control-plane access only. Unity Catalog is a separate permission system. RBAC does not flow into UC. Any identity — user or SP — that needs to query tables requires explicit UC `GRANT` statements run by a metastore admin.
This is why the P6 SP has Contributor RBAC and can call the Databricks REST API, but cannot read a single table until `notebooks/admin/00_grant_sp_permissions.sql` is run.
**Study guide reference:** P2 guide covers the full RBAC/UC distinction — don't duplicate here.

### `CREATE VIEW` is not grantable on a schema in UC 1.0 (P6)
Attempted `GRANT CREATE VIEW ON SCHEMA clinical_platform.gold`. UC metastore v1.0 returns `PRIVILEGE_NOT_APPLICABLE_TO_ENTITY` — `CREATE VIEW` is not a valid schema-level privilege; it is implicitly covered by `CREATE TABLE`. Removing the line and relying on `CREATE TABLE` is sufficient.
**Rule:** when a GRANT fails with `PRIVILEGE_NOT_APPLICABLE_TO_ENTITY`, the privilege doesn't exist at that securable level — check the UC privilege model for the object type before writing grants.

### Precision is more reliable than recall when judge = generator (P8)
In a RAGAS eval where GPT-4o both generates answers and judges them, recall is inflated by the same leniency that causes hallucinations — the judge over-credits paraphrases it would itself produce. In the P8 baseline: Q_P7 recall = 1.0 despite retrieval surfacing the wrong clinical scenario; Q_P7 faithfulness = 1.0 despite the answer containing the fabricated "third agent" bridge. Precision (rank-weighted AP, confirmed by interleaved test) scored correctly: 0.0 for clinical-vocab questions, 1.0 for guideline-vocab. **Rule:** when judge = generator, treat recall magnitudes as upper bounds and precision as the primary signal. Always read the generated answer directly — the metric alone is insufficient.

### Unverified mechanism asserted as explanation (P8, recurring pattern)
Three times in P8, an explanation was asserted without reading the source: (1) "almost certainly in chunk 9 or 10" for the first-line recommendation — required reading the actual chunk to confirm; (2) "garbled diagram/flowchart content" — PDF showed it was a bold-heading double-render, not a diagram; (3) "RAGAS joins contexts internally, need 0.2.x migration" — killed by a 5-minute interleaved AP test returning the exact closed-form value. All three were plausible inferences that a single observation disproved.
**Rule:** "almost certainly," "likely," and "probably" are signals to run the confirming check before writing the claim. A wrong confident explanation is worse than acknowledging uncertainty.

### Ground truth must be authored from observed chunk text, not recalled knowledge (P8)
Initial Q3a/Q3b ground truth included a conditional ("if DPP-4 not suitable → SU/pio/insulin") that stitched two separate chunks without verifying the conditional was verbatim in either. The conditional turned out to be real (PDF pages 104–105 confirm the tiering), but the process was wrong — a plausible bridge was asserted before it was observed.
**Rule:** every claim in a ground-truth reference answer must be traceable to a specific retrieved chunk. If the phrasing stitches two chunks, read both chunks and verify the linking conditional exists verbatim before writing it as ground truth.

---

## Pattern 5: Observability Code Needs the Same Correctness Discipline as the Pipeline It Monitors

**Root cause behind:** M-obs-1, M-obs-2, M-obs-3, M-obs-4.

**The failure mode:** telemetry and alerting code written quickly, without applying the same idempotency, boundary-condition, and signal-validity checks used for the pipeline itself. Result: the observability layer becomes its own source of silent corruption — duplicate rows skew the trend, a wrong fallback makes the alert blind to its worst case, truncated math fires late, and a log line masquerades as a gate.

**Process rule:** treat telemetry writes as Delta ingestion (idempotency), treat alert boundaries as contract conditions (verify the math), and treat the alert output as a proof artifact (it must be visible and unambiguous).

### M-obs-1 — `INSERT INTO` with no key → duplicates on Airflow retry (P9)
Initial `write_eval_telemetry` used a per-row `INSERT INTO` loop with no deduplication. An Airflow retry (or a mid-loop crash followed by retry) would write duplicate rows for the same `eval_run_id`, skewing every aggregate computed from the table. The trend P10 depends on would be wrong from the first retry.
**Fix:** DELETE WHERE eval_run_id = X, then single multi-row INSERT. Same discipline as Bronze MERGE — idempotency is not optional for append-only tables.
**Consequence if missed:** the degradation curve in P10 double-counts retried runs; the postmortem's "before" baseline is inflated.

### M-obs-2 — `get_index_built_ts()` returned `now()` when table is empty (P9)
Initial fallback: `if result is None: return datetime.now(timezone.utc)`. An unbuilt index reads as *perfectly fresh* — the one state where the freshness alert most needs to fire, it silently passes.
**Fix:** return epoch `datetime(1970, 1, 1, tzinfo=timezone.utc)`. Age = now() − epoch → always exceeds any reasonable TTL.
**Rule:** a "no data" fallback for an alert signal should be the worst-case value, not the neutral one.

### M-obs-3 — `timedelta.days` floors to integer; alert fires up to ~24h late (P9)
`age_days = (now - index_built_ts).days` — `.days` is the integer floor of the timedelta. An index 7d 21h old with TTL=7: `age_days=7`, `7 > 7` is False → no trip. For the feature whose entire purpose is detecting staleness, firing a day late is a correctness defect.
**Fix:** `(now - index_built_ts).total_seconds() / 86400` gives exact fractional days. Boundary is precise; format with `{:.1f}`.
**Rule:** use `total_seconds()` for any timedelta boundary comparison; `.days` is for display, not logic.

### M-obs-4 — Print-only alert is a log line, not a gate (P9)
Initial `_publish_metrics` printed a message on freshness trip. A `print()` is buried in stdout; nothing in the Airflow UI signals failure; the "automated gate" narrative is undermined by the demo being "I ran a log grep."
**Fix:** `raise AirflowException(...)` so the task goes red in the Airflow UI. The proof artifact is a failed task, not a grepped log line.
**Rule:** an alert that doesn't cause an observable failure state in the system it monitors is documentation, not observability.

---

## Pattern 6: Open Items Asserted as Settled in Proof Artifacts

### M-assert-1 — Footnote stated unverified outcome as fact (P9)
The `demo/observability_report.py` footnote originally read: "faithfulness=1.0 for Q_P7 despite fabricated clinical logic (P8-5)." But P8-5's status was explicitly **open**: "confirm by reading the generated answer." The note asserted an unverified outcome (judge missed a fabrication) as settled, in the wrong direction, in a screenshot to be shown in an interview.
**Correction:** "faithfulness=1.0 on Q_P7 is not independent evidence of grounding — a same-model judge would pass a fabricated answer too (P8-5, open; confirm by reading the generated answer). Precision is the validated signal."
**Why it matters:** stating an open item as settled invites the interviewer to ask "how do you know it fabricated?" — a question you cannot yet answer. Stating it as open and explaining *why the score can't distinguish the two cases* is actually the stronger line.
**Rule:** in any screenshot or artifact you will present: open items are open, not settled. The distinction between "I don't trust this score and here's why" vs "this score is wrong" is the difference between demonstrated rigour and an unsupported claim.

### Global git ignore (Windows) is invisible to WSL git (P6)
`.claude/` and `CLAUDE.md` were excluded via `core.excludesFile` in the Windows git global config. WSL git is a separate install with its own `~/.gitconfig` — it has no knowledge of the Windows global exclude. Files ignored in PowerShell were re-staged by WSL `git add .`.
**Fix:** `.git/info/exclude` lives inside the repo's `.git/` folder, shared by both shells on disk. Add exclusions there, not to a global config. Works in PowerShell and WSL identically, never pushed.
**Rule:** global git config is per-install. Repo-local `.git/info/exclude` is per-repo and shell-agnostic.
