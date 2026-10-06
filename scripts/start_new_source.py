"""
Create a new pipeline source: database, inventory spreadsheet, and config section.

Creates the database and config section, then renames the data tab on a
spreadsheet you copy into your own Google account. Service accounts have no
Drive storage, so the Drive API cannot own the copy. Leaves the DataLumos
password empty.

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
from scripts.new_source_google import prepare_existing_spreadsheet
from scripts.new_source_setup import (
    apply_new_source,
    assert_output_dir_available,
    assert_source_available,
    build_source_config,
    choose_template_source,
    normalize_source_code,
    tab_name_for,
)
from scripts.new_source_sheet import make_copy_url, prompt_for_copied_spreadsheet, spreadsheet_id_from_text

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
        help="Existing source whose spreadsheet is copied (default: active source)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_REPO_ROOT / "config.json",
        help="Path to config.json",
    )
    parser.add_argument(
        "--sheet-url",
        help="URL of a spreadsheet you already copied into your Google account",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without creating the sheet, database, or config entry",
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


def service_account_email(config: dict[str, Any], config_path: Path) -> str:
    """
    Return the service account email, or empty when credentials are absent.

    Args:
        config: Parsed config.json.
        config_path: Path used to resolve a relative credentials file.

    Returns:
        ``client_email`` from the credentials file, or ``""``.
    """
    import json

    creds_file = str(config.get("google_credentials") or "").strip()
    if not creds_file:
        return ""
    path = Path(creds_file)
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("client_email") or "")


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
    preview = build_source_config(code, template, "", contact)
    assert_output_dir_available(Path(preview["base_output_dir"]))
    template_id = str(template["google_sheet_id"])
    editor_email = service_account_email(config, config_path)
    if args.dry_run:
        print_plan(code, template_name, preview, make_copy_url(template_id), editor_email)
        return 0
    if args.sheet_url:
        sheet_id = spreadsheet_id_from_text(args.sheet_url)
    else:
        sheet_id = prompt_for_copied_spreadsheet(template_id, editor_email)
    sheets = google_sheets_client(config, config_path)
    sheet_url = prepare_existing_spreadsheet(
        sheets,
        sheet_id,
        str(template["google_sheet_name"]),
        tab_name_for(code),
    )
    section = build_source_config(code, template, sheet_id, contact)
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
