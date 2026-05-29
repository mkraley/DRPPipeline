"""
Normalize time_start and time_end in a USFS projects database.

Run from repo root:
    python scripts/normalize_usfs_db_dates.py
    python scripts/normalize_usfs_db_dates.py --db-path usfs.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.UsfsMetadataExtractor import normalize_temporal_date  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize USFS time_start/time_end in DB")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH.name})",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    updated = 0

    for row in conn.execute(
        "SELECT DRPID, time_start, time_end FROM projects ORDER BY DRPID"
    ):
        drpid = row["DRPID"]
        fields: dict[str, str] = {}
        for key in ("time_start", "time_end"):
            raw = row[key]
            if not raw:
                continue
            normalized = normalize_temporal_date(str(raw))
            if normalized and normalized != raw:
                fields[key] = normalized
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE projects SET {set_clause} WHERE DRPID = ?",
                (*fields.values(), drpid),
            )
            updated += 1
            print(f"DRPID {drpid}: {fields}", file=sys.stderr)

    conn.commit()
    conn.close()
    print(f"Updated {updated} row(s) in {args.db_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
