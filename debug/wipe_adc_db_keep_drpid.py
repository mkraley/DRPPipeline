"""Delete all adc.db projects except one DRPID and reset the ID sequence."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def wipe_except(db_path: Path, keep_drpid: int) -> None:
    """
    Remove every project row except ``keep_drpid``.

    Args:
        db_path: SQLite database file.
        keep_drpid: DRPID to retain.
    """
    connection = sqlite3.connect(db_path)
    before = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    connection.execute("DELETE FROM projects WHERE DRPID != ?", (keep_drpid,))
    connection.execute("DELETE FROM sqlite_sequence WHERE name='projects'")
    connection.execute(
        "INSERT INTO sqlite_sequence (name, seq) VALUES ('projects', ?)",
        (keep_drpid,),
    )
    connection.commit()
    after = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    row = connection.execute(
        "SELECT DRPID, status, title FROM projects",
    ).fetchone()
    connection.close()
    print(f"Deleted {before - after} rows; {after} remaining")
    print(f"Kept DRPID {keep_drpid}: {row}")


if __name__ == "__main__":
    keep = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    wipe_except(Path(__file__).resolve().parents[1] / "adc.db", keep)
