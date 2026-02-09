"""
Export status_notes from DRP Pipeline database to a spreadsheet (CSV).

Gathers all non-empty lines from status_notes across records and outputs
one row per line with columns: DRPID, source_url, title, data_type, url.

Usage:
    python export_status_notes.py [--output OUTPUT] [--db-path PATH]
"""

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import List, Tuple


def parse_status_notes_line(line: str) -> Tuple[str, str, str]:
    """
    Parse a single status_notes line into (title, data_type, url).

    Format: "  title -> data_type" or "  title -> data_type https://url"
    """
    line = line.strip()
    if not line:
        return ("", "", "")
    if " -> " not in line:
        return (line, "", "")
    title, rest = line.split(" -> ", 1)
    title = title.strip()
    rest = rest.strip()
    parts = rest.split(None, 1)
    data_type = parts[0] if parts else ""
    url = parts[1] if len(parts) > 1 else ""
    return (title, data_type, url)


def expand_status_notes_to_rows(
    drpid: int, source_url: str, status_notes: str
) -> List[Tuple[int, str, str, str, str]]:
    """
    Expand status_notes into one row per non-empty line.

    Returns:
        List of (drpid, source_url, title, data_type, url) tuples.
    """
    rows: List[Tuple[int, str, str, str, str]] = []
    seen_urls: set[str] = set()
    for line in status_notes.splitlines():
        line = line.strip()
        if not line:
            continue
        title, data_type, url = parse_status_notes_line(line)
        if data_type == "404":
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        rows.append((drpid, source_url, title, data_type, url))
    return rows


def main() -> None:
    """Export status_notes to CSV spreadsheet."""
    parser = argparse.ArgumentParser(description="Export status_notes to CSV")
    parser.add_argument(
        "--output",
        "-o",
        default="status_notes_export.csv",
        help="Output CSV file path",
    )
    parser.add_argument(
        "--db-path",
        default="drp_pipeline.db",
        help="Database path (default: drp_pipeline.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=__import__("sys").stderr)
        raise SystemExit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT DRPID, source_url, status_notes FROM projects "
        "WHERE status_notes IS NOT NULL AND TRIM(status_notes) != '' "
        "ORDER BY DRPID ASC"
    )
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    all_rows: List[Tuple[int, str, str, str, str]] = []
    for rec in records:
        drpid = rec["DRPID"]
        source_url = rec.get("source_url", "")
        status_notes = rec.get("status_notes") or ""
        rows = expand_status_notes_to_rows(drpid, source_url, status_notes)
        all_rows.extend(rows)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["DRPID", "source_url", "title", "data_type", "url"])
        writer.writerows(all_rows)

    print(f"Exported {len(all_rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
