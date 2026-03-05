# DRP Pipeline MCP Server — Design Plan

## Overview

An MCP server that lets Claude (via Claude Desktop or Claude Code) manage the DRP Pipeline through natural language — inspecting project status, querying the database, running pipeline modules, and modifying records — with built-in dry-run safety and post-run verification.

## Architecture

**Option A — Direct access**: The MCP server imports/calls the pipeline's existing database and subprocess infrastructure directly. No dependency on the Flask app being running.

**Transport**: `stdio` — compatible with both Claude Desktop and Claude Code.

**Language**: Python, using the `mcp` SDK (`pip install mcp`).

**DB access**: The server reads `config.json` for `db_path` (falling back to `drp_pipeline.db` in the project root), then opens sqlite3 connections directly. This avoids initializing the Storage/Args/Logger singletons in the MCP process.

**Module execution**: Runs `python main.py <module> [args]` via `subprocess.run`, same pattern as `interactive_collector/api_pipeline.py`. Captures and returns stdout+stderr.

## Files to Create/Modify

```
mcp_server/
    __init__.py        # empty
    server.py          # all tools; entry point: python mcp_server/server.py
.mcp.json              # Claude Code MCP config
requirements.txt       # add: mcp>=1.0.0
```

## Tools

### Query tools (read-only)

| Tool | Description |
|------|-------------|
| `get_pipeline_stats` | Total project count, counts by status, projects with errors/warnings, db path |
| `list_projects` | List projects filtered by status and/or has_errors; paginated with limit/offset |
| `get_project` | Full record for a single DRPID |

### Pipeline execution

| Tool | Description |
|------|-------------|
| `run_module` | Run a pipeline module. `dry_run=True` (default) shows eligible projects; `dry_run=False` executes via subprocess and returns captured log output. Accepts `num_rows`, `max_workers`, `start_drpid`, `log_level`. |

### Write tools (all default to `dry_run=True`)

| Tool | Description |
|------|-------------|
| `update_project` | Update metadata fields (title, agency, office, summary, keywords, time_start, time_end, data_types, extensions, download_date, collection_notes, file_size, status_notes). Returns a diff of old vs new values. |
| `clear_errors` | Clear the `errors` field on a project so it becomes eligible for re-processing. |
| `set_project_status` | Manually set a project's status (e.g. roll back to `sourcing` to re-collect). |
| `delete_project` | Delete a project record. Does not delete files from disk. |

### Verification tools

| Tool | Description |
|------|-------------|
| `verify_module_run` | After running a module, checks how many projects reached the expected output status, how many are stuck with errors, and surfaces a sample of error messages. Accepts `expected_count` to assert against. |
| `check_project_files` | Lists files in a project's `folder_path`, with names, sizes, and extensions. Confirms folder exists. |

## Safety Design

- All write tools and `run_module` default to `dry_run=True`.
- Dry-run responses are clearly labeled and describe exactly what *would* change.
- `delete_project` and `set_project_status` show the full current record before any deletion/mutation.
- Protected fields (`DRPID`, `source_url`, `datalumos_id`, `status`, `errors`, `warnings`, `published_url`) cannot be updated via `update_project`; use dedicated tools (`clear_errors`, `set_project_status`) for status/error fields.

## Module Registry (from Orchestrator.py)

| Module | Prereq status | Output status |
|--------|--------------|---------------|
| `noop` | — | — |
| `sourcing` | — | `sourcing` |
| `interactive_collector` | `sourcing` | `collector` |
| `socrata_collector` | `sourcing` | `collector` |
| `catalog_collector` | `sourcing` | `collector` |
| `upload` | `collector` | `upload` |
| `publisher` | `upload` | `publisher` |
| `cleanup_inprogress` | — | — (DataLumos only, no DB changes) |

Note: `publisher` also processes `not_found` and `no_links` status projects (sheet-only update). The dry-run for `run_module publisher` will show all three buckets.

## Configuration

### Claude Code (`.mcp.json` in project root)
```json
{
  "mcpServers": {
    "drp-pipeline": {
      "command": "python",
      "args": ["mcp_server/server.py"]
    }
  }
}
```

### Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "drp-pipeline": {
      "command": "python",
      "args": ["/Users/sefk/src/datarescue/DRPPipeline/mcp_server/server.py"]
    }
  }
}
```

## Open Questions / Future Work

- `run_module` with `dry_run=False` blocks until the subprocess finishes and then returns the full output. For long-running modules (upload, publisher with browser automation), this could take many minutes. A future enhancement could add a background-run mode that returns a job ID and a separate `poll_run` tool to check status.
- `cleanup_inprogress` has no DB effect and no verifiable output status; it only affects DataLumos. `verify_module_run` will return an error for this module.
- If `config.json` is absent, the server falls back to `drp_pipeline.db` in the project root. If the DB does not exist, all tools return a clear error.
