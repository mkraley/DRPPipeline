# DRP Pipeline

A modular pipeline for collecting data from various sources (e.g., government websites) and uploading to various repositories (e.g., DataLumos).

## Overview

The DRP Pipeline is a Python-based data collection and processing system that:
- Sources candidate URLs from spreadsheets
- Collects data and metadata from web sources
- Manages project status and progress in a SQLite database
- Processes projects through a series of modules (sourcing, collectors, etc.)

## Project Structure

```
DRPPipeline/
├── collectors/          # Data collection modules (e.g., SocrataCollector)
├── debug/              # Debug scripts
├── duplicate_checking/ # Duplicate detection (e.g., DataLumos search)
├── orchestration/      # Central orchestrator and module protocol
├── sourcing/           # Source URL discovery and project creation
├── storage/            # Database storage (SQLite implementation)
├── utils/              # Utilities (Args, Logger, file/URL utils)
├── main.py             # Main entry point
└── requirements.txt    # Python dependencies
```

## Setup

### Prerequisites

- Python 3.13 or later
- pip (Python package manager)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd DRPPipeline
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright browsers (required for web scraping):
   ```bash
   playwright install
   ```

### Configuration

The pipeline can be configured via:
- **Command line arguments** (highest priority)
- **Config file** (JSON format, default: `./DRPPipeline_config.json`)
- **Default values** (lowest priority, defined in `Args._defaults`)

**Note:** If `./DRPPipeline_config.json` exists, it will be automatically loaded. If it doesn't exist, a warning is shown but the pipeline continues with defaults and command-line arguments.

#### Command Line Arguments

```bash
python main.py <module> [options]
```

**Required:**
- `module`: Module to run (`noop`, `sourcing`, `collectors`)

**Optional:**
- `--config, -c`: Path to configuration file (JSON format). Default: `./DRPPipeline_config.json`
- `--log-level, -l`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `--num-rows, -n`: Max projects or candidate URLs per batch (None = unlimited)
- `--db-path`: Path to SQLite database file
- `--storage`: Storage implementation (default: `StorageSQLLite`)

#### Config File Format

Create a JSON file named `DRPPipeline_config.json` in the project root (or specify a different path with `--config`):

```json
{
  "log_level": "INFO",
  "num_rows": 10,
  "db_path": "drp_pipeline.db",
  "storage_implementation": "StorageSQLLite",
  "sourcing_spreadsheet_url": "https://docs.google.com/spreadsheets/d/...",
  "sourcing_url_column": "URL",
  "base_output_dir": "C:\\Documents\\DataRescue\\DRPData"
}
```

**Default behavior:** The pipeline automatically looks for `./DRPPipeline_config.json` in the current directory. If the file doesn't exist, a warning is displayed but the pipeline continues with default values and command-line arguments.

## Usage

### Basic Usage

Run a module:
```bash
python main.py sourcing
python main.py collectors
```

Run with options:
```bash
python main.py sourcing --num-rows 10 --log-level DEBUG
python main.py collectors --db-path /path/to/database.db
```

### Modules

#### `noop`
No-op module that does nothing. Useful for testing or when you need to satisfy the module requirement without running actual pipeline logic.

```bash
python main.py noop
```

#### `sourcing`
Discovers candidate source URLs from a configured spreadsheet, performs duplicate checks, and creates database records for new projects.

```bash
python main.py sourcing --num-rows 50
```

**Process:**
1. Fetches URLs from the configured spreadsheet
2. Checks for duplicates (in local DB and DataLumos)
3. Verifies source URL availability
4. Creates database records with generated DRPIDs

#### `collectors`
Processes eligible projects through the collectors module. Projects must have `status="sourcing"` and no errors.

```bash
python main.py collectors --num-rows 20
```

**Process:**
1. Finds projects with `status="sourcing"` and no errors
2. For each project, collects data and metadata
3. Updates project status on success
4. Appends warnings/errors as appropriate

### Database

The pipeline uses SQLite to track project status and metadata. By default, the database is created at `drp_pipeline.db` in the current working directory.

**Key Fields:**
- `DRPID`: Unique project identifier
- `source_url`: Source URL for the project
- `status`: Last successfully completed module name
- `warnings`: Newline-separated warning messages
- `errors`: Newline-separated error messages (projects with errors are ineligible for further processing)

**Eligibility Rules:**
- Projects are eligible for a module if:
  - `status == <prerequisite_module>` (e.g., `status="sourcing"` for collectors)
  - `errors IS NULL OR errors = ''` (warnings are allowed)

## Architecture

### Module Protocol

All modules implement `ModuleProtocol` with a `run(drpid: int)` method:
- Modules access Storage directly using the DRPID
- Modules update status, errors, and warnings directly to Storage
- For sourcing (no prerequisite), orchestrator passes `drpid=-1`

### Storage Singleton

Storage is a singleton accessible via class methods:
```python
from storage import Storage

Storage.initialize("StorageSQLLite", db_path="db.db")
Storage.create_record("https://example.com")
Storage.update_record(drpid, {"status": "sourcing"})
Storage.append_to_field(drpid, "warnings", "Warning message")
```

### Orchestrator

The orchestrator:
- Dynamically discovers module classes by name
- Manages module execution and error handling
- Tracks project eligibility and status
- Limits batch sizes via `num_rows`

## Development

### Running Tests

```bash
python -m unittest discover -p "test_*.py"
```

### Adding a New Module

1. Create a class that implements `ModuleProtocol`:
   ```python
   class MyModule:
       def run(self, drpid: int) -> None:
           # Get project data
           project = Storage.get(drpid)
           # Process project
           # Update status on success
           Storage.update_record(drpid, {"status": "mymodule"})
   ```

2. Register in `orchestration/Orchestrator.py`:
   ```python
   MODULES = {
       "mymodule": {
           "prereq": "sourcing",  # or None for no prerequisite
           "class_name": "MyModule",
       },
   }
   ```

3. The orchestrator will automatically discover the class by name.

### Code Style

- Follow PEP 8
- Use type hints
- Write unit tests for new functionality
- Default values should be in `Args._defaults`, not in client code

## Troubleshooting

### Import Errors

If you see `ImportError: Could not find module class 'X' in project tree`:
- Ensure the class name matches exactly (case-sensitive)
- Verify the module file is in the project tree (not in `__pycache__` or test files)
- Check that the class is defined in the module

### Database Issues

- Ensure the database path is writable
- Check that `db_path` is set correctly (defaults to `drp_pipeline.db` in current directory)
- Projects with errors won't be processed further - check the `errors` field

### Playwright Issues

- Run `playwright install` to install browser binaries
- For debugging, set `headless=False` in collector initialization

## License

[Add license information here]

## Contributing

[Add contributing guidelines here]
