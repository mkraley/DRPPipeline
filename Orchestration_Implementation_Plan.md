# Orchestration Implementation Plan

Based on `.cursorrules`, `Thoughts on restructuring.txt`, and the current codebase.

**Revisions:** Consolidate `sourcing_num_rows` -> `num_rows`; replace status-accumulation with `warnings`/`errors`; only set DB `status` at module completion on success; central orchestrator iterates DB, finds eligible projects, and calls each module with the full project row (or DRPID).

---

## 1. Summary of Requirements (from Thoughts)

- **First required CLI param**: module name (e.g. `sourcing`, `collectors`)
- **Run one module at a time** on a batch of projects
- **Status field**: last successfully completed module name — **set only at module completion on success**; never append to DB `status`
- **On success**: orchestrator sets `status = module_name` and may append module-returned messages to `warnings`
- **On error**: orchestrator appends to `errors`; project is **not eligible** for further processing
- **Eligibility**: `status == prereq` and **no** `errors` (warnings allowed)
- **Central orchestrator**: iterates the database, finds eligible projects, calls the module with **the full project row** (or DRPID). **Modules do not** call `list_eligible_projects` or observe `num_rows`; only the orchestrator does.
- **num_rows**: replaces `sourcing_num_rows`. Used only by the orchestrator: for Sourcing, passed as `run(limit=num_rows)`; for DB-fed modules, `list_eligible_projects(prereq, num_rows)`.
- **Module list & prereqs**: in main/orchestration. Sourcing has no prereq; Collectors has prereq `sourcing`

---

## 2. Components to Add or Change

### 2.1 Args (utils/Args.py)

| Change | Description |
|--------|-------------|
| **`module`** (required) | First/required CLI param: `sourcing`, `collectors`, etc. `typer.Argument`. |
| **`num_rows`** | General batch limit. `None` = unlimited. **Replace `sourcing_num_rows`** everywhere (Args, SpreadsheetCandidateFetcher, Sourcing, tests). |
| **`db_path`** | Optional. Path to SQLite DB. Default e.g. `drp_pipeline.db` in cwd. |
| **`storage_implementation`** | Optional; default `StorageSQLLite`. For `Storage.initialize()`. |

**CLI shape (Typer):** Root callback: `--config`, `--log-level`, `--num-rows`, `--db-path`, `--storage`; **required positional** `module`.

**Remove:** `sourcing_num_rows` from `_defaults` and all references. Orchestrator passes `num_rows` into `Sourcing.run(limit=num_rows)`; Sourcing passes `limit` to the fetcher. Only the orchestrator reads `num_rows` for orchestration; Sourcing uses the `limit` argument.

---

### 2.2 Storage: New Method (orchestrator only)

**`list_eligible_projects(prereq_status: str | None, limit: int | None) -> list[dict]`**

- **When `prereq_status` is not None** (e.g. `"sourcing"` for Collectors):
  - `WHERE status = ? AND (errors IS NULL OR errors = '')`
  - `ORDER BY DRPID ASC`
  - `LIMIT ?` if `limit` is not None
  - Return **full row dicts** (all columns) so the orchestrator can pass the entire row to `run_one(project)`.
- **When `prereq_status` is None**: return `[]` (Sourcing does not get its input from the DB).

**Only the orchestrator** calls this. Modules never call `list_eligible_projects` or `num_rows`. Add to `StorageProtocol` and `StorageSQLLite`; use `commit=False` for the SELECT.

---

### 2.3 Storage: Append for `warnings` / `errors`

**`append_to_field(drpid, field: Literal["warnings","errors"], text: str)`** — read current value, append `text`, `update_record`. Add to `StorageProtocol` and `StorageSQLLite`. **Format:** one entry per line (newline) — pick one and document.

---

### 2.4 Status, Warnings, and Errors (replace status-accumulation)

- **DB `status`**: Set **only once at module completion when the module succeeds**. Never append. The **orchestrator** does `update_record(drpid, {"status": module_name, ...})` on success only.
- **Replace status-accumulation in modules** with `warnings` and `errors`:
  - In **SocrataCollector**, **SocrataPageProcessor**, **SocrataDatasetDownloader**: replace `_update_status(msg)` and `_result['status']` with `_add_error(msg)` and `_add_warning(msg)` that append to `_result['errors']` and `_result['warnings']`.
  - **Errors**: conditions that mean the project failed (Invalid URL, Export button not found, PDF generation failed, timeout, etc.) -> `_add_error`. Orchestrator appends each to DB `errors`.
  - **Warnings**: recoverable or non-fatal (Large dataset warning - download skipped, etc.) -> `_add_warning`. Orchestrator appends each to DB `warnings`.
  - **Success/info** (e.g. "PDF generated", "Dataset downloaded"): keep as logs only; do not write to DB. DB `status` is set to the module name on success; no additional success text in `status`.
