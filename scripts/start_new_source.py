"""
Create a new pipeline source: database, inventory tab, and config section.

Adds a worksheet to the shared inventory spreadsheet and copies the header
row from the Baserow batch-import template tab. Leaves the DataLumos password
empty.

From the repo root:

  python scripts/start_new_source.py nrc
  python scripts/start_new_source.py nrc --template nps
  python scripts/start_new_source.py nrc --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.new_source_files import (
    create_database,
    create_output_dir,
    load_config,
    print_created,
    print_plan,
    save_config,
)
from scripts.new_source_google import add_inventory_tab
from scripts.new_source_setup import (
    apply_new_source,
    assert_output_dir_available,
    assert_source_available,
    build_source_config,
    choose_template_source,
    normalize_source_code,
    tab_name_for,
)
from scripts.new_source_sheet import HEADER_TEMPLATE_TAB, INVENTORY_SPREADSHEET_ID

_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        argv: Arguments excluding the program name. None reads sys.argv.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Create a new pipeline source.")
    parser.add_argument("initials", help="Short source code, for example nrc")
    parser.add_argument(
        "--template",
        help="Existing source whose tab supplies the header row (default: active source)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_REPO_ROOT / "config.json",
        help="Path to config.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without creating the tab, database, or config entry",
    )
    return parser.parse_args(argv)


def credentials_path(config: dict[str, Any], config_path: Path) -> Path:
    """
    Return the service-account JSON path from config.

    Args:
        config: Parsed config.json.
        config_path: Path used to resolve a relative credentials file.

    Returns:
        Absolute path to the credentials file.

    Raises:
        ValueError: If the path is missing or not a file.
    """
    creds_file = str(config.get("google_credentials") or "").strip()
    if not creds_file:
        raise ValueError("config.json needs google_credentials.")
    creds_path = Path(creds_file)
    if not creds_path.is_absolute():
        creds_path = (config_path.parent / creds_path).resolve()
    if not creds_path.is_file():
        raise ValueError(f"Credentials file not found: {creds_path}")
    return creds_path


def google_sheets_client(config: dict[str, Any], config_path: Path) -> Any:
    """
    Build a Sheets client from the config service account.

    Args:
        config: Parsed config.json.
        config_path: Path used to resolve a relative credentials file.

    Returns:
        Sheets v4 service.
    """
    from google.oauth2 import service_account

    from utils.google_sheets_service import build_google_api_service

    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path(config, config_path)),
        scopes=[_SHEETS_SCOPE],
    )
    return build_google_api_service("sheets", "v4", credentials)


def run(argv: list[str] | None = None) -> int:
    """
    Create a new source or print a dry-run plan.

    Args:
        argv: Arguments excluding the program name.

    Returns:
        Process exit code. 0 on success, 1 on a reported error.
    """
    args = parse_args(argv)
    try:
        return _run_checked(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _run_checked(args: argparse.Namespace) -> int:
    """
    Create a new source after arguments have been parsed.

    Args:
        args: Parsed CLI arguments.

    Returns:
        0 when the source is created or the dry run is printed.
    """
    config_path = args.config.resolve()
    config = load_config(config_path)
    code = normalize_source_code(args.initials)
    assert_source_available(config, code, config_path.parent)
    template_name, template = choose_template_source(config, args.template)
    contact = str(config.get("gwda_email") or "").strip()
    section = build_source_config(code, template, INVENTORY_SPREADSHEET_ID, contact)
    assert_output_dir_available(Path(section["base_output_dir"]))
    if args.dry_run:
        print_plan(code, template_name, section, HEADER_TEMPLATE_TAB)
        return 0
    sheets = google_sheets_client(config, config_path)
    sheet_url = add_inventory_tab(
        sheets,
        INVENTORY_SPREADSHEET_ID,
        HEADER_TEMPLATE_TAB,
        tab_name_for(code),
    )
    create_output_dir(Path(section["base_output_dir"]))
    create_database(config_path.parent / str(section["db_path"]))
    apply_new_source(config, code, section)
    save_config(config_path, config)
    print_created(code, section, sheet_url)
    return 0


def main() -> None:
    """Run the new-source command."""
    raise SystemExit(run())


if __name__ == "__main__":
    main()
