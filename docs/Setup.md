# DRP Pipeline — Setup

This document covers prerequisites, installation, and configuration. For running the pipeline and module details, see [Usage](Usage.md).

## Prerequisites

- Python 3.13 or later
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd DRPPipeline
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browsers (required for web scraping and DataLumos automation):
   ```bash
   playwright install
   ```

## Configuration

The pipeline is configured by (in order of priority, highest first):

1. **Command line arguments**
2. **Config file** (JSON, default: `./config.json`)
3. **Default values** (in `Args._defaults`)

If `./config.json` exists, it is loaded automatically. If it does not exist, a warning is shown but the pipeline continues with defaults and command-line arguments.

### Command line arguments

```bash
python main.py <module> [options]
```

**Required:**

- `module` — Module to run: `noop`, `sourcing`, `collector`, `upload`, `publisher`, `cleanup_inprogress`

**Optional:**

- `--config`, `-c` — Path to configuration file (JSON). Default: `./config.json`
- `--log-level`, `-l` — Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `--log-color` — Color the log severity in the terminal (DEBUG=gray, WARNING=orange, ERROR=red, exception=purple). Only when stdout is a TTY.
- `--num-rows`, `-n` — Max projects or candidate URLs per batch; omit for unlimited
- `--db-path` — Path to SQLite database file
- `--storage` — Storage implementation (default: `StorageSQLLite`)
- `--delete-all-db-entries` — Delete all database entries and reset auto-increment before running
- `--max-workers`, `-w` — Max concurrent projects for modules that support it (default: 1)
- `--download-timeout-ms` — Download timeout in milliseconds (default: 30 min)
- `--no-use-url-download` — Use Playwright save_as instead of URL + requests for downloads

### Config file format

Create a JSON file (e.g. `config.json`) in the project root:

```json
{
  "log_level": "INFO",
  "num_rows": 10,
  "db_path": "drp_pipeline.db",
  "storage_implementation": "StorageSQLLite",
  "sourcing_spreadsheet_url": "https://docs.google.com/spreadsheets/d/...",
  "sourcing_url_column": "URL",
  "base_output_dir": "C:\\Documents\\DataRescue\\DRPData",
  "datalumos_username": "your@email",
  "datalumos_password": "your-password",
  "upload_headless": false,
  "upload_timeout": 60000,
  "google_sheet_id": "1OYLn6NBWStOgPUTJfYpU0y0g4uY7roIPP4qC2YztgWY",
  "google_credentials": "C:\\path\\to\\service-account.json",
  "google_sheet_name": "CDC",
  "google_username": "mkraley"
}
```

Common options:

- **Sourcing:** `sourcing_spreadsheet_url`, `sourcing_url_column`
- **Upload / Publisher / Cleanup:** `datalumos_username`, `datalumos_password`; `upload_headless`, `upload_timeout` for browser behavior
- **Publisher (optional):** `google_sheet_id`, `google_credentials`, `google_sheet_name`, `google_username` for inventory sheet updates

See [README](../README.md) and module descriptions for context. Command-line values override config file values.
