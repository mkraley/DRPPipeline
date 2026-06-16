"""
Delete on-disk project folders and clear ``folder_path`` for ``updated_inventory`` rows.

Dry-run is the default (lists folders only). Use ``--execute`` to delete and update DB.

From repo root:

    python scripts/cleanup_updated_inventory_folders.py
    python scripts/cleanup_updated_inventory_folders.py --db-path usfs.db
    python scripts/cleanup_updated_inventory_folders.py --execute

Note: the publisher also deletes folders automatically after a successful sheet
update to ``updated_inventory``. This script is for batch cleanup of existing rows.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utils.file_utils import format_file_size  # noqa: E402
from utils.project_folder_cleanup import (  # noqa: E402
    evaluate_project_folder,
    folder_path_can_be_cleared,
    folder_size_bytes,
    try_delete_project_folder,
)

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"
STATUS_UPDATED_INVENTORY = "updated_inventory"

CANDIDATES_SQL = """
SELECT DRPID, folder_path, status, errors
FROM projects
WHERE status = ?
  AND folder_path IS NOT NULL
  AND TRIM(folder_path) != ''
ORDER BY DRPID
"""


@dataclass(frozen=True)
class FolderCleanupRow:
    drpid: int
    folder_path: Path
    size_bytes: Optional[int]
    note: str  # delete | clear_db | skip — ...


def fetch_candidates(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return list(
        conn.execute(CANDIDATES_SQL, (STATUS_UPDATED_INVENTORY,)).fetchall()
    )


def plan_cleanups(
    rows: Sequence[sqlite3.Row],
    *,
    compute_size: bool = True,
) -> List[FolderCleanupRow]:
    planned: List[FolderCleanupRow] = []
    for row in rows:
        drpid = int(row["DRPID"])
        decision = evaluate_project_folder(
            drpid,
            row["folder_path"],
            compute_size=compute_size,
        )
        path = decision.folder_path or Path()
        if decision.deleted:
            size: Optional[int] = None
            if compute_size and decision.folder_path is not None:
                try:
                    size = folder_size_bytes(decision.folder_path)
                except OSError:
                    size = None
            planned.append(FolderCleanupRow(drpid, path, size, "delete"))
        elif decision.message == "path does not exist":
            planned.append(FolderCleanupRow(drpid, path, None, "clear_db"))
        else:
            planned.append(FolderCleanupRow(drpid, path, None, f"skip — {decision.message}"))
    return planned


def clear_folder_path(conn: sqlite3.Connection, drpid: int) -> None:
    conn.execute(
        "UPDATE projects SET folder_path = NULL WHERE DRPID = ?",
        (drpid,),
    )


def print_plan(planned: Iterable[FolderCleanupRow], *, execute: bool) -> None:
    to_delete = [p for p in planned if p.note == "delete"]
    to_clear = [p for p in planned if p.note == "clear_db"]
    skipped = len(planned) - len(to_delete) - len(to_clear)

    mode = "EXECUTE" if execute else "DRY RUN"
    print(
        f"{mode}: {len(to_delete)} folder(s) to delete, "
        f"{len(to_clear)} row(s) to clear in DB, {skipped} skipped"
    )
    print()

    for item in to_delete:
        size_part = ""
        if item.size_bytes is not None:
            size_part = f" ({format_file_size(item.size_bytes)})"
        print(f"  DRPID {item.drpid:6d}  delete  {item.folder_path}{size_part}")

    for item in to_clear:
        print(f"  DRPID {item.drpid:6d}  clear_db  {item.folder_path}")

    for item in planned:
        if item.note.startswith("skip"):
            path_display = item.folder_path if item.folder_path.parts else "(none)"
            print(f"  DRPID {item.drpid:6d}  {path_display}  — {item.note}")

    if not execute and (to_delete or to_clear):
        print()
        print("Re-run with --execute to apply the actions listed above.")


def run_cleanup(
    db_path: Path,
    *,
    execute: bool,
    compute_size: bool,
) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        planned = plan_cleanups(
            fetch_candidates(conn),
            compute_size=compute_size,
        )
        to_delete = [p for p in planned if p.note == "delete"]
        to_clear = [p for p in planned if p.note == "clear_db"]
        skipped = len(planned) - len(to_delete) - len(to_clear)

        print_plan(planned, execute=execute)

        if not execute:
            return 0

        deleted = 0
        cleared = 0
        failed = 0
        for item in to_delete:
            result = try_delete_project_folder(item.drpid, str(item.folder_path))
            if folder_path_can_be_cleared(result):
                clear_folder_path(conn, item.drpid)
                cleared += 1
                if result.deleted:
                    deleted += 1
                    print(f"  deleted DRPID {item.drpid}: {item.folder_path}")
                else:
                    print(f"  cleared DRPID {item.drpid}: {item.folder_path} (already absent)")
            else:
                failed += 1
                print(
                    f"  FAILED DRPID {item.drpid}: {item.folder_path} — {result.message}",
                    file=sys.stderr,
                )

        for item in to_clear:
            clear_folder_path(conn, item.drpid)
            cleared += 1
            print(f"  cleared DRPID {item.drpid}: {item.folder_path}")

        conn.commit()

        print()
        print(
            f"Done: {deleted} deleted, {cleared} cleared in DB, {failed} failed, {skipped} skipped"
        )
        return 1 if failed else 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Delete project folders and clear folder_path for updated_inventory rows "
            "(dry-run by default)"
        )
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH.name})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete folders (default is dry-run only)",
    )
    parser.add_argument(
        "--no-size",
        action="store_true",
        help="Do not walk folders to compute sizes (faster dry-run)",
    )
    args = parser.parse_args()

    if not args.db_path.is_file():
        print(f"ERROR: database not found: {args.db_path}", file=sys.stderr)
        return 1

    return run_cleanup(
        args.db_path,
        execute=args.execute,
        compute_size=not args.no_size,
    )


if __name__ == "__main__":
    raise SystemExit(main())
