"""
Reconcile Google Sheet inventory rows against Storage (DB is source of truth).

Compares ``updated_inventory`` projects to the configured sheet tab using exact URL
matching. Only rows that need a fix or append are written (dry-run by default).

From repo root:

    python scripts/reconcile_inventory_sheet.py
    python scripts/reconcile_inventory_sheet.py --execute
    python scripts/reconcile_inventory_sheet.py --sample 10
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utils.inventory_sheet_reconcile import (  # noqa: E402
    ReconcileAction,
    classify_reconcile_actions,
    format_action_line,
)
from utils.project_utils import get_field  # noqa: E402

STATUS_UPDATED_INVENTORY = "updated_inventory"


def fetch_sheet_rows(sheet_name: str) -> List[Dict[str, str]]:
    from utils.Args import Args
    from sourcing.SpreadsheetCandidateFetcher import SpreadsheetCandidateFetcher
    from utils.sheet_url_utils import get_gid_for_sheet_name

    fetcher = SpreadsheetCandidateFetcher()
    gid = get_gid_for_sheet_name(
        Args.google_sheet_id,
        sheet_name,
        Path(Args.google_credentials),
    )
    if gid is None:
        raise RuntimeError(f"Sheet tab {sheet_name!r} not found")
    csv_text = fetcher._fetch_sheet_csv(Args.google_sheet_id, gid)
    reader = csv.DictReader(io.StringIO(csv_text))
    return [
        {(k or "").strip(): (v or "").strip() for k, v in row.items() if k}
        for row in reader
    ]


def load_db_rows(db_path: Path) -> List[Dict[str, object]]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT DRPID, source_url, datalumos_id, title, status
            FROM projects
            WHERE status = ?
            ORDER BY DRPID
            """,
            (STATUS_UPDATED_INVENTORY,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def print_summary(
    actions: List[ReconcileAction],
    *,
    sheet_name: str,
    sample: int,
) -> None:
    ok = [a for a in actions if a.action == "ok"]
    fixes = [a for a in actions if a.action == "fix"]
    appends = [a for a in actions if a.action == "append"]
    skipped = [a for a in actions if a.action == "skip"]
    to_update = fixes + appends

    print(f"Sheet tab: {sheet_name}")
    print(f"DB {STATUS_UPDATED_INVENTORY}: {len(actions) - len(skipped)}")
    print(f"  already correct (exact URL + datalumos_id): {len(ok)}")
    print(f"  fix existing row: {len(fixes)}")
    print(f"  append new row: {len(appends)}")
    if skipped:
        print(f"  skip (incomplete DB row): {len(skipped)}")
    print(f"API updates needed: {len(to_update)}")
    print()

    if sample > 0 and to_update:
        n = min(sample, len(to_update))
        print(f"Sample changes ({n} of {len(to_update)}):")
        print("=" * 100)
        for action in to_update[:n]:
            print(format_action_line(action, verbose=True))
            print()


def run_execute(actions: List[ReconcileAction], *, delay_seconds: float) -> int:
    from publisher.GoogleSheetUpdater import GoogleSheetUpdater
    from storage import Storage

    updater = GoogleSheetUpdater()
    to_run = [a for a in actions if a.action in ("fix", "append")]
    failed = 0

    for i, action in enumerate(to_run):
        if i > 0 and delay_seconds > 0:
            time.sleep(delay_seconds)

        project = Storage.get(action.drpid)
        if project is None:
            print(f"DRPID={action.drpid}: SKIP — not in storage", file=sys.stderr)
            failed += 1
            continue

        workspace_id = get_field(project, "datalumos_id")
        source_url = get_field(project, "source_url")
        if not workspace_id or not source_url:
            print(
                f"DRPID={action.drpid}: SKIP — missing datalumos_id or source_url",
                file=sys.stderr,
            )
            failed += 1
            continue

        ok, err = updater.update(source_url, workspace_id, project)
        if ok:
            Storage.update_record(action.drpid, {"status": STATUS_UPDATED_INVENTORY})
            print(f"DRPID={action.drpid}: OK — {action.action}")
        else:
            failed += 1
            print(f"DRPID={action.drpid}: FAIL — {err}", file=sys.stderr)

    print()
    print(f"Done: {len(to_run) - failed} updated, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile Google Sheet inventory from updated_inventory DB rows "
            "(dry-run by default)"
        )
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=REPO_ROOT / "config.json",
        help="Config JSON (default: ./config.json)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply fix/append updates via Google Sheets API",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        metavar="N",
        help="Number of suggested changes to print (default: 10, 0 to omit)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        metavar="SEC",
        help="Seconds to wait between API calls on --execute (default: 2)",
    )
    args = parser.parse_args()

    if not args.config.is_file():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 1

    from utils.Args import Args
    from utils.Logger import Logger
    from storage import Storage

    Args.initialize_from_config(args.config)
    Logger.initialize(log_level=Args.log_level, log_color=getattr(Args, "log_color", False))

    if not Args.google_sheet_id or not Args.google_credentials:
        print(
            "ERROR: google_sheet_id and google_credentials must be set in config.",
            file=sys.stderr,
        )
        return 1

    sheet_name = (getattr(Args, "google_sheet_name", None) or "").strip()
    if not sheet_name:
        print("ERROR: google_sheet_name must be set in config.", file=sys.stderr)
        return 1

    Storage.initialize(Args.storage_implementation, db_path=Path(Args.db_path))

    db_rows = load_db_rows(Path(Args.db_path))
    sheet_rows = fetch_sheet_rows(sheet_name)
    actions = classify_reconcile_actions(db_rows, sheet_rows)

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"{mode}")
    print_summary(actions, sheet_name=sheet_name, sample=args.sample)

    if not args.execute:
        to_update = sum(1 for a in actions if a.action in ("fix", "append"))
        if to_update:
            print("Re-run with --execute to apply the changes listed above.")
        return 0

    return run_execute(actions, delay_seconds=max(0.0, args.delay))


if __name__ == "__main__":
    raise SystemExit(main())
