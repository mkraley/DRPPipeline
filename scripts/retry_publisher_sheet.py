"""
Retry only the Google Sheet inventory update (no browser / no DataLumos publish).

Use when publish succeeded on DataLumos but the sheet step failed (e.g. SSL),
so status is already ``published`` — ``python main.py publisher`` will not pick
those rows again (it only lists ``uploaded``).

From repo root:

  python scripts/retry_publisher_sheet.py 101 102 103
  python scripts/retry_publisher_sheet.py --config other.json 42

Requires ``datalumos_id``, ``source_url``, and the same Google Sheet config as
the publisher module. On success, sets status to ``updated_inventory`` (same
as a full publisher run after a successful sheet update).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Run GoogleSheetUpdater only for given DRPIDs (no Playwright)."
    )
    parser.add_argument(
        "drpids",
        type=int,
        nargs="+",
        help="One or more DRPIDs to update in the sheet",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=root / "config.json",
        help="Config JSON (default: ./config.json)",
    )
    parser.add_argument(
        "--clear-errors",
        action="store_true",
        help="After a successful sheet update, clear the project's errors field",
    )
    args = parser.parse_args()

    if not args.config.is_file():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(root))

    from utils.Args import Args
    from utils.Logger import Logger
    from utils.project_utils import get_field
    from storage import Storage
    from publisher.GoogleSheetUpdater import GoogleSheetUpdater

    Args.initialize_from_config(args.config)
    Logger.initialize(log_level=Args.log_level, log_color=getattr(Args, "log_color", False))

    Storage.initialize(Args.storage_implementation, db_path=Path(Args.db_path))

    if not Args.google_sheet_id or not Args.google_credentials:
        print(
            "ERROR: google_sheet_id and google_credentials must be set in config.",
            file=sys.stderr,
        )
        return 1

    updater = GoogleSheetUpdater()
    exit_code = 0

    for drpid in args.drpids:
        project = Storage.get(drpid)
        if not project:
            print(f"DRPID={drpid}: SKIP — not in storage")
            exit_code = 1
            continue

        workspace_id = get_field(project, "datalumos_id")
        source_url = get_field(project, "source_url")
        status = (project.get("status") or "").strip().lower()

        if not workspace_id or not source_url:
            print(
                f"DRPID={drpid}: SKIP — need datalumos_id and source_url "
                f"(got workspace={workspace_id!r}, source_url set={bool(source_url)})"
            )
            exit_code = 1
            continue

        if status not in ("published", "uploaded", "updated_inventory"):
            print(
                f"DRPID={drpid}: WARN — status={status!r} (expected published, uploaded, or updated_inventory); continuing anyway"
            )

        ok, err = updater.update(source_url, workspace_id, project)
        if ok:
            updates: dict = {"status": "updated_inventory"}
            if args.clear_errors:
                updates["errors"] = ""
            Storage.update_record(drpid, updates)
            print(f"DRPID={drpid}: OK — sheet updated; status -> updated_inventory")
        else:
            print(f"DRPID={drpid}: FAIL — {err}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
