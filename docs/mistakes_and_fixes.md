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

### Global git ignore (Windows) is invisible to WSL git (P6)
`.claude/` and `CLAUDE.md` were excluded via `core.excludesFile` in the Windows git global config. WSL git is a separate install with its own `~/.gitconfig` — it has no knowledge of the Windows global exclude. Files ignored in PowerShell were re-staged by WSL `git add .`.
**Fix:** `.git/info/exclude` lives inside the repo's `.git/` folder, shared by both shells on disk. Add exclusions there, not to a global config. Works in PowerShell and WSL identically, never pushed.
**Rule:** global git config is per-install. Repo-local `.git/info/exclude` is per-repo and shell-agnostic.
