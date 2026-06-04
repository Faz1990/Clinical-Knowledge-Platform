# Mistakes and Fixes — Clinical Knowledge Platform

**Purpose:** surface recurring failure patterns and the process rules that prevent them.
Not a changelog — skip trivia. Only log mistakes that carry a transferable lesson or reveal a root cause that explains multiple errors. Cross-reference study guides rather than repeating their concept lessons.

**Backfill note:** P1–P4 entries are sparse because this file was started mid-P6. Add genuine P1–P4 mistakes here when reviewing those study guides — only entries that fit an existing pattern or reveal a new one.

---

## Pattern 1: Verify State Before Planning

**Root cause behind:** M-vfy-1, M-vfy-2, M-vfy-3, M-vfy-4.

**The failure mode:** write a plan that references a file, tool, or system — then discover mid-execution the assumed state was wrong. The plan breaks, backtracking costs time, and in a live interview the stumble is visible.

**Process rule:** before writing a plan or a line of code that touches a file or system, *read that file or system first.* Read `requirements.txt` before adding a package. Glob the directory before referencing a path. Check the installed version before relying on a feature. Read the full module docstring before assuming one code path exists.

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
**Rule applied:** `pip show <package>` before referencing version-specific behaviour.

### M-vfy-4 — Didn't read the DAG before assuming one auth path (P5 → P6)
Planned the MSAL swap as if there was one token path in the DAG. There are two: `get_databricks_token()` (dbt subprocess) and `databricks_default` connection (Databricks operators). The DAG module docstring at line 1 documents both paths and the P6 TODO explicitly — reading it first would have caught this before writing the plan.
**Rule applied:** read the full module — especially its docstring — before planning changes to it.

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
**Correction:** see `docs/project_state.md` → "Env-Var Naming — Three Contexts, Explicit Mapping." CD workflow YAML explicitly maps `secrets.AZURE_*` → `env.ARM_*`.
**Impact if uncorrected:** `databricks bundle deploy` authenticates with nothing; 401 with no obvious diagnostic.

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
