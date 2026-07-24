"""Inspect AHRQ project titles for cleanup patterns."""

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "ahrq.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT drpid, title FROM projects WHERE title IS NOT NULL AND trim(title) != '' ORDER BY drpid"
    ).fetchall()
    print(f"rows with title: {len(rows)}")
    for drpid, title in rows:
        print(f"{drpid}: {title!r}")


if __name__ == "__main__":
    main()
