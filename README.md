# DRP Pipeline

A modular pipeline for collecting data from various sources (e.g., government websites) and uploading to repositories such as DataLumos.

- **[Setup](docs/Setup.md)** — Prerequisites, installation, and configuration  
- **[Usage](docs/Usage.md)** — Running modules, database, and examples  

## Overview

The DRP Pipeline is a Python-based data collection and processing system that:

- **Sources** candidate URLs from spreadsheets
- **Collects** data and metadata from web sources (e.g., Socrata)
- **Tracks** project status and progress in a SQLite database
- **Uploads** to DataLumos and **publishes** projects
- Supports optional **cleanup** of in-progress DataLumos projects and **inventory** updates (e.g., Google Sheets)

Projects move through a series of modules in order; each module updates status so the next can process eligible projects.

## Project structure

```
DRPPipeline/
├── collectors/          # Data collection (e.g., SocrataCollector)
├── cleanup_inprogress/ # Delete DataLumos projects in Deposit In Progress
├── debug/              # Debug scripts
├── docs/               # Setup, Usage, design docs
├── duplicate_checking/ # Duplicate detection (e.g., DataLumos search)
├── orchestration/     # Orchestrator and module protocol
├── publisher/         # DataLumos publish and optional Google Sheet update
├── sourcing/          # Source URL discovery and project creation
├── storage/           # Database storage (SQLite)
├── upload/            # DataLumos upload (browser automation)
├── utils/             # Args, Logger, file/URL utilities
├── main.py            # Entry point
└── requirements.txt   # Dependencies
```

## Modules

| Module | Purpose |
|--------|--------|
| **noop** | No-op; useful for testing. |
| **sourcing** | Fetches candidate URLs from a spreadsheet, checks duplicates, creates DB records. |
| **collector** | Collects data and metadata for projects (e.g., Socrata); updates status. |
| **upload** | Uploads collected data to DataLumos via browser automation. |
| **publisher** | Runs DataLumos publish workflow; optionally updates inventory (e.g., Google Sheet). |
| **cleanup_inprogress** | Deletes DataLumos workspace projects in “Deposit In Progress” state (no DB changes). |

Each module (except `noop` and `cleanup_inprogress`) advances project `status` so the next module can run on eligible projects. See [Usage](docs/Usage.md) for how to run them and how the database is used.

## Architecture

- **Module protocol** — Modules implement `run(drpid: int)` and use the shared **Storage** singleton to read/update project data. Sourcing runs once with `drpid=-1`; others are invoked per eligible project.
- **Orchestrator** — Resolves the requested module by name, loads its class, and runs it (once for no-prereq modules, or over the list of eligible projects for prereq-based modules). Uses `Args` for config and `num_rows` for batch limits.
- **Storage** — SQLite-backed singleton; exposes `initialize`, `create_record`, `get`, `update_record`, `append_to_field`, `list_eligible_projects`, etc.

See [Usage](docs/Usage.md) for database fields and eligibility rules.

## Development

- **Tests:** `python -m pytest` or `python -m unittest discover -p "test_*.py"`
- **New module:** Implement a class with `run(drpid: int)`, register it in `orchestration/Orchestrator.py` under `MODULES`, and add the module to the `module` argument in `Args`. The orchestrator discovers the class by name. See `.cursorrules` and existing modules for style (type hints, docstrings, one class per file, tests).
- **Code style:** PEP 8, type hints, unit tests; defaults in `Args._defaults`.

## Troubleshooting

- **ImportError (module class not found):** Ensure the class name matches the `MODULES` entry and the module is in the project tree (not only in tests).
- **Database:** Ensure `db_path` is writable; projects with non-empty `errors` are not eligible for later modules.
- **Playwright:** Run `playwright install`; use `upload_headless: false` in config for visible browser debugging.

For full configuration and command-line options, see [Setup](docs/Setup.md).

## License

[Add license information here]

## Contributing

[Add contributing guidelines here]
