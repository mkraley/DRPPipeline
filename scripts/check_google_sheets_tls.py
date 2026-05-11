"""
Quick check: Google Sheets API + TLS (same stack as publisher sheet updates).

Run from repo root:
  python scripts/check_google_sheets_tls.py
  python scripts/check_google_sheets_tls.py --config path/to/config.json

Exit 0 if spreadsheets.get succeeds; nonzero on failure. Does not use Playwright.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Verify Google Sheets API TLS + credentials.")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=root / "config.json",
        help="Config JSON path (default: repo root config.json)",
    )
    args = parser.parse_args()
    config_path = args.config
    if not config_path.is_file():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        return 1

    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    creds_file = cfg.get("google_credentials")
    sheet_id = cfg.get("google_sheet_id")
    if not creds_file or not sheet_id:
        print(
            "ERROR: config needs google_credentials and google_sheet_id for this check.",
            file=sys.stderr,
        )
        return 1

    creds_path = Path(creds_file)
    if not creds_path.is_absolute():
        creds_path = (config_path.parent / creds_path).resolve()
    if not creds_path.is_file():
        print(f"ERROR: credentials file not found: {creds_path}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(root))

    try:
        from google.oauth2 import service_account
        from utils.google_sheets_service import build_sheets_v4_service
    except ImportError as e:
        print(f"ERROR: missing dependency: {e}", file=sys.stderr)
        return 1

    bundle_arg = None
    if cfg.get("ssl_ca_bundle"):
        p = Path(cfg["ssl_ca_bundle"])
        if not p.is_file() and not p.is_absolute():
            p = (config_path.parent / cfg["ssl_ca_bundle"]).resolve()
        if p.is_file():
            bundle_arg = str(p)

    creds_obj = service_account.Credentials.from_service_account_file(
        str(creds_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build_sheets_v4_service(
        creds_obj,
        cache_discovery=False,
        ssl_ca_bundle=bundle_arg,
    )
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=sheet_id, fields="properties(title),sheets(properties/title)")
        .execute()
    )
    title = (meta.get("properties") or {}).get("title", "")
    n = len(meta.get("sheets", []))
    print(f"OK — Google Sheets API succeeded. Spreadsheet title: {title!r}; {n} sheet(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
