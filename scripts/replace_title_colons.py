"""Replace colons in project titles with Baserow-style dashes."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.baserow_sheet_utils import replace_colons_in_baserow_title


def replace_title_colons_in_db(db_path: Path, *, dry_run: bool = False) -> int:
    """
    Update ``projects.title`` rows where colon replacement changes the value.

    Args:
        db_path: Path to the SQLite database file.
        dry_run: When True, report changes without writing.

    Returns:
        Number of rows that would be or were updated.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT drpid, title FROM projects WHERE title IS NOT NULL AND trim(title) != ''"
    ).fetchall()

    updates: list[tuple[str, int]] = []
    for row in rows:
        drpid = int(row["drpid"])
        old_title = str(row["title"])
        new_title = replace_colons_in_baserow_title(old_title)
        if new_title != old_title:
            updates.append((new_title, drpid))
            print(f"DRPID={drpid}")
            print(f"  before: {old_title!r}")
            print(f"  after:  {new_title!r}")

    if dry_run or not updates:
        conn.close()
        return len(updates)

    with conn:
        conn.executemany(
            "UPDATE projects SET title = ? WHERE drpid = ?",
            updates,
        )
    conn.close()
    return len(updates)


def main() -> None:
    """CLI entry point for colon-to-dash title updates."""
    parser = argparse.ArgumentParser(
        description="Replace colons in project titles with em dashes / hyphens."
    )
    parser.add_argument("db_path", type=Path, help="Path to SQLite database (e.g. bts.db)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without updating the database",
    )
    args = parser.parse_args()
    count = replace_title_colons_in_db(args.db_path, dry_run=args.dry_run)
    action = "Would update" if args.dry_run else "Updated"
    print(f"{action} {count} row(s) in {args.db_path}")


if __name__ == "__main__":
    main()
