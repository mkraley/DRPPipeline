"""
Delete on-disk project folders for rows with status ``updated_inventory`` and no errors.

Dry-run is the default (lists folders only). Use ``--execute`` to delete.

From repo root:

    python scripts/cleanup_updated_inventory_folders.py
    python scripts/cleanup_updated_inventory_folders.py --db-path usfs.db
    python scripts/cleanup_updated_inventory_folders.py --execute
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utils.file_utils import format_file_size  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"
STATUS_UPDATED_INVENTORY = "updated_inventory"

CANDIDATES_SQL = """
SELECT DRPID, folder_path, status, errors
FROM projects
WHERE status = ?
  AND (errors IS NULL OR TRIM(errors) = '')
ORDER BY DRPID
"""


@dataclass(frozen=True)
class FolderCleanupRow:
    drpid: int
    folder_path: Path
    status: str
    size_bytes: Optional[int]
    note: str


def row_has_no_errors(errors: object) -> bool:
    if errors is None:
        return True
    return not str(errors).strip()


def is_deletable_folder(path: Path) -> bool:
    """Reject empty, relative, or dangerously shallow paths."""
    if not path.is_absolute():
        return False
    if len(path.parts) < 3:
        return False
    return True


def folder_size_bytes(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def evaluate_folder(
    drpid: int,
    folder_path_raw: object,
    *,
    compute_size: bool,
) -> FolderCleanupRow:
    status = STATUS_UPDATED_INVENTORY
    if not folder_path_raw or not str(folder_path_raw).strip():
        return FolderCleanupRow(
            drpid, Path(), status, None, "skip — empty folder_path"
        )

    path = Path(str(folder_path_raw))
    if not is_deletable_folder(path):
        return FolderCleanupRow(drpid, path, status, None, "skip — unsafe or relative path")

    if not path.exists():
        return FolderCleanupRow(drpid, path, status, None, "skip — path does not exist")

    if path.is_file():
        return FolderCleanupRow(drpid, path, status, None, "skip — not a directory")

    size: Optional[int] = None
    if compute_size:
        try:
            size = folder_size_bytes(path)
        except OSError as exc:
            return FolderCleanupRow(
                drpid, path, status, None, f"skip — cannot size folder ({exc})"
            )

    return FolderCleanupRow(drpid, path, status, size, "delete")


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
        if not row_has_no_errors(row["errors"]):
            continue
        planned.append(
            evaluate_folder(
                int(row["DRPID"]),
                row["folder_path"],
                compute_size=compute_size,
            )
        )
    return planned


def delete_folder(path: Path) -> None:
    shutil.rmtree(path)


def print_plan(planned: Iterable[FolderCleanupRow], *, execute: bool) -> None:
    to_delete: List[FolderCleanupRow] = []
    skipped = 0
    for item in planned:
        if item.note == "delete":
            to_delete.append(item)
        else:
            skipped += 1

    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"{mode}: {len(to_delete)} folder(s) to delete, {skipped} skipped")
    print()

    for item in to_delete:
        size_part = ""
        if item.size_bytes is not None:
            size_part = f" ({format_file_size(item.size_bytes)})"
        print(f"  DRPID {item.drpid:6d}  {item.folder_path}{size_part}")

    for item in planned:
        if item.note != "delete":
            path_display = item.folder_path if item.folder_path.parts else "(none)"
            print(f"  DRPID {item.drpid:6d}  {path_display}  — {item.note}")

    if not execute and to_delete:
        print()
        print("Re-run with --execute to delete the folders listed above.")


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
    finally:
        conn.close()

    to_delete = [p for p in planned if p.note == "delete"]
    skipped = len(planned) - len(to_delete)

    print_plan(planned, execute=execute)

    if not execute:
        return 0

    failed = 0
    for item in to_delete:
        try:
            delete_folder(item.folder_path)
            print(f"  deleted DRPID {item.drpid}: {item.folder_path}")
        except OSError as exc:
            failed += 1
            print(
                f"  FAILED DRPID {item.drpid}: {item.folder_path} — {exc}",
                file=sys.stderr,
            )

    print()
    print(
        f"Done: {len(to_delete) - failed} deleted, {failed} failed, {skipped} skipped"
    )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Delete project folders for updated_inventory rows with no errors "
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
