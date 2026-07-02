"""Tally Globus survey lines from adc.db status_notes (read-only)."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

from utils.file_utils import format_file_size

SURVEY_RE = re.compile(
    r"Globus remote inventory:\s*([\d,]+)\s+files in\s*([\d,]+)\s+dirs,\s*"
    r"([\d.]+\s*[KMGT]?B)\s*\(surveyed\s*(\d{4}-\d{2}-\d{2}),\s*path\s*([^)]+)\)",
    re.IGNORECASE,
)
SIZE_TO_BYTES = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}


def parse_size_text(size_text: str) -> int:
    """Convert human-readable size text back to approximate bytes."""
    parts = size_text.strip().split()
    if len(parts) != 2:
        return 0
    value = float(parts[0].replace(",", ""))
    unit = parts[1].upper()
    return int(value * SIZE_TO_BYTES.get(unit, 1))


def main() -> None:
    """Print Globus survey tally from adc.db."""
    db_path = Path(__file__).resolve().parent.parent / "adc.db"
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT drpid, status, status_notes, errors
        FROM projects
        WHERE status = 'collected - external archive'
          AND status_notes LIKE '%Globus remote inventory:%'
        ORDER BY drpid
        """
    ).fetchall()
    conn.close()

    parsed: list[dict[str, object]] = []
    errors: list[tuple[int, str]] = []
    for drpid, status, notes, err in rows:
        match = SURVEY_RE.search(notes or "")
        if not match:
            continue
        files = int(match.group(1).replace(",", ""))
        dirs = int(match.group(2).replace(",", ""))
        size_text = match.group(3)
        path = match.group(5).strip()
        approx_bytes = parse_size_text(size_text)
        parsed.append(
            {
                "drpid": drpid,
                "files": files,
                "dirs": dirs,
                "size_text": size_text,
                "bytes": approx_bytes,
                "path": path,
            }
        )
        if (err or "").strip():
            errors.append((drpid, err.strip()))

    globus_total = conn = None
    conn = sqlite3.connect(db_path)
    globus_eligible = conn.execute(
        """
        SELECT COUNT(*) FROM projects
        WHERE status = 'collected - external archive'
          AND status_notes LIKE '%app.globus.org/file-manager%'
        """
    ).fetchone()[0]
    missing = conn.execute(
        """
        SELECT drpid FROM projects
        WHERE status = 'collected - external archive'
          AND status_notes LIKE '%app.globus.org/file-manager%'
          AND status_notes NOT LIKE '%Globus remote inventory:%'
        ORDER BY drpid
        """
    ).fetchall()
    conn.close()

    total_files = sum(int(r["files"]) for r in parsed)
    total_dirs = sum(int(r["dirs"]) for r in parsed)
    total_bytes = sum(int(r["bytes"]) for r in parsed)

    print(f"Globus external-archive projects: {globus_eligible}")
    print(f"Surveyed (inventory in status_notes): {len(parsed)}")
    print(f"Missing survey: {len(missing)}")
    if missing:
        print("  DRPIDs:", ", ".join(str(r[0]) for r in missing))
    print()
    print(f"Total files: {total_files:,}")
    print(f"Total dirs:  {total_dirs:,}")
    print(f"Total size:  {format_file_size(total_bytes)} ({total_bytes:,} bytes approx)")
    print()

    by_size = sorted(parsed, key=lambda r: int(r["bytes"]), reverse=True)
    print("Top 10 largest:")
    for row in by_size[:10]:
        print(
            f"  DRPID {row['drpid']:>3}: {row['size_text']:>8}  "
            f"{int(row['files']):>2} files  {row['path']}"
        )
    print()
    print("Smallest 5:")
    for row in sorted(parsed, key=lambda r: int(r["bytes"]))[:5]:
        print(
            f"  DRPID {row['drpid']:>3}: {row['size_text']:>8}  "
            f"{int(row['files']):>2} files  {row['path']}"
        )

    # Size bucket histogram
    buckets = {"<20 GB": 0, "20-40 GB": 0, "40-50 GB": 0, ">50 GB": 0}
    for row in parsed:
        gb = int(row["bytes"]) / (1024**3)
        if gb < 20:
            buckets["<20 GB"] += 1
        elif gb < 40:
            buckets["20-40 GB"] += 1
        elif gb <= 50:
            buckets["40-50 GB"] += 1
        else:
            buckets[">50 GB"] += 1
    print()
    print("Size distribution:")
    for label, count in buckets.items():
        print(f"  {label:>10}: {count}")


if __name__ == "__main__":
    main()