- **Module result:** Collector returns `errors: list[str]`, `warnings: list[str]`, plus `pdf_path`, `dataset_path`, `metadata`, etc. The orchestrator appends `errors`/`warnings` to the DB via `append_to_field`; on success it sets `status` and `updates` (folder_path, title, ...).

---

### 2.5 Module Registry and Interfaces (orchestrator-centric)

**Registry (e.g. in `orchestration/`):**

```python
MODULES = {
    "sourcing": {
        "prereq": None,
        "run": lambda storage, num_rows: Sourcing(storage).run(limit=num_rows),
    },
    "collectors": {
        "prereq": "sourcing",
        "run_one": collectors_run_one,  # (project: dict) -> ModuleResult
    },
}
```

- **Sourcing** (`prereq is None`): orchestrator calls `MODULES["sourcing"]["run"](storage, num_rows)` **once**. No `list_eligible_projects`. Sourcing receives `limit` via `run(limit=num_rows)` and passes it to the fetcher; it does not read `num_rows` or call `list_eligible_projects`. Sourcing creates records and, **on each successful creation**, sets `status="sourcing"` (the only "update on success at module completion" for that row).
- **DB-fed modules** (e.g. Collectors): orchestrator does: (1) `projects = storage.list_eligible_projects(prereq, num_rows)`; (2) `for project in projects: result = MODULES[module]["run_one"](project);` then apply `result` (update or append).

**Module contracts:**

- **`run(storage, num_rows)`** for Sourcing: `Sourcing.run(limit=num_rows)`. Uses `limit` when obtaining candidate URLs (passes `limit` to the fetcher). Creates records and sets `status="sourcing"` on each.
- **`run_one(project: dict) -> ModuleResult`** for Collectors: receives the **entire DB row** (dict). Does **not** call `list_eligible_projects` or `num_rows`. Returns `ModuleResult(success=bool, errors=list[str], warnings=list[str], updates=dict)`. Orchestrator: on success -> `update_record(drpid, {status: module_name, **result.updates})` and append `result.warnings` to DB; on failure -> append each `result.errors` to DB; on exception -> append `str(e)` to DB and continue.

---

### 2.6 Sourcing Adjustments

- **`Sourcing.run(limit: int | None) -> None`**: `limit` comes from the orchestrator (replaces `sourcing_num_rows`). Pass `limit` into the fetcher (or `get_candidate_urls(limit)`).
- Obtain candidates (with `limit`). For each URL: `process_candidate(url)`. When a record is **created**, set `status = "sourcing"` via `update_record(drpid, {"status": "sourcing"})`. No DB iteration; no `list_eligible_projects`.

---

### 2.7 Collectors: `run_one(project) -> ModuleResult`

- **`collectors_run_one(project: dict) -> ModuleResult`**: uses `SocrataCollector.collect(project["source_url"], project["DRPID"])`. Map collector return dict to `ModuleResult`:
  - `success = bool(result.get("pdf_path") or result.get("dataset_path"))`
  - `errors = result.get("errors", [])`
  - `warnings = result.get("warnings", [])`
  - `updates = {folder_path: ..., title: result["metadata"].get("title"), ...}` (orchestrator can derive `folder_path` from `Args.base_output_dir` and `project["DRPID"]`).
- **SocrataCollector (and subcomponents)**: replace `_update_status` / `_result['status']` with `_add_error` / `_add_warning`; `collect()` returns `errors` and `warnings` and drops the accumulated `status` string for DB purposes.

---

### 2.8 Main `run()` / Orchestration Flow (central orchestrator)

**Orchestrator** (e.g. `orchestration/Orchestrator.py`):

1. **Resolve module** from `MODULES`; if missing, fail with list of valid names.
2. **Storage** `storage = Storage.initialize(..., db_path=Args.db_path)`.
3. **`num_rows = Args.num_rows`** (only place that reads `num_rows` for orchestration).
4. **Branch:**
   - **If `prereq is None` (Sourcing):**
     `MODULES[module]["run"](storage, num_rows)`. No `list_eligible_projects`, no per-project loop.
   - **Else (DB-fed):**
     `projects = storage.list_eligible_projects(prereq, num_rows)`.
     `for project in projects:`
       `result = MODULES[module]["run_one"](project)`
       - **Success:** `update_record(drpid, {"status": module, **result.updates})`; for each `w` in `result.warnings`: `append_to_field(drpid, "warnings", w)`.
       - **Failure:** for each `e` in `result.errors`: `append_to_field(drpid, "errors", e)`.
       - **Exception:** `append_to_field(drpid, "errors", str(e))`; continue.
