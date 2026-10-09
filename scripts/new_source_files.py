"""Read and write the files created for a new pipeline source."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: Path) -> dict[str, Any]:
    """
    Load a config JSON object.

    Args:
        path: Path to config.json.

    Returns:
        Parsed object.

    Raises:
        ValueError: If the file is missing or not a JSON object.
    """
    if not path.is_file():
        raise ValueError(f"Config not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("config.json must be a JSON object.")
    return data


def save_config(path: Path, config: dict[str, Any]) -> None:
    """
    Write config.json with a trailing newline.

    Args:
        path: Destination path.
        config: Config object.
    """
    path.write_text(json.dumps(config, indent=4) + "\n", encoding="utf-8")


def create_output_dir(path: Path) -> None:
    """
    Create an empty download directory.

    Args:
        path: Directory to create. Existing empty directories are kept.
    """
    path.mkdir(parents=True, exist_ok=True)


def create_database(db_path: Path) -> None:
    """
    Create a SQLite database with the pipeline schema.

    Args:
        db_path: Database file to create.
    """
    from storage.StorageSQLLite import StorageSQLLite
    from utils.Logger import Logger

    if not Logger._initialized:
        Logger.initialize(log_level="INFO")
    store = StorageSQLLite()
    store.initialize(db_path)
    if store._connection is not None:
        store._connection.close()


def print_plan(
    code: str,
    template_name: str,
    section: dict[str, Any],
    template_tab: str,
) -> None:
    """
    Print what a live run would create.

    Args:
        code: New source code.
        template_name: Template source key.
        section: Planned config section.
        template_tab: Worksheet whose header row will be copied.
    """
    sheet_id = section["google_sheet_id"]
    print(f"Dry run: would create source '{code}' from template '{template_name}'.")
    print(f"  database: {section['db_path']}")
    print(f"  output: {section['base_output_dir']}")
    print(f"  spreadsheet: https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
    print(f"  new tab: {section['google_sheet_name']} (headers copied from {template_tab})")
    print(f"  DataLumos username: {section['datalumos_username'] or '(unset)'}")
    print("  DataLumos password is left blank.")


def print_created(code: str, section: dict[str, Any], sheet_url: str) -> None:
    """
    Print the created source and the DataLumos step still left to do.

    Args:
        code: New source code.
        section: Config section that was written.
        sheet_url: URL of the new worksheet.
    """
    username = section["datalumos_username"] or "(set datalumos_username)"
    print(f"Source '{code}' is active in config.json.")
    print(f"  database: {section['db_path']}")
    print(f"  output: {section['base_output_dir']}")
    print(f"  sheet: {sheet_url}")
    print(f"Create the DataLumos login {username} and set sources.{code}.datalumos_password.")
