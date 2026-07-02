"""Reset ADC collector statuses for DRPID range and optionally clear errors."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def reset_collector_range(
    db_path: Path,
    start_drpid: int,
    end_drpid: int,
) -> int:
    """
    Reset projects in a DRPID range to ``sourced`` for recollection.

    Clears ``errors`` and ``warnings`` so the collector starts fresh.

    Args:
        db_path: SQLite database path.
        start_drpid: First DRPID (inclusive).
        end_drpid: Last DRPID (inclusive).

    Returns:
        Number of rows updated.
    """
    connection = sqlite3.connect(db_path)
    cursor = connection.execute(
        """
        UPDATE projects
        SET status = 'sourced', errors = NULL, warnings = NULL
        WHERE DRPID >= ? AND DRPID <= ?
        """,
        (start_drpid, end_drpid),
    )
    updated = cursor.rowcount
    connection.commit()
    connection.close()
    return updated


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "adc.db"
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    end = int(sys.argv[3]) if len(sys.argv) > 3 else 106
    count = reset_collector_range(db, start, end)
    print(f"Reset {count} projects (DRPIDs {start}-{end}) to sourced")
