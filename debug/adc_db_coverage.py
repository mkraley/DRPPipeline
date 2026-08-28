"""Report adc.db coverage for source URLs and DataLumos IDs."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> None:
    db = Path("adc.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    with_dl = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE datalumos_id IS NOT NULL AND TRIM(datalumos_id) <> ''"
    ).fetchone()[0]
    with_url = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE source_url IS NOT NULL AND TRIM(source_url) <> ''"
    ).fetchone()[0]
    with_both = conn.execute(
        """
        SELECT COUNT(*) FROM projects
        WHERE datalumos_id IS NOT NULL AND TRIM(datalumos_id) <> ''
          AND source_url IS NOT NULL AND TRIM(source_url) <> ''
        """
    ).fetchone()[0]
    dl_no_url = conn.execute(
        """
        SELECT COUNT(*) FROM projects
        WHERE datalumos_id IS NOT NULL AND TRIM(datalumos_id) <> ''
          AND (source_url IS NULL OR TRIM(source_url) = '')
        """
    ).fetchone()[0]
    print(f"total={total}")
    print(f"with datalumos_id={with_dl}")
    print(f"with source_url={with_url}")
    print(f"with both={with_both}")
    print(f"datalumos_id but NO source_url={dl_no_url}")
    print("\nTop statuses (has datalumos_id):")
    for row in conn.execute(
        """
        SELECT status, COUNT(*) AS c FROM projects
        WHERE datalumos_id IS NOT NULL AND TRIM(datalumos_id) <> ''
        GROUP BY status ORDER BY c DESC LIMIT 12
        """
    ):
        print(f"  {row['status']}: {row['c']}")
    conn.close()


if __name__ == "__main__":
    main()