5. **Logging:** start/end, count of projects processed.

---

## 3. File / Module Layout

| File | Role |
|------|------|
| `main.py` | `setup()`; resolve `module` from Args; instantiate `Orchestrator` and call `run(module)`. |
| `orchestration/Orchestrator.py` | `Orchestrator` with `run(module: str)`, `MODULES` registry, and the branching logic. Central loop: `list_eligible_projects` and `run`/`run_one` only here. |
| `orchestration/__init__.py` | Export `Orchestrator`. |
| `storage/StorageProtocol.py` | Add `list_eligible_projects`, `append_to_field`. |
| `storage/StorageSQLLite.py` | Implement `list_eligible_projects`, `append_to_field`. |
| `utils/Args.py` | Add `module` (required), `num_rows` (replaces `sourcing_num_rows`), `db_path`, `storage_implementation`. |
| `sourcing/Sourcing.py` | `run(limit=...)`; after creating a record, `update_record(drpid, {"status": "sourcing"})`. |

**Collectors:** Add `collectors_run_one(project: dict) -> ModuleResult` (e.g. in `orchestration/` or `collectors/`). It calls `SocrataCollector.collect(...)` and maps the result to `ModuleResult`. The orchestrator does the DB loop and `update_record` / `append_to_field`; the module does not call `list_eligible_projects` or `num_rows`.

---

## 4. Module -> Runner Mapping

- **`sourcing`**: `run` = `Sourcing(storage).run(limit=num_rows)`. Orchestrator passes `num_rows` as `limit`.
- **`collectors`**: `run_one` = `collectors_run_one(project)`. Orchestrator calls `list_eligible_projects(prereq, num_rows)`, then for each project calls `run_one(project)` and applies the returned `ModuleResult`.

---

## 5. Status and Error / Warning Conventions

- **Status values**: lowercase module names, e.g. `"sourcing"`, `"collectors"`, to match `prereq` and simplify string comparison.
- **When to set status**: only when the module **completes successfully** for that project. On error, do **not** set `status` to the current module; only append to `errors`.
- **Warnings**: append via `append_to_field(drpid, "warnings", msg)`. One entry per line (or pick one format and document).
- **Errors**: same append; projects with non-empty `errors` are excluded by `list_eligible_projects`.

---

## 6. Implementation Order

1. **Args**: add `module` (required), `num_rows` (replace `sourcing_num_rows`), `db_path`, `storage_implementation`; update SpreadsheetCandidateFetcher, Sourcing, tests.
2. **StorageProtocol**: add `list_eligible_projects`, `append_to_field`.
3. **StorageSQLLite**: implement both; add tests in `test_StorageSQLLite.py`.
4. **Sourcing**: `run(limit=...)`; after creating a record, `update_record(drpid, {"status": "sourcing"})`; pass `limit` to fetcher. Add/update tests.
5. **Orchestration**: create `orchestration/`, `Orchestrator`, `MODULES`, and `collectors_run_one`; implement `run(module)` with Sourcing and DB-fed branches. Orchestrator does `list_eligible_projects` and the per-project loop for DB-fed modules.
6. **main.py**: after `setup()`, call `Orchestrator.run(Args.module)`.
7. **Tests**: `test_Orchestrator.py` with mocked storage and mocked Sourcing/Collectors.

---

## 7. .cursorrules Checklist

- Unit tests for new/changed code: `test_StorageSQLLite`, `test_Orchestrator`, `test_Args`, `test_Sourcing`.
- Type hints and docstrings on all new functions and classes.
- Short methods: e.g. `run()` delegates to `_run_sourcing()`, `_run_db_fed()`.
- DRY: orchestrator holds the single "find eligible, call run_one, apply result" loop.
- Git: at the end, `git add` and `git commit` for all touched files.

---

## 8. Open Decisions

1. **Orchestrator location**: `orchestration/Orchestrator.py` vs inlining in `main.py`.
2. **Collector result -> DB fields**: Exact mapping from `result["metadata"]` to `title`, `summary`, `keywords`, etc., and whether `folder_path` is computed in the orchestrator or returned by the collector.
3. **Append format**: newline vs `; ` for `warnings`/`errors` — choose one and document.

---

## 9. Stub / Future Modules

For `Uploading`, `Publication`, etc., add to `MODULES` with the right `prereq` and a `run_one` stub that logs "not implemented" or raises. That keeps the orchestration structure ready.
