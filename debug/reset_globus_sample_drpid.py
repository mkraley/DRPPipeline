"""Reset a DRPID to collected - external archive for Globus collector retry."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> None:
    """Reset status and errors for one DRPID."""
    drpid = int(sys.argv[1]) if len(sys.argv) > 1 else 223
    db_path = Path(__file__).resolve().parent.parent / "adc.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE projects SET status = ?, errors = ? WHERE drpid = ?",
        ("collected - external archive", "", drpid),
    )
    conn.commit()
    row = conn.execute(
        "SELECT drpid, status, errors FROM projects WHERE drpid = ?",
        (drpid,),
    ).fetchone()
    conn.close()
    print(row)


if __name__ == "__main__":
    main()
